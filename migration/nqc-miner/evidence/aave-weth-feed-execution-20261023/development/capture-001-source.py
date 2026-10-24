#!/usr/bin/env python3
"""Read-only, bounded WETH feed proxy routing at the three retained block hashes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
import urllib.request
import capture_aave_oracle as prior

identity, probe = prior.identity, prior.probe
DIRECTORY = identity.MODULE / 'evidence/aave-weth-feed-execution-20261023'
PROXY = '0x5424384b256154046e9667ddfaaa5e550145215e'
PROVIDERS = dict(prior.PROVIDERS)
MAX_REQUESTS = 108
# Bound against unchanged Solidity compiler output in build_aave_weth_feed_execution.py.
SELECTORS = {'aggregator': '245a7bfc', 'phase': '58303b10', 'controller': 'bc43cbaf', 'answer': '50d25bcd'}


def validate(provider, method, args):
    probe.check(provider in PROVIDERS, 'provider')
    if method in {'eth_chainId', 'eth_getBlockByNumber'}:
        return prior.validate(provider, method, args)
    probe.check(method in {'eth_call', 'eth_getCode', 'eth_getStorageAt'}, 'read-only method')
    probe.check(len(args) == (3 if method == 'eth_getStorageAt' else 2), 'argument count')
    pin = args[-1]
    probe.check(isinstance(pin, dict) and set(pin) == {'blockHash', 'requireCanonical'}
        and pin['requireCanonical'] is True and isinstance(pin['blockHash'], str)
        and re.fullmatch(r'0x[0-9a-f]{64}', pin['blockHash']) and int(pin['blockHash'], 16), 'canonical pin')
    if method == 'eth_getStorageAt':
        probe.check(args[0] == PROXY and args[1] in ['0x2', '0x5'], 'closed proxy slots'); return
    if method == 'eth_getCode':
        probe.check(isinstance(args[0], str) and re.fullmatch(r'0x[0-9a-f]{40}', args[0]) and int(args[0],16), 'code address'); return
    q = args[0]
    probe.check(isinstance(q,dict) and set(q) == {'to','data'}, 'call envelope')
    probe.check(isinstance(q['to'],str) and re.fullmatch(r'0x[0-9a-f]{40}',q['to']) and int(q['to'],16), 'call address')
    allowed = list(SELECTORS.values()) if q['to'] == PROXY else [SELECTORS['answer']]
    probe.check(q['data'] in ['0x'+s for s in allowed], 'closed getters')


class Rpc:
    def __init__(self): self.sequence = 0; self.last = 0
    def __call__(self, provider, method, args):
        validate(provider,method,args); probe.check(self.sequence < MAX_REQUESTS, 'request budget')
        time.sleep(max(0,.125-(time.monotonic()-self.last))); self.last=time.monotonic(); self.sequence+=1
        q={'jsonrpc':'2.0','id':self.sequence,'method':method,'params':args}
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs): return None
        req=urllib.request.Request(PROVIDERS[provider],data=json.dumps(q).encode(),headers={'Content-Type':'application/json','User-Agent':'nqc-miner-weth-feed-research'})
        with urllib.request.build_opener(NoRedirect).open(req,timeout=20) as r: raw=r.read(1_048_577)
        probe.check(len(raw)<=1_048_576,'oversize reply'); a=json.loads(raw)
        probe.check(a.get('jsonrpc')=='2.0' and type(a.get('id')) is int and a['id']==self.sequence and 'result' in a and 'error' not in a,'RPC envelope')
        return {'request':q,'response':a}


def capture_one(oracle, query):
    block,event=oracle['block'],oracle['event_anchor']; records=[]; observations=[]
    old=next(f for f in oracle['feeds'] if f['asset']==prior.ASSETS[1])
    probe.check(old['source']==PROXY, 'retained WETH source')
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
        def call(to,kind): return read(provider,'eth_call',[{'to':to,'data':'0x'+SELECTORS[kind]},pin])
        code=read(provider,'eth_getCode',[PROXY,pin]); probe.check(code==old['runtime_code'],'retained proxy code')
        phase_word=read(provider,'eth_getStorageAt',[PROXY,'0x2',pin]); packed=prior.word(phase_word)
        controller_word=read(provider,'eth_getStorageAt',[PROXY,'0x5',pin])
        aggregator=prior.address_word(call(PROXY,'aggregator')); phase=prior.word(call(PROXY,'phase'))
        controller=prior.address_word(call(PROXY,'controller'),True)
        probe.check(phase<2**16 and packed==phase+(int(aggregator,16)<<16),'packed phase/aggregator')
        probe.check(prior.address_word(controller_word,True)==controller, 'controller storage/getter')
        answer=call(PROXY,'answer'); probe.check(answer==old['answer_word'], 'retained proxy answer')
        aggregator_code=read(provider,'eth_getCode',[aggregator,pin]); probe.code_bytes(aggregator_code)
        aggregator_answer=call(aggregator,'answer'); probe.check(answer==aggregator_answer, 'underlying answer')
        observations.append({'runtime_code':code,'runtime_sha256':probe.sha(probe.code_bytes(code)),
            'phase_word':phase_word,'phase_id':phase,'aggregator':aggregator,
            'controller_word':controller_word,'controller':controller,'answer_word':answer,
            'aggregator_runtime_code':aggregator_code,'aggregator_runtime_sha256':probe.sha(probe.code_bytes(aggregator_code))})
        header(provider,block); header(provider,event); header(provider,finalized)
    probe.check(probe.same(*observations),'provider disagreement')
    for provider in PROVIDERS: header(provider,block); header(provider,event)
    return {'schema':'nqc-miner-weth-feed-observation-v1','block':block,'event_anchor':event,'proxy':PROXY,
        **observations[0],'records':records,'historical_state_authenticated':False,
        'transaction_prestate':False,'price_freshness_verified':False,'activation_allowed':False}


def replay(directory=None):
    directory=directory or DIRECTORY/'public'; manifest=probe.load(directory/'manifest.json')
    probe.check(manifest['complete'] is True and manifest['capture_sha256']==probe.sha(Path(__file__).read_bytes()),'capture integrity')
    probe.check(len(manifest['observations'])==3,'coverage'); results=[]; sequence=0
    for n,(entry,oracle) in enumerate(zip(manifest['observations'],prior.replay())):
        probe.check(entry['file']==f'feed-{n:03d}.json','capture path'); path=directory/entry['file']
        probe.check(probe.sha(path.read_bytes())==entry['sha256'],'capture hash')
        original=probe.load(path); records=iter(original['records'])
        def query(provider,method,args):
            nonlocal sequence
            sequence+=1; record=next(records); q,a=record['request'],record['response']
            probe.check(record['provider_id']==provider and q['method']==method and probe.same(q['params'],args),'request sequence')
            probe.check(q['jsonrpc']==a['jsonrpc']=='2.0' and type(q['id']) is int and type(a['id']) is int and q['id']==a['id']==sequence and 'error' not in a,'response identity')
            return {'request':q,'response':a}
        result=capture_one(oracle,query)
        probe.check(next(records,None) is None and probe.same(result,original),'capture replay'); results.append(result)
    probe.check(sequence==manifest['requests']==MAX_REQUESTS,'request coverage'); return results


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--output',type=Path,required=True); args=p.parse_args()
    probe.check(not any(p.is_symlink() for p in (args.output,*args.output.parents)),'output symlink')
    args.output.mkdir(parents=True,exist_ok=False); rpc=Rpc(); entries=[]; start=datetime.now(timezone.utc).isoformat()
    for n,oracle in enumerate(prior.replay()):
        try:
            value=capture_one(oracle,rpc); name=f'feed-{n:03d}.json'; probe.save(args.output/name,value)
            entries.append({'file':name,'sha256':probe.sha((args.output/name).read_bytes())})
            print(json.dumps({'block':value['block']['number'],'requests':rpc.sequence,'aggregator':value['aggregator'],'phase':value['phase_id'],'controller':value['controller']}),flush=True)
        except Exception as error:
            probe.save(args.output/'failure.json',{'index':n,'requests':rpc.sequence,'error_type':type(error).__name__,'complete':False}); raise
    probe.save(args.output/'manifest.json',{'schema':'nqc-miner-weth-feed-capture-v1','complete':True,
        'observations':entries,'requests':rpc.sequence,'capture_sha256':probe.sha(Path(__file__).read_bytes()),
        'started_at_utc':start,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'new_liquidation_events':0})


if __name__=='__main__': main()
