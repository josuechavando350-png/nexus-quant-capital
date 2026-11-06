"""Install the actual package offline and run public triage outside the source checkout."""
import json
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from check_case_triage import fixture
from nqc_defense.codec import canonical
from nqc_defense.files import sha256

SOURCE = Path(__file__).resolve().parents[1]


def run():
    version = tomllib.loads((SOURCE/'pyproject.toml').read_text())['project']['version']
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary); build = root/'source'; build.mkdir(); target = root/'installed'
        shutil.copy2(SOURCE/'pyproject.toml',build/'pyproject.toml')
        shutil.copytree(SOURCE/'nqc_defense',build/'nqc_defense',ignore=shutil.ignore_patterns('__pycache__'))
        subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--no-index','--no-deps',
            '--no-build-isolation','--target',str(target),str(build)],capture_output=True,text=True,check=True,timeout=120)
        inputs = root/'inputs'; inputs.mkdir(mode=0o700); f = fixture(inputs)
        report = f['mirror'].triage(f['mirror_receipt'],f['triage_policy'],f['items'])
        documents = {'triage.json':canonical(f['config']),'selection.json':canonical(f['selection']),
                     'receiver.json':canonical(f['mirror_receipt'])}
        metadata = {'version':version,'target':str(target),'inputs':str(inputs),
                    'registry_digest':f['registry'].digest,'authority_digest':f['authority_pin'],
                    'policy_digest':f['triage_policy'].digest,'selection_digest':sha256(documents['selection.json']),
                    'expected_report_digest':sha256(canonical(report))}
        for name,body in documents.items(): (inputs/name).write_bytes(body)
        for name in ('operations','policy','signer','authority','registry'): shutil.rmtree(inputs/name)
        for path in f['logs']+f['evidence_paths']: path.unlink()
        (root/'request.json').write_text(json.dumps(metadata))
        code = '''
import importlib.metadata as metadata
import json
from pathlib import Path
import nqc_defense
from nqc_defense.case_triage import TriagePolicy, load_selection
from nqc_defense.codec import canonical
from nqc_defense.dossier_attestation import public_bytes
from nqc_defense.files import sha256
from nqc_defense.registry_mirror import RegistryMirror
from nqc_defense.signer_registry import VerifiedRegistry
r = json.loads(Path('request.json').read_text()); root = Path(r['inputs'])
assert Path(nqc_defense.__file__).resolve().is_relative_to(Path(r['target']).resolve())
assert nqc_defense.__version__ == r['version']
policy = TriagePolicy((root/'triage.json').read_bytes(),r['policy_digest'])
items = load_selection(root,(root/'selection.json').read_bytes(),r['selection_digest'])
mirror = RegistryMirror(root/'mirror',r['registry_digest'],r['authority_digest'])
report = mirror.triage(json.loads((root/'receiver.json').read_bytes()),policy,items)
assert sha256(canonical(report)) == r['expected_report_digest']
assert len(public_bytes(b'x'*32)) == 32
print(json.dumps({'version':nqc_defense.__version__,'requirements':metadata.requires('nqc-defense-local'),
                  'selected_cases':report['queue_report']['selected_cases'],'installed_public_triage_matches_source':True}))
'''
        env = {**os.environ,'PYTHONPATH':str(target),'PYTHONDONTWRITEBYTECODE':'1'}
        child = subprocess.run([sys.executable,'-B','-c',code],cwd=root,env=env,capture_output=True,text=True,check=True,timeout=60)
        installed = json.loads(child.stdout)
        base_code = '''
from nqc_defense.engine import Engine
from nqc_defense.codec import Rejected
from nqc_defense.dossier_attestation import backend
try: backend()
except Rejected as exc: assert str(exc) == 'attestation_dependency_unavailable'
else: raise AssertionError('optional backend unexpectedly available')
print('passed')
'''
        base = subprocess.run([sys.executable,'-B','-S','-c',base_code],cwd=root,env=env,
                              capture_output=True,text=True,check=True,timeout=30)
        if base.stdout.strip() != 'passed': raise AssertionError('base package import failed')
        return {'verified':True,'installed_version':installed['version'],'requirements':installed['requirements'],
                'offline_install_no_dependency_resolution':True,'base_import_without_site_packages':True,
                'missing_optional_backend_rejected':True,'installed_signing_backend_worked':True,
                'installed_immutable_registry_imported':True,'installed_public_triage_matches_source':True,
                'selected_cases':installed['selected_cases'],'original_sources_and_private_keys_removed':True,
                'fixture_origin':'four authored authentication cases; installed package public verification'}


if __name__ == '__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
