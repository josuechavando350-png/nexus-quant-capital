#!/usr/bin/env python3
"""Cold local receipts with archived protocol state; public fixture signature only.

Only loopback Anvil is accepted. This script cannot submit a remote transaction.
It exports separate read-only Nitro plans; they are not run automatically.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'robinhood-real-state-replay-20261016'
PRIOR = HERE.parent / 'robinhood-opportunity-economics-20261016'
sys.path.insert(0, str(OLD))
sys.path.insert(0, str(PRIOR))
from local_replay import Local, load_capture, restore
from audit_result import EP, ARBSYS, USEROP, route
from prepare_fee_variant import unpack_handle_ops, limits, OPTYPE


def run(local, args, header, protocol):
    cast = lambda *a: subprocess.check_output([str(args.foundry_bin/'cast'), *a], text=True, timeout=15).strip()
    calldata = lambda sig, *a: cast('calldata', sig, *a)
    call = lambda addr, data: local.rpc('eth_call', [{'to':addr, 'data':data}, 'latest'])
    read_uint = lambda addr, sig, *a: int(call(addr, calldata(sig,*a)),16)
    dump = lambda name, obj: (args.out/name).write_text(json.dumps(obj,indent=2)+'\n')
    source = json.loads((PRIOR/'evidence/fee-variant/simulation-input.json').read_text())
    restore(local, protocol)
    for addr, state in source['state_overrides'].items():
        item = {k:v for k,v in state.items() if k not in {'state','stateDiff'}}
        if 'nonce' in item: item['nonce']=int(item['nonce'],16)
        item['storage']=state.get('state',state.get('stateDiff',{}))
        restore(local,{addr:item})
    height, timestamp = int(header['number'],16),int(header['timestamp'],16)
    def clock(value):
        local.rpc('anvil_setCode',[ARBSYS,'0x63'+value.to_bytes(4,'big').hex()+'60005260206000f3'])
    clock(height)
    local.rpc('anvil_setCoinbase',[header['miner']])
    sender = source['transaction']['from']
    local.rpc('anvil_impersonateAccount',[sender])
    admin = '0x000000000000000000000000000000000000cafe'
    local.rpc('anvil_impersonateAccount',[admin])
    local.rpc('anvil_setBalance',[admin,hex(10**18)])
    def send(tx, when):
        local.rpc('anvil_setNextBlockBaseFeePerGas',[header['baseFeePerGas']])
        local.rpc('evm_setNextBlockTimestamp',[when])
        identity=local.rpc('eth_sendTransaction',[tx])
        for _ in range(100):
            receipt=local.rpc('eth_getTransactionReceipt',[identity])
            if receipt is not None: break
            time.sleep(.05)
        else: raise RuntimeError('receipt timeout')
        trace=local.rpc('debug_traceTransaction',[identity,{'tracer':'callTracer','tracerConfig':{'withLog':True}}])
        return receipt,trace
    fields,_ = unpack_handle_ops(source['transaction']['data'])
    cap=limits(fields)['required_prefund_wei']
    op_hash=call(EP,calldata('getUserOpHash('+OPTYPE+')','('+','.join(fields)+')'))
    expected=json.loads((PRIOR/'evidence/fee-variant/report.json').read_text())['variant_userop_hash']
    if op_hash!=expected: raise ValueError('approved operation hash mismatch')
    pm=source['addresses']['paymaster']
    artifact=json.loads((args.build/'robinhood/out/NqcWindowedPaymasterFixture.sol/NqcWindowedPaymasterFixture.json').read_text())
    init=artifact['bytecode']['object']+cast('abi-encode','f(address,address,bytes32,uint256,uint256,uint48,uint48)',
        EP,fields[0],op_hash,str(cap),str(cap),str(timestamp),str(timestamp+args.window_seconds))[2:]
    deployment,_=send({'from':admin,'data':init,'gas':hex(8000000),'gasPrice':header['baseFeePerGas']},timestamp-10)
    if int(deployment['status'],16)!=1: raise ValueError('local fixture constructor failed')
    runtime=local.rpc('eth_getCode',[deployment['contractAddress'],'latest'])
    new_pm={'code':runtime,'state':{
        '0x'+(0).to_bytes(32,'big').hex():'0x'+int(admin,16).to_bytes(32,'big').hex(),
        '0x'+(1).to_bytes(32,'big').hex():'0x'+cap.to_bytes(32,'big').hex()}}
    local.rpc('anvil_setCode',[pm,runtime])
    # Constructor-equivalent state at the fixed laboratory paymaster address.
    for slot in range(5): local.rpc('anvil_setStorageAt',[pm,hex(slot),'0x'+'00'*32])
    for slot,value in new_pm['state'].items():local.rpc('anvil_setStorageAt',[pm,slot,value])
    if read_uint(pm,'validAfter()')!=timestamp or read_uint(pm,'validUntil()')!=timestamp+args.window_seconds:
        raise ValueError('runtime immutable windows differ')
    source['state_overrides'][pm]=new_pm
    source['window_fixture']={'approved_userop_hash':op_hash,'valid_after':timestamp,'valid_until':timestamp+args.window_seconds,
        'budget_wei':cap,'runtime_sha256':hashlib.sha256(bytes.fromhex(runtime[2:])).hexdigest(),
        'constructor_deployed_on_loopback_only':True,'public_fixture_signature_reused':True}
    dump('simulation-input.json',source)
    snapshot=local.rpc('evm_snapshot',[])
    account=source['addresses']['account']
    pos=calldata('position(bytes32,address)','0xaa586d26a6fe62d9c0f0948fede6e2130500ac7a655587447e2d4a37e6330589',
                 '0x689afbae02a62d10e9a20a6f76b08d94eb7361f0')
    records=[]
    cases=[('not_due',timestamp-1,height,False,None),('valid_after',timestamp,height,True,True),
           ('valid_until',timestamp+args.window_seconds,height,True,True),('expired',timestamp+args.window_seconds+1,height,False,None),
           ('l2_execution_expired',timestamp,height+1,True,False)]
    for name,when,l2,bundle_ok,userop_ok in cases:
        if not local.rpc('evm_revert',[snapshot]): raise ValueError('snapshot reset failed')
        snapshot=local.rpc('evm_snapshot',[]); clock(l2)
        before_deposit=read_uint(EP,'balanceOf(address)',pm)
        before_budget=read_uint(pm,'budgetRemaining()')
        before_position=call(route.MORPHO,pos)
        before_reserves=call(route.POOL,calldata('getReserves()'))
        receipt,trace=send(source['transaction'],when)
        dump(name+'-receipt.json',receipt); dump(name+'-trace.json',trace)
        status=int(receipt['status'],16)==1
        if status!=bundle_ok:raise ValueError(name+': unexpected root status')
        event=next((x for x in receipt['logs'] if x['address'].lower()==EP and x['topics'][0]==USEROP),None)
        after_deposit=read_uint(EP,'balanceOf(address)',pm)
        after_budget=read_uint(pm,'budgetRemaining()')
        surplus=read_uint(route.USDG,'balanceOf(address)',account)
        if event:
            nonce,success,cost,billed=route.words(event['data'],4)
            if bool(success)!=userop_ok or cost!=before_deposit-after_deposit or before_budget-after_budget!=cap:
                raise ValueError(name+': sponsorship reconciliation failed')
        else:
            cost,billed=0,0
            if event is not None or userop_ok is not None or before_deposit!=after_deposit or before_budget!=after_budget:
                raise ValueError(name+': failed bundle changed sponsorship')
            if b'AA32 paymaster expired or not due' not in bytes.fromhex(trace.get('output','0x')[2:]):
                raise ValueError(name+': expected AA32')
        if not userop_ok:
            if surplus!=0 or call(route.MORPHO,pos)!=before_position or call(route.POOL,calldata('getReserves()'))!=before_reserves:
                raise ValueError(name+': protocol did not roll back')
        records.append({'case':name,'timestamp':when,'local_l2_clock_stub':l2,'bundle_success':status,
            'userop_success':userop_ok,'sponsor_charge_wei':cost,'billed_gas':billed,
            'receipt_gas':int(receipt['gasUsed'],16),'local_network_fee_wei':int(receipt['gasUsed'],16)*int(receipt['effectiveGasPrice'],16),
            'surplus_usdg_raw':surplus,'budget_after_wei':after_budget})
    dump('report.json',{'records':records,'window':source['window_fixture'],'local_is_nitro':False,
                       'deployment_cost_included_in_cycle':False,'production_admission_proven':False})
    config={'tracer':'callTracer','tracerConfig':{'withLog':True},'timeout':'10s','reexec':0,
            'txIndex':'0x1','stateOverrides':source['state_overrides']}
    plan=[]
    for label,delta in [('not-due',-1),('valid-after',0),('valid-until',args.window_seconds),('expired',args.window_seconds+1)]:
        cfg=copy.deepcopy(config)
        if delta:cfg['blockOverrides']={'time':hex(timestamp+delta)}
        plan.append({'label':label,'method':'debug_traceCall','params':[source['transaction'],
                     {'blockHash':header['hash'],'requireCanonical':True},cfg]})
    for label,delta in [('valid-state-diff',0),('expired-state-diff',args.window_seconds+1)]:
        cfg=copy.deepcopy(config);cfg['tracer']='prestateTracer';cfg['tracerConfig']={'diffMode':True}
        if delta:cfg['blockOverrides']={'time':hex(timestamp+delta)}
        plan.append({'label':label,'method':'debug_traceCall','params':[source['transaction'],
                     {'blockHash':header['hash'],'requireCanonical':True},cfg]})
    plan.append({'label':'canonical-final','method':'eth_getBlockByHash','params':[header['hash'],False]})
    dump('nitro-plan.json',plan)
    print(json.dumps(records,indent=2))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--build',type=Path,required=True)
    ap.add_argument('--foundry-bin',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--window-seconds',type=int,choices=[1,31],default=1)
    args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    pins=json.loads((HERE.parent/'robinhood-aa-20261016/toolchain.json').read_text())
    for name in ['cast','anvil']:
        if hashlib.sha256((args.foundry_bin/name).read_bytes()).hexdigest()!=pins['binary_sha256'][name]:
            raise ValueError('unrecognized toolchain')
    _,_,header,_,state,_=load_capture(OLD/'evidence/provider-capture')
    local=Local(18568)
    cmd=[str(args.foundry_bin/'anvil'),'--host','127.0.0.1','--port','18568','--chain-id','4663',
         '--hardfork','osaka','--number',str(int(header['l1BlockNumber'],16)-2),
         '--timestamp',str(int(header['timestamp'],16)-100),'--gas-limit','30000000','--silent']
    with (args.out/'anvil.log').open('w') as log:
        process=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT)
        try:
            for _ in range(40):
                if process.poll() is not None:raise RuntimeError('Anvil exited')
                try:
                    if not local.rpc('web3_clientVersion',[]).lower().startswith('anvil'):raise RuntimeError('wrong local client')
                    break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('local startup timeout')
            run(local,args,header,state)
        finally:
            process.terminate();process.wait(timeout=5)


if __name__=='__main__':main()
