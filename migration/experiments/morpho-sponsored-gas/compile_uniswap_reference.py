"""Build pinned Uniswap V2 pair for LOCAL tests; never a deployed-code certificate."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

COMMIT = '6a9e7c97860676e0992f22a49665760444c1cdf5'
SOLC_SHA256 = 'a15f01700ec7e02f91bbdfd4b6ff4450b3c2decae173e4f41910a3cfbaf5d3d3'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--solc',type=Path,required=True)
    args=p.parse_args(); compiler=args.solc.resolve()
    if hashlib.sha256(compiler.read_bytes()).hexdigest()!=SOLC_SHA256:
        raise ValueError('unverified solc 0.5.16 Linux binary')
    def git(*a):return subprocess.check_output(['git','-C',str(args.source),*a])
    sources={};manifest=[]
    for line in git('ls-tree','-r',COMMIT,'contracts').decode().splitlines():
        meta,name=line.split('\t');mode,kind,sha=meta.split()
        if not name.endswith('.sol') or '/test/' in name:continue
        if mode!='100644' or kind!='blob':raise ValueError('unsupported source')
        data=git('cat-file','blob',sha)
        if hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()!=sha:
            raise ValueError('source identity mismatch')
        sources[name]={'content':data.decode()}
        manifest.append({'path':name,'git_blob':sha,'sha256':hashlib.sha256(data).hexdigest()})
    std={'language':'Solidity','sources':sources,'settings':{
        'optimizer':{'enabled':True,'runs':999999},'evmVersion':'istanbul',
        'outputSelection':{'contracts/UniswapV2Pair.sol':{'UniswapV2Pair':['abi','evm.bytecode.object']}}}}
    output=json.loads(subprocess.run([str(compiler),'--standard-json'],input=json.dumps(std),text=True,capture_output=True,check=True).stdout)
    errors=[e for e in output.get('errors',[]) if e['severity']=='error']
    if errors:raise ValueError(errors)
    c=output['contracts']['contracts/UniswapV2Pair.sol']['UniswapV2Pair']
    folder=Path(__file__).parent/'out-upstream';folder.mkdir(exist_ok=True)
    (folder/'UniswapV2Pair.json').write_text(json.dumps({'abi':c['abi'],'bytecode':{'object':'0x'+c['evm']['bytecode']['object']}},indent=2)+'\n')
    proof={'source_commit':COMMIT,'repo':'https://github.com/Uniswap/v2-core','solc_sha256':SOLC_SHA256,
           'sources':manifest,'creation_bytecode_sha256':hashlib.sha256(bytes.fromhex(c['evm']['bytecode']['object'])).hexdigest(),
           'scope':'LOCAL_ORIGINAL_SOURCE_BUILD_SYNTHETIC_RESERVES_NOT_HISTORICAL_REPLAY'}
    (folder/'uniswap-manifest.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({'source_commit':COMMIT,'source_files':len(sources),'contract':'UniswapV2Pair'}))


if __name__=='__main__':main()
