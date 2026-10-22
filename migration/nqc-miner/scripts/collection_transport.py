#!/usr/bin/env python3
"""Bounded local PostgreSQL collection delivery, with a post-COMMIT readback.

Standard library only. Consumes trusted preparer output, never attached SQL.
An absent/ambiguous acknowledgment is UNKNOWN, never a claim of rollback.
No daemon, discovery, credentials, remote TCP, schema changes or external relay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import selectors
import signal
import stat
import subprocess
import tempfile
import time
import uuid

MAX_REQUEST = 32 * 1024 * 1024
MAX_OUTPUT = 65536
FUNCTION_HASHES = {
    'import_verified_journal': 'ad3e1425c591fe9da04f2510b414d5e01bf019c3cfaaaf4b5f4d401e0e610d2b',
    'import_verified_collection': 'd37463d95edb51b1e74dc735fd86cf1b794493c8d7bd4c9d463fe484df05cde2',
}


class DeliveryError(ValueError):
    pass


def need(ok, message):
    if not ok:
        raise DeliveryError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def packed(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def parse(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'duplicate JSON field')
            result[key] = value
        return result
    def invalid(_):
        raise DeliveryError('nonfinite JSON value')
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)


def safe_path(path, *, new=False):
    path = Path(path)
    need(path.is_absolute() and '..' not in path.parts, 'absolute non-traversing path required')
    for component in [*reversed(path.parents), path]:
        if new and component == path and not os.path.lexists(path):
            continue
        need(not stat.S_ISLNK(component.lstat().st_mode), 'symlink path rejected')
    return path


def read(path, limit):
    path = safe_path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= limit,
             'input is not a bounded private regular file')
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        need(len(raw) <= limit and (before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
             (after.st_size, after.st_mtime_ns, after.st_ctime_ns), 'input changed while reading')
        return raw


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_new(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def canonical_uuid(value):
    need(isinstance(value, str) and str(uuid.UUID(value)) == value and uuid.UUID(value).int,
         'canonical nonzero UUID required')
    return value


def jsonb_text(value):
    # Only integer JSON is admitted, avoiding PostgreSQL/Python float differences.
    if isinstance(value, dict):
        keys = sorted(value, key=lambda k: (len(k.encode()), k.encode()))
        return '{' + ', '.join(jsonb_text(k) + ': ' + jsonb_text(value[k]) for k in keys) + '}'
    if isinstance(value, list):
        return '[' + ', '.join(jsonb_text(v) for v in value) + ']'
    need(value is None or type(value) in (str, int, bool), 'unsupported JSON scalar')
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def validate_target(target):
    need(type(target) is dict and set(target) == {'schema', 'database_id', 'archive_id',
         'socket_directory', 'port', 'login_user', 'psql', 'psql_sha256'}, 'target fields')
    need(target['schema'] == 'nqc-miner-local-postgres-target-v1', 'target schema')
    canonical_uuid(target['database_id']); canonical_uuid(target['archive_id'])
    need(type(target['port']) is int and 1024 <= target['port'] <= 65535, 'target port')
    need(target['login_user'] == pwd.getpwuid(os.getuid()).pw_name and
         re.fullmatch(r'[a-z_][a-z0-9_]{0,62}', target['login_user']), 'peer login identity')
    directory = safe_path(target['socket_directory'])
    info = directory.stat()
    need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and info.st_mode & 0o077 == 0,
         'private owned socket directory required')
    socket = safe_path(directory / f".s.PGSQL.{target['port']}")
    info = socket.stat()
    need(stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid(), 'owned Unix socket required')
    need(sha(read(Path(target['psql']), 32 * 1024 * 1024)) == target['psql_sha256'], 'psql identity changed')


def load_bundle(bundle, target):
    bundle = safe_path(bundle)
    manifest_raw = read(bundle / 'manifest.json', 2 * 1024 * 1024)
    manifest = parse(manifest_raw)
    raw = read(bundle / 'request.json', MAX_REQUEST)
    request = parse(raw)
    need(manifest.get('schema') == request.get('schema') == 'nqc-miner-postgres-collection-v1'
         and manifest.get('complete') is True and manifest.get('namespace') == 'nqc_miner_v1'
         and manifest.get('producer') == 'nqc-miner' and manifest.get('data_class') == 'historical', 'bundle identity')
    for flag in ['database_applied', 'observer_bridge_enabled', 'delivery_enabled',
                 'authenticity_verified', 'live_chain_revalidated']:
        need(manifest.get(flag) is False, 'bundle operational flag')
    need(sha(raw) == manifest['request_sha256'] and raw == packed(request) + b'\n', 'request bytes changed')
    for key in ['archive_id', 'database_id']:
        need(manifest[key] == request[key] == target[key], 'bundle target mismatch')
    run = manifest['run_id']
    need(isinstance(run, str) and re.fullmatch(r'[a-z0-9_-]{1,96}', run)
         and request['control']['owner']['run_id'] == run, 'bundle parent mismatch')
    receipt = parse(bytes.fromhex(request['receipt_hex']))
    snapshot_raw = bytes.fromhex(request['snapshot_hex'])
    snapshot = parse(snapshot_raw)
    need(type(receipt['sequence']) is int and type(manifest['receipt_sequence']) is int
         and 0 <= receipt['sequence'] < 10000, 'receipt sequence')
    fields = {k: v for k, v in receipt.items() if k != 'sha256'}
    canonical = json.dumps(fields, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    need(bytes.fromhex(request['receipt_fields_hex']) == canonical and sha(canonical) == receipt['sha256'], 'receipt hash')
    need(receipt['archive_id'] == target['archive_id'] and receipt['sha256'] == manifest['receipt_sha256']
         and receipt['sequence'] == manifest['receipt_sequence']
         and sha(snapshot_raw) == receipt['snapshot_sha256'] == manifest['snapshot_sha256']
         and receipt['status'] == snapshot['status'] == manifest['status'], 'receipt binding')
    need(snapshot['status'] in {'quarantined', 'verified_historical_snapshot'}
         and snapshot['owner'] == request['control']['owner'], 'snapshot binding')
    need(type(manifest['windows']) is int and len(request['windows']) == manifest['windows'] <= 64,
         'window count')
    records = len(request['control']['records']) + sum(len(w['journal']['records']) for w in request['windows'])
    need(type(manifest['records']) is int and records == manifest['records'] <= 10000, 'record count')
    need(len(jsonb_text(request).encode()) <= MAX_REQUEST, 'jsonb request bound')
    return request, manifest, sha(manifest_raw)


def delivery_sql(request, target):
    """Generate fixed SQL with validated IDs or hex-only payloads, never bundle SQL."""
    run = request['control']['owner']['run_id']
    seq = parse(bytes.fromhex(request['receipt_hex']))['sequence']
    hashes = ','.join(f"('{name}','{digest}')" for name, digest in FUNCTION_HASHES.items())
    return f"""SET search_path = pg_catalog;
