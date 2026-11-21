"""Execute fixed own Slither controls through a pinned crytic-compile environment."""
import hashlib
from importlib.metadata import distributions
import json
import os
from pathlib import Path
import resource
import sys


def main():
    root = Path.cwd()
    pins = json.loads((root/'packages.json').read_bytes())['packages']
    paths = [str(root/'packages'/row['directory']) for row in pins]
    sys.path[:0] = [str(Path(__file__).resolve().parent.parent), *paths]
    from superhunter.owned_slither_cases import SOURCES, SOURCE_PINS, fixture_provenance
    from superhunter.product_slither_native_network import install
    fixture_provenance()
    network = install(root/'libseccomp.so.2')  # No scanner import before socket denial.
    resource.setrlimit(resource.RLIMIT_CPU, (35, 35))
    resource.setrlimit(resource.RLIMIT_AS, (2*1024**3, 2*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))
    resource.setrlimit(resource.RLIMIT_NOFILE, (96, 96))
    expected = sorted((row['name'].lower().replace('_', '-'), row['version']) for row in pins)
    actual = sorted((d.metadata['Name'].lower().replace('_', '-'), d.version)
                    for d in distributions())
    if actual != expected:
        raise ValueError('visible Slither distribution index differs')
    from crytic_compile import CryticCompile
    from slither.slither import Slither
    from slither.detectors.statements.tx_origin import TxOrigin
    result = {}
    for name in sorted(SOURCES):
        os.chdir(root/name)
        if hashlib.sha256(Path('Owned.sol').read_bytes()).hexdigest() != SOURCE_PINS[name]:
            raise ValueError('owned Slither source differs')
        compiled = CryticCompile('Owned.sol', solc=str(root/'solc'),
                                compile_force_framework='solc',
                                solc_args='--metadata-hash none --evm-version cancun')
        compilations = list(compiled.compilation_units.values())
        if len(compilations) != 1 or len(compilations[0].source_units) != 1:
            raise ValueError('unexpected owned compilation units')
        unit = next(iter(compilations[0].source_units.values()))
        slither = Slither(compiled, disallow_partial=True)
        slither.register_detector(TxOrigin)
        findings = slither.run_detectors()
        if len(findings) != 1:
            raise ValueError('unexpected detector execution coverage')
        result[name] = {'abis': unit.abis, 'runtimes': unit.bytecodes_runtime,
                        'inits': unit.bytecodes_init, 'ast': unit.ast,
                        'detectors': findings[0]}
        if Path('Owned.sol').read_bytes() != SOURCES[name]:
            raise ValueError('owned Slither source changed during execution')
    print(json.dumps({'cases': result, 'network': network}, sort_keys=True))


if __name__ == '__main__':
    main()
