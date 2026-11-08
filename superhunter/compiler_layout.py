"""Bind supplied solc Standard JSON inputs/outputs to storage-layout review.

This is artifact validation, not a compiler, source parser, proof of compilation,
EVM executor or upgrade approval. An internally consistent forged AST remains
possible. Original bytes and all authority limits are preserved explicitly.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from . import storage_layout as layout
from . import source_types, storage_placement, solidity_inventory
from .native_runtime import load_components, source_inventory
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
MAX_SOURCES = 32
MAX_SOURCE_BYTES = 1_000_000
MAX_AST_OBJECTS = 40_000
MAX_CONTRACTS = 128
IDENTIFIER = re.compile(r'[A-Za-z_$][A-Za-z0-9_$]*\Z')
RAW_NAMES = ('before-input.json', 'before-output.json', 'after-input.json', 'after-output.json')
FILES = set(RAW_NAMES) | {'manifest.json', 'layout-manifest.json', 'before-layout.json',
                         'after-layout.json', 'result.json', 'audit.json', 'REVIEW.md'}
CODE_FILES = ('compiler_layout.py', 'storage_layout.py', 'safe_io.py', 'native_runtime.py', 'privacy.py', 'source_types.py', 'storage_placement.py', 'solidity_inventory.py')


class BindingError(ValueError):
    """Fixed codes only; supplied source or compiler diagnostics never echoed."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise BindingError(code)


def exact(value: Any, keys: set[str], code: str) -> None:
    need(type(value) is dict and set(value) == keys, code)


def source_name(value: Any) -> str:
    need(type(value) is str and 0 < len(value.encode('utf-8')) <= 512, 'SOURCE_NAME')
    p = PurePosixPath(value)
    need(not p.is_absolute() and '\\' not in value and ':' not in value and
         p.suffix == '.sol' and all(c not in ('', '.', '..') for c in value.split('/')) and
         all(ord(c) >= 32 and ord(c) != 127 for c in value), 'SOURCE_NAME')
    return value


def validate_manifest(m: Any) -> dict:
    exact(m, {'schema_version', 'repo', 'source', 'contract', 'before', 'after'}, 'MANIFEST_SCHEMA')
    need(type(m['schema_version']) is int and m['schema_version'] in (1,2,3,4), 'MANIFEST_VERSION')
    need(type(m['repo']) is str and layout.REPO.fullmatch(m['repo']) is not None and
         all(p not in ('.','..') for p in m['repo'].split('/')), 'REPOSITORY')
    source_name(m['source'])
    need(type(m['contract']) is str and IDENTIFIER.fullmatch(m['contract']) is not None, 'CONTRACT_NAME')
    for side in ('before','after'):
        record = m[side]
        exact(record, {'commit', 'compiler_version', 'input_sha256', 'output_sha256'}, 'SIDE_SCHEMA')
        need(type(record['commit']) is str and layout.COMMIT.fullmatch(record['commit']) is not None, 'COMMIT')
        need(type(record['compiler_version']) is str and
             layout.VERSION.fullmatch(record['compiler_version']) is not None, 'COMPILER_VERSION')
        for field in ('input_sha256','output_sha256'):
            need(type(record[field]) is str and layout.HEX.fullmatch(record[field]) is not None, 'ARTIFACT_HASH')
    return m


def _selection(settings: dict, source: str, contract: str, feature: str) -> bool:
    selection = settings.get('outputSelection')
    need(type(selection) is dict, 'OUTPUT_SELECTION')
    for file_key in ('*',source):
        entries = selection.get(file_key, {})
        need(type(entries) is dict, 'OUTPUT_SELECTION')
        keys = ('',) if feature == 'ast' else ('*',contract)
        for key in keys:
            flags = entries.get(key, [])
            need(type(flags) is list and all(type(v) is str for v in flags), 'OUTPUT_SELECTION')
            if feature in flags or '*' in flags:
                return True
    return False


def _span(value: Any, expected_file_id: int, raw: bytes) -> tuple[int,int]:
    need(type(value) is str and re.fullmatch(r'(?:0|[1-9][0-9]{0,9}):(?:0|[1-9][0-9]{0,9}):(?:0|[1-9][0-9]{0,9})', value) is not None,
         'SOURCE_SPAN_FORMAT')
    start, length, file_id = map(int,value.split(':'))
    need(file_id == expected_file_id, 'SOURCE_SPAN_FILE')
    need(0 <= start <= start + length <= len(raw), 'SOURCE_SPAN_BOUNDS')
    try:
        raw[:start].decode('utf-8',errors='strict')
        raw[start:start+length].decode('utf-8',errors='strict')
    except UnicodeError as exc:
        raise BindingError('SOURCE_SPAN_UTF8') from exc
    return start,length


