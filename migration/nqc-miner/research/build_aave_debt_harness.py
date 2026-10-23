#!/usr/bin/env python3
"""Compile a synthetic caller of original _burnDebtTokens with supplied token and strategy outcomes."""
import argparse
import gzip
import json
from pathlib import Path
import aave_runtime_identity as identity

NAME='fixtures/AaveDebtHarness.sol'
SIGNATURE='calculate((uint256,uint256,bool,uint256,uint256,bool,uint256,uint128,uint128,uint16,uint256,uint256,uint256,uint256,bool,bytes,bool,bytes),bool)'


def build(compiler,output):
    source=identity.read_json(identity.EVIDENCE/'source.json.gz')
    identity.verify_provenance(source)
    value=identity.compilation_input(source)
    harness=(identity.MODULE/NAME).read_text()
    value['sources'][NAME]={'content':harness}
    value['settings']['outputSelection']={NAME:{'AaveDebtHarness':['evm.deployedBytecode','evm.methodIdentifiers','storageLayout']}}
    raw,stderr=identity.compile_source(compiler,value)
    result=json.loads(raw)
    errors=[e for e in result.get('errors',[]) if e.get('severity')=='error']
    identity.check(not errors,str(errors))
    contract=result['contracts'][NAME]['AaveDebtHarness']
    code=contract['evm']['deployedBytecode']
    identity.check(not code['linkReferences'] and not code['immutableReferences'],'deployment references')
    layout=contract['storageLayout']
    slots=set()
    dynamic_slots=[]
    for var in layout['storage']:
        start=int(var['slot']); size=int(layout['types'][var['type']]['numberOfBytes'])
        if layout['types'][var['type']]['encoding']=='bytes': dynamic_slots.append(start)
        slots.update(range(start,start+(size+31)//32))
    runtime=bytes.fromhex(code['object'])
    fixture={'schema':'nqc-miner-aave-debt-harness-v1','kind':'synthetic_fixture',
      'compiler_sha256':identity.COMPILER_SHA,'compiler_version':identity.COMPILER_VERSION,
      'compiler_input_sha256':identity.sha(identity.encoded(value)),'compiler_output_sha256':identity.sha(raw),
      'harness_source_sha256':identity.sha(harness.encode()),'runtime_sha256':identity.sha(runtime),
      'runtime_code':'0x'+runtime.hex(),'selector':'0x'+contract['evm']['methodIdentifiers'][SIGNATURE],
      'storage_layout':layout,'explicit_zero_slots':sorted(slots),
      'dynamic_bytes_slots':dynamic_slots,'dynamic_bytes_zero_words_per_root':128,
      'original_sources':{p:identity.sha(v['content'].encode()) for p,v in source['sources'].items()},
      'reference_runtime_audit':'evidence/aave-compiled-identity-20261023/local/audit.json',
      'reference_function':'LiquidationLogic._burnDebtTokens',
      'external_outcomes_supplied':True,'token_implementation_verified':False,'rate_strategy_verified':False,'executable_eligibility_verified':False,'activation_allowed':False}
    output.mkdir(parents=True,exist_ok=False)
    (output/'input.json.gz').write_bytes(gzip.compress(identity.encoded(value),mtime=0))
    (output/'output.json.gz').write_bytes(gzip.compress(raw,mtime=0))
    (output/'compiler.stderr').write_bytes(stderr)
    (identity.MODULE/'fixtures/aave_debt_harness.json').write_bytes(identity.encoded(fixture))
    print(json.dumps({'runtime_bytes':len(runtime),'runtime_sha256':fixture['runtime_sha256'],'slots':sorted(slots)}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();build(a.compiler,a.output)
