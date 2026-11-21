"""Check the instruction and stack layouts of three immutable NQC compiler outputs."""
from collections import Counter
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .product_notice_ranking import ISOLATE
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_sources import git
from .safe_io import canonical, read_artifact, strict_json

CAPTURE = 'superhunter/tests/fixtures/bytecode_native_capture.json'
CAPTURE_SHA = '430e4399086eac62e3e1e51f14aaa052d70d69f65a81955111fc8d6493db7d88'
SUPPLY = 'superhunter/product_supply/'
SOLC_SHA = 'f3e987dc6ecebd4bd350c48edcbc320b46cf9e3109bd3fc3d88f1acaf4c428f7'
TOOLS = {
    'node': 'acbe4b8d9153b841ed0697cbfc4f93e767386620edb745ab9358306c0a6f31aa',
    'rustc': '859254978c0a0402c32f949f6de0d99aee73be8d15f45aac00ae1448aac51e74',
}
HEVM = 'argotorg/hevm'
WHATSABI = 'shazow/whatsabi'
KEVM = 'runtimeverification/evm-semantics'
REVM = 'bluealloy/revm'
KDIR = 'kevm-pyk/src/kevm_pyk/kproj/evm-semantics/'
UPSTREAM = {
    HEVM: ('017-hevm', '87598e81c044e2889e4a42e9fd706bd5396448f2', {
        'src/EVM/Op.hs': '402c99650410a124822e92fbcdc341f1a15dce8c0aa9a7b9f8a828a2f4da53dd'}),
    WHATSABI: ('020-whatsabi', 'eefa62383640b9056aade49d1d5ed2206ffcdb3b', {
        'src/opcodes.ts': 'b697e1edfaa58d0a16709bf4b38d3e0579a23b49e845045bda36be0182500148'}),
    KEVM: ('031-evm-semantics', 'fbb2edbb8e84bb05b6ba7a255ce1f44f76051ad1', {
        KDIR + 'evm.md': 'c2144e0754959b0f4bf8bb235b04da8b0d15eeb3004a1735ef17c73108304c96',
        KDIR + 'schedule.md': '4ffbba243e553b88c69a17ab1c6f5b99273669e18fca10deb6b3204ca9f66638'}),
    REVM: ('038-revm', '61eb0f231227db0a89f9cd2cd976cc372b6e94d1', {
        'crates/bytecode/src/opcode.rs': '275d2d7f6de0d6d7d96f18a64631cae008ea5cd0d235a1613e8854df79fe4937'}),
}


def checked(condition, message):
    if not condition:
        raise EvidenceError('fixed EVM layout: ' + message)


def sources(root):
    files = {}
    for repository, (folder, revision, paths) in UPSTREAM.items():
        checkout = Path(root) / folder
        checked(git(checkout, 'rev-parse', 'HEAD').decode().strip() == revision,
                f'unexpected checkout for {repository}')
        for path, digest in paths.items():
            raw = read_artifact(checkout, path)
            checked(sha(raw) == digest, 'source bytes differ for ' + path)
            files[path] = raw
    return files


def capture():
    raw = read_artifact(ROOT, CAPTURE)
    checked(sha(raw) == CAPTURE_SHA, 'changed compiler capture')
    return strict_json(raw)['cases']


def runtime(case):
    checked(case['input']['settings']['evmVersion'] == 'cancun', 'unexpected compiler target')
    output = strict_json(case['output_utf8'])
    contract = output['contracts']['State.sol']['StatefulConservation']
    bytecode = bytes.fromhex(contract['evm']['deployedBytecode']['object'])
    # This compiler profile emitted a fixed two-entry CBOR map with a SHA-256 IPFS
    # multihash and solc 0.8.30. Reject other map/length forms or missing separator.
    prefix = bytes.fromhex('a2646970667358221220')
    suffix = bytes.fromhex('64736f6c634300081e0033')
    trailer = bytecode[-53:]
    checked(len(trailer) == 53 and trailer.startswith(prefix) and trailer.endswith(suffix)
            and bytecode[-54:-53] == b'\xfe', 'invalid metadata boundary')
    return bytecode[:-53]


