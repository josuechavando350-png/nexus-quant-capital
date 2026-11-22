"""Offline retrospective and external conformance checks for Hunter's pinned RBAC engine."""
import argparse
import csv
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from time import monotonic_ns

REV = '05002c36c12a1b572b5d425b7b0714189c448109'
HERE = Path(__file__).resolve().parent
VERSIONS = ('v1.21.0', 'v1.22.0')
ROLES = ('admin', 'edit', 'view')
VERBS = ('create', 'update', 'patch', 'delete', 'deletecollection')
FAMILIES = {'basic': 'rbac_policy.csv', 'deny': 'rbac_with_deny_policy.csv',
            'hierarchy': 'rbac_with_hierarchy_policy.csv'}


def canonical(x):
    return (json.dumps(x, sort_keys=True, separators=(',', ':')) + '\n').encode()


def digest(data):
    return sha256(data).hexdigest()


def inputs(folder, fetch):
    pins = json.loads((HERE/'inputs.json').read_bytes())
    for name, info in pins.items():
        file = folder/name
        if fetch and not file.exists():
            file.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(['curl', '-fsSL', '--retry', '2', '--max-time', '45',
                            info['url'], '-o', file], check=True)
        if digest(file.read_bytes()) != info['sha256']:
            raise ValueError('input digest mismatch: ' + name)


def role():
    return {'inherits': [], 'allow': [], 'deny': []}


def model(roles, users, permissions, assertions=()):
    return {'schema_version': 1, 'model': 'sh-rbac-v1', 'policy_id': 'permission.review',
            'permissions': sorted(permissions), 'roles': roles, 'users': users,
            'assertions': list(assertions), 'separation_rules': [], 'revocations': []}


def projected_cluster(raw, subject, with_rule):
    """Keep direct grants and aggregation separate. Hunter resolves the transitive graph."""
    import yaml

    items = {r['metadata']['name']: r for r in yaml.safe_load(raw)['items']}
    aliases = {n: f'r{i}' for i, n in enumerate(sorted(items))}
    roles = {}
    def visit(name):
        key = aliases[name]
        if key in roles:
            return
        entry = items[name]
        grants = set()
        for r in entry.get('rules') or []:
            if r.get('resourceNames') or not {'', '*'} & set(r.get('apiGroups', [])):
                continue
            if not {'endpoints', '*'} & set(r.get('resources', [])):
                continue
            grants.update(v for v in VERBS if v in r['verbs'] or '*' in r['verbs'])
        parents = set()
        for selector in entry.get('aggregationRule', {}).get('clusterRoleSelectors', []):
            if set(selector) != {'matchLabels'}:
                raise ValueError('unsupported aggregation selector')
            for other, candidate in items.items():
                labels = candidate['metadata'].get('labels', {})
                if all(labels.get(k) == v for k, v in selector['matchLabels'].items()):
                    parents.add(other)
        roles[key] = {'inherits': sorted(aliases[p] for p in parents), 'allow': sorted(grants), 'deny': []}
        for parent in parents:
            visit(parent)

    visit(subject)
    checks = [{'id': 'q.'+v, 'user': 'principal', 'permission': v, 'expected': 'DENY'}
              for v in VERBS] if with_rule else []
    return model(roles, {'principal': {'roles': [aliases[subject]], 'disabled': False}}, VERBS, checks)


def casbin_model(folder, family):
    rows = list(csv.reader((folder/'casbin/examples'/FAMILIES[family]).read_text().splitlines(),
                           skipinitialspace=True))
    roles, permissions = {}, set()
    for row in filter(None, rows):
        kind, actor, *tail = row
        current = roles.setdefault(actor, role())
        if kind == 'g' and len(tail) == 1:
            parent, = tail
            roles.setdefault(parent, role())
            current['inherits'].append(parent)
        elif kind == 'p' and len(tail) in (2, 3):
            obj, act, *effect = tail
            permission = obj + '.' + act
            (mode,) = effect or ['allow']
            if mode not in ('allow', 'deny'):
                raise ValueError('unknown policy effect')
            current[mode].append(permission)
            permissions.add(permission)
        else:
            raise ValueError('unsupported Casbin test fixture')
    users = {n: {'roles': [n], 'disabled': False} for n in ('alice', 'bob')}
    return model(roles, users, permissions)


