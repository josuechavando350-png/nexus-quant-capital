"""Sustained verification of a frozen public receiver, with explicit temporary corruption checks."""
import argparse
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time


def worker(package, root, seconds, progress):
    sys.path.insert(0,str(package))
    import nqc_defense
    from nqc_defense.codec import Rejected, canonical
    from nqc_defense.registry_mirror import RegistryMirror
    request = json.loads((root/'request.json').read_bytes())
    data = (root/'attestation.json').read_bytes(); dossier = (root/'dossier.json').read_bytes()
    args = (request['mirror_receipt'],request['registration'],data,request['attestation_digest'],
            dossier,request['dossier_digest'],request['pins'])
    def reopen(): return RegistryMirror(root/'mirror',request['registry_digest'],request['authority_digest'])
    def digest(body): return hashlib.sha256(body).hexdigest()
    def sources():
        values = {name:digest((package/'nqc_defense'/name).read_bytes()) for name in
                  ('__init__.py','registry_mirror.py','signer_registry.py','dossier_attestation.py','sqlite_limits.py')
                  if (package/'nqc_defense'/name).exists()}
        values['harness:soak_registry_mirror.py'] = digest(Path(__file__).read_bytes())
        return values
    fingerprints = sources(); mirror = reopen(); bundle = mirror.export(request['mirror_receipt'])
    baseline = digest(canonical(mirror.verify(*args))); fd_start = len(list(Path('/proc/self/fd').iterdir()))
    started = time.monotonic(); count = corruption = reopened = 0; samples = []; failures = []; last_sample = -30
    try:
        while time.monotonic()-started < seconds:
            before = time.perf_counter(); result = mirror.verify(*args); latency = time.perf_counter()-before
            if digest(canonical(result)) != baseline: raise AssertionError('verification report changed')
            count += 1
            if count % 500 == 0:
                with mirror.connection(write=True) as db: db.execute('UPDATE snapshot SET bundle=?',(bundle+b' ',))
                try: mirror.verify(*args)
                except Rejected: corruption += 1
                else: raise AssertionError('changed storage was accepted')
                finally:
                    with mirror.connection(write=True) as db: db.execute('UPDATE snapshot SET bundle=?',(bundle,))
            if count % 5000 == 0:
                mirror = reopen(); reopened += 1
            elapsed = time.monotonic()-started
            if elapsed-last_sample >= 30:
                rss = next(line for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('VmRSS:'))
                sample = {'elapsed_seconds':round(elapsed,3),'verified_calls':count,'corruption_checks':corruption,
                          'reopens':reopened,'last_verify_seconds':latency,'rss_kib':int(rss.split()[1]),
                          'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                          'open_fds':len(list(Path('/proc/self/fd').iterdir()))}
                samples.append(sample); last_sample = elapsed
                if progress: progress.write_text(json.dumps(sample)+'\n')
    except Exception as exc:
        failures.append({'type':type(exc).__name__,'message':str(exc)})
    elapsed = time.monotonic()-started; unchanged = fingerprints == sources()
    restored = mirror.export(request['mirror_receipt']) == bundle
    final_fd = len(list(Path('/proc/self/fd').iterdir()))
    return {'schema':'nqc-mirror-endurance-v2','tested_package_version':nqc_defense.__version__,
            'verified':not failures and elapsed >= seconds and count > 0 and corruption > 0 and unchanged and restored,
            'requested_seconds':seconds,'elapsed_seconds':elapsed,'verified_calls':count,'corruption_checks':corruption,
            'reopens':reopened,'failures':failures,'source_sha256':fingerprints,'source_unchanged_at_finish':unchanged,
            'public_bundle_preserved':restored,'open_fds_initial':fd_start,'open_fds_final':final_fd,'samples':samples,
            'registry_rows':request['mirror_receipt']['registry_checkpoint']['revision'],
            'snapshot_bytes':len(bundle),'fixture_origin':'authored log case; signed bulk-prepared synthetic capture snapshots',
            'source_checkout':str(package),'production_performance_claimed':False,'independent_load_generator':False,
            'no_private_issuer_stores':not any((root/x).exists() for x in ('policy','signer','authority','registry','operations'))}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package',type=Path,required=True); parser.add_argument('--seconds',type=int,default=900)
    parser.add_argument('--rows',type=int,default=4096); parser.add_argument('--output',type=Path)
    parser.add_argument('--progress',type=Path); parser.add_argument('--worker',action='store_true')
    parser.add_argument('--root',type=Path); args = parser.parse_args()
    if not 1 <= args.seconds <= 7200: parser.error('seconds outside 1..7200')
    if not 2 <= args.rows <= 4096: parser.error('rows outside 2..4096')
    if args.worker:
        if not args.root: parser.error('worker root required')
        result = worker(args.package.resolve(),args.root,args.seconds,args.progress)
    else:
        if not args.output: parser.error('output required')
        from check_registry_cache import prepare
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); prepare(root,args.rows)
            command = [sys.executable,'-B',str(Path(__file__).resolve()),'--worker','--package',str(args.package.resolve()),
                       '--root',str(root),'--seconds',str(args.seconds)]
            if args.progress: command.extend(('--progress',str(args.progress.resolve())))
            process = subprocess.run(command,capture_output=True,text=True,timeout=args.seconds+120,check=True)
            result = json.loads(process.stdout)
        args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result,sort_keys=True))
    raise SystemExit(0 if result['verified'] else 1)