def _bind_side(m: dict, side: str, input_raw: bytes, output_raw: bytes) -> tuple[bytes,dict]:
    need(type(input_raw) is bytes and type(output_raw) is bytes and
         len(input_raw) <= 2_000_000 and len(output_raw) <= 2_000_000, 'ARTIFACT_SIZE')
    need(layout.sha(input_raw) == m[side]['input_sha256'] and
         layout.sha(output_raw) == m[side]['output_sha256'], 'ARTIFACT_HASH_MISMATCH')
    inp, out = strict_json(input_raw), strict_json(output_raw)
    exact(inp, {'language','sources','settings'}, 'STANDARD_INPUT_PROFILE')
    need(inp['language'] == 'Solidity', 'LANGUAGE')
    need(type(inp['sources']) is dict and 1 <= len(inp['sources']) <= MAX_SOURCES, 'SOURCE_BUDGET')
    need(type(inp['settings']) is dict, 'SETTINGS')
    sources = {}
    for name, item in inp['sources'].items():
        source_name(name)
        exact(item, {'content'}, 'INLINE_SOURCE_REQUIRED')
        need(type(item['content']) is str, 'SOURCE_CONTENT')
        sources[name] = item['content'].encode('utf-8')
    need(sum(map(len,sources.values())) <= MAX_SOURCE_BYTES, 'SOURCE_BYTES_BUDGET')
    need(m['source'] in sources, 'SELECTED_SOURCE_MISSING')
    diagnostics = out.get('errors', [])
    need(type(diagnostics) is list and len(diagnostics) <= 2048, 'DIAGNOSTICS_SCHEMA')
    for error in diagnostics:
        need(type(error) is dict and type(error.get('severity')) is str and
             error['severity'] in ('error','warning','info'), 'DIAGNOSTICS_SCHEMA')
    # solc Standard JSON can exit 0 while returning errors. Never use process success.
    need(not any(e['severity'] == 'error' for e in diagnostics), 'COMPILER_ERROR_IN_ARTIFACT')
    outputs = out.get('sources')
    need(type(outputs) is dict and set(outputs) == set(sources), 'SOURCE_INVENTORY_MISMATCH')
    nodes: dict[int,tuple[dict,str]] = {}
    contracts = {}; roots = {}; file_ids = set(); seen_objects = 0
    for name, raw in sources.items():
        info = outputs[name]
        need(type(info) is dict and type(info.get('id')) is int and info['id'] >= 0 and
             info['id'] not in file_ids, 'SOURCE_FILE_ID')
        file_ids.add(info['id'])
        need(_selection(inp['settings'],name,m['contract'],'ast'), 'AST_OUTPUT_NOT_REQUESTED')
        ast = info.get('ast')
        need(type(ast) is dict and ast.get('nodeType') == 'SourceUnit' and
             ast.get('absolutePath') == name and type(ast.get('nodes')) is list, 'SOURCE_AST_REQUIRED')
        roots[name] = _span(ast.get('src'),info['id'],raw)
        pending = [ast]
        while pending:
            node = pending.pop(); seen_objects += 1
            need(seen_objects <= MAX_AST_OBJECTS, 'AST_BUDGET')
            if type(node) is dict:
                if 'nodeType' in node:
                    need(type(node['nodeType']) is str, 'AST_NODE_TYPE')
                    if 'id' in node:
                        identifier = node['id']
                        need(type(identifier) is int and identifier >= 0 and identifier not in nodes, 'AST_NODE_ID')
                        nodes[identifier] = (node,name)
                    if node['nodeType'] in ('ContractDefinition','VariableDeclaration'):
                        need('id' in node, 'DECLARATION_ID_REQUIRED')
                    if node['nodeType'] == 'ContractDefinition':
                        need(type(node.get('name')) is str and IDENTIFIER.fullmatch(node['name']) is not None,
                             'CONTRACT_NAME')
                        need(type(node.get('nodes')) is list and type(node.get('baseContracts')) is list,
                             'CONTRACT_AST_SCHEMA')
                        key = (name,node['name'])
                        need(key not in contracts and len(contracts) < MAX_CONTRACTS, 'CONTRACT_INVENTORY')
                        start,length = _span(node.get('src'),info['id'],raw)
                        root_start,root_length = roots[name]
                        need(root_start <= start and start+length <= root_start+root_length, 'SOURCE_UNIT_SPAN')
                        contracts[key] = node
                pending.extend(node.values())
            elif type(node) is list:
                pending.extend(node)
    selected = contracts.get((m['source'],m['contract']))
    need(selected is not None, 'SELECTED_CONTRACT_AST_MISSING')
    need(_selection(inp['settings'],m['source'],m['contract'],'storageLayout'), 'LAYOUT_OUTPUT_NOT_REQUESTED')
    by_id = {node['id']:node for node in contracts.values()}
    reachable = set(); active = set()

    def visit(identifier: int) -> None:
        need(identifier in by_id, 'INHERITANCE_REFERENCE')
        need(identifier not in active, 'INHERITANCE_CYCLE')
        if identifier in reachable:
            return
        active.add(identifier)
        node = by_id[identifier]
        parent_ids = set()
        for spec in node['baseContracts']:
            need(type(spec) is dict and type(spec.get('baseName')) is dict, 'INHERITANCE_SCHEMA')
            ref = spec['baseName'].get('referencedDeclaration')
            need(type(ref) is int and ref not in parent_ids, 'INHERITANCE_REFERENCE')
            parent_ids.add(ref);visit(ref)
        active.remove(identifier);reachable.add(identifier)

    visit(selected['id'])
    lineage = selected.get('linearizedBaseContracts')
    need(type(lineage) is list and all(type(v) is int for v in lineage) and
         bool(lineage) and lineage[0] == selected['id'] and len(set(lineage)) == len(lineage) and
         set(lineage) == reachable, 'INHERITANCE_CLOSURE_MISMATCH')
    # Only the set is checked. We do not claim independent C3 ordering or semantic parsing.
    persistent = {}; excluded = Counter(); spans = {}
    for identifier in lineage:
        contract = by_id[identifier]; source = nodes[identifier][1]
        contract_start,contract_len = _span(contract['src'],outputs[source]['id'],sources[source])
        for var in contract['nodes']:
            need(type(var) is dict, 'CONTRACT_CHILD_SCHEMA')
            if var.get('nodeType') != 'VariableDeclaration':
                continue
            need(var.get('stateVariable') is True, 'TOP_LEVEL_STATE_DECLARATION')
            need(type(var.get('name')) is str and IDENTIFIER.fullmatch(var['name']) is not None, 'VARIABLE_NAME')
            need(type(var.get('constant')) is bool and var.get('mutability') in ('mutable','constant','immutable') and
                 var.get('storageLocation') in ('default','transient'), 'STATE_VARIABLE_PROFILE')
            need(var['constant'] == (var['mutability'] == 'constant'), 'STATE_MUTABILITY_CONTRADICTION')
            start,length = _span(var.get('src'),outputs[source]['id'],sources[source])
            need(length > 0 and contract_start <= start and start+length <= contract_start+contract_len,
                 'DECLARATION_OUTSIDE_CONTRACT')
            name_start,name_length = _span(var.get('nameLocation'),outputs[source]['id'],sources[source])
            need(start <= name_start and name_start+name_length <= start+length and
                 sources[source][name_start:name_start+name_length] == var['name'].encode('utf-8'),
                 'DECLARATION_NAME_BYTES_MISMATCH')
            if var['mutability'] != 'mutable' or var['storageLocation'] == 'transient':
                excluded[var['mutability'] if var['mutability'] != 'mutable' else 'transient'] += 1
                continue
            persistent[var['id']] = var
            spans[var['id']] = {'source':source,'source_sha256':layout.sha(sources[source]),
                                'start_byte':start,'length_bytes':length,
                                'name_start_byte':name_start,'name_length_bytes':name_length,
                                'span_sha256':layout.sha(sources[source][start:start+length])}
    all_contracts = out.get('contracts')
    need(type(all_contracts) is dict and type(all_contracts.get(m['source'])) is dict and
         type(all_contracts[m['source']].get(m['contract'])) is dict, 'CONTRACT_OUTPUT_MISSING')
    storage = all_contracts[m['source']][m['contract']].get('storageLayout')
    need(type(storage) is dict and set(storage) == {'storage','types'} and
         type(storage['storage']) is list and len(storage['storage']) <= layout.MAX_ENTRIES, 'LAYOUT_MISSING')
    fq = m['source']+':'+m['contract']; seen = set(); bound = []
    for row in storage['storage']:
        need(type(row) is dict and type(row.get('astId')) is int and row['astId'] not in seen, 'LAYOUT_DECLARATION_ID')
        ref = row['astId'];seen.add(ref)
        need(ref in persistent, 'LAYOUT_NOT_PERSISTENT_DECLARATION')
        var = persistent[ref]
        need(row.get('contract') == fq, 'LAYOUT_CONTRACT_MISMATCH')
        need(row.get('label') == var['name'], 'LAYOUT_AST_LABEL_MISMATCH')
        bound.append({'ast_id':ref,'declaration_name_sha256':layout.sha(var['name'].encode()),**spans[ref]})
    need(seen == set(persistent), 'STORAGE_DECLARATION_COVERAGE_MISMATCH')
    artifact = {'schema_version':1,
                'target':{'repo':m['repo'],'commit':m[side]['commit'],'contract':fq},
                'compiler_version':m[side]['compiler_version'],'storage_layout':storage}
    facts = {'source_sha256':{k:layout.sha(v) for k,v in sorted(sources.items())},
             'settings_sha256':layout.sha(canonical(inp['settings'])),
             'persistent_declarations':len(persistent),'bound_declarations':sorted(bound,key=lambda r:r['ast_id']),
             'excluded_declarations':dict(sorted(excluded.items())),
             'contract_ancestry_count':len(lineage),
             'diagnostic_counts':dict(sorted(Counter(e['severity'] for e in diagnostics).items())),
             'ignored_output_sections':sorted(set(out)-{'sources','contracts','errors'}),
             'type_semantics_from_source_checked':False,'c3_order_independently_checked':False}
    if m['schema_version'] >= 2:
        typed = []
        for row in storage['storage']:
            declaration = persistent[row['astId']]
            origin = nodes[declaration['id']][1]
            typed.append(source_types.bind_declaration(declaration, row, storage['types'],
                                                        sources[origin], outputs[origin]['id']))
        checked = sum(r['status'] == 'TYPE_CONSISTENT_IN_PROFILE' for r in typed)
        facts['type_correspondence'] = {
            'profile':'elementary-literal-arrays-mappings-v1',
            'declarations':len(typed), 'checked':checked, 'review_required':len(typed)-checked,
            'all_declared_types_checked':checked == len(typed),
            'records':sorted(typed,key=lambda r:r['ast_id']),
            'full_solidity_semantic_analysis':False,
        }
    if m['schema_version'] >= 3:
        facts['storage_head_placement'] = storage_placement.verify_heads(
            contract=selected, lineage=lineage, persistent=persistent, storage=storage,
            source=sources[m['source']], file_id=outputs[m['source']]['id'],
            compiler_version=m[side]['compiler_version'], typed=typed)
    if m['schema_version'] == 4:
        facts['source_declaration_inventory'] = solidity_inventory.verify_declarations(
            sources[m['source']], selected, outputs[m['source']]['id'], m[side]['compiler_version'])
    return canonical(artifact),facts


