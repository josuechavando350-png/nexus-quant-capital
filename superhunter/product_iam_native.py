"""Classify fixed owned IAM policy actions with a pinned upstream implementation and data snapshot."""
from pathlib import Path
import subprocess
import sys
import tempfile

from .product_notice_ranking import ISOLATE, install_wheels
from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .repository_boundary import git_object
from .safe_io import canonical, read_artifact, strict_json

REPOSITORIES = {'salesforce/policy_sentry': 'executable'}
LOCK = 'superhunter/product_supply/iam-native-linux-py312.txt'
LOCK_SHA = '72bd33b5bd3fe4d77146025e45715a9977d99a4c52a97dd24e09de9b5dcb554f'
PROOFS = 'superhunter/product_supply/iam-native-sources.json'
PROOFS_SHA = '3316d5bc2adf9e82db6b9ae16929d86115df3ebf32c3dfb300851e7635d4ab8e'


def inputs():
    actions = {'readonly': ['s3:GetObject'], 'permissions': ['s3:GetObject', 'iam:PassRole'],
               'wildcard': ['s3:GetObject', 'iam:Pass*'],
               'unknown': ['iam:NQCActionDoesNotExist'], 'denied': ['iam:PassRole']}
    return {'policies': {name: {'Version': '2012-10-17', 'Statement': [
        {'Effect': 'Deny' if name == 'denied' else 'Allow', 'Action': values, 'Resource': '*'}]}
        for name, values in actions.items()}}


def verify_installed(work, proof):
    expected = proof['python_git_blobs']
    actual = {p.relative_to(work/'lib').as_posix() for p in (work/'lib/policy_sentry').rglob('*.py')}
    if set(expected) != actual:
        raise EvidenceError('IAM native Python membership differs from the catalog')
    for name, oid in expected.items():
        if git_object('blob', read_artifact(work/'lib', name)) != oid:
            raise EvidenceError('IAM native source differs from the catalog Git blob')
    data = proof['data']
    # The 13 MB upstream database has an explicit bound; it does not expand the
    # generic artifact budget. Stage verified bytes in the private installation.
    checked = work/'verified-iam.json'
    copy_release('IAM database', work/'lib'/data['path'], checked, data['installed_sha256'],
                 limit=data['installed_bytes'], executable=False)
    if checked.stat().st_size != data['installed_bytes']:
        raise EvidenceError('IAM database size differs')
    checked.replace(work/'lib'/data['path'])
    return len(actual)


def validate(native, payload):
    if (set(native) != {'version', 'cases'} or native['version'] != '0.16.1'
            or set(native['cases']) != set(payload['policies'])):
        raise EvidenceError('IAM native version or control membership differs')
    expected_actions = {'readonly': ['s3:GetObject'], 'permissions': ['iam:PassRole', 's3:GetObject'],
                        'wildcard': ['iam:PassRole', 's3:GetObject'],
                        'unknown': ['iam:NQCActionDoesNotExist'], 'denied': []}
    checked = {}
    for name, policy in payload['policies'].items():
        levels = {'Read': ['s3:GetObject'] if name in ('readonly', 'permissions', 'wildcard') else [],
                  'Write': [],
                  'Permissions management': ['iam:PassRole'] if name in ('permissions', 'wildcard') else []}
        unknown = ['iam:NQCActionDoesNotExist'] if name == 'unknown' else []
        expanded = {'Version': '2012-10-17', 'Statement': [
            {**policy['Statement'][0], 'Action': expected_actions[name]}]}
        wanted = {'expanded': expanded, 'access_levels': levels, 'unknown_actions': unknown}
        if canonical(native['cases'][name]) != canonical(wanted):
            raise EvidenceError('IAM native control disagrees with the owned policy witness')
        # Absence from the upstream catalog must remain unresolved, never safe.
        state = ('unknown_action' if unknown else 'permissions_management_present'
                 if levels['Permissions management'] else 'no_management_action_in_this_control')
        checked[name] = {**wanted, 'input_sha256': sha(canonical(policy)), 'review_state': state}
    return checked


def run(kit):
    if sys.version_info[:2] != (3, 12):
        raise EvidenceError('IAM native kit requires CPython 3.12')
    raw = read_artifact(ROOT, PROOFS)
    if sha(raw) != PROOFS_SHA:
        raise EvidenceError('IAM source proof differs')
    proof, payload = strict_json(raw), inputs()
    with tempfile.TemporaryDirectory(prefix='nqc-iam-native-') as temp:
        work = Path(temp)
        env = {'HOME': temp, 'TMPDIR': temp, 'PATH': '/usr/bin:/bin', 'PYTHONIOENCODING': 'utf-8'}
        install_wheels(Path(kit), work, env, lock_path=LOCK, lock_digest=LOCK_SHA, producer='IAM native')
        count = verify_installed(work, proof)
        proc = subprocess.run([*ISOLATE, sys.executable, '-I', '-B', '-S',
                               str(Path(__file__).with_name('product_iam_native_worker.py'))],
                              cwd=work, env=env, input=canonical(payload), capture_output=True, timeout=45)
        if proc.returncode or proc.stdout or proc.stderr:
            raise EvidenceError('IAM native worker did not complete cleanly')
        observations = validate(strict_json(read_artifact(work, 'iam-native.json')), payload)
    return {'schema_version': 1, 'repository': 'salesforce/policy_sentry', 'revision': proof['revision'],
            'version': '0.16.1', 'lock_sha256': LOCK_SHA, 'source_proofs_sha256': PROOFS_SHA,
            'verified_python_files': count, 'database_sha256': proof['data']['installed_sha256'],
            'input_sha256': sha(canonical(payload)), 'observations': observations,
            'scope': {'fixed_owned_policies': 5, 'network_access': False,
                      'effective_aws_authorization_evaluated': False,
                      'unknown_actions_preserved': True, 'original_vulnerabilities_confirmed': 0,
                      'limits': 'Catalog classification only; conditions, deny precedence, resource boundaries, service control policies and account state are not evaluated.'}}
