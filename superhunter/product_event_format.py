"""Check two published Transfer log fixtures against the product's pinned interface references."""
from itertools import product
import re

from .product_census_header import pinned
from .product_infra_batch import capture
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_source_references import IERC20, IERC20_SHA, OZ
from .product_sources import git
from .safe_io import canonical, strict_json

HEIMDALL = 'Jon-Becker/heimdall-rs'
OPENZEPPELIN = 'OpenZeppelin/openzeppelin-contracts'
SIGNATURE = 'Transfer(address,address,uint256)'
TYPES = ('address', 'address', 'uint256')
TYPED_VECTOR = 'ci/nqc-census/typed-observation-vectors.json'
VECTOR_SHA = '3d39c20e8e34e18e1e9ae761745c8887a7e35c2822e2aff82dd6140761bc7788'
IERC721 = 'contracts/token/ERC721/IERC721.sol'
FIXTURES = {
    'three_indexed': 'crates/core/tests/testdata/decompile/indexed-events/bayc-transfer.json',
    'indexed_positions_unknown': 'crates/core/tests/testdata/decompile/indexed-events/weth-transfer-ambiguous.json',
}
SOURCES = {
    HEIMDALL: ('033-heimdall-rs', '89e107f033f6e8fc037ba58757ac855e2a7049dd', tuple(FIXTURES.values())),
    OPENZEPPELIN: ('039-openzeppelin-contracts', OZ, (IERC20, IERC721)),
}
WORD = re.compile(r'0x[0-9a-fA-F]{64}')


def declaration(raw):
    # Only the static Transfer event in the two pinned Solidity interfaces is in scope.
    declarations = re.findall(r'^\s*event\s+Transfer\s*\(([^();]+)\)\s*;', raw, re.MULTILINE)
    if len(declarations) != 1:
        raise EvidenceError('missing or ambiguous ABI event declaration')
    fields = [re.fullmatch(r'(address|uint256)\s+(?:(indexed)\s+)?[a-zA-Z_]\w*', part.strip())
              for part in declarations[0].split(',')]
    if not all(fields) or tuple(field[1] for field in fields) != TYPES:
        raise EvidenceError('unsupported ABI event declaration')
    return tuple(field[2] is not None for field in fields)


def placements(row, signature_topic):
    topics, data = row['topics'], row['data']
    if (type(topics) is not list or not 1 <= len(topics) <= 4 or
            not all(type(t) is str and WORD.fullmatch(t) for t in topics) or topics[0].lower() != signature_topic or
            type(data) is not str or not re.fullmatch(r'0x(?:[0-9a-fA-F]{64}){0,3}', data)):
        raise EvidenceError('stored event framing or signature topic differs')
    indexed = [int(t, 16) for t in topics[1:]]
    payload = [int(data[i:i+64], 16) for i in range(2, len(data), 64)]
    if len(indexed) + len(payload) != len(TYPES):
        raise EvidenceError('stored event field count differs')
    compatible = set()
    for mask in product((False, True), repeat=len(TYPES)):
        if sum(mask) != len(indexed):
            continue
        sections = {True: iter(indexed), False: iter(payload)}
        words = [next(sections[flag]) for flag in mask]
        if all(value.bit_length() <= (160 if typ == 'address' else 256) for typ, value in zip(TYPES, words)):
            compatible.add(mask)
    return compatible


def check_fixture(doc, topic, declarations):
    rows = doc['logs']
    if doc['signature'] != SIGNATURE or type(rows) is not list or not 0 < len(rows) <= 16:
        raise EvidenceError('stored Transfer fixture identity or number of observations differs')
    candidates = set.intersection(*(placements(row, topic) for row in rows))
    label = doc['expectedIndexed']
    if not candidates:
        raise EvidenceError('incompatible indexed placement across observations')
    if label is None:
        if len(candidates) == 1:
            raise EvidenceError('fixture labelled ambiguous has a unique layout')
    elif (type(label) is not list or len(label) != len(TYPES) or any(type(bit) is not bool for bit in label)
          or candidates != {tuple(label)}):
        raise EvidenceError('fixture indexing claim lacks a unique wire interpretation')
    return {'records': len(rows), 'plausible_index_masks': len(candidates),
            'unlabelled_layout_ambiguous': len(candidates) > 1,
            'compatible_declared_interfaces': sorted(name for name, mask in declarations.items() if mask in candidates)}


def review(root):
    for directory, revision, _ in SOURCES.values():
        if git(root / directory, 'rev-parse', 'HEAD').decode().strip() != revision:
            raise EvidenceError('event fixture or reference checkout differs')
    fixture_files, fixture_manifest = capture(root, HEIMDALL, SOURCES, binary=True)
    interfaces, interface_manifest = capture(root, OPENZEPPELIN, SOURCES, binary=True)
    if sha(interfaces[IERC20]) != IERC20_SHA:
        raise EvidenceError('ERC20 declaration differs from the product ABI reference')
    declarations = {name: declaration(interfaces[path].decode()) for name, path in
                    (('IERC20', IERC20), ('IERC721', IERC721))}
    vector = strict_json(pinned(ROOT, TYPED_VECTOR, VECTOR_SHA))
    topic = '0x' + vector['keccak256'][SIGNATURE]
    if not WORD.fullmatch(topic):
        raise EvidenceError('invalid recorded event signature witness')
    cases = {label: check_fixture(strict_json(fixture_files[path]), topic, declarations)
             for label, path in FIXTURES.items()}
    if (cases['three_indexed']['compatible_declared_interfaces'] != ['IERC721']
            or cases['indexed_positions_unknown']['compatible_declared_interfaces'] != ['IERC20']
            or not cases['indexed_positions_unknown']['unlabelled_layout_ambiguous']):
        raise EvidenceError('event fixture disagrees with declared ABI compatibility controls')
    return {HEIMDALL: {'revision': SOURCES[HEIMDALL][1], 'role': 'reference',
                       'operation': 'check_indexed_layout_compatibility_of_stored_transfer_records',
                       'source_manifest_sha256': sha(canonical(fixture_manifest)),
                       'interface_manifest_sha256': sha(canonical(interface_manifest)),
                       'typed_observation_vector_sha256': VECTOR_SHA, 'result': cases}}
