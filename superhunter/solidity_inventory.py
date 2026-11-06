"""Read a bounded Solidity state-declaration inventory directly from source bytes.

NOT a compiler or complete Solidity grammar. A single ordinary contract and the
explicit type subset are supported. Function bodies are balanced opaque regions,
not analyzed statements; inherited/custom-layout/imported sources require review.
A supplied AST cannot establish completeness by agreeing with a supplied layout.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import re
from typing import Any

from . import source_types
from .safe_io import canonical

MAX_BYTES = 1_000_000
MAX_TOKENS = 100_000
MAX_DEPTH = 64
MAX_DECLARATIONS = 2048
IDENT = re.compile(rb'[A-Za-z_$][A-Za-z0-9_$]*')
NUMBER = re.compile(rb'(?:0[xX][0-9a-fA-F_]+|[0-9][0-9_]*(?:\.[0-9_]+)?(?:[eE][+-]?[0-9_]+)?)')
WHITESPACE = b' \t\r\n\v\f'
PAIRS = {'(': ')', '[': ']', '{': '}'}
CLOSE = set(PAIRS.values())
RESERVED_NAMES = {'contract','abstract','pragma','function','constructor','modifier',
                  'mapping','struct','enum','uint','int','bool','address','bytes','string',
                  'return','if','else','while','for','public','private','internal',
                  'external','constant','immutable','transient','true','false'}


class InventoryError(ValueError):
    """Fixed diagnostic codes; never echo submitted source or labels."""


class InventoryNeedsReview(InventoryError):
    """Unsupported syntax is explicitly inconclusive, never silently omitted."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise InventoryError(code)


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    start: int
    end: int


def tokenize(raw: bytes) -> list[Token]:
    need(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, 'SOURCE_INVENTORY_BYTE_BUDGET')
    try:
        raw.decode('utf-8', errors='strict')
    except UnicodeError as exc:
        raise InventoryError('SOURCE_INVENTORY_UTF8') from exc
    out = []; i = 0
    while i < len(raw):
        b = raw[i]
        if b in WHITESPACE:
            i += 1; continue
        if raw[i:i+2] == b'//':
            i += 2
            while i < len(raw) and raw[i] not in b'\r\n':
                i += 1
            continue
        if raw[i:i+2] == b'/*':
            end = raw.find(b'*/', i+2)
            need(end != -1, 'UNTERMINATED_SOURCE_COMMENT')
            i = end+2; continue
        if b in (34, 39):
            # Store no string value. Delimiters inside strings are not structure.
            start = i; quote = b; i += 1
            while i < len(raw) and raw[i] != quote:
                need(raw[i] not in b'\r\n', 'UNESCAPED_STRING_NEWLINE')
                if raw[i] == 92:
                    i += 1
                    need(i < len(raw), 'UNTERMINATED_SOURCE_STRING')
                    if raw[i:i+2] == b'\r\n':
                        i += 1
                i += 1
            need(i < len(raw), 'UNTERMINATED_SOURCE_STRING')
            i += 1; out.append(Token('string', '<string>', start, i))
        else:
            match = IDENT.match(raw, i)
            if match:
                out.append(Token('identifier', match[0].decode('ascii'), i, match.end())); i = match.end()
            else:
                match = NUMBER.match(raw, i)
                if match:
                    out.append(Token('number', match[0].decode('ascii'), i, match.end())); i = match.end()
                elif raw[i:i+2] == b'=>':
                    out.append(Token('symbol', '=>', i, i+2)); i += 2
                elif 32 <= b < 127 and chr(b) in '{}[]();,:.=+-*/%^&|!<>?~':
                    out.append(Token('symbol', chr(b), i, i+1)); i += 1
                else:
                    raise InventoryNeedsReview('SOURCE_CHARACTER_OUTSIDE_PROFILE')
        need(len(out) <= MAX_TOKENS, 'SOURCE_INVENTORY_TOKEN_BUDGET')
    need(bool(out), 'EMPTY_SOURCE_INVENTORY')
    return out


