#!/usr/bin/env python3
"""Bounded dual-provider Aave oracle identity/routing capture at retained block hashes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
import urllib.request
import capture_aave_rewards as prior

identity = prior.identity
probe = prior.probe
DIRECTORY = identity.MODULE / 'evidence/aave-oracle-execution-20261023'
ORACLE = '0x54586be62e3c3580375ae3723c145253060ca0c2'
PROVIDER = identity.IMMUTABLES['ADDRESSES_PROVIDER']
ASSETS = ('0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48', '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2')
PROVIDERS = dict(prior.PROVIDERS)
MAX_REQUESTS = 144
SELECTORS = {'provider_oracle':'fca513a8', 'provider':'0542975c', 'base':'e19f4700',
    'unit':'8c89b64f', 'fallback':'6210308c', 'source':'92bf2be0', 'price':'b3596f07', 'answer':'50d25bcd'}


def calldata(kind, asset=None):
    return '0x' + SELECTORS[kind] + (asset[2:].rjust(64,'0') if asset else '')


def word(value):
    probe.check(isinstance(value,str) and re.fullmatch(r'0x[0-9a-f]{64}',value), 'ABI word')
    return int(value,16)


def address_word(value, zero=False):
    n=word(value); probe.check(n < 2**160 and (zero or n!=0), 'ABI address')
    return '0x'+format(n,'040x')


def validate(provider, method, args):
    probe.check(provider in PROVIDERS, 'provider')
    if method=='eth_chainId': probe.check(args==[], 'chain parameters'); return
    if method=='eth_getBlockByNumber':
        probe.check(len(args)==2 and args[1] is False and
            (args[0]=='finalized' or re.fullmatch(r'0x[1-9a-f][0-9a-f]*',args[0])), 'header parameters'); return
    probe.check(method in {'eth_call','eth_getCode','eth_getStorageAt'}, 'read-only method')
    probe.check(len(args)==(3 if method=='eth_getStorageAt' else 2), 'argument count')
    pin=args[-1]
    probe.check(isinstance(pin,dict) and set(pin)=={'blockHash','requireCanonical'} and pin['requireCanonical'] is True
        and isinstance(pin['blockHash'],str) and re.fullmatch(r'0x[0-9a-f]{64}',pin['blockHash']) and int(pin['blockHash'],16), 'canonical pin')
    if method=='eth_getStorageAt': probe.check(args[:-1]==[ORACLE,'0x1'], 'fallback slot'); return
    if method=='eth_getCode':
        probe.check(isinstance(args[0],str) and re.fullmatch(r'0x[0-9a-f]{40}',args[0]) and int(args[0],16), 'code address'); return
    q=args[0]; probe.check(isinstance(q,dict) and set(q)=={'to','data'}, 'call envelope')
    probe.check(re.fullmatch(r'0x[0-9a-f]{40}',q['to']) and int(q['to'],16), 'call address')
    allowed=([calldata('provider_oracle')] if q['to']==PROVIDER else
        [calldata(k) for k in ['provider','base','unit','fallback']] +
        [calldata(k,a) for k in ['source','price'] for a in ASSETS] if q['to']==ORACLE else [calldata('answer')])
    probe.check(q['data'] in allowed, 'closed getter scope')


class Rpc:
    def __init__(self): self.sequence=0; self.last=0
    def __call__(self, provider, method, args):
        validate(provider,method,args); probe.check(self.sequence<MAX_REQUESTS,'request budget')
        time.sleep(max(0,.125-(time.monotonic()-self.last))); self.last=time.monotonic(); self.sequence+=1
        q={'jsonrpc':'2.0','id':self.sequence,'method':method,'params':args}
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs): return None
        req=urllib.request.Request(PROVIDERS[provider],data=json.dumps(q).encode(),headers={'Content-Type':'application/json','User-Agent':'nqc-miner-oracle-research'})
        with urllib.request.build_opener(NoRedirect).open(req,timeout=20) as r: raw=r.read(1_048_577)
        probe.check(len(raw)<=1_048_576,'oversize reply'); a=json.loads(raw)
        probe.check(a.get('jsonrpc')=='2.0' and type(a.get('id')) is int and a['id']==self.sequence and 'result' in a and 'error' not in a,'RPC envelope')
        return {'request':q,'response':a}


def capture_one(plan, query):
    block,event=plan['block'],plan['event_anchor']; records=[]; observations=[]
    def read(provider,method,args):
        validate(provider,method,args); r=query(provider,method,args); value=r['response']['result']
        if method=='eth_getBlockByNumber': value={k:value[k] for k in ['number','hash','parentHash','timestamp']}
        records.append({'provider_id':provider,'request':r['request'],'response':{**r['response'],'result':value}})
        return value
    def header(provider,expected):
        probe.check(probe.same(probe.header(read(provider,'eth_getBlockByNumber',[hex(expected['number']),False])),expected),'header changed')
    for provider in PROVIDERS:
        probe.check(read(provider,'eth_chainId',[])=='0x1','chain')
        finalized=probe.header(read(provider,'eth_getBlockByNumber',['finalized',False]))
        probe.check(finalized['number']>=event['number'],'finality'); header(provider,block); header(provider,event)
        pin={'blockHash':block['hash'],'requireCanonical':True}
        def call(to,kind,asset=None): return read(provider,'eth_call',[{'to':to,'data':calldata(kind,asset)},pin])
        probe.check(address_word(call(PROVIDER,'provider_oracle'))==ORACLE,'provider oracle routing')
        code=read(provider,'eth_getCode',[ORACLE,pin]); probe.code_bytes(code)
        imm={'ADDRESSES_PROVIDER':call(ORACLE,'provider'),'BASE_CURRENCY':call(ORACLE,'base'),'BASE_CURRENCY_UNIT':call(ORACLE,'unit')}
        probe.check(address_word(imm['ADDRESSES_PROVIDER'])==PROVIDER,'immutable provider')
        probe.check(address_word(imm['BASE_CURRENCY'],True)=='0x'+'00'*20 and word(imm['BASE_CURRENCY_UNIT'])==10**8,'base currency profile')
        fallback=call(ORACLE,'fallback'); address_word(fallback,True)
        probe.check(read(provider,'eth_getStorageAt',[ORACLE,'0x1',pin])==fallback,'fallback storage/getter')
        feeds=[]
        for asset in ASSETS:
            source=address_word(call(ORACLE,'source',asset))
            price=call(ORACLE,'price',asset); word(price)
            runtime=read(provider,'eth_getCode',[source,pin]); probe.code_bytes(runtime)
            answer=call(source,'answer'); raw=word(answer); signed=raw if raw<2**255 else raw-2**256
            probe.check(signed>0 and raw==word(price),'observed positive feed/price equality')
            feeds.append({'asset':asset,'source':source,'price_word':price,'answer_word':answer,
                'runtime_code':runtime,'runtime_sha256':probe.sha(probe.code_bytes(runtime))})
        observations.append({'runtime_code':code,'runtime_sha256':probe.sha(probe.code_bytes(code)),
            'immutable_words':imm,'fallback_word':fallback,'feeds':feeds})
        header(provider,block); header(provider,event); header(provider,finalized)
    probe.check(probe.same(*observations),'provider disagreement')
    for provider in PROVIDERS: header(provider,block); header(provider,event)
    return {'schema':'nqc-miner-aave-oracle-observation-v1',**plan,'oracle':ORACLE,**observations[0],
        'records':records,'historical_state_authenticated':False,'transaction_prestate':False,
        'price_freshness_verified':False,'activation_allowed':False}


def replay(directory=None):
    directory=directory or DIRECTORY/'public'; manifest=probe.load(directory/'manifest.json')
    probe.check(manifest['complete'] is True and manifest['capture_sha256']==probe.sha(Path(__file__).read_bytes()),'capture integrity')
    probe.check(len(manifest['observations'])==3,'coverage'); results=[]; sequence=0
    for n,(entry,plan) in enumerate(zip(manifest['observations'],prior.plans())):
        probe.check(entry['file']==f'oracle-{n:03d}.json','capture path'); path=directory/entry['file']
        probe.check(probe.sha(path.read_bytes())==entry['sha256'],'capture hash')
        original=probe.load(path); records=iter(original['records'])
        def query(provider,method,args):
            nonlocal sequence
            sequence+=1; record=next(records); q,a=record['request'],record['response']
            probe.check(record['provider_id']==provider and q['method']==method and probe.same(q['params'],args),'request sequence')
            probe.check(q['jsonrpc']==a['jsonrpc']=='2.0' and type(q['id']) is int and type(a['id']) is int and q['id']==a['id']==sequence and 'error' not in a,'response identity')
            return {'request':q,'response':a}
        result=capture_one(plan,query)
        probe.check(next(records,None) is None and probe.same(result,original),'capture replay'); results.append(result)
    probe.check(sequence==manifest['requests']==MAX_REQUESTS,'request coverage'); return results


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--output',type=Path,required=True); args=p.parse_args()
    probe.check(not any(p.is_symlink() for p in (args.output,*args.output.parents)),'output symlink')
    args.output.mkdir(parents=True,exist_ok=False); rpc=Rpc(); entries=[]; start=datetime.now(timezone.utc).isoformat()
    for n,plan in enumerate(prior.plans()):
        try:
            value=capture_one(plan,rpc); name=f'oracle-{n:03d}.json'; probe.save(args.output/name,value)
            entries.append({'file':name,'sha256':probe.sha((args.output/name).read_bytes())})
        except Exception as error:
            probe.save(args.output/'failure.json',{'index':n,'requests':rpc.sequence,'error_type':type(error).__name__,'complete':False}); raise
    probe.save(args.output/'manifest.json',{'schema':'nqc-miner-aave-oracle-capture-v1','complete':True,
        'observations':entries,'requests':rpc.sequence,'capture_sha256':probe.sha(Path(__file__).read_bytes()),
        'started_at_utc':start,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'new_liquidation_events':0})
    print(json.dumps({'complete':True,'requests':rpc.sequence,'blocks':3}))


if __name__=='__main__': main()
