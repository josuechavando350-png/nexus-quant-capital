"""Compare declarative resource policies with fixed, offline Kubernetes workload manifests."""
from collections import Counter
from fractions import Fraction
import re

from .product_config_batch import yaml_modules
from .product_infra_batch import capture
from .product_reasoning import EvidenceError
from .product_review import sha
from .product_sources import git
from .safe_io import canonical

KUBE = 'stackrox/kube-linter'
CRAPI = 'OWASP/crAPI'
POLICIES = {
    'cpu': 'pkg/builtinchecks/yamls/unset-cpu-requirements.yaml',
    'memory': 'pkg/builtinchecks/yamls/unset-memory-requirements.yaml',
}
POD_SCOPE = 'pkg/extract/customtypes/pod_spec.go'
WORKLOAD_DIR = 'deploy/k8s/base/'
WORKLOADS = tuple(WORKLOAD_DIR + name + '/' + kind + '.yaml' for name, kind in (
    ('chatbot', 'deployment'), ('chromadb', 'statefulset'), ('community', 'deployment'),
    ('gateway-service', 'deployment'), ('identity', 'deployment'), ('mailhog', 'deployment'),
    ('mongodb', 'statefulset'), ('postgres', 'statefulset'), ('web', 'deployment'), ('workshop', 'deployment')))
SOURCES = {
    KUBE: ('082-kube-linter', '85cdcb9843fe07f0bf7d82026de0e79e4b517576', (*POLICIES.values(), POD_SCOPE)),
    CRAPI: ('196-crapi', 'b5fc307f3e5f875809b095b771108ef342a33724', WORKLOADS),
}
# The pinned workload corpus uses whole CPU, millicores, MiB and whole bytes.
# All comparisons are exact. Other units are outside this input contract.
UNITS = {'cpu': {'': 1000, 'm': 1}, 'memory': {'': 1, 'Mi': 1024**2, 'Gi': 1024**3}}
CONTAINER_FIELDS = {'containers': 'Containers', 'initContainers': 'InitContainers',
                    'ephemeralContainers': 'EphemeralContainers'}


def parse_policy(files, load):
    rules = {}
    for resource, path in POLICIES.items():
        rule = load(files[path])
        key_suffix = 'Millis' if resource == 'cpu' else 'MB'
        params = rule['params']
        if (rule['template'] != resource + '-requirements'
                or rule['scope']['objectKinds'] != ['DeploymentLike']
                or params['requirementsType'] not in ('request', 'limit')
                or params['lowerBound' + key_suffix] != 0 or params['upperBound' + key_suffix] != 0):
            raise EvidenceError('unsupported resource policy or bounds')
        rules[resource] = params['requirementsType'] + 's'
    body = files[POD_SCOPE].split('func (p *PodSpec) AllContainers() []v1.Container {', 1)[-1].split('\n}', 1)[0]
    scoped = set(re.findall(r'p\.PodSpec\.(\w+Containers|Containers)\b', body))
    if scoped != set(CONTAINER_FIELDS.values()):
        raise EvidenceError('unexpected container selection')
    return rules


def resource_value(resource, value):
    if type(value) not in (str, int) or len(str(value)) > 24:
        raise EvidenceError('invalid resource quantity')
    match = re.fullmatch(r'(0|[1-9][0-9]*)(\.[0-9]{1,3})?(m|Mi|Gi)?', str(value))
    if not match or (match[3] or '') not in UNITS[resource]:
        raise EvidenceError('invalid or unsupported resource quantity')
    number = Fraction(match[1] + (match[2] or '')) * UNITS[resource][match[3] or '']
    if number.denominator != 1:
        raise EvidenceError('quantity below supported resource precision')
    return int(number)


def summarize(workloads, rules):
    kinds, groups, policy_hits, completed = Counter(), Counter(), Counter(), Counter()
    comparisons = 0
    for workload in workloads:
        kind = workload['kind']
        if workload['apiVersion'] != 'apps/v1' or kind not in ('Deployment', 'StatefulSet'):
            raise EvidenceError('unsupported workload kind')
        kinds[kind] += 1
        pod = workload['spec']['template']['spec']
        if not isinstance(pod.get('containers'), list) or not pod['containers']:
            raise EvidenceError('workload has no app containers')
        for field in CONTAINER_FIELDS:
            containers = pod.get(field, [])
            if not isinstance(containers, list):
                raise EvidenceError('invalid container collection')
            groups[field] += len(containers)
            for container in containers:
                resources = container.get('resources', {})
                if not isinstance(resources, dict):
                    raise EvidenceError('invalid resource map')
                pairs = {}
                for purpose in ('requests', 'limits'):
                    quantities = resources.get(purpose, {})
                    if not isinstance(quantities, dict):
                        raise EvidenceError('invalid request or limit map')
                    pairs[purpose] = {k: resource_value(k, quantities[k]) for k in UNITS if k in quantities}
                for resource, purpose in rules.items():
                    # Kubernetes ResourceList accessors yield zero for a missing key.
                    policy_hits[resource] += pairs[purpose].get(resource, 0) == 0
                    if resource in pairs['requests'] and resource in pairs['limits']:
                        if pairs['requests'][resource] > pairs['limits'][resource]:
                            raise EvidenceError('resource request exceeds limit')
                        comparisons += 1
                complete = all(len(pairs[purpose]) == len(UNITS) for purpose in ('requests', 'limits'))
                completed['all_four' if complete else 'incomplete'] += 1
    return {'workloads': dict(kinds), 'containers': dict(groups), 'policy_diagnostics': dict(policy_hits),
            'container_resource_fields': dict(completed), 'request_limit_pairs_compared': comparisons}


def review(root):
    # The registered environment already authenticates these exact pure-Python YAML files.
    yaml_modules()
    import yaml
    for directory, revision, _ in SOURCES.values():
        if git(root / directory, 'rev-parse', 'HEAD').decode().strip() != revision:
            raise EvidenceError('workload or rule checkout differs')
    rules_src, rule_manifest = capture(root, KUBE, SOURCES)
    data, workload_manifest = capture(root, CRAPI, SOURCES)
    repository, revision, _ = SOURCES[CRAPI]
    entries = git(root / repository, 'ls-tree', '-rz', '--name-only', revision, '--', WORKLOAD_DIR)
    selected = {p.decode() for p in entries.split(b'\0') if p.endswith((b'/deployment.yaml', b'/statefulset.yaml'))}
    if selected != set(WORKLOADS):
        raise EvidenceError('workload inventory differs')
    rules = parse_policy(rules_src, yaml.safe_load)
    summary = summarize([yaml.safe_load(data[name]) for name in WORKLOADS], rules)
    hashes = {'rules_sha256': sha(canonical(rule_manifest)), 'workloads_sha256': sha(canonical(workload_manifest))}
    return {
        KUBE: {'revision': SOURCES[KUBE][1], 'role': 'reference', 'operation': 'apply_zero_resource_policies_to_workloads',
               **hashes, 'result': {'checked_fields': rules, 'containers': summary['containers'],
                                     'policy_diagnostics': summary['policy_diagnostics']}},
        CRAPI: {'revision': SOURCES[CRAPI][1], 'role': 'reference', 'operation': 'check_declared_workload_resource_pairs',
                **hashes, 'result': {key: summary[key] for key in
                                      ('workloads', 'containers', 'container_resource_fields', 'request_limit_pairs_compared')}},
    }
