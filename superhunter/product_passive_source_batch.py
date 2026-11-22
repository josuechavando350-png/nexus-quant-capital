"""Reconcile checksum-control diagnostics, SARIF locations and evidence-sampling coverage."""
import ast
from collections import Counter
from fractions import Fraction
import hashlib
from math import comb, isclose
from pathlib import Path
import re

from .product_review import CATALOG, CATALOG_SHA, ROOT, sha
from .product_sources import git
from .safe_io import canonical, read_artifact, strict_json

DIRECTORY = 'superhunter/product_supply/passive-source-excerpts'
ORIGINS_SHA = '57df165578dad6ed725f1c18c5f91da496b51f38d407f41356ffe11cc1c78ff5'
SOURCE = 'superhunter/product_review.py'


def checked_origins():
    raw = read_artifact(ROOT, DIRECTORY + '/origins.json')
    if sha(raw) != ORIGINS_SHA:
        raise ValueError('changed source-excerpt origins')
    rows = strict_json(raw)['sources']
    for row in rows:
        notice = f"{DIRECTORY}/LICENSE-{row['id']:03}.txt"
        if (sha(read_artifact(ROOT, row['local'])) != row['sha256']
                or sha(read_artifact(ROOT, notice)) != row['license_sha256']):
            raise ValueError('changed source excerpt or notice')
    return rows


def compare_originals(upstream):
    """Authenticate source ranges against the complete pinned objects, without executing them."""
    rows = checked_origins()
    for row in rows:
        name = row['repository'].split('/')[1].lower()
        repo = upstream / f"{row['id']:03}-{name}"
        rev = row['revision']
        if git(repo, 'rev-parse', rev + '^{tree}').decode().strip() != row['tree']:
            raise ValueError('wrong source revision or tree')
        for path, oid in ((row['path'], row['blob']), (row['license_path'], row['license_blob'])):
            if git(repo, 'rev-parse', rev + ':' + path).decode().strip() != oid:
                raise ValueError('original path is not the recorded blob')
        lines = git(repo, 'cat-file', 'blob', row['blob']).splitlines(keepends=True)
        selected = b'\n\n'.join(b''.join(lines[first-1:last]) for first, last in row['spans'])
        if selected != read_artifact(ROOT, row['local'])[row['prefix_bytes']:]:
            raise ValueError('excerpt differs from committed upstream lines')
        if sha(git(repo, 'cat-file', 'blob', row['license_blob'])) != row['license_sha256']:
            raise ValueError('original license differs')
    return [r['repository'] for r in rows]


def severity_map(raw):
    """Interpret only Dalfox's pinned Rust match table as a reporting convention."""
    rules = {}
    for line in raw.decode('ascii').splitlines():
        if '=>' not in line:
            continue
        match = re.fullmatch(r'\s*((?:"[a-z]+"(?:\s*\|\s*)?)+|_) => "(error|warning|note)",', line)
        if not match:
            raise ValueError('unrecognised severity convention')
        keys = ['_'] if match[1] == '_' else re.findall(r'"([a-z]+)"', match[1])
        if rules.keys() & set(keys) or len(keys) != len(set(keys)):
            raise ValueError('duplicate severity convention')
        rules.update(dict.fromkeys(keys, match[2]))
    if set(rules) != {'critical', 'high', 'medium', 'low', 'info', '_'}:
        raise ValueError('incomplete severity convention')
    return rules


def digest_source(raw):
    """Read the constructor used in NQC's single-return sha function, without importing it."""
    function, = [n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name == 'sha']
    stmt, = function.body
    if not isinstance(stmt, ast.Return):
        raise ValueError('unrecognised checksum implementation')
    match = re.fullmatch(r'hashlib\.(sha256|sha1|md5)\(raw\)\.hexdigest\(\)', ast.unparse(stmt.value))
    if not match:
        raise ValueError('unrecognised checksum expression')
    line = stmt.lineno
    return match[1], line, raw.splitlines()[line-1].decode().strip()


def bound_locations(candidates, sources):
    from .passive_strix_locations import _build_physical_locations
    normalized, invalid = _build_physical_locations(candidates)
    accepted = []
    unbound = 0
    for location in normalized:
        physical = location['physicalLocation']
        uri = physical['artifactLocation']['uri']
        region = physical['region']
        lines = sources.get(uri, b'').splitlines()
        start = region['startLine']
        if (start > len(lines) or region.get('endLine', start) != start
                or region.get('snippet', {}).get('text') != lines[start-1].decode().strip()):
            unbound += 1
            continue
        accepted.append({'uri': uri, 'line': start, 'snippet': region['snippet']['text']})
    return accepted, invalid, unbound


