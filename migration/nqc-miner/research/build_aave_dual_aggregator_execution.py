#!/usr/bin/env python3
"""Recompile observed DualAggregator and bind its read path to retained round slots."""
import argparse
import copy
import gzip
import json
from pathlib import Path
import subprocess
import tempfile
import build_aave_weth_feed_execution as feed
import capture_aave_dual_aggregator as capture

identity=feed.identity
DIRECTORY=capture.DIRECTORY
SOURCE='src/DualAggregator.sol'
CONTRACT='DualAggregator'
VERSION='0.8.24+commit.e11b9ed9'
CHECKSUM='fb03a29a517452b9f12bcf459ef37d0a543765bb3bbc911e70a87d6a37c30d5f'


def compilation_input():
    raw=gzip.decompress((DIRECTORY/'source.json.gz').read_bytes());r=identity.read_json(DIRECTORY/'retrieval.json');s=json.loads(raw)
    identity.check(r['sha256']==identity.sha(raw) and r['bytes']==len(raw) and r['url']=='https://sourcify.dev/server/v2/contract/1/'+capture.AGGREGATOR+'?fields=all','source retrieval')
    identity.check(s['chainId']=='1' and s['address'].lower()==capture.AGGREGATOR and s['compilation']['compilerVersion']==VERSION
        and s['compilation']['fullyQualifiedName']==SOURCE+':'+CONTRACT,'source identity')
    index=identity.read_json(identity.EVIDENCE/'compiler-list.json.gz');build=next(b for b in index['builds'] if b['longVersion']==VERSION)
    cr=identity.read_json(DIRECTORY/'compiler-retrieval.json')
    identity.check(build['sha256']=='0x'+CHECKSUM and cr['sha256']==CHECKSUM and cr['url']=='https://raw.githubusercontent.com/ethereum/solc-bin/gh-pages/linux-amd64/'+build['path'],'compiler provenance')
    v=copy.deepcopy(s['stdJsonInput'])
    identity.check(v['sources']==s['sources'] and v['settings']==s['compilation']['compilerSettings'],'unchanged source/settings')
    identity.check(all(set(x)=={'content'} and isinstance(x['content'],str) for x in v['sources'].values()),'literal sources')
    v['settings']['outputSelection']={SOURCE:{CONTRACT:['evm.deployedBytecode','evm.methodIdentifiers','storageLayout'],'':['ast']}}
    return s,v


def compile_source(compiler,value):
    identity.check(identity.sha(compiler.read_bytes())==CHECKSUM,'compiler checksum')
    r=subprocess.run([str(compiler),'--version'],capture_output=True,check=True);identity.check(VERSION in r.stdout.decode(),'compiler version')
    with tempfile.TemporaryDirectory(prefix='nqc-dual-solc-') as cwd:
        r=subprocess.run([str(compiler.resolve()),'--standard-json','--no-import-callback'],input=identity.encoded(value),cwd=cwd,capture_output=True,timeout=120,check=True)
    identity.check(len(r.stdout)<=16_000_000 and len(r.stderr)<=100_000,'compiler output bounds');return r.stdout,r.stderr


