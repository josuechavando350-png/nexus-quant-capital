"""Read-only syntactic dependency analysis of this package's actual Python files.

No imports or code bodies from analyzed files are executed. Edges are IMPORT
references, not call paths, feasible attack paths, or proof of runtime coverage.
Dynamic loading and missing links are exposed as uncertainty, never invented.
"""
from __future__ import annotations

import ast
import argparse
from collections import deque
import hashlib
import json
import os
import threading
from pathlib import Path, PurePosixPath
from typing import Any

from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
MAX_FILES = 256
MAX_TOTAL = 8_000_000
MAX_NODES = 200_000
FILES = {'graph.json', 'REVIEW.md'}
# One bounded entry, keyed by captured BYTES and analyzer identity, not mtime.
# The cached JSON is immutable; callers receive a newly parsed object.
_GRAPH_LOCK = threading.RLock()
_GRAPH_CACHE: tuple[dict[str, bytes], object, bytes] | None = None


def _module(path: str, package: str) -> str:
    p = PurePosixPath(path)
    if (type(path) is not str or p.is_absolute() or '\\' in path or ':' in path or
            any(x in ('', '.', '..') for x in path.split('/')) or p.suffix != '.py'):
        raise ValueError('invalid source path')
    parts = list(p.with_suffix('').parts)
    if any(not x.isidentifier() for x in parts):
        raise ValueError('invalid module identifier')
    if parts[-1] == '__init__':
        parts.pop()
    return '.'.join([package] + parts)


def capture(root: Path = ROOT) -> dict[str, bytes]:
    """Capture regular .py files; omit tests/caches; no symlink traversal."""
    if root.is_symlink():
        raise ValueError('source root symlink rejected')
    result, total = {}, 0
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in ('tests', '__pycache__'))
        if any((Path(base)/d).is_symlink() for d in dirs):
            raise ValueError('source directory symlink rejected')
        for name in sorted(names):
            if not name.endswith('.py'):
                continue
            relative = (Path(base)/name).relative_to(root).as_posix()
            raw = read_artifact(root, relative)
            total += len(raw)
            if len(result) >= MAX_FILES or total > MAX_TOTAL:
                raise ValueError('source graph budget exceeded')
            result[relative] = raw
    if not result:
        raise ValueError('no Python source files')
    return dict(sorted(result.items()))


def reachable(edges: list[dict], start: str, modules: set[str]) -> list[str]:
    """Graph closure only: conditional and function-local imports count as edges."""
    adjacency = {name: set() for name in modules}
    for row in edges:
        adjacency[row['from']].add(row['to'])
    seen, queue = {start}, deque([start])
    while queue:
        current = queue.popleft()
        for target in sorted(adjacency[current] - seen):
            seen.add(target)
            queue.append(target)
    return sorted(seen)


