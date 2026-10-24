#!/usr/bin/env python3
"""Execute the observed WETH EACAggregatorProxy; downstream prices remain supplied."""
import argparse
import copy
import gzip
import json
from pathlib import Path
import subprocess
import tempfile
import build_aave_oracle_execution as oracle
import capture_aave_weth_feed as capture

identity = oracle.identity
DIRECTORY = capture.DIRECTORY
NAME = 'fixtures/SyntheticFeedAccessController.sol'
CONTRACT = 'SyntheticFeedAccessController'
PROXY_PATH = '/Users/yos/chainlink2/evm-contracts/src/v0.6/EACAggregatorProxy.sol'
VERSION = '0.6.6+commit.6c089d02'
CHECKSUM = '5d8cd4e0cc02e9946497db68c06d56326a78ff95a21c9265cfedb819a10a539d'
HARNESS = '''// SPDX-License-Identifier: UNLICENSED
pragma solidity 0.8.27;
// Explicit test double, not the observed Chainlink controller.
contract SyntheticFeedAccessController {
  uint256 private allowed;
  uint256 private blocked;
  address private expectedUser;
  address private expectedProxy;
  function hasAccess(address user, bytes calldata data) external view returns (bool) {
    require(blocked == 0, "synthetic controller blocked");
    return allowed != 0 && user == expectedUser && msg.sender == expectedProxy
      && keccak256(data) == keccak256(hex"50d25bcd");
  }
}
// Only models caller-dependent answers; it is not Chainlink DualAggregator code.
contract SyntheticCallerSensitiveFeed {
  uint256 private expectedProxy;
  int256 private proxyAnswer;
  int256 private directAnswer;
  function latestAnswer() external view returns (int256) {
    return msg.sender == address(uint160(expectedProxy)) ? proxyAnswer : directAnswer;
  }
}
'''


def proxy_input():
    raw=gzip.decompress((DIRECTORY/'source.json.gz').read_bytes()); retrieval=identity.read_json(DIRECTORY/'retrieval.json')
    identity.check(retrieval['url']=='https://sourcify.dev/server/v2/contract/1/'+capture.PROXY+'?fields=all'
        and retrieval['sha256']==identity.sha(raw) and retrieval['bytes']==len(raw),'feed source retrieval')
    source=json.loads(raw)
    identity.check(source['chainId']=='1' and source['address'].lower()==capture.PROXY and
        source['compilation']['compilerVersion']==VERSION and source['compilation']['fullyQualifiedName']==PROXY_PATH+':EACAggregatorProxy','feed source identity')
    index=identity.read_json(identity.EVIDENCE/'compiler-list.json.gz')
    build=next(b for b in index['builds'] if b['longVersion']==VERSION)
    identity.check(build['sha256']=='0x'+CHECKSUM,'feed compiler index')
    cr=identity.read_json(DIRECTORY/'compiler-retrieval.json')
    identity.check(cr['sha256']==CHECKSUM and cr['url']=='https://raw.githubusercontent.com/ethereum/solc-bin/gh-pages/linux-amd64/'+build['path'],'compiler retrieval')
    value=copy.deepcopy(source['stdJsonInput'])
    identity.check(value['sources']==source['sources'] and value['settings']==source['compilation']['compilerSettings'],'unchanged feed sources/settings')
    identity.check(all(set(s)=={'content'} and isinstance(s['content'],str) for s in value['sources'].values()),'literal feed sources')
    value['settings']['outputSelection']={PROXY_PATH:{'EACAggregatorProxy':['evm.deployedBytecode','evm.methodIdentifiers','storageLayout']}}
    return source,value


def compile_proxy(compiler,value):
    identity.check(identity.sha(compiler.read_bytes())==CHECKSUM,'feed compiler checksum')
    version=subprocess.run([str(compiler),'--version'],capture_output=True,check=True).stdout.decode()
    identity.check(VERSION in version,'feed compiler version')
    # This historical compiler has no --no-import-callback; all sources are literal.
    with tempfile.TemporaryDirectory(prefix='nqc-weth-feed-solc-') as cwd:
        result=subprocess.run([str(compiler.resolve()),'--standard-json'],input=identity.encoded(value),cwd=cwd,capture_output=True,timeout=120,check=True)
    identity.check(len(result.stdout)<=16_000_000 and len(result.stderr)<=100_000,'compiler output size')
    return result.stdout,result.stderr


