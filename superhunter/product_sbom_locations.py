"""Locate package and dependency references in the original bytes of verified CycloneDX documents."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
from xml.etree import ElementTree

from .product_reasoning import EvidenceError, python_name
from .product_review import copy_release, sha
from .safe_io import read_artifact, strict_json

VERSION = '0.27.2'
BINARY_SHA = 'a658dfc7704d6595a3d2f50eba2590f5919ecd54beedf978ba9888ec914fec1f'
GRAMMAR_COMMIT = 'ee35a6ebefcef0c5c416c0d1ccec7370cfca5a24'
GRAMMAR = {'parser.c': 'e8e1ff5df0d73e3b82574129724e68ef4fa0faf1b8c43dd3f5c1a84839f830ab',
           'tree_sitter/parser.h': 'a1f6ef161fbaf48a0e10fca90ef5290a062462b307b3898aa562993853b9f80a'}
ISOLATE = ['/usr/bin/unshare', '--user', '--map-current-user', '--net']


def string_locations(raw, xml, name):
    """Cross-check the native tree in document order against the standard JSON decoder."""
    value = strict_json(raw)
    try:
        tree = ElementTree.fromstring(xml)
    except ElementTree.ParseError as error:
        raise EvidenceError('invalid Tree-sitter XML') from error
    if (tree.tag != 'sources' or len(tree) != 1 or tree[0].tag != 'source' or tree[0].get('name') != name
            or len(tree[0]) != 1 or tree[0][0].tag != 'document' or len(tree[0][0]) != 1):
        raise EvidenceError('unexpected Tree-sitter document')
    line_starts = [0, *(i + 1 for i, b in enumerate(raw) if b == 10)]
    locations = {}

    def offset(node, prefix):
        row = int(node.attrib[prefix + 'row'])
        col = int(node.attrib[prefix + 'col'])
        if not 0 <= row < len(line_starts) or col < 0:
            raise EvidenceError('invalid Tree-sitter row or byte column')
        end = line_starts[row + 1] - 1 if row + 1 < len(line_starts) else len(raw)
        pos = line_starts[row] + col
        if pos > end:
            raise EvidenceError('Tree-sitter column exceeds source line')
        return pos

    def visit(node, observed, path, bounds):
        start, end = offset(node, 's'), offset(node, 'e')
        if not bounds[0] <= start < end <= bounds[1]:
            raise EvidenceError('Tree-sitter range outside parent or out of order')
        cursor = start
        if type(observed) is dict:
            if node.tag != 'object' or len(node) != len(observed):
                raise EvidenceError('Tree-sitter object differs from JSON')
            for pair, (key, child) in zip(node, observed.items()):
                if (pair.tag != 'pair' or len(pair) != 2 or pair[0].get('field') != 'key'
                        or pair[1].get('field') != 'value'):
                    raise EvidenceError('Tree-sitter object member differs')
                lo, hi = offset(pair, 's'), offset(pair, 'e')
                if not cursor <= lo < hi <= end:
                    raise EvidenceError('Tree-sitter member out of order')
                key_end = visit(pair[0], key, None, (lo, hi))
                cursor = visit(pair[1], child, (*path, key), (key_end, hi))
        elif type(observed) is list:
            if node.tag != 'array' or len(node) != len(observed):
                raise EvidenceError('Tree-sitter array differs from JSON')
            for i, (item, child) in enumerate(zip(node, observed)):
                cursor = visit(item, child, (*path, i), (cursor, end))
        else:
            tag = {str: 'string', int: 'number', float: 'number', bool: 'true' if observed else 'false',
                   type(None): 'null'}[type(observed)]
            if node.tag != tag or json.loads(raw[start:end]) != observed:
                raise EvidenceError('Tree-sitter token disagrees with original bytes')
            if tag == 'string' and path is not None:
                locations[path] = (start, end)
        return end

    visit(tree[0][0][0], value, (), (0, len(raw)))
    return value, locations


def document_locations(name, raw, xml):
    document, slots = string_locations(raw, xml, name)
    digest = sha(raw)

    def location(path):
        start, end = slots[path]
        return {'file': name, 'sha256': digest, 'pointer': '/' + '/'.join(map(str, path)),
                'start_byte': start, 'end_byte': end}

    components = [(('metadata', 'component'), document['metadata']['component'])]
    components += [(('components', i), c) for i, c in enumerate(document['components'])]
    refs = {c['bom-ref']: c for _, c in components}
    if len(refs) != len(components):
        raise EvidenceError('duplicate component reference')
    records = {}
    for path, c in components:
        key = python_name(c['name'])
        records.setdefault(key, []).append({**location((*path, 'purl')), 'kind': 'component', 'purl': c['purl']})
    edges = 0
    for i, dep in enumerate(document['dependencies']):
        source = refs[dep['ref']]
        for j, target in enumerate(dep['dependsOn']):
            target = refs[target]
            edge = {**location(('dependencies', i, 'dependsOn', j)), 'kind': 'dependency',
                    'from': source['purl'], 'to': target['purl']}
            for key in {python_name(source['name']), python_name(target['name'])}:
                records[key].append(edge)
            edges += 1
    return {'sha256': digest, 'component_locations': len(components), 'dependency_locations': edges}, records


def build(binary, grammar, docs):
    evidence = {'version': VERSION, 'binary_sha256': BINARY_SHA, 'json_grammar_commit': GRAMMAR_COMMIT,
                'documents': {}}
    packages = {}
    with tempfile.TemporaryDirectory(prefix='nqc-sbom-locations-') as temp:
        work = Path(temp)
        copy_release('Tree-sitter', binary, work/'tree-sitter', BINARY_SHA)
        (work/'tree_sitter').mkdir()
        for name, expected in GRAMMAR.items():
            raw = read_artifact(grammar, name)
            if sha(raw) != expected:
                raise EvidenceError('Tree-sitter JSON grammar digest mismatch')
            (work/name).write_bytes(raw)
        env = {'HOME': temp, 'TMPDIR': temp, 'PATH': '/usr/bin:/bin'}
        subprocess.run([*ISOLATE, '/usr/bin/cc', '-std=c11', '-O2', '-shared', '-fPIC', '-I.', 'parser.c',
                        '-o', 'json.so'], cwd=work, env=env, capture_output=True, check=True, timeout=30)
        for name, raw in sorted(docs.items()):
            (work/name).write_bytes(raw)
            with (work/'tree.xml').open('wb') as output:
                subprocess.run([*ISOLATE, './tree-sitter', 'parse', '--lib-path', str(work/'json.so'),
                                '--lang-name', 'json', '--xml', name], cwd=work, env=env,
                               stdout=output, stderr=subprocess.PIPE, check=True, timeout=30)
            summary, records = document_locations(name, raw, read_artifact(work, 'tree.xml'))
            evidence['documents'][name] = summary
            for key, rows in records.items():
                packages.setdefault(key, []).extend(rows)
    return evidence, packages
