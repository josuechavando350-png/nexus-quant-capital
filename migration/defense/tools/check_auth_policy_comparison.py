"""Run the policy comparison, prove exact differences and reproduce it from an offline installation."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nqc_defense.auth_policy_comparison import compare, publish_comparison, verify_comparison
from nqc_defense.codec import canonical
from nqc_defense.files import sha256

SOURCE=Path(__file__).resolve().parents[1]


def run():
    corpus=(SOURCE/'docs/AUTH_EVALUATION_CORPUS.json').read_bytes()
    baseline=(SOURCE/'docs/AUTH_EVALUATION_POLICY.json').read_bytes()
    candidate=(SOURCE/'docs/AUTH_POLICY_CANDIDATE.json').read_bytes()
    pins=json.loads((SOURCE/'docs/AUTH_EVALUATION_INPUTS.json').read_text())
    if (sha256(corpus),sha256(baseline)) != (pins['corpus_digest'],pins['policy_digest']):
        raise AssertionError('reference corpus or baseline changed')
    args=(corpus,pins['corpus_digest'],baseline,pins['policy_digest'],candidate,sha256(candidate))
    report=compare(*args)
    if report['confusion_delta'] != {'true_positive':-7,'false_positive':-2,'true_negative':2,'false_negative':7}:
        raise AssertionError('comparison regression requires review')
    if report['metric_delta']['precision'] is not None or report['metric_delta']['recall'] != {'numerator':-7,'denominator':9}:
        raise AssertionError('metric denominator or sign changed')
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary); output=root/'comparison.json'
        receipt=publish_comparison(output,report)
        if not verify_comparison(output.read_bytes(),receipt['comparison_digest'],compare(*args))['verified']:
            raise AssertionError('comparison did not recompute')
        build=root/'build'; build.mkdir(); target=root/'installed'
        shutil.copy2(SOURCE/'pyproject.toml',build/'pyproject.toml')
        shutil.copytree(SOURCE/'nqc_defense',build/'nqc_defense',ignore=shutil.ignore_patterns('__pycache__'))
        subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--no-index','--no-deps',
            '--no-build-isolation','--target',str(target),str(build)],capture_output=True,text=True,check=True,timeout=120)
        shutil.rmtree(build)
        for name,data in [('corpus',corpus),('baseline',baseline),('candidate',candidate)]: (root/(name+'.json')).write_bytes(data)
        version=tomllib.loads((SOURCE/'pyproject.toml').read_text())['project']['version']
        (root/'request.json').write_text(json.dumps({'target':str(target),'version':version,
            'corpus_digest':args[1],'baseline_digest':args[3],'candidate_digest':args[5],
            'comparison_digest':receipt['comparison_digest']}))
        code='''
import json,sys
from pathlib import Path
import nqc_defense
from nqc_defense.auth_policy_comparison import compare,publish_comparison
from nqc_defense.codec import canonical
from nqc_defense.files import sha256
r=json.loads(Path('request.json').read_text())
assert Path(nqc_defense.__file__).resolve().is_relative_to(Path(r['target']).resolve())
assert nqc_defense.__version__ == r['version']
report=compare(Path('corpus.json').read_bytes(),r['corpus_digest'],Path('baseline.json').read_bytes(),r['baseline_digest'],Path('candidate.json').read_bytes(),r['candidate_digest'])
assert sha256(canonical(report)) == r['comparison_digest']
assert publish_comparison(Path('installed-comparison.json'),report)['verified']
assert 'cryptography' not in sys.modules
print(json.dumps({'version':nqc_defense.__version__,'stdlib_only':True,'identical_report':True}))
'''
        result=subprocess.run([sys.executable,'-B','-S','-c',code],cwd=root,
            env={**os.environ,'PYTHONPATH':str(target),'PYTHONDONTWRITEBYTECODE':'1'},
            capture_output=True,text=True,check=True,timeout=60)
        installed=json.loads(result.stdout)
    criteria=['both_policies_pinned_before_execution','same_observations_and_evaluator_sources',
              'exact_metric_changes_with_undefined_ratios_preserved','trigger_sets_link_to_embedded_evidence',
              'private_publication_and_full_recomputation','installed_stdlib_only_execution_matches']
    return {'verified':True,'criteria':criteria,'criteria_passed':6,'criteria_total':6,
            'report':report,'comparison_digest':sha256(canonical(report)),
            'installed_version':installed['version'],'installed_stdlib_only':installed['stdlib_only'],
            'installed_report_identical':installed['identical_report'],'production_policy_changed':False,
            'reference_corpus_preserved':True,'reference_labels_preserved':True,'independent_evaluation':False}


if __name__=='__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
