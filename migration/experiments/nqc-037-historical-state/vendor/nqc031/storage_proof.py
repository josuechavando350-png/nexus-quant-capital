#!/usr/bin/env python3
"""Offline EIP-1186 verification RELATIVE TO a supplied root, not chain anchoring.

No network client, proof generation, root discovery, consensus or Nitro execution.
Reference: https://eips.ethereum.org/EIPS/eip-1186 .
"""
import argparse
from pathlib import Path
from util import read,save,require,k256,unhex,quantity

def rlp_encode(x):
    if isinstance(x,list):raw=b''.join(rlp_encode(v) for v in x);offset=0xc0
    else:
        require(isinstance(x,bytes),'RLP accepts bytes or lists');raw=x;offset=0x80
        if len(raw)==1 and raw[0]<0x80:return raw
    if len(raw)<56:return bytes([offset+len(raw)])+raw
    n=len(raw).to_bytes((len(raw).bit_length()+7)//8,'big')
    return bytes([offset+55+len(n)])+n+raw

def rlp_decode(raw):
    require(isinstance(raw,bytes) and 0<len(raw)<=1048576,'RLP size limit')
    def parse(at,end,depth):
        require(depth<=64 and at<end,'RLP depth or truncated input')
        prefix=raw[at];at+=1
        if prefix<128:return bytes([prefix]),at
        is_list=prefix>=192;offset=192 if is_list else 128
        length=prefix-offset
        if length>55:
            n=length-55;require(at+n<=end and raw[at]!=0,'RLP length encoding')
            length=int.from_bytes(raw[at:at+n],'big');at+=n;require(length>=56,'noncanonical RLP long length')
        finish=at+length;require(finish<=end,'truncated RLP payload')
        if not is_list:
            require(length!=1 or raw[at]>=128,'noncanonical RLP single byte');return raw[at:finish],finish
        values=[]
        while at<finish:
            value,at=parse(at,finish,depth+1);values.append(value)
        return values,finish
    value,end=parse(0,len(raw),0);require(end==len(raw),'RLP trailing bytes');return value

EMPTY_ROOT=k256(rlp_encode(b''))
EMPTY_CODE_HASH=k256(b'')
def nibbles(raw):return tuple(n for b in raw for n in (b>>4,b&15))
def compact_path(raw):
    require(isinstance(raw,bytes) and raw,'missing compact path');digits=nibbles(raw);flag=digits[0]
    require(flag<=3,'invalid compact path flag')
    if flag%2:path=digits[1:]
    else:
        require(digits[1]==0,'invalid even compact padding');path=digits[2:]
    return bool(flag&2),path

def trie_value(root,key,proof):
    """Return included value or None for proven absence; reject incomplete proofs."""
    require(len(root)==32 and isinstance(key,bytes) and len(key)<=128,'invalid trie root/key')
    require(isinstance(proof,list) and len(proof)<=256,'proof node count limit')
    require(all(isinstance(n,bytes) for n in proof) and sum(map(len,proof))<=4*1048576,'proof size limit')
    if root==EMPTY_ROOT:
        require(not proof or proof==[rlp_encode(b'')],'unexpected empty-root proof');return None
    table={k256(n):n for n in proof};require(len(table)==len(proof),'duplicate proof node')
    path=nibbles(key);ref=root
    for step in range(257):
        if ref==b'':return None
        if isinstance(ref,list):
            require(len(rlp_encode(ref))<32,'oversized inline child');node=ref
        else:
            require(isinstance(ref,bytes) and len(ref)==32,'invalid hashed reference')
            require(ref in table,'incomplete proof: missing node');raw=table[ref]
            require(step==0 or len(raw)>=32,'hashed short child');node=rlp_decode(raw)
        require(isinstance(node,list) and len(node) in (2,17),'invalid trie node arity')
        if len(node)==17:
            require(isinstance(node[16],bytes),'branch value must be bytes')
            if not path:return node[16] or None
            ref=node[path[0]];path=path[1:];continue
        leaf,fragment=compact_path(node[0])
        require(leaf or bool(fragment),'empty extension path')
        if path[:len(fragment)]!=fragment:return None
        path=path[len(fragment):]
        if leaf:
            require(isinstance(node[1],bytes) and bool(node[1]),'invalid leaf value')
            return node[1] if not path else None
        ref=node[1];require(ref!=b'','empty extension child')
    raise ValueError('trie traversal limit')

def uint(raw):
    require(isinstance(raw,bytes) and len(raw)<=32 and (not raw or raw[0]!=0),'noncanonical trie integer')
    return int.from_bytes(raw,'big')

def verify(root,proof):
    address=unhex(proof['address'],20)
    account=trie_value(root,k256(address),[unhex(x) for x in proof['accountProof']])
    if account is None:nonce,balance,storage_root,code_hash=0,0,EMPTY_ROOT,EMPTY_CODE_HASH
    else:
        fields=rlp_decode(account);require(isinstance(fields,list) and len(fields)==4,'bad account encoding')
        nonce,balance=uint(fields[0]),uint(fields[1]);storage_root,code_hash=fields[2:]
        require(isinstance(storage_root,bytes) and len(storage_root)==32 and isinstance(code_hash,bytes) and len(code_hash)==32,'bad account roots')
    require(quantity(proof['nonce'])==nonce and quantity(proof['balance'])==balance,'account fields mismatch')
    require(unhex(proof['storageHash'],32)==storage_root and unhex(proof['codeHash'],32)==code_hash,'account root/hash mismatch')
    require(isinstance(proof['storageProof'],list) and len(proof['storageProof'])<=1024,'storage proof count limit')
    seen=set();values={}
    for item in proof['storageProof']:
        slot=quantity(item['key']);require(slot not in seen,'duplicate storage slot');seen.add(slot)
        value=trie_value(storage_root,k256(slot.to_bytes(32,'big')),[unhex(x) for x in item['proof']])
        n=0 if value is None else uint(rlp_decode(value))
        require(n==quantity(item['value']),'storage value mismatch');values['0x'+slot.to_bytes(32,'big').hex()]=str(n)
    return {'status':'PROOF_VERIFIED_RELATIVE_TO_SUPPLIED_ROOT','address':proof['address'],
            'supplied_state_root':'0x'+root.hex(),'code_hash':'0x'+code_hash.hex(),'storage_values':values,
            'canonical_root_authenticated':False,'historical_position_authenticated':False,
            'nitro_prefix_replayed':False,'commercial_admission':False}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state-root',required=True);p.add_argument('--proof',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    require(not a.out.exists(),'fresh output required');proof=read(a.proof);result=verify(unhex(a.state_root,32),proof.get('result',proof));save(a.out,result);print(result['status'])
if __name__=='__main__':main()
