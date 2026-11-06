"""Compare public verification against an explicit, trusted local baseline checkout.

Fixtures use bulk-loaded synthetic capture snapshots; this is not a write-throughput test.
Both interpreters verify the same public bytes after issuer stores have been removed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

PACKAGE = Path(__file__).resolve().parents[1]


def worker(package, root, repetitions):
    sys.path.insert(0, str(package))
    import platform
    import resource
    from nqc_defense.codec import canonical
    from nqc_defense.registry_mirror import RegistryMirror
    request = json.loads((root/'request.json').read_bytes())
    mirror = RegistryMirror(root/'mirror',request['registry_digest'],request['authority_digest'])
    attestation = (root/'attestation.json').read_bytes(); dossier = (root/'dossier.json').read_bytes()
    args = (request['mirror_receipt'],request['registration'],attestation,request['attestation_digest'],
            dossier,request['dossier_digest'],request['pins'])
    samples = []; reports = set(); cpu_start = time.process_time()
    for _ in range(repetitions+1):
        started = time.perf_counter(); report = mirror.verify(*args)
        samples.append(time.perf_counter()-started)
        reports.add(hashlib.sha256(canonical(report)).hexdigest())
    if len(reports) != 1: raise AssertionError('unstable verification report')
    sources = {}
    for name in ('signer_registry.py','registry_mirror.py','dossier_attestation.py'):
        sources[name] = hashlib.sha256((package/'nqc_defense'/name).read_bytes()).hexdigest()
    return {'cold_seconds':samples[0],'warm_seconds':samples[1:],
            'warm_median_seconds':statistics.median(samples[1:]),'report_digest':reports.pop(),
            'cpu_seconds':time.process_time()-cpu_start,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'python':platform.python_version(),'platform':platform.platform(),'source_sha256':sources,
            'repetitions':repetitions,'private_issuer_stores_present':any((root/x).exists() for x in
                ('policy','signer','authority','operations','registry'))}


def prepare(root, count):
    sys.path.insert(0, str(PACKAGE)); sys.path.insert(0, str(PACKAGE/'tools'))
    from check_signer_registry import fixture
    from nqc_defense.codec import canonical
    from nqc_defense.dossier_attestation import attest_dossier, public_bytes
    from nqc_defense.files import sha256
    from nqc_defense.registry_mirror import EMPTY, RegistryMirror
    from nqc_defense.signer_registry import ORIGIN, row_head, signed_row
    f = fixture(root); registry = f['registry']
    head = registry.change(f['authority'],'activate',f['key_pin'],'activate','Benchmark signer',ORIGIN,
                           public_bytes(f['signing_key']))['receipt']
    original = json.loads(f['dossier']); rows = []
    for index in range(1,count):
        dossier = canonical({**original,'captured_ns':original['captured_ns']+index})
        data = attest_dossier(dossier,sha256(dossier),f['pins'],f['policy'].key,f['signing_key'],f['key_pin'])
        event = registry._event('record',f['key_pin'],f'fixture_{index}','Synthetic benchmark capture',
            attestation_digest=sha256(data),dossier_digest=sha256(dossier),pins=f['pins'])
        row = signed_row(f['authority'],head['revision']+1,head['head'],event)
        rows.append(row); head = {'revision':row[0],'head':row_head(row)}
    with registry.connection(write=True) as db: db.executemany('INSERT INTO entries VALUES(?,?,?,?)',rows)
    bundle = registry.export(head); mirror = RegistryMirror.create(root/'mirror',registry.digest,f['authority_pin'])
    accepted = mirror.accept(bundle,sha256(bundle),head,EMPTY)['receipt']
    request = {'registry_digest':registry.digest,'authority_digest':f['authority_pin'],
               'mirror_receipt':accepted,'registration':head,'attestation_digest':sha256(data),
               'dossier_digest':sha256(dossier),'pins':f['pins']}
    (root/'request.json').write_bytes(canonical(request))
    (root/'attestation.json').write_bytes(data); (root/'dossier.json').write_bytes(dossier)
    for name in ('operations','policy','signer','authority','registry'): shutil.rmtree(root/name)
    f['log'].unlink(); (root/'evidence.json').unlink()
    return {'rows':count,'bundle_bytes':len(bundle),'bulk_prepared_records':count-1,
            'all_rows_added_via_record_api':False,'private_issuer_stores_removed':True}


def run(baseline, repetitions=12, sizes=(512,4096)):
    baseline = baseline.resolve()
    if baseline == PACKAGE: raise ValueError('baseline must be a distinct trusted checkout')
    if not 3 <= repetitions <= 100: raise ValueError('repetitions must be between 3 and 100')
    if any(type(count) is not int or not 2 <= count <= 4096 for count in sizes):
        raise ValueError('row count must be between 2 and 4096')
    started = time.monotonic(); cases = []
    with tempfile.TemporaryDirectory() as temporary:
        for count in sizes:
            root = Path(temporary)/str(count); root.mkdir(mode=0o700)
            case = prepare(root,count); rounds = []
            for order in (('baseline','candidate'),('candidate','baseline')):
                result = {}
                for label in order:
                    source = baseline if label == 'baseline' else PACKAGE
                    child = subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--worker',
                        '--package',str(source),'--root',str(root),'--repetitions',str(repetitions)],
                        capture_output=True,text=True,timeout=300,check=True)
                    result[label] = json.loads(child.stdout)
                if result['baseline']['report_digest'] != result['candidate']['report_digest']:
                    raise AssertionError('candidate changed public verification report')
                rounds.append({'order':order,**result})
            base_samples = [x for r in rounds for x in r['baseline']['warm_seconds']]
            candidate_samples = [x for r in rounds for x in r['candidate']['warm_seconds']]
            case.update({'rounds':rounds,'reports_identical':True,
                'baseline_warm_median_seconds':statistics.median(base_samples),
                'candidate_warm_median_seconds':statistics.median(candidate_samples),
                'observed_median_ratio':statistics.median(base_samples)/statistics.median(candidate_samples)})
            cases.append(case)
    return {'verified':all(case['reports_identical'] for case in cases),'cases':cases,
            'elapsed_seconds':time.monotonic()-started,'fixture_origin':'authored case; distinct synthetic capture snapshots',
            'measurement':'single interpreter per run; cold first call followed by repeated same-snapshot verification',
            'baseline_checkout':str(baseline),'candidate_checkout':str(PACKAGE),
            'concurrent_workload':'registry endurance and other development work on the same host',
            'production_throughput_claimed':False,'independent_load_generator':False,
            'cold_full_replay_required':True,'each_warm_call_reads_sqlite_and_rechecks_dossier_signature':True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path); parser.add_argument('--repetitions',type=int,default=12)
    parser.add_argument('--worker',action='store_true'); parser.add_argument('--package',type=Path)
    parser.add_argument('--root',type=Path); arguments = parser.parse_args()
    if arguments.worker:
        if not arguments.package or not arguments.root: parser.error('worker requires package and root')
        result = worker(arguments.package,arguments.root,arguments.repetitions)
    else:
        if not arguments.baseline: parser.error('baseline checkout required')
        result = run(arguments.baseline,arguments.repetitions)
    print(json.dumps(result,indent=2,sort_keys=True))