def evaluate(manifest: Any, inputs: dict[str,bytes]) -> tuple[dict,dict[str,bytes]]:
    m = validate_manifest(manifest)
    exact(inputs,set(RAW_NAMES),'INPUT_SET')
    artifacts = {}; bindings = {}
    for side in ('before','after'):
        artifacts[side],bindings[side] = _bind_side(m,side,inputs[side+'-input.json'],inputs[side+'-output.json'])
    lm = {'schema_version':1,'repo':m['repo'],'contract':m['source']+':'+m['contract'],
          **{side:{'commit':m[side]['commit'],'sha256':layout.sha(artifacts[side])} for side in artifacts}}
    comparison = layout.compare(lm,artifacts['before'],artifacts['after'])
    settings_changed = bindings['before']['settings_sha256'] != bindings['after']['settings_sha256']
    incomplete_types = (m['schema_version'] >= 2 and any(
        not b['type_correspondence']['all_declared_types_checked'] for b in bindings.values()))
    incomplete_placement = (m['schema_version'] >= 3 and any(
        not b['storage_head_placement']['all_declared_heads_checked'] for b in bindings.values()))
    incomplete_inventory = (m['schema_version'] == 4 and any(
        not b['source_declaration_inventory']['all_source_state_declarations_matched'] for b in bindings.values()))
    state = ('SOURCE_LAYOUT_CHANGE_DETECTED' if comparison['status'] == 'LAYOUT_CHANGE_DETECTED' else
             'SOURCE_LAYOUT_REVIEW_REQUIRED' if incomplete_types or incomplete_placement or incomplete_inventory or settings_changed or comparison['status'] != 'LAYOUT_PRESERVED_IN_PROFILE'
             else 'SOURCE_LAYOUT_PRESERVED_IN_PROFILE')
    result = {'schema_version':1,'profile':('solc-standard-json-source-inventory-v4' if m['schema_version']==4 else 'solc-standard-json-placement-v3' if m['schema_version']==3 else 'solc-standard-json-typed-binding-v2' if m['schema_version']==2
                                           else 'solc-standard-json-declaration-binding-v1'),'status':state,
              'expected_manifest_sha256':layout.sha(canonical(m)),
              'input_sha256':{k:layout.sha(v) for k,v in inputs.items()},
              'bindings':bindings,'layout_review':comparison,'compiler_settings_changed':settings_changed,
              'source_bytes_changed':bindings['before']['source_sha256'] != bindings['after']['source_sha256'],
              'compiler_executed_here':False,'compiler_output_authenticated':False,
              'source_syntax_reparsed':False,'deployed_state_verified':False,
              'upgrade_authorized':False,'vulnerability_confirmed':False,'human_review_required':True}
    if m['schema_version'] >= 2:
        result['all_declared_types_checked'] = not incomplete_types
    if m['schema_version'] >= 3:
        result['all_declared_storage_heads_checked'] = not incomplete_placement
    if m['schema_version'] == 4:
        result['all_source_state_declarations_matched'] = not incomplete_inventory
    derived = {'layout-manifest.json':canonical(lm),
               'before-layout.json':artifacts['before'],'after-layout.json':artifacts['after']}
    need(len(canonical(result)) <= 2_000_000, 'OUTPUT_SIZE')
    return result,derived


