#!/usr/bin/env python3
"""Audit the pinned native client experiment without executing attached programs.

Validates exact sources, bounded archive, all attempts/results, fault evidence,
original database bytes and restart. This is consistency, not host attestation.
"""
import argparse
import base64
from datetime import datetime
import gzip
import json
from pathlib import Path
import re
import subprocess
import tarfile

from audit_termux_collection_evidence import check_snapshot, collection_response, receipt, same
from audit_termux_postgres_evidence import AuditError, need, parse_json, sha
import collection_transport as client

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'a1fb66a40f55728ecc5dd4913e2450bde8929473'
ATTEMPTS = {
    'initial': ('normal-two', 'applied', 'imported', 4, 0, None),
    'repeat': ('normal-two', 'applied', 'idempotent', 0, 0, None),
    'extend': ('normal-three', 'applied', 'imported', 2, 1, None),
    'stale': ('normal-two', 'superseded', 'stale', 0, 1, None),
    'revoke': ('normal-revoked', 'quarantined', 'quarantined', 1, 2, 'parent_invalidated'),
    'old-after-revoke': ('normal-two', 'quarantined', 'quarantined', 0, 2, None),
    'foreign-archive': ('foreign-archive', 'unknown', None, 0, 0, None),
    'lost-ack': ('rollback', 'unknown', None, 0, 0, None),
    'lost-ack-retry': ('rollback', 'applied', 'idempotent', 0, 0, None),
    'client-timeout': ('interrupt', 'unknown', None, 0, 0, None),
    'timeout-retry': ('interrupt', 'applied', 'imported', 4, 0, None),
    'concurrent-1': ('concurrent', 'applied', None, None, 0, None),
    'concurrent-2': ('concurrent', 'applied', None, None, 0, None),
    'excess-privilege': ('child', 'unknown', None, 0, 0, None),
    'child': ('child', 'applied', 'imported', 4, 0, None),
    'child-revoked': ('child', 'quarantined', 'quarantined', 0, 0, 'member_quarantined'),
}
BASE_FILES = set('''started-at.txt client-version.txt architecture.txt runner.sha256
postgres.sql postgres_import.sql postgres_collection.sql fixtures.sql fixture-verification.json
collection_transport.py postgres_transport_runtime.py transport-source.json input.sha256
initdb.log postgresql.conf pg_hba.conf startup.log server.log roles.log database.log
apply-base.log apply-importer.log apply-collection.log fixtures.log runtime.log target.json
python-version.txt fault-lost-ack.py fault-lost-ack-input.sha256 fault-lost-ack-underlying.json
fault-before-commit.py fault-before-commit-input.sha256 timeout-observed-wait.json
timeout-owned-backends.json child-invalidation.json runtime-results.json server-settings.txt
before-restart.json after-restart.json shutdown.log result.json SHA256SUMS'''.split())
FILES = BASE_FILES | {f'attempts/{n}/{f}.json' for n in ATTEMPTS for f in ['attempt', 'result']}


def read_archive(path):
    need(path.stat().st_size <= 2_000_000, 'compressed archive bound')
    data, seen, total = {}, set(), 0
    dirs = {'evidence', 'evidence/attempts', 'evidence/__pycache__'} | {'evidence/attempts/' + n for n in ATTEMPTS}
    with tarfile.open(path, 'r:gz') as archive:
        for member in archive:
            need(member.name not in seen and len(seen) < 120, 'duplicate/excessive archive members')
            seen.add(member.name)
            if member.isdir():
                need(member.name in dirs, 'foreign archive directory')
                continue
            name = member.name.removeprefix('evidence/')
            cache = re.fullmatch(r'__pycache__/collection_transport\.cpython-3[0-9]{2}\.pyc', name)
            need(member.isfile() and member.name == 'evidence/' + name
                 and (name in FILES or cache), 'unsafe or foreign archive member')
            total += member.size
            need(0 <= member.size <= 1_000_000 and total <= 10_000_000, 'expanded archive bound')
            data[name] = archive.extractfile(member).read()
    need(FILES <= set(data) and len(set(data) - FILES) <= 1, 'missing files or multiple caches')
    return data


