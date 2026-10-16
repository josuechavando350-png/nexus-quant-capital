#!/usr/bin/env python3
"""Rebuild/check the exact constructor bytecode with an already installed solc."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent


def build(solc):
    version = subprocess.check_output([solc, '--version'], text=True).strip()
    if '0.8.23+commit.f704f362' not in version:
        raise ValueError('PINNED_COMPILER_REQUIRED')
    source = (HERE / 'NqcStateReadLens.sol').read_bytes()
    settings = {'optimizer': {'enabled': True, 'runs': 200}, 'evmVersion': 'paris',
                'metadata': {'bytecodeHash': 'none', 'appendCBOR': False},
                'outputSelection': {'*': {'*': ['abi', 'evm.bytecode.object', 'evm.bytecode.opcodes']}}}
    payload = {'language': 'Solidity', 'sources': {'NqcStateReadLens.sol': {'content': source.decode()}}, 'settings': settings}
    result = json.loads(subprocess.check_output([solc, '--standard-json'], input=json.dumps(payload).encode()))
    if any(e['severity'] == 'error' for e in result.get('errors', [])):
        raise ValueError(result['errors'])
    contract = result['contracts']['NqcStateReadLens.sol']['NqcStateReadLens']
    bytecode = bytes.fromhex(contract['evm']['bytecode']['object'])
    return {'compiler': version, 'settings': settings, 'source_sha256': hashlib.sha256(source).hexdigest(),
            'creation_bytecode': '0x' + bytecode.hex(), 'creation_bytecode_sha256': hashlib.sha256(bytecode).hexdigest(),
            'creation_bytes': len(bytecode), 'abi': contract['abi']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--solc', required=True); parser.add_argument('--write', action='store_true')
    args = parser.parse_args(); artifact = build(args.solc); path = HERE / 'lens-build.json'
    if args.write: path.write_text(json.dumps(artifact, indent=2) + '\n')
    else:
        existing = json.loads(path.read_text())
        # The descriptive compiler banner may differ across distributions, but the pinned
        # version, source, settings, ABI and every byte of output must match.
        for key in artifact:
            if key != 'compiler' and existing.get(key) != artifact[key]: raise ValueError('BUILD_MISMATCH_' + key)
    print(json.dumps({'checked': not args.write, 'creation_bytes': artifact['creation_bytes'],
                      'creation_bytecode_sha256': artifact['creation_bytecode_sha256']}))