def casbin_reference(folder, family, permissions):
    if family == 'hierarchy':
        text = (folder/'casbin/rbac_api_test.go').read_text().split('func TestImplicitPermissionAPI(')[1]
        part = text.split('e, _ = NewEnforcer', 1)[0]
        lines = [s for s in part.splitlines() if 'testGetImplicitPermissions(t, e,' in s]
        result = {}
        for line in lines:
            subject = re.search(r'testGetImplicitPermissions\(t, e, "(\w+)"', line)[1]
            entries = re.findall(r'\{"\w+", "(\w+)", "(\w+)"\}', line)
            if not entries:
                raise ValueError('empty external permission table')
            expected = {obj+'.'+act for obj, act in entries}
            if not expected <= set(permissions):
                raise ValueError('incomplete policy dimension')
            result.update({(subject, perm): perm in expected for perm in permissions})
    else:
        test = 'TestRBACModel' if family == 'basic' else 'TestRBACModelWithDeny'
        body = (folder/'casbin/model_test.go').read_text().split('func '+test+'(')[1].split('\n}', 1)[0]
        lines = [s for s in body.splitlines() if 'testEnforce(' in s]
        result = {}
        for line in lines:
            match = re.fullmatch(r'\s*testEnforce\(t, e, "(\w+)", "(\w+)", "(\w+)", (true|false)\)', line)
            if not match:
                raise ValueError('unsupported upstream assertion')
            user, obj, act, answer = match.groups()
            result[user, obj+'.'+act] = answer == 'true'
        if len(lines) != len(result):
            raise ValueError('repeated external assertion')
    if len(result) != 8:
        raise ValueError('unexpected external case membership')
    return result