def pinned_inputs():
    runner = subprocess.check_output(['git', '-C', str(ROOT), 'show',
        f'{SOURCE}:migration/nqc-miner/scripts/nqc-miner-sync-check.sh'])
    pattern = (r"base64 -d <<'(NQC_MINER_SYNC_INPUT_\d+)' \| gzip -d > "
               r'"\$MINER_TEST_EVIDENCE/([^"/]+)"\n([A-Za-z0-9+/=\n]+)\n\1\n')
    inputs = {name: gzip.decompress(base64.b64decode(value))
              for _, name, value in re.findall(pattern, runner.decode())}
    need(len(inputs) == 8, 'pinned input inventory')
    return runner, inputs


def expected_ack(p, head, quarantined):
    r = receipt(p)
    return {'schema': 'nqc-miner-collection-ack-v1', 'database_id': p['database_id'],
        'archive_id': p['archive_id'], 'parent_run_id': p['control']['owner']['run_id'],
        'head_sequence': head, 'quarantined': quarantined,
        'stored_receipt': {'receipt_sequence': r['sequence'], 'receipt_sha256': r['sha256'],
            'snapshot_sha256': r['snapshot_sha256'], 'request_sha256': sha(client.jsonb_text(p).encode())}}


def audit(path):
    data = read_archive(path)
    text = lambda n: data[n].decode('utf-8')
    obj = lambda n: parse_json(data[n])
    manifest = {}
    for line in text('SHA256SUMS').splitlines():
        match = re.fullmatch(r'([a-f0-9]{64})  \./([A-Za-z0-9_./-]+)', line)
        need(match is not None, 'manifest syntax')
        digest, name = match.groups()
        need(name in data and name not in manifest and sha(data[name]) == digest, 'manifest file mismatch')
        manifest[name] = digest
    need(set(manifest) == set(data) - {'SHA256SUMS'}, 'manifest inventory')
    runner, inputs = pinned_inputs()
    for name, raw in inputs.items():
        need(data[name] == raw, 'pinned input: ' + name)
    need((ROOT / 'scripts/collection_transport.py').read_bytes() == inputs['collection_transport.py'],
         'local SQL reconstruction client differs from pinned source')
    need(re.fullmatch(sha(runner) + r'  /[^\n]+/nqc-miner-sync-check\.sh\n', text('runner.sha256')), 'runner identity')
    need(text('input.sha256') == ''.join(f'{sha(v)}  {n}\n' for n, v in inputs.items()), 'input manifest')
    flags = {'production_integration': False, 'observer_bridge_enabled': False, 'spending_authorized': False}
    same(obj('result.json'), {'schema': 'nqc-miner-sync-contract-check-v1', 'status': 'pass',
         'data_origin': 'artificial_historical_admission', **flags}, 'runner status')
    source = obj('transport-source.json')
    report = obj('fixture-verification.json')
    fixtures = {name: parse_json(bytes.fromhex(raw)) for name, raw in re.findall(
        r"VALUES \('([^']+)',convert_from\(decode\('([0-9a-f]+)','hex'\),'UTF8'\)::jsonb\);", text('fixtures.sql'))}
    need(len(fixtures) == 12 and set(fixtures) == set(report['fixtures']), 'fixture inventory')
    for name, p in fixtures.items():
        need(sha(client.packed(p) + b'\n') == report['fixtures'][name]['request_sha256'], 'fixture request')
    target = obj('target.json')
    socket = target['socket_directory']
    need(re.fullmatch(r'/data/data/com.termux/files/home/nqc-miner-sync\.[A-Za-z0-9]{6}/s', socket), 'private socket')
    need(re.fullmatch(r'u0_a\d+', target['login_user']) and re.fullmatch(r'[a-f0-9]{64}', target['psql_sha256']), 'target client/user')
    same(target, {'schema': 'nqc-miner-local-postgres-target-v1', 'database_id': report['database_id'],
         'archive_id': fixtures['child']['archive_id'], 'socket_directory': socket, 'port': 55435,
         'login_user': target['login_user'], 'psql': '/data/data/com.termux/files/usr/bin/psql',
         'psql_sha256': target['psql_sha256']}, 'target identity')
    runtime = obj('runtime-results.json')
    need(set(runtime['results']) == set(ATTEMPTS), 'attempt inventory')
    same({k: v for k, v in runtime.items() if k != 'results'},
         {'schema': 'nqc-miner-transport-runtime-v1', 'status': 'pass', 'checks': source['checks'],
          'artificial_fixtures': True, **flags}, 'runtime summary')
    need(len(source['checks']) == 17 and text('runtime.log') == ''.join(
         'MINER_SYNC_PASS: ' + label + '\n' for label in source['checks']), 'runtime check labels')
    for name, (fixture, outcome, status, inserted, head, reason) in ATTEMPTS.items():
        p = fixtures[fixture]; m = report['fixtures'][fixture]['manifest']; r = receipt(p)
        destination = dict(target)
        if name == 'foreign-archive': destination['archive_id'] = p['archive_id']
        if name in ['lost-ack', 'client-timeout']:
            fault = 'lost-ack' if name == 'lost-ack' else 'before-commit'
            destination.update(psql=socket[:-2] + '/fault-' + fault, psql_sha256=sha(data['fault-' + fault + '.py']))
        sql = client.delivery_sql(p, destination)
        same(obj(f'attempts/{name}/attempt.json'), {'schema': 'nqc-miner-delivery-attempt-v1',
            'request_sha256': m['request_sha256'], 'manifest_sha256': sha(client.packed(m) + b'\n'),
            'target_sha256': sha(client.packed(destination)), 'sql_sha256': sha(sql),
            'database_id': destination['database_id'], 'archive_id': destination['archive_id'],
            'parent_run_id': m['run_id'], 'receipt_sha256': m['receipt_sha256'],
            'receipt_sequence': m['receipt_sequence'], 'outcome': 'unknown'}, 'attempt provenance: ' + name)
        value = obj(f'attempts/{name}/result.json')
        same(runtime['results'][name], value, 'durable result: ' + name)
        need(type(value['elapsed_ms']) is int and 0 <= value['elapsed_ms'] <= 120000, 'elapsed bound')
        need(re.fullmatch(r'[a-f0-9]{64}', value['stderr_sha256']), 'stderr hash')
        expected = {'schema': 'nqc-miner-collection-delivery-v1', 'outcome': outcome,
            'commit_confirmed': outcome != 'unknown', 'observer_bridge_enabled': False, 'spending_authorized': False,
            'elapsed_ms': value['elapsed_ms'], 'stderr_sha256': value['stderr_sha256'], 'limited': False,
            'returncode': 0, 'sqlstates': []}
        if outcome == 'unknown':
            expected.update(error_type='DeliveryError', returncode=3)
            if name in ['foreign-archive', 'excess-privilege']: expected['sqlstates'] = ['P0001']
            if name == 'lost-ack': expected['returncode'] = 2
            if name == 'client-timeout':
                expected.update(returncode=-9, limited=True, stderr_sha256=sha(b''))
                need(10000 <= value['elapsed_ms'] <= 20000, 'timeout elapsed evidence')
        else:
            if name.startswith('concurrent-'):
                inserted = value['import_result']['inserted']
                need(type(inserted) is int and inserted in [0, 4], 'concurrent insertion')
                status = 'imported' if inserted == 4 else 'idempotent'
            result = collection_response(p, status, inserted, reason)
            if name in ['stale', 'old-after-revoke']:
                result.pop('reason'); result.pop('receipt_sequence')
            expected.update(import_result=result, acknowledgment=expected_ack(p, head, outcome == 'quarantined'))
        same(value, expected, 'client result: ' + name)
    need(sorted(runtime['results'][f'concurrent-{i}']['import_result']['inserted'] for i in [1, 2]) == [0, 4], 'concurrent idempotency')
    lost = obj('fault-lost-ack-underlying.json')
    same({k: v for k, v in lost.items() if k != 'stdout'}, {'returncode': 0,
         'stderr_sha256': runtime['results']['lost-ack']['stderr_sha256']}, 'underlying client success')
    same([parse_json(line) for line in lost['stdout'].splitlines()],
         [collection_response(fixtures['rollback'], 'imported', 4), expected_ack(fixtures['rollback'], 0, False)], 'lost acknowledgment was committed')
    for fault, fixture in [('lost-ack', 'rollback'), ('before-commit', 'interrupt')]:
        sql = client.delivery_sql(fixtures[fixture], target)
        if fault == 'before-commit': sql = sql.replace(b'\nCOMMIT;\n', b'\nSELECT pg_sleep(30);\nCOMMIT;\n')
        need(text('fault-' + fault + '-input.sha256') == sha(sql) + '\n', 'fault SQL binding')
        # Parse source text only; bytecode and attachments are never imported.
        code = text('fault-' + fault + '.py')
        need(code.startswith('#!/data/data/com.termux/files/usr/bin/python3\n'), 'fault interpreter')
        # The exact template is taken as text from the pinned driver and expanded
        # with only the six fixed literal expressions below, never eval/exec.
        driver = inputs['postgres_transport_runtime.py'].decode()
        template = driver.split("code = f'''", 1)[1].split("'''", 1)[0]
        template = template.replace('\\\\', '\\').replace('{{', '{').replace('}}', '}')
        substitutions = {
            '{sys.executable}': '/data/data/com.termux/files/usr/bin/python3', '{name!r}': repr(fault),
            '{str(client)!r}': repr(target['psql']),
            "{str(evidence / ('fault-' + name + '-input.sha256'))!r}": repr(socket[:-2] + '/evidence/fault-' + fault + '-input.sha256'),
            "{str(evidence / ('fault-' + name + '-underlying.json'))!r}": repr(socket[:-2] + '/evidence/fault-' + fault + '-underlying.json'),
        }
        for old, new in substitutions.items(): template = template.replace(old, new)
        need(code == template, 'fault wrapper differs from pinned driver')
    waiting = obj('timeout-observed-wait.json')
    need(type(waiting['pid']) is int and waiting['pid'] > 0, 'owned backend PID')
    same(waiting, {'pid': waiting['pid'], 'database': 'nqc_miner_v1', 'wait_event': 'PgSleep',
         'application_name': 'nqc_miner_collection_sync'}, 'observed precommit wait')
    terminated = obj('timeout-owned-backends.json')
    need(json.dumps(terminated) in ['[]', '[true]'], 'termination result')
    invalidated = fixtures['child-invalidated']
    same(obj('child-invalidation.json'), {'reason': 'journal_invalidated', 'run_id': invalidated['owner']['run_id'],
         'status': 'quarantined', 'inserted': 1, 'journal_sha256': invalidated['journal_sha256']}, 'independent invalidation')
    need(data['before-restart.json'] == data['after-restart.json'], 'restart bytes differ')
    start = datetime.fromisoformat(text('started-at.txt').strip())
    need(start.tzinfo is not None, 'start timezone')
    counts = check_snapshot(obj('before-restart.json'), fixtures, start, sync=True)
    settings = text('server-settings.txt').splitlines()
    need(len(settings) == 5 and settings[0].startswith('PostgreSQL 18.6 on aarch64-unknown-linux-android,')
         and settings[1:] == ['', socket, 'on', 'on'], 'server settings')
    config = {}
    for line in text('postgresql.conf').splitlines():
        line = line.split('#', 1)[0].strip()
        if line:
            need('=' in line, 'config syntax')
            key, value = line.split('=', 1); config[key.strip()] = value.strip().strip("'")
    required = {'listen_addresses': '', 'unix_socket_directories': socket, 'unix_socket_permissions': '0700',
        'port': '55435', 'shared_buffers': '32MB', 'max_connections': '10', 'max_parallel_workers': '0'}
    allowed = set('dynamic_shared_memory_type max_wal_size min_wal_size log_timezone autovacuum_worker_slots datestyle timezone lc_messages lc_monetary lc_numeric lc_time default_text_search_config fsync synchronous_commit'.split())
    need(set(config) <= set(required) | allowed, 'foreign configuration')
    for k, v in required.items(): need(config.get(k) == v, 'config mismatch: ' + k)
    need(config.get('fsync', 'on') == config.get('synchronous_commit', 'on') == 'on', 'durability configuration')
    hba = [' '.join(l.split()) for l in text('pg_hba.conf').splitlines() if l.strip() and not l.lstrip().startswith('#')]
    same(hba, ['local all all peer', 'host all all 127.0.0.1/32 reject', 'host all all ::1/128 reject',
               'local replication all peer', 'host replication all 127.0.0.1/32 reject', 'host replication all ::1/128 reject'], 'HBA')
    need(text('client-version.txt') == 'psql (PostgreSQL) 18.6\n' and text('architecture.txt') == 'aarch64\n', 'platform')
    need(re.match(r'3\.(1[0-9]|[2-9][0-9])\.', text('python-version.txt')), 'Python version')
    need(text('roles.log').splitlines() == ['CREATE ROLE'] * 3 and data['database.log'] == b'', 'setup identities')
    need('creating directory ' + socket[:-1] + 'data ... ok' in text('initdb.log')
         and 'owned by user "' + target['login_user'] + '"' in text('initdb.log')
         and 'syncing data to disk ... ok' in text('initdb.log'), 'fresh cluster')
    for n in ['initdb.log', 'roles.log', 'apply-base.log', 'apply-importer.log', 'apply-collection.log', 'fixtures.log']:
        need(not re.search(r'ERROR:|FATAL:|PANIC:|FAILED', text(n)), 'setup failure')
    need(text('apply-base.log').splitlines() == ['SET', 'BEGIN', 'DO', 'CREATE SCHEMA', 'REVOKE', 'SET'] + ['CREATE TABLE'] * 6 + ['REVOKE', 'ALTER DEFAULT PRIVILEGES', 'COMMIT'], 'base migration')
    need(text('apply-importer.log').splitlines()[:11] == ['SET', 'BEGIN', 'SET', 'DO', 'CREATE TABLE', 'INSERT 0 1', 'CREATE TABLE', 'CREATE FUNCTION', 'REVOKE', 'REVOKE', 'COMMIT'], 'importer migration')
    need(text('apply-collection.log').splitlines() == ['SET', 'BEGIN', 'SET', 'DO'] + ['CREATE TABLE'] * 4 + ['CREATE FUNCTION', 'CREATE VIEW', 'CREATE VIEW', 'REVOKE', 'REVOKE', 'COMMIT'], 'collection migration')
    need(text('fixtures.log').splitlines() == ['SET', 'CREATE TABLE'] + ['INSERT 0 1'] * 12 + ['UPDATE 1'] + ['GRANT'] * 4, 'fixture setup')
    logs = text('server.log') + text('startup.log')
    same(re.findall(r'\] ERROR:\s+([^\n]+)', logs), ['Collection belongs to a different archive UUID', 'Miner local delivery target rejected'], 'server errors')
    fatal = re.findall(r'\[(\d+)\] FATAL:\s+([^\n]+)', logs)
    expected_fatal = [(str(waiting['pid']), 'terminating connection due to administrator command')] if terminated else []
    same(fatal, expected_fatal, 'owned termination acknowledgment and server log disagree')
    if terminated:
        need(f"[{waiting['pid']}] STATEMENT:  SELECT pg_sleep(30);" in logs, 'termination not bound to precommit pause')
    need('PANIC:' not in logs and 'listening on IPv' not in logs, 'panic or TCP listener')
    for n in ['server.log', 'startup.log']:
        log = text(n)
        for marker in ['database system is ready to accept connections', 'received fast shutdown request',
                       'database system is shut down', f'listening on Unix socket "{socket}/.s.PGSQL.55435"']:
            need(log.count(marker) == 1, 'lifecycle marker: ' + marker)
        need(log.index('ready to accept') < log.index('received fast shutdown') < log.index('database system is shut down'), 'lifecycle order')
    need(re.fullmatch(r'waiting for server to shut down\.+ done\nserver stopped\n', text('shutdown.log')), 'shutdown')
    return {'schema': 'nqc-miner-termux-sync-audit-v1', 'status': 'pass', 'runtime_source_commit': SOURCE,
        'archive_sha256': sha(path.read_bytes()), 'archive_bytes': path.stat().st_size,
        'runner_sha256': sha(runner), 'manifest_files_verified': len(manifest), 'embedded_inputs_verified': len(inputs),
        'client_checks_passed': source['checks'], 'attempts_verified': len(ATTEMPTS), 'snapshot_rows_verified': counts,
        'lost_ack_commit_and_idempotent_retry': True, 'observed_precommit_interruption_and_retry': True,
        'restart_byte_identical': True, 'snapshot_sha256': sha(data['before-restart.json']),
        'final_shutdown_confirmed': True, 'cache_bytes_not_executed': True,
        'data_origin': 'artificial_historical_admission', 'new_rpc_observations': 0,
        'remote_host_attestation': False, **flags}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('archive', type=Path)
    print(json.dumps(audit(p.parse_args().archive), indent=2, sort_keys=True))
