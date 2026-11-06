"""Deterministic malformed-input checks on public registry replay; temporary owned fixtures only."""
import json
from pathlib import Path
import tempfile
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_signer_registry import fixture
from nqc_defense.codec import Rejected, canonical
from nqc_defense.dossier_attestation import attest_dossier, public_bytes
from nqc_defense.files import sha256
from nqc_defense.signer_registry import ORIGIN, row_head, signed_row, verify_bundle


def run():
    counts = {'cases':0,'controlled_rejections':0,'structurally_valid_variants':0}
    families = {}; failures = []
    values = [None,False,True,0,-1,2**63, '', 'x', '0'*64, '\ud800', '\x00', 'x'*10000,
              [], {}, [0], {'revision':True,'head':'0'*64}, {'revision':0,'head':'0'*64}, 1.5]
    with tempfile.TemporaryDirectory() as temporary:
        f = fixture(Path(temporary)); registry = f['registry']
        head = registry.change(f['authority'],'activate',f['key_pin'],'activate','Malformed-input fixture',ORIGIN,
                               public_bytes(f['signing_key']))['receipt']
        data = attest_dossier(f['dossier'],sha256(f['dossier']),f['pins'],f['policy'].key,f['signing_key'],f['key_pin'])
        head = registry.record(f['authority'],data,sha256(data),f['dossier'],sha256(f['dossier']),f['pins'],f['key_pin'],
                               'record','Validation fixture',head)['receipt']
        original = json.loads(registry.export(head)); last_event = json.loads(original['rows'][-1][1])
        def check(family, value, target=head):
            encoded = canonical(value); counts['cases'] += 1
            families[family] = families.get(family,0)+1
            try:
                verify_bundle(encoded,sha256(encoded),registry.digest,f['authority_pin'],target)
            except Rejected:
                counts['controlled_rejections'] += 1
            except Exception as exc:
                failures.append({'family':family,'case':counts['cases'],'exception':type(exc).__name__})
            else:
                counts['structurally_valid_variants'] += 1
        for field in original:
            for value in values:
                check('bundle.'+field,{**original,field:value})
        for column in range(4):
            for value in values:
                mutated = json.loads(canonical(original)); mutated['rows'][-1][column] = value
                check('row.'+str(column),mutated)
        for field in last_event:
            for value in values:
                event = {**last_event,field:value}
                row = signed_row(f['authority'],2,original['rows'][-1][2],event)
                mutated = {**original,'rows':[original['rows'][0],row]}
                check('signed_event.'+field,mutated,{'revision':2,'head':row_head(row)})
        for field in f['pins']:
            for value in values:
                event = {**last_event,'pins':{**f['pins'],field:value}}
                row = signed_row(f['authority'],2,original['rows'][-1][2],event)
                check('signed_pin.'+field,{**original,'rows':[original['rows'][0],row]}, {'revision':2,'head':row_head(row)})
        for value in values:
            check('external_checkpoint',original,value)
    result = {'verified':not failures, **counts,'families':families,'unexpected_exceptions':failures,
              'fixture_origin':'authored test records; deterministic JSON type/shape mutations and authority-signed invalid records',
              'signature_bypass_claimed':False,'independent_fuzzing':False,'production_tested':False}
    if failures:
        raise AssertionError(json.dumps(result,sort_keys=True))
    return result


if __name__ == '__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
