#!/usr/bin/env python3
"""Generate artificial collection bundles with real Rust/Polars for Termux."""
import argparse
import base64
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'research'))
import archive_collection as archive
import prepare_postgres_collection as collection
import prepare_postgres_import as journal
import test_archive_collection as fixture

DATABASE_ID = 'dfb1a49f-38d1-40ab-b19d-90a9577271be'
ARCHIVE_ID = '9ff8211f-7187-466f-8dfb-46b3df60795d'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class FixtureClock:
    @staticmethod
    def now(tz):
        return datetime(2026, 10, 22, tzinfo=timezone.utc)


def fixtures(verifier):
    topic = json.loads(subprocess.check_output([str(verifier), 'topics']))['aave-v3'][0]
    requests, reports = {}, {}
    with tempfile.TemporaryDirectory(prefix='nqc-miner-collection-fixtures-') as work:
        root = Path(work)
        clock = archive.datetime
        archive.datetime = FixtureClock  # Synthetic receipts only, for repeatable bytes.
        try:
            def prepare(name, state, store, config, aid=ARCHIVE_ID):
                archive.archive_collection(state, store, verifier)
                output = root / ('prepared-' + name)
                manifest = collection.prepare_collection(store, output, verifier, aid, DATABASE_ID, config['run_id'])
                raw = (output / 'request.json').read_bytes()
                requests[name] = json.loads(raw)
                reports[name] = {'request_sha256': sha(raw), 'manifest': manifest,
                    'rust_verification': json.loads((output / 'verification.json').read_bytes())}

            def state_for(name, aid=ARCHIVE_ID):
                state, store = root / ('state-' + name), root / ('archive-' + name)
                config = fixture.fixture(state, topic, run_id='pgcoll_' + name)
                archive.init_archive(store, aid)
                return state, store, config

            state, store, config = state_for('normal')
            prepare('normal-two', state, store, config)
            fixture.fixture(state, topic, windows=3, run_id=config['run_id'])
            prepare('normal-three', state, store, config)
            fixture.journal(state, config, [{'kind': 'invalidated', 'chain_id': 1, 'from_block': 10,
                                            'reason': 'artificial parent revocation with missing child'}])
            shutil.rmtree(state / 'window-00000000000000000001')
            prepare('normal-revoked', state, store, config)
            for name in ['rollback', 'concurrent', 'interrupt', 'child', 'conflict']:
                state, store, config = state_for(name)
                prepare(name, state, store, config)
                if name == 'child':
                    path = state / 'window-00000000000000000000'
                    cfg = json.loads((path / 'config.json').read_bytes())
                    records = [json.loads(l)['record'] for l in (path / 'events.jsonl').read_bytes().splitlines()]
                    records.append({'kind': 'invalidated', 'chain_id': 1, 'from_block': 10,
                                    'reason': 'artificial independent child invalidation'})
                    fixture.journal(path, cfg, records)
                    output = root / 'prepared-child-invalidated'
                    manifest = journal.prepare_import(path, output, verifier, DATABASE_ID)
                    raw = (output / 'request.json').read_bytes()
                    requests['child-invalidated'] = json.loads(raw)
                    reports['child-invalidated'] = {'request_sha256': sha(raw), 'manifest': manifest,
                        'rust_verification': json.loads((output / 'verified-export/verification.json').read_bytes())}
                if name == 'conflict':
                    other = root / 'archive-conflicting-receipt'; archive.init_archive(other, ARCHIVE_ID)
                    path = state / 'window-00000000000000000000'
                    cfg = json.loads((path / 'config.json').read_bytes())
                    records = [json.loads(l)['record'] for l in (path / 'events.jsonl').read_bytes().splitlines()]
                    records[0]['observed_at'] += 1
                    fixture.journal(path, cfg, records)
                    prepare('conflicting-receipt', state, other, config)
            state, store, config = state_for('revoked_first')
            fixture.journal(state, config, [{'kind': 'invalidated', 'chain_id': 1, 'from_block': 10,
                                            'reason': 'artificial revocation before first import'}])
            prepare('revoked-first', state, store, config)
            foreign_id = str(uuid.UUID('21ce0f48-4a6a-479b-b7be-c04fa193a156'))
            state, store, config = state_for('foreign', foreign_id)
            # Same root identity as normal, different explicitly owned archive.
            shutil.rmtree(state); config = fixture.fixture(state, topic, run_id='pgcoll_normal')
            prepare('foreign-archive', state, store, config, foreign_id)
        finally:
            archive.datetime = clock
    return requests, {'schema': 'nqc-miner-collection-fixtures-v1',
        'data_origin': 'artificial fixtures; historical class exercises collector admission only',
        'database_id': DATABASE_ID, 'fixtures': reports, 'postgres_executed': False,
        'economic_evidence': False, 'new_rpc_observations': 0,
        'source_hashes': {n: sha((ROOT / n).read_bytes()) for n in [
            'research/prepare_postgres_collection.py', 'infra/postgres_collection.sql',
            'research/archive_collection.py', 'research/prepare_postgres_import.py', 'research/test_archive_collection.py']}}


