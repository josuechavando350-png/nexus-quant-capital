"""Reconstruct declared storage HEAD positions for an explicit Solidity subset.

No compiler, VM, source inventory proof or deployed-state reader. Types originate
from spans already cross-checked against supplied AST/layout by compiler_layout.
Two arithmetic implementations agree before any supplied position is compared.
Only ordinary single-contract declarations with default base zero are supported.
Dynamic payloads, structs, C3 inheritance and custom layouts require other checks.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from . import source_types
from .safe_io import canonical

MAX_DECLARATIONS = 2048
MAX_DEPTH = 24
SLOTS = 1 << 256
SPACE = SLOTS * 32


class PlacementError(ValueError):
    """Fixed codes; do not echo source, labels or supplied values."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise PlacementError(code)


def _width(name: str) -> int | None:
    if name in ('bytes', 'string'):
        return None
    if name == 'bool':
        return 1
    if name in ('address', 'address payable'):
        return 20
    m = re.fullmatch(r'(?:uint|int)([1-9][0-9]{0,2})', name)
    if m:
        bits = int(m[1]); need(8 <= bits <= 256 and bits % 8 == 0, 'INTEGER_WIDTH')
        return bits // 8
    m = re.fullmatch(r'bytes([1-9][0-9]?)', name)
    if m:
        width = int(m[1]); need(width <= 32, 'BYTES_WIDTH')
        return width
    raise PlacementError('ELEMENT_OUTSIDE_PLACEMENT_PROFILE')


def _validate(shape: Any, depth: int = 0) -> None:
    need(depth <= MAX_DEPTH and type(shape) is tuple and bool(shape), 'TYPE_SHAPE_BUDGET_OR_SCHEMA')
    if shape[0] == 'elementary':
        need(len(shape) == 2 and type(shape[1]) is str, 'ELEMENTARY_SCHEMA')
        _width(shape[1])
    elif shape[0] == 'array':
        need(len(shape) == 3 and (shape[1] is None or
             type(shape[1]) is int and 0 < shape[1] < SLOTS), 'ARRAY_LENGTH')
        _validate(shape[2], depth+1)
    elif shape[0] == 'mapping':
        need(len(shape) == 3, 'MAPPING_SCHEMA')
        _validate(shape[1], depth+1); _validate(shape[2], depth+1)
        need(shape[1][0] == 'elementary', 'MAPPING_KEY')
    else:
        raise PlacementError('TYPE_OUTSIDE_PLACEMENT_PROFILE')


