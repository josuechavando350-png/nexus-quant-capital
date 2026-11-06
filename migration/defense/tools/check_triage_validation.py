"""Check typed policy and proof boundaries with deterministic mutations of owned fixtures."""
import copy
import json
from pathlib import Path
import tempfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from check_case_triage import fixture
from nqc_defense.case_triage import TriagePolicy
from nqc_defense.codec import Rejected, canonical
from nqc_defense.files import sha256


def run():
    counts = {'cases':0,'controlled_rejections':0,'structurally_valid_variants':0}
    families = {}; failures = []
    values = [None,False,True,0,-1,2**63, '', 'x', '0'*64, '\ud800', '\x00', 'x'*10000,
              [], {}, [0], {'revision':True,'head':'0'*64}, {'revision':0,'head':'0'*64}, 1.5]
    def check(family, action):
        counts['cases'] += 1; families[family] = families.get(family,0)+1
        try: action()
        except Rejected: counts['controlled_rejections'] += 1
        except Exception as exc: failures.append({'family':family,'case':counts['cases'],'exception':type(exc).__name__})
        else: counts['structurally_valid_variants'] += 1
    with tempfile.TemporaryDirectory() as temporary:
        f = fixture(Path(temporary)); mirror = f['mirror']; receipt = f['mirror_receipt']
        original_bundle = mirror.export(receipt); original_report = mirror.triage(receipt,f['triage_policy'],f['items'])
        for field in f['config']:
            for value in values:
                data = canonical({**f['config'],field:value})
                check('policy.'+field,lambda:TriagePolicy(data,sha256(data)))
        for group in ('weights','bands'):
            for field in f['config'][group]:
                for value in values:
                    data = canonical({**f['config'],group:{**f['config'][group],field:value}})
                    check('policy.'+group+'.'+field,lambda:TriagePolicy(data,sha256(data)))
        item = f['items'][0]
        for field in item:
            for value in values:
                proof = {**item,field:value}
                check('proof.'+field,lambda:mirror.triage(receipt,f['triage_policy'],[proof]))
        for group in ('pins','registration_receipt'):
            for field in item[group]:
                for value in values:
                    proof = {**item,group:{**item[group],field:value}}
                    check('proof.'+group+'.'+field,lambda:mirror.triage(receipt,f['triage_policy'],[proof]))
        for value in values:
            check('receiver_receipt',lambda:mirror.triage(value,f['triage_policy'],f['items']))
        unchanged = mirror.export(receipt) == original_bundle and mirror.triage(receipt,f['triage_policy'],f['items']) == original_report
    result = {'verified':not failures and unchanged,**counts,'families':families,'unexpected_exceptions':failures,
              'receiver_and_original_report_preserved':unchanged,
              'fixture_origin':'authored cases; deterministic type/shape mutations of policy, proof metadata and receiver receipt',
              'independent_fuzzing':False,'production_tested':False}
    if failures or not unchanged: raise AssertionError(json.dumps(result,sort_keys=True))
    return result


if __name__ == '__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