def audit_proxy(value,raw,history):
    source,expected=proxy_input(); identity.check(value==expected,'feed compilation input')
    out=json.loads(raw); identity.check(not any(e.get('severity')=='error' for e in out.get('errors',[])),'feed compiler errors')
    contract=out['contracts'][PROXY_PATH]['EACAggregatorProxy']; bytecode=contract['evm']['deployedBytecode']
    identity.check(not bytecode['linkReferences'] and not bytecode['immutableReferences'],'feed deployment references')
    code='0x'+bytecode['object']
    identity.check(code==source['runtimeBytecode']['onchainBytecode'],'full feed runtime including metadata')
    identity.check(len(history)==3 and [h['block']['number'] for h in history]==list(identity.BLOCKS),'feed coverage')
    for h in history: identity.check(h['proxy']==capture.PROXY and h['runtime_code']==code,'historical feed runtime')
    selectors=contract['evm']['methodIdentifiers']
    for kind,sig in [('aggregator','aggregator()'),('phase','phaseId()'),('controller','accessController()'),('answer','latestAnswer()')]:
        identity.check(selectors[sig]==capture.SELECTORS[kind],'feed getter selectors')
    layout=contract['storageLayout']; fields={f['label']:f for f in layout['storage']}
    identity.check(fields['currentPhase']['slot']=='2' and fields['currentPhase']['offset']==0
        and fields['accessController']['slot']=='5' and fields['accessController']['offset']==0,'proxy routing slots')
    members=layout['types'][fields['currentPhase']['type']]['members']
    identity.check([(m['label'],m['slot'],m['offset']) for m in members]==[('id','0',0),('aggregator','0',2)],'packed phase layout')
    identity.check([layout['types'][m['type']]['numberOfBytes'] for m in members]==['2','20'],'packed phase widths')
    return {'runtime_code':code,'runtime_sha256':identity.sha(bytes.fromhex(code[2:])), 'runtime_bytes':len(code[2:])//2,
        'selectors':selectors,'storage_layout':layout,'source_files':{n:identity.sha(v['content'].encode()) for n,v in source['sources'].items()},
        'compiler_version':VERSION,'compiler_sha256':CHECKSUM,'full_runtime_recompiled_match':True,
        'metadata_bytes_compared':True,'canonical_code_proof_verified':False}


def harness_input():
    return {'language':'Solidity','sources':{NAME:{'content':HARNESS}},'settings':{
        'optimizer':{'enabled':True,'runs':200},'evmVersion':'cancun','metadata':{'bytecodeHash':'ipfs'},
        'outputSelection':{NAME:{n:['evm.deployedBytecode','evm.methodIdentifiers','storageLayout'] for n in [CONTRACT,'SyntheticCallerSensitiveFeed']}}}}


def fixture(value,raw,proxy_value,proxy_raw):
    identity.check(value==harness_input(),'controller input')
    out=json.loads(raw); identity.check(not any(e.get('severity')=='error' for e in out.get('errors',[])),'controller compiler errors')
    history=capture.replay(); proxy=audit_proxy(proxy_value,proxy_raw,history)
    p=oracle.DIRECTORY/'compiler'
    result=oracle.fixture(identity.read_json(p/'input.json.gz'),gzip.decompress((p/'output.json.gz').read_bytes()),
        identity.read_json(p/'oracle-input.json.gz'),gzip.decompress((p/'oracle-output.json.gz').read_bytes()))
    for name in [CONTRACT,'SyntheticCallerSensitiveFeed']:
        c=out['contracts'][NAME][name]; code=c['evm']['deployedBytecode']
        identity.check(not code['linkReferences'] and not code['immutableReferences'],'double references')
        result['contracts'][name]={'runtime_code':'0x'+code['object'],'runtime_sha256':identity.sha(bytes.fromhex(code['object'])),
            'selectors':c['evm']['methodIdentifiers'],'storage_layout':c['storageLayout']}
    result['contracts']['EACAggregatorProxy']=proxy
    result.update(schema='nqc-miner-weth-feed-execution-fixture-v1',controller_compiler_input_sha256=identity.sha(identity.encoded(value)),
        controller_compiler_output_sha256=identity.sha(raw),controller_source_sha256=identity.sha(HARNESS.encode()),
        proxy_compiler_input_sha256=identity.sha(identity.encoded(proxy_value)),proxy_compiler_output_sha256=identity.sha(proxy_raw),
        previous_oracle_fixture_sha256=identity.sha((identity.MODULE/'fixtures/aave_oracle_execution.json').read_bytes()),
        oracle_kind='observed_aave_oracle_and_weth_feed_proxy_with_synthetic_downstream',weth_feed_proxy_address=capture.PROXY,
        feed_kind='observed_weth_proxy_with_synthetic_aggregator_and_usdc_feed',
        observed_feed_runtime_executed=True,all_observed_feed_runtimes_executed=False,
        weth_feed_proxy_runtime_executed=True,weth_feed_proxy_runtime_recompiled_match=True,
        weth_aggregator_runtime_executed=False,usdc_feed_runtime_executed=False,
        access_controller_test_double=True,feed_state_authenticated=False,feed_answers_supplied=True,price_freshness_verified=False,
        weth_feed_observations=[{k:h[k] for k in ['block','phase_word','phase_id','aggregator','controller_word','controller',
            'answer_word','direct_aggregator_answer_word','proxy_caller_answer_word','aggregator_runtime_sha256']} for h in history])
    return result


def build(compiler,proxy_compiler,output):
    _,pv=proxy_input(); praw,perr=compile_proxy(proxy_compiler,pv)
    value=harness_input(); raw,err=identity.compile_source(compiler,value)
    result=fixture(value,raw,pv,praw); output.mkdir(parents=True,exist_ok=False)
    for name,data in [('input.json.gz',identity.encoded(value)),('output.json.gz',raw),('proxy-input.json.gz',identity.encoded(pv)),('proxy-output.json.gz',praw)]:
        (output/name).write_bytes(gzip.compress(data,mtime=0))
    (output/'compiler.stderr').write_bytes(err); (output/'proxy-compiler.stderr').write_bytes(perr)
    (identity.MODULE/NAME).write_text(HARNESS)
    (identity.MODULE/'fixtures/aave_weth_feed_execution.json').write_bytes(identity.encoded(result))
    print(json.dumps({'proxy_bytes':result['contracts']['EACAggregatorProxy']['runtime_bytes'],'runtime_recompiled_match':True,'aggregator_synthetic':True}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--compiler',type=Path,required=True)
    p.add_argument('--proxy-compiler',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(); build(a.compiler,a.proxy_compiler,a.output)
