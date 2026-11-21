"""Compare EVMole and WhatsABI runtime surfaces with solc on fixed owned NQC source."""
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
from zipfile import ZipFile

from .product_census_header import pinned
from .product_notice_ranking import ISOLATE
from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .product_solidity_headers import inputs, SOLC_SHA
from .safe_io import canonical, read_artifact, strict_json

REPOSITORIES = {'cdump/evmole': 'executable', 'shazow/whatsabi': 'executable'}
SCOPES = {
    'cdump/evmole': 'Recover runtime function selectors and record uncertain argument/mutability inference on owned NQC contracts.',
    'shazow/whatsabi': 'Recover runtime function selectors and ABI-like surfaces without any RPC or signature lookup.',
}
EVMOLE_REVISION = '763f2984f6be5ea33636336e804022c75318a260'
WHATSABI_REVISION = 'eefa62383640b9056aade49d1d5ed2206ffcdb3b'
WHEEL = 'evmole-0.10.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl'
WHEEL_SHA = '6624a8eb39010ea3cffeb34d1a02452bf019bc2932ce158b23a3e267704e5ea6'
NODE_SHA = 'acbe4b8d9153b841ed0697cbfc4f93e767386620edb745ab9358306c0a6f31aa'
PINS = 'superhunter/product_supply/evm-native-npm-pins.json'
PINS_SHA = '2a4a395aed7b810b4e058cac30dbce7e20bb62979d7ad90b23199403ca9d68e5'
SOURCES = {
    'aave': ('ci/nqc-protocol-fork/recovered-source/contracts/src/NqcAaveV3Executor.sol', 'NqcAaveV3Executor'),
    'backrun': ('ci/nqc-protocol-fork/reimplementation/nqc-v2-backrun-executor/contracts/src/NqcV2BackrunExecutor.sol', 'NqcV2BackrunExecutor'),
}
CASE_NAMES = {'aave', 'backrun', 'changed', 'stop', 'decoy'}


def source_inputs():
    original, _ = inputs()
    sources = {name+'.sol': {'content': original[path]} for name, (path, _) in SOURCES.items()}
    target = 'function execute(ExecutionPlan calldata plan)'
    if sources['backrun.sol']['content'].count(target) != 1:
        raise EvidenceError('owned interface mutation target is ambiguous')
    sources['changed.sol'] = {'content': sources['backrun.sol']['content'].replace(
        target, 'function reviewedExecute(ExecutionPlan calldata plan)')}
    return sources


def abi_type(row):
    if row['type'].startswith('tuple'):
        return '(' + ','.join(abi_type(c) for c in row['components']) + ')' + row['type'][5:]
    return row['type']


def compiler_cases(compiled, sources):
    if any(row.get('severity') == 'error' for row in compiled.get('errors', [])):
        raise EvidenceError('owned bytecode compilation failed')
    cases = {}
    for name in ('aave', 'backrun', 'changed'):
        contract = SOURCES['backrun' if name == 'changed' else name][1]
        try:
            row = compiled['contracts'][name+'.sol'][contract]
            code, methods = row['evm']['deployedBytecode']['object'], row['evm']['methodIdentifiers']
            abi = {}
            for fn in row['abi']:
                if fn['type'] == 'function':
                    arguments = ','.join(abi_type(arg) for arg in fn['inputs'])
                    signature = fn['name'] + '(' + arguments + ')'
                    abi[signature] = {'arguments': arguments, 'state_mutability': fn['stateMutability']}
            if (set(abi) != set(methods) or not code or len(code) > 131072 or
                    not re.fullmatch(r'(?:[0-9a-f]{2})+', code) or
                    len(set(methods.values())) != len(methods) or
                    any(not re.fullmatch(r'[0-9a-f]{8}', s) for s in methods.values())):
                raise EvidenceError('invalid compiled runtime surface')
        except (KeyError, TypeError) as exc:
            raise EvidenceError('incomplete compiled runtime surface') from exc
        cases[name] = {'code': code, 'methods': methods, 'abi': abi, 'contract': contract,
                       'source_sha256': sha(sources[name+'.sol']['content'].encode())}
    for name, code in [('stop', '00'), ('decoy', '63deadbeef5000')]:
        cases[name] = {'code': code, 'methods': {}, 'abi': {}, 'contract': None, 'source_sha256': None}
    return cases


