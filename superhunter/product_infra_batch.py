"""Cross-check the declared x86-64 ABI of NQC's dedicated compute worker.

Uses the upstream projects as reference data. No tracing sensors are installed
and this review does not apply a filter or attest the host.
"""
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import re

from .owned_compute_guard import PROFILE, rules
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_sources import git
from .repository_boundary import git_object
from .safe_io import canonical, read_artifact, strict_json

STRACE = 'strace/strace'
TRACEE = 'aquasecurity/tracee'
TETRAGON = 'cilium/tetragon'
GADGET = 'inspektor-gadget/inspektor-gadget'

# Paths are resolved from Git trees. A receipt covers only the files consumed.
SOURCES = {
    STRACE: ('050-strace', 'ec439c5485b234228c1d07a9daf111dafadde75c',
             ('src/linux/x86_64/syscallent.h',)),
    TRACEE: ('087-tracee', '2f9dc40c20b17c2ba27f6d92b25e62790bd48a62',
             ('pkg/events/core.go', 'pkg/events/core_amd64.go')),
    TETRAGON: ('088-tetragon', '951e79711c673ac932528b535471f895cd8b0094',
               ('pkg/syscallinfo/syscalls.json',)),
    GADGET: ('090-inspektor-gadget', '24db8bae213b56a0f8f9ed915e607cc8aed1dc31',
             ('pkg/utils/syscalls/syscalls_amd64.go',)),
}

# Semantics of the named comparisons in OWNED_RESTRICTED_REVIEW.md. Unlike the
# executable guard these constraints do not identify arguments by integer slot.
EXPECTED = {
    'close': [[('fd', 4, n, 0)] for n in (0, 1, 2)],
    'fstat': [[('fd', 4, n, 0)] for n in (0, 1, 2)],
    'read': [[('fd', 4, 0, 0)]],
    'write': [[('fd', 4, n, 0)] for n in (1, 2)],
    'mmap': [[('prot', 7, 4, 0), ('flags', 7, 32, 32), ('fd', 7, 4294967295, 4294967295)]],
    'mprotect': [[('prot', 7, 4, 0)]],
    'mremap': [[('flags', 4, n, 0)] for n in (0, 1)],
    'prctl': [[('option', 4, n, 0)] for n in (21, 39)],
}


def capture(source_root, repo):
    directory, revision, paths = SOURCES[repo]
    root = source_root / directory
    entries = git(root, 'ls-tree', '-z', revision, '--', *paths).decode().split('\0')
    result, evidence = {}, {}
    for record in filter(None, entries):
        attrs, name = record.split('\t')
        mode, kind, oid = attrs.split()
        if (mode, kind) != ('100644', 'blob') or name not in paths:
            raise EvidenceError('unexpected infrastructure source entry')
        raw = read_artifact(source_root, directory + '/' + name)
        if git_object('blob', raw) != oid:
            raise EvidenceError('infrastructure source bytes differ from pinned Git tree')
        result[name] = raw.decode('utf-8')
        evidence[name] = {'git_blob': oid, 'sha256': sha(raw)}
    if set(result) != set(paths):
        raise EvidenceError('missing infrastructure source in pinned Git tree')
    return result, {'revision': revision, 'files': evidence}


def _tracee(events, ids, wanted):
    numbers = dict(re.findall(r'^\s*(\w+)\s+ID\s*=\s*(\d+)\s*$', ids, re.M))
    result = {}
    for match in re.finditer(r'^\t(\w+): \{\n(.*?)^\t\},$', events, re.M | re.S):
        symbol, spec = match.groups()
        found = re.search(r'\bname:\s*"(\w+)"', spec)
        if not found or found[1] not in wanted:
            continue
        name = found[1]
        fields = re.findall(r'ArgMeta: trace\.ArgMeta\{Type: "[^"]+", Name: "(\w+)"', spec)
        if (name in result or symbol not in numbers or not re.search(r'\bsyscall:\s*true,', spec)
                or not fields or fields[-1] != 'returnValue'):
            raise EvidenceError('ambiguous Tracee syscall event definition')
        result[name] = {'number': int(numbers[symbol]), 'arguments': fields[:-1]}
    return result