def invoke(product, args):
    run = subprocess.run([sys.executable, '-B', '-m', 'superhunter', *args], cwd=product,
                         stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
    if run.returncode not in (0, 1):
        raise ValueError('Hunter did not produce a verified review: '+str(run.returncode))
    receipt = json.loads(run.stdout)
    if (run.returncode == 1) != (receipt['status'] == 'POLICY_ASSERTIONS_FAIL'):
        raise ValueError('ambiguous review result')
    return receipt['status']


def audit(product, temp, policy):
    with tempfile.TemporaryDirectory(dir=temp) as out:
        base = Path(out)
        (base/'policy.json').write_bytes(canonical(policy))
        status = invoke(product, ['audit-permissions', '--policy', base/'policy.json', '--out', base/'result'])
        replay = invoke(product, ['verify-permissions', '--bundle', base/'result'])
        analysis = json.loads((base/'result/analysis.json').read_bytes())
        if status != replay or replay != analysis['status']:
            raise ValueError('audit and replay disagree')
        return analysis


def historic(product, folder, work, mode):
    from superhunter import holdout_protocol as h

    root = work/mode
    ins = root/'inputs'
    ins.mkdir(parents=True)
    cases, labels, policies, keymap = [], [], {}, {}
    for version in VERSIONS:
        raw = (folder/(version+'.yaml')).read_bytes()
        for name in ROLES:
            source = {'manifest': digest(raw), 'role': name}
            hashed = digest(canonical(source))
            key = 'case.' + hashed[:16]
            cases.append({'case_id': key, 'group_id': 'k8s.shared.mitigation', 'split': 'test',
                          'family': 'role.policy', 'content_sha256': hashed})
            positive = version == 'v1.21.0' and name in ('admin', 'edit')
            labels.append({'case_id': key, 'truth': 'positive' if positive else 'negative',
                           'severity': 'medium' if positive else 'none'})
            policies[key] = projected_cluster(raw, name, mode == 'explicit')
            keymap[key] = version+'/'+name
    manifest = {'schema_version': 1, 'corpus_id': 'historic.rbac', 'provenance': 'curated', 'cases': cases}
    (ins/'manifest.json').write_bytes(canonical(manifest))
    (ins/'labels.json').write_bytes(canonical({'schema_version': 1, 'corpus_id': 'historic.rbac', 'cases': labels}))
    prepared = h.prepare(ins/'manifest.json', ins/'labels.json', root/'public', root/'private')['prepared_sha256']
    records, decisions = [], {}
    for key in sorted(policies):
        start = monotonic_ns()
        result = audit(product, work, policies[key])
        decision = {'POLICY_ASSERTIONS_FAIL': 'positive', 'POLICY_ASSERTIONS_PASS': 'negative',
                    'POLICY_REVIEW_ONLY': 'abstain'}[result['status']]
        records.append({'case_id': key, 'decision': decision, 'elapsed_ms': (monotonic_ns()-start)//1000000,
                        'cost_micro_usd': None})
        decisions[keymap[key]] = decision
    predictions = {'schema_version': 1, 'run_id': 'historic.'+mode, 'records': records,
                   'producer': {'name': 'hunter.rbac', 'source_sha256': digest((product/'superhunter/permissions.py').read_bytes())},
                   'manifest_sha256': digest(canonical(manifest))}
    (ins/'predictions.json').write_bytes(canonical(predictions))
    frozen = h.freeze(root/'public', ins/'predictions.json', root/'frozen', expected_prepared_sha256=prepared)
    anchors = {'expected_prepared': prepared, 'expected_frozen': frozen['submission_sha256']}
    scored = h.score(root/'frozen', root/'private', root/'scored', **anchors)
    (root/'anchors.json').write_bytes(canonical(anchors))
    checked = h.verify(root/'scored', **anchors)
    if checked != scored:
        raise ValueError('holdout replay differs')
    return {'counts': checked['metrics']['overall']['counts'], 'decisions': decisions}


def conformance(product, folder, work):
    results = {}
    for family in FAMILIES:
        policy = casbin_model(folder, family)
        analysis = audit(product, work, policy)
        # Serialize the full permission state before loading any upstream expected output.
        snapshot = work/('casbin-'+family+'.json')
        with snapshot.open('xb') as stream:
            stream.write(canonical(analysis['states']))
        frozen = snapshot.read_bytes()
        truth = casbin_reference(folder, family, policy['permissions'])
        states = json.loads(frozen)
        counts = Counter()
        for (actor, perm), wanted in truth.items():
            observed = perm in states[actor]['allowed']
            counts['correct' if observed == wanted else 'incorrect'] += 1
            counts['reference_allow' if wanted else 'reference_deny'] += 1
        results[family] = {'counts': dict(counts), 'frozen_state_sha256': digest(frozen)}
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inputs', type=Path)
    parser.add_argument('--fetch-only', action='store_true')
    parser.add_argument('--product', type=Path)
    parser.add_argument('--evidence-dir', type=Path, required=False, help='new directory for native receipts')
    args = parser.parse_args()
    inputs(args.inputs, args.fetch_only)
    if args.fetch_only:
        return
    if args.product is None:
        parser.error('--product is required for scoring')
    product = args.product.resolve()
    git = ['git', '-C', str(product)]
    if (subprocess.check_output([*git, 'rev-parse', 'HEAD']).decode().strip() != REV or
            subprocess.check_output([*git, 'status', '--porcelain', '--untracked-files=all'])):
        raise ValueError('a clean checkout of the published producer is required')
    sys.path.insert(0, str(product))
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        if args.evidence_dir is not None:
            work = args.evidence_dir.resolve()
            if work.is_relative_to(product) or work.is_relative_to(args.inputs.resolve()):
                raise ValueError('evidence must be outside the product and input directories')
            work.mkdir(mode=0o700, parents=False, exist_ok=False)
        report = {'producer': REV, 'protocol_sha256': digest((HERE/'protocolo.txt').read_bytes()),
                  'historical': {mode: historic(product, args.inputs, work, mode)
                                 for mode in ('explicit', 'without_rule')},
                  'casbin_conformance': conformance(product, args.inputs, work)}
        output = json.dumps(report, indent=2, sort_keys=True)
        (work/'resultado.json').write_text(output+'\n')
        print(output)


if __name__ == '__main__':
    main()
