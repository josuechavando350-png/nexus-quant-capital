"""Closed OWNED corpus: six known quota-ledger source variants, no targets."""
from __future__ import annotations

from . import evm_execution as evm, native_compile as compiler
from .safe_io import canonical, strict_json
import hashlib
import re

SOURCE_FILE, CONTRACT = 'OwnedQuota.sol', 'OwnedQuota'
VARIANTS = ('correct', 'reconciled', 'quota_not_charged', 'strict_boundary',
            'double_debit', 'extra_credit')
CODEGEN = ('legacy', 'ir_optimized')
INITIAL = {'remaining':20, 'distributed':0, 'quota':5}
SEQUENCES = (
    ((0,evm.GAS),(1,evm.GAS),(4,evm.GAS),(0,evm.GAS),(1,evm.GAS)),
    ((5,evm.GAS),(1,evm.GAS)),
    ((6,evm.GAS),(255,evm.GAS),(2,evm.GAS)),
    ((2,evm.GAS),(2,evm.GAS),(2,evm.GAS)),
    ((3,1),(3,evm.GAS),(2,evm.GAS)),
    ((4,evm.GAS),(1,evm.GAS),(0,evm.GAS)),
)
STORAGE = [('remaining','0',0,'uint16'), ('distributed','0',2,'uint16'),
           ('quota','0',4,'uint16')]


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def owned_source(variant: str) -> str:
    need(type(variant) is str and variant in VARIANTS, 'QUOTA_VARIANT')
    header = '''// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;
contract OwnedQuota {
    uint16 public remaining = 20;
    uint16 public distributed;
    uint16 public quota = 5;
    function release(uint8 amount) external {
'''
    if variant == 'reconciled':
        body = '''        require(uint256(distributed) + amount <= 5);
        require(uint256(distributed) + amount <= 20);
        distributed += amount;
        remaining = 20 - distributed;
        quota = 5 - distributed;
'''
    else:
        guard = '<' if variant == 'strict_boundary' else '<='
        body = f'        require(amount {guard} quota);\n        require(amount <= remaining);\n'
        if variant != 'quota_not_charged':
            body += '        quota -= amount;\n'
        debit = 'uint16(amount) * 2' if variant == 'double_debit' else 'amount'
        credit = 'uint16(amount) + 1' if variant == 'extra_credit' else 'amount'
        body += f'        remaining -= {debit};\n        distributed += {credit};\n'
    return header + body + '    }\n}\n'


def compile_input(variant: str, codegen: str) -> dict:
    need(type(codegen) is str and codegen in CODEGEN, 'QUOTA_CODEGEN')
    settings = {'optimizer':{'enabled':codegen != 'legacy','runs':200},
                'evmVersion':'cancun','modelChecker':{'engine':'none'},
                'outputSelection':{'*':{'':['ast'],'*':['abi','storageLayout','evm.bytecode',
                                          'evm.deployedBytecode','evm.methodIdentifiers']}}}
    if codegen == 'ir_optimized':
        settings['viaIR'] = True
    return {'language':'Solidity','sources':{SOURCE_FILE:{'content':owned_source(variant)}},
            'settings':settings}


def compile_owned(image: bytes, variant: str, codegen: str) -> dict:
    inp = compile_input(variant,codegen)
    output,stderr = compiler._execute(image,'compile',canonical(inp))
    need(not stderr and compiler.classify_output(inp,output)['status'] ==
         'SOLC_COMPILATION_COMPLETED','QUOTA_COMPILATION')
    obj = strict_json(output)
    need(set(obj['contracts']) == {SOURCE_FILE} and
         set(obj['contracts'][SOURCE_FILE]) == {CONTRACT},'QUOTA_CONTRACT')
    contract = obj['contracts'][SOURCE_FILE][CONTRACT]
    layout = contract['storageLayout']
    need([(r['label'],r['slot'],r['offset'],layout['types'][r['type']]['label'])
          for r in layout['storage']] == STORAGE,'QUOTA_LAYOUT')
    methods = contract['evm']['methodIdentifiers']
    need(set(methods) == {'remaining()','distributed()','quota()','release(uint8)'} and
         all(type(v) is str and re.fullmatch('[0-9a-f]{8}',v) for v in methods.values()),
         'QUOTA_SELECTORS')
    birth = contract['evm']['bytecode']; runtime = contract['evm']['deployedBytecode']
    for item in (birth,runtime):
        need(type(item['object']) is str and len(item['object']) % 2 == 0 and
             re.fullmatch('[0-9a-f]+',item['object']) and not item['linkReferences'],
             'QUOTA_BYTECODE')
    need(not runtime['immutableReferences'],'QUOTA_IMMUTABLES')
    return {'contract':contract,'record':{'variant':variant,'codegen':codegen,
        'source_sha256':sha(owned_source(variant).encode()),'input_sha256':sha(canonical(inp)),
        'output_sha256':sha(output),'creation_sha256':sha(bytes.fromhex(birth['object'])),
        'runtime_sha256':sha(bytes.fromhex(runtime['object']))}}


def decode(alloc: dict, contract: dict) -> dict:
    need(type(alloc) is dict and evm.RECEIVER in alloc,'QUOTA_ACCOUNT')
    account = alloc[evm.RECEIVER]
    need(account['code'] == '0x'+contract['evm']['deployedBytecode']['object'],
         'QUOTA_RUNTIME')
    storage = account['storage']
    need(type(storage) is dict and set(storage) <= {evm.SLOT},'QUOTA_STORAGE_KEYS')
    word = int(storage.get(evm.SLOT,'0x0'),16)
    need(0 <= word < 2**48,'QUOTA_STORAGE_WORD')
    return {'remaining':word & 65535,'distributed':(word >> 16) & 65535,
            'quota':(word >> 32) & 65535}