class _Parser:
    def __init__(self, raw: bytes):
        self.raw = raw; self.tokens = tokenize(raw); self.pos = 0
        self.opaque = Counter()

    def peek(self) -> str | None:
        return self.tokens[self.pos].text if self.pos < len(self.tokens) else None

    def take(self, text: str | None = None) -> Token:
        need(self.pos < len(self.tokens), 'UNEXPECTED_SOURCE_END')
        t = self.tokens[self.pos]
        need(text is None or t.text == text, 'SOURCE_MEMBER_SYNTAX')
        self.pos += 1
        return t

    def identifier(self) -> Token:
        t = self.take()
        need(t.kind == 'identifier' and t.text not in RESERVED_NAMES, 'SOURCE_MEMBER_IDENTIFIER')
        return t

    def balanced(self, opening: str) -> Token:
        self.take(opening); stack = [PAIRS[opening]]
        while stack:
            t = self.take()
            if t.kind == 'symbol' and t.text in PAIRS:
                stack.append(PAIRS[t.text]); need(len(stack) <= MAX_DEPTH, 'SOURCE_NESTING_BUDGET')
            elif t.kind == 'symbol' and t.text in CLOSE:
                need(t.text == stack[-1], 'UNBALANCED_SOURCE_DELIMITER')
                stack.pop()
        return t

    def type_span(self, depth: int = 0) -> tuple[int, int]:
        need(depth <= 24, 'SOURCE_TYPE_DEPTH')
        first = self.take(); need(first.kind == 'identifier', 'SOURCE_TYPE_EXPECTED')
        if first.text == 'mapping':
            self.take('('); self.type_span(depth+1)
            if self.peek() != '=>': self.identifier()
            self.take('=>'); self.type_span(depth+1)
            if self.peek() != ')': self.identifier()
            self.take(')')
        else:
            if first.text == 'address' and self.peek() == 'payable': self.take()
            try:
                source_types.source_shape(self.raw[first.start:self.tokens[self.pos-1].end])
            except source_types.TypeNeedsReview as exc:
                raise InventoryNeedsReview('STATE_TYPE_OUTSIDE_INVENTORY_PROFILE') from exc
        while self.peek() == '[':
            self.take()
            if self.peek() != ']':
                length = self.take()
                if length.kind != 'number' or self.peek() != ']':
                    raise InventoryNeedsReview('ARRAY_LENGTH_OUTSIDE_INVENTORY_PROFILE')
            self.take(']')
        return first.start, self.tokens[self.pos-1].end

    def opaque_member(self) -> None:
        kind = self.take().text
        if kind in ('struct','enum'):
            self.identifier(); self.balanced('{')
        elif kind in ('event','error'):
            self.identifier(); self.balanced('(')
            if kind == 'event' and self.peek() == 'anonymous': self.take()
            self.take(';')
        else:
            if kind in ('function','modifier'):
                if self.peek() == '(':
                    raise InventoryNeedsReview('FUNCTION_TYPE_STATE_REVIEW')
                self.identifier()
            if self.peek() == '(':
                self.balanced('(')
            elif kind != 'modifier':
                raise InventoryError('CALLABLE_PARAMETER_LIST')
            # Headers and bodies are OPAQUE. Only balanced structural boundaries
            # are checked; no Solidity semantics or method AST correspondence.
            while self.peek() not in ('{',';'):
                if self.peek() == '(':
                    self.balanced('(')
                elif self.peek() in (None, '}', '=', '['):
                    raise InventoryNeedsReview('CALLABLE_HEADER_OUTSIDE_PROFILE')
                else:
                    self.take()
            if self.peek() == ';':
                self.take()
            else:
                self.balanced('{')
        self.opaque[kind] += 1

    def declaration(self) -> dict:
        start, type_end = self.type_span()
        try:
            shape = source_types.source_shape(self.raw[start:type_end])
        except source_types.TypeNeedsReview as exc:
            raise InventoryNeedsReview('STATE_TYPE_OUTSIDE_INVENTORY_PROFILE') from exc
        visibility = 'internal'; storage = 'default'; mutability = 'mutable'; seen = set()
        qualifiers = {'public','internal','private','constant','immutable','transient'}
        while self.peek() in qualifiers:
            word = self.take().text
            group = ('visibility' if word in ('public','internal','private') else
                     'storage' if word == 'transient' else 'mutability')
            need(group not in seen, 'DUPLICATE_STATE_QUALIFIER'); seen.add(group)
            if group == 'visibility': visibility = word
            elif group == 'storage': storage = word
            else: mutability = word
        need(storage == 'default' or mutability == 'mutable', 'STATE_QUALIFIER_CONFLICT')
        if self.peek() == 'override':
            raise InventoryNeedsReview('OVERRIDE_DECLARATION_REVIEW')
        name = self.identifier()
        initialized = False
        if self.peek() == '=':
            self.take(); initialized = True
            # Only simple literals here; no initializer expression interpretation.
            if self.peek() in ('+','-'): self.take()
            if self.peek() in ('hex','unicode'): self.take()
            literal = self.take()
            if literal.kind not in ('number','string') and literal.text not in ('true','false'):
                raise InventoryNeedsReview('INITIALIZER_EXPRESSION_REVIEW')
            if self.peek() != ';':
                raise InventoryNeedsReview('INITIALIZER_EXPRESSION_REVIEW')
        need(mutability != 'constant' or initialized, 'CONSTANT_INITIALIZER_REQUIRED')
        last = self.tokens[self.pos-1].end
        semi = self.take(';')
        return {'name': name.text, 'name_start': name.start, 'name_end': name.end,
                'start': start, 'type_end': type_end, 'last_end': last,
                'semicolon_start': semi.start, 'end': semi.end, 'shape': shape,
                'visibility': visibility, 'mutability': mutability, 'storage': storage,
                'initializer_present': initialized}

    def parse(self, expected: str) -> dict:
        while self.peek() == 'pragma':
            self.take(); pragma = self.take()
            if pragma.text not in ('solidity','abicoder'):
                raise InventoryNeedsReview('PRAGMA_OUTSIDE_INVENTORY_PROFILE')
            count = 0
            while self.peek() != ';':
                token = self.take(); count += 1
                need(count <= 64 and token.kind != 'string' and token.text not in ('{','}','[',']','(',')'),
                     'PRAGMA_SYNTAX_OUTSIDE_PROFILE')
            need(count > 0, 'EMPTY_PRAGMA'); self.take(';')
        if self.peek() not in ('contract','abstract'):
            raise InventoryNeedsReview('SOURCE_UNIT_OUTSIDE_INVENTORY_PROFILE')
        first = self.take()
        if first.text == 'abstract': self.take('contract')
        name = self.identifier()
        need(name.text == expected, 'SOURCE_CONTRACT_NAME_MISMATCH')
        if self.peek() != '{':
            raise InventoryNeedsReview('CONTRACT_HEADER_INVENTORY_REVIEW')
        self.take('{'); declarations = []; names = set()
        supported_opaque = {'function','constructor','receive','fallback','modifier','event','error','struct','enum'}
        while self.peek() != '}':
            need(self.peek() is not None, 'UNTERMINATED_CONTRACT')
            if self.peek() in supported_opaque:
                self.opaque_member()
            elif self.peek() in ('using','type','contract','interface','library','import'):
                raise InventoryNeedsReview('CONTRACT_MEMBER_OUTSIDE_PROFILE')
            else:
                record = self.declaration()
                need(record['name'] not in names, 'DUPLICATE_SOURCE_STATE_NAME')
                names.add(record['name']); declarations.append(record)
                need(len(declarations) <= MAX_DECLARATIONS, 'SOURCE_DECLARATION_BUDGET')
        end = self.take('}').end
        if self.pos != len(self.tokens):
            raise InventoryNeedsReview('ADDITIONAL_SOURCE_UNIT_MEMBERS')
        return {'start':first.start,'end':end,'name':name.text,'declarations':declarations,
                'opaque_members':dict(sorted(self.opaque.items()))}


