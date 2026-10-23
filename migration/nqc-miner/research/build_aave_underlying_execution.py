#!/usr/bin/env python3
"""Execute original collateral burn with complete observed WETH runtime."""
import argparse
import copy
import gzip
import json
from pathlib import Path
import subprocess
import tempfile
import build_aave_transfer_execution as transfer
import capture_aave_underlying as capture
identity=transfer.identity
DIRECTORY=capture.DIRECTORY
NAME='fixtures/AaveUnderlyingExecutionHarness.sol'
CONTRACT='AaveUnderlyingExecutionHarness'
VERSION='0.4.19+commit.c4cbbb05'
WETH_COMPILER_SHA='07f89753cdda28054bb6f159a21911716caeb43b3c7659a25f1f2d9dd17bc827'
SIGNATURE=transfer.SIGNATURE[:-2]+',uint128,uint256,uint256,uint256,uint128))'


def weth_input():
    raw=gzip.decompress((DIRECTORY/'weth-source.json.gz').read_bytes());retrieval=identity.read_json(DIRECTORY/'retrieval.json')
    identity.check(identity.sha(raw)==retrieval['sha256'] and retrieval['url']=='https://sourcify.dev/server/v2/contract/1/'+capture.WETH+'?fields=all','WETH retrieval')
    source=json.loads(raw);identity.check(source['chainId']=='1' and source['address'].lower()==capture.WETH and source['compilation']['compilerVersion']==VERSION and source['compilation']['fullyQualifiedName']=='WETH9.sol:WETH9','WETH source identity')
    index=identity.read_json(identity.EVIDENCE/'compiler-list.json.gz');entry=next(b for b in index['builds'] if b['longVersion']==VERSION);identity.check(entry['sha256']=='0x'+WETH_COMPILER_SHA,'compiler identity')
    value=copy.deepcopy(source['stdJsonInput']);identity.check(value['sources']==source['sources'] and value['settings']==source['compilation']['compilerSettings'],'WETH sources/settings')
    identity.check(value['settings']=={'libraries':{},'optimizer':{'runs':200,'enabled':False},'remappings':[]},'WETH original settings')
    value['settings']['outputSelection']={'*':{'*':['abi','evm.deployedBytecode','evm.methodIdentifiers'],'':['ast']}}
    return source,value


def compile_weth(compiler,value):
    identity.check(identity.sha(compiler.read_bytes())==WETH_COMPILER_SHA,'WETH compiler checksum')
    version=subprocess.run([str(compiler),'--version'],capture_output=True,check=True).stdout.decode();identity.check(VERSION in version,'WETH compiler version')
    with tempfile.TemporaryDirectory(prefix='nqc-weth-') as cwd:
        result=subprocess.run([str(compiler),'--standard-json'],input=identity.encoded(value),cwd=cwd,capture_output=True,timeout=60)
    identity.check(result.returncode==0,'WETH compiler exit')
    output=json.loads(result.stdout);identity.check(not any(e.get('severity')=='error' for e in output.get('errors',[])),str(output.get('errors',[])))
    return result.stdout,result.stderr


