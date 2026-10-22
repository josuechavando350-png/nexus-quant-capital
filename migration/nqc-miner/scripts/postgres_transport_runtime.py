#!/usr/bin/env python3
"""Actual client/PostgreSQL experiment, only inside the new Termux test cluster.

Uses the shipped transport unchanged. Fault wrappers call real psql and discard
an acknowledgment or pause before COMMIT; neither substitutes for a SQL server.
"""
import concurrent.futures
import copy
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import sys
import time

import collection_transport as transport

CHECKS = ['initial_commit_readback', 'repeat_no_duplicates', 'extension_committed',
          'stale_not_current', 'parent_revocation_committed', 'old_receipt_stays_blocked',
          'wrong_target_rejected_before_process', 'foreign_archive_rejected',
          'lost_ack_is_unknown', 'lost_ack_retry_is_idempotent',
          'client_timeout_is_unknown', 'uncommitted_collection_absent', 'timeout_retry_committed',
          'concurrent_clients_one_insertion', 'excessive_writer_privilege_rejected',
          'child_seed_committed', 'independent_child_revocation_propagated']


def main(root):
    root = Path(root).resolve()
    evidence = root / 'evidence'
    transport.need(root.parent == Path('/data/data/com.termux/files/home')
        and re.fullmatch(r'nqc-miner-sync\.[A-Za-z0-9]{6}', root.name), 'dedicated Termux root required')
    client = Path(shutil.which('psql')).resolve()
    target = {'schema': 'nqc-miner-local-postgres-target-v1',
        'database_id': 'dfb1a49f-38d1-40ab-b19d-90a9577271be',
        'archive_id': '9ff8211f-7187-466f-8dfb-46b3df60795d',
        'socket_directory': str(root / 's'), 'port': 55435,
        'login_user': pwd.getpwuid(os.getuid()).pw_name,
        'psql': str(client), 'psql_sha256': transport.sha(client.read_bytes())}
    transport.write_new(evidence / 'target.json', transport.packed(target) + b'\n')
    transport.write_new(evidence / 'python-version.txt', (sys.version + '\n').encode())
    requests = {name: transport.parse(bytes.fromhex(raw)) for name, raw in re.findall(
        r"VALUES \('([^']+)',convert_from\(decode\('([0-9a-f]+)','hex'\),'UTF8'\)::jsonb\);",
        (evidence / 'fixtures.sql').read_text())}
    reports = json.loads((evidence / 'fixture-verification.json').read_bytes())['fixtures']
    bundles = root / 'bundles'; bundles.mkdir(mode=0o700)
    for name, request in requests.items():
        if name == 'child-invalidated': continue
        path = bundles / name; path.mkdir(mode=0o700)
        transport.write_new(path / 'request.json', transport.packed(request) + b'\n')
        transport.write_new(path / 'manifest.json', transport.packed(reports[name]['manifest']) + b'\n')
    attempts = evidence / 'attempts'; attempts.mkdir(mode=0o700)
    checks, results = [], {}

    def check(label, ok):
        transport.need(ok and label not in checks, 'runtime assertion: ' + label)
        checks.append(label)
        print('MINER_SYNC_PASS: ' + label, flush=True)

    def query(sql):
        command = [str(client), '-X', '-w', '-qAt', '-h', str(root / 's'), '-p', '55435',
                   '-U', target['login_user'], '-d', 'nqc_miner_v1', '-v', 'ON_ERROR_STOP=1', '-c', sql]
        result = subprocess.run(command, capture_output=True, timeout=15)
        transport.need(result.returncode == 0, 'owned test query failed')
        return result.stdout.decode().strip()

    def apply(label, fixture, *, configuration=None, timeout=120):
        result = transport.apply_bundle(bundles / fixture, configuration or target, attempts / label, timeout=timeout)
        results[label] = result
        return result

    def accepted(value, outcome, inserted):
        return value['outcome'] == outcome and value['commit_confirmed'] is True and value['import_result']['inserted'] == inserted

    check(CHECKS[0], accepted(apply('initial', 'normal-two'), 'applied', 4))
    check(CHECKS[1], accepted(apply('repeat', 'normal-two'), 'applied', 0))
    check(CHECKS[2], accepted(apply('extend', 'normal-three'), 'applied', 2))
    check(CHECKS[3], accepted(apply('stale', 'normal-two'), 'superseded', 0))
    check(CHECKS[4], accepted(apply('revoke', 'normal-revoked'), 'quarantined', 1))
    check(CHECKS[5], accepted(apply('old-after-revoke', 'normal-two'), 'quarantined', 0))
    wrong = {**target, 'database_id': '00000000-0000-4000-8000-000000000001'}
    rejected = False
    try:
        apply('wrong-target', 'rollback', configuration=wrong)
    except transport.DeliveryError:
        rejected = True
    check(CHECKS[6], rejected and not (attempts / 'wrong-target').exists())
    foreign = {**target, 'archive_id': reports['foreign-archive']['manifest']['archive_id']}
    value = apply('foreign-archive', 'foreign-archive', configuration=foreign)
    check(CHECKS[7], value['outcome'] == 'unknown' and not value['commit_confirmed']
        and query("SELECT count(*) FROM nqc_miner_v1.collection_windows WHERE parent_run_id='pgcoll_normal'") == '3')

    def fault_client(name):
        path = root / ('fault-' + name)
        code = f'''#!{sys.executable}
import hashlib,json,subprocess,sys
from pathlib import Path
raw=sys.stdin.buffer.read()
if {name!r} == 'before-commit':
    if raw.count(b'\\nCOMMIT;\\n') != 1: raise SystemExit(9)
    raw=raw.replace(b'\\nCOMMIT;\\n',b'\\nSELECT pg_sleep(30);\\nCOMMIT;\\n')
Path({str(evidence / ('fault-' + name + '-input.sha256'))!r}).write_text(hashlib.sha256(raw).hexdigest()+'\\n')
result=subprocess.run([{str(client)!r},*sys.argv[1:]],input=raw,capture_output=True)
Path({str(evidence / ('fault-' + name + '-underlying.json'))!r}).write_text(json.dumps({{'returncode':result.returncode,'stdout':result.stdout.decode(),'stderr_sha256':hashlib.sha256(result.stderr).hexdigest()}})+'\\n')
sys.stderr.buffer.write(result.stderr)
if {name!r} == 'lost-ack' and result.returncode == 0:
    sys.stdout.buffer.write(result.stdout.splitlines(keepends=True)[0]);raise SystemExit(2)
sys.stdout.buffer.write(result.stdout);raise SystemExit(result.returncode)
'''
        transport.write_new(path, code.encode()); path.chmod(0o700)
        # Retain the exact injection code independently of the temporary program.
        transport.write_new(evidence / ('fault-' + name + '.py'), code.encode())
        return {**target, 'psql': str(path), 'psql_sha256': transport.sha(path.read_bytes())}

    value = apply('lost-ack', 'rollback', configuration=fault_client('lost-ack'))
    check(CHECKS[8], value['outcome'] == 'unknown' and not value['commit_confirmed']
        and query("SELECT count(*) FROM nqc_miner_v1.eligible_collection_ledger WHERE parent_run_id='pgcoll_rollback'") == '4')
    check(CHECKS[9], accepted(apply('lost-ack-retry', 'rollback'), 'applied', 0))

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(apply, 'client-timeout', 'interrupt',
                              configuration=fault_client('before-commit'), timeout=10)
        waiting = None
        for _ in range(60):
            observed = query("SELECT jsonb_build_object('pid',pid,'wait_event',wait_event,'application_name',application_name,'database',datname) FROM pg_stat_activity WHERE application_name='nqc_miner_collection_sync' AND datname='nqc_miner_v1' AND wait_event='PgSleep'")
            if observed:
                waiting = json.loads(observed)
                break
            if pending.done(): break
            time.sleep(0.05)
        transport.write_new(evidence / 'timeout-observed-wait.json', transport.packed(waiting) + b'\n')
        value = pending.result()
    check(CHECKS[10], waiting is not None and value['outcome'] == 'unknown'
          and value['limited'] and not value['commit_confirmed'])
    # Only the fresh experiment's idle/sleeping client may be terminated. Some
    # PostgreSQL builds notice the disconnect before this query; then it is absent.
    transport.need(type(waiting['pid']) is int, 'owned backend PID')
    terminated = query(f"SELECT coalesce(json_agg(pg_terminate_backend(pid)),'[]'::json) FROM pg_stat_activity WHERE pid={waiting['pid']} AND application_name='nqc_miner_collection_sync' AND datname='nqc_miner_v1' AND wait_event='PgSleep'")
    transport.write_new(evidence / 'timeout-owned-backends.json', (terminated + '\n').encode())
    for _ in range(100):
        if query("SELECT count(*) FROM pg_stat_activity WHERE application_name='nqc_miner_collection_sync' AND datname='nqc_miner_v1'") == '0': break
        time.sleep(0.05)
    absent = query("SELECT NOT EXISTS(SELECT FROM nqc_miner_v1.runs WHERE run_id='pgcoll_interrupt' OR run_id IN (SELECT w->'journal'->'owner'->>'run_id' FROM nqc_miner_v1.test_inputs t CROSS JOIN LATERAL jsonb_array_elements(t.payload->'windows') w WHERE t.name='interrupt'))")
    check(CHECKS[11], absent == 't')
    check(CHECKS[12], accepted(apply('timeout-retry', 'interrupt'), 'applied', 4))

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        pending = [pool.submit(apply, 'concurrent-' + str(i), 'concurrent') for i in [1, 2]]
        values = [future.result() for future in pending]
    check(CHECKS[13], all(v['outcome'] == 'applied' for v in values)
        and sorted(v['import_result']['inserted'] for v in values) == [0, 4])

    query('GRANT UPDATE ON nqc_miner_v1.journal_ledger TO nqc_miner_import_writer')
    try:
        value = apply('excess-privilege', 'child')
        check(CHECKS[14], value['outcome'] == 'unknown' and not value['commit_confirmed']
            and query("SELECT count(*) FROM nqc_miner_v1.collections WHERE parent_run_id='pgcoll_child'") == '0')
    finally:
        query('REVOKE UPDATE ON nqc_miner_v1.journal_ledger FROM nqc_miner_import_writer')
    check(CHECKS[15], accepted(apply('child', 'child'), 'applied', 4))
    invalidation = query("SET ROLE nqc_miner_import_writer; SELECT nqc_miner_v1.import_verified_journal(payload) FROM nqc_miner_v1.test_inputs WHERE name='child-invalidated'")
    transport.write_new(evidence / 'child-invalidation.json', (invalidation + '\n').encode())
    value = apply('child-revoked', 'child')
    check(CHECKS[16], accepted(value, 'quarantined', 0)
        and query("SELECT count(*) FROM nqc_miner_v1.eligible_collection_ledger WHERE parent_run_id='pgcoll_child'") == '0')
    transport.need(checks == CHECKS, 'runtime check inventory')
    transport.write_new(evidence / 'runtime-results.json', transport.packed({
        'schema': 'nqc-miner-transport-runtime-v1', 'status': 'pass', 'checks': checks, 'results': results,
        'artificial_fixtures': True, 'production_integration': False,
        'observer_bridge_enabled': False, 'spending_authorized': False}) + b'\n')
    transport.sync_dir(evidence)


if __name__ == '__main__':
    main(sys.argv[1])
