"""Compare two fixed NQC inputs against two pinned upstream type definitions."""
import ast
from pathlib import Path
import re
import tempfile

from .product_census_header import FIXTURE, FIXTURE_SHA, pinned
from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .product_solidity_headers import SOLC_SHA, inputs, run
from .safe_io import canonical, strict_json

CONSENSUS = '2d519bc04f0f9c52f0e0876f69b238a9523f1ef8'
OZ = '5172e1681f05f4aa189b7740bf2c0316af67c3b3'
DENEB = 'specs/deneb/beacon-chain.md'
PRESET = 'presets/mainnet/bellatrix.yaml'
DENEB_SHA = 'e20523b731123b61284c114ba8aa566aaffe58e4baf6b6cfe75c822ffeee18f5'
PRESET_SHA = 'ad30262a50a0781e711edba465911a67ebb9d1ad1b0a910e1d091af5a5283529'
IERC20 = 'contracts/token/ERC20/IERC20.sol'
IERC20_SHA = '01b6f5c4fa45fd38822b286ecef6daf983d27306dd6362496fa71b3e4600b72c'
WETH = 'ci/nqc-census/weth-physical/test/NqcRmc011WethPhysicalCompatibilityFork.t.sol'
ALIASES = {'parent_hash': 'parentHash', 'fee_recipient': 'miner', 'state_root': 'stateRoot',
           'receipts_root': 'receiptsRoot', 'logs_bloom': 'logsBloom', 'prev_randao': 'mixHash',
           'block_number': 'number', 'gas_limit': 'gasLimit', 'gas_used': 'gasUsed', 'timestamp': 'timestamp',
           'extra_data': 'extraData', 'base_fee_per_gas': 'baseFeePerGas', 'block_hash': 'hash',
           'blob_gas_used': 'blobGasUsed', 'excess_blob_gas': 'excessBlobGas'}


def payload_fields(markdown):
    block, = re.findall(r'(?ms)^```python\n(class ExecutionPayload\(Container\):\n.*?)^```', markdown)
    fields = {node.target.id: node.annotation.id for node in ast.parse(block).body[0].body
              if isinstance(node, ast.AnnAssign)}
    # The historical fixture records only roots for these two lists.
    if set(fields) != set(ALIASES) | {'transactions', 'withdrawals'}:
        raise EvidenceError('Deneb payload field inventory differs')
    return {name: fields[name] for name in ALIASES}


def invalid_fields(block, fields, bloom_bytes, max_extra):
    bad = []
    for name, kind in fields.items():
        key = ALIASES[name]
        value = block.get(key, '')
        if not isinstance(value, str) or not re.fullmatch(r'0x[0-9a-fA-F]*', value):
            bad.append(key)
            continue
        if kind in ('Uint64', 'Uint256'):
            valid = bool(re.fullmatch(r'0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)', value))
            valid = valid and int(value, 16).bit_length() <= int(kind[4:])
        else:
            size = {'Hash32': 32, 'Bytes32': 32, 'ExecutionAddress': 20,
                    'LogsBloom': bloom_bytes, 'ExtraData': max_extra}[kind]
            valid = len(value) % 2 == 0 and (len(value) <= 2 + size*2 if kind == 'ExtraData'
                                             else len(value) == 2 + size*2)
        if not valid:
            bad.append(key)
    return sorted(bad)


