"""Read-only import inventory of this Python package; no target execution.

This is a syntactic, file-layout model, not a call graph, a vulnerability scan,
SlithIR, or proof of runtime reachability. Dynamic loading and unresolved imports
are retained as uncertainty. The declared QA dependency graph is kept distinct.
"""
from __future__ import annotations

import ast
import argparse
from collections import deque
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
MAX_FILES = 256
MAX_TOTAL_BYTES = 8_000_000
MAX_NODES_PER_FILE = 100_000
PACKAGE = 'superhunter'
FIXED = {'inventory.json', 'graph.json', 'REPORT.md'}
PHASES = ('MODULE', 'CONDITIONAL', 'DEFERRED')


def need(value: bool, code: str) -> None:
    if not value:
        raise ValueError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def path_module(path: str, package: str) -> str:
    need(type(path) is str and bool(path) and '\\' not in path and ':' not in path,
         'INVALID_SOURCE_PATH')
    p = PurePosixPath(path)
    need(not p.is_absolute() and all(x not in ('', '.', '..') for x in path.split('/'))
         and p.suffix == '.py', 'INVALID_SOURCE_PATH')
    parts = list(p.with_suffix('').parts)
    need(all(re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', x) for x in parts), 'INVALID_MODULE_NAME')
    if parts[-1] == '__init__':
        parts.pop()
    return '.'.join([package, *parts])


def capture(root: Path = ROOT) -> dict[str, bytes]:
    """Only runtime .py sources: exclude tests and caches, reject symlinks."""
    need(not root.is_symlink(), 'SYMLINK_ROOT')
    sources: dict[str, bytes] = {}
    total = 0
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            need(not (Path(base)/name).is_symlink(), 'SYMLINK_SOURCE_DIRECTORY')
        dirs[:] = sorted(d for d in dirs if d not in ('tests', '__pycache__', '.git'))
        for name in sorted(files):
            if not name.endswith('.py'):
                continue
            relative = (Path(base)/name).relative_to(root).as_posix()
            raw = read_artifact(root, relative)
            total += len(raw)
            need(len(sources) < MAX_FILES and total <= MAX_TOTAL_BYTES, 'SOURCE_INVENTORY_LIMIT')
            sources[relative] = raw
    need(bool(sources), 'EMPTY_SOURCE_INVENTORY')
    return dict(sorted(sources.items()))


def parse_sources(sources: dict[str, bytes], package: str) -> tuple[dict, dict]:
    need(type(package) is str and re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', package) is not None,
         'INVALID_PACKAGE_NAME')
    need(type(sources) is dict and 0 < len(sources) <= MAX_FILES, 'SOURCE_INVENTORY_LIMIT')
    need(all(type(v) is bytes and len(v) <= 2_000_000 for v in sources.values()), 'SOURCE_SIZE_LIMIT')
    need(sum(map(len, sources.values())) <= MAX_TOTAL_BYTES, 'SOURCE_SIZE_LIMIT')
    trees, modules = {}, {}
    for path in sorted(sources):
        name = path_module(path, package)
        need(name not in modules, 'AMBIGUOUS_MODULE_LAYOUT')
        try:
            tree = ast.parse(sources[path], filename=path)
        except (SyntaxError, UnicodeError, ValueError) as exc:
            raise ValueError('SOURCE_PARSE_FAILED') from exc
        need(sum(1 for _ in ast.walk(tree)) <= MAX_NODES_PER_FILE, 'AST_NODE_LIMIT')
        trees[path], modules[name] = tree, path
    return trees, modules


def declared_registry(tree: ast.Module | None) -> dict:
    """Read a literal COMPONENTS assignment, without importing quality.py."""
    if tree is None:
        return {}
    assignments = [n.value for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'COMPONENTS' for t in n.targets)]
    need(len(assignments) == 1, 'COMPONENT_REGISTRY_NOT_LITERAL')
    try:
        value = ast.literal_eval(assignments[0])
    except (TypeError, ValueError, SyntaxError) as exc:
        raise ValueError('COMPONENT_REGISTRY_NOT_LITERAL') from exc
    need(type(value) is dict and 0 < len(value) <= MAX_FILES, 'COMPONENT_REGISTRY_INVALID')
    for key, item in value.items():
        need(type(key) is str and type(item) is dict and set(item) == {'files', 'tests', 'depends'},
             'COMPONENT_REGISTRY_INVALID')
        for field in ('files', 'tests', 'depends'):
            need(type(item[field]) is list and all(type(s) is str for s in item[field]),
                 'COMPONENT_REGISTRY_INVALID')
        need(all(d in value for d in item['depends']), 'UNKNOWN_DECLARED_COMPONENT')
    return value


class Imports(ast.NodeVisitor):
    """Lexical import sites; guards aren't evaluated and bindings aren't executed."""
    def __init__(self, module: str, path: str, known: dict[str, str], package: str):
        self.module, self.path, self.known, self.package = module, path, known, package
        self.parent = module if path.endswith('__init__.py') else module.rpartition('.')[0]
        self.depth, self.guards = 0, 0
        self.edges: list[dict] = []
        self.external: list[dict] = []
        self.unresolved: list[dict] = []
        self.dynamic: list[dict] = []
        self.namespaces = {'.'.join(k.split('.')[:n]) for k in known for n in range(1, len(k.split('.')))}

    def site(self, node: ast.AST) -> dict:
        return {'source': self.module, 'file': self.path, 'line': node.lineno,
                'column_byte': node.col_offset,
                'phase': 'DEFERRED' if self.depth else 'CONDITIONAL' if self.guards else 'MODULE'}

    def emit(self, name: str, node: ast.AST, kind: str, *, member: str | None = None) -> None:
        site = {**self.site(node), 'target': name, 'kind': kind}
        if member is not None:
            site['member'] = member
        if name == '__future__':
            return
        if name == self.package or name.startswith(self.package + '.'):
            if name in self.known:
                self.edges.append({**site, 'target_file': self.known[name]})
            elif name in self.namespaces:
                self.unresolved.append({**site, 'reason': 'NAMESPACE_WITHOUT_SOURCE_BODY'})
            else:
                self.unresolved.append({**site, 'reason': 'MODULE_NOT_IN_SNAPSHOT'})
        else:
            # Classification is intentionally not guessed from the host environment.
            self.external.append(site)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.emit(alias.name, node, 'import')

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level:
            parts = self.parent.split('.')
            if node.level > len(parts):
                self.unresolved.append({**self.site(node), 'reason': 'RELATIVE_IMPORT_ESCAPES_PACKAGE'})
                return
            base = '.'.join(parts[:len(parts)-node.level+1])
            if node.module:
                base += '.' + node.module
        else:
            base = node.module or ''
        # from package import submodule: resolve the captured submodule, when present.
        for alias in node.names:
            child = base + '.' + alias.name
            if child in self.known:
                self.emit(child, node, 'from-submodule')
            else:
                self.emit(base, node, 'from-symbol', member=alias.name)
                if alias.name == '*':
                    self.dynamic.append({**self.site(node), 'reason': 'WILDCARD_EXPORTS_NOT_RESOLVED'})
                elif not node.module and base == self.package:
                    self.unresolved.append({**self.site(node), 'target': child,
                                            'reason': 'FROM_MEMBER_MAY_BE_ATTRIBUTE_OR_MODULE'})

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Defaults/decorators run in the enclosing scope, unlike the function body.
        for value in [*node.decorator_list, *node.args.defaults,
                      *(x for x in node.args.kw_defaults if x is not None)]:
            self.visit(value)
        self.depth += 1
        for child in node.body:
            self.visit(child)
        self.depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for value in [*node.args.defaults, *(x for x in node.args.kw_defaults if x is not None)]:
            self.visit(value)
        self.depth += 1
        self.visit(node.body)
        self.depth -= 1

    def guarded(self, node: ast.AST) -> None:
        self.guards += 1
        self.generic_visit(node)
        self.guards -= 1

    visit_If = guarded
    visit_Try = guarded
    visit_TryStar = guarded
    visit_For = guarded
    visit_AsyncFor = guarded
    visit_While = guarded
    visit_With = guarded
    visit_AsyncWith = guarded
    visit_Match = guarded

    def visit_Call(self, node: ast.Call) -> None:
        name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
        if name in {'exec', 'eval', '__import__', 'import_module', 'load_module', 'exec_module'}:
            self.dynamic.append({**self.site(node), 'reason': 'DYNAMIC_LOADING_OR_EXECUTION_NOT_RESOLVED',
                                 'call_syntax': name})
        self.generic_visit(node)


def reachability(nodes: list[str], edges: list[dict], starts: list[str], *, immediate: bool = False) -> list[str]:
    adjacency = {name: set() for name in nodes}
    for row in edges:
        if not immediate or row['phase'] == 'MODULE':
            adjacency[row['source']].add(row['target'])
    seen = set(starts)
    todo = deque(starts)
    while todo:
        for child in sorted(adjacency[todo.popleft()]):
            if child not in seen:
                seen.add(child); todo.append(child)
    return sorted(seen)


def cycle_groups(nodes: list[str], edges: list[dict], *, immediate: bool) -> list[list[str]]:
    """SCCs via reachability intersections; bounded to the package's <=256 nodes."""
    closure = {n: set(reachability(nodes, edges, [n], immediate=immediate)) for n in nodes}
    seen, groups = set(), []
    self_edges = {e['source'] for e in edges if e['source'] == e['target'] and (not immediate or e['phase'] == 'MODULE')}
    for node in sorted(nodes):
        if node in seen:
            continue
        group = sorted(n for n in nodes if n in closure[node] and node in closure[n])
        seen.update(group)
        if len(group) > 1 or node in self_edges:
            groups.append(group)
    return groups


def analyze(sources: dict[str, bytes], package: str = PACKAGE) -> dict:
    trees, modules = parse_sources(sources, package)
    registry = declared_registry(trees.get('quality.py'))
    owners = {}
    for name, component in registry.items():
        for path in component['files']:
            need(path in sources and path not in owners, 'COMPONENT_SOURCE_OWNERSHIP')
            owners[path] = name
    edges, external, unresolved, dynamic = [], [], [], []
    for module, path in sorted(modules.items()):
        visitor = Imports(module, path, modules, package)
        visitor.visit(trees[path])
        edges += visitor.edges; external += visitor.external
        unresolved += visitor.unresolved; dynamic += visitor.dynamic
    def ordered(rows):
        return sorted({canonical(r): r for r in rows}.values(), key=canonical)
    edges, external, unresolved, dynamic = map(ordered, (edges, external, unresolved, dynamic))
    component_edges = []
    def declared_relation(origin, target):
        if target in registry[origin]['depends']:
            return 'DIRECT'
        seen, todo = set(), [origin]
        while todo:
            current = todo.pop()
            if current in seen:
                continue
            seen.add(current)
            todo.extend(registry[current]['depends'])
        return 'TRANSITIVE' if target in seen else 'ABSENT'
    for edge in edges:
        origin, target = owners.get(edge['file']), owners.get(edge['target_file'])
        if origin and target and origin != target:
            component_edges.append({'source_component': origin, 'target_component': target,
                'file': edge['file'], 'line': edge['line'], 'phase': edge['phase'],
                'declared_direct_dependency': target in registry[origin]['depends'],
                'declared_relation': declared_relation(origin, target)})
    entrypoints = [n for n in (package, package + '.__main__') if n in modules]
    reached = reachability(list(modules), edges, entrypoints)
    component_edges = ordered(component_edges)
    unrepresented = [e for e in component_edges if e['declared_relation'] == 'ABSENT']
    snapshot = {p: sha(raw) for p, raw in sorted(sources.items())}
    return {'schema_version': 1, 'analysis': 'python-import-syntax-v1',
        'status': 'SOURCE_GRAPH_REVIEW_REQUIRED' if unresolved or dynamic or unrepresented else 'SOURCE_GRAPH_INVENTORIED',
        'package': package, 'sources': snapshot, 'source_digest': sha(canonical(snapshot)),
        'modules': [{'module': n, 'file': modules[n], 'component': owners.get(modules[n])} for n in sorted(modules)],
        'import_edges': edges, 'external_imports': external,
        'unresolved_imports': unresolved, 'dynamic_sites': dynamic,
        'component_edges': ordered(component_edges), 'declared_components': registry,
        'entry_modules': entrypoints, 'syntactically_reachable': reached,
        'not_reached_by_static_imports': sorted(set(modules)-set(reached)),
        'module_phase_cycles': cycle_groups(list(modules), edges, immediate=True),
        'all_phase_cycles': cycle_groups(list(modules), edges, immediate=False),
        'module_count': len(modules), 'import_reference_count': len(edges),
        'undeclared_component_edges': len(unrepresented),
        'target_executed': False, 'runtime_reachability_proven': False,
        'vulnerability_confirmed': False, 'all_dependencies_resolved': False,
        'limitations': ['Syntactic imports only; no call/data/permission graph.',
            'Deferred and conditional sites may never execute; guards are not evaluated.',
            'Dynamic import aliases, custom loaders and monkeypatching may be missed.',
            'Implicit parent package initialization edges are not included.',
            'Native vendored paths model file layout, not dynamically assigned module names.',
            'Missing QA dependency declarations are review observations, not security findings.',
            'No installed dependency versions, CVEs, licenses or exploitability are inferred.']}


@lru_cache(maxsize=4)
def _cached_graph_bytes(items: tuple[tuple[str, bytes], ...]) -> bytes:
    # Pure analysis keyed by exact source bytes. Return immutable bytes, not a
    # shared mutable AST/result. Explicit bundle verification bypasses this cache.
    return canonical(analyze(dict(items)))


def current_graph(root: Path = ROOT) -> dict:
    sources = capture(root)
    return strict_json(_cached_graph_bytes(tuple(sources.items())))


def summary(result: dict) -> dict:
    return {k: result[k] for k in ('status', 'source_digest', 'module_count',
        'import_reference_count', 'undeclared_component_edges', 'target_executed',
        'runtime_reachability_proven', 'vulnerability_confirmed')}


def render(result: dict) -> bytes:
    lines = ['# Inventario estático de imports del propio paquete', '',
        f"Estado: {result['status']}", f"Módulos: {result['module_count']}; referencias de import local: {result['import_reference_count']}.",
        f"Imports sin resolver: {len(result['unresolved_imports'])}; sitios dinámicos: {len(result['dynamic_sites'])}.",
        f"Relaciones sin respaldo directo ni transitivo en QA: {result['undeclared_component_edges']}.", '',
        '**No se ejecutó el código analizado. No es SlithIR ni detección de vulnerabilidades.**', '',
        '## Relaciones no directas: cobertura transitiva o ausente', '']
    for edge in result['component_edges']:
        if not edge['declared_direct_dependency']:
            lines.append(f"- {edge['source_component']} → {edge['target_component']} · {edge['file']}:{edge['line']} · {edge['phase']} · {edge['declared_relation']}")
    lines += ['', '## Imports no resueltos', '']
    for row in result['unresolved_imports']:
        lines.append(f"- {row['file']}:{row['line']} · {row['reason']} · {row['phase']}")
    lines += ['', '## Límites', '', *('- '+x for x in result['limitations']), '']
    return ('\n'.join(lines)+'\n').encode()


def create_audit(out: Path, *, root: Path = ROOT) -> dict:
    need(not out.exists() and not out.is_symlink(), 'OUTPUT_EXISTS')
    need(not out.resolve().is_relative_to(root.resolve().parent), 'OUTPUT_INSIDE_CHECKOUT')
    sources = capture(root)
    result = analyze(sources)
    inventory = {'schema_version': 1, 'package': PACKAGE, 'sources': [
        {'path': p, 'sha256': sha(raw), 'artifact': f'source-{i:03d}.py'}
        for i, (p, raw) in enumerate(sources.items())]}
    files = {'inventory.json': canonical(inventory), 'graph.json': canonical(result), 'REPORT.md': render(result)}
    files.update({row['artifact']: sources[row['path']] for row in inventory['sources']})
    need(sources == capture(root), 'SOURCE_CHANGED_DURING_ANALYSIS')
    write_new_bundle(out, files)
    return verify_audit(out)


def verify_audit(root: Path) -> dict:
    marker = strict_json(read_artifact(root, 'COMPLETE.json'))
    need(set(marker) == {'schema_version','sha256'} and type(marker['schema_version']) is int
         and marker['schema_version'] == 1 and type(marker['sha256']) is dict, 'INVALID_MANIFEST')
    inv = strict_json(read_artifact(root, 'inventory.json'))
    need(set(inv) == {'schema_version','package','sources'} and type(inv['schema_version']) is int
         and inv['schema_version'] == 1 and inv['package'] == PACKAGE, 'INVALID_INVENTORY')
    rows = inv['sources']
    need(type(rows) is list and 0 < len(rows) <= MAX_FILES, 'INVALID_INVENTORY')
    sources, expected = {}, set(FIXED)
    for i, row in enumerate(rows):
        need(type(row) is dict and set(row) == {'path','sha256','artifact'} and row['artifact'] == f'source-{i:03d}.py', 'INVALID_SOURCE_ROW')
        path_module(row['path'], PACKAGE)
        need(row['path'] not in sources, 'DUPLICATE_SOURCE')
        raw = read_artifact(root, row['artifact'])
        need(sha(raw) == row['sha256'], 'SOURCE_HASH_MISMATCH')
        sources[row['path']] = raw; expected.add(row['artifact'])
    need(list(sources) == sorted(sources), 'SOURCE_ORDER')
    need(set(marker['sha256']) == expected and {p.name for p in root.iterdir()} == expected | {'COMPLETE.json'}, 'BUNDLE_SET_MISMATCH')
    for name in sorted(expected):
        need(sha(read_artifact(root, name)) == marker['sha256'][name], 'BUNDLE_HASH_MISMATCH')
    result = analyze(sources)
    need(read_artifact(root, 'graph.json') == canonical(result), 'GRAPH_RECOMPUTATION_MISMATCH')
    need(read_artifact(root, 'REPORT.md') == render(result), 'REPORT_RECOMPUTATION_MISMATCH')
    return result


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, 'Invalid arguments; input values are not echoed.\n')


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Read-only import graph of the installed SUPERHUNTER source package')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('audit-source-graph').add_argument('--out', type=Path, required=True)
    sub.add_parser('verify-source-graph').add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = create_audit(args.out) if args.command == 'audit-source-graph' else verify_audit(args.bundle)
        print(json.dumps({k: result[k] for k in ('status','module_count','import_reference_count','source_digest','target_executed','vulnerability_confirmed')}))
        return 0 if result['status'] == 'SOURCE_GRAPH_INVENTORIED' else 1
    except (ValueError, OSError, TypeError, KeyError, RecursionError) as exc:
        print(json.dumps({'status':'SOURCE_GRAPH_ERROR', 'error_type':type(exc).__name__, 'vulnerability_confirmed':False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
