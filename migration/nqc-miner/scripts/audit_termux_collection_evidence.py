#!/usr/bin/env python3
"""Read-only audit of the pinned artificial Termux collection experiment.

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
SOURCE = 'e4700af5bed905e6b071d93cbc17f7489521b342'
FILES = set('''started-at.txt client-version.txt architecture.txt runner.sha256
postgres.sql postgres_import.sql postgres_collection.sql fixtures.sql fixture-verification.json cases.sql
holder.sql input.sha256 initdb.log postgresql.conf pg_hba.conf startup.log server.log
roles.log database.log apply-base.log wrong-database.log apply-importer.log
apply-collection.log duplicate-collection.log fixtures.log cases.log writer-denials.log outsider-denial.log
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
        f'{SOURCE}:migration/nqc-miner/scripts/nqc-miner-collection-check.sh'])
    pattern = (r'base64 -d <<\'(NQC_MINER_COLLECTION_INPUT_\d+)\' \| gzip -d > '
               r'"\$MINER_TEST_EVIDENCE/([^"/]+)"\n([A-Za-z0-9+/=\n]+)\n\1\n')
    inputs = {name: gzip.decompress(base64.b64decode(encoded))
              for _, name, encoded in re.findall(pattern, runner.decode())}
    need(len(inputs) == 7, 'pinned runner inputs missing')
    return runner, inputs


def receipt(p):
    return parse_json(bytes.fromhex(p['receipt_hex']))


def collection_response(p, status, inserted, reason=None):
    return {'parent_run_id': p['control']['owner']['run_id'], 'status': status,
            'inserted': inserted, 'reason': reason, 'receipt_sequence': receipt(p)['sequence']}


def jsonb_text(value):
    """Reproduce jsonb's text representation for these bounded integer fixtures.

    Object keys are ordered by UTF-8 byte length, then bytes. Reject floats rather
    than silently applying Python's different numeric formatting. This is not a
    general PostgreSQL numeric/encoding compatibility layer.
    """
    if isinstance(value, dict):
        keys = sorted(value, key=lambda k: (len(k.encode('utf-8')), k.encode('utf-8')))
        return '{' + ', '.join(jsonb_text(k) + ': ' + jsonb_text(value[k]) for k in keys) + '}'
    if isinstance(value, list):
        return '[' + ', '.join(jsonb_text(v) for v in value) + ']'
    need(value is None or type(value) in (str, int, bool), 'unsupported fixture JSON scalar')
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def check_snapshot(snapshot, fixtures, start):
    expected = {k: [] for k in ['runs', 'ledger', 'outbox', 'quarantine', 'collections',
                               'windows', 'receipts', 'revocations']}
    journals = {}
    selected = ['normal-three', 'child', 'conflict', 'rollback', 'concurrent', 'interrupt', 'revoked-first']
    for name in selected:
        p = fixtures[name]
        parent = p['control']['owner']['run_id']
        r = receipt(p)
        expected['collections'].append({'parent_run_id': parent, 'archive_id': p['archive_id'],
            'collection_key': r['collection_key'], 'collector_bytes': '\\x' + p['collector_hex']})
        journals[parent] = p['control']
        for w in p['windows']:
            journal = w['journal']
            child = journal['owner']['run_id']
            need(child not in journals, 'repeated child identity in pinned fixtures')
            journals[child] = journal
            expected['windows'].append({'parent_run_id': parent, 'window_index': w['index'],
                'child_run_id': child, 'journal_sha256': journal['journal_sha256'],
                'record_count': len(journal['records'])})
    # Later invalidations append evidence without changing original membership.
    for p in [fixtures['normal-revoked']['control'], fixtures['child-invalidated']]:
        journals[p['owner']['run_id']] = p
    for run, p in journals.items():
        owner = p['owner']
        expected['runs'].append({**{k: owner[k] for k in ['run_id', 'producer', 'namespace',
            'data_class', 'code_commit', 'config_sha256', 'cargo_lock_sha256']},
            'owner_sha256': p['owner_sha256'], 'original_owner': '\\x' + p['original_owner_hex'],
            'original_config': '\\x' + p['original_config_hex'],
            **dict.fromkeys(['observer_bridge_enabled', 'signing_enabled', 'telegram_enabled', 'kms_enabled'], False),
            'gas_budget_mxn_centavos': 0})
        for r in p['records']:
            expected['ledger'].append({**{k: r[k] for k in ['sequence', 'record_kind',
                'envelope_sha256', 'previous_sha256', 'raw_line_sha256']}, 'run_id': run,
                'data_class': owner['data_class'], 'owner_sha256': p['owner_sha256'],
                'raw_line': '\\x' + r['raw_line_hex']})
            expected['outbox'].append({'run_id': run, 'sequence': r['sequence'],
                'data_class': owner['data_class'], 'topic': 'nqc_miner_v1.historical.ledger.v1',
                'message_key': 'nqc_miner_v1/historical/' + run,
                'envelope_sha256': r['envelope_sha256'], 'payload': '\\x' + r['raw_line_hex'],
                'delivery_enabled': False, 'delivered_at': None})
        if any(r['record_kind'] == 'invalidated' for r in p['records']):
            expected['quarantine'].append({'run_id': run, 'reason': 'journal_invalidated',
                'incoming_owner_sha256': p['owner_sha256'], 'incoming_journal_sha256': p['journal_sha256']})
    for name in ['normal-two', 'normal-three', 'normal-revoked', 'child', 'conflict',
                 'rollback', 'concurrent', 'interrupt', 'revoked-first']:
        p = fixtures[name]
        r = receipt(p)
        expected['receipts'].append({'parent_run_id': p['control']['owner']['run_id'],
            'receipt_sequence': r['sequence'], 'receipt_sha256': r['sha256'],
            'snapshot_sha256': r['snapshot_sha256'], 'source_status': r['status'],
            'applied_status': 'quarantined' if name in ['normal-revoked', 'revoked-first'] else 'verified',
            'original_receipt': '\\x' + p['receipt_hex'], 'original_snapshot': '\\x' + p['snapshot_hex'],
            'request_sha256': sha(jsonb_text(p).encode('utf-8'))})
    for name, reason in [('normal-revoked', 'parent_invalidated'), ('revoked-first', 'parent_invalidated'),
                         ('child', 'member_quarantined'), ('conflicting-receipt', 'receipt_conflict')]:
        p = fixtures[name]
        expected['revocations'].append({'parent_run_id': p['control']['owner']['run_id'],
            'reason': reason, 'receipt_sha256': receipt(p)['sha256'],
            'control_journal_sha256': p['control']['journal_sha256']})
    need(set(snapshot) == set(expected) | {'identity', 'registry', 'gates', 'lifecycle',
         'eligible_ledger', 'eligible_outbox'}, 'snapshot tables')
    same(snapshot['identity'], [{'singleton': True, 'database_id': fixtures['child']['database_id'],
         'contract': 'nqc-miner-postgres-import-v1'}], 'database identity')
    for table in ['registry', 'gates', 'lifecycle']:
        need(snapshot[table] is None, 'unexpected operational rows')
    timestamps = {'runs': 'created_at', 'ledger': 'imported_at', 'outbox': 'created_at',
                  'quarantine': 'quarantined_at', 'collections': 'created_at',
                  'receipts': 'imported_at', 'revocations': 'quarantined_at'}
    ordered = lambda rows: sorted(rows, key=lambda r: json.dumps(r, sort_keys=True))
    counts = {}
    for table, rows in expected.items():
        need(isinstance(snapshot[table], list), 'invalid snapshot rows')
        actual = []
        for row in snapshot[table]:
            need(isinstance(row, dict), 'invalid snapshot row')
            timestamp = timestamps.get(table)
            if timestamp:
                need(timestamp in row, 'missing timestamp')
                date = datetime.fromisoformat(row[timestamp])
                need(date.tzinfo is not None and 0 <= (date - start).total_seconds() <= 600,
                     'timestamp outside bounded experiment')
            actual.append({k: v for k, v in row.items() if k != timestamp})
        same(ordered(actual), ordered(rows), 'snapshot mismatch: ' + table)
        counts[table] = len(rows)
    # Eligibility is reconstructed from the expected membership/revocations, and
    # includes the exact timestamps of the already verified original rows.
    members = {w['child_run_id']: w for w in expected['windows']
               if w['parent_run_id'] in {'pgcoll_rollback', 'pgcoll_concurrent', 'pgcoll_interrupt'}}
    for table in ['ledger', 'outbox']:
        rows = [{**row, **{k: members[row['run_id']][k] for k in ['parent_run_id', 'window_index']}}
                for row in snapshot[table] if row['run_id'] in members]
        same(ordered(snapshot['eligible_' + table]), ordered(rows), 'eligibility mismatch: ' + table)
        counts['eligible_' + table] = len(rows)
    counts['identity'] = 1
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
    need(re.fullmatch(sha(runner) + r'  /[^\n]+/nqc-miner-collection-check\.sh\n',
                      text('runner.sha256')), 'runner hash mismatch')
    names = ['postgres.sql', 'postgres_import.sql', 'postgres_collection.sql', 'fixtures.sql', 'fixture-verification.json', 'cases.sql', 'holder.sql']
    need(text('input.sha256') == ''.join(f'{sha(inputs[n])}  {n}\n' for n in names), 'input manifest')
    same(parse_json(data['result.json']), {'schema': 'nqc-miner-collection-contract-check-v1',
         'status': 'pass', 'data_origin': 'artificial_historical_admission', 'production_integration': False,
         'observer_bridge_enabled': False, 'spending_authorized': False}, 'runner result')
    report = parse_json(inputs['fixture-verification.json'])
    for name, digest in report['source_hashes'].items():
        need(sha(subprocess.check_output(['git', '-C', str(ROOT), 'show',
             f'{SOURCE}:migration/nqc-miner/{name}'])) == digest, 'fixture source identity')
    fixtures = {}
    for name, encoded in re.findall(r"VALUES \('([^']+)',convert_from\(decode\('([0-9a-f]+)','hex'\),'UTF8'\)::jsonb\);", text('fixtures.sql')):
        need(name not in fixtures, 'duplicate fixture')
        raw = bytes.fromhex(encoded)
        fixtures[name] = parse_json(raw)
        need(sha(raw + b'\n') == report['fixtures'][name]['request_sha256'], 'fixture request identity')
        verification = report['fixtures'][name]['rust_verification']
        if name in ['normal-revoked', 'revoked-first']:
            need(verification['status'] == 'quarantined', 'fixture revocation status')
            verification = verification['control']
        need(verification['integrity_verified'] is True, 'fixture verification absent')
    need(len(fixtures) == 12 and set(fixtures) == set(report['fixtures']), 'fixture count')
    labels = re.findall(r"'([a-z0-9_]+)'\); -- CASE", text('cases.sql'))
    actual_labels = re.findall(r'MINER_COLLECTION_PASS: ([a-z0-9_]+)', text('cases.log'))
    need(len(labels) == 33 and len(set(labels)) == 33 and actual_labels == labels, 'SQL checks mismatch')
    need(not re.search(r'ERROR:|FATAL:|PANIC:|FAILED', text('cases.log')), 'unexpected case failure')
    responses = [parse_json(line.strip()) for line in text('cases.log').splitlines() if line.strip().startswith('{')]
    calls = re.findall(r"SELECT pg_temp.expect_import\('([^']+)','([^']+)',(\d+),'([^']+)'\);", text('cases.sql'))
    reasons = {'parent_revocation_imported': 'parent_invalidated',
               'revocation_before_any_child_import': 'parent_invalidated',
               'child_quarantine_propagates_on_replay': 'member_quarantined',
               'same_sequence_changed_receipt_quarantined': 'receipt_conflict'}
    short = {'old_receipt_cannot_regress', 'old_bundle_never_reactivates',
             'repeat_revocation', 'conflicting_collection_stays_quarantined'}
    expected_responses = []
    for name, status, inserted, label in calls:
        expected = collection_response(fixtures[name], status, int(inserted), reasons.get(label))
        if label in short:
            expected.pop('reason')
            expected.pop('receipt_sequence')
        expected_responses.append(expected)
    need(len(calls) == 14, 'pinned import response count')
    same(responses, expected_responses, 'SQL import response mismatch')
    expected_errors = ['Miner collection migration requires its dedicated database and owner',
                       'relation "collections" already exists']
    for filename, state, message in [('wrong-database.log', 'P0001', expected_errors[0]),
                                      ('duplicate-collection.log', '42P07', expected_errors[1])]:
        same(re.findall(r'ERROR:\s+([^\n]+)', text(filename)), [state + ': ' + message], 'guard rejection')
    denials = ['permission denied for table ' + n for n in ['journal_ledger', 'collection_quarantine', 'collection_windows', 'collections']]
    outsider = 'permission denied for function import_verified_collection'
    same(re.findall(r'ERROR:\s+([^\n]+)', text('writer-denials.log')), ['42501: ' + n for n in denials], 'writer denials')
    same(re.findall(r'ERROR:\s+([^\n]+)', text('outsider-denial.log')), ['42501: ' + outsider], 'outsider denial')
    need(text('apply-base.log').splitlines() == ['SET', 'BEGIN', 'DO', 'CREATE SCHEMA', 'REVOKE', 'SET'] + ['CREATE TABLE'] * 6 + ['REVOKE', 'ALTER DEFAULT PRIVILEGES', 'COMMIT'], 'base installation')
    need(text('apply-importer.log').splitlines()[:11] == ['SET', 'BEGIN', 'SET', 'DO', 'CREATE TABLE', 'INSERT 0 1', 'CREATE TABLE', 'CREATE FUNCTION', 'REVOKE', 'REVOKE', 'COMMIT'], 'importer installation')
    same(text('apply-collection.log').splitlines(), ['SET', 'BEGIN', 'SET', 'DO'] +
         ['CREATE TABLE'] * 4 + ['CREATE FUNCTION', 'CREATE VIEW', 'CREATE VIEW', 'REVOKE', 'REVOKE', 'COMMIT'], 'collection installation')
    ids = re.findall(r'^ ([0-9a-f-]{36})$', text('apply-importer.log'), re.M)
    need(len(ids) == 1 and ids[0] != report['database_id'], 'fresh database UUID')
    need(text('fixtures.log').splitlines() == ['SET', 'CREATE TABLE'] + ['INSERT 0 1'] * 12 + ['UPDATE 1'] + ['GRANT'] * 4, 'fixture installation')
    for filename in ['concurrent-1.stderr', 'concurrent-2.stderr', 'interruption-retry.stderr', 'database.log']:
        need(data[filename] == b'', 'unexpected client error')
    def imported(name, status, inserted):
        return collection_response(fixtures[name], status, inserted)
    concurrent = [parse_json(data[f'concurrent-{i}.json']) for i in [1, 2]]
    same(sorted(concurrent, key=lambda r: r['inserted']), [imported('concurrent', 'idempotent', 0), imported('concurrent', 'imported', 4)], 'concurrent results')
    need(text('holder.log').count('MINER_COLLECTION_BOTH_WAITERS_BLOCKED') == 1 and not re.search(r'ERROR:|FATAL:|PANIC:', text('holder.log')), 'real concurrent waiters')
    same(parse_json(data['concurrency.json']), {'status': 'pass', 'blocked_importers': 2, 'committed_records': 4, 'committed_outbox': 4}, 'concurrency summary')
    same(parse_json(text('interrupted-client.log').splitlines()[0]), imported('interrupt', 'imported', 4), 'uncommitted result')
    same(re.findall(r'FATAL:\s+([^\n]+)', text('interrupted-client.log')), ['57P01: terminating connection due to administrator command'], 'injected backend termination')
    need(text('terminate-session.txt') == 't\n', 'termination confirmation')
    same(parse_json(data['interruption-retry.json']), imported('interrupt', 'imported', 4), 'retry result')
    same(parse_json(data['interruption.json']), {'status': 'pass', 'uncommitted_rows_absent': True, 'retry_records': 4, 'backend_termination_injected': True}, 'rollback confirmation')
    need(data['before-restart.json'] == data['after-restart.json'], 'restart snapshot bytes changed')
    start = datetime.fromisoformat(text('started-at.txt').strip())
    need(start.tzinfo is not None, 'start timezone absent')
    counts = check_snapshot(parse_json(data['before-restart.json']), fixtures, start)
    settings = text('server-settings.txt').splitlines()
    need(len(settings) == 5 and settings[0].startswith('PostgreSQL 18.6 on aarch64-unknown-linux-android,') and settings[1] == '' and settings[3:] == ['on', 'on'], 'runtime server settings')
    socket = settings[2]
    need(re.fullmatch(r'/data/data/com.termux/files/home/nqc-miner-collection\.[A-Za-z0-9]{6}/s', socket), 'foreign socket')
    config = {}
    for line in text('postgresql.conf').splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        need('=' in line, 'unrecognized configuration directive')
        key, value = line.split('=', 1)
        config[key.strip()] = value.strip().strip("'")
    required = {'listen_addresses': '', 'unix_socket_directories': socket,
                'unix_socket_permissions': '0700', 'port': '55434',
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
    for filename in ['initdb.log', 'apply-base.log', 'apply-importer.log', 'apply-collection.log', 'fixtures.log', 'roles.log']:
        need(not re.search(r'ERROR:|FATAL:|PANIC:|FAILED', text(filename)), 'unexpected setup failure')
    logs = text('server.log') + text('startup.log')
    same(re.findall(r'\] ERROR:\s+([^\n]+)', logs), expected_errors + denials + [outsider], 'unexpected server errors')
    same(re.findall(r'\] FATAL:\s+([^\n]+)', logs), ['terminating connection due to administrator command'], 'unexpected server termination')
    fatal = re.search(r'\[(\d+)\] FATAL:  terminating connection due to administrator command', logs)
    need(fatal and f"[{fatal[1]}] STATEMENT:  BEGIN; SELECT nqc_miner_v1.import_verified_collection(payload) FROM nqc_miner_v1.test_inputs WHERE name='interrupt'; SELECT pg_sleep(60); COMMIT;" in logs, 'termination belongs to owned test statement')
    need('PANIC:' not in logs and 'listening on IPv' not in logs, 'server panic or TCP listener')
    for filename in ['server.log', 'startup.log']:
        log = text(filename)
        for marker in ['database system is ready to accept connections', 'received fast shutdown request', 'database system is shut down', f'listening on Unix socket "{socket}/.s.PGSQL.55434"']:
            need(log.count(marker) == 1, 'missing lifecycle event: ' + marker)
        need(log.index('ready to accept') < log.index('received fast shutdown') < log.index('database system is shut down'), 'server lifecycle order')
    need(text('shutdown.log').splitlines() == ['waiting for server to shut down.... done', 'server stopped'], 'final shutdown missing')
    return {'schema': 'nqc-miner-termux-collection-audit-v1', 'status': 'pass',
            'archive_sha256': sha(path.read_bytes()), 'runtime_source_commit': SOURCE,
            'runner_sha256': sha(runner), 'archive_bytes': path.stat().st_size,
            'manifest_files_verified': len(manifest), 'embedded_inputs_verified': len(inputs),
            'rust_verified_artificial_fixtures': len(fixtures), 'sql_checks_passed': labels,
            'import_responses_verified': len(responses), 'writer_denials': 4, 'outsider_denials': 1,
            'concurrent_importers': 2, 'backend_interruption_and_retry': True,
            'snapshot_rows_verified': counts, 'restart_byte_identical': True,
            'snapshot_sha256': sha(data['before-restart.json']), 'final_shutdown_confirmed': True,
            'data_origin': 'artificial_historical_admission', 'new_rpc_observations': 0,
            'remote_host_attestation': False, 'production_integration': False,
            'observer_bridge_enabled': False, 'spending_authorized': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.archive), indent=2, sort_keys=True))