SET statement_timeout = '90s';
SET lock_timeout = '5s';
SET ROLE nqc_miner_import_writer;
BEGIN ISOLATION LEVEL READ COMMITTED;
SET LOCAL search_path = pg_catalog;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '90s';
SET LOCAL synchronous_commit = on;
DO $guard$ BEGIN
  IF current_database()<>'nqc_miner_v1' OR current_user<>'nqc_miner_import_writer'
    OR inet_server_addr() IS NOT NULL OR current_setting('listen_addresses')<>''
    OR current_setting('fsync')<>'on' OR current_setting('synchronous_commit')<>'on'
    OR current_setting('server_version_num')::integer<>180006
    OR NOT EXISTS (SELECT FROM nqc_miner_v1.import_identity WHERE singleton
       AND database_id='{target['database_id']}'::uuid AND contract='nqc-miner-postgres-import-v1')
    OR EXISTS (SELECT FROM pg_roles WHERE rolname=current_user AND
       (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls))
    OR EXISTS (SELECT FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
       WHERE n.nspname='nqc_miner_v1' AND c.relkind='r' AND
       has_table_privilege(current_user,c.oid,'UPDATE,DELETE,TRUNCATE'))
    OR EXISTS (SELECT FROM (VALUES {hashes}) wanted(name,digest) WHERE NOT EXISTS (
       SELECT FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
       WHERE n.nspname='nqc_miner_v1' AND p.proname=wanted.name AND p.oid=to_regprocedure('nqc_miner_v1.'||wanted.name||'(jsonb)')
         AND p.proowner=n.nspowner AND NOT p.prosecdef AND p.provolatile='v'
         AND p.proconfig=ARRAY['search_path=pg_catalog']
         AND encode(sha256(convert_to(p.prosrc,'UTF8')),'hex')=wanted.digest)) THEN
    RAISE EXCEPTION 'Miner local delivery target rejected';
  END IF;
