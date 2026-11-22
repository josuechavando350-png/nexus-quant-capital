"""Inspect one fixed T36 compiler output with upstream source and ABI libraries."""
import ctypes as C
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def solidity_syntax(library, source):
    class Node(C.Structure):
        _fields_ = [('context', C.c_uint32 * 4), ('id', C.c_void_p), ('tree', C.c_void_p)]
    lib = C.CDLL(str(library))
    def fn(name, returns, *args):
        call = getattr(lib, name)
        call.restype, call.argtypes = returns, args
        return call
    ptr, u32 = C.c_void_p, C.c_uint32
    language = fn('tree_sitter_solidity', ptr)()
    parser = fn('ts_parser_new', ptr)()
    tree = None
    try:
        if not fn('ts_parser_set_language', C.c_bool, ptr, ptr)(parser, language):
            raise ValueError('incompatible Semgrep Solidity grammar')
        tree = fn('ts_parser_parse_string', ptr, ptr, ptr, C.c_char_p, u32)(parser, None, source, len(source))
        if not tree:
            raise ValueError('could not parse Solidity')
        root = fn('ts_tree_root_node', Node, ptr)(tree)
        if fn('ts_node_has_error', C.c_bool, Node)(root):
            raise ValueError('Semgrep grammar found a syntax error')
        count = fn('ts_node_named_child_count', u32, Node)
        child = fn('ts_node_named_child', Node, Node, u32)
        kind = fn('ts_node_type', C.c_char_p, Node)
        todo, functions = [root], 0
        while todo:
            item = todo.pop()
            functions += kind(item) == b'function_definition'
            todo.extend(child(item, i) for i in range(count(item)))
        return functions
    finally:
        if tree:
            fn('ts_tree_delete', None, ptr)(tree)
        fn('ts_parser_delete', None, ptr)(parser)


def copy_module(repo, relative, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(subprocess.check_output(['git', '-C', repo, 'show', 'HEAD:' + relative]))


def abi_type(parameter):
    type_name = parameter['type']
    if type_name.startswith('tuple'):
        fields = ','.join(abi_type(field) for field in parameter['components'])
        return '(' + fields + ')' + type_name.removeprefix('tuple')
    return type_name


def main():
    runtime, root = map(Path, sys.argv[1:3])
    work = Path.cwd()
    # A minimal package layout loads the ABI parser without importing Manticore's EVM runtime.
    for name, members in {'manticore': ('exceptions.py', 'ethereum/abitypes.py'),
                          'halmos': ('mapper.py', 'logs.py', 'exceptions.py')}.items():
        for member in members:
            src = ('src/halmos/' if name == 'halmos' else 'manticore/') + member
            copy_module(root / 'upstream' / name, src, work / name / member)
    sys.path[:0] = [str(work), *(str(runtime / path) for path in
                    ('ply', 'pyevmasm', 'rich', 'markdown-it-py', 'mdurl/src'))]
    (work / 'future').symlink_to(runtime / 'future/src/future', target_is_directory=True)
    from manticore.ethereum.abitypes import parse
    from halmos.mapper import Mapper
    artifacts = {
        'slither_selector': ('013-slither', 'slither/utils/function.py'),
        'mythril_opcodes': ('mythril', 'mythril/support/opcodes.py'),
        'kontrol_sources': ('kontrol', 'src/kontrol/solc.py')}
    modules = {}
    for name, (folder, relative) in artifacts.items():
        location = work / (name + '.py')
        copy_module(root / 'upstream' / folder, relative, location)
        modules[name] = module(name, location)
    data = json.loads((work / 'joined-input.json').read_text())
    source = (work / 'src/NqcFlashFundingExecutor.sol').read_bytes()
    ast = data['ast']
    name = 'NqcFlashFundingExecutor'
    mapper = Mapper()
    mapper.parse_ast(ast)
    mapping = mapper.get_by_name(name).nodes
    evm = data['contract']['evm']
    signatures = evm['methodIdentifiers']
    abi = {}
    for entry in data['contract']['abi']:
        if entry['type'] == 'function':
            types = [abi_type(parameter) for parameter in entry['inputs']]
            abi[entry['name'] + '(' + ','.join(types) + ')'] = len(types)
    if signatures.keys() != abi.keys():
        raise ValueError('ABI declarations differ from solc method identifiers')
    selectors = {}
    for signature, expected in signatures.items():
        label, args = signature.split('(', 1)
        shape = parse('(' + args)
        computed = f'{modules["slither_selector"].get_function_id(signature):08x}'
        if (shape[0] != 'tuple' or len(shape[1]) != abi[signature]
                or computed != expected or mapping['0x' + computed].name != label):
            raise ValueError('ABI selector mismatch for ' + signature)
        selectors[signature] = computed
    function_names = [node['name'] for contract in ast['nodes'] for node in contract.get('nodes', [])
                      if node['nodeType'] == 'FunctionDefinition' and node.get('kind') == 'function']
    declarations = len(function_names)
    syntax = solidity_syntax(runtime / 'semgrep-solidity.so', source)
    if not declarations or syntax != declarations:
        raise ValueError(f'Solidity function counts differ: {declarations} and {syntax}')
    lines = int(subprocess.check_output([runtime / 'aderyn-lines'], input=source))
    if not 0 < lines <= len(source.splitlines()):
        raise ValueError('invalid Aderyn source metrics')
    code = bytes.fromhex(evm['deployedBytecode']['object'])
    walk = subprocess.check_output([runtime / 'ityfuzz-opcodes'], input=code, timeout=15).decode().splitlines()
    instructions = modules['kontrol_sources'].ContractSource(0, data['contract'], None).instructions
    opnames = modules['mythril_opcodes'].ADDRESS_OPCODE_MAPPING
    if not walk or len(instructions) != len(walk):
        raise ValueError('instruction counts differ')
    mapped = 0
    frequency = {}
    for row, instr in zip(walk, instructions, strict=True):
        pc, opcode = map(int, row.split())
        if pc != instr.pc or code[pc] != opcode:
            raise ValueError('instruction boundary differs')
        mnemonic = opnames.get(opcode, f'0x{opcode:02x}')
        frequency[mnemonic] = frequency.get(mnemonic, 0) + 1
        start, size, file_id, *_ = instr.source_map_entry
        if file_id == 0:
            if not 0 <= start <= start + size <= len(source):
                raise ValueError('invalid solc source range')
            mapped += 1
    if mapped < 1:
        raise ValueError('no instructions mapped to T36')
    print(json.dumps({'method_selectors': selectors, 'grammar_functions': syntax, 'code_lines': lines,
                      'function_names': sorted(function_names), 'instructions': len(walk), 'mapped_to_source': mapped, 'opcode_counts': frequency}))


if __name__ == '__main__':
    main()
