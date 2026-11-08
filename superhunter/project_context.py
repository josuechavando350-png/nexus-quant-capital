"""One authoritative 27-item plan, with a checked compatibility projection.

This contains no discovery engine. It prevents documentation/report consumers
from silently assigning different completion states to the same requirement.
"""
from __future__ import annotations

import ast
from pathlib import Path
from .safe_io import canonical, read_artifact

STATE_MAP = {'IMPLEMENTED_BOUNDED': 'BOUNDED_IMPLEMENTED', 'PARTIAL': 'PARTIAL', 'PENDING': 'PENDING'}


def milestone_projection(plan: dict) -> dict:
    """Derive the legacy B01..B27 view without dropping partial evidence."""
    if type(plan) is not dict or type(plan.get('schema_version')) is not int or plan['schema_version'] != 1:
        raise ValueError('invalid authoritative context schema')
    items = plan.get('items')
    if type(items) is not list or len(items) != 27:
        raise ValueError('27 context requirements required')
    result = []
    groups = [1]*4 + [2]*5 + [3]*6 + [4]*6 + [5]*6
    for number, (item, group) in enumerate(zip(items, groups), 1):
        if type(item) is not dict or set(item) != {'id','group','title','status','scope','components','required_tests'}:
            raise ValueError('context item schema mismatch')
        if type(item['id']) is not int or item['id'] != number or type(item['group']) is not int or item['group'] != group:
            raise ValueError('context identity or order changed')
        if type(item['status']) is not str or item['status'] not in STATE_MAP:
            raise ValueError('invalid context state')
        if any(type(item[k]) is not str or not item[k].strip() for k in ('title','scope')):
            raise ValueError('context text missing')
        for field in ('components','required_tests'):
            refs = item[field]
            if type(refs) is not list or any(type(r) is not str or not r for r in refs) or len(set(refs)) != len(refs):
                raise ValueError('context evidence references invalid')
            if bool(refs) != (item['status'] != 'PENDING'):
                raise ValueError('implemented or partial context requires evidence')
        result.append({'id': f'B{number:02d}', 'group': group, 'title': item['title'],
                       'status': STATE_MAP[item['status']], 'boundary': item['scope'],
                       'tests': list(item['required_tests'])})
    return {'schema_version': 1, 'items': result}


def verify_projection(plan: dict, projection: dict) -> None:
    """Canonical equality distinguishes booleans, numbers and added claims."""
    if type(projection) is not dict or canonical(projection) != canonical(milestone_projection(plan)):
        raise ValueError('checklists disagree with canonical integration; regenerate compatibility projection from authoritative plan')


def test_inventory(root: Path) -> list[str]:
    """Read static unittest identities from the current, own-package sources.

    Unsupported dynamic/top-level test generators are not silently accepted.
    This does not import test modules or execute test bodies.
    """
    names = []
    for path in sorted((root/'tests').glob('test*.py')):
        tree = ast.parse(read_artifact(root, 'tests/'+path.name), filename=path.name)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == 'load_tests':
                raise ValueError('dynamic unittest inventory needs explicit review')
            if not isinstance(node, ast.ClassDef):
                continue
            methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith('test')]
            if not methods:
                continue
            if len(node.bases) != 1 or ast.unparse(node.bases[0]) != 'unittest.TestCase':
                raise ValueError('unsupported inherited unittest inventory')
            names.extend(path.stem+'.'+node.name+'.'+method.name for method in methods)
    if not names or len(names) != len(set(names)):
        raise ValueError('empty or duplicate static unittest inventory')
    return sorted(names)
