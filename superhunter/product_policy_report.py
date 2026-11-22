"""Corroborate the public-principal interpretation of five archived Policy Sentry inputs."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .product_iam_native import inputs as iam_inputs
from .product_notice_ranking import ISOLATE
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_sources import git
from .product_state_formats_batch import GO_SHA
from .repository_boundary import git_object
from .safe_io import canonical, read_artifact, strict_json


REPOSITORY = 'BishopFox/cloudfox'
REVISION = 'f65be085cde3768281c2dbafc57542a56ee12ebe'
FOLDER = 'internal/aws/policy'
TREE = 'b493724d10fc59d227e5e6d472f7774bfa5a3e52'
SOURCE = ('policy.go', 'statement.go', 'principal.go', 'condition.go')
OWNED_SHA = 'f4f57428286558c8f5e7a06a420be8bf70b4f64a4d478072d4d0d3994c87f9a0'
BINARY_SHA = '8202aaee22033cabd6f4ac4de908ea1b5691eb18b769b7cd2da10ba92f8c87b8'
SENTRY_REPORT = 'superhunter/product_supply/iam-native-result.json'
SENTRY_SHA = 'eca8aacd8dded157fd8ac2a45d4ed08a0d2d6c84f87532db431bda0183bd36fe'
DRIVER = """package main

import (
    "encoding/json"
    "os"
    "nqc.local/policyreview/policy"
)

type classification struct {
    Public bool `json:"public"`
    Conditional bool `json:"conditional"`
    Statements int `json:"statements"`
}