def audit_weth(source,output,history):
    ast=output['sources']['WETH9.sol']['ast']
    contracts=[n for n in ast['nodes'] if n.get('nodeType')=='ContractDefinition']
    identity.check(len(contracts)==1 and contracts[0]['name']=='WETH9' and contracts[0]['baseContracts']==[],'WETH AST inheritance')
    declarations=[n for n in contracts[0]['nodes'] if n.get('nodeType')=='VariableDeclaration' and n.get('stateVariable')]
    identity.check([(n['name'],n['typeDescriptions']['typeString'],n['constant']) for n in declarations]==[('name','string storage ref',False),('symbol','string storage ref',False),('decimals','uint8',False),('balanceOf','mapping(address => uint256)',False),('allowance','mapping(address => mapping(address => uint256))',False)],'WETH declaration order/types')
    c=output['contracts']['WETH9.sol']['WETH9'];code=c['evm']['deployedBytecode'];compiled=bytes.fromhex(code['object']);observed=bytes.fromhex(source['runtimeBytecode']['onchainBytecode'][2:])
    identity.check(not code['linkReferences'],'WETH links')
    # Preserve the mismatch; never replace compiler metadata with deployment data.
    # The old Solidity CBOR footer is exactly a bzzr0 bytes32 map plus length 0x29.
    prefix=bytes.fromhex('a165627a7a72305820')
    for data in [compiled,observed]:identity.check(len(data)==3124 and data[-43:-34]==prefix and data[-2:]==b'\x00\x29','WETH CBOR format/length')
    identity.check(compiled[:-43]==observed[:-43],'WETH executable mismatch')
    identity.check(compiled[-34:-2]!=observed[-34:-2],'retained metadata mismatch expected')
    identity.check('0x'+compiled.hex()==source['runtimeBytecode']['recompiledBytecode'],'independent compiler result')
    identity.check(len(history)==3,'historical coverage')
    for h,plan in zip(history,capture.prior.plans()):
        identity.check(h['block']==plan['block'] and h['event_anchor']==plan['event_anchor'] and h['asset']==capture.WETH and h['a_token']==capture.ATOKEN,'historical binding')
        identity.check(h['runtime_code']=='0x'+observed.hex() and h['runtime_sha256']==identity.sha(observed) and h['runtime_bytes']==3124,'historical full runtime')
        identity.check(capture.probe.implementation(h['underlying_slot_word'])==capture.WETH,'underlying asset')
        pin={'blockHash':h['block']['hash'],'requireCanonical':True}
        for provider in capture.PROVIDERS:
            codes=[r for r in h['records'] if r['provider_id']==provider and r['request']['method']=='eth_getCode'];slots=[r for r in h['records'] if r['provider_id']==provider and r['request']['method']=='eth_getStorageAt']
            identity.check(len(codes)==len(slots)==1 and codes[0]['request']['params']==[capture.WETH,pin] and codes[0]['response']['result']==h['runtime_code'],'provider code/pin')
            identity.check(slots[0]['request']['params']==[capture.ATOKEN,'0x3d',pin] and slots[0]['response']['result']==h['underlying_slot_word'],'provider underlying slot/pin')
    return {'runtime_code':'0x'+observed.hex(),'runtime_sha256':identity.sha(observed),'compiled_runtime_sha256':identity.sha(compiled),'executable_prefix_bytes':3081,'executable_prefix_sha256':identity.sha(compiled[:-43]),'compiler_metadata_bzzr0':'0x'+compiled[-34:-2].hex(),'deployed_metadata_bzzr0':'0x'+observed[-34:-2].hex(),'full_runtime_recompiled':False,'executable_prefix_equal':True,'metadata_hash_equal':False,'runtime_from_complete_historical_capture':True,'selectors':c['evm']['methodIdentifiers'],'storage_layout_kind':'original_declaration_order_and_executed_getters_not_compiler_storageLayout','balance_mapping_slot':3,'allowance_mapping_slot':4,'historical_state_authenticated':False}


def harness_input():
    source=identity.read_json(identity.EVIDENCE/'source.json.gz');identity.verify_provenance(source)
    harness,segments=transfer.extracted_harness(source)
    original=source['sources'][transfer.SOURCE_PATH]['content'];a=original.index('  struct LiquidationCallLocalVars {');structure=original[a:original.index('\n\n  /**',a)]
    def replace(old,new):
        nonlocal harness
        identity.check(harness.count(old)==1,'unique synthetic wrapper edit: '+old[:50]);harness=harness.replace(old,new)
    replace('contract AaveTransferExecutionHarness {','contract '+CONTRACT+' {')
    replace(structure,'')
    replace('    LiquidationCallLocalVars memory vars;','    LiquidationLogic.LiquidationCallLocalVars memory vars;')
    replace('    uint256 price; uint256 unit; uint256 totalBase; uint16 collateralId;','    uint256 price; uint256 unit; uint256 totalBase; uint16 collateralId;\n    uint128 collateralVirtual; uint256 collateralScaledDebt; uint256 collateralBorrowIndex;\n    uint256 collateralFactor; uint128 collateralDeficit;')
    replace('    collateralReserve.id = input.collateralId;','''    collateralReserve.id = input.collateralId;
    collateralReserve.deficit = input.collateralDeficit;
    collateralReserve.virtualUnderlyingBalance = input.collateralVirtual;
    vars.collateralReserveCache.nextScaledVariableDebt = input.collateralScaledDebt;
    vars.collateralReserveCache.nextVariableBorrowIndex = input.collateralBorrowIndex;
    vars.collateralReserveCache.reserveFactor = input.collateralFactor;''')
    a=harness.index('    // Only the original receiveAToken=true branch');b=harness.index('    // Transfer fee to treasury',a)
    harness=harness[:a]+'''    // Original full collateral helper: rate update, aToken burn and actual WETH transfer.
    LiquidationLogic._burnCollateralATokens(collateralReserve, params, vars);
'''+harness[b:]
    replace('returns (uint256[19] memory result)','returns (uint256[24] memory result)')
    replace('      hasNoCollateralLeft ? 1 : 0];','''      hasNoCollateralLeft ? 1 : 0, uint256(collateralReserve.virtualUnderlyingBalance),
      uint256(collateralReserve.currentLiquidityRate), uint256(collateralReserve.currentVariableBorrowRate),
      UnderlyingView(params.collateralAsset).balanceOf(input.aToken),
      UnderlyingView(params.collateralAsset).balanceOf(params.liquidator)];''')
    replace('contract '+CONTRACT+' {','interface UnderlyingView { function balanceOf(address) external view returns (uint256); }\ncontract '+CONTRACT+' {')
    a=original.index('  function _burnCollateralATokens(');burn=original[a:original.index('\n  /**',a)]
    segments.pop('receive_atoken_transfer');segments['unchanged_internal_collateral_burn']=identity.sha(burn.encode())
    value=identity.compilation_input(source);value['sources'][NAME]={'content':harness};value['settings']['outputSelection']={NAME:{CONTRACT:['evm.deployedBytecode','evm.methodIdentifiers','storageLayout']}}
    return value,harness,segments


