"""Check the fixed Census block-header test vector with upstream field definitions and three local libraries."""
import ast
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .product_notice_ranking import ISOLATE
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .safe_io import canonical, read_artifact, strict_json

FIXTURE = 'nqc-census/crates/nqc-census-chain/tests/fixtures/mainnet-block-25437474.json'
FIXTURE_SHA = '7fdfd8e9d583c854001e5a74b80bdc9b359f551496bfa1a6d6912c1de75d5501'
CENSUS = 'nqc-census/crates/nqc-census-chain/src/ethereum.rs'
CENSUS_SHA = '05d9b7735078f69c6717abf069933a4e94166ff2b4146f1312c448771ba72aee'
LOCK = 'superhunter/product_supply/header-npm-lock.json'
LOCK_SHA = 'e28d9bdcedd5230bc91c4f70cc09949a2561ab56d5da13edb416e4b8fd23268e'
SPEC_SHA = '6e283ad6cb047242e083786a420151eec0a7bbcbe9257fe2c0cad6d0f27a66b8'
EIP_SHA = '99b3272f275293fd5e9af5f45d673132a909dbf28816a7ea7804c247485622a2'
SPEC_COMMIT = '391d8a05d5cb182542ac7e7330c858b6ee03f990'
EIP_COMMIT = 'b4b2ac745e77291d7b47d45665d4e016ab58d31e'
ALIASES = {'ommers_hash': 'sha3Uncles', 'coinbase': 'miner', 'receipt_root': 'receiptsRoot',
           'bloom': 'logsBloom', 'prev_randao': 'mixHash'}


def pinned(root, path, digest):
    data = read_artifact(root, path)
    if sha(data) != digest:
        raise EvidenceError('Census header input differs from its recorded revision: ' + path)
    return data


def field_order(census, spec):
    # These two tables belong to the immutable Census migration.
    fields = []
    for table in ('BASE_FIELDS', 'OPTIONAL_FIELDS'):
        body = re.search(r'const ' + table + r':[^=]+?= \[(.*?)\];', census, re.S)
        if not body:
            raise EvidenceError('Census header field table missing')
        fields.extend(re.findall(r'\("(\w+)", Kind::(\w+)\)', body[1]))
    header, = [node for node in ast.parse(spec).body if isinstance(node, ast.ClassDef) and node.name == 'Header']
    annotations = [n for n in header.body if isinstance(n, ast.AnnAssign)]
    expected = []
    for node in annotations:
        name = node.target.id
        first, *parts = name.split('_')
        key = ALIASES.get(name, first + ''.join(p.title() for p in parts))
        expected.append((key, node.annotation.id in {'Uint', 'U256', 'U64'}))
    if len(fields) != 21 or [(key, kind == 'Quantity') for key, kind in fields] != expected:
        raise EvidenceError('Prague and Census disagree on field order or quantity encoding')
    return fields


def reconcile(output, expected_hash):
    results = {}
    for case in ('original', 'changed_gas_used'):
        rows = output[case]
        if set(rows) != {'ethers', 'viem', 'ethereumjs'} or not all(row == rows['ethereumjs'] for row in rows.values()):
            raise EvidenceError('header producers disagree on RLP or Keccak')
        row = rows['ethereumjs']
        if (row['hash'] == expected_hash) != (case == 'original'):
            raise EvidenceError('header hash differs from expected control outcome')
        rlp = bytes.fromhex(row['rlp'].removeprefix('0x'))
        results[case] = {'keccak256': row['hash'], 'rlp_bytes': len(rlp), 'rlp_sha256': sha(rlp)}
    if results['original']['rlp_sha256'] == results['changed_gas_used']['rlp_sha256']:
        raise EvidenceError('gasUsed mutation preserved the encoded header')
    return results


