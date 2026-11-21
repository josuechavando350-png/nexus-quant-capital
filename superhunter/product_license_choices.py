"""Derive the inclusion-minimal identifier sets that satisfy observed SPDX AND/OR expressions."""
from __future__ import annotations

import ast
from functools import reduce
from operator import and_, or_

from .product_reasoning import EvidenceError
from .product_review import sha
from .product_spdx_groups import TOKEN
from .safe_io import canonical


def tree(expression, names):
    indexes = {name: f'p{i}' for i, name in enumerate(names)}
    tokens = TOKEN.findall(expression)
    if ''.join(tokens) != ''.join(expression.split()):
        raise EvidenceError('unsupported license expression')
    text = ' '.join(indexes[t] if t in indexes else t.lower() for t in tokens)
    def visit(node):
        if isinstance(node, ast.Name) and node.id in indexes.values():
            return int(node.id[1:])
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            op = 'and' if isinstance(node.op, ast.And) else 'or'
            return reduce(lambda a, b: (op, a, b), map(visit, node.values))
        raise EvidenceError('unsupported license expression node')
    try:
        return visit(ast.parse(text, mode='eval').body)
    except SyntaxError as error:
        raise EvidenceError('invalid license expression') from error


def evaluate(node, mask):
    if isinstance(node, int):
        return bool(mask & (1 << node))
    op, left, right = node
    return (and_ if op == 'and' else or_)(evaluate(left, mask), evaluate(right, mask))


def alternatives(masks, size):
    def combine(op, nodes):
        return reduce(lambda a, b: (op, a, b), nodes)
    return combine('or', [combine('and', [i for i in range(size) if m & (1 << i)]) for m in masks])


def prepare(evidence):
    claims = []
    expected = {s for s in evidence['sources'].values() if s}
    if not expected or expected != set(evidence['expressions']):
        raise EvidenceError('license decisions do not match the observed sources')
    for expr in sorted(expected):
        proof = evidence['expressions'][expr]
        names = proof['identifiers']
        if not 1 <= len(names) <= 12 or names != sorted(set(names)):
            raise EvidenceError('invalid license identifier inventory')
        formula = tree(expr, names)
        limit = 1 << len(names)
        accepted = {m for m in range(limit) if evaluate(formula, m)}
        truth = sum(1 << m for m in accepted)
        if (0 in accepted or not accepted or limit != proof['assignments_checked'] or
                sha(truth.to_bytes((limit + 7) // 8, 'little')) != proof['truth_table_sha256']):
            raise EvidenceError('license choice computation differs from verified SPDX semantics')
        minima = sorted(m for m in accepted if all(m ^ (1 << i) not in accepted for i in range(len(names)) if m & (1 << i)))
        candidate = alternatives(minima, len(names))
        if any((m in accepted) != evaluate(candidate, m) for m in range(limit)):
            raise EvidenceError('incomplete minimal license choices')
        claims.append({'expression': expr, 'names': names, 'original': formula, 'candidate': candidate, 'minima': minima})
    witness = next((c for c in claims if len(c['minima']) > 1), claims[0])
    other = witness['minima'][1:]
    negative = {**witness, 'candidate': alternatives(other, len(witness['names'])) if other else None}
    return claims, negative


def report(evidence, claims, negative):
    sets = {c['expression']: [[n for i, n in enumerate(c['names']) if m & (1 << i)] for m in c['minima']]
            for c in claims}
    return {'choices_by_expression': sets, 'sources': evidence['sources'],
            'sources_sha256': sha(canonical(evidence['sources'])), 'choices_sha256': sha(canonical(sets)),
            'counterexample': {'expression': negative['expression'], 'removed_choice': sets[negative['expression']][0]}}