def analyze(sources: dict[str, bytes], package: str = 'superhunter') -> dict:
    if type(package) is not str or not package.isidentifier():
        raise ValueError('invalid package identifier')
    if type(sources) is not dict or not 1 <= len(sources) <= MAX_FILES:
        raise ValueError('invalid source inventory')
    if any(type(p) is not str or type(v) is not bytes for p,v in sources.items()):
        raise ValueError('source paths/bytes required')
    if sum(map(len,sources.values())) > MAX_TOTAL or any(len(b)>2_000_000 for b in sources.values()):
        raise ValueError('source graph budget exceeded')
    modules, parsed, inventory = {}, {}, {}
    for path, raw in sorted(sources.items()):
        name = _module(path, package)
        if name in modules:
            raise ValueError('ambiguous module identity')
        modules[name] = path
        inventory[path] = hashlib.sha256(raw).hexdigest()
        try:
            tree = ast.parse(raw, filename=path)
        except (SyntaxError, UnicodeError, ValueError) as exc:
            raise ValueError('source cannot be parsed') from exc
        if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
            raise ValueError('AST budget exceeded')
        parsed[name] = tree
    namespaces = set(modules)
    for name in modules:
        parts = name.split('.')
        namespaces.update('.'.join(parts[:i]) for i in range(1,len(parts)))
    edges, external, unresolved, dynamic = [], [], [], []
    bindings = {}
    # Export-name knowledge prevents mislabeling `from . import CONST` as a module.
    for name, tree in parsed.items():
        symbols = set()
        for node in tree.body:
            if isinstance(node,(ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbols.add(node.name)
            elif isinstance(node,(ast.Assign,ast.AnnAssign)):
                for target in node.targets if isinstance(node,ast.Assign) else [node.target]:
                    symbols.update(n.id for n in ast.walk(target) if isinstance(n,ast.Name))
            elif isinstance(node,(ast.Import,ast.ImportFrom)):
                symbols.update(a.asname or a.name.split('.')[0] for a in node.names if a.name != '*')
        bindings[name] = symbols

    for origin, tree in parsed.items():
        path = modules[origin]
        parent = origin if path.endswith('__init__.py') else origin.rsplit('.',1)[0]
        # ast.walk includes dead branches/function-local imports by design.
        def add(target: str, node: ast.AST, form: str) -> None:
            witness = {'from':origin, 'to':target, 'file':path, 'line':node.lineno,
                       'kind':form, 'execution_proven':False}
            if target == package or target.startswith(package+'.'):
                if target in namespaces:
                    # A namespace has no executable __init__; record only concrete modules.
                    if target in modules:
                        edges.append(witness)
                else:
                    unresolved.append({**witness,'reason':'local_module_missing'})
            else:
                external.append(witness)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    add(alias.name,node,'import')
                    # Python also imports parent packages with executable __init__ files.
                    parts = alias.name.split('.')
                    for index in range(1,len(parts)):
                        p='.'.join(parts[:index])
                        if p in modules:
                            add(p,node,'parent_package')
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    parts = parent.split('.')
                    if node.level > len(parts):
                        unresolved.append({'from':origin,'file':path,'line':node.lineno,
                                           'reason':'relative_import_outside_package'})
                        continue
                    target = '.'.join(parts[:len(parts)-node.level+1])
                    if node.module:
                        target += '.'+node.module
                else:
                    target = node.module or ''
                add(target,node,'from')
                local = target == package or target.startswith(package+'.')
                for alias in node.names:
                    if alias.name == '*':
                        dynamic.append({'module':origin,'file':path,'line':node.lineno,'kind':'wildcard_import'})
                    elif local and target in namespaces:
                        child = target+'.'+alias.name
                        if child in namespaces:
                            add(child,node,'from_submodule')
                        elif alias.name not in bindings.get(target,set()):
                            # Could be a dynamically exported attribute, not necessarily missing code.
                            unresolved.append({'from':origin,'file':path,'line':node.lineno,
                                               'to':child,'reason':'attribute_or_submodule_unresolved'})
            elif isinstance(node, ast.Call):
                func = node.func
                kind = None
                if isinstance(func, ast.Name) and func.id in ('exec','eval','__import__'):
                    kind = func.id
                elif isinstance(func, ast.Attribute) and func.attr in ('import_module','exec_module','load_module','spec_from_file_location'):
                    kind = func.attr
                if kind:
                    dynamic.append({'module':origin,'file':path,'line':node.lineno,'kind':kind})
    # Stable, exact evidence; duplicates on one source line don't inflate counts.
    unique = lambda rows: sorted({canonical(x):x for x in rows}.values(),key=canonical)
    edges, external, unresolved, dynamic = map(unique,(edges,external,unresolved,dynamic))
    entry = package+'.__main__'
    reached = reachable(edges,entry,set(modules)) if entry in modules else []
    result = {
        'schema_version':1,'package':package,'analysis_kind':'syntactic-python-imports',
        'source_sha256':inventory,'source_digest':hashlib.sha256(canonical(inventory)).hexdigest(),
        'modules':[{'module':n,'file':modules[n]} for n in sorted(modules)],
        'local_imports':edges,'external_imports':external,'unresolved':unresolved,'dynamic_loading':dynamic,
        'entrypoint':entry if entry in modules else None,
        'syntactically_reachable':reached,'not_proven_reachable':sorted(set(modules)-set(reached)),
        'status':'SOURCE_GRAPH_REVIEW_REQUIRED' if unresolved or dynamic else 'SOURCE_GRAPH_RESOLVED',
        'all_runtime_links_proven':False,'external_dependencies_verified':False,
        'vulnerability_confirmed':False,
        'limitations':[
            'Imports are syntax, not executed call paths; conditional/dead imports remain visible.',
            'Dynamic loaders, process launches and reflection may create links absent from this graph.',
            'Missing attributes may be computed dynamically; unresolved is not a confirmed defect.',
            'External packages and vulnerable-version reachability are not checked.',
        ]}
    if len(canonical(result)) > 2_000_000:
        raise ValueError('graph output budget exceeded')
    return result


def current_graph() -> dict:
    """Re-use parsing only for identical source bytes; always re-read both sides.

    The single-entry cache does not authenticate a producer or freeze the source
    tree. Its scope is one process. A changed byte, file inventory or analyzer
    invalidates it, and callers cannot mutate the cached serialized result.
    """
    global _GRAPH_CACHE
    with _GRAPH_LOCK:
        before = capture()
        cached = _GRAPH_CACHE
        analyzer = analyze
        if cached is not None and cached[0] == before and cached[1] is analyzer:
            payload = cached[2]
        else:
            payload = canonical(analyzer(before))
        if capture() != before:
            raise ValueError('source changed during graph analysis')
        result = strict_json(payload)
        _GRAPH_CACHE = (dict(before), analyzer, payload)
        return result


def render(result: dict) -> str:
    return ('# SUPERHUNTER — enlaces leídos del código Python\n\n'
            f"Estado: {result['status']}. Fuentes: `{result['source_digest']}`.\n\n"
            f"Módulos: {len(result['modules'])}; referencias locales: {len(result['local_imports'])}; "
            f"referencias externas: {len(result['external_imports'])}.\n"
            f"Enlaces sin resolver: {len(result['unresolved'])}; llamadas de carga dinámica: {len(result['dynamic_loading'])}.\n"
            f"Módulos alcanzables sintácticamente desde __main__: {len(result['syntactically_reachable'])}.\n\n"
            '**No demuestra que todo se ejecute conectado ni que el programa sea seguro.**\n'
            'El JSON conserva ubicaciones y hashes. Las referencias sin resolver requieren revisión.\n'
            'No se importó ni ejecutó el código analizado; no es SlithIR, taint ni análisis EVM.\n')


def create(out: Path) -> dict:
    if out.exists() or out.is_symlink() or out.resolve().is_relative_to(ROOT.parent):
        raise ValueError('new output outside source checkout required')
    result = current_graph()
    write_new_bundle(out,{'graph.json':canonical(result),'REVIEW.md':render(result).encode()})
    return verify(out)


def verify(root: Path) -> dict:
    marker = strict_json(read_artifact(root,'COMPLETE.json'))
    if (set(marker) != {'schema_version','sha256'} or type(marker['schema_version']) is not int or
            marker['schema_version']!=1 or type(marker['sha256']) is not dict or set(marker['sha256'])!=FILES):
        raise ValueError('source graph manifest mismatch')
    if {p.name for p in root.iterdir()} != FILES | {'COMPLETE.json'}:
        raise ValueError('unexpected graph artifact')
    result = current_graph()
    expected = {'graph.json':canonical(result),'REVIEW.md':render(result).encode()}
    for name, raw in expected.items():
        actual = read_artifact(root,name)
        if actual!=raw or hashlib.sha256(actual).hexdigest()!=marker['sha256'][name]:
            raise ValueError('graph differs from current source')
    return result


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, "Invalid arguments. Use --help; input values are not echoed.\n")


def main(argv: list[str]) -> int:
    p=PrivateArgumentParser(description='Analyze own-package import syntax without executing source')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('audit-wiring').add_argument('--out',type=Path,required=True)
    sub.add_parser('verify-wiring').add_argument('--bundle',type=Path,required=True)
    a=p.parse_args(argv)
    try:
        r=create(a.out) if a.command=='audit-wiring' else verify(a.bundle)
        print(json.dumps({'status':r['status'],'modules':len(r['modules']),
                          'unresolved':len(r['unresolved']),'all_runtime_links_proven':False}))
        return 0 if r['status']=='SOURCE_GRAPH_RESOLVED' else 1
    except (ValueError,OSError,TypeError,KeyError,RecursionError):
        print(json.dumps({'status':'SOURCE_GRAPH_ERROR','all_runtime_links_proven':False}))
        return 2


if __name__=='__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
