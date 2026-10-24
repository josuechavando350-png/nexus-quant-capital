#!/usr/bin/env python3
"""Bounded historical WETH code and aWETH underlying-slot reads, never transactions."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import time
import urllib.request
import capture_aave_rewards as prior
probe=prior.probe
identity=prior.identity
DIRECTORY=identity.MODULE/'evidence/aave-underlying-execution-20261023'
WETH='0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'
ATOKEN='0x4d5f47fa6a74757f35c14fd3a6ef8e3c9bc514e8'
PROVIDERS=dict(prior.PROVIDERS)


def validate(provider,method,args):
    probe.check(provider in PROVIDERS,'provider')
    if method=='eth_chainId':probe.check(args==[],'chain parameters')
    elif method=='eth_getBlockByNumber':probe.check(len(args)==2 and args[1] is False and (args[0]=='finalized' or re.fullmatch(r'0x[1-9a-f][0-9a-f]*',args[0])),'header parameters')
    else:
        probe.check(method in {'eth_getCode','eth_getStorageAt'},'read-only method')
        probe.check(args[:-1]==([WETH] if method=='eth_getCode' else [ATOKEN,'0x3d']),'closed address/slot scope')
        pin=args[-1];probe.check(isinstance(pin,dict) and set(pin)=={'blockHash','requireCanonical'} and pin['requireCanonical'] is True and isinstance(pin['blockHash'],str) and re.fullmatch(r'0x[0-9a-f]{64}',pin['blockHash']) and int(pin['blockHash'],16),'canonical block-hash pin')


class Rpc:
    def __init__(self):self.sequence=0;self.last=0
    def __call__(self,provider,method,args):
        validate(provider,method,args);time.sleep(max(0,.125-(time.monotonic()-self.last)));self.last=time.monotonic();self.sequence+=1
        q={'jsonrpc':'2.0','id':self.sequence,'method':method,'params':args}
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        req=urllib.request.Request(PROVIDERS[provider],data=json.dumps(q).encode(),headers={'Content-Type':'application/json','User-Agent':'nqc-miner-underlying-research'})
        with urllib.request.build_opener(NoRedirect).open(req,timeout=20) as r:raw=r.read(1_048_577)
        probe.check(len(raw)<=1_048_576,'oversize reply');a=json.loads(raw)
        probe.check(a.get('jsonrpc')=='2.0' and type(a.get('id')) is int and a['id']==self.sequence and 'result' in a and 'error' not in a,'RPC envelope')
        return {'request':q,'response':a}


def capture_one(plan,query):
    block,event=plan['block'],plan['event_anchor'];records=[];observations=[]
    def read(provider,method,args):
        validate(provider,method,args);r=query(provider,method,args);v=r['response']['result']
        if method=='eth_getBlockByNumber':v={k:v[k] for k in ('number','hash','parentHash','timestamp')}
        records.append({'provider_id':provider,'request':r['request'],'response':{**r['response'],'result':v}});return v
    def header(provider,h):probe.check(probe.same(probe.header(read(provider,'eth_getBlockByNumber',[hex(h['number']),False])),h),'header changed')
    for provider in PROVIDERS:
        probe.check(read(provider,'eth_chainId',[])=='0x1','chain')
        finalized=probe.header(read(provider,'eth_getBlockByNumber',['finalized',False]));probe.check(finalized['number']>=event['number'],'finality')
        header(provider,block);header(provider,event);pin={'blockHash':block['hash'],'requireCanonical':True}
        slot=read(provider,'eth_getStorageAt',[ATOKEN,'0x3d',pin]);probe.check(probe.implementation(slot)==WETH,'aToken underlying target')
        code=read(provider,'eth_getCode',[WETH,pin]);raw=probe.code_bytes(code)
        observations.append({'underlying_slot_word':slot,'runtime_code':code,'runtime_sha256':probe.sha(raw),'runtime_bytes':len(raw)})
        header(provider,block);header(provider,event);header(provider,finalized)
    probe.check(probe.same(*observations),'provider disagreement')
    for provider in PROVIDERS:header(provider,block);header(provider,event)
    return {'schema':'nqc-miner-weth-observation-v1',**plan,'asset':WETH,'a_token':ATOKEN,**observations[0],'records':records,'historical_state_authenticated':False,'transaction_prestate':False,'activation_allowed':False}


def replay(directory=DIRECTORY/'public'):
    m=probe.load(directory/'manifest.json');probe.check(m['complete'] is True and m['capture_sha256']==probe.sha(Path(__file__).read_bytes()),'capture integrity')
    probe.check(len(m['observations'])==3,'coverage');sequence=0;results=[]
    for n,(entry,plan) in enumerate(zip(m['observations'],prior.plans())):
        probe.check(entry['file']==f'weth-{n:03d}.json','capture path');p=directory/entry['file'];probe.check(probe.sha(p.read_bytes())==entry['sha256'],'capture hash')
        original=probe.load(p);records=iter(original['records'])
        def query(provider,method,args):
            nonlocal sequence
            sequence+=1;r=next(records);q,a=r['request'],r['response']
            probe.check(r['provider_id']==provider and q['method']==method and probe.same(q['params'],args),'request sequence')
            probe.check(q['jsonrpc']==a['jsonrpc']=='2.0' and type(q['id']) is int and type(a['id']) is int and q['id']==a['id']==sequence and 'error' not in a,'response identity')
            return {'request':q,'response':a}
        result=capture_one(plan,query);probe.check(next(records,None) is None and probe.same(result,original),'capture replay');results.append(result)
    probe.check(sequence==m['requests']==66,'request coverage');return results


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    probe.check(not any(p.is_symlink() for p in (args.output,*args.output.parents)),'output symlink');args.output.mkdir(parents=True,exist_ok=False)
    rpc=Rpc();entries=[];start=datetime.now(timezone.utc).isoformat()
    for n,plan in enumerate(prior.plans()):
        try:
            result=capture_one(plan,rpc);name=f'weth-{n:03d}.json';probe.save(args.output/name,result);entries.append({'file':name,'sha256':probe.sha((args.output/name).read_bytes())})
        except Exception as e:probe.save(args.output/'failure.json',{'index':n,'error_type':type(e).__name__,'complete':False});raise
    probe.save(args.output/'manifest.json',{'schema':'nqc-miner-weth-capture-v1','complete':True,'observations':entries,'requests':rpc.sequence,'capture_sha256':probe.sha(Path(__file__).read_bytes()),'started_at_utc':start,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'new_liquidation_events':0})
    print(json.dumps({'complete':True,'requests':rpc.sequence,'blocks':3}))
