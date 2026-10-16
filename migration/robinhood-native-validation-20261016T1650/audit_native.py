"""Offline reconstruction of the completed local capture; no RPC calls."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from native_validation import HERE, PREVIOUS, ROOT, CASES, NATIVE, cases_and_genesis, read, summarize, prior, failed_op
from capture_native import verify_lock


def need(condition,message):
    if not condition: raise ValueError(message)


def dynamic_string(data, offset):
    need(offset % 32 == 0 and offset+32<=len(data),'string offset')
    size=int.from_bytes(data[offset:offset+32],'big')
    end=offset+32+((size+31)//32)*32
    need(end==len(data) and not any(data[offset+32+size:]),'string length/padding')
    return data[offset+32:offset+32+size].decode('utf8')


def decode_deposit_error(raw):
    data=bytes.fromhex(raw[2:])
    need(data[:4]==prior.keccak256(b'FailedOp(uint256,string)')[:4],'deposit error selector')
    data=data[4:]
    need(int.from_bytes(data[:32],'big')==0 and int.from_bytes(data[32:64],'big')==64,'deposit error ABI')
    return dynamic_string(data,64)


def decode_budget_error(raw):
    outer=failed_op(raw)
    need(outer['op_index']==0 and outer['reason']=='AA33 reverted','budget outer error')
    inner=bytes.fromhex(outer['inner'][2:])
    need(inner[:4]==prior.keccak256(b'Error(string)')[:4],'budget inner selector')
    data=inner[4:]
    need(int.from_bytes(data[:32],'big')==32,'budget inner ABI')
    return dynamic_string(data,32)


def audit(out):
    verify_lock()
    rows,report=read(out/'requests.json'),read(out/'report.json')
    need(report['registration_commit']=='4a814940a80d3b5f6effced72984d3ffc53f6f5d','registration changed')
    need(report['status']=='LOCAL_NATIVE_VALIDATION_COMPLETE_FULL_BUNDLER_BLOCKED','capture not complete')
    need(report['public_rpc_methods']==report['transactions_sent']==0,'scope differs')
    need(report['full_bundler_executed'] is False,'full bundler overclaim')
    methods=['web3_clientVersion','eth_chainId','eth_getBlockByNumber']+['debug_traceCall']*6+['eth_getBlockByNumber']
    need([r['request']['method'] for r in rows]==methods,'request order/count')
    responses=[]
    for i,row in enumerate(rows,1):
        need(row['request']['jsonrpc']=='2.0' and row['request']['id']==i,'request id')
        need(row['http_status']==200 and 'error' not in row,'HTTP/RPC failure')
        body=(out/row['file']).read_bytes()
        need(len(body)<=2*1024*1024,'response byte cap')
        need(hashlib.sha256(body).hexdigest()==row['response_sha256'],'response hash mismatch')
        obj=json.loads(body)
        need(obj['jsonrpc']=='2.0' and obj['id']==i and 'error' not in obj,'response envelope')
        responses.append(obj['result'])
    need(responses[0]==report['local_client'] and responses[0].startswith('Geth/v1.17.8'),'client')
    need(int(responses[1],16)==4663,'chain')
    header,final=responses[2],responses[-1]
    need(header==final and int(header['number'],16)==0,'canonical genesis changed')
    need(int(header['timestamp'],16)==1789786800,'genesis timestamp')
    need(report['local_genesis_hash']==header['hash'] and report['local_state_unchanged'] is True,'header report')
    cases,initial=cases_and_genesis()
    need(read(out/'genesis.json')==initial,'genesis allocation differs')
    reconstructed=[]
    tracer=(PREVIOUS/'build/tracer.js').read_text()
    for case,row,trace in zip(cases,rows[3:9],responses[3:9]):
        need(read(out/(case['case']+'-input.json'))==case,'input file differs')
        tx,block_hash,options=row['request']['params']
        need(tx==case['transaction'] and block_hash==header['hash'],'transaction/hash differs')
        need(options=={'tracer':tracer,'timeout':'10s','reexec':0,'stateOverrides':case['stateOverrides']},'trace options differ')
        reconstructed.append(summarize(case,trace))
    need(reconstructed==report['cases'],'case report mismatch')
    deposit=decode_deposit_error(responses[7]['calls'][-1]['data'])
    budget=decode_budget_error(responses[8]['calls'][-1]['data'])
    need(deposit=='AA31 paymaster deposit too low' and budget=='BUDGET_POLICY','negative policy differs')
    gaps=[(b['dispatch_seconds']-a['dispatch_seconds'])*1000 for a,b in zip(rows,rows[1:])]
    need(min(gaps)>=350,'dispatch rate')
    need(report['local_rpc_methods']==10 and rows[-1]['end_seconds']<=report['elapsed_seconds']<900,'global limits')
    need(report['process_stopped'] is True,'process closure missing')
    start,end=map(datetime.fromisoformat,(report['started_utc'],report['ended_utc']))
    need(start.tzinfo is not None and end>start,'UTC receipt')
    positives=[x for x in reconstructed if 'decoded' in x]
    need(len(positives)==3 and all(x['decoded']['account_validation_data']==0 for x in positives),'positive signature')
    native_data={x['native_ecrecover']['data'] for x in positives}
    need(len(native_data)==1,'recovered signer differs')
    return {'audit':'EXACT_CAPTURE_RECONSTRUCTED','started_utc':report['started_utc'],
            'ended_utc':report['ended_utc'],'process_seconds':report['elapsed_seconds'],
            'journal_end_seconds':rows[-1]['end_seconds'],'wait_seconds':sum(r['wait_seconds'] for r in rows),
            'minimum_dispatch_gap_ms':min(gaps),'local_rpc_methods':10,'public_rpc_methods':0,
            'transactions_sent':0,'planned_controls':6,'completed_controls':6,
            'positive_validations':3,'expected_rejections':3,'native_signature_control_passed':True,
            'recovered_signer':'0x'+next(iter(native_data))[-40:],
            'deposit_error':deposit,'budget_error':budget,
            'prefund_wei':positives[0]['decoded']['prefund_wei'],
            'validation_preop_gas':[x['decoded']['preop_gas'] for x in positives],
            'window_seconds':[x['decoded']['valid_until']-x['decoded']['valid_after'] for x in positives],
            'paymaster_stake_wei':[x['decoded']['paymaster_stake_wei'] for x in positives],
            'native_precompile_balance_preserved_in_genesis':initial['alloc'][NATIVE[2:]]['balance'],
            'local_state_unchanged':True,'full_bundler_admission_proven':False,
            'nitro_or_full_route_measured':False,'funding_available_proven':False,'profit_proven':False,
            'cases':reconstructed}


if __name__=='__main__':
    print(json.dumps(audit(HERE/'evidence/pilot'),indent=2))
