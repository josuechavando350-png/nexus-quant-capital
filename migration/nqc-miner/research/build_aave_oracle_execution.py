#!/usr/bin/env python3
"""Compose byte-matched historical AaveOracle code with explicit synthetic feeds."""
import argparse
import copy
import gzip
import json
from pathlib import Path
import subprocess
import tempfile
import build_aave_account_execution as account
import capture_aave_oracle as capture

identity=account.identity
DIRECTORY=capture.DIRECTORY
NAME='fixtures/AaveOracleExecutionHarness.sol'
CONTRACT='AaveOracleExecutionHarness'
SIGNATURE=account.SIGNATURE
ORACLE_PATH='@aave/core-v3/contracts/misc/AaveOracle.sol'
VERSION='0.8.10+commit.fc410830'
CHECKSUM='c7effacf28b9d64495f81b75228fbf4266ac0ec87e8f1adc489ddd8a4dd06d89'


def oracle_input():
    raw=gzip.decompress((DIRECTORY/'source.json.gz').read_bytes()); retrieval=identity.read_json(DIRECTORY/'retrieval.json')
    identity.check(retrieval['url']=='https://sourcify.dev/server/v2/contract/1/'+capture.ORACLE+'?fields=all'
        and retrieval['sha256']==identity.sha(raw) and retrieval['bytes']==len(raw),'oracle source retrieval')
    s=json.loads(raw)
    identity.check(s['chainId']=='1' and s['address'].lower()==capture.ORACLE and
        s['compilation']['compilerVersion']==VERSION and s['compilation']['fullyQualifiedName']==ORACLE_PATH+':AaveOracle','oracle source identity')
    index=identity.read_json(identity.EVIDENCE/'compiler-list.json.gz')
    build=next(b for b in index['builds'] if b['longVersion']==VERSION)
    identity.check(build['sha256']=='0x'+CHECKSUM,'oracle compiler index')
    cr=identity.read_json(DIRECTORY/'compiler-retrieval.json')
    identity.check(cr['sha256']==CHECKSUM and cr['url']=='https://raw.githubusercontent.com/ethereum/solc-bin/gh-pages/linux-amd64/'+build['path'],'compiler retrieval')
    v=copy.deepcopy(s['stdJsonInput'])
    identity.check(v['sources']==s['sources'] and v['settings']==s['compilation']['compilerSettings'],'unchanged oracle sources/settings')
    identity.check(all(set(x)=={'content'} and isinstance(x['content'],str) for x in v['sources'].values()),'literal oracle sources')
    v['settings']['outputSelection']={'*':{'*':['evm.methodIdentifiers']},ORACLE_PATH:{'AaveOracle':['evm.deployedBytecode','evm.methodIdentifiers','storageLayout'],'':['ast']}}
    return s,v


def compile_oracle(compiler,value):
    identity.check(identity.sha(compiler.read_bytes())==CHECKSUM,'oracle compiler checksum')
    version=subprocess.run([str(compiler),'--version'],capture_output=True,check=True).stdout.decode()
    identity.check(VERSION in version,'oracle compiler version')
    # 0.8.10 lacks --no-import-callback. All seven literal dependency sources are supplied.
    with tempfile.TemporaryDirectory(prefix='nqc-oracle-solc-') as cwd:
        r=subprocess.run([str(compiler.resolve()),'--standard-json'],input=identity.encoded(value),cwd=cwd,capture_output=True,timeout=120,check=True)
    identity.check(len(r.stdout)<=16_000_000 and len(r.stderr)<=100_000,'oracle compiler output size')
    return r.stdout,r.stderr


