"""Reviewed block-addressed diagnostic, not a retry of the missing hash lookup.

Reason: run 39379758996 got chain ID and both correct historic blocks, but the
hash-indexed receipt lookup returned null. Geth documents independent retention
of its transaction index; Ethereum exposes eth_getBlockReceipts by block hash.
This is a NEW finite diagnostic on the SAME authorized public origin, not a
provider/quota/access-denial bypass. No repeats of eth_chainId or receipt-by-hash,
no alternate provider, no signatures, no historical assertions relaxed.

Scope: at most THREE reads: receipts at exact target hash; full target block at
that hash; Morpho runtime at the parent. Count the prior five requests toward the
session's original 1200 cap. Stop on first null/error/denial/conflict. The prior
run remains failed. This diagnostic NEVER calls forge or grants financial GO.
Original source bundle and Solidity files remain immutable.

Primary documentation reviewed 2026-10-20:
https://geth.ethereum.org/docs/fundamentals/command-line-options
https://ethereum.github.io/execution-apis/api/methods/eth_getBlockReceipts/
"""
from pathlib import Path
import hashlib,json,os,sys
import rpc_guard as g

BLOCK_HASH='0x2702da91c548f69a98373525ae8409c6bd28189439bb53f2acb971a029ac5882'
PARENT_HASH='0xc3b1f4fe26e6743df8727eceec10c536b33db580b3346fa87e731d888ca5f4d3'
MORPHO='0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb'

def check_receipts(receipts):
    if not isinstance(receipts,list) or len(receipts)!=41:
        raise ValueError('Expected all 41 block receipts')
    by_index={}
    for r in receipts:
        if not isinstance(r,dict):raise ValueError('Malformed receipt')
        idx=int(r['transactionIndex'],16)
        if idx in by_index:raise ValueError('Duplicate transaction index')
        if r['blockHash'].lower()!=BLOCK_HASH or int(r['blockNumber'],16)!=g.TARGET:
            raise ValueError('Receipt block identity conflict')
        by_index[idx]=r
    if set(by_index)!=set(range(41)):raise ValueError('Missing indices')
    if by_index[0]['transactionHash'].lower()!=g.PREFIX:raise ValueError('Prefix conflict')
    target=by_index[1]
    if target['transactionHash'].lower()!=g.TX:raise ValueError('Target conflict')
    if target['status']!='0x1':raise ValueError('Target not successful')
    return by_index

def diagnostic():
    out=Path('block_lookup_evidence');out.mkdir(exist_ok=True)
    guard=g.Guard(out)
    def validate(method,params):
        if method=='eth_getBlockReceipts' and params==[BLOCK_HASH]:return
        if method=='eth_getBlockByHash' and params==[BLOCK_HASH,True]:return
        if method=='eth_getCode' and params==[MORPHO,hex(g.PARENT)]:return
        raise g.Closed('Outside three-read diagnostic')
    # Original guard assumes every eth_getBlock* result is a block object.
    # Override only the collection method by using a dedicated read adapter.
    g.MAX_READS=3;g.MAX_SECONDS=120;g.validate=validate
    result={'schema':'nqc-block-addressed-diagnostic-v1','producer_sha':os.environ.get('GITHUB_SHA'),
      'previous_session_requests':5,'max_this_diagnostic':3,'receipts_recovered':False,
      'historic_code_received':False,'baseline_replayed':False,'variant_tested':False,
      'commercial_admission':False,'net_NQC_profit':None}
    try:
        receipts=guard.call('eth_getBlockReceipts',[BLOCK_HASH])
        indexed=check_receipts(receipts)
        result['receipts_recovered']=True
        t=indexed[1]
        result['target_receipt']={'gas_used':int(t['gasUsed'],16),
          'effective_gas_price':int(t['effectiveGasPrice'],16),'logs':len(t['logs']),
          'status':t['status'],'blockHash':t['blockHash'],'transactionHash':t['transactionHash']}
        print('TARGET_RECEIPT_JSON '+json.dumps(t,sort_keys=True),flush=True)
        if result['target_receipt']['gas_used']!=602029 or result['target_receipt']['effective_gas_price']!=302819782345:
            raise ValueError('Original receipt differs from pinned ledger; no replay')
        block=guard.call('eth_getBlockByHash',[BLOCK_HASH,True])
        if block['hash'].lower()!=BLOCK_HASH or block['parentHash'].lower()!=PARENT_HASH or len(block['transactions'])!=41:
            raise ValueError('Full block anchor mismatch')
        for i,tx in enumerate(block['transactions']):
            if tx['hash'].lower()!=indexed[i]['transactionHash'].lower() or int(tx['transactionIndex'],16)!=i:
                raise ValueError('Full transaction/receipt mismatch')
        print('PREFIX_TRANSACTION_JSON '+json.dumps(block['transactions'][0],sort_keys=True),flush=True)
        print('TARGET_TRANSACTION_JSON '+json.dumps(block['transactions'][1],sort_keys=True),flush=True)
        result['full_block_transactions_received']=True
        code=guard.call('eth_getCode',[MORPHO,hex(g.PARENT)])
        if not isinstance(code,str) or not code.startswith('0x') or len(code)<=2:raise ValueError('Missing Morpho runtime')
        b=bytes.fromhex(code[2:]);result['historic_code_received']=True
        result['morpho_runtime_bytes']=len(b);result['morpho_runtime_sha256']=hashlib.sha256(b).hexdigest()
        result['verdict']='BLOCK_ADDRESSED_DATA_AVAILABLE_NOT_EVM_PROOF'
    except Exception as e:
        result['error']=type(e).__name__+': '+str(e)
        result['verdict']='DIAGNOSTIC_STOPPED_NOT_ECONOMIC_RESULT'
    finally:
        result['rpc']=guard.summary();result['combined_session_requests']=5+guard.used
        result['raw_records_sha256']=hashlib.sha256((out/'rpc_history.jsonl').read_bytes()).hexdigest() if (out/'rpc_history.jsonl').exists() else None
        # Log response metadata/hashes; full upstream bodies remain on ephemeral runner.
        if (out/'rpc_history.jsonl').exists():
            for line in (out/'rpc_history.jsonl').read_text().splitlines():
                row=json.loads(line)
                if 'raw_response_text' in row:
                    row.pop('raw_response_text');row['raw_response_omitted_from_summary']=True
                print('RPC_DIAGNOSTIC_RECORD '+json.dumps(row,sort_keys=True),flush=True)
        print('NQC_BLOCK_DIAGNOSTIC '+json.dumps(result,sort_keys=True),flush=True)
    return 0 if result['historic_code_received'] else 2

if __name__=='__main__':raise SystemExit(diagnostic())
