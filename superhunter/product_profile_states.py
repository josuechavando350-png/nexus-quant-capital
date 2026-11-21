"""Enumerate compatible groupings of NQC's declared Python profiles with the TLC model checker."""
from __future__ import annotations

from collections import Counter
from itertools import combinations
import json
from pathlib import Path
import re
import subprocess
import tempfile

from .product_cdxgen import capture
from .product_reasoning import EvidenceError, INPUTS, PROFILES, declared_facts
from .product_review import copy_release, sha
from .safe_io import canonical, read_artifact

JAR_SHA = '936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88'
CONFIG = b'INIT Init\nNEXT Next\nINVARIANT Valid\nCHECK_DEADLOCK FALSE\n'
SPEC = r'''---- MODULE Profiles ----
EXTENDS Naturals, Sequences, FiniteSets

Pins == PROFILE_PIN_SETS
VARIABLE groups
Init == groups = <<>>
Compatible(i,j) == \A p \in Pins[i] : p[1] \notin {q[1] : q \in Pins[j]} \/ p \in Pins[j]
Next ==
  LET i == Len(groups) + 1
      Used == {groups[k] : k \in 1..Len(groups)}
  IN /\ i <= Len(Pins)
     /\ \E g \in 1..(Cardinality(Used)+1) :
           /\ \A j \in 1..Len(groups) : groups[j] = g => Compatible(i,j)
           /\ groups' = Append(groups,g)
Valid == \A i,j \in 1..Len(groups) : groups[i] = groups[j] => Compatible(i,j)
====
'''


def model(inputs):
    facts = declared_facts({local: inputs[rel] for local, rel in INPUTS.items()})
    sets = []
    for profile in PROFILES:
        pairs = [f'<<{json.dumps(name)}, {json.dumps(version)}>>'
                 for path, name, version in sorted(facts) if path == profile + '/requirements.txt']
        sets.append('{' + ', '.join(pairs) + '}')
    return SPEC.replace('PROFILE_PIN_SETS', '<<' + ',\n'.join(sets) + '>>').encode()


def parse_states(raw):
    states = set()
    for seq, entry in enumerate(raw.decode('ascii').strip().split('\n\n'), 1):
        match = re.fullmatch(r'State (\d+):\ngroups = <<([1-9]\d*(?:, [1-9]\d*)*)?>>', entry)
        if not match or int(match[1]) != seq:
            raise EvidenceError('invalid TLC state dump')
        state = tuple(map(int, match[2].split(', '))) if match[2] else ()
        if state in states or len(state) > len(PROFILES):
            raise EvidenceError('duplicate or oversized TLC state')
        states.add(state)
    return states


def assess(states, report):
    # The native model compares the full pin sets; this reader uses NQC's existing conflict report.
    incompatible = set()
    for versions in report['conflicting_python_pins'].values():
        for left, right in combinations(range(len(PROFILES)), 2):
            a, b = versions.get(PROFILES[left]), versions.get(PROFILES[right])
            if a is not None and b is not None and a != b:
                incompatible.add((left, right))
    prefixes = {()}
    expected = set(prefixes)
    for i in range(len(PROFILES)):
        prefixes = {(*p, group) for p in prefixes for group in range(1, max(p, default=0) + 2)
                    if all(old != group or (j, i) not in incompatible for j, old in enumerate(p))}
        expected.update(prefixes)
    if states != expected:
        raise EvidenceError('TLC state set differs from independently enumerated compatible profiles')
    counts = Counter(max(state) for state in prefixes)
    minimum = min(counts)
    choices = [[[name for name, tag in zip(PROFILES, p) if tag == g] for g in range(1, minimum + 1)]
               for p in sorted(prefixes) if max(p) == minimum]
    previous = {frozenset(names) for names in report['one_valid_grouping']}
    if (minimum != report['minimum_python_pin_groups'] or
            not any({frozenset(group) for group in choice} == previous for choice in choices)):
        raise EvidenceError('TLC groupings disagree with the verified product minimum or witness')
    return {'reachable_states': len(states), 'compatible_partitions': len(prefixes),
            'partitions_by_environment_count': {str(n): counts[n] for n in sorted(counts)},
            'minimum_environments': minimum, 'minimum_groupings': choices,
            'state_set_sha256': sha(canonical(sorted(states)))}


def build(jar, product):
    source = model(capture(product))
    with tempfile.TemporaryDirectory(prefix='nqc-profile-model-') as temp:
        work = Path(temp)
        copy_release('TLC', jar, work/'tla2tools.jar', JAR_SHA, executable=False)
        (work/'Profiles.tla').write_bytes(source)
        (work/'Profiles.cfg').write_bytes(CONFIG)
        subprocess.run(['/usr/bin/unshare', '--user', '--map-current-user', '--net', '/usr/bin/java',
                        '-XX:ActiveProcessorCount=2', '-Xmx192m', '-cp', 'tla2tools.jar', 'tlc2.TLC',
                        '-workers', '1', '-dump', 'profiles', '-config', 'Profiles.cfg', 'Profiles.tla'],
                       cwd=work, env={'HOME': temp, 'PATH': '/usr/bin:/bin'}, stdin=subprocess.DEVNULL,
                       capture_output=True, check=True, timeout=60)
        states = parse_states(read_artifact(work, 'profiles.dump'))
    return {**assess(states, product), 'release': '1.7.4', 'jar_sha256': JAR_SHA, 'model_sha256': sha(source),
            'config_sha256': sha(CONFIG), 'manifest_sha256': {
                p: product['input_sha256'][INPUTS[p + '/requirements.txt']] for p in PROFILES}}
