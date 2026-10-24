#!/usr/bin/env python3
"""Build a self-contained Termux importer test after real Rust fixture verification."""
from __future__ import annotations
import argparse
import base64
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import textwrap

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'research'))
from prepare_postgres_import import prepare_import, packed, OWNER_FIELDS

DATABASE_ID = 'dfb1a49f-38d1-40ab-b19d-90a9577271be'
SOURCE_COMMIT = 'a1d0f150633fda2e5142fe59c0beda924c7bd830'
SCENARIOS = {
    'normal-prefix': ('normal', 2, None), 'normal-full': ('normal', 3, None),
    'empty': ('empty', 0, None), 'uuid': ('uuid', 3, None),
    'conflict-base': ('conflict', 3, None), 'conflict-space': ('conflict', 3, 'line_space'),
    'owner-base': ('owner', 3, None), 'owner-pretty': ('owner', 3, 'owner_pretty'),
    'invalidated-base': ('invalidated', 3, None), 'invalidated-full': ('invalidated', 4, 'invalidation'),
    'gap': ('gap', 3, None), 'outbox': ('outbox', 3, None),
    'payload': ('payload', 3, None), 'rollback': ('rollback', 3, None),
    'concurrent': ('concurrent', 3, None), 'interrupt': ('interrupt', 3, None),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fixtures(verifier):
    original = json.loads((ROOT / 'evidence/postgres-import-preparation-20261022/synthetic-example/request.json').read_bytes())
    requests, reports = {}, {}
    with tempfile.TemporaryDirectory(prefix='nqc-miner-import-fixtures-') as work:
        temp = Path(work)
        for name, (suffix, count, change) in SCENARIOS.items():
            config = json.loads(bytes.fromhex(original['original_config_hex']))
            config['run_id'] = 'pgimp_' + suffix
            owner = copy.deepcopy(original['owner'])
            owner.update(run_id=config['run_id'], config_sha256=sha(packed(config)))
            owner = {key: owner[key] for key in OWNER_FIELDS}
            owner_hash = sha(packed(owner))
            records = [json.loads(bytes.fromhex(row['raw_line_hex']))['record'] for row in original['records']]
            if change == 'invalidation':
                records.append({'kind':'invalidated','chain_id':1,'from_block':10,'reason':'synthetic importer regression'})
            previous = '0' * 64
            lines = []
            for seq, record in enumerate(records[:count]):
                digest = sha(packed([seq, owner_hash, previous, record]))
                line = packed({'sequence':seq,'owner_sha256':owner_hash,'previous_sha256':previous,
                               'record':record,'sha256':digest}) + b'\n'
                if change == 'line_space' and seq == 0:
                    line = b' ' + line
                lines.append(line)
                previous = digest
            state = temp / ('state-' + name)
            state.mkdir()
            (state/'config.json').write_bytes(packed(config))
            (state/'owner.json').write_bytes((json.dumps(owner, indent=2)+'\n').encode() if change=='owner_pretty' else packed(owner))
            (state/'events.jsonl').write_bytes(b''.join(lines))
            output = temp / ('prepared-' + name)
            manifest = prepare_import(state, output, verifier, DATABASE_ID)
            request = (output/'request.json').read_bytes()
            requests[name] = json.loads(request)
            reports[name] = {'request_sha256':sha(request), 'manifest':manifest,
                'rust_verification':json.loads((output/'verified-export/verification.json').read_bytes())}
    return requests, {'schema':'nqc-miner-import-test-fixtures-v1','data_class':'synthetic',
        'candidate_source_commit':SOURCE_COMMIT, 'database_id':DATABASE_ID,
        'fixtures':reports, 'postgres_executed':False, 'economic_evidence':False}


def render(verifier):
    requests, report = fixtures(verifier)
    fixture_sql = ['-- Artificial journals verified by Rust before bundling.\n',
        'SET ROLE nqc_miner_import_owner;\n',
        'CREATE TABLE nqc_miner_v1.test_inputs(name text PRIMARY KEY, payload jsonb NOT NULL);\n']
    for name, request in requests.items():
        fixture_sql.append("INSERT INTO nqc_miner_v1.test_inputs VALUES ('" + name +
            "',convert_from(decode('" + packed(request).hex() + "','hex'),'UTF8')::jsonb);\n")
    fixture_sql += ["UPDATE nqc_miner_v1.import_identity SET database_id='"+DATABASE_ID+"'::uuid;\n",
        'GRANT USAGE ON SCHEMA nqc_miner_v1 TO nqc_miner_import_writer,nqc_miner_import_outsider;\n',
        'GRANT SELECT ON nqc_miner_v1.test_inputs,nqc_miner_v1.import_identity TO nqc_miner_import_writer;\n',
        'GRANT SELECT,INSERT ON nqc_miner_v1.runs,nqc_miner_v1.journal_ledger,nqc_miner_v1.outbox,nqc_miner_v1.import_quarantine TO nqc_miner_import_writer;\n',
        'GRANT EXECUTE ON FUNCTION nqc_miner_v1.import_verified_journal(jsonb) TO nqc_miner_import_writer;\n']
    inputs = {'postgres.sql':(ROOT/'infra/postgres.sql').read_bytes(),
        'postgres_import.sql':(ROOT/'infra/postgres_import.sql').read_bytes(),
        'fixtures.sql':''.join(fixture_sql).encode(),
        'fixture-verification.json':(json.dumps(report,indent=2,sort_keys=True)+'\n').encode(),
        'cases.sql':(ROOT/'scripts/postgres_import_cases.sql').read_bytes(),
        'holder.sql':(ROOT/'scripts/postgres_import_holder.sql').read_bytes()}
    chunks, sums = [], []
    for index,(name,data) in enumerate(inputs.items()):
        marker = 'NQC_MINER_IMPORT_INPUT_' + str(index)
        encoded = '\n'.join(textwrap.wrap(base64.b64encode(gzip.compress(data,mtime=0)).decode(),76))
        chunks.append(f"base64 -d <<'{marker}' | gzip -d > \"$MINER_TEST_EVIDENCE/{name}\"\n{encoded}\n{marker}\n")
        sums.append(f'{sha(data)}  {name}\n')
    chunks.append("cat > \"$MINER_TEST_EVIDENCE/input.sha256\" <<'NQC_MINER_IMPORT_HASHES'\n"+''.join(sums)+'NQC_MINER_IMPORT_HASHES\n')
    # Every successful assertion has one explicit, unique static label.
    import re
    labels = re.findall(r"'([a-z][a-z0-9_]+)'\); -- CASE", inputs['cases.sql'].decode())
    if not labels or len(labels) != len(set(labels)):
        raise ValueError('missing or duplicate test labels')
    template=(ROOT/'scripts/termux_import_check.template.sh').read_text()
    result=template.replace('__EMBEDDED_INPUTS__',''.join(chunks)).replace('__EXPECTED_CASES__',str(len(labels)))
    return result, {name:sha(data) for name,data in inputs.items()}, labels


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verifier',required=True,type=Path)
    args=parser.parse_args()
    script, inputs, labels=render(args.verifier)
    destination=ROOT/'scripts/nqc-miner-import-check.sh'
    destination.write_text(script)
    print(json.dumps({'file':str(destination),'sha256':sha(script.encode()),'input_hashes':inputs,
                      'sql_assertions':len(labels),'labels':labels,'postgres_executed':False},indent=2))


if __name__=='__main__':
    main()
