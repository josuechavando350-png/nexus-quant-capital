#!/usr/bin/env python3
"""Read-only audit of the pinned synthetic Termux importer experiment.

Does not execute attached SQL/scripts, connect to a database, attest the phone,
or certify production integration. Expected bytes come from a pinned Git runner.
"""
import argparse
import base64
from datetime import datetime
import gzip
import json
from pathlib import Path
import re
import subprocess

from audit_termux_postgres_evidence import AuditError, need, parse_json, sha
from audit_termux_postgres_evidence import read_archive as bounded_archive

ROOT = Path(__file__).resolve().parents[1]
SOURCE = '7ee9e9cba98c876c72082580ae2e514867917e6f'
CANDIDATE = 'a1d0f150633fda2e5142fe59c0beda924c7bd830'
FILES = set('''started-at.txt client-version.txt architecture.txt runner.sha256
postgres.sql postgres_import.sql fixtures.sql fixture-verification.json cases.sql
holder.sql input.sha256 initdb.log postgresql.conf pg_hba.conf startup.log server.log
roles.log database.log apply-base.log wrong-database.log apply-importer.log
duplicate-importer.log fixtures.log cases.log writer-denials.log outsider-denial.log
holder.log concurrent-1.json concurrent-2.json concurrent-1.stderr concurrent-2.stderr
concurrency.json interrupted-client.log terminate-session.txt interruption-retry.json
interruption-retry.stderr interruption.json server-settings.txt before-restart.json
after-restart.json shutdown.log result.json SHA256SUMS'''.split())


def read_archive(path):
    return bounded_archive(path, FILES)


def same(actual, expected, label):
    # Python's plain equality treats False == 0 and True == 1.
    need(json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True), label)


def pinned_inputs():
    runner = subprocess.check_output(['git', '-C', str(ROOT), 'show',
        f'{SOURCE}:migration/nqc-miner/scripts/nqc-miner-import-check.sh'])
    pattern = (r'base64 -d <<\'(NQC_MINER_IMPORT_INPUT_\d+)\' \| gzip -d > '
               r'"\$MINER_TEST_EVIDENCE/([^"/]+)"\n([A-Za-z0-9+/=\n]+)\n\1\n')
    inputs = {name: gzip.decompress(base64.b64decode(encoded))
              for _, name, encoded in re.findall(pattern, runner.decode())}
    need(len(inputs) == 6, 'pinned runner inputs missing')
    return runner, inputs


def check_snapshot(snapshot, fixtures, start):
    need(set(snapshot) == {'identity', 'runs', 'ledger', 'outbox', 'quarantine',
                           'registry', 'gates', 'lifecycle'}, 'snapshot tables')
    for table in ['registry', 'gates', 'lifecycle']:
        need(snapshot[table] is None, 'unexpected operational rows')
    same(snapshot['identity'], [{'singleton': True, 'database_id': fixtures['empty']['database_id'],
         'contract': 'nqc-miner-postgres-import-v1'}], 'database identity')
    selected = ['normal-full', 'empty', 'conflict-base', 'owner-base', 'invalidated-full',
                'gap', 'outbox', 'payload', 'rollback', 'concurrent', 'interrupt']
    runs, ledger, outbox, quarantine = [], [], [], []
    for name in selected:
        p = fixtures[name]
        owner, run = p['owner'], p['owner']['run_id']
        runs.append({**{k: owner[k] for k in ['run_id', 'producer', 'namespace', 'data_class',
                      'code_commit', 'config_sha256', 'cargo_lock_sha256']},
                     'owner_sha256': p['owner_sha256'],
                     'original_owner': '\\x' + p['original_owner_hex'],
                     'original_config': '\\x' + p['original_config_hex'],
                     **dict.fromkeys(['observer_bridge_enabled', 'signing_enabled',
                                      'telegram_enabled', 'kms_enabled'], False),
                     'gas_budget_mxn_centavos': 0})
        for r in p['records']:
            seq = r['sequence']
            # These faults are explicitly injected by the pinned cases.sql.
            if name == 'gap' and seq == 1:
                continue
            ledger.append({**{k: r[k] for k in ['sequence', 'record_kind', 'envelope_sha256',
                           'previous_sha256', 'raw_line_sha256']}, 'run_id': run,
                           'data_class': 'synthetic', 'owner_sha256': p['owner_sha256'],
                           'raw_line': '\\x' + r['raw_line_hex']})
            if name == 'outbox' and seq == 1:
                continue
            outbox.append({'run_id': run, 'sequence': seq, 'data_class': 'synthetic',
                           'topic': 'nqc_miner_v1.synthetic.ledger.v1',
                           'message_key': 'nqc_miner_v1/synthetic/' + run,
                           'envelope_sha256': r['envelope_sha256'],
                           'payload': '\\x' + ('00' if name == 'payload' and seq == 1 else r['raw_line_hex']),
                           'delivery_enabled': False, 'delivered_at': None})
    for name, reason in [('conflict-space', 'journal_conflict'), ('owner-pretty', 'owner_conflict'),
                         ('invalidated-full', 'journal_invalidated'), ('gap', 'database_gap'),
                         ('outbox', 'outbox_conflict'), ('payload', 'outbox_conflict')]:
        p = fixtures[name]
        quarantine.append({'run_id': p['owner']['run_id'], 'reason': reason,
                           'incoming_owner_sha256': p['owner_sha256'],
                           'incoming_journal_sha256': p['journal_sha256']})
    counts = {}
    for table, expected, timestamp in [('runs', runs, 'created_at'), ('ledger', ledger, 'imported_at'),
                                       ('outbox', outbox, 'created_at'),
                                       ('quarantine', quarantine, 'quarantined_at')]:
        rows = snapshot[table]
        need(isinstance(rows, list), 'invalid snapshot rows')
        actual = []
        for row in rows:
            need(timestamp in row, 'missing timestamp')
            date = datetime.fromisoformat(row[timestamp])
            need(date.tzinfo is not None and 0 <= (date - start).total_seconds() <= 600,
                 'timestamp outside bounded experiment')
            actual.append({k: v for k, v in row.items() if k != timestamp})
        key = lambda row: (row['run_id'], row.get('sequence', 0))
        same(sorted(actual, key=key), sorted(expected, key=key), 'snapshot mismatch: ' + table)
        counts[table] = len(rows)
    return counts


