#!/usr/bin/env python3
"""Recompile official v0.7 runtime; compare every byte to the archived RPC result."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess

ADDRESS = '0x0000000071727de22e5e9d8baf0edac6f37da032'
EXPECTED_CODE_SHA = '674d73ee2acf6d72a5b32b6e05150b9ddcfcee0429a0e7914929faccbc2bf4d5'
SOLC_SHA = '28726a452290c70e1984f15c53ad3088e7d98783ee3070b11b3664da77415732'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dependencies', type=Path, required=True)
    ap.add_argument('--rpc-evidence', type=Path, required=True)
    ap.add_argument('--solc', type=Path, required=True)
    ap.add_argument('--cast', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    if hashlib.sha256(args.solc.read_bytes()).hexdigest() != SOLC_SHA:
        raise ValueError('unexpected compiler bytes')
    pins = {'account-abstraction':'7af70c8993a6f42973f520ae0752386a5032abe7', 'openzeppelin-contracts':'dbb6104ce834628e473d2173bbc9d47f81a9eec3'}
    for name, pin in pins.items():
        path = args.dependencies / name
        if subprocess.check_output(['git','rev-parse','HEAD'],cwd=path,text=True).strip() != pin:
            raise ValueError('dependency revision mismatch')
        if subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=path,text=True).strip():
            raise ValueError('dependency worktree changed')
    sources = {}
    def collect(name):
        if name in sources:
            return
        path = args.dependencies / ('openzeppelin-contracts/contracts/' + name[len('@openzeppelin/contracts/'):] if name.startswith('@openzeppelin/contracts/') else 'account-abstraction/' + name)
        text = path.read_text()
        sources[name] = {'content':text}
        for imp in re.findall(r'import[^;]*?[\"\']([^\"\']+)[\"\']\s*;', text):
            collect(posixpath.normpath(str(PurePosixPath(name).parent / imp)) if imp.startswith('.') else imp)
    collect('contracts/core/EntryPoint.sol')
    inp = {'language':'Solidity','sources':sources,'settings':{
        'evmVersion':'paris', 'optimizer':{'enabled':True,'runs':1000000},
        'viaIR':True,'metadata':{'bytecodeHash':'ipfs'},
        'outputSelection':{'*':{'*':['evm.deployedBytecode','evm.bytecode','metadata','abi']}}}}
    out = args.out
    out.mkdir(parents=True,exist_ok=True)
    (out/'compiler-input.json').write_text(json.dumps(inp,sort_keys=True))
    with (out/'compiler-input.json').open() as f:
        proc = subprocess.run([str(args.solc),'--standard-json'],stdin=f,capture_output=True,text=True,check=True)
    result = json.loads(proc.stdout)
    errors = [e for e in result.get('errors',[]) if e['severity']=='error']
    if errors:
        raise ValueError(errors)
    ep = result['contracts']['contracts/core/EntryPoint.sol']['EntryPoint']
    runtime = bytearray.fromhex(ep['evm']['deployedBytecode']['object'])
    # CREATE nonce 1 in EntryPoint's constructor. Only the compiler-declared immutable
    # locations are filled, using the independently derived canonical child address.
    creator = subprocess.check_output([str(args.cast),'compute-address',ADDRESS,'--nonce','1','--json'],text=True)
    creator_address = re.search(r'0x[0-9a-fA-F]{40}', creator).group(0)
    refs = ep['evm']['deployedBytecode']['immutableReferences']
    assert len(refs)==1
    locations = next(iter(refs.values()))
    for loc in locations:
        assert loc['length']==32
        runtime[loc['start']:loc['start']+32] = bytes.fromhex(creator_address[2:]).rjust(32,b'\0')
    rows = json.loads(args.rpc_evidence.read_text())
    row = next(x for x in rows if x['request']['method']=='eth_getCode' and x['request']['params'][0].lower()==ADDRESS)
    observed = bytes.fromhex(row['result'][2:])
    assert hashlib.sha256(observed).hexdigest()==EXPECTED_CODE_SHA
    assert next(x for x in rows if x['request']['method']=='eth_chainId')['result']=='0x1237'
    header = next(x for x in rows if x['request']['method']=='eth_getBlockByNumber')['result']
    assert row['request']['params'][1]==header['number']
    report = {'scope':'HISTORICAL_SINGLE_RPC_RUNTIME_REBUILD_WITH_EXPLORER_SOURCE_CHECK',
        'chain_id':4663,'address':ADDRESS,'block':int(header['number'],16),'block_hash':header['hash'],
        'official_commits':pins,'compiler_sha256':SOLC_SHA,'source_file_count':len(sources),
        'source_sha256':{k:hashlib.sha256(v['content'].encode()).hexdigest() for k,v in sources.items()},
        'compiled_bytes':len(runtime),'observed_bytes':len(observed),
        'compiled_sha256':hashlib.sha256(runtime).hexdigest(),'observed_sha256':EXPECTED_CODE_SHA,
        'full_byte_equality_including_metadata':bytes(runtime)==observed,
        'sender_creator':creator_address,'immutable_locations':locations,
        'fresh_rpc_read':False,'external_bundler_admission':False,'live_useroperation':False}
    (out/'runtime.hex').write_text('0x'+observed.hex()+'\n')
    (out/'runtime.json').write_text(json.dumps({'runtime':'0x'+observed.hex()})+'\n')
    (out/'EntryPoint.compiled.json').write_text(json.dumps(ep,sort_keys=True))
    (out/'comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='source_sha256'},indent=2))
    if bytes(runtime)!=observed:
        raise SystemExit('FULL BYTECODE IDENTITY NOT PROVEN')

if __name__=='__main__':
    main()