END $guard$;
SELECT nqc_miner_v1.import_verified_collection(convert_from(decode('{packed(request).hex()}','hex'),'UTF8')::jsonb);
COMMIT;
SELECT jsonb_build_object(
 'schema','nqc-miner-collection-ack-v1',
 'database_id',(SELECT database_id FROM nqc_miner_v1.import_identity WHERE singleton),
 'parent_run_id','{run}',
 'archive_id',(SELECT archive_id FROM nqc_miner_v1.collections WHERE parent_run_id='{run}'),
 'head_sequence',(SELECT max(receipt_sequence) FROM nqc_miner_v1.collection_receipts WHERE parent_run_id='{run}'),
 'stored_receipt',(SELECT jsonb_build_object('receipt_sha256',receipt_sha256,'snapshot_sha256',snapshot_sha256,
   'request_sha256',request_sha256,'receipt_sequence',receipt_sequence) FROM nqc_miner_v1.collection_receipts
   WHERE parent_run_id='{run}' AND receipt_sequence={seq}),
 'quarantined',EXISTS(SELECT FROM nqc_miner_v1.collection_quarantine WHERE parent_run_id='{run}')
   OR EXISTS(SELECT FROM nqc_miner_v1.import_quarantine WHERE run_id='{run}')
   OR EXISTS(SELECT FROM nqc_miner_v1.collection_windows w JOIN nqc_miner_v1.import_quarantine q ON q.run_id=w.child_run_id WHERE w.parent_run_id='{run}'));