def audit(value,raw,history):
    source,expected=compilation_input();identity.check(value==expected,'compilation input')
    out=json.loads(raw);identity.check(not any(e.get('severity')=='error' for e in out.get('errors',[])),'compiler errors')
    c=out['contracts'][SOURCE][CONTRACT];b=c['evm']['deployedBytecode'];identity.check(not b['linkReferences'],'links')
    definitions=[n for n in out['sources'][SOURCE]['ast']['nodes'] if n.get('nodeType')=='ContractDefinition' and n['name']==CONTRACT]
    identity.check(len(definitions)==1,'contract AST')
    names={str(n['id']):n['name'] for n in definitions[0]['nodes'] if n.get('mutability')=='immutable'}
    identity.check(set(names.values())=={'i_minAnswer','i_maxAnswer','i_decimals','i_secondaryProxy','i_maxSyncIterations'} and len(names)==5,'immutable declarations')
    identity.check(set(b['immutableReferences'])==set(names),'immutable coverage')
    identity.check(len(history)==3 and [h['block']['number'] for h in history]==list(identity.BLOCKS),'historical coverage')
    observed=bytes.fromhex(history[0]['runtime_code'][2:]);runtime=bytearray.fromhex(b['object'])
    identity.check(len(observed)==len(runtime),'runtime length');words={};edits=[];touched=set()
    for key,refs in b['immutableReferences'].items():
        identity.check(bool(refs),'empty immutable references')
        for ref in refs:
            offset,length=ref['start'],ref['length'];positions=set(range(offset,offset+length))
            identity.check(length==32 and 0<=offset and offset+32<=len(runtime) and not positions&touched and runtime[offset:offset+32]==bytes(32),'immutable bounds/placeholders')
            word='0x'+observed[offset:offset+32].hex();name=names[key]
            identity.check(name not in words or words[name]==word,'consistent immutable occurrences')
            words[name]=word;touched|=positions;runtime[offset:offset+32]=observed[offset:offset+32]
            edits.append({'name':name,'offset':offset,'length':length,'word':word})
    code='0x'+runtime.hex()
    identity.check(code==source['runtimeBytecode']['onchainBytecode'],'complete published runtime equality')
    identity.check(int(words['i_secondaryProxy'],16)==int(capture.PROXY,16) and int(words['i_maxSyncIterations'],16)==capture.MAX_SYNC
        and int(words['i_decimals'],16)==8,'immutable route/profile')
    for h in history:
        identity.check(h['aggregator']==capture.AGGREGATOR and h['runtime_code']==code,'complete observed runtime equality')
        identity.check(all(words[k]==v for k,v in h['immutable_getters'].items()) and set(h['immutable_getters'])=={'i_minAnswer','i_maxAnswer','i_decimals'},'immutable getter equality')
    selectors=c['evm']['methodIdentifiers']
    for kind,sig in [('min','minAnswer()'),('max','maxAnswer()'),('decimals','decimals()'),('round','latestRoundData()')]:
        identity.check(selectors[sig]==capture.SELECTORS[kind],'capture selectors')
    layout=c['storageLayout'];fields={x['label']:x for x in layout['storage']}
    for label,slot in [('s_hotVars','13'),('s_transmissions','17'),('s_cutoffTime','18')]:
        identity.check(fields[label]['slot']==slot and fields[label]['offset']==0,'storage roots')
    hot=layout['types'][fields['s_hotVars']['type']]['members']
    h={x['label']:x for x in hot}
    for label,offset in [('latestAggregatorRoundId',6),('latestSecondaryRoundId',10),('isLatestSecondary',30)]:
        identity.check(h[label]['slot']=='0' and h[label]['offset']==offset,'hot variable layout')
    mapping=layout['types'][fields['s_transmissions']['type']];members=layout['types'][mapping['value']]['members']
    identity.check([(x['label'],x['slot'],x['offset']) for x in members]==[('answer','0',0),('observationsTimestamp','0',24),('recordedTimestamp','0',28)],'transmission layout')
    identity.check([layout['types'][x['type']]['numberOfBytes'] for x in members]==['24','4','4'],'transmission widths')
    return {'runtime_code':code,'runtime_sha256':identity.sha(runtime),'runtime_bytes':len(runtime),'selectors':selectors,
        'storage_layout':layout,'immutable_words':words,'immutable_substitutions':edits,
        'compiler_version':VERSION,'compiler_sha256':CHECKSUM,'source_files':{n:identity.sha(v['content'].encode()) for n,v in source['sources'].items()},
        'full_runtime_recompiled_match':True,'metadata_bytes_compared':True,'metadata_source_hash_present':False,
        'original_source_text_authenticated':False,'canonical_code_proof_verified':False}


def fixture(value,raw):
    history=capture.replay();dual=audit(value,raw,history);p=feed.DIRECTORY/'compiler'
    result=feed.fixture(identity.read_json(p/'input.json.gz'),gzip.decompress((p/'output.json.gz').read_bytes()),
        identity.read_json(p/'proxy-input.json.gz'),gzip.decompress((p/'proxy-output.json.gz').read_bytes()))
    result['contracts'][CONTRACT]=dual
    result.update(schema='nqc-miner-dual-aggregator-execution-fixture-v1',dual_compiler_input_sha256=identity.sha(identity.encoded(value)),
        dual_compiler_output_sha256=identity.sha(raw),previous_weth_feed_fixture_sha256=identity.sha((identity.MODULE/'fixtures/aave_weth_feed_execution.json').read_bytes()),
        oracle_kind='observed_aave_oracle_weth_proxy_and_dual_aggregator_with_supplied_state',
        feed_kind='observed_weth_chain_with_synthetic_usdc_feed',weth_aggregator_runtime_executed=True,
        weth_aggregator_runtime_recompiled_match=True,round_selection_executed=True,round_storage_observed=True,
        feed_answers_supplied=True,feed_state_authenticated=False,price_freshness_verified=False,
        dual_observations=[{k:h[k] for k in ['block','hot_word','cutoff_word','direct_round_data','secondary_round_data','transmissions']} for h in history],
        slot_vectors=[{'key':str(k),'root':str(r),'slot':capture.word_pair_slot(k,r)} for k,r in [(0,0),(0,17),(1,17),(2**32-1,17),(2**256-1,2**256-1)]+[(n*7919,n*37) for n in range(1,33)]])
    return result


def build(compiler,output):
    _,value=compilation_input();raw,err=compile_source(compiler,value);result=fixture(value,raw);output.mkdir(parents=True,exist_ok=False)
    for name,data in [('input.json.gz',identity.encoded(value)),('output.json.gz',raw)]: (output/name).write_bytes(gzip.compress(data,mtime=0))
    (output/'compiler.stderr').write_bytes(err);(identity.MODULE/'fixtures/aave_dual_aggregator_execution.json').write_bytes(identity.encoded(result))
    print(json.dumps({'runtime_bytes':result['contracts'][CONTRACT]['runtime_bytes'],'immutable_occurrences':len(result['contracts'][CONTRACT]['immutable_substitutions']),'observed_blocks':3}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();build(a.compiler,a.output)
