"""Bounded three-way consistency of supplied Solidity type descriptions.

Parses ONLY the declared type span for elementary types, literal arrays and
mappings; it is not a Solidity compiler or full source-language parser. Compare
source tokens, an independently walked AST shape, and a storage descriptor graph.
Unknown types/expressions remain review-required. Never evaluates expressions,
compiles code, opens a network connection, or executes any analyzed input.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from .safe_io import canonical

MAX_DEPTH = 24
MAX_TOKENS = 2048
MAX_FRAGMENT = 16_384
MAX_NODES = 4096
IDENT = re.compile(r'[A-Za-z_$][A-Za-z0-9_$]*\Z')
SPAN = re.compile(r'(0|[1-9][0-9]{0,9}):(0|[1-9][0-9]{0,9}):(0|[1-9][0-9]{0,9})\Z')
LEX = re.compile(rb'[ \t\r\n]+|//[^\r\n]*(?:\r?\n|\Z)|/\*.*?\*/|=>|[A-Za-z_$][A-Za-z0-9_$]*|[0-9][0-9_]*|[()[\]]', re.S)


class TypeBindingError(ValueError):
    """Fixed diagnostic codes only; no supplied source values are echoed."""


class TypeNeedsReview(TypeBindingError):
    """A type shape is outside this explicitly declared profile."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise TypeBindingError(code)


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _element(name: Any, *, payable: bool = False) -> tuple:
    need(type(name) is str and len(name) <= 128, 'TYPE_NAME')
    if name in ('uint', 'int'):
        name += '256'
    integer = re.fullmatch(r'(u?int)([1-9][0-9]{0,2})', name)
    fixed_bytes = re.fullmatch(r'bytes([1-9][0-9]?)', name)
    if integer:
        width = int(integer[2])
        need(8 <= width <= 256 and width % 8 == 0, 'INTEGER_TYPE_WIDTH')
    elif fixed_bytes:
        need(1 <= int(fixed_bytes[1]) <= 32, 'BYTES_TYPE_WIDTH')
    elif name not in ('bool', 'address', 'bytes', 'string'):
        raise TypeNeedsReview('TYPE_OUTSIDE_PROFILE')
    need(not payable or name == 'address', 'PAYABLE_TYPE')
    return ('elementary', name + (' payable' if payable else ''))


def _length(text: Any) -> int:
    need(type(text) is str and len(text) <= 156, 'ARRAY_LENGTH_LITERAL')
    if not re.fullmatch(r'[0-9]+(?:_[0-9]+)*', text):
        raise TypeNeedsReview('ARRAY_EXPRESSION_REVIEW')
    value = int(text.replace('_', ''))
    need(0 < value < 2**256, 'ARRAY_LENGTH_RANGE')
    return value


def _tokens(raw: bytes) -> list[str]:
    need(type(raw) is bytes and 0 < len(raw) <= MAX_FRAGMENT, 'TYPE_FRAGMENT_BUDGET')
    out = []
    offset = 0
    while offset < len(raw):
        match = LEX.match(raw, offset)
        if match is None:
            if raw[offset:offset+2] == b'/*':
                raise TypeBindingError('UNTERMINATED_TYPE_COMMENT')
            raise TypeNeedsReview('TYPE_SYNTAX_OUTSIDE_PROFILE')
        token = match[0]
        offset = match.end()
        if token[:1] in b' \r\n\t' or token.startswith((b'//', b'/*')):
            continue
        out.append(token.decode('ascii'))
        need(len(out) <= MAX_TOKENS, 'TYPE_TOKEN_BUDGET')
    need(bool(out), 'EMPTY_TYPE_FRAGMENT')
    return out


