#!/usr/bin/env python3
"""Build a synthetic Pool/proxy/rewards wrapper around two audited real runtimes."""
import argparse
import gzip
import json
from pathlib import Path
import aave_runtime_identity as identity
import audit_aave_dependencies as dependencies
import capture_aave_dependencies as capture

NAME = 'fixtures/AaveDebtExecutionHarness.sol'
SIGNATURE = 'calculate((uint256,uint256,bool,uint256,uint256,uint128,uint128,uint16,uint256,uint256))'
TOKEN = '0xb27c52c7f84819e3157993489741cb60786ae330'
STRATEGY = capture.STRATEGY


def build(compiler, output):
    source = identity.read_json(identity.EVIDENCE/'source.json.gz')
    identity.verify_provenance(source)
    value = identity.compilation_input(source)
    harness = (identity.MODULE/NAME).read_text()
    value['sources'][NAME] = {'content':harness}
    value['settings']['outputSelection'] = {NAME:{'*':['evm.deployedBytecode','evm.methodIdentifiers','storageLayout']}}
    raw, stderr = identity.compile_source(compiler, value)
    result = json.loads(raw)
    identity.check(not any(e.get('severity')=='error' for e in result.get('errors',[])),str(result.get('errors',[])))
    profiles, _, outputs = dependencies.retained_inputs()
    dependencies.audit(capture.replay(), profiles, outputs)
    contracts = {}
    for name in ['AaveDebtExecutionHarness','SyntheticDebtProxy','RewardsProbe']:
        c = result['contracts'][NAME][name]; b = c['evm']['deployedBytecode']
        identity.check(not b['linkReferences'] and not b['immutableReferences'], 'unexpected wrapper references')
        contracts[name] = {'runtime_code':'0x'+b['object'],'runtime_sha256':identity.sha(bytes.fromhex(b['object'])), 'storage_layout':c['storageLayout'], 'selectors':c['evm']['methodIdentifiers']}
    for name, address in [('VariableDebtTokenInstance',TOKEN),('DefaultReserveInterestRateStrategyV2',STRATEGY)]:
        p = next(p for p in profiles if p['address']==address)
        runtime, substitutions = dependencies.render_runtime(outputs[address],p)
        path, contract = p['target'].rsplit(':',1)
        contracts[name] = {'runtime_code':runtime,'runtime_sha256':identity.sha(bytes.fromhex(runtime[2:])), 'storage_layout':outputs[address]['contracts'][path][contract]['storageLayout'],'implementation_address':address,'compiler_output_sha256':p['compiler_output_sha256'],'substitutions':substitutions}
    fixture = {'schema':'nqc-miner-aave-debt-execution-fixture-v1','kind':'synthetic_fixture','compiler_input_sha256':identity.sha(identity.encoded(value)),'compiler_output_sha256':identity.sha(raw),'compiler_sha256':identity.COMPILER_SHA,'harness_source_sha256':identity.sha(harness.encode()),'contracts':contracts,'token_burn_outcome_supplied':False,'rate_quote_supplied':False,'rewards_controller_synthetic':True,'proxy_synthetic':True,'pool_entrypoint_synthetic':True,'historical_state_authenticated':False,'executable_eligibility_verified':False,'activation_allowed':False}
    output.mkdir(parents=True,exist_ok=False)
    for name, data in [('input.json.gz',identity.encoded(value)),('output.json.gz',raw)]:
        (output/name).write_bytes(gzip.compress(data,mtime=0))
    (output/'compiler.stderr').write_bytes(stderr)
    (identity.MODULE/'fixtures/aave_debt_execution.json').write_bytes(identity.encoded(fixture))
    print(json.dumps({k:len(v['runtime_code'])//2-1 for k,v in contracts.items()}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();build(args.compiler,args.output)