def fixture(value,raw,weth_raw):
    expected,harness,segments=harness_input();identity.check(value==expected,'harness compiler input identity');out=json.loads(raw)
    identity.check(not any(e.get('severity')=='error' for e in out.get('errors',[])),str(out.get('errors',[])))
    c=out['contracts'][NAME][CONTRACT];code=c['evm']['deployedBytecode'];identity.check(not code['linkReferences'] and not code['immutableReferences'],'harness deployment references')
    source,wi=weth_input();identity.check(wi==identity.read_json(DIRECTORY/'compiler/weth-input.json.gz'),'WETH input bytes')
    wc=audit_weth(source,json.loads(weth_raw),capture.replay())
    prior=identity.read_json(transfer.DIRECTORY/'compiler/input.json.gz');prior_raw=gzip.decompress((transfer.DIRECTORY/'compiler/output.json.gz').read_bytes());result=transfer.fixture(prior,prior_raw)
    result['contracts'].pop(transfer.CONTRACT);result['contracts'][CONTRACT]={'runtime_code':'0x'+code['object'],'runtime_sha256':identity.sha(bytes.fromhex(code['object'])),'storage_layout':c['storageLayout'],'selectors':c['evm']['methodIdentifiers']};result['contracts']['WETH9']=wc
    result.update(schema='nqc-miner-aave-underlying-execution-fixture-v1',compiler_input_sha256=identity.sha(identity.encoded(value)),compiler_output_sha256=identity.sha(raw),harness_source_sha256=identity.sha(harness.encode()),extracted_segments=segments,previous_transfer_fixture_sha256=identity.sha((identity.MODULE/'fixtures/aave_transfer_execution.json').read_bytes()),weth_compiler_sha256=WETH_COMPILER_SHA,weth_compiler_output_sha256=identity.sha(weth_raw),underlying_transfer_executed=True,receive_atoken_only=False,receive_underlying_only=True,weth_full_source_runtime_match=False,historical_state_authenticated=False)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler-directory',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    _,wi=weth_input();wr,we=compile_weth(a.compiler_directory/'solc-0.4.19',wi)
    for name,data in [('weth-input.json.gz',identity.encoded(wi)),('weth-output.json.gz',wr)]: (a.output/name).write_bytes(gzip.compress(data,mtime=0))
    (a.output/'weth.stderr').write_bytes(we)
    value,harness,_=harness_input();raw,err=identity.compile_source(a.compiler_directory/'solc-0.8.27',value)
    for name,data in [('harness-input.json.gz',identity.encoded(value)),('harness-output.json.gz',raw)]: (a.output/name).write_bytes(gzip.compress(data,mtime=0))
    (a.output/'harness.stderr').write_bytes(err)
    result=fixture(value,raw,wr);(identity.MODULE/NAME).write_text(harness);(identity.MODULE/'fixtures/aave_underlying_execution.json').write_bytes(identity.encoded(result))
    print(json.dumps({'harness_bytes':(len(result['contracts'][CONTRACT]['runtime_code'])-2)//2,'WETH_bytes':3124,'WETH_full_source_runtime_match':False,'WETH_instruction_prefix_equal':True}))


if __name__=='__main__':main()
