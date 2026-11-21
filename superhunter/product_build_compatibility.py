"""Compare storage and callable interfaces of fixed NQC compiler outputs with four source projects."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from zipfile import ZipFile

from .product_evm_standards_batch import CAPTURE_SHA, SOLC_SHA, capture, run, runtime_path
from .product_notice_ranking import install_wheels
from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .product_sources import git
from .safe_io import canonical, read_artifact, strict_json

CRYTIC = 'crytic/crytic-compile'
OZ = 'OpenZeppelin/openzeppelin-upgrades'
HH = 'NomicFoundation/hardhat'
PROPS = 'crytic/properties'
WETH = 'ci/nqc-census/weth-physical/test/NqcRmc011WethPhysicalCompatibilityFork.t.sol'
SUPPLY = 'superhunter/product_supply/'
LOCK = SUPPLY+'compile-abi-linux-py312.txt'

LOCK_SHA = 'e3a96133c021014f5d62797e223d908b2b8210c4f6858d9a76eee81c5758f1e0'
WETH_SHA = '3feb5782549ea38ed705cc48531c0c5be5e3abc52dcd942658f7eb538a67d276'
UPSTREAM = {
    'crytic/properties': ('018-properties', '5ea14b813ff296e24b4257ab52a0402360f916f6', {
        'contracts/util/IERC20.sol': 'eecb1f4284f5e51c09fcf9e35d3fc03d853bcdd7cdd30bcc599ae121460a43a2',
    }),
    'OpenZeppelin/openzeppelin-upgrades': ('040-openzeppelin-upgrades', '54bb8bb913c2d52f417d3bcf1ef94e9061b89da8', {
        'packages/core/src/storage/layout.ts': '8c2c8ad2805e5a0a859da1ee3f7013bf1928284ea1ec565d4532c5ade77de851',
        'packages/core/src/storage/compare.ts': '6f35c74957f6c022fdecbd4e44db9a6521930645aec125b20c5941f1af9c0e91',
    }),
    'NomicFoundation/hardhat': ('171-hardhat', 'c6a0b31a8bcbb839aa2051f700476e2019e5529d', {
        'packages/hardhat/src/internal/builtin-plugins/solidity/build-system/artifacts.ts': '476e4b4d7adae5da639753e493b2f98c4bc392fb32f12039790ae87cf712d74f',
        'packages/hardhat-utils/src/hex.ts': '55b8c9a4084c1117ca10aa7fb7792fc4befe8042b045944031081994ce13a249',
    }),
    'crytic/crytic-compile': ('178-crytic-compile', '7e8a89ddd7718d387b0c7b4e43a7391e1a6d79f3', {
        'crytic_compile/source_unit.py': '0a683c6c3e3f1ae279bb7a0469b803fe74bc9904b5a34ec5b7df1bdfced4dc9f',
        'pyproject.toml': '9ec841f278e7c264191bf1be301807c51aec3964f53c3472eb9269dd25e62964',
    }),
}

def need(ok, why):
    if not ok:
        raise EvidenceError('NQC ABI/storage compatibility: ' + why)


def material(root):
    docs = {}
    for repo, (dirname, rev, paths) in UPSTREAM.items():
        path = Path(root)/dirname
        need(git(path, 'rev-parse', 'HEAD').decode().strip() == rev, 'changed commit for ' + repo)
        for name, digest in paths.items():
            raw = read_artifact(path, name)
            need(sha(raw) == digest, 'changed source at ' + name)
            docs[name] = raw.decode()
    return docs


def source_wheel(root, wheels):
    dirname, rev, _ = UPSTREAM[CRYTIC]
    tree = git(Path(root)/dirname, 'ls-tree', '-rz', rev, '--', 'crytic_compile')
    actual = {}
    for line in tree.decode().split('\0'):
        if line.endswith('.py'):
            meta, path = line.split('\t')
            actual[path] = meta.split()[2]
    wheel, = wheels.glob('crytic_compile-*.whl')
    need(sha(wheel.read_bytes()) == '18025359f0f615fac0ff10c706933860fdac12b5edd534ff6a47346a44ff9024',
         'unreviewed Crytic wheel')
    with ZipFile(wheel) as source:
        names = {p for p in source.namelist() if p.startswith('crytic_compile/') and p.endswith('.py')}
        need(set(actual) == names and len(names) == 41, 'Python source inventory mismatch')
        for path in names:
            raw = source.read(path)
            digest = hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()
            need(digest == actual[path], 'wheel and source Git tree differ')
    return len(names)


def ts_function(source, name):
    result = re.search(r'^export function '+name+r'\([\s\S]*?^\}', source, re.M)
    need(result is not None, 'upstream function missing: ' + name)
    return result[0]


def emit_libraries(docs, work):
    layout, compare = [docs[k] for k in UPSTREAM[OZ][2]]
    ranges = [ts_function(compare, 'storageFieldBegin'), ts_function(compare, 'storageFieldEnd'),
              ts_function(layout, 'hasLayout')]
    method = re.search(r'^  getLayoutChange\([\s\S]*?^  \}', compare, re.M)
    need(method is not None, 'upstream layout comparator missing')
    (work/'ranges.mts').write_text('\n'.join(ranges) + '\nexport class WidthComparison {\n' + method[0] + '\n}')
    artifact, hexutil = [docs[k] for k in UPSTREAM[HH][2]]
    (work/'hardhat.mts').write_text('\n'.join((ts_function(hexutil, 'isPrefixedHexString'),
        ts_function(hexutil, 'getPrefixedHexString'), ts_function(artifact, 'getContractArtifact'))))
    (work/'layout.mjs').write_bytes(read_artifact(ROOT, SUPPLY+'compile-layout-worker.mjs.txt'))


def recipe(sources):
    return {'language': 'Solidity', 'sources': {name: {'content': value} for name, value in sources.items()},
            'settings': {'evmVersion': 'cancun', 'optimizer': {'enabled': False},
                         'outputSelection': {'*': {'': ['ast'], '*': ['abi', 'storageLayout', 'evm.bytecode',
                            'evm.deployedBytecode', 'evm.methodIdentifiers', 'userdoc', 'devdoc']}}}}


def compare_fields(rows, compiled):
    # The independent calculator uses solc's AST order and primitive integer
    # widths, then Solidity's 32-byte slot packing. This profile accepts uints only.
    state = compiled['sources']['State.sol']['ast']['nodes'][-1]
    added, byte = [], 0
    for field in state['nodes']:
        if field['nodeType'] != 'VariableDeclaration' or not field['stateVariable']:
            continue
        name = field['typeDescriptions']['typeString']
        m = re.fullmatch(r'uint(8|16|32|64|128|256)', name)
        need(m, 'unsupported field type')
        width = int(m[1])//8
        if byte % 32 + width > 32:
            byte += 32-byte % 32
        added.append({'label': field['name'], 'type': name, 'begin': byte, 'end': byte+width})
        byte += width
    need(rows == added, 'storage ranges disagree with independently packed AST')


def interfaces(one, two):
    def index(contract):
        result = {}
        for fn in contract['abi']:
            if fn['type'] != 'function':
                continue
            sig = fn['name']+'('+','.join(v['type'] for v in fn['inputs'])+')'
            result[sig] = ([o['type'] for o in fn['outputs']], fn['stateMutability'])
        return result
    ref, owned = index(one), index(two)
    need(set(ref) <= set(owned) and all(ref[k][0] == owned[k][0] for k in ref), 'reference ABI unavailable')
    return {'shared_signatures': sorted(ref), 'owned_only': sorted(owned.keys()-ref.keys()),
            'mutability_differences': {k: {'reference': ref[k][1], 'owned': owned[k][1]}
                                       for k in sorted(ref) if ref[k][1] != owned[k][1]}}


def review(source_root):
    docs = material(source_root)
    history = capture()
    source = history['conservation']['input']['sources']['State.sol']['content']
    old = ' uint16 private debit = 15;\n uint16 private credit = 0;'
    need(old in source, 'control declaration changed')
    variants = {k: v['input']['sources']['State.sol']['content'] for k,v in history.items()}
    variants['append'] = source.replace(' uint8 private steps = 0;', ' uint8 private steps = 0;\n uint32 private note;')
    variants['reorder'] = source.replace(old, ' uint16 private credit = 0;\n uint16 private debit = 15;')
    variants['retype'] = source.replace('uint8 private steps', 'uint16 private steps')
    cases = {k: recipe({'State.sol': v}) for k,v in variants.items()}
    weth = read_artifact(ROOT, WETH)
    need(sha(weth) == WETH_SHA, 'owned interface changed')
    interface = re.search(rb'^interface IMainnetWeth \{[\s\S]*?^\}', weth, re.M)[0].decode()
    cases['interfaces'] = recipe({'Reference.sol': docs['contracts/util/IERC20.sol'],
                                  'Owned.sol': '// SPDX-License-Identifier: MIT\npragma solidity ^0.8.24;\n'+interface})
    kit = Path(os.environ.get('NQC_BUILD_KIT', '/no-build-kit'))
    with tempfile.TemporaryDirectory(prefix='nqc-build-shapes-') as tmp:
        work = Path(tmp)
        copy_release('solc', kit/'solc', work/'solc', SOLC_SHA)
        env = {'HOME': tmp, 'TMPDIR': tmp, 'PATH': os.defpath, 'LANG': 'C'}
        prepared = kit/'compile-lib.zip'
        if prepared.exists():
            cache = work/'compile-lib.zip'
            copy_release('Crytic package cache', prepared, cache,
                         'b0e65cc9be5c323b7991021a66b8b066dee45e55763dbd80d4b6b163911cc205', executable=False)
            with ZipFile(cache) as packages:
                packages.extractall(work/'lib')  # Exact archive built from the ten reviewed wheel hashes.
        else:
            install_wheels(kit, work, env, lock_path=LOCK, lock_digest=LOCK_SHA, producer='Crytic Compile')
        count = source_wheel(source_root, kit)
        (work/'worker.py').write_bytes(read_artifact(ROOT, SUPPLY+'compile-abi-worker.py'))
        ids = strict_json(run(sys.executable, ['-I', '-S', '-B', 'worker.py'], work, canonical(cases)))
        compiled = {k: strict_json(run(work/'solc', ['--standard-json'], work, canonical(v))) for k,v in cases.items()}
        states = {}
        for case, output in compiled.items():
            need('contracts' in output, 'failed compilation for '+case)
            for group in output['contracts'].values():
                for name, contract in group.items():
                    need(ids[case][name] == contract['evm']['methodIdentifiers'], 'native selector disagreement')
            if case in history:
                old_contract = strict_json(history[case]['output_utf8'])['contracts']['State.sol']['StatefulConservation']
                current = output['contracts']['State.sol']['StatefulConservation']
                need(all(current[k] == old_contract[k] for k in ('abi', 'storageLayout'))
                     and all(current['evm'][k]['object'] == old_contract['evm'][k]['object']
                             for k in ('bytecode', 'deployedBytecode')), 'historical artifact was not reproduced')
            if case != 'interfaces':
                states[case] = {'contract': output['contracts']['State.sol']['StatefulConservation'],
                                'inputHash': sha(canonical(cases[case]))}
        emit_libraries(docs, work)
        # Canonical JSON sorts object keys. Keep the baseline first for the native comparator.
        artifacts = strict_json(run(runtime_path('node'), ['--permission', '--allow-fs-read='+tmp,
            '--disable-warning=ExperimentalWarning', 'layout.mjs'], work, json.dumps(states).encode()))
    checked = {}
    for case, observed in artifacts.items():
        contract = states[case]['contract']
        item = observed['artifact']
        need(item['_format'] == 'hh3-artifact-1' and item['abi'] == contract['abi']
             and item['buildInfoId'] == states[case]['inputHash'] and item['inputSourceName'] == 'State.sol'
             and item['sourceName'] == 'State.sol' and item['contractName'] == 'StatefulConservation'
             and item['linkReferences'] == item['deployedLinkReferences'] == item['immutableReferences'] == {}
             and item['bytecode'] == '0x'+contract['evm']['bytecode']['object']
             and item['deployedBytecode'] == '0x'+contract['evm']['deployedBytecode']['object'],
             'Hardhat artifact differs from compiler')
        compare_fields(observed['fields'], compiled[case])
        base = {r['label']: r for r in artifacts['conservation']['fields']}
        now = {r['label']: r for r in observed['fields']}
        expected = sorted(k for k in base if now.get(k) != base[k])
        need(sorted(observed['changed']) == expected, 'OpenZeppelin comparator disagrees')
        checked[case] = {'layout': observed['fields'], 'changed_existing_fields': expected,
                         'preserves_existing_fields': not expected, 'artifact_sha256': sha(canonical(item)),
                         'compiler_selectors': ids[case]['StatefulConservation']}
    need(all(checked[k]['preserves_existing_fields'] for k in ('conservation','delayed_credit','unreachable','append'))
         and checked['reorder']['changed_existing_fields'] == ['credit','debit']
         and checked['retype']['changed_existing_fields'] == ['steps'], 'compatibility controls')
    contracts = compiled['interfaces']['contracts']
    comparison = interfaces(contracts['Reference.sol']['IERC20'], contracts['Owned.sol']['IMainnetWeth'])
    need(len(comparison['shared_signatures']) == 7 and comparison['mutability_differences'] ==
         {'decimals()': {'reference': 'nonpayable', 'owned': 'view'}}, 'frozen interface comparison')
    roles = {CRYTIC: ('executable', 'standard-json recompile and native ABI selector extraction'),
             HH: ('executable', 'native Hardhat artifact assembly for six real compiler outputs'),
             OZ: ('executable', 'native storage position and width comparator for packed fields'),
             PROPS: ('reference', 'compile and compare IERC20 reference to the historical NQC WETH interface')}
    return {repo: {'revision': UPSTREAM[repo][1], 'role': role, 'operation': op, 'source_files': UPSTREAM[repo][2],
                   'input_sha256': CAPTURE_SHA, 'owned_interface_sha256': WETH_SHA, 'results': checked,
                   'interface_comparison': comparison, 'reference_selectors': ids['interfaces']['IERC20'],
                   'source_matched_python_modules': count, 'wheel_lock_sha256': LOCK_SHA}
            for repo,(role,op) in roles.items()}
