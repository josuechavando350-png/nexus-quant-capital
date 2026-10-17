"""Reuse pinned compilers without writing any Directiva 003 file."""
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'morpho-sponsor-e2e-20261017'

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def main():
    original = load('previous_build', PREVIOUS / 'build_local.py')
    # Identical source text and compilation-unit name preserve metadata/bytecode.
    (HERE / 'LabSupport.sol').write_bytes((PREVIOUS / 'LabSupport.sol').read_bytes())
    original.HERE = HERE
    original.main()
    workspace = Path(sys.argv[sys.argv.index('--workspace') + 1])
    toolchain = Path(sys.argv[sys.argv.index('--toolchain') + 1])
    bundler = load('original_bundler_compiler', HERE.parent / 'morpho-sponsored-gas/compile_bundler_reference.py')
    bundler.__file__ = str(HERE / 'compile_bundler_reference.py')  # Only redirects its output folder.
    bundler.compile_reference(workspace / 'bundler3', toolchain / 'solc-0.8.28')
    artifacts = json.loads((HERE / 'build/artifacts.json').read_text())
    for name in ('Bundler3', 'EthereumGeneralAdapter1'):
        obj = json.loads((HERE / 'out-upstream' / (name + '.json')).read_text())
        artifacts[name] = {'abi': obj['abi'], 'bytecode': obj['bytecode']['object'],
                           'runtime_template': obj['deployedBytecode']['object']}
    # This inert constructor dependency is NOT a lending/AMM/flash implementation.
    # Lido and MORPHO-wrapper operations are outside the tested route.
    source = (HERE / 'ConstructorMetadataFixture.sol').read_text()
    std = {'language': 'Solidity', 'sources': {'ConstructorMetadataFixture.sol': {'content': source}},
           'settings': {'optimizer': {'enabled': True, 'runs': 200}, 'evmVersion': 'cancun',
                        'outputSelection': {'*': {'*': ['abi', 'evm.bytecode.object', 'evm.deployedBytecode.object']}}}}
    result = json.loads(subprocess.run([str(toolchain / 'solc-0.8.24'), '--standard-json'],
                        input=json.dumps(std), text=True, capture_output=True, check=True).stdout)
    assert not [e for e in result.get('errors', []) if e['severity'] == 'error']
    c = result['contracts']['ConstructorMetadataFixture.sol']['ConstructorMetadataFixture']
    artifacts['ConstructorMetadataFixture'] = {'abi': c['abi'], 'bytecode': '0x' + c['evm']['bytecode']['object'],
                            'runtime_template': '0x' + c['evm']['deployedBytecode']['object']}
    (HERE / 'build/artifacts.json').write_text(json.dumps(artifacts) + '\n')
    hashes = {k: hashlib.sha256(bytes.fromhex(v['bytecode'][2:])).hexdigest() for k, v in artifacts.items()}
    prior = json.loads((PREVIOUS / 'evidence/build-manifest.json').read_text())['bytecode_sha256']
    assert all(hashes[k] == v for k, v in prior.items()), 'C1 bytecode changed'
    report = {'bytecode_sha256': hashes, 'all_C1_creation_bytecodes_equal_corrected_003': True,
              'metadata_fixture_scope': 'constructor address getters only; not authentic Lido/wrapper compatibility',
              'input_sha256': {str(p.relative_to(HERE.parent)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (PREVIOUS / 'build_local.py', HERE.parent / 'morpho-sponsored-gas/compile_bundler_reference.py',
                            HERE / 'ConstructorMetadataFixture.sol')}}
    (HERE / 'evidence/bytecode-parity.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'parity': True, 'contracts': len(artifacts)}))

if __name__ == '__main__':
    main()
