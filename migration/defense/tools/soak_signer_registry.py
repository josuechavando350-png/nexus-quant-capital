"""Duration-bounded local endurance measurement; synthetic snapshots, real persistence/replay."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import resource
import secrets
import sys
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_signer_registry import fixture
from nqc_defense.codec import Rejected, canonical
from nqc_defense.dossier_attestation import attest_dossier, public_bytes
from nqc_defense.files import sha256
from nqc_defense.signer_registry import MAX_ROWS, ORIGIN, SignerRegistry, verify_registered


def run(seconds, output, progress):
    if not 1 <= seconds <= 7200:
        raise ValueError('duration must be 1..7200 seconds')
    started, cpu_start = time.monotonic(), time.process_time()
    started_utc = datetime.now(timezone.utc).isoformat()
    deadline = started + seconds
    source_root = Path(__file__).resolve().parents[1]
    sources = {str(p.relative_to(source_root)):sha256(p.read_bytes()) for p in
               [source_root/'nqc_defense/signer_registry.py', source_root/'nqc_defense/dossier_attestation.py',
                source_root/'tools/check_signer_registry.py', Path(__file__).resolve()]}
    count = rotations = restarts = rejections = batches = completed_capacity_runs = 0
    maxima = {'database_bytes':0, 'registry_rows':0, 'bundle_bytes':0, 'open_fds':0}
    measurements = []; last_progress = 0; failures = []
    try:
        while time.monotonic() < deadline:
            batches += 1
            with tempfile.TemporaryDirectory() as temporary:
                f = fixture(Path(temporary)); registry = f['registry']; key = f['signing_key']; key_pin = f['key_pin']
                head = registry.change(f['authority'],'activate',key_pin,'activate','Endurance fixture',ORIGIN,public_bytes(key))['receipt']
                original = json.loads(f['dossier']); iteration = 0
                while time.monotonic() < deadline:
                    iteration += 1
                    if iteration % 128 == 0 and head['revision'] < MAX_ROWS:
                        new_key = secrets.token_bytes(32)
                        head = registry.change(f['authority'],'rotate',key_pin,f'rotate_{iteration}',
                            'Endurance rotation',head,public_bytes(new_key))['receipt']
                        key = new_key; key_pin = sha256(public_bytes(key)); rotations += 1
                    # These are artificial volume snapshots, not additional real security incidents.
                    snapshot = {**original, 'captured_ns':original['captured_ns']+iteration}
                    dossier = canonical(snapshot); dossier_digest = sha256(dossier)
                    data = attest_dossier(dossier,dossier_digest,f['pins'],f['policy'].key,key,key_pin); digest = sha256(data)
                    t0 = time.monotonic()
                    if head['revision'] == MAX_ROWS:
                        try:
                            registry.record(f['authority'],data,digest,dossier,dossier_digest,f['pins'],key_pin,
                                f'record_{iteration}','Endurance capacity rejection',head)
                        except Rejected as exc:
                            if str(exc) != 'registry_capacity': raise
                            rejections += 1; completed_capacity_runs += 1
                        else:
                            raise AssertionError('capacity overflow was accepted')
                        if registry.status(head)['checkpoint'] != head: raise AssertionError('capacity rejection changed state')
                        break
                    previous_head = head
                    head = registry.record(f['authority'],data,digest,dossier,dossier_digest,f['pins'],key_pin,
                        f'record_{iteration}','Synthetic volume snapshot',head)['receipt']
                    bundle = registry.export(head)
                    result = verify_registered(bundle,sha256(bundle),registry.digest,f['authority_pin'],head,head,
                        data,digest,dossier,dossier_digest,f['pins'])
                    if not result['registry_accepted']: raise AssertionError('record did not verify')
                    count += 1
                    if iteration % 64 == 0:
                        registry = SignerRegistry(registry.root,registry.digest,f['authority_pin'])
                        if registry.status(head)['active_key'] != key_pin: raise AssertionError('restart changed active key')
                        restarts += 1
                        try: registry.export(previous_head)
                        except Rejected as exc:
                            if str(exc) != 'registry_checkpoint_mismatch': raise
                            rejections += 1
                        else: raise AssertionError('incorrect checkpoint accepted')
                    elapsed = time.monotonic()-started
                    maxima['database_bytes'] = max(maxima['database_bytes'],registry.path.stat().st_size)
                    maxima['registry_rows'] = max(maxima['registry_rows'],head['revision'])
                    maxima['bundle_bytes'] = max(maxima['bundle_bytes'],len(bundle))
                    maxima['open_fds'] = max(maxima['open_fds'],len(os.listdir('/proc/self/fd')))
                    if elapsed-last_progress >= 30 or count == 1:
                        sample = {'elapsed_seconds':round(elapsed,3),'records':count,'batch':batches,
                                  'registry_rows':head['revision'],'last_record_export_verify_seconds':round(time.monotonic()-t0,6),
                                  'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'open_fds':len(os.listdir('/proc/self/fd'))}
                        measurements.append(sample); progress.write_text(json.dumps(sample)+'\n')
                        print(json.dumps(sample),flush=True); last_progress=elapsed
    except BaseException as exc:
        failures.append(type(exc).__name__+':'+str(exc))
        raise
    finally:
        unchanged = all(sha256((source_root/name).read_bytes()) == digest for name,digest in sources.items())
        report = {'schema':'nqc-registry-endurance-v1','verified':not failures and count > 0 and unchanged and time.monotonic()-started >= seconds,'requested_seconds':seconds,
            'started_utc':started_utc,'ended_utc':datetime.now(timezone.utc).isoformat(),
            'elapsed_seconds':round(time.monotonic()-started,3),'cpu_seconds':round(time.process_time()-cpu_start,3),
            'fixture_origin':'authored OpenSSH log; synthetic distinct capture-time snapshots; real SQLite and signatures',
            'records_registered_and_publicly_verified':count,'rotations':rotations,'store_reopens':restarts,
            'expected_rejections':rejections,'batches':batches,'completed_capacity_runs':completed_capacity_runs,
            'maxima':maxima,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'samples':measurements,'failures':failures,'source_sha256':sources,'source_unchanged_at_finish':unchanged,
            'production_performance_claimed':False,'independent_load_generator':False,'power_loss_tested':False}
        output.write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--progress',type=Path,required=True)
    args = parser.parse_args()
    result = run(args.seconds,args.output,args.progress)
    print(json.dumps({k:result[k] for k in ('verified','elapsed_seconds','records_registered_and_publicly_verified','completed_capacity_runs')}))