def parse_source(raw: bytes, contract_name: str) -> dict:
    """Parse a declaration-boundary subset, never execute Solidity or expressions."""
    need(type(contract_name) is str and re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_$]*', contract_name) is not None,
         'CONTRACT_IDENTIFIER')
    return _Parser(raw).parse(contract_name)


def _span(value: Any, raw: bytes, file_id: int) -> tuple[int,int]:
    need(type(value) is str and re.fullmatch(r'[0-9]{1,10}:[0-9]{1,10}:[0-9]{1,10}', value) is not None,
         'INVENTORY_AST_SPAN')
    a, n, f = map(int, value.split(':'))
    need(f == file_id and n > 0 and a+n <= len(raw), 'INVENTORY_AST_RANGE')
    return a, a+n


def verify_declarations(raw: bytes, contract: dict, file_id: int, compiler_version: str) -> dict:
    """Full source scan first; compare ALL state declarations, even nonpersistent.

    Completeness means outer state declarations within this lexical profile.
    It does not mean AST authenticity, full syntax checking or compilation.
    """
    need(type(raw) is bytes and type(compiler_version) is str and
         type(file_id) is int and file_id >= 0 and type(contract) is dict, 'INVENTORY_INPUT')
    facts = {'profile':'single-contract-source-state-inventory-v1',
             'source_sha256': hashlib.sha256(raw).hexdigest(),
             'status':'DECLARATION_INVENTORY_REVIEW_REQUIRED','all_source_state_declarations_matched':False,
             'full_solidity_syntax_checked':False,'function_bodies_analyzed':False,
             'compiler_execution_authenticated':False,'source_declarations':None,
             'records':[], 'opaque_members':{}, 'review_reasons':[]}
    if compiler_version.split('+',1)[0] != '0.8.30':
        facts['review_reasons']=['COMPILER_VERSION_OUTSIDE_INVENTORY_PROFILE']; return facts
    if contract.get('baseContracts') or contract.get('storageLayout') is not None:
        facts['review_reasons']=['INHERITED_OR_CUSTOM_LAYOUT_REVIEW']; return facts
    try:
        parsed = parse_source(raw, contract.get('name'))
    except (InventoryNeedsReview, source_types.TypeNeedsReview) as exc:
        facts['review_reasons']=[str(exc)]; return facts
    need(_span(contract.get('src'),raw,file_id) == (parsed['start'],parsed['end']), 'CONTRACT_SOURCE_BOUNDARY_MISMATCH')
    need(type(contract.get('nodes')) is list, 'INVENTORY_CONTRACT_NODES')
    ast = [n for n in contract['nodes'] if type(n) is dict and n.get('nodeType')=='VariableDeclaration']
    need(len(ast)==len(parsed['declarations']), 'SOURCE_AST_DECLARATION_SET_MISMATCH')
    indexed = {}
    for n in ast:
        need(n.get('stateVariable') is True, 'SOURCE_AST_STATE_CLASSIFICATION')
        key = _span(n.get('nameLocation'),raw,file_id)
        need(key not in indexed, 'DUPLICATE_AST_NAME_SPAN'); indexed[key] = n
    records = []
    for d in parsed['declarations']:
        key = (d['name_start'],d['name_end']); n = indexed.pop(key,None)
        need(n is not None and n.get('name')==d['name'], 'SOURCE_AST_DECLARATION_SET_MISMATCH')
        a, b = _span(n.get('src'),raw,file_id)
        need(a==d['start'] and b in (d['last_end'], d['semicolon_start'], d['end']), 'SOURCE_AST_DECLARATION_BOUNDARY')
        need(type(n.get('typeName')) is dict, 'INVENTORY_TYPE_AST_REQUIRED')
        need(_span(n['typeName'].get('src'),raw,file_id)==(d['start'],d['type_end']), 'SOURCE_AST_TYPE_BOUNDARY')
        need(n.get('mutability')==d['mutability'] and n.get('constant') is (d['mutability']=='constant') and
             n.get('storageLocation')==d['storage'], 'SOURCE_AST_STATE_QUALIFIER_MISMATCH')
        need(n.get('visibility','internal')==d['visibility'], 'SOURCE_AST_VISIBILITY_MISMATCH')
        if 'value' in n:
            need((n['value'] is not None)==d['initializer_present'], 'SOURCE_AST_INITIALIZER_PRESENCE')
        # Check nonpersistent declaration type ASTs too, not only rows in layout.
        shape = source_types.ast_shape(n.get('typeName'),raw,file_id,(d['start'],d['type_end']))
        need(shape==d['shape'], 'SOURCE_AST_INVENTORY_TYPE_MISMATCH')
        records.append({'ast_id':n['id'],'name_sha256':hashlib.sha256(d['name'].encode()).hexdigest(),
                        'start_byte':d['start'],'end_byte':d['end'],
                        'name_start_byte':d['name_start'],'type_end_byte':d['type_end'],
                        'classification':d['storage'] if d['storage']=='transient' else d['mutability'],
                        'type_sha256':hashlib.sha256(canonical(d['shape'])).hexdigest()})
    need(not indexed, 'SOURCE_AST_DECLARATION_SET_MISMATCH')
    facts.update(status='SOURCE_DECLARATION_INVENTORY_MATCHED', all_source_state_declarations_matched=True,
                 source_declarations=len(records),records=records,opaque_members=parsed['opaque_members'])
    return facts