def _tables(source_root, names):
    data, provenance = {}, {}
    for repo in SOURCES:
        files, provenance[repo] = capture(source_root, repo)
        data[repo] = [files[name] for name in SOURCES[repo][2]]
    tracer = {name: {'number': int(nr), 'arity': int(arity)}
              for nr, arity, name in re.findall(
                  r'^\[\s*(\d+)\]\s*=\s*\{\s*(\d+),[^\n]*?"(\w+)"', data[STRACE][0], re.M)
              if name in names}
    tracee = _tracee(*data[TRACEE], names)
    declarations = strict_json(data[TETRAGON][0])
    # The Tetragon data omits certain argument-less syscalls. Limit its
    # participation to the eight calls whose arguments the NQC policy tests.
    signatures = {name: [f['Name'] for f in declarations[name]] for name in EXPECTED}
    table = data[GADGET][0]
    forward = {name: int(nr) for name, nr in re.findall(r'^\s*"(\w+)":\s*(\d+),', table, re.M)}
    reverse = {int(nr): name for nr, name in re.findall(r'^\s*(\d+):\s*"(\w+)",', table, re.M)}
    if set(tracer) != names or set(tracee) != names:
        raise EvidenceError('missing NQC syscall from a trace source')
    return tracer, tracee, signatures, forward, reverse, provenance


def verify(policy, tracer, tracee, signatures, forward, reverse):
    names = {line['syscall'] for line in policy}
    if len({tracer[name]['number'] for name in names}) != len(names):
        raise EvidenceError('duplicate ABI number')
    observed = defaultdict(list)
    for name in sorted(names):
        nr = tracer[name]['number']
        if nr != tracee[name]['number'] or forward.get(name) != nr or reverse.get(nr) != name:
            raise EvidenceError('x86-64 syscall identity mismatch')
        if tracer[name]['arity'] != len(tracee[name]['arguments']):
            raise EvidenceError('syscall argument count mismatch')
    for line in policy:
        name = line['syscall']
        comparisons = []
        for index, op, arg, arg2 in line['comparisons']:
            if not 0 <= index < tracer[name]['arity'] or index >= len(signatures.get(name, [])):
                raise EvidenceError('argument slot outside the declared ABI')
            field = tracee[name]['arguments'][index]
            if field != signatures[name][index]:
                raise EvidenceError('syscall comparison field differs across sources')
            comparisons.append((field, op, arg, arg2))
        if comparisons or name in EXPECTED:
            observed[name].append(comparisons)
    if {k: sorted(v) for k, v in observed.items()} != {k: sorted(v) for k, v in EXPECTED.items()}:
        raise EvidenceError('computed argument restrictions differ from declared intent')


def review(source_root: Path) -> dict:
    policy = rules()
    names = {line['syscall'] for line in policy}
    tracer, tracee, signatures, forward, reverse, receipts = _tables(source_root, names)
    verify(policy, tracer, tracee, signatures, forward, reverse)

    # Force two different contradictions independently of any altered checkout.
    controls = {}
    wrong_field = deepcopy(policy)
    next(rule for rule in wrong_field if rule['syscall'] == 'write')['comparisons'][0][0] = 2
    bad_reverse = {**reverse, forward['read']: 'write'}
    for label, inputs, expected in (
        ('wrong_comparison_argument', (wrong_field, reverse), 'computed argument restrictions differ from declared intent'),
        ('swapped_decoder_name', (policy, bad_reverse), 'x86-64 syscall identity mismatch'),
    ):
        try:
            verify(inputs[0], tracer, tracee, signatures, forward, inputs[1])
        except EvidenceError as exc:
            if str(exc) != expected:
                raise
            controls[label] = expected
        else:
            raise EvidenceError('infrastructure negative control passed unexpectedly')

    nums = {n: forward[n] for n in sorted(names)}
    slots = {n: sorted({c[0] for row in policy if row['syscall'] == n for c in row['comparisons']})
             for n in signatures}
    results = {
        STRACE: ('decode_syscall_numbers_and_arities', tracer),
        TRACEE: ('map_allowed_syscall_event_fields', tracee),
        TETRAGON: ('resolve_named_guard_arguments',
                   {n: {str(i): signatures[n][i] for i in slots[n]} for n in slots}),
        GADGET: ('verify_bidirectional_amd64_names', {'numbers': nums, 'decoded': [reverse[n] for n in sorted(nums.values())]}),
    }
    source_sha = sha(read_artifact(ROOT, 'superhunter/owned_compute_guard.py'))
    for repo, (operation, result) in results.items():
        receipts[repo].update({'role': 'reference', 'operation': operation, 'result': result,
                               'profile': PROFILE, 'guard_source_sha256': source_sha,
                               'policy_sha256': sha(canonical(policy)), 'rule_count': len(policy),
                               'distinct_syscalls': len(names), 'checked_comparisons': sum(len(row['comparisons']) for row in policy),
                               'negative_controls': controls})
    return receipts
