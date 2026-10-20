"""Offline integrity of preserved headers and transaction encodings, not consensus proof."""
from pathlib import Path
import hashlib, json, subprocess, sys
HERE=Path(__file__).resolve().parent

def ib(n): return n.to_bytes((n.bit_length()+7)//8,'big')
def hb(s): return bytes.fromhex(s[2:])
def rlp(x):
    if isinstance(x,int):return rlp(ib(x))
    if isinstance(x,list):
        b=b''.join(rlp(v) for v in x); offset=192
    else:
        b=x;offset=128
        if len(b)==1 and b[0]<128:return b
    if len(b)<56:return bytes([offset+len(b)])+b
    l=ib(len(b));return bytes([offset+55+len(l)])+l+b

def keccak(b,cast):
    return hb(subprocess.check_output([str(cast),'keccak','0x'+b.hex()],text=True).strip())

def tx_bytes(t):
    typ=int(t.get('type','0x0'),16)
    fields=[]
    if typ==2:
        fields=[int(t[k],16) for k in ['chainId','nonce','maxPriorityFeePerGas','maxFeePerGas','gas']]
    elif typ==0:fields=[int(t[k],16) for k in ['nonce','gasPrice','gas']]
    else:raise ValueError('Unsupported transaction type '+str(typ))
    fields += [hb(t['to']) if t.get('to') else b'',int(t['value'],16),hb(t['input'])]
    if typ==2:fields += [[[hb(a['address']),[hb(k) for k in a['storageKeys']]] for a in t['accessList']]]
    fields += [int(t.get('yParity',t['v']),16) if typ==2 else int(t['v'],16),int(t['r'],16),int(t['s'],16)]
    return (bytes([typ]) if typ else b'')+rlp(fields)

def header_bytes(h):
    binary={'parentHash','sha3Uncles','miner','stateRoot','transactionsRoot','receiptsRoot','logsBloom','extraData','mixHash','nonce','withdrawalsRoot','parentBeaconBlockRoot','requestsHash'}
    keys=['parentHash','sha3Uncles','miner','stateRoot','transactionsRoot','receiptsRoot','logsBloom','difficulty','number','gasLimit','gasUsed','timestamp','extraData','mixHash','nonce','baseFeePerGas','withdrawalsRoot','blobGasUsed','excessBlobGas','parentBeaconBlockRoot','requestsHash']
    return rlp([hb(h[k]) if k in binary else int(h[k],16) for k in keys if k in h])

def compact(nibbles,leaf):
    odd=len(nibbles)%2;ns=[2*int(leaf)+odd]+([] if odd else [0])+nibbles
    return bytes(ns[i]*16+ns[i+1] for i in range(0,len(ns),2))

def trie_node(pairs,cast):
    if len(pairs)==1:
        key,value=pairs[0];return [compact(key,True),value]
    common=0
    while all(len(k)>common for k,v in pairs) and len({k[common] for k,v in pairs})==1:common+=1
    if common:
        child=trie_node([(k[common:],v) for k,v in pairs],cast)
        encoded=rlp(child);ref=child if len(encoded)<32 else keccak(encoded,cast)
        return [compact(pairs[0][0][:common],False),ref]
    node=[b'']*17
    for i in range(16):
        subset=[(k[1:],v) for k,v in pairs if k and k[0]==i]
        if subset:
            child=trie_node(subset,cast);encoded=rlp(child)
            node[i]=child if len(encoded)<32 else keccak(encoded,cast)
    for k,v in pairs:
        if not k:node[16]=v
    return node

def run(cast):
    prior=HERE/'evidence/prior_run'
    rows=[json.loads(s) for s in (prior/'rpc_history.jsonl').read_text().splitlines()]
    data={}
    for row in rows:
        raw=row['raw_response_text'].encode()
        assert hashlib.sha256(raw).hexdigest()==row['sha256']
        assert len(raw)==row['body_bytes']
        q=row['request'];data[(q['method'],json.dumps(q['params']))]=json.loads(raw)['result']
    def get(m,p):return data[(m,json.dumps(p))]
    report={'schema':'nqc068-offline-wire-integrity-v1','headers':[],'transactions':[],
            'consensus_finality_independently_verified':False,'receipt_trie_inclusion_verified':False,
            'complete_state_witness':False,'evm_replay':False}
    for n in [21762896,21762897]:
        h=get('eth_getBlockByNumber',[hex(n),False]);enc=header_bytes(h);computed='0x'+keccak(enc,cast).hex()
        report['headers'].append({'number':n,'hash':h['hash'],'computed_hash':computed,'match':computed==h['hash'],'state_root':h['stateRoot']})
        assert computed==h['hash']
    hashes=['0x85f35a2fffc14c6a0b5744401b31ec3ff902f5981ff78d42af1a82f81c084595','0x2a8880470bddca62a3b10586e1c65bd760c5a0d65da03d55cde94d0d709ed1eb']
    out=HERE/'evidence/offline';out.mkdir(exist_ok=True)
    for i,txhash in enumerate(hashes):
        t=get('eth_getTransactionByHash',[txhash]);enc=tx_bytes(t);computed='0x'+keccak(enc,cast).hex()
        assert computed==txhash
        decoded=json.loads(subprocess.check_output([str(cast),'decode-transaction','0x'+enc.hex(),'--json'],text=True))
        assert decoded['signer'].lower()==t['from'].lower() and decoded['hash']==txhash
        (out/f'tx{i}_decoded.json').write_text(json.dumps(decoded,indent=2)+'\n')
        report['transactions'].append({'index':i,'hash':txhash,'computed_hash':computed,'match':True,'from_reported':t['from'],'signer_recovered':decoded['signer'],'signer_matches':True,'signed_payload_bytes':len(enc)})
    full=HERE/'evidence/continuation_historical_metadata/response_11.bin'
    if full.exists():
        block=json.loads(full.read_bytes())['result'];pairs=[]
        anchor=get('eth_getBlockByNumber',['0x14c1351',False])
        assert '0x'+keccak(header_bytes(block),cast).hex()==anchor['hash']
        assert block['transactionsRoot']==anchor['transactionsRoot']
        for i,t in enumerate(block['transactions']):
            enc=tx_bytes(t);assert '0x'+keccak(enc,cast).hex()==t['hash']
            assert t['hash']==anchor['transactions'][i] and int(t['transactionIndex'],16)==i
            k=rlp(i);ns=[n for byte in k for n in [byte>>4,byte&15]];pairs.append((ns,enc))
        root='0x'+keccak(rlp(trie_node(pairs,cast)),cast).hex()
        assert root==block['transactionsRoot']
        report['full_block_transactions_root']={'computed':root,'expected':block['transactionsRoot'],'match':True,'count':len(pairs)}
    (out/'CHAIN_INTEGRITY.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':run(Path(sys.argv[1]))