func main() {
    var inputs map[string]json.RawMessage
    if json.NewDecoder(os.Stdin).Decode(&inputs) != nil || len(inputs) != 13 { os.Exit(1) }
    results := make(map[string]classification)
    for name, raw := range inputs {
        parsed, err := policy.ParseJSONPolicy(raw)
        if err != nil || len(parsed.Statement) == 0 { os.Exit(1) }
        results[name] = classification{parsed.IsPublic(), parsed.IsConditionallyPublic(), len(parsed.Statement)}
    }
    if json.NewEncoder(os.Stdout).Encode(results) != nil { os.Exit(1) }
}
"""


def source_files(root):
    repo = root / '079-cloudfox'
    if repo.is_symlink() or git(repo, 'rev-parse', 'HEAD', 'HEAD:' + FOLDER).decode().splitlines() != [REVISION, TREE]:
        raise EvidenceError('CloudFox source revision or policy tree differs')
    files, blobs = {}, {}
    for line in git(repo, 'ls-tree', '-r', TREE).decode().splitlines():
        meta, path = line.split('\t')
        if path not in (*SOURCE, 'policy_test.go') and not path.startswith('testdata/'):
            continue
        mode, kind, blob = meta.split()
        data = read_artifact(repo, FOLDER + '/' + path)
        if (mode, kind) != ('100644', 'blob') or git_object('blob', data) != blob:
            raise EvidenceError('CloudFox policy source or fixture bytes differ')
        files[path] = data
        blobs[path] = blob
    return files, blobs


def build(work, files, go):
    with go.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != GO_SHA:
            raise EvidenceError('Go compiler differs from reviewed producer')
    package = work / 'policy'
    package.mkdir()
    for name in SOURCE:
        (package / name).write_bytes(files[name])
    (work / 'main.go').write_text(DRIVER)
    (work / 'go.mod').write_text('module nqc.local/policyreview\n\ngo 1.27.4\n')
    temp = work / 'tmp'
    temp.mkdir()
    env = {'GOROOT': str(go.parent.parent), 'GOCACHE': str(work / 'cache'), 'GOPATH': str(work / 'gopath'),
           'GOSUMDB': 'off', 'GOPROXY': 'off', 'GOTOOLCHAIN': 'local', 'GOENV': 'off', 'CGO_ENABLED': '0',
           'HOME': str(work), 'TMPDIR': str(temp), 'PATH': os.defpath, 'LANG': 'C'}
    target = work / 'classify'
    subprocess.run([*ISOLATE, go, 'build', '-p', '2', '-trimpath', '-mod=readonly', '-buildvcs=false',
                    '-ldflags=-buildid=', '-o', target, '.'], cwd=work, env=env, capture_output=True, check=True,
                   timeout=150)
    return target


def upstream_expectations(src):
    tables = {}
    for native, field in [('IsPublic', 'public'), ('IsConditionallyPublic', 'conditional')]:
        declaration = 'func Test' + native + '(t *testing.T) {'
        if src.count(declaration) != 1:
            raise EvidenceError('missing CloudFox assertion function')
        body = src.split(declaration)[1].split('\n}', 1)[0]
        records = re.findall(r'\{filename: "([a-z0-9-]+\.json)", want: (true|false)\}', body)
        if len(records) != 8 or len(dict(records)) != 8 or 'actual := policy.' + native + '()' not in body:
            raise EvidenceError('incomplete CloudFox assertion table')
        tables[field] = {name: val == 'true' for name, val in records}
    if set(tables['public']) != set(tables['conditional']):
        raise EvidenceError('CloudFox reference cases disagree')
    return {name: {field: table[name] for field, table in tables.items()} for name in tables['public']}


def terms(value):
    return (isinstance(value, str) and bool(value)) or (
        isinstance(value, list) and bool(value) and all(isinstance(item, str) and item for item in value))


def statements(policy, *, resource_policy=False):
    if (type(policy) is not dict or set(policy) - {'Statement', 'Version', 'Id'}
            or type(policy.get('Statement')) is not list or not policy['Statement']
            or any(type(policy[k]) is not str or not policy[k] for k in ('Version', 'Id') if k in policy)):
        raise EvidenceError('incomplete IAM policy')
    for s in policy['Statement']:
        if (type(s) is not dict or set(s) - {'Sid', 'Effect', 'Action', 'Resource', 'Principal', 'Condition'}
                or s.get('Effect') not in ('Allow', 'Deny') or not terms(s.get('Action')) or not terms(s.get('Resource'))):
            raise EvidenceError('unexpected or incomplete IAM statement')
        if resource_policy and 'Principal' not in s:
            raise EvidenceError('resource policy is missing its principal')
        if 'Principal' in s:
            p = s['Principal']
            if not ((isinstance(p, str) and p) or (isinstance(p, dict) and p
                    and not set(p) - {'AWS', 'Service', 'Federated', 'CanonicalUser'} and all(terms(v) for v in p.values()))):
                raise EvidenceError('malformed resource principal')
        if 'Condition' in s:
            conditions = s['Condition']
            if (type(conditions) is not dict or not conditions or any(
                type(clause) is not dict or not clause or not all(terms(v) for v in clause.values())
                for clause in conditions.values()
            )):
                raise EvidenceError('malformed resource condition')
    return policy['Statement']


def sentry_states(owned, report):
    observations = report.get('observations')
    if (report.get('input_sha256') != sha(canonical({'policies': owned}))
            or type(observations) is not dict or set(observations) != set(owned)):
        raise EvidenceError('Policy Sentry report does not cover these inputs')
    states = {}
    for name, policy in owned.items():
        observation = observations[name]
        if observation.get('input_sha256') != sha(canonical(policy)) or type(observation.get('review_state')) is not str:
            raise EvidenceError('Policy Sentry row belongs to another input')
        states[name] = observation['review_state']
    return states


def classify(root, work):
    files, blobs = source_files(root)
    expected = upstream_expectations(files['policy_test.go'].decode())
    if {k for k in files if k.startswith('testdata/')} != {'testdata/' + name for name in expected}:
        raise EvidenceError('CloudFox test controls differ from its assertion tables')
    reference = {name: strict_json(files['testdata/' + name]) for name in expected}
    owned = iam_inputs()['policies']
    if sha(canonical(owned)) != OWNED_SHA or len(owned) != 5:
        raise EvidenceError('owned Policy Sentry inputs differ')
    raw_report = read_artifact(ROOT, SENTRY_REPORT)
    if sha(raw_report) != SENTRY_SHA:
        raise EvidenceError('archived Policy Sentry report differs')
    states = sentry_states(owned, strict_json(raw_report))
    for name in owned:
        rows = statements(owned[name])
        if any('Principal' in row or row['Resource'] != '*' for row in rows):
            raise EvidenceError('owned identity policy no longer has its reviewed shape')
        expected[name] = {'public': False, 'conditional': False}
    policies = dict(reference, **owned)
    for name, item in policies.items():
        resource = name in reference and name != 'amazon-ec2-full-access.json'
        expected[name]['statements'] = len(statements(item, resource_policy=resource))
    compiler = os.environ.get('NQC_STATE_GO') or shutil.which('go')
    if compiler is None:
        raise EvidenceError('reviewed Go compiler unavailable')
    go = Path(compiler).resolve(strict=True)
    target = build(work, files, go)
    digest = sha(target.read_bytes())
    if digest != BINARY_SHA:
        raise EvidenceError('compiled policy classifier differs from reproduced binary')
    run = subprocess.run([*ISOLATE, target], cwd=work, input=canonical(policies), env={'HOME': str(work)},
                         capture_output=True, check=True, timeout=8)
    results = strict_json(run.stdout)
    if canonical(results) != canonical(expected):
        raise EvidenceError('native principal classification disagrees with independent expectations')
    return {REPOSITORY: {'revision': REVISION, 'operation': 'compare_public_principals_in_owned_policy_report',
                         'source_tree': TREE, 'blobs': blobs, 'compiler_sha256': GO_SHA, 'binary_sha256': digest,
                         'identity_policies_sha256': OWNED_SHA, 'sentry_report_sha256': SENTRY_SHA,
                         'owned_identity_policies': {k: {**results[k], 'action_review': states[k]} for k in owned},
                         'upstream_public_principal_controls': {k: results[k] for k in reference}}}


def review(root):
    with tempfile.TemporaryDirectory(prefix='nqc-policy-report-') as directory:
        return classify(root, Path(directory))