class _Parser:
    def __init__(self, raw: bytes):
        self.tokens = _tokens(raw)
        self.pos = 0

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self, token: str | None = None) -> str:
        current = self.peek()
        need(current is not None and (token is None or current == token), 'TYPE_SYNTAX_MISMATCH')
        self.pos += 1
        return current

    def typ(self, depth: int = 0) -> tuple:
        if depth > MAX_DEPTH:
            raise TypeNeedsReview('TYPE_DEPTH_REVIEW')
        first = self.take()
        if first == 'mapping':
            self.take('(')
            key = self.typ(depth+1)
            if self.peek() != '=>':
                need(IDENT.fullmatch(self.take()) is not None, 'MAPPING_KEY_NAME')
            self.take('=>')
            value = self.typ(depth+1)
            if self.peek() != ')':
                need(IDENT.fullmatch(self.take()) is not None, 'MAPPING_VALUE_NAME')
            self.take(')')
            # This subset intentionally excludes user-defined mapping keys.
            need(key[0] == 'elementary', 'MAPPING_KEY_PROFILE')
            shape = ('mapping', key, value)
        else:
            payable = first == 'address' and self.peek() == 'payable'
            if payable:
                self.take('payable')
            shape = _element(first, payable=payable)
        while self.peek() == '[':
            self.take('[')
            size = None
            if self.peek() != ']':
                literal = self.take()
                if self.peek() != ']':
                    raise TypeNeedsReview('ARRAY_EXPRESSION_REVIEW')
                size = _length(literal)
            self.take(']')
            shape = ('array', size, shape)
            depth += 1
            if depth > MAX_DEPTH:
                raise TypeNeedsReview('TYPE_DEPTH_REVIEW')
        return shape


def source_shape(raw: bytes) -> tuple:
    """Return a structural type shape; no identifiers are executed/evaluated."""
    p = _Parser(raw)
    shape = p.typ()
    need(p.pos == len(p.tokens), 'TRAILING_TYPE_TOKENS')
    return shape


def _range(value: Any, raw: bytes, file_id: int) -> tuple[int, int]:
    need(type(value) is str and SPAN.fullmatch(value) is not None, 'TYPE_SOURCE_SPAN')
    start, length, index = map(int, value.split(':'))
    need(type(file_id) is int and index == file_id and length > 0 and start+length <= len(raw),
         'TYPE_SOURCE_RANGE')
    try:
        raw[:start].decode('utf-8')
        raw[start:start+length].decode('utf-8')
    except UnicodeError as exc:
        raise TypeBindingError('TYPE_SOURCE_UTF8') from exc
    return start, start+length


def ast_shape(node: Any, raw: bytes, file_id: int, bounds: tuple[int, int],
              *, depth: int = 0, budget: list[int] | None = None) -> tuple:
    if depth > MAX_DEPTH:
        raise TypeNeedsReview('TYPE_DEPTH_REVIEW')
    budget = [0] if budget is None else budget
    budget[0] += 1
    need(budget[0] <= MAX_NODES and type(node) is dict, 'TYPE_AST_BUDGET_OR_SCHEMA')
    start, end = _range(node.get('src'), raw, file_id)
    need(bounds[0] <= start < end <= bounds[1], 'TYPE_AST_SPAN_OUTSIDE_PARENT')
    kind = node.get('nodeType')
    if kind == 'ElementaryTypeName':
        mutability = node.get('stateMutability', 'nonpayable')
        need(mutability in ('nonpayable', 'payable'), 'ELEMENTARY_STATE_MUTABILITY')
        shape = _element(node.get('name'), payable=mutability == 'payable')
    elif kind == 'ArrayTypeName':
        child = ast_shape(node.get('baseType'), raw, file_id, (start, end), depth=depth+1, budget=budget)
        size_node = node.get('length')
        size = None
        if size_node is not None:
            need(type(size_node) is dict, 'ARRAY_LENGTH_AST')
            if size_node.get('nodeType') != 'Literal' or size_node.get('kind') != 'number':
                raise TypeNeedsReview('ARRAY_EXPRESSION_REVIEW')
            need(size_node.get('subdenomination') is None, 'ARRAY_LENGTH_UNIT')
            a, b = _range(size_node.get('src'), raw, file_id)
            need(start <= a < b <= end, 'ARRAY_LENGTH_SPAN')
            size = _length(size_node.get('value'))
            literal = _tokens(raw[a:b])
            need(len(literal) == 1 and _length(literal[0]) == size, 'ARRAY_LENGTH_SOURCE_MISMATCH')
        shape = ('array', size, child)
    elif kind == 'Mapping':
        key = ast_shape(node.get('keyType'), raw, file_id, (start,end), depth=depth+1, budget=budget)
        value = ast_shape(node.get('valueType'), raw, file_id, (start,end), depth=depth+1, budget=budget)
        need(key[0] == 'elementary', 'MAPPING_KEY_PROFILE')
        shape = ('mapping', key, value)
    else:
        raise TypeNeedsReview('TYPE_AST_OUTSIDE_PROFILE')
    # Parse source independently at every node. Child containment alone is not enough.
    need(source_shape(raw[start:end]) == shape, 'SOURCE_AST_TYPE_MISMATCH')
    return shape