def _footprint(shape: tuple) -> tuple[bool, int]:
    """(packable, byte-width or full head-region size); never expand arrays."""
    kind = shape[0]
    if kind == 'elementary':
        width = _width(shape[1])
        return (width is not None, width if width is not None else 32)
    if kind == 'mapping' or shape[1] is None:
        return False, 32
    packable, child = _footprint(shape[2])
    size = ((shape[1] + (32 // child) - 1) // (32 // child)) * 32 if packable else shape[1] * child
    need(size <= SPACE, 'HEAD_REGION_OVERFLOW')
    return False, size


def _reference_region(shape: tuple) -> tuple[bool, int]:
    """Separate size arithmetic; sizes are still interpreted under the SAME model."""
    tag = shape[0]
    if tag == 'mapping' or tag == 'array' and shape[1] is None:
        return False, 1  # slots for aggregates, bytes for scalars
    if tag == 'elementary':
        label = shape[1]
        if label in ('string', 'bytes'):
            return False, 1
        if label.startswith(('uint', 'int')):
            return True, int(re.search(r'[0-9]+\Z', label)[0]) >> 3
        if label.startswith('bytes'):
            return True, int(label[5:])
        return True, {'bool': 1, 'address': 20, 'address payable': 20}[label]
    scalar, extent = _reference_region(shape[2])
    if scalar:
        per_word = 32 // extent
        count = (shape[1] - 1) // per_word + 1
    else:
        count = shape[1] * extent
    need(count <= SLOTS, 'HEAD_REGION_OVERFLOW')
    return False, count


def _inputs(shapes: Any) -> None:
    need(type(shapes) is list and len(shapes) <= MAX_DECLARATIONS, 'DECLARATION_BUDGET')
    for shape in shapes:
        _validate(shape)


def allocate_primary(shapes: list[tuple]) -> list[dict]:
    """Slot/offset cursor; aggregate regions always start and finish on a slot."""
    _inputs(shapes)
    slot, offset = 0, 0
    result = []
    for shape in shapes:
        packable, extent = _footprint(shape)
        if not packable or offset + extent > 32:
            if offset:
                slot += 1
            offset = 0
        need(slot < SLOTS and 32 * slot + offset + extent <= SPACE, 'PLACEMENT_OVERFLOW')
        result.append({'slot': str(slot), 'offset': offset, 'head_bytes': str(extent)})
        if packable:
            offset += extent
            if offset == 32:
                slot += 1; offset = 0
        else:
            slot += extent // 32
    return result


def allocate_reference(shapes: list[tuple]) -> list[dict]:
    """Absolute-byte cursor with separate region arithmetic; no primary calls."""
    _inputs(shapes)
    cursor = 0
    result = []
    for shape in shapes:
        scalar, extent = _reference_region(shape)
        if scalar:
            end_slot = (cursor + extent - 1) // 32
            if cursor // 32 != end_slot:
                cursor = ((cursor // 32) + 1) * 32
            size = extent
        else:
            cursor = -(-cursor // 32) * 32
            size = extent * 32
        need(cursor < SPACE and cursor + size <= SPACE, 'PLACEMENT_OVERFLOW')
        word, byte = divmod(cursor, 32)
        result.append({'slot': str(word), 'offset': byte, 'head_bytes': str(size)})
        cursor += size
    return result


def _ordinary_header(source: bytes, contract: dict) -> bool:
    """Small header recognizer, not a Solidity parser. Comments do not add flags."""
    if contract.get('storageLayout') is not None or contract.get('contractKind', 'contract') != 'contract':
        return False
    try:
        start, size, _ = map(int, contract['src'].split(':'))
        raw = source[start:start + min(size, 16_384)]
    except (ValueError, KeyError, TypeError):
        raise PlacementError('CONTRACT_HEADER_RANGE') from None
    words = []; i = 0
    while i < len(raw):
        if raw[i:i+1] in (b' ', b'\t', b'\n', b'\r'):
            i += 1; continue
        if raw[i:i+2] == b'//':
            j = raw.find(b'\n', i+2)
            if j == -1: return False
            i = j+1; continue
        if raw[i:i+2] == b'/*':
            j = raw.find(b'*/', i+2)
            if j == -1: return False
            i = j+2; continue
        if raw[i:i+1] == b'{':
            return words in (['contract', contract['name']], ['abstract', 'contract', contract['name']])
        m = re.match(rb'[A-Za-z_$][A-Za-z0-9_$]*', raw[i:])
        if not m or len(words) >= 4: return False
        words.append(m[0].decode('ascii')); i += len(m[0])
    return False


def _review(reason: str, total: int) -> dict:
    return {'profile': 'default-zero-single-contract-heads-solidity-0.8.30',
            'status': 'PLACEMENT_REVIEW_REQUIRED', 'reason': reason,
            'declarations': total, 'checked': 0, 'all_declared_heads_checked': False,
            'records': [], 'compiler_execution_verified': False, 'dynamic_payloads_checked': False,
            'source_inventory_complete_proven': False, 'deployed_values_checked': False}


def verify_heads(*, contract: dict, lineage: list[int], persistent: dict[int, dict],
                 storage: dict, source: bytes, file_id: int,
                 compiler_version: str, typed: list[dict]) -> dict:
    """Only after source/AST/type binding. Reject inconsistent declared heads.

    Declaration ordering comes from source-byte offsets, NOT AST array order,
    AST identifiers, or the provided storage order. Missing declarations in a
    consistently forged AST remain possible; this does not authenticate an AST.
    """
    count = len(persistent)
    if compiler_version.split('+', 1)[0] != '0.8.30':
        return _review('COMPILER_VERSION_OUTSIDE_PLACEMENT_PROFILE', count)
    if len(lineage) != 1:
        return _review('INHERITANCE_ORDER_NOT_RECONSTRUCTED', count)
    if not _ordinary_header(source, contract):
        return _review('CUSTOM_OR_UNSUPPORTED_CONTRACT_HEADER', count)
    if len(typed) != count or any(t['status'] != 'TYPE_CONSISTENT_IN_PROFILE' for t in typed):
        return _review('TYPE_COVERAGE_INCOMPLETE', count)
    ordered = []
    for ast_id, var in persistent.items():
        start, end = source_types._range(var['src'], source, file_id)
        a, b = source_types._range(var['typeName']['src'], source, file_id)
        shape = source_types.source_shape(source[a:b])
        ordered.append((start, end, ast_id, shape))
    ordered.sort(key=lambda row: row[0])
    for left, right in zip(ordered, ordered[1:]):
        need(left[1] <= right[0], 'DECLARATION_SPANS_OVERLAP')
    shapes = [row[3] for row in ordered]
    primary = allocate_primary(shapes)
    reference = allocate_reference(shapes)
    need(primary == reference, 'PLACEMENT_ALGORITHMS_DISAGREE')
    supplied = {row['astId']: row for row in storage['storage']}
    need(set(supplied) == set(persistent), 'PLACEMENT_DECLARATION_COVERAGE')
    records = []
    for (_, _, ast_id, shape), expected in zip(ordered, primary):
        row = supplied[ast_id]
        need(type(row['offset']) is int and type(row['slot']) is str and
             row['offset'] == expected['offset'] and row['slot'] == expected['slot'],
             'DECLARED_PLACEMENT_MISMATCH')
        records.append({'ast_id': ast_id, **expected,
                        'shape_sha256': hashlib.sha256(canonical(shape)).hexdigest()})
    return {'profile': 'default-zero-single-contract-heads-solidity-0.8.30',
            'status': 'HEAD_POSITIONS_RECONSTRUCTED', 'reason': None,
            'declarations': count, 'checked': count, 'all_declared_heads_checked': True,
            'records': records, 'compiler_execution_verified': False, 'dynamic_payloads_checked': False,
            'source_inventory_complete_proven': False, 'deployed_values_checked': False}