""".encode()


def run_psql(target, sql, timeout):
    need(type(timeout) is int and 1 <= timeout <= 120, 'bounded timeout required')
    # Preserve the platform runtime; discard every ambient libpq/psql setting.
    env = {k: v for k, v in os.environ.items() if not k.startswith(('PG', 'PSQL'))}
    env.update(PGPASSFILE='/dev/null', PGSERVICEFILE='/dev/null', PGCONNECT_TIMEOUT='5',
               PGCLIENTENCODING='UTF8', PGREQUIREAUTH='none', PGREQUIREPEER=target['login_user'],
               PGAPPNAME='nqc_miner_collection_sync', PSQL_PAGER='cat', LC_ALL='C')
    command = [target['psql'], '-X', '-w', '-qAt', '-h', target['socket_directory'],
               '-p', str(target['port']), '-U', target['login_user'], '-d', 'nqc_miner_v1',
               '-v', 'ON_ERROR_STOP=1', '-v', 'VERBOSITY=sqlstate', '-P', 'pager=off', '-f', '-']
    started = time.monotonic()
    with tempfile.TemporaryFile() as source, selectors.DefaultSelector() as selector:
        source.write(sql); source.seek(0)
        process = subprocess.Popen(command, stdin=source, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=env, start_new_session=True)
        buffers = {'stdout': bytearray(), 'stderr': bytearray()}
        for name in buffers:
            stream = getattr(process, name)
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        limited = False
        try:
            while selector.get_map() or process.poll() is None:
                if time.monotonic() - started > timeout:
                    limited = True
                    break
                for key, _ in selector.select(0.02):
                    chunk = os.read(key.fd, min(8192, MAX_OUTPUT + 1 - len(buffers[key.data])))
                    if not chunk:
                        selector.unregister(key.fileobj)
                    else:
                        buffers[key.data].extend(chunk)
                        if len(buffers[key.data]) > MAX_OUTPUT:
                            limited = True
                            break
                if limited:
                    break
            if limited:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait()
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            process.stdout.close(); process.stderr.close()
        out, err = bytes(buffers['stdout']), bytes(buffers['stderr'])
    return {'returncode': process.returncode, 'limited': limited or max(len(out), len(err)) > MAX_OUTPUT,
            'stdout': out, 'stderr_sha256': sha(err),
            'sqlstates': re.findall(rb'(?:ERROR|FATAL):\s+([A-Z0-9]{5})', err),
            'elapsed_ms': round((time.monotonic() - started) * 1000)}


def interpret(stdout, request, manifest, target):
    lines = stdout.splitlines()
    need(len(lines) == 2, 'missing result or post-commit acknowledgment')
    result, ack = map(parse, lines)
    run, seq = manifest['run_id'], manifest['receipt_sequence']
    need(type(result) is dict and result.get('parent_run_id') == run and
         result.get('status') in {'imported', 'idempotent', 'quarantined', 'stale'} and
         type(result.get('inserted')) is int and 0 <= result['inserted'] <= manifest['records'], 'import response')
    need(set(result) in ({'status', 'parent_run_id', 'inserted'},
         {'status', 'parent_run_id', 'inserted', 'receipt_sequence', 'reason'}), 'import response fields')
    if 'receipt_sequence' in result:
        need(type(result['receipt_sequence']) is int and result['receipt_sequence'] == seq, 'result sequence')
        reasons = {'parent_invalidated', 'control_quarantined', 'member_quarantined', 'receipt_conflict',
                   'membership_conflict', 'collection_regressed', 'collector_conflict'}
        need(result['status'] != 'stale' and (result['reason'] in reasons if result['status'] == 'quarantined'
             else result['reason'] is None), 'import reason')
    else:
        need(result['status'] in {'stale', 'quarantined'} and result['inserted'] == 0, 'short import response')
    need(result['status'] != 'idempotent' or result['inserted'] == 0, 'idempotent insertion')
    need(type(ack) is dict and set(ack) == {'schema', 'database_id', 'parent_run_id', 'archive_id',
         'head_sequence', 'stored_receipt', 'quarantined'}, 'acknowledgment fields')
    need(ack['schema'] == 'nqc-miner-collection-ack-v1' and ack['database_id'] == target['database_id']
         and ack['archive_id'] == target['archive_id'] and ack['parent_run_id'] == run
         and type(ack['quarantined']) is bool and type(ack['head_sequence']) is int
         and 0 <= ack['head_sequence'] < 10000, 'acknowledgment identity')
    if ack['quarantined']:
        return 'quarantined', result, ack
    need(result['status'] != 'quarantined', 'quarantine disappeared after commit')
    expected = {'receipt_sha256': manifest['receipt_sha256'], 'snapshot_sha256': manifest['snapshot_sha256'],
                'request_sha256': sha(jsonb_text(request).encode()), 'receipt_sequence': seq}
    if result['status'] == 'stale' or ack['head_sequence'] > seq:
        need(ack['head_sequence'] > seq, 'stale result without newer receipt')
        return 'superseded', result, ack
    need(json.dumps(ack['stored_receipt'], sort_keys=True) == json.dumps(expected, sort_keys=True), 'committed receipt mismatch')
    need(ack['head_sequence'] == seq and manifest['status'] == 'verified_historical_snapshot', 'unexpected active receipt')
    need(set(result) == {'status', 'parent_run_id', 'inserted', 'receipt_sequence', 'reason'}
         and result['reason'] is None and (result['status'] != 'idempotent' or result['inserted'] == 0), 'active result fields')
    return 'applied', result, ack


def apply_bundle(bundle, target, output, *, timeout=120):
    validate_target(target)
    request, manifest, manifest_hash = load_bundle(bundle, target)
    output = safe_path(output, new=True)
    bundle = Path(bundle)
    need(not output.exists() and output != bundle and bundle not in output.parents
         and output not in bundle.parents, 'delivery output must be new and outside bundle')
    sql = delivery_sql(request, target)
    output.mkdir(mode=0o700)
    write_new(output / 'attempt.json', packed({'schema': 'nqc-miner-delivery-attempt-v1',
        'request_sha256': manifest['request_sha256'], 'manifest_sha256': manifest_hash,
        'target_sha256': sha(packed(target)), 'sql_sha256': sha(sql),
        'database_id': target['database_id'], 'archive_id': target['archive_id'],
        'parent_run_id': manifest['run_id'], 'receipt_sha256': manifest['receipt_sha256'],
        'receipt_sequence': manifest['receipt_sequence'], 'outcome': 'unknown'}) + b'\n')
    sync_dir(output); sync_dir(output.parent)
    value = {'schema': 'nqc-miner-collection-delivery-v1', 'outcome': 'unknown',
             'commit_confirmed': False, 'observer_bridge_enabled': False, 'spending_authorized': False}
    try:
        execution = run_psql(target, sql, timeout)
        value.update({k: execution[k] for k in ['returncode', 'limited', 'stderr_sha256', 'elapsed_ms']})
        value['sqlstates'] = [s.decode() for s in execution['sqlstates']]
        need(execution['returncode'] == 0 and not execution['limited'], 'client did not complete')
        need(sha(read(Path(target['psql']), 32 * 1024 * 1024)) == target['psql_sha256'], 'client changed during delivery')
        outcome, result, ack = interpret(execution['stdout'], request, manifest, target)
        value.update(outcome=outcome, commit_confirmed=True, import_result=result, acknowledgment=ack)
    except (DeliveryError, OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
        # Do not reflect raw server messages, SQL or ambient credentials in logs.
        value['error_type'] = type(error).__name__
    write_new(output / 'result.json', packed(value) + b'\n')
    sync_dir(output)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['bundle', 'target', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args()
    try:
        result = apply_bundle(args.bundle, parse(read(args.target, 65536)), args.output, timeout=args.timeout)
    except (DeliveryError, OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
        print(json.dumps({'outcome': 'unknown', 'commit_confirmed': False, 'error_type': type(error).__name__}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return {'applied': 0, 'unknown': 2, 'quarantined': 3, 'superseded': 4}[result['outcome']]


if __name__ == '__main__':
    raise SystemExit(main())
