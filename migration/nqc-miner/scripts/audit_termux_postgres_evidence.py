#!/usr/bin/env python3
"""Audit a returned Termux contract-test archive without executing its contents.

This verifies consistency and source binding of user-supplied evidence. It is not
remote host attestation, a fresh PostgreSQL execution, or importer certification.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = '6a89668b5c326a0e120288a0631204ec4a082827'
FILES = set('started-at.txt client-version.txt architecture.txt runner.sha256 postgres.sql cases.sql input.sha256 initdb.log postgresql.conf pg_hba.conf startup.log server.log roles.log database.log wrong-database.log apply-schema.log duplicate-schema.log cases.log writer-denials.log server-settings.txt before-restart.json after-restart.json shutdown.log result.json SHA256SUMS'.split())


class AuditError(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise AuditError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source_bytes(name):
    return subprocess.check_output(['git', '-C', str(ROOT), 'show',
        f'{SOURCE}:migration/nqc-miner/{name}'])


def read_archive(path):
    need(path.stat().st_size <= 2_000_000, 'compressed archive too large')
    result = {}
    seen = set()
    total = 0
    with tarfile.open(path, 'r:gz') as archive:
        for member in archive:
            need(member.name not in seen, 'duplicate archive member')
            seen.add(member.name)
            need(len(seen) <= 100, 'too many archive members')
            if member.isdir():
                need(member.name == 'evidence', 'unexpected directory')
                continue
            need(member.isfile(), 'non-regular archive member')
            need(re.fullmatch(r'evidence/[A-Za-z0-9_.-]+', member.name), 'unsafe archive path')
            total += member.size
            need(total <= 10_000_000 and member.size <= 1_000_000, 'expanded archive too large')
            result[member.name.removeprefix('evidence/')] = archive.extractfile(member).read()
    need(set(result) == FILES, 'unexpected or missing evidence files')
    return result


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        need(key not in value, 'duplicate JSON key')
        value[key] = item
    return value


def parse_json(data):
    def invalid(value):
        raise AuditError('non-finite JSON value')
    return json.loads(data, object_pairs_hook=unique_object, parse_constant=invalid)


def audit(path):
    data = read_archive(path)
    text = lambda name: data[name].decode('utf-8')
    manifest = {}
    for line in text('SHA256SUMS').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  \./([A-Za-z0-9_.-]+)', line)
        need(match is not None, 'invalid file manifest')
        digest, name = match.groups()
        need(name not in manifest and name in data, 'invalid manifest member')
        need(sha(data[name]) == digest, 'file hash mismatch: ' + name)
        manifest[name] = digest
    need(set(manifest) == FILES - {'SHA256SUMS'}, 'incomplete manifest')
    for target, source in [('postgres.sql', 'infra/postgres.sql'), ('cases.sql', 'scripts/postgres_contract_cases.sql')]:
        need(data[target] == source_bytes(source), 'SQL source mismatch')
    runner_hash = sha(source_bytes('scripts/nqc-miner-postgres-check.sh'))
    need(re.fullmatch(runner_hash + r'  /[^\n]+/nqc-miner-postgres-check\.sh\n', text('runner.sha256')), 'runner hash mismatch')
    need(text('input.sha256') == ''.join(f'{sha(data[name])}  {name}\n' for name in ['postgres.sql', 'cases.sql']), 'input manifest mismatch')
    expected_result = {'schema': 'nqc-miner-postgres-contract-check-v1', 'status': 'pass',
        'data_class': 'synthetic', 'production_integration': False,
        'observer_bridge_enabled': False, 'spending_authorized': False}
    result = parse_json(data['result.json'])
    need(result == expected_result, 'runner did not report the expected pass')
    need(all(result[name] is False for name in ['production_integration', 'observer_bridge_enabled', 'spending_authorized']), 'ambiguous result flags')
    statements = re.findall(r'SELECT pg_temp\.(?:check_ok|reject_sql)\(.*?\);', text('cases.sql'), re.S)
    labels = [re.search(r",\s*'([a-z0-9_]+)'\);$", s).group(1) for s in statements]
    actual = re.findall(r'MINER_PASS: ([a-z0-9_]+)', text('cases.log'))
    need(len(labels) == 30 and len(set(labels)) == 30 and actual == labels, 'missing, duplicate or incorrect SQL checks')
    need('ERROR:' not in text('cases.log') and 'FAILED' not in text('cases.log'), 'unexpected SQL failure')
    apply = text('apply-schema.log').splitlines()
    need(apply == ['SET', 'BEGIN', 'DO', 'CREATE SCHEMA', 'REVOKE', 'SET'] + ['CREATE TABLE'] * 6 + ['REVOKE', 'ALTER DEFAULT PRIVILEGES', 'COMMIT'], 'schema application not complete')
    for name, states in [('wrong-database.log', ['P0001']), ('duplicate-schema.log', ['42P06']), ('writer-denials.log', ['42501'] * 3)]:
        need(re.findall(r'ERROR:\s+([A-Z0-9]{5}):', text(name)) == states, 'unexpected rejection reason: ' + name)
    need('Refusing foreign database: expected nqc_miner_v1' in text('wrong-database.log'), 'foreign-database guard missing')
    need(text('roles.log').splitlines() == ['CREATE ROLE'] * 3 and data['database.log'] == b'', 'role/database setup differs')
    settings = text('server-settings.txt').splitlines()
    need(len(settings) == 5 and settings[0].startswith('PostgreSQL 18.6 on aarch64-unknown-linux-android,'), 'unexpected server identity')
    need(settings[1] == '' and settings[3:] == ['on', 'on'], 'network/durability settings differ')
    need(re.fullmatch(r'/data/data/com\.termux/files/home/nqc-miner-check\.[A-Za-z0-9]{6}/s', settings[2]), 'unexpected socket location')
    need(text('client-version.txt') == 'psql (PostgreSQL) 18.6\n' and text('architecture.txt') == 'aarch64\n', 'client/platform identity differs')
    config = {}
    for line in text('postgresql.conf').splitlines():
        line = line.split('#', 1)[0].strip()
        if '=' in line:
            key, value = line.split('=', 1)
            config[key.strip()] = value.strip().strip("'")
    for key, value in {'listen_addresses': '', 'unix_socket_directories': settings[2], 'unix_socket_permissions': '0700', 'port': '55432', 'shared_buffers': '32MB', 'max_connections': '10', 'max_parallel_workers': '0'}.items():
        need(config.get(key) == value, 'configuration mismatch: ' + key)
    rules = [line.split() for line in text('pg_hba.conf').splitlines() if line.strip() and not line.lstrip().startswith('#')]
    need(len(rules) == 6 and all((r[0] == 'local' and r[-1] == 'peer') or (r[0] == 'host' and r[-1] == 'reject') for r in rules), 'authentication configuration differs')
    need(data['before-restart.json'] == data['after-restart.json'], 'restart changed persisted rows')
    rows = parse_json(data['after-restart.json'])
    need(set(rows) == {'runs', 'ledger', 'outbox', 'registry'} and all(isinstance(v, list) and len(v) == 1 for v in rows.values()), 'unexpected persisted fixture counts')
    need(all(v[0]['run_id'] == 'pg_contract_synthetic' and v[0]['data_class'] == 'synthetic' for v in rows.values()), 'foreign fixture identity')
    need(all(type(rows[name][0]['sequence']) is int and rows[name][0]['sequence'] == 0 for name in ['ledger', 'outbox']), 'rolled-back rows survived')
    need(rows['ledger'][0]['raw_line'] == rows['outbox'][0]['payload'] == r'\x000aff80', 'binary payload changed')
    need(rows['outbox'][0]['delivery_enabled'] is False and rows['outbox'][0]['delivered_at'] is None, 'outbox activated')
    need(rows['registry'][0]['lifecycle_state'] == 'detected', 'live lifecycle state')
    need(all(rows['runs'][0][key] is False for key in ['observer_bridge_enabled', 'signing_enabled', 'telegram_enabled', 'kms_enabled']), 'safety flag changed')
    need(type(rows['runs'][0]['gas_budget_mxn_centavos']) is int and rows['runs'][0]['gas_budget_mxn_centavos'] == 0, 'spending enabled')
    for name in ['server.log', 'startup.log']:
        need('database system is ready to accept connections' in text(name) and 'database system is shut down' in text(name), 'missing startup/shutdown: ' + name)
        need('FATAL:' not in text(name) and 'PANIC:' not in text(name), 'unexpected fatal server error')
        need('listening on Unix socket "' + settings[2] + '/.s.PGSQL.55432"' in text(name), 'server socket differs')
    need(len(re.findall(r'\] ERROR:', text('server.log'))) == 5 and '] ERROR:' not in text('startup.log'), 'unexpected server error count')
    need(text('shutdown.log').splitlines() == ['waiting for server to shut down.... done', 'server stopped'], 'final shutdown not confirmed')
    started = datetime.fromisoformat(text('started-at.txt').strip().replace('Z', '+00:00'))
    need(started.tzinfo is not None, 'missing execution timezone')
    return {'schema': 'nqc-miner-termux-postgres-evidence-audit-v1', 'status': 'pass',
        'audited_at_utc': datetime.now(timezone.utc).isoformat(), 'source_commit': SOURCE,
        'archive_sha256': sha(path.read_bytes()), 'archive_bytes': path.stat().st_size,
        'manifest_files_verified': len(manifest), 'total_evidence_files': len(data),
        'runner_sha256': runner_hash, 'sql_sha256': sha(data['postgres.sql']),
        'cases_sha256': sha(data['cases.sql']), 'execution_started_at_utc': started.isoformat(),
        'server_version': '18.6', 'platform': 'aarch64-unknown-linux-android',
        'sql_checks_passed': labels, 'writer_mutations_rejected': 3,
        'wrong_database_rejected': True, 'existing_schema_rejected': True,
        'snapshot_sha256': sha(data['after-restart.json']), 'restart_bytes_unchanged': True,
        'final_shutdown_confirmed': True, 'tcp_listener_enabled': False,
        'execution_origin': 'user-operated Termux; agent audited returned files offline',
        'cryptographic_host_attestation': False, 'data_class': 'synthetic',
        'real_journal_importer_executed': False, 'production_integration': False,
        'observer_bridge_enabled': False, 'spending_authorized': False,
        'economic_certification': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.archive), indent=2))