def audit(path):
    data = read_archive(path)
    text = lambda name: data[name].decode('utf-8')
    manifest = {}
    for line in text('SHA256SUMS').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  \./([A-Za-z0-9_.-]+)', line)
        need(match is not None, 'invalid manifest line')
        digest, name = match.groups()
        need(name in data and name not in manifest, 'invalid manifest member')
        need(sha(data[name]) == digest, 'file hash mismatch: ' + name)
        manifest[name] = digest
    need(set(manifest) == FILES - {'SHA256SUMS'}, 'incomplete manifest')
    runner, inputs = pinned_inputs()
    for name, expected in inputs.items():
        need(data[name] == expected, 'pinned input mismatch: ' + name)
    need(re.fullmatch(sha(runner) + r'  /[^\n]+/nqc-miner-import-check\.sh\n',
                      text('runner.sha256')), 'runner hash mismatch')
    names = ['postgres.sql', 'postgres_import.sql', 'fixtures.sql', 'fixture-verification.json', 'cases.sql', 'holder.sql']
    need(text('input.sha256') == ''.join(f'{sha(inputs[n])}  {n}\n' for n in names), 'input manifest')
    same(parse_json(data['result.json']), {'schema': 'nqc-miner-import-contract-check-v1',
         'status': 'pass', 'data_class': 'synthetic', 'production_integration': False,
         'observer_bridge_enabled': False, 'spending_authorized': False}, 'runner result')
    report = parse_json(inputs['fixture-verification.json'])
    need(report['candidate_source_commit'] == CANDIDATE, 'candidate identity')
    fixtures = {}
    for name, encoded in re.findall(r"VALUES \('([^']+)',convert_from\(decode\('([0-9a-f]+)','hex'\),'UTF8'\)::jsonb\);", text('fixtures.sql')):
        need(name not in fixtures, 'duplicate fixture')
        raw = bytes.fromhex(encoded)
        fixtures[name] = parse_json(raw)
        need(sha(raw + b'\n') == report['fixtures'][name]['request_sha256'], 'fixture request identity')
        need(report['fixtures'][name]['rust_verification']['integrity_verified'] is True,
             'fixture verification absent')
    need(len(fixtures) == 16 and set(fixtures) == set(report['fixtures']), 'fixture count')
    labels = re.findall(r"'([a-z0-9_]+)'\); -- CASE", text('cases.sql'))
    actual_labels = re.findall(r'MINER_IMPORT_PASS: ([a-z0-9_]+)', text('cases.log'))
    need(len(labels) == 35 and len(set(labels)) == 35 and actual_labels == labels, 'SQL checks mismatch')
    need(not re.search(r'ERROR:|FATAL:|PANIC:|FAILED', text('cases.log')), 'unexpected case failure')
    responses = [parse_json(line.strip()) for line in text('cases.log').splitlines() if line.strip().startswith('{')]
    calls = re.findall(r"SELECT pg_temp.expect_import\('([^']+)','([^']+)',(\d+),(NULL|'[^']+'),'([^']+)'\);", text('cases.sql'))
    expected_responses, tips = [], {}
    for name, status, inserted, reason, label in calls:
        p = fixtures[name]
        run = p['owner']['run_id']
        expected = {'run_id': run, 'status': status, 'inserted': int(inserted), 'journal_sha256': p['journal_sha256']}
        if status != 'quarantined':
            tips[run] = max(tips.get(run, 0), len(p['records']))
            expected['stored_records'] = tips[run]
        elif reason != 'NULL':
            expected['reason'] = reason.strip("'")
        expected_responses.append(expected)
    same(responses, expected_responses, 'SQL import response mismatch')
    expected_errors = ['Miner importer requires its dedicated database and schema owner',
                       'relation "import_identity" already exists']
    for filename, state, message in [('wrong-database.log', 'P0001', expected_errors[0]),
                                      ('duplicate-importer.log', '42P07', expected_errors[1])]:
        same(re.findall(r'ERROR:\s+([^\n]+)', text(filename)), [state + ': ' + message], 'guard rejection')
    denials = ['permission denied for table ' + n for n in ['journal_ledger', 'import_quarantine', 'outbox', 'import_identity']]
    outsider = 'permission denied for function import_verified_journal'
    same(re.findall(r'ERROR:\s+([^\n]+)', text('writer-denials.log')), ['42501: ' + n for n in denials], 'writer denials')
    same(re.findall(r'ERROR:\s+([^\n]+)', text('outsider-denial.log')), ['42501: ' + outsider], 'outsider denial')
    need(text('apply-base.log').splitlines() == ['SET', 'BEGIN', 'DO', 'CREATE SCHEMA', 'REVOKE', 'SET'] + ['CREATE TABLE'] * 6 + ['REVOKE', 'ALTER DEFAULT PRIVILEGES', 'COMMIT'], 'base installation')
    need(text('apply-importer.log').splitlines()[:11] == ['SET', 'BEGIN', 'SET', 'DO', 'CREATE TABLE', 'INSERT 0 1', 'CREATE TABLE', 'CREATE FUNCTION', 'REVOKE', 'REVOKE', 'COMMIT'], 'importer installation')
    ids = re.findall(r'^ ([0-9a-f-]{36})$', text('apply-importer.log'), re.M)
    need(len(ids) == 1 and ids[0] != report['database_id'], 'fresh database UUID')
    need(text('fixtures.log').splitlines() == ['SET', 'CREATE TABLE'] + ['INSERT 0 1'] * 16 + ['UPDATE 1'] + ['GRANT'] * 4, 'fixture installation')
    for filename in ['concurrent-1.stderr', 'concurrent-2.stderr', 'interruption-retry.stderr', 'database.log']:
        need(data[filename] == b'', 'unexpected client error')
    def imported(name, status, inserted):
        p = fixtures[name]
        return {'run_id': p['owner']['run_id'], 'status': status, 'inserted': inserted,
                'journal_sha256': p['journal_sha256'], 'stored_records': 3}
    concurrent = [parse_json(data[f'concurrent-{i}.json']) for i in [1, 2]]
    same(sorted(concurrent, key=lambda r: r['inserted']), [imported('concurrent', 'idempotent', 0), imported('concurrent', 'imported', 3)], 'concurrent results')
    need(text('holder.log').count('MINER_IMPORT_BOTH_WAITERS_BLOCKED') == 1 and not re.search(r'ERROR:|FATAL:|PANIC:', text('holder.log')), 'real concurrent waiters')
    same(parse_json(data['concurrency.json']), {'status': 'pass', 'blocked_importers': 2, 'committed_records': 3, 'committed_outbox': 3}, 'concurrency summary')
    same(parse_json(text('interrupted-client.log').splitlines()[0]), imported('interrupt', 'imported', 3), 'uncommitted result')
    same(re.findall(r'FATAL:\s+([^\n]+)', text('interrupted-client.log')), ['57P01: terminating connection due to administrator command'], 'injected backend termination')
    need(text('terminate-session.txt') == 't\n', 'termination confirmation')
    same(parse_json(data['interruption-retry.json']), imported('interrupt', 'imported', 3), 'retry result')
    same(parse_json(data['interruption.json']), {'status': 'pass', 'uncommitted_rows_absent': True, 'retry_records': 3, 'backend_termination_injected': True}, 'rollback confirmation')
    need(data['before-restart.json'] == data['after-restart.json'], 'restart snapshot bytes changed')
    start = datetime.fromisoformat(text('started-at.txt').strip())
    need(start.tzinfo is not None, 'start timezone absent')
    counts = check_snapshot(parse_json(data['before-restart.json']), fixtures, start)
    settings = text('server-settings.txt').splitlines()
    need(len(settings) == 5 and settings[0].startswith('PostgreSQL 18.6 on aarch64-unknown-linux-android,') and settings[1] == '' and settings[3:] == ['on', 'on'], 'runtime server settings')
    socket = settings[2]
    need(re.fullmatch(r'/data/data/com.termux/files/home/nqc-miner-import\.[A-Za-z0-9]{6}/s', socket), 'foreign socket')
    config = {}
    for line in text('postgresql.conf').splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        need('=' in line, 'unrecognized configuration directive')
        key, value = line.split('=', 1)
        config[key.strip()] = value.strip().strip("'")
    required = {'listen_addresses': '', 'unix_socket_directories': socket,
                'unix_socket_permissions': '0700', 'port': '55433',
                'shared_buffers': '32MB', 'max_connections': '10', 'max_parallel_workers': '0'}
    defaults = set('dynamic_shared_memory_type max_wal_size min_wal_size log_timezone autovacuum_worker_slots datestyle timezone lc_messages lc_monetary lc_numeric lc_time default_text_search_config fsync synchronous_commit'.split())
    need(set(config) <= set(required) | defaults, 'unexpected configuration option')
    for key, value in required.items():
        need(config.get(key) == value, 'private cluster config: ' + key)
    need(config.get('fsync', 'on') == 'on' and config.get('synchronous_commit', 'on') == 'on', 'durability config')
    hba = [' '.join(l.split()) for l in text('pg_hba.conf').splitlines() if l.strip() and not l.lstrip().startswith('#')]
    same(hba, ['local all all peer', 'host all all 127.0.0.1/32 reject', 'host all all ::1/128 reject', 'local replication all peer', 'host replication all 127.0.0.1/32 reject', 'host replication all ::1/128 reject'], 'authentication config')
    need(text('client-version.txt') == 'psql (PostgreSQL) 18.6\n' and text('architecture.txt') == 'aarch64\n', 'client platform')
    need(text('roles.log').splitlines() == ['CREATE ROLE'] * 3, 'role creation')
    need('creating directory ' + socket[:-1] + 'data ... ok' in text('initdb.log')
         and 'syncing data to disk ... ok' in text('initdb.log')
         and re.search(r'owned by user "u0_a\d+"', text('initdb.log')), 'owned cluster initialization')
    for filename in ['initdb.log', 'apply-base.log', 'apply-importer.log', 'fixtures.log', 'roles.log']:
        need(not re.search(r'ERROR:|FATAL:|PANIC:|FAILED', text(filename)), 'unexpected setup failure')
    logs = text('server.log') + text('startup.log')
    same(re.findall(r'\] ERROR:\s+([^\n]+)', logs), expected_errors + denials + [outsider], 'unexpected server errors')
    same(re.findall(r'\] FATAL:\s+([^\n]+)', logs), ['terminating connection due to administrator command'], 'unexpected server termination')
    fatal = re.search(r'\[(\d+)\] FATAL:  terminating connection due to administrator command', logs)
    need(fatal and f"[{fatal[1]}] STATEMENT:  BEGIN; SELECT nqc_miner_v1.import_verified_journal(payload) FROM nqc_miner_v1.test_inputs WHERE name='interrupt'; SELECT pg_sleep(60); COMMIT;" in logs, 'termination belongs to owned test statement')
    need('PANIC:' not in logs and 'listening on IPv' not in logs, 'server panic or TCP listener')
    for filename in ['server.log', 'startup.log']:
        log = text(filename)
        for marker in ['database system is ready to accept connections', 'received fast shutdown request', 'database system is shut down', f'listening on Unix socket "{socket}/.s.PGSQL.55433"']:
            need(log.count(marker) == 1, 'missing lifecycle event: ' + marker)
        need(log.index('ready to accept') < log.index('received fast shutdown') < log.index('database system is shut down'), 'server lifecycle order')
    need(text('shutdown.log').splitlines() == ['waiting for server to shut down.... done', 'server stopped'], 'final shutdown missing')
    return {'schema': 'nqc-miner-termux-import-audit-v1', 'status': 'pass',
            'archive_sha256': sha(path.read_bytes()), 'runtime_source_commit': SOURCE,
            'candidate_source_commit': CANDIDATE, 'runner_sha256': sha(runner),
            'manifest_files_verified': len(manifest), 'embedded_inputs_verified': len(inputs),
            'rust_verified_synthetic_fixtures': len(fixtures), 'sql_checks_passed': labels,
            'import_responses_verified': len(responses), 'writer_denials': 4, 'outsider_denials': 1,
            'concurrent_importers': 2, 'backend_interruption_and_retry': True,
            'snapshot_rows_verified': counts, 'restart_byte_identical': True,
            'snapshot_sha256': sha(data['before-restart.json']), 'final_shutdown_confirmed': True,
            'data_class': 'synthetic', 'new_rpc_observations': 0,
            'remote_host_attestation': False, 'production_integration': False,
            'observer_bridge_enabled': False, 'spending_authorized': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.archive), indent=2, sort_keys=True))
