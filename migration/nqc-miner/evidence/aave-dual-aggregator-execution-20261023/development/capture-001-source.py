#!/usr/bin/env python3
"""Bounded batched reads of DualAggregator rounds; never sends transactions."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import urllib.request
import capture_aave_weth_feed as prior
from evm_word_pair_slot import word_pair_slot

identity,probe=prior.identity,prior.probe
DIRECTORY=identity.MODULE/'evidence/aave-dual-aggregator-execution-20261023'
AGGREGATOR='0x7c7fdfca295a787ded12bb5c1a49a8d2cc20e3f8'
PROXY=prior.PROXY
PROVIDERS=dict(prior.PROVIDERS)
MAX_SYNC=20
MAX_REQUESTS=228
SELECTORS={'min':'22adbc78','max':'70da2f67','decimals':'313ce567','round':'feaf968c'}


def validate(provider,method,args):
    probe.check(provider in PROVIDERS,'provider')
    if method in {'eth_chainId','eth_getBlockByNumber'}: return prior.validate(provider,method,args)
    probe.check(method in {'eth_getCode','eth_getStorageAt','eth_call'},'read-only method')
    probe.check(len(args)==(3 if method=='eth_getStorageAt' else 2),'argument count')
    pin=args[-1]
    probe.check(isinstance(pin,dict) and set(pin)=={'blockHash','requireCanonical'} and pin['requireCanonical'] is True
        and isinstance(pin['blockHash'],str) and re.fullmatch(r'0x[0-9a-f]{64}',pin['blockHash']) and int(pin['blockHash'],16),'canonical pin')
    if method=='eth_getCode': probe.check(args[0]==AGGREGATOR,'code address');return
    if method=='eth_getStorageAt':
        probe.check(args[0]==AGGREGATOR and (args[1] in ['0xd','0x12'] or re.fullmatch(r'0x[0-9a-f]{64}',args[1])),'storage address/key');return
    q=args[0];probe.check(isinstance(q,dict) and set(q) in [{'to','data'},{'to','data','from'}],'call envelope')
    probe.check(q['to']==AGGREGATOR and q['data'] in ['0x'+v for v in SELECTORS.values()],'closed getters')
    if 'from' in q: probe.check(q['from']==PROXY and q['data']=='0x'+SELECTORS['round'],'proxy caller scope')


def normalize_batch(requests,response):
    probe.check(isinstance(response,list) and len(response)==len(requests),'batch response coverage')
    ids=[r.get('id') for r in response]
    probe.check(all(type(i) is int for i in ids) and len(set(ids))==len(ids) and set(ids)=={q['id'] for q in requests},'batch identities')
    by_id={r['id']:r for r in response}; result=[]
    for q in requests:
        a=by_id[q['id']];probe.check(a.get('jsonrpc')=='2.0' and 'result' in a and 'error' not in a,'RPC envelope')
        result.append({'request':q,'response':a})
    return result


class Rpc:
    def __init__(self):self.sequence=0;self.batches=0
    def __call__(self,provider,calls):
        probe.check(0<len(calls)<=21 and self.sequence+len(calls)<=MAX_REQUESTS,'request budget')
        requests=[]
        for method,args in calls:
            validate(provider,method,args);self.sequence+=1
            requests.append({'jsonrpc':'2.0','id':self.sequence,'method':method,'params':args})
        self.batches+=1
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args,**kwargs):return None
        q=urllib.request.Request(PROVIDERS[provider],data=json.dumps(requests).encode(),headers={'Content-Type':'application/json','User-Agent':'nqc-miner-dual-research'})
        with urllib.request.build_opener(NoRedirect).open(q,timeout=30) as r:raw=r.read(2_000_001)
        probe.check(len(raw)<=2_000_000,'reply size')
        return normalize_batch(requests,json.loads(raw))


def decode_round(raw):
    probe.check(isinstance(raw,str) and re.fullmatch(r'0x[0-9a-f]{320}',raw),'round ABI')
    values=[int(raw[i:i+64],16) for i in range(2,322,64)]
    probe.check(values[0]<2**32 and values[2]<2**32 and values[3]<2**32 and values[4]==values[0],'round fields')
    signed=values[1] if values[1]<2**255 else values[1]-2**256
    probe.check(-2**191<=signed<2**191,'int192 answer');return values


def capture_one(old,query):
    block,event=old['block'],old['event_anchor'];records=[];observations=[]
    probe.check(old['aggregator']==AGGREGATOR,'retained aggregator route')
    def read(provider,calls):
        for method,args in calls:validate(provider,method,args)
        rows=query(provider,calls);probe.check(len(rows)==len(calls),'batch coverage');values=[]
        for row,(method,args) in zip(rows,calls):
            value=row['response']['result']
            if method=='eth_getBlockByNumber':value={k:value[k] for k in ['number','hash','parentHash','timestamp']}
            records.append({'provider_id':provider,'request':row['request'],'response':{**row['response'],'result':value}});values.append(value)
        return values
    def header_call(b):return ('eth_getBlockByNumber',[hex(b['number']),False])
    def check_headers(values,expected):
        for value,want in zip(values,expected):probe.check(probe.same(probe.header(value),want),'header changed')
    for provider in PROVIDERS:
        chain,finalized,b,e=read(provider,[('eth_chainId',[]),('eth_getBlockByNumber',['finalized',False]),header_call(block),header_call(event)])
        probe.check(chain=='0x1','chain');finalized=probe.header(finalized);probe.check(finalized['number']>=event['number'],'finality');check_headers([b,e],[block,event])
        pin={'blockHash':block['hash'],'requireCanonical':True}
        def call(kind,secondary=False):
            q={'to':AGGREGATOR,'data':'0x'+SELECTORS[kind]}
            if secondary:q['from']=PROXY
            return ('eth_call',[q,pin])
        code,minimum,maximum,decimals,hot,cutoff,direct,secondary=read(provider,[('eth_getCode',[AGGREGATOR,pin]),call('min'),call('max'),call('decimals'),
            ('eth_getStorageAt',[AGGREGATOR,'0xd',pin]),('eth_getStorageAt',[AGGREGATOR,'0x12',pin]),call('round'),call('round',True)])
        probe.check(code==old['aggregator_runtime_code'],'retained aggregator code')
        for w in [minimum,maximum,decimals,hot,cutoff]:prior.prior.word(w)
        dv,sv=decode_round(direct),decode_round(secondary)
        probe.check(dv[1]==int(old['direct_aggregator_answer_word'],16) and sv[1]==int(old['answer_word'],16),'retained answers')
        hot_n=int(hot,16);latest=(hot_n>>48)&(2**32-1);last_secondary=(hot_n>>80)&(2**32-1)
        rounds=sorted(set(range(max(1,latest-MAX_SYNC+1),latest+1))|{last_secondary,dv[0],sv[0]})
        probe.check(len(rounds)<=21,'round coverage budget')
        slots=[word_pair_slot(n,17) for n in rounds]
        words=read(provider,[('eth_getStorageAt',[AGGREGATOR,slot,pin]) for slot in slots])
        transmissions=[]
        for n,slot,word in zip(rounds,slots,words):
            prior.prior.word(word);transmissions.append({'round':n,'slot':slot,'word':word})
        by_round={t['round']:int(t['word'],16) for t in transmissions}
        for row in [dv,sv]:
            expected=(row[1]%(2**192))|(row[2]<<192)|(row[3]<<224)
            probe.check(by_round[row[0]]==expected,'round getter/storage')
        observations.append({'runtime_code':code,'runtime_sha256':probe.sha(probe.code_bytes(code)),
            'immutable_getters':{'i_minAnswer':minimum,'i_maxAnswer':maximum,'i_decimals':decimals},
            'hot_word':hot,'cutoff_word':cutoff,'direct_round_data':direct,'secondary_round_data':secondary,'transmissions':transmissions})
        check_headers(read(provider,[header_call(b) for b in [block,event,finalized]]),[block,event,finalized])
    probe.check(probe.same(*observations),'provider disagreement')
    for provider in PROVIDERS:check_headers(read(provider,[header_call(block),header_call(event)]),[block,event])
    return {'schema':'nqc-miner-dual-observation-v1','block':block,'event_anchor':event,'aggregator':AGGREGATOR,**observations[0],
        'records':records,'historical_state_authenticated':False,'price_freshness_verified':False,'activation_allowed':False}


def replay(directory=None):
    directory=directory or DIRECTORY/'public';m=probe.load(directory/'manifest.json')
    probe.check(m['complete'] is True and m['capture_sha256']==probe.sha(Path(__file__).read_bytes())
        and m['slot_helper_sha256']==probe.sha(Path(__file__).with_name('evm_word_pair_slot.py').read_bytes()),'capture integrity')
    probe.check(len(m['observations'])==3,'coverage');results=[];sequence=0
    for n,(entry,old) in enumerate(zip(m['observations'],prior.replay())):
        probe.check(entry['file']==f'dual-{n:03d}.json','capture path');p=directory/entry['file'];probe.check(probe.sha(p.read_bytes())==entry['sha256'],'capture hash')
        original=probe.load(p);rows=iter(original['records'])
        def query(provider,calls):
            nonlocal sequence
            results=[]
            for method,args in calls:
                sequence+=1;r=next(rows);q,a=r['request'],r['response']
                probe.check(r['provider_id']==provider and q['jsonrpc']==a['jsonrpc']=='2.0' and q['method']==method and probe.same(q['params'],args),'request sequence')
                probe.check(type(q['id']) is int and type(a['id']) is int and q['id']==a['id']==sequence and 'error' not in a,'response identity');results.append({'request':q,'response':a})
            return results
        result=capture_one(old,query);probe.check(next(rows,None) is None and probe.same(result,original),'capture replay');results.append(result)
    probe.check(sequence==m['requests'] and sequence<=MAX_REQUESTS and m['batches']==30,'request coverage');return results


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    probe.check(not any(p.is_symlink() for p in [a.output,*a.output.parents]),'output symlink');a.output.mkdir(parents=True,exist_ok=False)
    rpc=Rpc();entries=[];start=datetime.now(timezone.utc).isoformat()
    for n,old in enumerate(prior.replay()):
        try:
            value=capture_one(old,rpc);name=f'dual-{n:03d}.json';probe.save(a.output/name,value);entries.append({'file':name,'sha256':probe.sha((a.output/name).read_bytes())})
            print(json.dumps({'block':value['block']['number'],'requests':rpc.sequence,'rounds':len(value['transmissions'])}),flush=True)
        except Exception as error:
            probe.save(a.output/'failure.json',{'index':n,'requests':rpc.sequence,'batches':rpc.batches,'error_type':type(error).__name__,'complete':False});raise
    probe.save(a.output/'manifest.json',{'complete':True,'observations':entries,'requests':rpc.sequence,'batches':rpc.batches,
        'capture_sha256':probe.sha(Path(__file__).read_bytes()),'slot_helper_sha256':probe.sha(Path(__file__).with_name('evm_word_pair_slot.py').read_bytes()),
        'started_at_utc':start,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'new_liquidation_events':0})


if __name__=='__main__':main()
