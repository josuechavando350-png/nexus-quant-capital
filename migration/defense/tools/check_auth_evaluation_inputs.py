"""Deterministic type and framing checks for the evaluation boundary; no detector tuning."""
from copy import deepcopy
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nqc_defense.auth_evaluation import inputs
from nqc_defense.codec import Rejected, canonical
from nqc_defense.files import sha256


def run():
    root = Path(__file__).resolve().parents[1]/'docs'
    corpus = json.loads((root/'AUTH_EVALUATION_CORPUS.json').read_bytes())
    policy = json.loads((root/'AUTH_EVALUATION_POLICY.json').read_bytes())
    counts = {'variants':0,'controlled_rejections':0,'structurally_valid':0}
    failures, families = [], {}
    values = [None,True,False,0,-1,2**63,1.5,'','x','\x00','\ud800',[],{},[0],{'id':'x'},'x'*22000]
    def check(name,candidate,settings):
        counts['variants'] += 1; families[name] = families.get(name,0)+1
        c,p = canonical(candidate),canonical(settings)
        try: inputs(c,sha256(c),p,sha256(p))
        except Rejected: counts['controlled_rejections'] += 1
        except Exception as exc: failures.append({'case':counts['variants'],'family':name,'exception':type(exc).__name__})
        else: counts['structurally_valid'] += 1
    for field in corpus:
        for value in values:
            check('corpus.'+field,{**corpus,field:value},policy)
    for field in policy:
        for value in values:
            check('policy.'+field,corpus,{**policy,field:value})
    for field in corpus['scenarios'][0]:
        for value in values:
            changed = deepcopy(corpus); changed['scenarios'][0][field] = value
            check('scenario.'+field,changed,policy)
    for value in values:
        changed = deepcopy(corpus); changed['scenarios'][0]['records_base64'][0] = value
        check('record',changed,policy)
    report = {'verified':not failures,**counts,'families':families,'unexpected_exceptions':failures,
              'fixture_origin':'owned authored corpus with deterministic mutations',
              'independent_fuzzing':False,'production_tested':False}
    if failures: raise AssertionError(json.dumps(report,sort_keys=True))
    return report


if __name__ == '__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