def consensus(root, header):
    if header is None or header['fixture_sha256'] != FIXTURE_SHA:
        raise EvidenceError('consensus reference requires the Census header receipt')
    spec = root/'upstream/189-consensus-specs'
    fields = payload_fields(pinned(spec, DENEB, DENEB_SHA).decode())
    preset = pinned(spec, PRESET, PRESET_SHA).decode()
    def constant(name):
        value, = re.findall(r'(?m)^' + name + r': ([0-9]+)$', preset)
        return int(value)
    limits = constant('BYTES_PER_LOGS_BLOOM'), constant('MAX_EXTRA_DATA_BYTES')
    original = strict_json(pinned(ROOT, FIXTURE, FIXTURE_SHA))['block']
    changed = {**original, 'gasUsed': hex(2**64), 'logsBloom': original['logsBloom'][:-2]}
    control = invalid_fields(changed, fields, *limits)
    if invalid_fields(original, fields, *limits) or control != ['gasUsed', 'logsBloom']:
        raise EvidenceError('Deneb type check disagrees with fixed controls')
    return {'revision': CONSENSUS, 'field_types': fields, 'preset_limits': list(limits),
            'spec_sha256': DENEB_SHA, 'preset_sha256': PRESET_SHA, 'fixture_sha256': FIXTURE_SHA,
            'header_report_sha256': sha(canonical(header)), 'rejected_fields_in_control': control}


def signatures(ast_root, interface):
    node, = [n for n in ast_root['nodes'] if n.get('contractKind') == 'interface' and n['name'] == interface]
    def types(parameters):
        return [p['typeName']['name'] for p in parameters['parameters']]
    return {n['name']: [types(n['parameters']), types(n['returnParameters']), n['stateMutability'], n['visibility']]
            for n in node['nodes'] if n['nodeType'] == 'FunctionDefinition'}


def oz_interface(root, kit):
    spec = pinned(root/'upstream/039-openzeppelin-contracts', IERC20, IERC20_SHA).decode()
    source = inputs()[0][WETH]
    # Limit the control to NQC's public interface declaration.
    start = source.index('interface IMainnetWeth {')
    end = source.index('}', start) + 1
    fragment = source[start:end]
    target = 'function balanceOf(address account) external view returns (uint256)'
    if fragment.count(target) != 1:
        raise EvidenceError('balanceOf declaration differs from the pinned NQC interface')
    altered = fragment.replace(target, target.replace('uint256', 'uint128'))
    sources = {'oz.sol': spec, 'owned.sol': source, 'control.sol': 'pragma solidity ^0.8.24;\n' + altered}
    with tempfile.TemporaryDirectory(prefix='nqc-ierc20-') as tmp:
        work = Path(tmp)
        copy_release('solc', kit/'solc', work/'solc', SOLC_SHA)
        result = run([work/'solc', '--no-import-callback', '--standard-json'], work, {'HOME': tmp},
                     {'language': 'Solidity', 'sources': {k: {'content': v} for k, v in sources.items()},
                      'settings': {'stopAfter': 'parsing', 'outputSelection': {'*': {'': ['ast']}}}})
    if any(err['severity'] == 'error' for err in result.get('errors', [])):
        raise EvidenceError('solc could not parse a pinned interface')
    def read(name, iface):
        return signatures(result['sources'][name]['ast'], iface)
    authority = read('oz.sol', 'IERC20')
    observed, control = read('owned.sol', 'IMainnetWeth'), read('control.sol', 'IMainnetWeth')
    differences = sorted(k for k, v in authority.items() if control.get(k) != v)
    if len(authority) != 6 or any(observed.get(k) != v for k, v in authority.items()) or differences != ['balanceOf']:
        raise EvidenceError('ERC20 signature comparison disagrees with fixed controls')
    return {'revision': OZ, 'reference_sha256': IERC20_SHA, 'nqc_source': WETH,
            'nqc_source_sha256': sha(source.encode()), 'solc_sha256': SOLC_SHA, 'signatures': authority,
            'additional_owned_functions': sorted(observed.keys() - authority.keys()),
            'rejected_signatures_in_control': differences}


def attach(index, root, kit):
    if kit is None:
        raise EvidenceError('source references require the Solidity metadata kit')
    reports = {'ethereum/consensus-specs': consensus(root, index.census_header),
               'openzeppelin/openzeppelin-contracts': oz_interface(root, kit)}
    for key, report in reports.items():
        index.repos[key]['source_reference'] = {'revision': report['revision'], 'report': 'source-references',
                                               'report_sha256': sha(canonical(report))}
    index.source_references = reports
