"""Rebuild the independent solc instruction-map hashes for NQC's frozen controls."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile

from superhunter.product_evm_standards_batch import SOLC_SHA, capture, checked, run, runtime
from superhunter.product_review import sha
from superhunter.safe_io import canonical, strict_json


def instruction_map(disassembly, code):
    tokens = iter(disassembly.split())
    rows = []
    pc = 0
    while pc < len(code):
        name = next(tokens)
        length = re.fullmatch(r'PUSH(\d+)', name)
        width = int(length[1]) if length else 0
        operand = b''
        if width:
            scalar = next(tokens)
            checked(scalar.startswith('0x'), 'missing compiler operand')
            operand = int(scalar, 16).to_bytes(width, 'big')
            checked(code[pc+1:pc+1+width] == operand, 'compiler operand differs from runtime')
        rows.append([pc, name, operand.hex()])
        pc += 1 + width
    checked(pc == len(code), 'compiler disassembly crossed metadata boundary')
    return rows


def rebuild(solc):
    solc = Path(solc).resolve()
    with solc.open('rb') as stream:
        checked(hashlib.file_digest(stream, 'sha256').hexdigest() == SOLC_SHA, 'compiler pin differs')
    results = {}
    with tempfile.TemporaryDirectory(prefix='nqc-solc-layout-') as cwd:
        for name, case in capture().items():
            recipe = case['input']
            recipe['settings']['outputSelection']['*']['*'].append('evm.deployedBytecode.opcodes')
            compiled = strict_json(run(solc, ['--standard-json'], cwd, canonical(recipe)))
            actual = compiled['contracts']['State.sol']['StatefulConservation']['evm']['deployedBytecode']
            previous = strict_json(case['output_utf8'])['contracts']['State.sol']['StatefulConservation']
            checked(actual['object'] == previous['evm']['deployedBytecode']['object'], 'compiler bytecode changed')
            results[name] = sha(canonical(instruction_map(actual['opcodes'], runtime(case))))
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('solc', type=Path)
    print(json.dumps(rebuild(parser.parse_args().solc), indent=2, sort_keys=True))
