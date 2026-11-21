"""Reason about exact dependency pins on NQC's own product inputs."""
from __future__ import annotations

from collections import defaultdict
from itertools import combinations
import re
import tomllib

from .safe_io import strict_json


PROFILES = ('custody', 'local-lab', 'otel-qa', 'owned-cross-evm', 'owned-slither', 'owned-spec-evm')
INPUTS = {'census/Cargo.lock': 'nqc-census/Cargo.lock', **{
    f'{profile}/requirements.txt': f'superhunter/requirements-{profile}.txt' for profile in PROFILES}}
PIN = re.compile(r'([A-Za-z0-9][A-Za-z0-9_.-]*)==([A-Za-z0-9][A-Za-z0-9.+!-]*)(?:\s+--hash=sha256:[a-f0-9]{64})?')


class EvidenceError(ValueError):
    """Diagnostic containing only fixed product terms."""


def python_name(name):
    return re.sub(r'[-_.]+', '-', name.casefold())


def declared_facts(inputs):
    """Independent of Syft: read exact versions directly from TOML and requirements."""
    facts = set()
    for location, raw in inputs.items():
        if location == 'census/Cargo.lock':
            lock = tomllib.loads(raw.decode())
            if lock['version'] != 4 or not lock['package']:
                raise EvidenceError('unsupported Cargo lock')
            rows = [(p['name'], p['version']) for p in lock['package']]
        else:
            rows = []
            for line in raw.decode().splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    match = PIN.fullmatch(line)
                    if not match:
                        raise EvidenceError('unsupported Python requirement')
                    rows.append((python_name(match[1]), match[2]))
            if len({name for name, _ in rows}) != len(rows):
                raise EvidenceError('duplicate package in a Python profile')
        if not rows or len(set(rows)) != len(rows):
            raise EvidenceError('empty or duplicate input facts')
        facts.update((location, name, version) for name, version in rows)
    return facts


def observed_facts(raw):
    sbom = strict_json(raw)
    if (sbom['descriptor']['name'], sbom['descriptor']['version'], sbom['schema']['version']) != (
            'syft', '1.38.2', '16.1.0'):
        raise EvidenceError('unexpected SBOM producer or schema')
    facts = set()
    for item in sbom['artifacts']:
        if not item['locations'] or not isinstance(item['name'], str) or not isinstance(item['version'], str):
            raise EvidenceError('incomplete SBOM observation')
        for loc in item['locations']:
            location = loc['path'].removeprefix('/')
            if location not in INPUTS:
                raise EvidenceError('SBOM location outside product inputs')
            rust = location == 'census/Cargo.lock'
            expected = ('rust-crate', 'rust-cargo-lock-cataloger') if rust else ('python', 'python-package-cataloger')
            if (item['type'], item['foundBy']) != expected:
                raise EvidenceError('unexpected cataloger at source location')
            name = item['name'] if rust else python_name(item['name'])
            fact = (location, name, item['version'])
            if fact in facts:
                raise EvidenceError('duplicate SBOM observation')
            facts.add(fact)
    return facts


def pin_conflicts(facts):
    """Extract the shared packages which would need two versions in one environment."""
    pins = defaultdict(dict)
    for path, name, version in sorted(facts):
        if path.endswith('/requirements.txt'):
            pins[name][path.split('/')[0]] = version
    return {name: versions for name, versions in sorted(pins.items()) if len(set(versions.values())) > 1}


def isolation_candidates(conflicts):
    """Check first the profile whose isolation removes the most conflicting pairs."""
    neighbors = defaultdict(set)
    for versions in conflicts.values():
        for left, right in combinations(versions, 2):
            if versions[left] != versions[right]:
                neighbors[left].add(right)
                neighbors[right].add(left)
    return sorted(neighbors, key=lambda p: (-len(neighbors[p]), p))


def solver_input(conflicts, count, *, excluding=None):
    lines = ['(set-logic QF_LIA)']
    for i in range(len(PROFILES)):
        lines.extend((f'(declare-const p{i} Int)', f'(assert (and (<= 0 p{i}) (< p{i} {count})))'))
    edges = set()
    for pins in conflicts.values():
        for a, b in combinations(sorted(pins), 2):
            if excluding not in (a, b) and pins[a] != pins[b]:
                edges.add((PROFILES.index(a), PROFILES.index(b)))
    lines.extend(f'(assert (distinct p{a} p{b}))' for a, b in sorted(edges))
    return ('\n'.join([*lines, '(check-sat)', '(exit)', ''])).encode()


def minimum_partition(facts):
    """Independent verifier: try every unlabelled partition directly against file pins."""
    pins = {p: {} for p in PROFILES}
    for path, name, version in facts:
        if path.endswith('/requirements.txt'):
            pins[path.split('/')[0]][name] = version
    best = [[p] for p in PROFILES]

    def visit(index, groups):
        nonlocal best
        if len(groups) >= len(best):
            return
        if index == len(PROFILES):
            best = [g.copy() for g in groups]
            return
        profile = PROFILES[index]
        for group in groups:
            if all(pins[other].get(name, version) == version
                   for other in group for name, version in pins[profile].items()):
                group.append(profile)
                visit(index + 1, groups)
                group.pop()
        visit(index + 1, [*groups, [profile]])

    visit(0, [])
    return best
