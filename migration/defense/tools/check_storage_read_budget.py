"""Compare bounded reads with a trusted local baseline using temporary oversized database values."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import sqlite3
import subprocess
import sys
import tempfile
import time

PACKAGE = Path(__file__).resolve().parents[1]


def worker(package, root, kind):
    sys.path.insert(0,str(package))
    from nqc_defense.codec import Rejected
    from nqc_defense.registry_mirror import RegistryMirror
    from nqc_defense.signer_registry import SignerRegistry
    r = json.loads((root/'request.json').read_bytes())
    def memory():
        values = {}
        for line in Path('/proc/self/status').read_text().splitlines():
            if line.startswith(('VmRSS:','VmHWM:')): values[line.split(':')[0]] = int(line.split()[1])
        return values
    initial_memory = memory(); started = time.perf_counter(); reason = None
    try:
        if kind == 'registry':
            SignerRegistry(root/'registry',r['registry_digest'],r['authority_digest']).status(r['registry_head'])
        else:
            RegistryMirror(root/'mirror',r['registry_digest'],r['authority_digest']).status(r['mirror_receipt'])
    except Rejected as exc: reason = str(exc)
    if reason is None: raise AssertionError('oversized corrupted value accepted')
    fingerprints = {}
    for name in ('signer_registry.py','registry_mirror.py','sqlite_limits.py'):
        source = package/'nqc_defense'/name
        fingerprints[name] = hashlib.sha256(source.read_bytes()).hexdigest() if source.exists() else None
    measured = memory()
    return {'rejected':True,'reason':reason,'elapsed_seconds':time.perf_counter()-started,
            'rss_before_kib':initial_memory['VmRSS'],'rss_after_kib':measured['VmRSS'],
            'process_vm_hwm_kib':measured['VmHWM'],
            'rusage_peak_rss_kib_may_include_pre_exec_peak':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'source_sha256':fingerprints}


def run(baseline):
    if baseline.resolve() == PACKAGE: raise ValueError('distinct trusted baseline required')
    from check_case_triage import fixture
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary); f = fixture(root,specifications=[(2,None,False)])
        request = {'registry_digest':f['registry'].digest,'authority_digest':f['authority_pin'],
                   'registry_head':f['registry_head'],'mirror_receipt':f['mirror_receipt']}
        (root/'request.json').write_text(json.dumps(request))
        size = 64*1024*1024
        with sqlite3.connect(f['registry'].path) as db:
            db.execute('UPDATE entries SET payload=CAST(zeroblob(?) AS TEXT) WHERE revision=1',(size,))
        with sqlite3.connect(f['mirror'].path) as db: db.execute('UPDATE snapshot SET bundle=zeroblob(?)',(size,))
        results = []
        for kind in ('registry','mirror'):
            path = f[kind].path
            with path.open('rb') as stream: before = hashlib.file_digest(stream,'sha256').hexdigest()
            runs = []
            for order in (('baseline','candidate'),('candidate','baseline')):
                compared = {'order':order}
                for label in order:
                    source = baseline.resolve() if label == 'baseline' else PACKAGE
                    child = subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--worker','--package',str(source),
                        '--root',str(root),'--kind',kind],capture_output=True,text=True,check=True,timeout=60)
                    compared[label] = json.loads(child.stdout)
                runs.append(compared)
            with path.open('rb') as stream: after = hashlib.file_digest(stream,'sha256').hexdigest()
            if before != after: raise AssertionError('read check changed database bytes')
            results.append({'kind':kind,'oversized_value_bytes':size,'database_bytes':path.stat().st_size,
                            'database_unchanged':True,'runs':runs})
        return {'verified':True,'results':results,'baseline_checkout':str(baseline.resolve()),'candidate_checkout':str(PACKAGE),
                'fixture_origin':'owned temporary stores; explicit 64 MiB zero-filled corruption fixtures',
                'measurement':'separate interpreter per run; alternating order; Linux /proc/self/status VmHWM and VmRSS',
                'rusage_peak_not_used_for_comparison':'observed identical inherited pre-exec high-water mark; retained only for transparency',
                'concurrent_workload':'other endurance tests on the same host','production_performance_claimed':False,
                'os_memory_quota_claimed':False,'whole_database_integrity_claimed':False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path); parser.add_argument('--worker',action='store_true')
    parser.add_argument('--package',type=Path); parser.add_argument('--root',type=Path)
    parser.add_argument('--kind',choices=('registry','mirror')); args = parser.parse_args()
    if args.worker:
        if not args.package or not args.root or not args.kind: parser.error('worker arguments required')
        result = worker(args.package.resolve(),args.root,args.kind)
    else:
        if not args.baseline: parser.error('baseline required')
        result = run(args.baseline)
    print(json.dumps(result,indent=2,sort_keys=True))
