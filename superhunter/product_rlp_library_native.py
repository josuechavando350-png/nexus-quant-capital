"""Execute unchanged Ethernaut RLP libraries on a historical NQC test vector."""
import base64
import gzip
from pathlib import Path
import re
import subprocess
import tempfile

from .native_compile import PIN as SOLC
from .product_census_header import CENSUS, CENSUS_SHA, FIXTURE, FIXTURE_SHA, GETH_BINARY, pinned
from .product_notice_ranking import ISOLATE
from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .product_solidity_headers import FORGE_SHA
from .safe_io import MAX_BYTES, canonical, strict_json

REPOSITORIES = {'OpenZeppelin/ethernaut': 'executable'}
SCOPE = 'Execute unchanged RLP reader/writer libraries to reconstruct and decode the fixed historical Census header; compare independent bytes and fields and expose incomplete canonical validation.'
PINS = 'superhunter/product_supply/rlp-library-native-pins.json'
PINS_SHA = '13488ec8269670a8c90d5119809612cc4e179dddeb5ed8763c23f264e27bd15e'
HARNESS = 'superhunter/product_supply/rlp-library-native-owned.txt'
HARNESS_SHA = '3f115bbf770cf8df99ec5a45a2bcede4fe636496a99b1035428447dad2234871'
WITNESS = 'superhunter/product_supply/rlp-library-native-header-witness.json'
WITNESS_SHA = '89df1c5192d562237be6a66b3b504fb9af2dcc8fb3f4e0a60bcbca53e99ba132'
EVENT_TOPIC = '0xd26e16cad4548705e4c9e2d94f98ee91c289085ee425594fd5635fa2964ccf18'
FIELDS = [('parentHash', 'Hash'), ('sha3Uncles', 'Hash'), ('miner', 'Address'),
          ('stateRoot', 'Hash'), ('transactionsRoot', 'Hash'), ('receiptsRoot', 'Hash'),
          ('logsBloom', 'Bloom'), ('difficulty', 'Quantity'), ('number', 'Quantity'),
          ('gasLimit', 'Quantity'), ('gasUsed', 'Quantity'), ('timestamp', 'Quantity'),
          ('extraData', 'Data'), ('mixHash', 'Hash'), ('nonce', 'Nonce'),
          ('baseFeePerGas', 'Quantity'), ('withdrawalsRoot', 'Hash'),
          ('blobGasUsed', 'Quantity'), ('excessBlobGas', 'Quantity'),
          ('parentBeaconBlockRoot', 'Hash'), ('requestsHash', 'Hash')]
BYTE_CONTROLS = {'empty': b'', 'single_low': b'\x01', 'single_high': b'\x80',
                 'short55': bytes(range(55)), 'long56': bytes(range(56)), 'long256': b'\xab'*256}
NONCANONICAL = {
    'nonminimal_byte': (b'\x81\x01', False, b'\x01'),
    'long_form_short': (b'\xb8\x01\x01', False, b'\x01'),
    'trailing_bytes': (b'\x01\x02', False, b'\x01'),
    'trailing_list_items': (b'\xc1\x01\x02', True, b'\xc2\x01\x02'),
}