def storage_shape(identifier: Any, types: Any, *, depth: int = 0,
                  active: set[str] | None = None) -> tuple:
    if depth > MAX_DEPTH:
        raise TypeNeedsReview('TYPE_DEPTH_REVIEW')
    need(type(types) is dict and type(identifier) is str and identifier in types, 'STORAGE_TYPE_REFERENCE')
    active = set() if active is None else active
    if identifier in active:
        raise TypeNeedsReview('RECURSIVE_TYPE_REVIEW')
    active.add(identifier)
    try:
        node = types[identifier]
        need(type(node) is dict and type(node.get('label')) is str, 'STORAGE_TYPE_SCHEMA')
        enc, label = node.get('encoding'), node['label']
        if enc == 'mapping':
            return ('mapping', storage_shape(node.get('key'),types,depth=depth+1,active=active),
                    storage_shape(node.get('value'),types,depth=depth+1,active=active))
        if enc == 'dynamic_array' or (enc == 'inplace' and 'base' in node):
            size = None
            if enc == 'inplace':
                match = re.search(r'\[([1-9][0-9]{0,77})\]\Z', label)
                need(match is not None, 'STORAGE_ARRAY_LENGTH')
                size = _length(match[1])
            return ('array', size, storage_shape(node.get('base'),types,depth=depth+1,active=active))
        if enc == 'inplace' and 'members' in node:
            raise TypeNeedsReview('STRUCT_TYPE_REVIEW')
        if enc in ('bytes','inplace'):
            payable = label == 'address payable'
            return _element('address' if payable else label, payable=payable)
        raise TypeNeedsReview('STORAGE_TYPE_OUTSIDE_PROFILE')
    finally:
        active.remove(identifier)


def bind_declaration(declaration: dict, row: dict, types: dict, source: bytes,
                     file_id: int) -> dict:
    """Compare one persistent declaration already bound by compiler_layout v2."""
    typ = declaration.get('typeName')
    need(type(typ) is dict, 'TYPE_AST_REQUIRED')
    a, b = _range(declaration.get('src'),source,file_id)
    n, _ = _range(declaration.get('nameLocation'),source,file_id)
    start, end = _range(typ.get('src'),source,file_id)
    need(a <= start < end <= n < b, 'TYPE_NOT_BEFORE_DECLARED_NAME')
    # Require the type to start the declaration, not a chosen later substring.
    # Source spans are supplied, so this is consistency, not AST authenticity.
    prefix = source[a:start]
    if prefix.strip():
        # Whitespace/comments only: append a marker and require only that token.
        need(_tokens(prefix+b'uint8') == ['uint8'], 'TYPE_NOT_AT_DECLARATION_START')
    suffix_tokens = _tokens(source[end:n]+b' uint8')[:-1]
    need(all(t in ('public','private','internal','override') for t in suffix_tokens),
         'TYPE_SUFFIX_NOT_SUPPORTED_MODIFIERS')
    need(len(suffix_tokens) == len(set(suffix_tokens)), 'DUPLICATE_TYPE_MODIFIER')
    witness = {'ast_id':declaration['id'], 'type_start_byte':start, 'type_length_bytes':end-start,
               'type_span_sha256':_hash(source[start:end])}
    try:
        from_ast = ast_shape(typ,source,file_id,(a,n))
        from_storage = storage_shape(row.get('type'),types)
        need(from_ast == from_storage, 'AST_STORAGE_TYPE_MISMATCH')
    except TypeNeedsReview as exc:
        return {**witness,'status':'TYPE_REVIEW_REQUIRED','reason':str(exc),'shape_sha256':None}
    return {**witness,'status':'TYPE_CONSISTENT_IN_PROFILE','reason':None,
            'shape_sha256':_hash(canonical(from_ast))}
