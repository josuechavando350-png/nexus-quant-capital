"""Verify the separate authored corpus, reproducible reports, CLI and stdlib-only installed evaluation."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from nqc_defense.auth_evaluation import evaluate, publish_report
from nqc_defense.codec import canonical
from nqc_defense.files import sha256

SOURCE = Path(__file__).resolve().parents[1]


def run():
    pins = json.loads((SOURCE/'docs/AUTH_EVALUATION_INPUTS.json').read_text())
    corpus = (SOURCE/'docs'/pins['corpus_file']).read_bytes()
    policy = (SOURCE/'docs'/pins['policy_file']).read_bytes()
    report = evaluate(corpus,pins['corpus_digest'],policy,pins['policy_digest'],batch_size=1)
    again = evaluate(corpus,pins['corpus_digest'],policy,pins['policy_digest'],batch_size=200)
    if report != again:
        raise AssertionError('batch size or temporary paths changed semantic evaluation')
    if report['confusion_matrix'] != {'true_positive':7,'false_positive':2,'true_negative':4,'false_negative':2}:
        raise AssertionError('authored corpus regression requires review; do not silently adjust labels')
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root/'corpus.json').write_bytes(corpus); (root/'policy.json').write_bytes(policy)
        receipt = publish_report(root/'report.json',report)
        common = ['--corpus',str(root/'corpus.json'),'--corpus-digest',pins['corpus_digest'],
                  '--policy',str(root/'policy.json'),'--policy-digest',pins['policy_digest']]
        child = subprocess.run([sys.executable,'-B',str(SOURCE/'tools/auth_evaluation.py'),'verify',*common,
            '--report',str(root/'report.json'),'--report-digest',receipt['report_digest']],
            cwd=root,capture_output=True,text=True,check=True,timeout=60)
        if json.loads(child.stdout).get('verified') is not True:
            raise AssertionError('CLI evaluation verification failed')
        build = root/'build'; build.mkdir(); target = root/'installed'
        shutil.copy2(SOURCE/'pyproject.toml',build/'pyproject.toml')
        shutil.copytree(SOURCE/'nqc_defense',build/'nqc_defense',ignore=shutil.ignore_patterns('__pycache__'))
        subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--no-index','--no-deps',
            '--no-build-isolation','--target',str(target),str(build)],capture_output=True,text=True,check=True,timeout=120)
        shutil.rmtree(build)
        version = tomllib.loads((SOURCE/'pyproject.toml').read_text())['project']['version']
        request = {'target':str(target),'version':version,'corpus_digest':pins['corpus_digest'],
                   'policy_digest':pins['policy_digest'],'report_digest':receipt['report_digest']}
        (root/'request.json').write_text(json.dumps(request))
        code = '''
import json,sys
from pathlib import Path
import nqc_defense
from nqc_defense.auth_evaluation import evaluate,publish_report
from nqc_defense.codec import canonical
from nqc_defense.files import sha256
r=json.loads(Path('request.json').read_text())
assert Path(nqc_defense.__file__).resolve().is_relative_to(Path(r['target']).resolve())
assert nqc_defense.__version__ == r['version']
report=evaluate(Path('corpus.json').read_bytes(),r['corpus_digest'],Path('policy.json').read_bytes(),r['policy_digest'])
assert sha256(canonical(report)) == r['report_digest']
assert publish_report(Path('installed-report.json'),report)['verified']
assert 'cryptography' not in sys.modules
print(json.dumps({'version':nqc_defense.__version__,'report_digest':sha256(canonical(report)),'stdlib_only':True}))
'''
        installed = subprocess.run([sys.executable,'-B','-S','-c',code],cwd=root,
            env={**os.environ,'PYTHONPATH':str(target),'PYTHONDONTWRITEBYTECODE':'1'},
            capture_output=True,text=True,check=True,timeout=60)
        installed = json.loads(installed.stdout)
    criteria = [
        'pinned_corpus_and_policy_feed_real_ingestion',
        'unknown_labels_and_excluded_records_remain_visible',
        'all_created_cases_have_reverified_preserved_evidence',
        'batch_sizes_reopens_and_temporary_paths_preserve_report',
        'private_publication_and_cli_recomputation',
        'offline_installed_package_without_site_packages_matches',
    ]
    return {'verified':True,'installed_version':installed['version'],'criteria_passed':len(criteria),
        'criteria_total':len(criteria),'criteria':criteria,'report':report,'report_digest':sha256(canonical(report)),
        'installed_stdlib_only':installed['stdlib_only'],'cli_recomputed':True,
        'corpus_labels_changed_by_evaluator':False,'detector_rule_changed':False,
        'independent_evaluation':False,'production_accuracy_claimed':False}


if __name__ == '__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