def audit_oracle(value,raw,history):
    source,expected=oracle_input(); identity.check(value==expected,'oracle compilation input')
    out=json.loads(raw); identity.check(not any(e.get('severity')=='error' for e in out.get('errors',[])),'oracle compiler errors')
    c=out['contracts'][ORACLE_PATH]['AaveOracle']; bytecode=c['evm']['deployedBytecode']
    identity.check(not bytecode['linkReferences'],'oracle links')
    definitions=[n for n in out['sources'][ORACLE_PATH]['ast']['nodes'] if n.get('nodeType')=='ContractDefinition' and n['name']=='AaveOracle']
    identity.check(len(definitions)==1,'oracle AST')
    names={str(n['id']):n['name'] for n in definitions[0]['nodes'] if n.get('mutability')=='immutable'}
    identity.check(set(names.values())=={'ADDRESSES_PROVIDER','BASE_CURRENCY','BASE_CURRENCY_UNIT'} and len(names)==3,'oracle immutables')
    identity.check(len(history)==3 and [h['block']['number'] for h in history]==list(identity.BLOCKS),'oracle block coverage')
    words=history[0]['immutable_words']; runtime=bytearray.fromhex(bytecode['object']); edits=[]; touched=set()
    identity.check(set(bytecode['immutableReferences'])==set(names),'oracle declared immutable coverage')
    for key,refs in bytecode['immutableReferences'].items():
        for ref in refs:
            offset,length=ref['start'],ref['length']; positions=set(range(offset,offset+length))
            identity.check(length==32 and offset>=0 and offset+32<=len(runtime) and not positions&touched and runtime[offset:offset+32]==bytes(32),'oracle immutable bounds/placeholder')
            touched|=positions; runtime[offset:offset+32]=bytes.fromhex(words[names[key]][2:])
            edits.append({'offset':offset,'length':length,'name':names[key],'word':words[names[key]]})
    code='0x'+runtime.hex()
    identity.check(code==source['runtimeBytecode']['onchainBytecode'],'complete oracle source/runtime equality')
    for h in history:
        identity.check(h['oracle']==capture.ORACLE and h['immutable_words']==words and h['runtime_code']==code,'historical oracle runtime equality')
    selectors=c['evm']['methodIdentifiers']
    for kind,signature in [('provider','ADDRESSES_PROVIDER()'),('base','BASE_CURRENCY()'),('unit','BASE_CURRENCY_UNIT()'),('fallback','getFallbackOracle()'),('price','getAssetPrice(address)'),('source','getSourceOfAsset(address)')]:
        identity.check(selectors[signature]==capture.SELECTORS[kind],'oracle capture selector')
    base='@aave/core-v3/contracts/'
    identity.check(out['contracts'][base+'interfaces/IPoolAddressesProvider.sol']['IPoolAddressesProvider']['evm']['methodIdentifiers']['getPriceOracle()']==capture.SELECTORS['provider_oracle'],'provider selector')
    identity.check(out['contracts'][base+'dependencies/chainlink/AggregatorInterface.sol']['AggregatorInterface']['evm']['methodIdentifiers']['latestAnswer()']==capture.SELECTORS['answer'],'feed selector')
    return {'runtime_code':code,'runtime_sha256':identity.sha(runtime),'runtime_bytes':len(runtime),
        'selectors':selectors,'storage_layout':c['storageLayout'],'immutable_substitutions':edits,
        'source_files':{p:identity.sha(v['content'].encode()) for p,v in source['sources'].items()},
        'compiler_version':VERSION,'compiler_sha256':CHECKSUM,'full_runtime_recompiled_match':True,
        'metadata_bytes_compared':True,'canonical_code_proof_verified':False}


def harness_input():
    value,harness,segments=account.harness_input()
    identity.check(harness.count(account.CONTRACT)==1,'account contract name')
    harness=harness.replace(account.CONTRACT,CONTRACT)
    old='    params.priceOracle = 0x5555555555555555555555555555555555555555;'
    identity.check(harness.count(old)==1,'oracle address edit')
    harness=harness.replace(old,'    params.priceOracle = 0x54586bE62E3c3580375aE3723C145253060Ca0C2;')
    marker='// Explicit test double: supplied prices, not the deployed Aave oracle or Chainlink.'
    identity.check(harness.count(marker)==1,'synthetic oracle boundary'); harness=harness[:harness.index(marker)]
    harness+='''// Explicit feed doubles. Their runtime and answer/freshness state are not authenticated.
contract SyntheticOracleFeed {
  int256 private answer;
  bool private blocked;
  function latestAnswer() external view returns (int256) {
    require(!blocked, "synthetic feed blocked");
    return answer;
  }
}
contract SyntheticFallbackOracle {
  mapping(address => uint256) private prices;
  bool private blocked;
  function getAssetPrice(address asset) external view returns (uint256) {
    require(!blocked, "synthetic fallback blocked");
    return prices[asset];
  }
}
'''
    value['sources'].pop(account.NAME); value['sources'][NAME]={'content':harness}
    value['settings']['outputSelection']={NAME:{name:['evm.deployedBytecode','evm.methodIdentifiers','storageLayout'] for name in [CONTRACT,'SyntheticOracleFeed','SyntheticFallbackOracle']}}
    return value,harness,segments


