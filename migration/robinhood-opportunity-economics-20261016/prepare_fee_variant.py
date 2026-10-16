#!/usr/bin/env python3
"""Prepare a historical, read-only experiment using the PUBLIC 0x1234 test key.

No endpoint, deployment, real key, or broadcast method. Only the maxFee field
changes; the original gas limits, calldata and hypothetical funding stay fixed.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'robinhood-real-state-replay-20261016'
sys.path.insert(0, str(PREVIOUS))
from nqc_local_cycle import decode_op, OPTYPE, KEY
from audit_result import EP, USEROP, ordered_logs

CAST_SHA = 'ccd95a4607ca3ebfcb88bb90e7235cdb7f0564f5f1afa17478d5fccabbb222cb'


def unpack_handle_ops(data):
    raw = bytes.fromhex(data[2:])
    if raw[:4].hex() != '765e827f':
        raise ValueError('expected v0.7 handleOps')
    args = raw[4:]
    offset = int.from_bytes(args[:32], 'big')
    beneficiary = '0x' + args[44:64].hex()
    array = args[offset:]
    if int.from_bytes(array[:32], 'big') != 1:
        raise ValueError('exactly one fixture operation required')
    start = 32 + int.from_bytes(array[32:64], 'big')
    fields = decode_op('0x' + (32).to_bytes(32, 'big').hex() + array[start:].hex())
    return fields, beneficiary


def limits(fields):
    account = int(fields[4], 16)
    fees = int(fields[6], 16)
    pm = bytes.fromhex(fields[7][2:])
    if len(pm) != 52:
        raise ValueError('expected original fixture paymaster')
    values = dict(verification=account >> 128, call=account % 2**128,
                  paymaster_verification=int.from_bytes(pm[20:36], 'big'),
                  paymaster_postop=int.from_bytes(pm[36:52], 'big'),
                  pre_verification=int(fields[5]))
    return dict(gas_limits=values, max_fee_wei=fees % 2**128,
                priority_fee_wei=fees >> 128,
                required_prefund_wei=sum(values.values()) * (fees % 2**128))


def prepare(cast_path):
    if hashlib.sha256(cast_path.read_bytes()).hexdigest() != CAST_SHA:
        raise ValueError('unrecognized pinned cast binary')
    def cast(*args):
        return subprocess.check_output([str(cast_path), *args], text=True, timeout=15).strip()
    def op_hash(fields):
        packed = cast('abi-encode', 'f(address,uint256,bytes32,bytes32,bytes32,uint256,bytes32,bytes32)',
                      fields[0], fields[1], cast('keccak', fields[2]), cast('keccak', fields[3]),
                      fields[4], fields[5], fields[6], cast('keccak', fields[7]))
        return cast('keccak', cast('abi-encode', 'f(bytes32,address,uint256)', cast('keccak', packed), EP, '4663'))
    source = json.loads((PREVIOUS / 'evidence/final-simulation-input.json').read_text())
    fields, beneficiary = unpack_handle_ops(source['transaction']['data'])
    original = cast('calldata', 'handleOps(' + OPTYPE + '[],address)', '[(' + ','.join(fields) + ')]', beneficiary)
    if original.lower() != source['transaction']['data'].lower():
        raise ValueError('ABI round-trip mismatch')
    trace = json.loads((PREVIOUS / 'evidence/nitro-phase5/01-nqc-plain-eoa-success.json').read_text())['result']
    event = next(x for x in ordered_logs(trace) if x['topics'][0] == USEROP)
    original_hash = op_hash(fields)
    if original_hash.lower() != event['topics'][1].lower():
        raise ValueError('operation hash not calibrated')
    old = limits(fields)
    block = json.loads((PREVIOUS / 'evidence/provider-capture/05-block.json').read_text())['result']
    base = int(block['baseFeePerGas'], 16)
    # Illustrative 50% base fee headroom, retaining the original priority fee.
    cap = (base * 3 + 1) // 2 + old['priority_fee_wei']
    fields[6] = '0x' + ((old['priority_fee_wei'] << 128) | cap).to_bytes(32, 'big').hex()
    new_hash = op_hash(fields)
    fields[8] = cast('wallet', 'sign', '--private-key', KEY, new_hash)
    data = copy.deepcopy(source)
    data['transaction']['data'] = cast('calldata', 'handleOps(' + OPTYPE + '[],address)', '[(' + ','.join(fields) + ')]', beneficiary)
    config = {'tracer': 'callTracer', 'tracerConfig': {'withLog': True}, 'timeout': '10s', 'reexec': 0,
              'txIndex': '0x1', 'stateOverrides': data['state_overrides']}
    plan = [{'label': 'lower-fee-cap-at-index', 'method': 'debug_traceCall',
             'params': [data['transaction'], {'blockHash': block['hash'], 'requireCanonical': True}, config]}]
    return data, plan, {'original': old, 'variant': limits(fields), 'original_userop_hash': original_hash,
                        'variant_userop_hash': new_hash, 'base_fee_wei': base,
                        'test_key_only': True, 'production_fee_quote': False,
                        'changed_fields': ['maxFeePerGas', 'fixture_signature']}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--cast', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    data, plan, report = prepare(args.cast)
    args.out.mkdir(parents=True, exist_ok=False)
    for name, obj in [('simulation-input.json', data), ('plan.json', plan), ('report.json', report)]:
        (args.out / name).write_text(json.dumps(obj, indent=2) + '\n')
    print(json.dumps(report, indent=2))