def _engine() -> dict:
    return {'sources':{n:layout.sha(read_artifact(ROOT,n)) for n in CODE_FILES},
            'native_sources':source_inventory()}


def _audit(result: dict, engine: dict) -> dict:
    log = load_components().audit.AuditLog(clock=lambda:'1970-01-01T00:00:00+00:00')
    log.append('compiler_layout.inputs',{'manifest_sha256':result['expected_manifest_sha256'],
                                        'inputs':result['input_sha256']})
    for side in ('before','after'):
        log.append('compiler_layout.bind',{'side':side,'binding_sha256':layout.sha(canonical(result['bindings'][side]))})
    log.append('compiler_layout.result',{'result_sha256':layout.sha(canonical(result))})
    log.assert_intact()
    return {'engine':engine,'entries':[asdict(e) for e in log.entries],
            'event_time_semantics':'fixed-reference-not-wall-clock'}


def render(result: dict) -> bytes:
    b = result['bindings']
    return ('# Correspondencia fuente–AST–layout\n\n'
            f"Estado: {result['status']}.\n"
            f"Declaraciones persistentes antes/después: {b['before']['persistent_declarations']}/"
            f"{b['after']['persistent_declarations']}.\n"
            f"Cambios estructurales: {len(result['layout_review']['changes'])}.\n\n"
            f"Perfil: {result['profile']}.\n"
            f"Contraste de tipos completo en el perfil: {result.get('all_declared_types_checked', False)}.\n\n"
            f"Posiciones de almacenamiento reconstruidas: {result.get('all_declared_storage_heads_checked', False)}.\n\n"
            'Se comprobaron artefactos aportados, no una compilación ejecutada.\n'
            f"Inventario de declaraciones contrastado desde fuente: {result.get('all_source_state_declarations_matched', False)}.\n"
            'Un AST fabricado de forma consistente sigue siendo posible. No se autentica al compilador,\n'
            'la pertenencia a un commit ni el comportamiento del código. No se autoriza un upgrade.\n'
            'Las fuentes y diagnósticos originales son privados y no se incluyen en este resumen.\n').encode()