def render(verifier):
    requests, report = fixtures(verifier)
    sql = ['-- Invented historical-admission fixtures, not market observations.\n',
           'SET ROLE nqc_miner_import_owner;\n',
           'CREATE TABLE nqc_miner_v1.test_inputs(name text PRIMARY KEY,payload jsonb NOT NULL);\n']
    for name, request in requests.items():
        sql.append("INSERT INTO nqc_miner_v1.test_inputs VALUES ('" + name + "',convert_from(decode('" +
                   journal.packed(request).hex() + "','hex'),'UTF8')::jsonb);\n")
    sql += [f"UPDATE nqc_miner_v1.import_identity SET database_id='{DATABASE_ID}'::uuid;\n",
        'GRANT USAGE ON SCHEMA nqc_miner_v1 TO nqc_miner_import_writer,nqc_miner_import_outsider;\n',
        'GRANT SELECT ON ALL TABLES IN SCHEMA nqc_miner_v1 TO nqc_miner_import_writer;\n',
        'GRANT INSERT ON nqc_miner_v1.runs,nqc_miner_v1.journal_ledger,nqc_miner_v1.outbox,nqc_miner_v1.import_quarantine,nqc_miner_v1.collections,nqc_miner_v1.collection_windows,nqc_miner_v1.collection_receipts,nqc_miner_v1.collection_quarantine TO nqc_miner_import_writer;\n',
        'GRANT EXECUTE ON FUNCTION nqc_miner_v1.import_verified_journal(jsonb),nqc_miner_v1.import_verified_collection(jsonb) TO nqc_miner_import_writer;\n']
    inputs = {n: (ROOT / 'infra' / n).read_bytes() for n in ['postgres.sql', 'postgres_import.sql', 'postgres_collection.sql']}
    inputs.update({'fixtures.sql': ''.join(sql).encode(),
                   'fixture-verification.json': (json.dumps(report, indent=2, sort_keys=True)+'\n').encode(),
                   'cases.sql': (ROOT / 'scripts/postgres_collection_cases.sql').read_bytes(),
                   'holder.sql': (ROOT / 'scripts/postgres_collection_holder.sql').read_bytes()})
    chunks, sums = [], []
    for index, (name, data) in enumerate(inputs.items()):
        marker = 'NQC_MINER_COLLECTION_INPUT_' + str(index)
        encoded = '\n'.join(textwrap.wrap(base64.b64encode(gzip.compress(data, mtime=0)).decode(), 76))
        chunks.append(f"base64 -d <<'{marker}' | gzip -d > \"$MINER_TEST_EVIDENCE/{name}\"\n{encoded}\n{marker}\n")
        sums.append(f'{sha(data)}  {name}\n')
    chunks.append("cat > \"$MINER_TEST_EVIDENCE/input.sha256\" <<'NQC_COLLECTION_HASHES'\n" + ''.join(sums) + 'NQC_COLLECTION_HASHES\n')
    labels = re.findall(r"'([a-z][a-z0-9_]+)'\); -- CASE", inputs['cases.sql'].decode())
    if not labels or len(labels) != len(set(labels)): raise ValueError('invalid case labels')
    template = (ROOT / 'scripts/termux_collection_check.template.sh').read_text()
    return template.replace('__EMBEDDED_INPUTS__', ''.join(chunks)).replace('__EXPECTED_CASES__', str(len(labels))), inputs, labels


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verifier', type=Path, required=True)
    args = parser.parse_args()
    script, inputs, labels = render(args.verifier)
    target = ROOT / 'scripts/nqc-miner-collection-check.sh'; target.write_text(script)
    print(json.dumps({'file': str(target), 'sha256': sha(script.encode()), 'sql_assertions': len(labels),
                      'labels': labels, 'input_hashes': {n: sha(raw) for n, raw in inputs.items()},
                      'postgres_executed': False}, indent=2))