def compare(cases, evmole, whatsabi):
    if set(cases) != CASE_NAMES or set(evmole) != CASE_NAMES or set(whatsabi) != CASE_NAMES:
        raise EvidenceError('incomplete bytecode controls')
    result = {}
    for name, case in cases.items():
        expected = sorted(case['methods'].values())
        inferred = evmole[name]
        if (not isinstance(inferred, list) or any(not isinstance(row, dict) for row in inferred) or
                sorted(row.get('selector', '') for row in inferred) != expected):
            raise EvidenceError('EVMole surface disagrees with compiler')
        observed = whatsabi[name]
        if not isinstance(observed, dict):
            raise EvidenceError('invalid WhatsABI report')
        for key in ('selectors', 'abi_selectors'):
            if sorted(observed.get(key, [])) != ['0x'+s for s in expected]:
                raise EvidenceError('WhatsABI surface disagrees with compiler')
        by_selector = {selector: case['abi'][sig] for sig, selector in case['methods'].items()}
        differences = []
        for row in inferred:
            offset = row.get('offset')
            if (row.get('dispatch') != 'abi' or type(offset) is not int or
                    not 0 <= offset < len(case['code'])//2 or
                    any(not isinstance(row.get(k), (str, type(None))) for k in ('arguments', 'state_mutability'))):
                raise EvidenceError('invalid EVMole function observation')
            for field in ('arguments', 'state_mutability'):
                expected_value = by_selector[row['selector']][field]
                if row[field] != expected_value:
                    differences.append({'selector': row['selector'], 'field': field,
                                        'declared': expected_value, 'inferred': row[field]})
        result[name] = {'contract': case['contract'], 'source_sha256': case['source_sha256'],
                        'runtime_sha256': sha(bytes.fromhex(case['code'])), 'runtime_bytes': len(case['code'])//2,
                        'compiler_methods': case['methods'], 'selectors': expected,
                        'evmole_functions': sorted(inferred, key=lambda r: r['selector']),
                        'whatsabi_selectors': sorted(observed['selectors']),
                        'inference_differences': differences}
    old, new = set(result['backrun']['selectors']), set(result['changed']['selectors'])
    if old-new != {'e4befb51'} or new-old != {'8e812b17'} or len(old & new) != 4:
        raise EvidenceError('owned interface mutation was not recovered exactly')
    if result['stop']['selectors'] or result['decoy']['selectors']:
        raise EvidenceError('negative bytecode control produced selectors')
    return {'cases': result, 'interface_change': {'removed': sorted(old-new), 'added': sorted(new-old),
             'unchanged': sorted(old & new)}, 'interpretation': 'Selector recovery is checked against compiled owned ABI. Inferred argument and mutability differences remain uncertainty, not confirmed vulnerabilities.'}


def stage(kit, work):
    copy_release('solc', kit/'solc', work/'solc', SOLC_SHA)
    copy_release('Node', kit/'node', work/'node', NODE_SHA)
    copy_release('EVMole', kit/WHEEL, work/WHEEL, WHEEL_SHA, executable=False)
    with ZipFile(work/WHEEL) as wheel:
        wheel.extractall(work/'evmole')
    pins = strict_json(pinned(ROOT, PINS, PINS_SHA))['packages']
    for index, row in enumerate(pins):
        archive = work/f'package-{index}.tgz'
        copy_release(row['path'], kit/row['filename'], archive, row['sha256'], executable=False)
        folder = work/f'extract-{index}'
        folder.mkdir()
        with tarfile.open(archive, 'r:gz') as package:
            package.extractall(folder, filter='data')
        dest = work/row['path']
        dest.parent.mkdir(parents=True, exist_ok=True)
        (folder/'package').rename(dest)
    runner = read_artifact(ROOT, 'superhunter/product_supply/evm-native-whatsabi.txt')
    (work/'whatsabi.cjs').write_bytes(runner)
    return pins


def run(kit):
    if sys.version_info[:2] != (3, 12):
        raise EvidenceError('EVM native kit requires CPython 3.12')
    sources = source_inputs()
    with tempfile.TemporaryDirectory(prefix='nqc-evm-native-') as tmp:
        work = Path(tmp)
        pins = stage(Path(kit), work)
        env = {'HOME': tmp, 'TMPDIR': tmp, 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}
        def execute(command, payload):
            proc = subprocess.run([*ISOLATE, *command], input=canonical(payload), cwd=work,
                                  env=env, capture_output=True, timeout=120, check=True)
            return strict_json(proc.stdout)
        compiled = execute([work/'solc', '--no-import-callback', '--standard-json'], {
            'language': 'Solidity', 'sources': sources, 'settings': {
                'optimizer': {'enabled': True, 'runs': 200}, 'viaIR': True, 'evmVersion': 'paris',
                'metadata': {'bytecodeHash': 'none'},
                'outputSelection': {'*': {'*': ['abi', 'evm.deployedBytecode.object', 'evm.methodIdentifiers']}}}})
        cases = compiler_cases(compiled, sources)
        payload = {name: row['code'] for name, row in cases.items()}
        evmole = execute([sys.executable, '-I', '-B', '-S', Path(__file__).with_name('product_evm_native_worker.py')], payload)
        whatsabi = execute([work/'node', work/'whatsabi.cjs'], payload)
        report = compare(cases, evmole, whatsabi)
    report['tools'] = {
        'cdump/evmole': {'version': '0.10.1', 'wheel_sha256': WHEEL_SHA, 'catalog_revision': EVMOLE_REVISION,
                          'scope': SCOPES['cdump/evmole'], 'executed_form': 'official PyPI binary wheel',
                          'binary_rebuilt_from_catalog_revision': False},
        'shazow/whatsabi': {'version': '0.30.0', 'catalog_revision': WHATSABI_REVISION,
                            'package_sha256': next(row['sha256'] for row in pins if row['path'] == 'node_modules/@shazow/whatsabi'),
                            'npm_lock_sha256': PINS_SHA, 'pinned_runtime_packages': len(pins),
                            'scope': SCOPES['shazow/whatsabi'], 'executed_form': 'official npm JavaScript package',
                            'typescript_source_files_matching_catalog': 34},
        'solc': {'version': '0.8.24', 'binary_sha256': SOLC_SHA},
        'node': {'version': '24.22.3', 'binary_sha256': NODE_SHA},
    }
    return report
