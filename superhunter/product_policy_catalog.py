"""Reconcile the five owned IAM report fixtures with iamlive's pinned static SDK mapping."""
from fnmatch import fnmatchcase
import json

from .product_iam_native import inputs
from .product_policy_report import OWNED_SHA, SENTRY_REPORT, SENTRY_SHA, sentry_states
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_sources import git
from .repository_boundary import git_object
from .safe_io import canonical, read_artifact, strict_json


PROJECT = 'iann0036/iamlive'
REVISION = '3ec1a40e560c2f00ec82c50223add810e2567efb'
PINS = {
    'map.json': ('998ede474e5e5daaa3f04ba43543e8109c250e04', 7352372,
                 'f6ab658506c1f21875cc8dd3c4a4ed2191c7eb4e6233c36678c841c3e2b330b4'),
    'iam_definition.json': ('ecf3df0a28567b358005fd922f21dc367c856999', 11081787,
                            '2ec6e80322edd149eeff984bcbc67736b3d01f7b75e3abc8734a6a84847b855d'),
}


def read_table(repo, name):
    # Read only the two exact, size-bounded blobs. Generic artifact limits still apply elsewhere.
    blob, size, digest = PINS[name]
    oid = git(repo, 'rev-parse', REVISION + ':iamlivecore/' + name).decode().strip()
    if oid != blob or int(git(repo, 'cat-file', '-s', oid)) != size:
        raise EvidenceError('iamlive static corpus object or size differs')
    data = git(repo, 'cat-file', 'blob', oid)
    if len(data) != size or sha(data) != digest or git_object('blob', data) != oid:
        raise EvidenceError('iamlive static corpus differs from its pinned bytes')
    return json.loads(data)


def definitions(services):
    levels = {}
    for service in services:
        prefix = service['prefix']
        if prefix not in ('iam', 's3'):
            continue
        for row in service['privileges']:
            action = prefix + ':' + row['privilege']
            if action in levels or not row['access_level']:
                raise EvidenceError('duplicate or unclassified permission in reviewed service')
            levels[action] = row['access_level']
    if {act.split(':')[0] for act in levels} != {'iam', 's3'}:
        raise EvidenceError('missing an owned service definition')
    return levels


def action_summary(actions, levels, catalog):
    if catalog.get('schema_version') != '1.0.2':
        raise EvidenceError('unreviewed SDK mapping schema')
    seen = {action: set() for action in actions}
    conditional = {action: set() for action in actions}
    for method, rows in catalog['sdk_method_iam_mappings'].items():
        if type(rows) is not list:
            raise EvidenceError('invalid SDK method mapping')
        for row in rows:
            if type(row) is not dict or type(row.get('action')) is not str:
                raise EvidenceError('missing explicit SDK permission mapping')
            action = row['action']
            if action in seen:
                seen[action].add(method)
                if 'conditions' in row:
                    conditional[action].add(method)
    out = {}
    for action in sorted(actions):
        service, operation = action.split(':')
        if action not in levels and seen[action]:
            raise EvidenceError('SDK permission mapping is absent from the IAM definition')
        aliases = catalog['service_sdk_mappings'].get(service)
        if type(aliases) is not list or not aliases or not all(type(a) is str for a in aliases):
            raise EvidenceError('incomplete SDK service aliases')
        out[action] = {'defined_access_level': levels.get(action),
                       'sdk_methods_linked': len(seen[action]),
                       'sdk_methods_with_mapping_conditions': len(conditional[action]),
                       'has_same_named_mapped_method': any(alias + '.' + operation in seen[action] for alias in aliases)}
    return out


def join(owned, sentry, levels, mapping):
    states = sentry_states(owned, sentry)
    actions = set()
    rows = {}
    for name, policy in owned.items():
        item = sentry['observations'][name]
        statement, = policy['Statement']
        expanded, unknown = set(), set()
        for pattern in statement['Action']:
            matches = {a for a in levels if fnmatchcase(a.lower(), pattern.lower())}
            if matches:
                expanded.update(matches)
            else:
                unknown.add(pattern)
        observed, = item['expanded']['Statement']
        # These are identity policy examples. A Deny has no allowed expansion.
        applicable = expanded if statement['Effect'] == 'Allow' else set()
        unresolved = unknown if statement['Effect'] == 'Allow' else set()
        if (set(item['unknown_actions']) != unresolved or set(observed['Action']) != applicable | unresolved
                or observed['Effect'] != statement['Effect']):
            raise EvidenceError('independent catalog and archived action expansion disagree')
        for kind, members in item['access_levels'].items():
            if set(members) != {a for a in applicable if levels[a] == kind}:
                raise EvidenceError('independent and reported IAM access levels disagree')
        if not {levels[a] for a in applicable}.issubset(item['access_levels']):
            raise EvidenceError('report omitted a recognized access level')
        actions.update(expanded | unknown)
        rows[name] = {'effect': statement['Effect'], 'defined_actions': sorted(expanded),
                      'included_in_allow_statement': sorted(applicable), 'unknown_actions': sorted(unknown),
                      'sentry_action_review': states[name], 'input_sha256': sha(canonical(policy))}
    return {'permissions': action_summary(actions, levels, mapping), 'cases': rows}


def corroborate(catalog, cloudfox):
    owned = inputs()['policies']
    if (catalog['identity_policies_sha256'] != OWNED_SHA or cloudfox['identity_policies_sha256'] != OWNED_SHA
            or catalog['sentry_report_sha256'] != SENTRY_SHA or cloudfox['sentry_report_sha256'] != SENTRY_SHA
            or set(catalog['cases']) != set(owned) or set(cloudfox['owned_identity_policies']) != set(owned)):
        raise EvidenceError('IAM report consumers used different fixtures')
    for name, case in catalog['cases'].items():
        counterpart = cloudfox['owned_identity_policies'][name]
        if (case['input_sha256'] != sha(canonical(owned[name])) or case['sentry_action_review'] != counterpart['action_review']
                or counterpart['public'] is not False
                or counterpart['conditional'] is not False or counterpart['statements'] != 1):
            raise EvidenceError('identity policy and public-principal corroboration disagree')
    summary = {'cases_compared': len(catalog['cases']), 'public_principals': 0,
               'catalog_sha256': sha(canonical(catalog)), 'cloudfox_sha256': sha(canonical(cloudfox))}
    return {**summary, 'joint_sha256': sha(canonical(summary))}


def review(root):
    repo = root / '084-iamlive'
    if repo.is_symlink() or git(repo, 'rev-parse', 'HEAD').decode().strip() != REVISION:
        raise EvidenceError('iamlive source revision differs')
    raw = read_artifact(ROOT, SENTRY_REPORT)
    owned = inputs()['policies']
    if sha(raw) != SENTRY_SHA or sha(canonical(owned)) != OWNED_SHA:
        raise EvidenceError('owned policy report differs')
    result = join(owned, strict_json(raw), definitions(read_table(repo, 'iam_definition.json')),
                  read_table(repo, 'map.json'))
    return {PROJECT: {'revision': REVISION, 'operation': 'reconcile_action_catalog_and_sdk_method_counts',
                      'identity_policies_sha256': OWNED_SHA, 'sentry_report_sha256': SENTRY_SHA,
                      'corpus_sha256': {k: v[2] for k, v in PINS.items()}, **result}}
