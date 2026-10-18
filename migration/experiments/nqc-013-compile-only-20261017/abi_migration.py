"""NQC research-only ABI migration; no signer, network client or admission authority.

Only the exact two static Plan layouts in source/ are supported. Ethereum
Keccak-256 is implemented separately from hashlib.sha3_256 (different padding).
Compile and compare against solc methodIdentifiers before any EVM use.
"""
from __future__ import annotations
from dataclasses import dataclass
import re

MASK = (1 << 64) - 1
RC = (0x0000000000000001,0x0000000000008082,0x800000000000808a,0x8000000080008000,
      0x000000000000808b,0x0000000080000001,0x8000000080008081,0x8000000000008009,
      0x000000000000008a,0x0000000000000088,0x0000000080008009,0x000000008000000a,
      0x000000008000808b,0x800000000000008b,0x8000000000008089,0x8000000000008003,
      0x8000000000008002,0x8000000000000080,0x000000000000800a,0x800000008000000a,
      0x8000000080008081,0x8000000000008080,0x0000000080000001,0x8000000080008008)
ROT = ((0,36,3,41,18),(1,44,10,45,2),(62,6,43,15,61),(28,55,25,21,56),(27,20,39,8,14))

def keccak256(data: bytes) -> bytes:
    if type(data) is not bytes: raise TypeError('bytes required')
    rate = 136
    pad = rate - (len(data) % rate)
    msg = data + (b'\x81' if pad == 1 else b'\x01' + b'\0'*(pad-2) + b'\x80')
    state = [0]*25
    def rol(x: int, n: int) -> int:
        return ((x << n) | (x >> ((64-n) % 64))) & MASK
    for off in range(0,len(msg),rate):
        for i in range(rate//8):
            state[i] ^= int.from_bytes(msg[off+8*i:off+8*i+8], 'little')
        for rc in RC:
            c = [state[x]^state[x+5]^state[x+10]^state[x+15]^state[x+20] for x in range(5)]
            d = [c[(x-1)%5]^rol(c[(x+1)%5],1) for x in range(5)]
            for x in range(5):
                for y in range(5): state[x+5*y] ^= d[x]
            b = [0]*25
            for x in range(5):
                for y in range(5): b[y+5*((2*x+3*y)%5)] = rol(state[x+5*y],ROT[x][y])
            for x in range(5):
                for y in range(5): state[x+5*y] = b[x+5*y]^((~b[(x+1)%5+5*y])&b[(x+2)%5+5*y])
            state[0] ^= rc
    return b''.join(x.to_bytes(8,'little') for x in state)[:32]

MARKET = '(address,address,address,address,uint256)'
# market + borrower + seven uint256 + sponsor address + sponsor amount
PLAN_OLD = '(' + MARKET + ',address,' + ','.join(['uint256']*7) + ',address,uint256)'
PLAN_NEW = PLAN_OLD[:-1] + ',address,uint8)'
SIG_OLD = f'execute({PLAN_OLD},bytes,bytes)'
SIG_NEW = f'execute({PLAN_NEW},bytes,bytes)'


def selector(signature: str) -> bytes:
    return keccak256(signature.encode('ascii'))[:4]

def uint(value: int, bits: int = 256) -> int:
    if type(value) is not int or not 0 <= value < (1 << bits):
        raise ValueError(f'exact uint{bits} required')
    return value

def word(value: int) -> bytes:
    return uint(value).to_bytes(32,'big')

def address_word(value: str) -> bytes:
    if type(value) is not str or not re.fullmatch(r'0x[0-9a-fA-F]{40}',value):
        raise ValueError('20-byte hexadecimal address required')
    return word(int(value,16))

@dataclass(frozen=True)
class Decoded:
    words: tuple[int,...]
    collateral_route: bytes
    weth_route: bytes

def _dynamic(data: bytes) -> bytes:
    if type(data) is not bytes: raise TypeError('route must be bytes')
    return word(len(data)) + data + b'\0'*((-len(data))%32)

def encode_raw(plan_words: tuple[int,...], route: bytes, weth_route: bytes, *, new: bool) -> bytes:
    count = 17 if new else 15
    if len(plan_words) != count: raise ValueError('wrong static Plan width')
    for v in plan_words: uint(v)
    for i in (0,1,2,3,5,13): uint(plan_words[i],160)
    if new:
        uint(plan_words[15],160)
        if plan_words[16] not in (0,1): raise ValueError('invalid layout enum')
    a,b = _dynamic(route), _dynamic(weth_route)
    head = (count+2)*32
    return selector(SIG_NEW if new else SIG_OLD)+b''.join(word(x) for x in plan_words)+word(head)+word(head+len(a))+a+b

def decode_raw(payload: bytes, *, new: bool) -> Decoded:
    if type(payload) is not bytes: raise TypeError('payload must be bytes')
    n = 17 if new else 15; head = (n+2)*32
    if payload[:4] != selector(SIG_NEW if new else SIG_OLD): raise ValueError('wrong selector/version')
    body = payload[4:]
    if len(body) < head+64 or len(body)%32: raise ValueError('truncated/unaligned payload')
    w = tuple(int.from_bytes(body[32*i:32*i+32],'big') for i in range(n))
    o1 = int.from_bytes(body[32*n:32*n+32],'big'); o2 = int.from_bytes(body[32*(n+1):head],'big')
    def read_dynamic(offset: int) -> bytes:
        if offset < head or offset%32 or offset+32 > len(body): raise ValueError('bad dynamic offset')
        size=int.from_bytes(body[offset:offset+32],'big')
        if offset+32+size > len(body): raise ValueError('truncated route')
        return body[offset+32:offset+32+size]
    r1,r2=read_dynamic(o1),read_dynamic(o2)
    # Reject aliases, nonzero padding, trailing data and noncanonical encodings.
    if encode_raw(w,r1,r2,new=new)!=payload: raise ValueError('noncanonical payload')
    return Decoded(w,r1,r2)

def migrate(payload: bytes, *, expected_fee_recipient: str, shared: bool) -> bytes:
    if type(shared) is not bool: raise ValueError('explicit boolean mode required')
    decoded=decode_raw(payload,new=False)
    address=int.from_bytes(address_word(expected_fee_recipient),'big')
    if address == 0: raise ValueError('zero expected fee recipient')
    sponsor=decoded.words[13]
    if sponsor == 0: raise ValueError('zero sponsor')
    if (sponsor==address) != shared: raise ValueError('mode does not match recipients')
    return encode_raw(decoded.words+(address,int(shared)),decoded.collateral_route,decoded.weth_route,new=True)

def validate_compiler_abi(abi: list, identifiers: dict, *, new: bool) -> None:
    def canonical(item):
        if item['type'].startswith('tuple'):
            return '('+','.join(canonical(c) for c in item['components'])+')'+item['type'][5:]
        return item['type']
    calls=[x for x in abi if x.get('type')=='function' and x.get('name')=='execute']
    if len(calls)!=1: raise ValueError('compiler ABI: expected one execute')
    actual='execute('+','.join(canonical(x) for x in calls[0]['inputs'])+')'
    expected=SIG_NEW if new else SIG_OLD
    if actual!=expected or identifiers.get(actual)!=selector(expected).hex():
        raise ValueError('compiler ABI/selector differs from encoder')