def run(program, args, cwd, stdin=b''):
    env = {'PATH': os.defpath, 'LANG': 'C', 'HOME': str(cwd), 'TMPDIR': str(cwd)}
    try:
        return subprocess.run([*ISOLATE, str(program), *args], cwd=cwd, env=env, input=stdin,
                              capture_output=True, timeout=40, check=True).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise EvidenceError('fixed EVM layout: isolated tool failed') from exc


def runtime_path(name):
    tool = shutil.which(name)
    checked(tool is not None, 'missing ' + name)
    with open(tool, 'rb') as stream:
        checked(hashlib.file_digest(stream, 'sha256').hexdigest() == TOOLS[name],
                'unreviewed ' + name + ' executable')
    return Path(tool).resolve()


def native(files, inputs, work):
    (work/'opcodes.mts').write_bytes(files['src/opcodes.ts'])
    (work/'opcode.rs').write_bytes(files['crates/bytecode/src/opcode.rs'])
    for destination, artifact in [('reader.mjs', 'fixed-opcodes-node.mjs.txt'), ('main.rs', 'fixed-opcodes-rust.rs.txt')]:
        (work/destination).write_bytes(read_artifact(ROOT, SUPPLY + artifact))
    run(runtime_path('rustc'), ['--edition=2021', '--crate-name', 'nqc_layout', 'main.rs', '-o', 'reader'], work)
    js = strict_json(run(runtime_path('node'), ['--permission', '--allow-fs-read=' + str(work),
                                                '--disable-warning=ExperimentalWarning', 'reader.mjs'],
                         work, canonical([b.hex() for b in inputs])))['instructions']
    rs = run(work/'reader', [], work, ''.join(b.hex() + '\n' for b in inputs).encode()).decode().splitlines()
    rust = []
    for line in rs:
        rows = []
        for entry in line.split(';') if line else ():
            pc, name, width, pops, pushes = entry.split(',')
            rows.append((int(pc), name, int(width), int(pops), int(pushes)))
        rust.append(rows)
    checked(len(js) == len(rust) == len(inputs), 'missing native result')
    return js, rust


def hevm_names(source):
    block = source.decode().split('intToOpName a =', 1)[1].split('opString ::', 1)[0]
    return {int(n, 16): name for n, name in re.findall(r'^    (0x[0-9a-f]+) -> "([A-Z0-9]+)"$', block, re.M)}


def k_rules(files):
    semantics = files[KDIR + 'evm.md'].decode()
    schedule = files[KDIR + 'schedule.md'].decode()
    rules = {}
    for line in semantics.splitlines():
        match = re.fullmatch(r'\s*rule #dasmOpCode\(\s*(\d+),\s*(?:_|SCHED)\s*\) => (\w+(?:\(\d+\))?)'
                             r'(?:\s+requires (\w+)\s*<< SCHED >>)?\s*', line)
        if match:
            number, token, gate = match.groups()
            token = {'PUSHZERO': 'PUSH0', 'EVMOR': 'OR'}.get(token, token)
            rules[int(number)] = (token.replace('(', '').replace(')', ''), gate)
    flags = {(chain, flag): value == 'true' for flag, chain, value in re.findall(
        r'\]:\s+(G\w+)\s+<< (\w+) >> => (true|false)', schedule)}
    parents = dict(re.findall(r'\]:\s+SCHEDFLAG\s+<< (\w+) >> => SCHEDFLAG << (\w+) >>', schedule))
    return rules, flags, parents


def gate_enabled(gate, chain, flags, parents):
    seen = set()
    while chain not in seen:
        if (chain, gate) in flags:
            return flags[chain, gate]
        seen.add(chain)
        if chain not in parents:
            break
        chain = parents[chain]
    raise EvidenceError('fixed EVM layout: missing schedule rule for ' + gate)