def build(kit):
    block = strict_json(pinned(ROOT, FIXTURE, FIXTURE_SHA))['block']
    fields = field_order(pinned(ROOT, CENSUS, CENSUS_SHA).decode(), pinned(kit, 'blocks.py', SPEC_SHA))
    eip = pinned(kit, 'eip-7685.md', EIP_SHA)
    if b'the `requests_hash` is simply `sha256("")`' not in eip or block['requestsHash'] != '0x' + sha(b''):
        raise EvidenceError('fixture differs from the EIP-7685 empty-request commitment')
    lock = pinned(ROOT, LOCK, LOCK_SHA)
    package = strict_json(lock)['packages']['']
    node, npm = shutil.which('node'), shutil.which('npm')
    if not node or not npm:
        raise EvidenceError('Node and npm are required for the offline Census header replay')
    cache = (kit/'npm-cache').resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='nqc-header-rlp-') as temp:
        work = Path(temp)
        env = {'PATH': str(Path(node).parent) + ':/usr/bin:/bin', 'HOME': temp, 'TMPDIR': temp,
               'NPM_CONFIG_USERCONFIG': str(work/'empty-user-config'), 'NPM_CONFIG_GLOBALCONFIG': '/dev/null'}
        (work/'package.json').write_bytes(canonical(package))
        (work/'package-lock.json').write_bytes(lock)
        (work/'check.mjs').write_bytes(read_artifact(ROOT, 'superhunter/product_supply/header-check.txt'))
        options = dict(cwd=work, env=env, capture_output=True, check=True, timeout=150)
        subprocess.run([*ISOLATE, npm, 'ci', '--offline', '--no-audit', '--no-fund', '--ignore-scripts',
                        '--cache', cache, '--logs-dir', work/'logs'], stdin=subprocess.DEVNULL, **options)
        proc = subprocess.run([*ISOLATE, node, 'check.mjs'], input=canonical({'block': block, 'fields': fields}),
                              **options)
    comparisons = reconcile(strict_json(proc.stdout), block['hash'])
    return {'fixture': FIXTURE, 'fixture_sha256': FIXTURE_SHA, 'block_number': int(block['number'], 16),
            'fixture_scope': 'historical test vector', 'npm_lock_sha256': LOCK_SHA, 'npm_packages': package['dependencies'],
            'field_order': [name for name, _ in fields], 'requests_hash_matches_empty_commitment': True,
            'census_source_sha256': CENSUS_SHA, 'prague_spec_sha256': SPEC_SHA, 'eip_7685_sha256': EIP_SHA,
            'cases': comparisons}


def attach(index, kit):
    index.census_header = build(kit)
    report_hash = sha(canonical(index.census_header))
    for name, package in (('ethers-io/ethers.js', 'ethers'), ('wevm/viem', 'viem'),
                          ('ethereumjs/ethereumjs-monorepo', '@ethereumjs/block')):
        index.repos[name]['census_header_evidence'] = {
            'report': 'census-header', 'report_sha256': report_hash, 'package': package,
            'version': index.census_header['npm_packages'][package], 'npm_lock_sha256': LOCK_SHA}
    for name, commit, path, digest in (
            ('ethereum/execution-specs', SPEC_COMMIT, 'src/ethereum/forks/prague/blocks.py', SPEC_SHA),
            ('ethereum/eips', EIP_COMMIT, 'EIPS/eip-7685.md', EIP_SHA)):
        index.repos[name]['census_header_reference'] = {
            'report': 'census-header', 'report_sha256': report_hash,
            'revision': commit, 'path': path, 'sha256': digest}


GETH_REVISION = '2b7829ea6aed9a95a3fd793cca46731202c6c310'
GETH_BINARY = 'af8353f39c60f5038cfa0c894ebc9566ad8ea958575d83a1108e00b23089bec7'


def check_geth(output, comparison):
    if canonical(output) != canonical(comparison['cases']):
        raise EvidenceError('Geth disagrees with the three product header implementations')
    return {'git_revision': GETH_REVISION, 'binary_sha256': GETH_BINARY,
            'fixture_sha256': FIXTURE_SHA, 'comparison_sha256': sha(canonical(comparison)),
            'cases': output}


def attach_geth(index, executable):
    from .product_review import copy_release

    if index.census_header is None:
        raise EvidenceError('Geth comparison requires --census-header-kit')
    block = strict_json(pinned(ROOT, FIXTURE, FIXTURE_SHA))['block']
    with tempfile.TemporaryDirectory(prefix='nqc-census-geth-') as temp:
        binary = Path(temp)/'geth-header'
        copy_release('Census Geth helper', executable, binary, GETH_BINARY, limit=10*1024**2)
        result = subprocess.run([*ISOLATE, str(binary)], input=canonical(block), cwd=temp,
                                env={'HOME': temp}, capture_output=True, timeout=15, check=True)
    index.geth_header = check_geth(strict_json(result.stdout), index.census_header)
    index.repos['ethereum/go-ethereum']['geth_header_evidence'] = {
        'report': 'geth-census', 'report_sha256': sha(canonical(index.geth_header)),
        'revision': GETH_REVISION, 'binary_sha256': GETH_BINARY}
