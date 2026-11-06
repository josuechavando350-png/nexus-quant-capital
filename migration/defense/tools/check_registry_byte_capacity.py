"""Reach the actual 32 MiB signed-bundle ceiling, then reject one more API record.

Distinct capture-time snapshots and padded reasons are explicit capacity fixtures.
Most rows are bulk prepared; the final record and overflow attempt use the real API.
"""
import json
from pathlib import Path
import tempfile
import time
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from check_signer_registry import fixture
from nqc_defense.codec import Rejected, canonical
from nqc_defense.dossier_attestation import attest_dossier, public_bytes
from nqc_defense.files import sha256
from nqc_defense.registry_mirror import EMPTY, MAX_SQLITE_ROW as MIRROR_ROW, RegistryMirror
from nqc_defense.signer_registry import MAX_BUNDLE, MAX_EVENT_BYTES, MAX_ROWS, ORIGIN, row_head, signed_row


def reason_for_size(event, revision, previous, target=None):
    """ASCII/backslash/newline padding exercises both JSON encoding layers exactly."""
    event = {**event,'reason':''}; payload = canonical(event).decode()
    base = len(canonical([revision,payload,previous,'0'*128])); room = MAX_EVENT_BYTES-len(payload)
    maximum = base+4*(room//2)+(room%2)
    desired = maximum if target is None else target
    extra = desired-base
    for newlines in range(4):
        remaining = extra-3*newlines
        if remaining < 0: continue
        slashes,plain = divmod(remaining,4)
        reason = '\\'*slashes+'\n'*newlines+'x'*plain
        if reason.strip() and len(reason.encode()) <= 4096 and 2*(slashes+newlines)+plain <= room:
            candidate = {**event,'reason':reason}; encoded = canonical(candidate).decode()
            if len(canonical([revision,encoded,previous,'0'*128])) != desired: raise AssertionError('padding size mismatch')
            return reason,desired,base+1,maximum
    raise AssertionError('capacity padding is not representable')


def run():
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as temporary:
        f = fixture(Path(temporary)); registry = f['registry']; original = json.loads(f['dossier'])
        head = registry.change(f['authority'],'activate',f['key_pin'],'activate','Byte capacity fixture',ORIGIN,
                               public_bytes(f['signing_key']))['receipt']
        size = len(registry.export(head)); prepared = []; index = 1
        def proof(number):
            dossier = canonical({**original,'captured_ns':original['captured_ns']+number})
            data = attest_dossier(dossier,sha256(dossier),f['pins'],f['policy'].key,f['signing_key'],f['key_pin'])
            event = registry._event('record',f['key_pin'],f'capacity_{number}','',attestation_digest=sha256(data),
                                    dossier_digest=sha256(dossier),pins=f['pins'])
            return {'event':event,'dossier':dossier,'attestation':data}
        current = proof(index)
        while True:
            if head['revision']+2 > MAX_ROWS: raise AssertionError('row capacity reached before byte capacity')
            reason,maximum,_,_ = reason_for_size(current['event'],head['revision']+1,head['head'])
            following = proof(index+1)
            _,next_maximum,next_minimum,_ = reason_for_size(following['event'],head['revision']+2,'0'*64)
            remaining = MAX_BUNDLE-size
            if remaining > maximum+next_maximum+2:
                event = {**current['event'],'reason':reason}
                row = signed_row(f['authority'],head['revision']+1,head['head'],event)
                prepared.append(row); size += len(canonical(row))+1
                head = {'revision':row[0],'head':row_head(row)}
                index += 1; current = following
                continue
            # Two real records split the remainder, reserving a nonempty reason for each.
            current_target = min(maximum,remaining-next_minimum-2)
            reason,_,_,_ = reason_for_size(current['event'],head['revision']+1,head['head'],current_target)
            row = signed_row(f['authority'],head['revision']+1,head['head'],{**current['event'],'reason':reason})
            prepared.append(row); size += len(canonical(row))+1; head = {'revision':row[0],'head':row_head(row)}
            final_reason,_,_,_ = reason_for_size(following['event'],head['revision']+1,head['head'],MAX_BUNDLE-size-1)
            final_proof = following
            break
        with registry.connection(write=True) as db: db.executemany('INSERT INTO entries VALUES(?,?,?,?)',prepared)
        final_started = time.monotonic()
        final = registry.record(f['authority'],final_proof['attestation'],sha256(final_proof['attestation']),
            final_proof['dossier'],sha256(final_proof['dossier']),f['pins'],f['key_pin'],final_proof['event']['request_id'],
            final_reason,head)['receipt']
        final_seconds = time.monotonic()-final_started
        bundle = registry.export(final)
        if len(bundle) != MAX_BUNDLE: raise AssertionError('exact byte ceiling not reached')
        mirror = RegistryMirror.create(Path(temporary)/'mirror',registry.digest,f['authority_pin'])
        receipt = mirror.accept(bundle,sha256(bundle),final,EMPTY)['receipt']
        mirror = RegistryMirror(mirror.root,registry.digest,f['authority_pin'])
        verified = mirror.verify(receipt,final,final_proof['attestation'],sha256(final_proof['attestation']),
            final_proof['dossier'],sha256(final_proof['dossier']),f['pins'])
        if not verified['registry_report']['registry_accepted'] or mirror.export(receipt) != bundle:
            raise AssertionError('maximum-sized received bundle failed')
        overflow = proof(index+2); rejection = None
        try:
            registry.record(f['authority'],overflow['attestation'],sha256(overflow['attestation']),
                overflow['dossier'],sha256(overflow['dossier']),f['pins'],f['key_pin'],'overflow','Expected byte limit',final)
        except Rejected as exc: rejection = str(exc)
        if rejection != 'registry_bundle_size' or registry.export(final) != bundle:
            raise AssertionError('overflow did not preserve exact previous bundle')
        return {'verified':True,'bundle_bytes':len(bundle),'configured_bundle_limit':MAX_BUNDLE,
                'registry_rows':final['revision'],'configured_row_limit':MAX_ROWS,
                'activation_api_writes':1,'bulk_prepared_record_rows':len(prepared),'final_record_api_writes':1,
                'all_rows_added_via_record_api':False,'overflow_rejection':rejection,
                'final_api_write_seconds':final_seconds,'elapsed_seconds':time.monotonic()-started,
                'cold_receiver_verified_at_exact_byte_limit':True,'receiver_sqlite_row_limit':MIRROR_ROW,
                'registry_database_bytes':registry.path.stat().st_size,'mirror_database_bytes':mirror.path.stat().st_size,
                'fixture_origin':'authored case; distinct synthetic capture-time snapshots; explicitly padded reasons',
                'production_throughput_claimed':False,'physical_disk_quota_claimed':False}


if __name__ == '__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
