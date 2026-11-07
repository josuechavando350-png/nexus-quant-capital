"""Preserve failed QA evidence without relaxing any positive QA gate."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ARTIFACTS = ('receipt.json','tests.log','COMPLETE.json')
STAGES = ('worker_execution','worker_validation','aggregate','bundle_validation')
ERRORS = ('ValueError','OSError','RuntimeError','TimeoutExpired','KeyError','TypeError')


def need(ok: bool, code: str) -> None:
    if not ok: raise ValueError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def summarize(snapshot: dict, attempts: list[dict], files: dict[str,bytes], stage: str,
              error_type: str) -> dict:
    need(type(snapshot) is dict and snapshot and all(type(k) is str and type(v) is str and
         re.fullmatch('[0-9a-f]{64}',v) for k,v in snapshot.items()),'FAILURE_SOURCE_SCHEMA')
    need(stage in STAGES and error_type in ERRORS and type(attempts) is list and
         1 <= len(attempts) <= 8,'FAILURE_CONTEXT')
    inventory,observed,workers = None,set(),[]
    inventory_conflict = False
    expected_files = {'source-snapshot.json'}
    for index,attempt in enumerate(attempts):
        need(type(attempt) is dict and set(attempt) == {'partition','returncode','available'} and
             type(attempt['partition']) is int and attempt['partition'] == index and
             (attempt['returncode'] is None or type(attempt['returncode']) is int) and
             type(attempt['available']) is list and
             attempt['available'] == [n for n in ARTIFACTS if n in attempt['available']],
             'FAILURE_ATTEMPT_SCHEMA')
        names = {n:f'worker-{index}-{n}' for n in attempt['available']}
        expected_files.update(names.values())
        row = {'partition':index,'returncode':attempt['returncode'],
               'available':attempt['available'],'receipt_status':'UNAVAILABLE',
               'worker_manifest_matches':False,'reported_tests_run':None,
               'recorded_tests':None,'missing_declared_test_ids':None,'unexpected_test_ids':None,
               'duplicate_test_records':None,'counters':None,'source_matches':False}
        if all(n in names for n in ARTIFACTS):
            try:
                marker = strict_json(files[names['COMPLETE.json']])
                row['worker_manifest_matches'] = (canonical(marker) == canonical({
                    'schema_version':1,'sha256':{n:sha(files[names[n]])
                        for n in ('receipt.json','tests.log')}}))
            except (ValueError,TypeError): pass
        if 'receipt.json' in names:
            try:
                receipt = strict_json(files[names['receipt.json']])
                global_ids,declared,tests = (receipt[k] for k in ('global_discovered','discovered','tests'))
                need(type(receipt['schema_version']) is int and receipt['schema_version'] == 1 and
                     type(receipt['partition_count']) is int and receipt['partition_count'] == 8 and
                     type(receipt['partition_index']) is int and receipt['partition_index'] == index,
                     'FAILURE_RECEIPT_IDENTITY')
                for ids in (global_ids,declared):
                    need(type(ids) is list and ids and all(type(i) is str and '.' in i for i in ids)
                         and len(set(ids)) == len(ids),'FAILURE_TEST_INVENTORY')
                need(type(tests) is list and all(type(t) is dict and set(t) == {'id','outcome'} and
                     type(t['id']) is str and t['outcome'] in ('PASS','FAIL','ERROR','SKIP','INCOMPLETE',
                     'EXPECTED_FAILURE','UNEXPECTED_SUCCESS') for t in tests),'FAILURE_TEST_RECORDS')
                counters = {k:receipt[k] for k in ('failures','errors','skipped',
                    'expected_failures','unexpected_successes')}
                need(type(receipt['tests_run']) is int and receipt['tests_run'] >= 0 and
                     all(type(v) is int and v >= 0 for v in counters.values()),'FAILURE_COUNTERS')
                ids = [t['id'] for t in tests]
                row.update(receipt_status='PARSED',reported_tests_run=receipt['tests_run'],
                    recorded_tests=len(ids),missing_declared_test_ids=sorted(set(declared)-set(ids)),
                    unexpected_test_ids=sorted(set(ids)-set(declared)),
                    duplicate_test_records=len(ids)-len(set(ids)),counters=counters,
                    source_matches=(canonical(receipt.get('sources_before')) == canonical(snapshot) ==
                                    canonical(receipt.get('sources_after'))))
                need(set(declared) <= set(global_ids),'FAILURE_DECLARED_INVENTORY')
                if row['source_matches'] and row['worker_manifest_matches']:
                    if inventory is None: inventory = set(global_ids)
                    elif inventory != set(global_ids): inventory_conflict = True
                    observed.update(ids)
            except (ValueError,KeyError,TypeError): row['receipt_status'] = 'MALFORMED'
        workers.append(row)
    need(set(files) == expected_files,'FAILURE_FILE_SET')
    inventory_known = inventory is not None and not inventory_conflict
    return {'schema_version':1,'status':'LOCAL_QA_EXECUTION_FAILED','qa_passed':False,
        'source_digest':sha(canonical(snapshot)),'stage':stage,'error_type':error_type,
        'attempts':attempts,'workers':workers,'worker_count_limit':8,
        'inventory_known':inventory_known,'inventory_conflict':inventory_conflict,
        'declared_total':len(inventory) if inventory_known else None,
        'recorded_unique_declared_tests':len(inventory & observed) if inventory_known else None,
        'not_observed_test_ids':sorted(inventory-observed) if inventory_known else None,
        'counts_are_receipt_claims':True,'tests_rerun_by_verifier':False,
        'producer_authenticated':False,'vulnerability_confirmed':False}


class FailureCapture:
    def __init__(self, output: Path, snapshot: dict):
        self.output = output.with_name(output.name+'.failure')
        if self.output.exists() or self.output.is_symlink():
            raise FileExistsError('failure evidence requires a new output path')
        raw_snapshot = canonical(snapshot)
        self.snapshot = strict_json(raw_snapshot)
        self.files = {'source-snapshot.json':raw_snapshot}
        self.attempts = []

    def record(self, index: int, returncode: int | None, work: Path) -> None:
        if index < len(self.attempts): return
        need(index == len(self.attempts),'FAILURE_WORKER_ORDER')
        available = []
        # Do not follow a replaced worker directory into another evidence tree.
        candidates = () if work.is_symlink() or not work.is_dir() else ARTIFACTS
        for name in candidates:
            try: raw = read_artifact(work,name)
            except (OSError,ValueError): continue
            self.files[f'worker-{index}-{name}'] = raw
            available.append(name)
        self.attempts.append({'partition':index,'returncode':returncode,'available':available})

    def save(self, stage: str, exception: Exception) -> dict:
        error_type = type(exception).__name__
        if error_type not in ERRORS:
            error_type = 'OSError' if isinstance(exception,OSError) else 'RuntimeError'
        report = summarize(self.snapshot,self.attempts,self.files,stage,error_type)
        write_new_bundle(self.output,{**self.files,'failure.json':canonical(report)})
        return report


def verify(root: Path, expected_source: str) -> dict:
    need(root.is_dir() and not root.is_symlink(),'FAILURE_BUNDLE_DIRECTORY')
    need(type(expected_source) is str and re.fullmatch('[0-9a-f]{64}',expected_source),
         'FAILURE_EXTERNAL_SOURCE_REFERENCE')
    marker = strict_json(read_artifact(root,'COMPLETE.json'))
    need(type(marker) is dict and set(marker) == {'schema_version','sha256'} and
         type(marker['schema_version']) is int and marker['schema_version'] == 1 and
         type(marker['sha256']) is dict and {'failure.json','source-snapshot.json'} <= set(marker['sha256']) and
         len(marker['sha256']) <= 26 and {p.name for p in root.iterdir()} == set(marker['sha256'])|{'COMPLETE.json'},
         'FAILURE_BUNDLE_MANIFEST')
    names = set(marker['sha256'])
    need(all(n in ('failure.json','source-snapshot.json') or
         re.fullmatch(r'worker-[0-7]-(receipt\.json|tests\.log|COMPLETE\.json)',n) for n in names),
         'FAILURE_ARTIFACT_NAME')
    files = {n:read_artifact(root,n) for n in names}
    need(all(sha(raw) == marker['sha256'][n] for n,raw in files.items()),'FAILURE_ARTIFACT_HASH')
    report = strict_json(files.pop('failure.json'))
    snapshot = strict_json(files['source-snapshot.json'])
    need(sha(canonical(snapshot)) == expected_source,'FAILURE_SOURCE_REFERENCE')
    rebuilt = summarize(snapshot,report['attempts'],files,report['stage'],report['error_type'])
    need(canonical(rebuilt) == canonical(report),'FAILURE_REPORT_MISMATCH')
    return {'status':'QA_FAILURE_EVIDENCE_VERIFIED','qa_passed':False,
        'source_digest':expected_source,'workers_captured':len(report['attempts']),
        'not_observed_tests':len(report['not_observed_test_ids']) if report['inventory_known'] else None,
        'tests_rerun':False,'vulnerability_confirmed':False}


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Verify failure evidence, never promote QA to PASS')
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--source-digest',required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify(args.bundle,args.source_digest),sort_keys=True))
        return 1  # Valid failure evidence still represents FAILED QA.
    except (ValueError,OSError,TypeError,KeyError):
        print(json.dumps({'status':'QA_FAILURE_EVIDENCE_INVALID','qa_passed':False})); return 2
