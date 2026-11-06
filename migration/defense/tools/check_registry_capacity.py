"""Check the actual registry row ceiling using explicit bulk-loaded signed test fixtures."""
import json
from pathlib import Path
import tempfile
import time
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_signer_registry import fixture
from nqc_defense.codec import Rejected, canonical
from nqc_defense.dossier_attestation import attest_dossier, public_bytes
from nqc_defense.files import sha256
from nqc_defense.signer_registry import MAX_ROWS, ORIGIN, row_head, signed_row, verify_registered


def run():
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as temporary:
        f = fixture(Path(temporary)); registry = f['registry']; policy_key = f['policy'].key
        head = registry.change(f['authority'],'activate',f['key_pin'],'activate','Capacity fixture',ORIGIN,public_bytes(f['signing_key']))['receipt']
        original = json.loads(f['dossier']); rows = []
        for index in range(1,MAX_ROWS-1):
            dossier = canonical({**original,'captured_ns':original['captured_ns']+index})
            digest = sha256(dossier)
            attestation = attest_dossier(dossier,digest,f['pins'],policy_key,f['signing_key'],f['key_pin'])
            event = registry._event('record',f['key_pin'],f'fixture_{index}','Explicit synthetic capacity snapshot',
                attestation_digest=sha256(attestation),dossier_digest=digest,pins=f['pins'])
            row = signed_row(f['authority'],head['revision']+1,head['head'],event)
            rows.append(row); head = {'revision':row[0],'head':row_head(row)}
        # Fixture preparation is deliberately bulk insertion, not a claim of thousands of API writes.
        with registry.connection(write=True) as db:
            db.executemany('INSERT INTO entries VALUES(?,?,?,?)',rows)
        assert registry.status(head)['checkpoint']['revision'] == MAX_ROWS-1
        dossier = canonical({**original,'captured_ns':original['captured_ns']+MAX_ROWS})
        attestation = attest_dossier(dossier,sha256(dossier),f['pins'],policy_key,f['signing_key'],f['key_pin'])
        final_started = time.monotonic()
        receipt = registry.record(f['authority'],attestation,sha256(attestation),dossier,sha256(dossier),f['pins'],f['key_pin'],
            'final_api_record','Actual API write at the ceiling',head)['receipt']
        final_write_seconds = time.monotonic()-final_started
        assert receipt['revision'] == MAX_ROWS
        bundle = registry.export(receipt)
        report = verify_registered(bundle,sha256(bundle),registry.digest,f['authority_pin'],receipt,receipt,
            attestation,sha256(attestation),dossier,sha256(dossier),f['pins'])
        next_dossier = canonical({**original,'captured_ns':original['captured_ns']+MAX_ROWS+1})
        next_attestation = attest_dossier(next_dossier,sha256(next_dossier),f['pins'],policy_key,f['signing_key'],f['key_pin'])
        rejected = None
        try:
            registry.record(f['authority'],next_attestation,sha256(next_attestation),next_dossier,sha256(next_dossier),
                f['pins'],f['key_pin'],'overflow','Expected capacity rejection',receipt)
        except Rejected as exc:
            rejected = str(exc)
        assert rejected == 'registry_capacity'
        assert registry.status(receipt)['checkpoint'] == receipt
        assert registry.export(receipt) == bundle
        return {'verified':report['registry_accepted'],'fixture_origin':'authored case; distinct synthetic capture-time snapshots; real signatures and SQLite',
                'bulk_prepared_record_rows':len(rows),'activation_api_writes':1,'final_record_api_writes':1,
                'rows_at_ceiling':receipt['revision'],'bundle_bytes':len(bundle),'database_bytes':registry.path.stat().st_size,
                'overflow_rejection':rejected,'checkpoint_and_bundle_unchanged_after_rejection':True,
                'final_record_seconds':round(final_write_seconds,6),'elapsed_seconds':round(time.monotonic()-started,3),
                'production_throughput_claimed':False,'all_rows_added_via_record_api':False}


if __name__ == '__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