def views(code, js, rust, names, semantics, oracle):
    rules, flags, parents = semantics
    checked(len(rust) == len(js) > 0, 'native readers disagree on instruction count')
    stops = {'STOP', 'JUMP', 'JUMPI', 'RETURN', 'REVERT', 'INVALID'}
    blocks, gates, boundaries = [], Counter(), []
    required = depth = start = cursor = 0
    for index, (pc, name, width, pops, pushes) in enumerate(rust):
        checked(pc == cursor and pc < len(code), 'uncovered or overlapping bytes')
        opcode = code[pc]
        checked(js[index] == [pc, name, width, pops, pushes - pops], 'native readers disagree')
        checked(names.get(opcode) == name, 'HEVM mnemonic disagrees')
        kname, gate = rules.get(opcode, (None, None))
        checked(kname == name, 'KEVM encoding disagrees')
        if gate:
            checked(gate_enabled(gate, 'CANCUN', flags, parents), 'inactive fork feature')
            gates[gate] += 1
        cursor = pc + width + 1
        checked(cursor <= len(code), 'truncated immediate')
        boundaries.append([pc, name, code[pc + 1:cursor].hex()])
        if name == 'JUMPDEST' and pc != start:
            blocks.append([start, pc, required, depth])
            start, required, depth = pc, 0, 0
        required = max(required, pops - depth)
        depth += pushes - pops
        if name in stops:
            blocks.append([start, cursor, required, depth])
            start, required, depth = cursor, 0, 0
    checked(cursor == len(code) == start, 'incomplete block partition')
    digest = sha(canonical(boundaries))
    checked(digest == oracle, 'solc opcode or operand disagreement')
    maximum = max(row[2] for row in blocks)
    peak_blocks = [{'start_pc': begin, 'end_pc_exclusive': end, 'net_delta': delta}
                   for begin, end, needed, delta in blocks if needed == maximum]
    return {'runtime_code_sha256': sha(code), 'code_bytes': len(code), 'instructions': len(boundaries),
            'mnemonics': len({b[1] for b in boundaries}), 'instruction_map_sha256': digest,
            'blocks': len(blocks), 'stack_layout_sha256': sha(canonical(blocks)),
            'maximum_block_entry_requirement': maximum, 'blocks_at_maximum': peak_blocks,
            'fork_gated_instructions': dict(gates)}


def review(source_root):
    files = sources(source_root)
    cases = capture()
    codes = [runtime(case) for case in cases.values()]
    oracle = strict_json(read_artifact(ROOT, SUPPLY + 'fixed-opcodes-solc.json'))
    checked(sha(canonical(oracle)) == '41f58cee10a4678dcf71b0ba8dd6389d2124541a4cc16d7aed678114387500b9'
            and set(oracle) == set(cases), 'compiler oracle case mismatch')
    with tempfile.TemporaryDirectory(prefix='nqc-evm-layout-') as directory:
        js, rust = native(files, [*codes, b'\x61\xaa', b'\x60\x5b\x00'], Path(directory))
    checked(js[-2] == rust[-2] == [], 'truncated immediate accepted')
    checked([r[0] for r in js[-1]] == [r[0] for r in rust[-1]] == [0, 2],
            'operand incorrectly decoded as JUMPDEST')
    names = hevm_names(files['src/EVM/Op.hs'])
    semantics = k_rules(files)
    checked(not gate_enabled('Ghaspushzero', 'BERLIN', *semantics[1:]), 'premature PUSH0 availability')
    results = {case: views(codes[i], js[i], rust[i], names, semantics, oracle[case])
               for i, case in enumerate(cases)}
    roles = {HEVM: ('reference', 'independent mnemonic-by-offset verification'),
             KEVM: ('reference', 'fork activation and formal instruction encoding'),
             WHATSABI: ('executable', 'instruction boundaries, mnemonics and stack delta'),
             REVM: ('executable', 'instruction immediates, stack requirements and basic-block transfer')}
    return {repo: {'revision': UPSTREAM[repo][1], 'role': role, 'operation': operation,
                   'source_files': UPSTREAM[repo][2], 'input_sha256': CAPTURE_SHA, 'runtime_binaries_sha256': TOOLS,
                   'results': results, 'solc_oracle_sha256': sha(canonical(oracle)),
                   'checks': ['independent solc opcode/operand map', 'truncated immediate rejected',
                              'PUSH data boundary preserved', 'Berlin PUSH0 gate closed']}
            for repo, (role, operation) in roles.items()}
