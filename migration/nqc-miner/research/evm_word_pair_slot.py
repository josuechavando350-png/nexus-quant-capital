"""Ethereum Keccak-256 of exactly two ABI uint256 words, for research storage keys.

This single-rate-block implementation is cross-checked against Alloy in the Rust
execution tests. It does not use SHA3-256, whose domain padding differs.
"""
MASK = (1 << 64) - 1
ROT = [0,1,62,28,27,36,44,6,55,20,3,10,43,25,39,41,45,15,21,8,18,2,61,56,14]
RC = [0x1,0x8082,0x800000000000808a,0x8000000080008000,0x808b,0x80000001,
      0x8000000080008081,0x8000000000008009,0x8a,0x88,0x80008009,0x8000000a,
      0x8000808b,0x800000000000008b,0x8000000000008089,0x8000000000008003,
      0x8000000000008002,0x8000000000000080,0x800a,0x800000008000000a,
      0x8000000080008081,0x8000000000008080,0x80000001,0x8000000080008008]


def word_pair_slot(key, slot):
    if not all(type(v) is int and 0 <= v < 2**256 for v in [key,slot]):
        raise ValueError('uint256 words required')
    message=key.to_bytes(32,'big')+slot.to_bytes(32,'big')+b'\x01'+bytes(70)+b'\x80'
    a=[int.from_bytes(message[i:i+8],'little') for i in range(0,136,8)]+[0]*8
    def rol(v,n): return ((v<<n)|(v>>(64-n)))&MASK
    for rc in RC:
        c=[a[x]^a[x+5]^a[x+10]^a[x+15]^a[x+20] for x in range(5)]
        d=[c[(x-1)%5]^rol(c[(x+1)%5],1) for x in range(5)]
        a=[v^d[i%5] for i,v in enumerate(a)]; b=[0]*25
        for y in range(5):
            for x in range(5): b[y+5*((2*x+3*y)%5)]=rol(a[x+5*y],ROT[x+5*y])
        a=[b[x+5*y]^((~b[(x+1)%5+5*y])&b[(x+2)%5+5*y]) for y in range(5) for x in range(5)]
        a[0]^=rc
    return '0x'+b''.join(v.to_bytes(8,'little') for v in a[:4]).hex()
