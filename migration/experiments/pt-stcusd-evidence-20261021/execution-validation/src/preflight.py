#!/usr/bin/env python3
"""Reject incomplete original-replay inputs. Never declares EVM PASS."""
import argparse
import json
from pathlib import Path
import sys
from acquire import TX, PARENT, BLOCK

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'route-audit/src'))
from route_audit import expand

def validate(folder, source):
    missing=[]; errors=[]; data={}
    for name in ('chain','parent_header','target_header','transaction','receipt','prestate','call_trace','state_diff'):
        p=folder/(source+'_'+name+'.json')
        if not p.exists():
            missing.append(name); continue
        try:
            capture=json.loads(p.read_text())
            if capture['status']!='RECEIVED': raise ValueError('transport or RPC failure')
            envelope=json.loads(capture['body'])
            if envelope.get('jsonrpc')!='2.0' or envelope.get('id')!=1 or 'error' in envelope: raise ValueError('invalid RPC envelope')
            value=envelope['result']
            if value is None: raise ValueError('null result')
            data[name]=value
        except (KeyError,TypeError,ValueError) as e:
            errors.append(name+': '+str(e))
    if missing or errors:
        return {'status':'BLOCKED_MISSING_OR_FAILED_RPC_INPUTS','missing':missing,'errors':errors,'evm_executed':False}
    def check(ok, message):
        if not ok: errors.append(message)
    try:
        check(data['chain']=='0x1','wrong chain')
        parent=data['parent_header']; target=data['target_header']; tx=data['transaction']; receipt=data['receipt']
        check(int(parent['number'],16)==PARENT and int(target['number'],16)==BLOCK,'wrong block number')
        check(parent['hash'].lower()==target['parentHash'].lower(),'broken parent link')
        expected=json.loads((ROOT.parent/'route-audit/inputs/route_evidence.json').read_text())
        check(target['hash'].lower()==expected['block_hash_from_prior_upload'],'unexpected target hash')
        for item in (tx,receipt):
            check(int(item['blockNumber'],16)==BLOCK and item['blockHash'].lower()==target['hash'].lower(),'tx/receipt block binding')
            check(int(item['transactionIndex'],16)==0,'wrong tx index')
        check(tx['hash'].lower()==TX and receipt['transactionHash'].lower()==TX,'wrong tx hash')
        check(target['transactions'][0].lower()==TX,'transaction absent at position zero')
        check(receipt['status']=='0x1','original not successful')
        for key in ('stateRoot','receiptsRoot','transactionsRoot','mixHash','parentBeaconBlockRoot','baseFeePerGas','gasLimit','timestamp'):
            check(key in target, 'target missing '+key)
        check('stateRoot' in parent,'missing parent state root')
        check(isinstance(tx['input'],str) and len(tx['input'])>10 and len(bytes.fromhex(tx['input'][2:]))*2==len(tx['input'])-2,'invalid calldata')
        for key in ('nonce','gas','maxFeePerGas','maxPriorityFeePerGas','value','type','chainId','r','s'):
            check(key in tx,'transaction missing '+key)
        expected_logs=[expand(e,expected['addresses'],expected['event_signatures']) for e in expected['events']]
        actual_logs=[{'index':int(e['logIndex'],16),'address':e['address'].lower(),
                      'topics':[t.lower() for t in e['topics']], 'data':e['data'].lower()} for e in receipt['logs']]
        check(actual_logs==expected_logs,'receipt differs from 53 normalized captured logs')
        for e in receipt['logs']:
            check(e['transactionHash'].lower()==TX and e['blockHash'].lower()==target['hash'].lower() and not e.get('removed',False),'log binding')
        check(int(receipt['gasUsed'],16)==1870816,'original gas mismatch')
        check(int(receipt['effectiveGasPrice'],16)==1042435069,'effective gas price mismatch')
        pre=data['prestate']; call=data['call_trace']; diff=data['state_diff']
        for key in ('MORPHO','EXECUTOR','USDC','WETH','PT','SY','YT','STCUSD','CUSD','ADAPTER','VAULT','STRATEGY','RESERVE','ROUTER','POOL'):
            addr=expected['addresses'][key]
            account=pre.get(addr,{})
            check(bool(account.get('code')) and account.get('code')!='0x','missing prestate runtime '+key)
        check(call['from'].lower()==tx['from'].lower() and call['to'].lower()==tx['to'].lower(),'trace account mismatch')
        check(call['input'].lower()==tx['input'].lower() and not call.get('error'),'trace input or error')
        check(isinstance(diff.get('pre'),dict) and isinstance(diff.get('post'),dict),'missing state diff')
    except (KeyError,TypeError,ValueError,IndexError) as e:
        errors.append('invalid shape: '+str(e))
    return {'status':'BLOCKED_INVALID_INPUTS' if errors else 'INPUTS_PRESENT_EVM_AND_PROOFS_NOT_VERIFIED',
            'missing':missing,'errors':errors,'evm_executed':False,
            'consensus_header_and_receipt_proofs_verified':False,
            'system_transition_parity_verified':False}

def main():
    p=argparse.ArgumentParser();p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--source',default='alchemy');args=p.parse_args()
    result=validate(args.capture,args.source);print(json.dumps(result,indent=2))
    return 2 if result['status'].startswith('BLOCKED') else 0

if __name__=='__main__':raise SystemExit(main())
