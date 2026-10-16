#!/usr/bin/env python3
"""Cold transaction gas evidence on a fresh, isolated Anvil only. Never accepts a remote URL."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import urllib.request

EP = '0x0000000071727de22e5e9d8baf0edac6f37da032'
ARBSYS = '0x0000000000000000000000000000000000000064'
BUNDLER = '0x000000000000000000000000000000000000beef'
KEY = '0x' + '1234'.rjust(64,'0')  # Public local fixture only.
OPTYPE = '(address,uint256,bytes,bytes,bytes32,uint256,bytes32,bytes,bytes)'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port',type=int,required=True)
    ap.add_argument('--build',type=Path,required=True)
    ap.add_argument('--cast',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args = ap.parse_args()
    if not 1024 <= args.port <= 65535:
        raise ValueError('invalid localhost port')
    url = f'http://127.0.0.1:{args.port}'
    session = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def rpc(method,params):
        body=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode()
        with session.open(urllib.request.Request(url,data=body,headers={'Content-Type':'application/json'}),timeout=20) as r:
            result=json.load(r)
        if 'error' in result:
            raise ValueError((method,result['error']))
        return result['result']
    assert rpc('web3_clientVersion',[]).lower().startswith('anvil')
    assert int(rpc('eth_chainId',[]),16)==4663
    assert int(rpc('eth_blockNumber',[]),16)==0, 'must use a FRESH local chain'
    sender = rpc('eth_accounts',[])[0]
    def cast(*v):
        return subprocess.check_output([str(args.cast),*map(str,v)],text=True).strip()
    def calldata(sig,*v): return cast('calldata',sig,*v)
    def call(address,data): return rpc('eth_call',[{'to':address,'data':data},'latest'])
    def uintcall(address,sig,*v): return int(call(address,calldata(sig,*v)),16)
    def addresscall(address,sig): return '0x'+call(address,calldata(sig))[-40:]
    def send(data,to=None,value=0):
        rpc('anvil_setNextBlockBaseFeePerGas',[hex(10**9)])
        tx={'from':sender,'data':data,'value':hex(value),'gas':hex(30_000_000),'gasPrice':hex(2*10**9)}
        if to: tx['to']=to
        txhash=rpc('eth_sendTransaction',[tx])
        receipt=None
        for _ in range(100):
            receipt=rpc('eth_getTransactionReceipt',[txhash])
            if receipt is not None: break
            time.sleep(0.05)
        assert receipt is not None
        return tx,receipt
    runtime=json.loads((args.build/'robinhood/runtime.json').read_text())['runtime']
    assert hashlib.sha256(bytes.fromhex(runtime[2:])).hexdigest()=='674d73ee2acf6d72a5b32b6e05150b9ddcfcee0429a0e7914929faccbc2bf4d5'
    rpc('anvil_setCode',[EP,runtime])
    rpc('anvil_setStorageAt',[EP,'0x'+'00'*32,'0x'+'00'*31+'01'])
    def clock(n):
        # Synthetic ArbSys stand-in; no claim that its gas equals the Nitro precompile.
        rpc('anvil_setCode',[ARBSYS,'0x63'+n.to_bytes(4,'big').hex()+'60005260206000f3'])
    clock(90_000_000)
    artifact=json.loads((args.build/'robinhood/out/NqcRobinhoodCycle.t.sol/NqcLocalScenario.json').read_text())
    morpho=json.loads((args.build/'morpho-native-lab/out/Morpho.sol/Morpho.json').read_text())['bytecode']['object']
    owner=cast('wallet','address','--private-key',KEY)
    constructor=cast('abi-encode','f(address,bytes,address,uint256)',EP,morpho,owner,11*10**17)
    _,deployment=send(artifact['bytecode']['object']+constructor[2:],value=10**17)
    assert int(deployment['status'],16)==1
    scene=deployment['contractAddress']
    sponsor=addresscall(scene,'paymaster()')
    account=addresscall(scene,'account()')
    loan=addresscall(scene,'loan()')
    snapshot=rpc('evm_snapshot',[])
    topic=cast('keccak','UserOperationEvent(bytes32,address,address,uint256,bool,uint256,uint256)')
    def decode_op(raw):
        b=bytes.fromhex(raw[2:]); offset=int.from_bytes(b[:32],'big'); b=b[offset:]
        vals=[]
        for i in range(9):
            w=b[i*32:(i+1)*32]
            if i in (2,3,7,8):
                off=int.from_bytes(w,'big');n=int.from_bytes(b[off:off+32],'big');vals.append('0x'+b[off+32:off+32+n].hex())
            elif i==0: vals.append('0x'+w[-20:].hex())
            elif i in (1,5): vals.append(str(int.from_bytes(w,'big')))
            else: vals.append('0x'+w.hex())
        return vals
    records=[]
    scenarios=[('success_original_limits',1_800_000,160_000,'success'),
               ('success_reduced_limits',600_000,160_000,'success'),
               ('expired_l2',600_000,160_000,'expired'),
               ('swap_revert',600_000,160_000,'swap'),
               ('postop_revert',600_000,160_000,'postop'),
               ('call_out_of_gas',30_000,160_000,'oog'),
               ('invalid_signature_bundle_revert',600_000,160_000,'signature')]
    for name,gas,post,kind in scenarios:
        assert rpc('evm_revert',[snapshot]);snapshot=rpc('evm_snapshot',[])
        if kind=='expired': clock(90_000_001)
        if kind=='postop':
            _,r=send(calldata('rejectPostOp()'),scene);assert int(r['status'],16)==1
        if kind=='swap':
            # Synthetic DEX rate is immutable: empty its prefunded output inventory.
            # This is a local liquidity failure, not a real route/slippage replay.
            executor=addresscall(scene,'executor()');dex=addresscall(executor,'router()')
            slot=cast('index','address',dex,'0')
            rpc('anvil_setStorageAt',[loan,slot,'0x'+'00'*32])
        vals=decode_op(call(scene,calldata('unsignedOp(uint256,bytes32,uint256,uint256)',90_000_000,'0x'+(201).to_bytes(32,'big').hex(),gas,post)))
        unsigned='('+','.join(vals)+')'
        opHash=call(EP,calldata('getUserOpHash('+OPTYPE+')',unsigned))
        vals[8]=cast('wallet','sign','--private-key',KEY,opHash)
        if kind=='signature': vals[8]='0x'+'00'*65
        data=calldata('handleOps('+OPTYPE+'[],address)','[('+','.join(vals)+')]',BUNDLER)
        before=uintcall(EP,'balanceOf(address)',sponsor)
        beforeBundler=int(rpc('eth_getBalance',[BUNDLER,'latest']),16)
        budget=uintcall(sponsor,'budgetRemaining()')
        tx,receipt=send(data,EP)
        debit=before-uintcall(EP,'balanceOf(address)',sponsor)
        beneficiary=int(rpc('eth_getBalance',[BUNDLER,'latest']),16)-beforeBundler
        reserved=budget-uintcall(sponsor,'budgetRemaining()')
        gasUsed=int(receipt['gasUsed'],16); price=int(receipt['effectiveGasPrice'],16)
        log=next((x for x in receipt['logs'] if x['address'].lower()==EP and x['topics'][0]==topic),None)
        event=None
        if log:
            raw=bytes.fromhex(log['data'][2:]);v=[int.from_bytes(raw[i:i+32],'big') for i in range(0,len(raw),32)]
            event={'nonce':v[0],'success':bool(v[1]),'actualGasCost':v[2],'actualGasUsed':v[3]}
            assert debit==beneficiary==v[2]>0 and reserved>=debit
            assert event['success']==(kind=='success')
        else:
            assert kind=='signature' and int(receipt['status'],16)==0 and debit==reserved==beneficiary==0
        surplus=uintcall(loan,'balanceOf(address)',account)
        assert surplus>=50_000_000 if kind=='success' else surplus==0
        assert int(rpc('eth_getBalance',[account,'latest']),16)==0
        record={'scenario':name,'tx':tx,'receipt':receipt,'userop_event':event,
            'tx_gas_used':gasUsed,'effective_gas_price_wei':price,'bundler_tx_fee_wei':gasUsed*price,
            'paymaster_debit_wei':debit,'beneficiary_credit_wei':beneficiary,
            'bundler_difference_wei':beneficiary-gasUsed*price,'budget_reserved_wei':reserved,
            'postop_cost_argument_wei':uintcall(sponsor,'postOpCostArgument()'),
            'loan_surplus_raw':surplus,'calldata_bytes':len(bytes.fromhex(data[2:])),
            'call_gas_limit':gas,'postop_gas_limit':post}
        records.append(record)
        print(json.dumps({k:v for k,v in record.items() if k not in ('tx','receipt')},sort_keys=True))
    args.out.mkdir(parents=True,exist_ok=True)
    report={'scope':'LOCAL_ANVIL_COLD_RECEIPTS_SYNTHETIC_MARKET_AND_DEX',
        'runtime_sha256':hashlib.sha256(bytes.fromhex(runtime[2:])).hexdigest(),
        'chain_id_fixture':4663,'actual_chain_rpc_used':False,'l1_data_fee_measured':False,
        'account_deployment_in_handleops':False,'preverification_gas':120000,
        'production_bundler_admission':False,'native_eth_value_is_fake':True,
        'nqc_realized_usd':'0','deployment_receipt':deployment,'records':records}
    (args.out/'local-receipts.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__': main()