def _documents(mraw: bytes, inputs: dict[str,bytes]) -> dict[str,bytes]:
    identity = _engine()
    result,derived = evaluate(strict_json(mraw),inputs)
    files = {'manifest.json':mraw,**inputs,**derived,
             'result.json':canonical(result),'audit.json':canonical(_audit(result,identity)),
             'REVIEW.md':render(result)}
    need(_engine() == identity, 'ENGINE_CHANGED')
    need(all(len(v) <= 2_000_000 for v in files.values()), 'OUTPUT_SIZE')
    return files


def create(expected: Path, before_input: Path, before_output: Path,
           after_input: Path, after_output: Path, out: Path) -> dict:
    need(not out.exists() and not out.is_symlink(), 'NEW_OUTPUT_REQUIRED')
    need(not out.resolve().is_relative_to(ROOT.parent), 'OUTPUT_IN_CHECKOUT')
    need(not expected.resolve().is_relative_to(out.resolve()), 'EXTERNAL_MANIFEST_REQUIRED')
    paths = dict(zip(RAW_NAMES,(before_input,before_output,after_input,after_output)))
    raw = read_artifact(expected.parent,expected.name)
    inputs = {k:read_artifact(p.parent,p.name) for k,p in paths.items()}
    documents = _documents(raw,inputs)
    need(read_artifact(expected.parent,expected.name) == raw and
         all(read_artifact(p.parent,p.name) == inputs[k] for k,p in paths.items()), 'INPUT_CHANGED')
    write_new_bundle(out,documents)
    return verify(out,expected)