def uint_bytes(value):
    return value.to_bytes((value.bit_length()+7)//8, 'big')


def rlp_prefix(size, offset):
    if size < 56:
        return bytes([offset+size])
    length = uint_bytes(size)
    return bytes([offset+55+len(length)]) + length


def rlp_bytes(value):
    return value if len(value) == 1 and value[0] < 128 else rlp_prefix(len(value), 128)+value


def rlp_list(values):
    body = b''.join(rlp_bytes(value) for value in values)
    return rlp_prefix(len(body), 192)+body


def field_values(block):
    values = []
    for name, kind in FIELDS:
        value = block.get(name)
        if not isinstance(value, str) or not re.fullmatch(r'0x[0-9a-f]*', value):
            raise EvidenceError('invalid fixed header field')
        if kind == 'Quantity':
            if not re.fullmatch(r'0x(?:0|[1-9a-f][0-9a-f]*)', value):
                raise EvidenceError('nonminimal fixed header quantity')
            raw = uint_bytes(int(value, 16))
            if len(raw) > 32:
                raise EvidenceError('fixed header quantity too large')
        else:
            if len(value) % 2:
                raise EvidenceError('odd fixed header bytes')
            raw = bytes.fromhex(value[2:])
            widths = {'Hash': 32, 'Address': 20, 'Bloom': 256, 'Nonce': 8}
            if (kind in widths and len(raw) != widths[kind]) or (kind == 'Data' and len(raw) > 32):
                raise EvidenceError('incorrect fixed header field width')
        values.append(raw)
    return values


def header_context():
    witness = strict_json(pinned(ROOT, WITNESS, WITNESS_SHA))
    archive = strict_json(pinned(ROOT, witness['historical_archive'], witness['historical_archive_sha256']))
    raw = gzip.decompress(base64.b64decode(archive['gzip_base64'], validate=True))
    if len(raw) != 997677 or sha(raw) != witness['historical_session_sha256'] or sha(raw) != archive['raw_sha256']:
        raise EvidenceError('historical header comparison archive changed')
    rows = [strict_json(b'{"row":'+line+b'}')['row'] for line in raw.splitlines()]
    headers = [row for row in rows if isinstance(row, dict) and row.get('fixture') == FIXTURE]
    geth = [row for row in rows if isinstance(row, dict) and row.get('binary_sha256') == GETH_BINARY]
    if (headers != [witness['report']] or len(geth) != 1 or
            geth[0]['cases'] != witness['report']['cases'] or
            geth[0]['comparison_sha256'] != sha(canonical(witness['report']))):
        raise EvidenceError('historical independent header witnesses disagree')
    source = pinned(ROOT, CENSUS, CENSUS_SHA).decode()
    fields = []
    for name in ('BASE_FIELDS', 'OPTIONAL_FIELDS'):
        match = re.search(r'const '+name+r':[^=]+?= \[(.*?)\];', source, re.S)
        if match is None:
            raise EvidenceError('immutable Census field order missing')
        fields.extend(re.findall(r'\("(\w+)", Kind::(\w+)\)', match[1]))
    if fields != FIELDS or witness['report']['field_order'] != [name for name, _ in FIELDS]:
        raise EvidenceError('immutable Census field order changed')
    fixture = strict_json(pinned(ROOT, FIXTURE, FIXTURE_SHA))
    if fixture['purpose'] != 'TEST_VECTOR_PUBLIC_MAINNET_HEADER_NOT_CENSUS_EVIDENCE':
        raise EvidenceError('historical test vector purpose changed')
    block = fixture['block']
    changed = {**block, 'gasUsed': hex(int(block['gasUsed'], 16)+1)}
    cases = {}
    for name, row in (('original', block), ('changed_gas_used', changed)):
        values = field_values(row)
        encoded = rlp_list(values)
        expected = witness['report']['cases'][name]
        if len(encoded) != expected['rlp_bytes'] or sha(encoded) != expected['rlp_sha256']:
            raise EvidenceError('independent RLP encoder disagrees with historical witnesses')
        cases[name] = {'fields': values, 'encoded': encoded, 'hash': bytes.fromhex(expected['keccak256'][2:])}
    if cases['original']['hash'].hex() != block['hash'][2:] or cases['original']['hash'] == cases['changed_gas_used']['hash']:
        raise EvidenceError('fixed header hash controls changed')
    return cases, witness


def abi_dynamic(value):
    return len(value).to_bytes(32, 'big')+value+b'\0'*((-len(value)) % 32)


def error_bytes(reason):
    return bytes.fromhex('08c379a0')+(32).to_bytes(32, 'big')+abi_dynamic(reason.encode())


def event_data(name, value):
    first = abi_dynamic(name.encode())
    return (64).to_bytes(32, 'big')+(64+len(first)).to_bytes(32, 'big')+first+abi_dynamic(value)


def malformed_controls(cases):
    return {
        'empty_input': (b'', False, 'RLP item cannot be null.'),
        'truncated_string': (b'\x82\x01', False, 'Invalid RLP short string.'),
        'string_as_list': (b'\x80', True, 'Invalid RLP list value.'),
        'list_as_bytes': (b'\xc0', False, 'Invalid RLP bytes value.'),
        'truncated_header': (cases['original']['encoded'][:-1], True, 'Invalid RLP long list.'),
        'missing_long_length': (b'\xf9\x00', True, 'Invalid RLP long list length.'),
        'thirty_three_items': (rlp_list([b'\x01']*33), True, 'Provided RLP list exceeds max list length.'),
    }


def expected_observations(cases):
    expected = {}
    for name, method in (('original', 'HistoricalHeader'), ('changed_gas_used', 'ChangedGasUsed')):
        case = cases[name]
        expected['test'+method+'()'] = [('encoded', case['encoded']), ('hash', case['hash'])] + [
            ('field/'+field, raw) for (field, _), raw in zip(FIELDS, case['fields'])]
    expected['testByteBoundaries()'] = [(name+'/'+operation, value) for name, raw in BYTE_CONTROLS.items()
        for operation, value in (('encoded', rlp_bytes(raw)), ('decoded', raw))]
    expected['testThirtyTwoItems()'] = [('encoded', rlp_list([b'\x01']*32))]
    expected['testMalformedInputsRejected()'] = [(name, error_bytes(reason))
        for name, (_, _, reason) in malformed_controls(cases).items()]
    expected['testNoncanonicalInputsNeedOwnGuard()'] = [(name+'/'+operation, value)
        for name, (raw, _, normalized) in NONCANONICAL.items()
        for operation, value in (('input', raw), ('normalized', normalized), ('guard', error_bytes('OWNED_NONCANONICAL')))]
    return expected


def owned_harness(cases):
    source = pinned(ROOT, HARNESS, HARNESS_SHA).decode()
    methods = []
    for name, method in (('original', 'HistoricalHeader'), ('changed_gas_used', 'ChangedGasUsed')):
        case = cases[name]
        lines = [f'function test{method}() public {{', 'bytes[] memory values = new bytes[](21);']
        lines.extend(f'values[{i}] = hex"{value.hex()}";' for i, value in enumerate(case['fields']))
        lines.extend(['bytes memory encoded = encodeList(values);',
            f'bytes memory independent = hex"{case["encoded"].hex()}";',
            'require(same(encoded, independent), "independent RLP bytes differ");',
            f'require(keccak256(encoded) == bytes32(hex"{case["hash"].hex()}"), "historical header hash differs");',
            'bytes[] memory decoded = readList(independent);', 'require(decoded.length == 21, "header field count differs");',
            'emit log_named_bytes("encoded", encoded);', 'emit log_named_bytes("hash", abi.encodePacked(keccak256(encoded)));'])
        for i, (field, _) in enumerate(FIELDS):
            lines.extend([f'require(same(decoded[{i}], values[{i}]), "decoded field differs");',
                          f'emit log_named_bytes("field/{field}", decoded[{i}]);'])
        methods.append('\n'.join([*lines, '}']))
    replacements = {
        'HEADER_METHODS': '\n'.join(methods),
        'BYTE_CONTROLS': '\n'.join(f'bytesControl("{name}", hex"{value.hex()}", hex"{rlp_bytes(value).hex()}");'
                                  for name, value in BYTE_CONTROLS.items()),
        'NEGATIVE_CONTROLS': '\n'.join(f'rejectInput("{name}", hex"{value.hex()}", {str(is_list).lower()});'
            for name, (value, is_list, _) in malformed_controls(cases).items()),
        'NONCANONICAL_CONTROLS': '\n'.join(f'needsGuard("{name}", hex"{value.hex()}", {str(is_list).lower()});'
            for name, (value, is_list, _) in NONCANONICAL.items()),
    }
    for name, replacement in replacements.items():
        if source.count('%%'+name+'%%') != 1:
            raise EvidenceError('owned codec harness marker changed')
        source = source.replace('%%'+name+'%%', replacement)
    return source.encode()


def reconcile(raw, cases):
    data = strict_json(raw)
    if set(data) != {'test/Owned.t.sol:OwnedRlpLibraryTest'}:
        raise EvidenceError('unexpected native codec test contract')
    suite = data['test/Owned.t.sol:OwnedRlpLibraryTest']
    expected = expected_observations(cases)
    tests = suite.get('test_results', {})
    if set(tests) != set(expected) or suite.get('warnings') != []:
        raise EvidenceError('incomplete native codec controls')
    result = {}
    for name, observations in expected.items():
        row = tests[name]
        try:
            gas = row['kind']['Unit']['gas']
            if (row['status'] != 'Success' or row['reason'] is not None or row['counterexample'] is not None or
                    type(gas) is not int or gas <= 0 or len(row['logs']) != len(observations)):
                raise EvidenceError('native codec test did not pass or omitted observations')
            rendered = []
            for log, (key, value) in zip(row['logs'], observations):
                if (log['topics'] != [EVENT_TOPIC] or log['data'] != '0x'+event_data(key, value).hex() or
                        not re.fullmatch(r'0x[0-9a-f]{40}', log['address'])):
                    raise EvidenceError('native codec bytes or fields differ from independent witness')
                rendered.append(key+': 0x'+value.hex())
            if row['decoded_logs'] != rendered:
                raise EvidenceError('decoded codec observations differ from raw event bytes')
        except (KeyError, TypeError) as exc:
            raise EvidenceError('malformed native codec output') from exc
        result[name] = {'status': 'Success', 'gas': gas, 'observations': len(observations)}
    return result


def _native_output(kit, pins, harness):
    with tempfile.TemporaryDirectory(prefix='nqc-rlp-library-') as tmp:
        work, kit = Path(tmp), Path(kit)
        copy_release('solc', kit/'solc', work/'solc', SOLC['sha256'])
        copy_release('forge', kit/'forge', work/'forge', FORGE_SHA)
        for row in pins['sources']:
            target = work/row['kit_path']
            target.parent.mkdir(parents=True, exist_ok=True)
            copy_release(row['source_path'], kit/row['kit_path'], target, row['sha256'], executable=False)
        (work/'test').mkdir()
        (work/'test/Owned.t.sol').write_bytes(harness)
        (work/'foundry.toml').write_text('[profile.default]\nevm_version = "paris"\noffline = true\noptimizer = false\n')
        proc = subprocess.run([*ISOLATE, work/'forge', 'test', '--root', work, '--use', work/'solc',
            '--offline', '--match-contract', 'OwnedRlpLibraryTest', '--json', '-vv'], cwd=work,
            env={'HOME': tmp, 'TMPDIR': tmp, 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'},
            capture_output=True, timeout=90)
        if proc.returncode or proc.stderr or len(proc.stdout) > MAX_BYTES:
            error = EvidenceError('native codec replay failed')
            error.stdout, error.stderr = proc.stdout[:MAX_BYTES], proc.stderr[:MAX_BYTES]
            raise error
        return proc.stdout


def run(kit):
    cases, witness = header_context()
    pins = strict_json(pinned(ROOT, PINS, PINS_SHA))
    harness = owned_harness(cases)
    tests = reconcile(_native_output(kit, pins, harness), cases)
    return {'tools': {'OpenZeppelin/ethernaut': {'catalog_revision': pins['revision'], 'scope': SCOPE,
                'executed_source_files': 2, 'source_pins_sha256': PINS_SHA, 'upstream_sources_modified': False}},
        'native_tests': tests, 'fixture_sha256': FIXTURE_SHA, 'census_field_source_sha256': CENSUS_SHA,
        'fixture_scope': 'Historical public mainnet test vector; not Census production evidence or a live-chain attestation.',
        'header_cases': {name: {'rlp_bytes': len(case['encoded']), 'rlp_sha256': sha(case['encoded']),
            'keccak256': '0x'+case['hash'].hex(), 'decoded_fields': [
                {'name': field, 'bytes': len(value), 'hex': '0x'+value.hex()}
                for (field, _), value in zip(FIELDS, case['fields'])]} for name, case in cases.items()},
        'byte_boundary_lengths': [len(value) for value in BYTE_CONTROLS.values()],
        'list_boundary': {'accepted_items': 32, 'rejected_items': 33},
        'malformed_inputs_rejected': sorted(malformed_controls(cases)),
        'canonical_limits': {'upstream_accepts_tested_noncanonical_inputs': sorted(NONCANONICAL),
            'own_reencode_equality_guard_rejects_those_inputs': True,
            'general_canonical_validation_certified': False,
            'scope': 'The unmodified upstream reader accepts the four recorded overlong/trailing encodings. The own guard rejects them by comparing re-encoded bytes. Only flat byte-string lists and the recorded cases are covered.'},
        'historical_comparison': {'witness_sha256': WITNESS_SHA,
            'session_sha256': witness['historical_session_sha256'],
            'producers': ['ethers', 'viem', 'EthereumJS', 'Geth'], 'reexecuted_by_this_adapter': False},
        'owned_template_sha256': HARNESS_SHA, 'generated_harness_sha256': sha(harness),
        'solc_sha256': SOLC['sha256'], 'forge_sha256': FORGE_SHA,
        'network_at_execution': False, 'original_vulnerabilities_confirmed': 0}