def fixture(value,raw,oracle_value,oracle_raw):
    expected,harness,segments=harness_input(); identity.check(value==expected,'oracle harness input')
    out=json.loads(raw); identity.check(not any(e.get('severity')=='error' for e in out.get('errors',[])),'harness compiler errors')
    history=capture.replay(); oracle=audit_oracle(oracle_value,oracle_raw,history)
    p=account.DIRECTORY/'compiler'
    result=account.fixture(identity.read_json(p/'input.json.gz'),gzip.decompress((p/'output.json.gz').read_bytes()))
    for name in [account.CONTRACT,account.ORACLE_CONTRACT]: result['contracts'].pop(name)
    for name in [CONTRACT,'SyntheticOracleFeed','SyntheticFallbackOracle']:
        c=out['contracts'][NAME][name]; code=c['evm']['deployedBytecode']
        identity.check(not code['linkReferences'] and not code['immutableReferences'],'harness deployment references')
        result['contracts'][name]={'runtime_code':'0x'+code['object'],'runtime_sha256':identity.sha(bytes.fromhex(code['object'])),
            'selectors':c['evm']['methodIdentifiers'],'storage_layout':c['storageLayout']}
    result['contracts']['AaveOracle']=oracle
    result.update(schema='nqc-miner-aave-oracle-execution-fixture-v1',compiler_input_sha256=identity.sha(identity.encoded(value)),
        compiler_output_sha256=identity.sha(raw),harness_source_sha256=identity.sha(harness.encode()),extracted_segments=segments,
        oracle_compiler_input_sha256=identity.sha(identity.encoded(oracle_value)),oracle_compiler_output_sha256=identity.sha(oracle_raw),
        previous_account_fixture_sha256=identity.sha((identity.MODULE/'fixtures/aave_account_execution.json').read_bytes()),
        oracle_address=capture.ORACLE,oracle_kind='observed_aave_oracle_runtime_with_synthetic_feeds',
        oracle_runtime_recompiled_match=True,oracle_runtime_authenticated=False,oracle_state_authenticated=False,
        oracle_routing_observed=True,feed_kind='synthetic_test_double',observed_feed_runtime_executed=False,
        feed_answers_supplied=True,price_freshness_verified=False,
        oracle_observations=[{'block':h['block'],'fallback_word':h['fallback_word'],
            'feeds':[{k:f[k] for k in ['asset','source','runtime_sha256','price_word','answer_word']} for f in h['feeds']]} for h in history])
    return result


def build(compiler,oracle_compiler,output):
    _,ov=oracle_input(); oraw,oerr=compile_oracle(oracle_compiler,ov)
    value,harness,_=harness_input(); raw,err=identity.compile_source(compiler,value)
    result=fixture(value,raw,ov,oraw); output.mkdir(parents=True,exist_ok=False)
    for name,data in [('input.json.gz',identity.encoded(value)),('output.json.gz',raw),('oracle-input.json.gz',identity.encoded(ov)),('oracle-output.json.gz',oraw)]:
        (output/name).write_bytes(gzip.compress(data,mtime=0))
    (output/'compiler.stderr').write_bytes(err); (output/'oracle-compiler.stderr').write_bytes(oerr)
    (identity.MODULE/NAME).write_text(harness); (identity.MODULE/'fixtures/aave_oracle_execution.json').write_bytes(identity.encoded(result))
    print(json.dumps({'harness_bytes':len(bytes.fromhex(result['contracts'][CONTRACT]['runtime_code'][2:])),
        'oracle_bytes':result['contracts']['AaveOracle']['runtime_bytes'],'oracle_runtime_recompiled_match':True,'feed_kind':'synthetic_test_double'}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--compiler',type=Path,required=True)
    p.add_argument('--oracle-compiler',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(); build(args.compiler,args.oracle_compiler,args.output)