def verify(root: Path, expected: Path) -> dict:
    need(not root.is_symlink(), 'ROOT_SYMLINK')
    need(not expected.resolve().is_relative_to(root.resolve()), 'EXTERNAL_MANIFEST_REQUIRED')
    raw = read_artifact(expected.parent,expected.name)
    validate_manifest(strict_json(raw))
    marker = strict_json(read_artifact(root,'COMPLETE.json'))
    exact(marker,{'schema_version','sha256'},'BUNDLE_SCHEMA')
    need(type(marker['schema_version']) is int and marker['schema_version'] == 1 and
         type(marker['sha256']) is dict and set(marker['sha256']) == FILES and
         {p.name for p in root.iterdir()} == FILES | {'COMPLETE.json'}, 'BUNDLE_FILES')
    data = {n:read_artifact(root,n) for n in FILES}
    need(all(layout.sha(v) == marker['sha256'][k] for k,v in data.items()), 'BUNDLE_HASH')
    need(canonical(strict_json(data['manifest.json'])) == canonical(strict_json(raw)), 'EXTERNAL_REFERENCE_MISMATCH')
    recomputed = _documents(data['manifest.json'],{n:data[n] for n in RAW_NAMES})
    need(recomputed == data, 'RECOMPUTATION_MISMATCH')
    need(read_artifact(expected.parent,expected.name) == raw, 'EXTERNAL_REFERENCE_CHANGED')
    return strict_json(data['result.json'])


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Check supplied Solidity source/AST/layout artifacts; no compiler execution')
    sub = parser.add_subparsers(dest='command',required=True)
    make = sub.add_parser('review-compiler-layout')
    for name in ('expected','before-input','before-output','after-input','after-output','out'):
        make.add_argument('--'+name,type=Path,required=True)
    check = sub.add_parser('verify-compiler-layout')
    check.add_argument('--bundle',type=Path,required=True)
    check.add_argument('--expected',type=Path,required=True)
    args = parser.parse_args(argv)
    try:
        r = (create(args.expected,args.before_input,args.before_output,args.after_input,args.after_output,args.out)
             if args.command == 'review-compiler-layout' else verify(args.bundle,args.expected))
        print(json.dumps({k:r[k] for k in ('status','compiler_executed_here','vulnerability_confirmed')}))
        return 0 if r['status'] == 'SOURCE_LAYOUT_PRESERVED_IN_PROFILE' else 1
    except (ValueError,OSError,KeyError,TypeError,RecursionError,UnicodeError,OverflowError) as exc:
        print(json.dumps({'status':'COMPILER_LAYOUT_REJECTED','error_type':type(exc).__name__,
                          'compiler_executed_here':False,'vulnerability_confirmed':False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