def sampled_rejection(total, rejected):
    from .passive_garak_sampling import hit_at_k
    if total < 1 or not 0 <= rejected <= total:
        raise ValueError('invalid number of evidence records')
    records = []
    for k in sorted({1, min(total, 2), total}):
        independent = 1 - Fraction(comb(total-rejected, k), comb(total, k))
        estimate = hit_at_k(total, rejected, k)
        if not isclose(estimate, float(independent), rel_tol=1e-13, abs_tol=1e-13):
            raise ValueError('sampling estimate differs from exact subset count')
        records.append({'k': k, 'numerator': independent.numerator, 'denominator': independent.denominator})
    return records


def review(source_root: Path):
    # These selections and licenses ship with NQC. No original scanner or target is needed.
    origins = checked_origins()
    data = read_artifact(ROOT, CATALOG)
    source = read_artifact(ROOT, SOURCE)
    original, line, original_snippet = digest_source(source)
    if original != 'sha256' or sha(data) != CATALOG_SHA:
        raise ValueError('owned checksum baseline differs')
    table = severity_map(read_artifact(ROOT, origins[1]['local']))
    standards = {'md5': 'high', 'sha1': 'medium'}
    baseline_count = source.count(original_snippet.encode())
    if baseline_count != 1:
        raise ValueError('ambiguous checksum source')
    sources = {SOURCE: source}
    probes = []
    outcomes = []
    for algorithm in (original, *standards):
        snippet = original_snippet.replace('sha256', algorithm)
        candidate = source.replace(original_snippet.encode(), snippet.encode())
        observed, position, witness = digest_source(candidate)
        if observed != algorithm or line != position or witness != snippet:
            raise ValueError('source variant changed outside its checksum call')
        actual = hashlib.new(observed, data).hexdigest()
        matches = actual == CATALOG_SHA
        if matches != (algorithm == original) or hashlib.new(observed, data + b'\n').hexdigest() == CATALOG_SHA:
            raise ValueError('digest and content controls disagree')
        row = {'algorithm': algorithm, 'digest': actual, 'matches_catalog': matches,
               'altered_input_matches_catalog': False, 'source_sha256': sha(candidate)}
        if not matches:
            uri = 'controls/' + algorithm + '/product_review.py'
            sources[uri] = candidate
            row.update(level=table[standards[algorithm]], uri=uri)
            probes.append({'file': uri, 'start_line': line, 'end_line': line, 'snippet': witness})
        outcomes.append(row)
    if [r.get('level') for r in outcomes] != [None, 'error', 'warning']:
        raise ValueError('SARIF levels disagree with the independent control oracle')

    base = probes[0]
    bad_paths = ('/tmp/outside.py', '../outside.py', 'https://invalid.example/file', 'C:\\private\\file')
    path_controls = [dict(base, file=path) for path in bad_paths]
    binding_controls = [dict(base, start_line=line+2000), dict(base, snippet='different source'),
                        dict(base, file='controls/missing.py')]
    candidates = probes + path_controls + [dict(base, start_line=0)] + binding_controls
    accepted, invalid, unbound = bound_locations(candidates, sources)
    expected = [{'uri': p['file'], 'line': line, 'snippet': p['snippet']} for p in probes]
    if accepted != expected or (invalid, unbound) != (5, 3):
        raise ValueError('location consumer accepted an unbound result or lost valid evidence')

    distributions = sampled_rejection(len(candidates), invalid+unbound)
    report = {'catalog_sha256': sha(data), 'location': {'path': SOURCE, 'line': line},
              'checksums': outcomes, 'accepted_locations': accepted,
              'rejected_by_formatter': invalid, 'rejected_by_source_binding': unbound}
    evidence = {'usestrix/strix': {'operation': 'Normalize physical SARIF locations, then bind the emitted lines to the measured source variants.',
                                  'output': {'locations': accepted, 'rejected_by_formatter': invalid, 'rejected_by_consumer': unbound}},
                'hahwul/dalfox': {'operation': 'Use the report formatter severity convention to encode independently witnessed checksum discrepancies.',
                                  'output': {'outcomes': outcomes, 'levels': dict(Counter(r['level'] for r in outcomes if 'level' in r))}},
                'NVIDIA/garak': {'operation': 'Measure the probability of sampling a rejected evidence record without replacement and compare with exact subset counts.',
                                 'output': {'total': len(candidates), 'rejected': invalid+unbound, 'sample': distributions}}}
    for origin in origins:
        name = origin['repository']
        evidence[name].update(revision=origin['revision'], source_blob=origin['blob'],
                              excerpt_sha256=origin['sha256'], input_sha256=sha(data),
                              role='reference' if origin['id'] == 10 else 'execution',
                              combined_report_sha256=sha(canonical(report)))
    return evidence
