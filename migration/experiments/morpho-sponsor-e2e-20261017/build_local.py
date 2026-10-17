"""Compile pinned original sources and local helpers, writing only the new experiment."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'morpho-sponsored-gas'
PINS={'morpho-blue':'9cf6d5b844625ba108e36d1cf911f5d2faf7c136',
      'nqc-uniswap-v2':'6a9e7c97860676e0992f22a49665760444c1cdf5',
      'bundler3/lib/permit2/lib/solmate':'8d910d876f51c3b2585c9109409d601f600e68e1'}
COMPILERS={'0.8.19':'7a5c1d3dc9a8eba62bb2ec37192c9178ae5fe8a54a56e5573fd3c9c17cd9eb48',
           '0.8.24':'fb03a29a517452b9f12bcf459ef37d0a543765bb3bbc911e70a87d6a37c30d5f',
           '0.5.16':'a15f01700ec7e02f91bbdfd4b6ff4450b3c2decae173e4f41910a3cfbaf5d3d3'}

def sha(raw): return hashlib.sha256(raw).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',type=Path,required=True)
    p.add_argument('--toolchain',type=Path,required=True)
    a=p.parse_args(); artifacts={}; provenance={}; compilers={}
    def original(repo,prefix):
        root=a.workspace/repo; pin=PINS[repo]
        entries=subprocess.check_output(['git','-C',str(root),'ls-tree','-r',pin,prefix],text=True)
        sources={}; manifest=[]
        for line in entries.splitlines():
            meta,name=line.split('\t'); mode,kind,blob=meta.split()
            if not name.endswith('.sol'): continue
            if '/test/' in name and not (repo=='nqc-uniswap-v2' and name=='contracts/test/ERC20.sol'): continue
            if mode!='100644' or kind!='blob': raise ValueError('source type')
            data=subprocess.check_output(['git','-C',str(root),'cat-file','blob',blob])
            if hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()!=blob: raise ValueError('blob')
            sources[name]={'content':data.decode()}
            manifest.append({'path':name,'git_blob':blob,'sha256':sha(data)})
        provenance[repo]={'commit':pin,'sources':manifest}
        return sources
    def compile_(version,sources,targets,evm,runs):
        binary=a.toolchain/f'solc-{version}'; digest=sha(binary.read_bytes())
        if version in COMPILERS and digest!=COMPILERS[version]: raise ValueError('compiler digest')
        compilers[version]={'sha256':digest,'version':subprocess.check_output([str(binary),'--version'],text=True).strip()}
        std={'language':'Solidity','sources':sources,'settings':{'optimizer':{'enabled':True,'runs':runs},
             'evmVersion':evm,'outputSelection':{f:{n:['abi','evm.bytecode.object','evm.deployedBytecode.object'] for n in nn} for f,nn in targets.items()}}}
        result=json.loads(subprocess.run([str(binary),'--standard-json'],input=json.dumps(std),text=True,capture_output=True,check=True).stdout)
        errors=[e for e in result.get('errors',[]) if e['severity']=='error']
        if errors: raise ValueError(errors)
        for f, nn in targets.items():
            for n in nn:
                c=result['contracts'][f][n]
                artifacts[n]={'abi':c['abi'],'bytecode':'0x'+c['evm']['bytecode']['object'],
                    'runtime_template':'0x'+c['evm']['deployedBytecode']['object']}
    compile_('0.8.19',original('morpho-blue','src'),{'src/Morpho.sol':['Morpho']},'paris',999999)
    compile_('0.5.16',original('nqc-uniswap-v2','contracts'),{
        'contracts/UniswapV2Pair.sol':['UniswapV2Pair'],'contracts/test/ERC20.sol':['ERC20']},'istanbul',999999)
    src=original('bundler3/lib/permit2/lib/solmate','src')
    # Only the transitive WETH imports are necessary; other Solmate files may use different compiler features.
    src={k:v for k,v in src.items() if k in ('src/tokens/WETH.sol','src/tokens/ERC20.sol','src/utils/SafeTransferLib.sol')}
    local=HERE/'LabSupport.sol'; executor=BASE/'contracts/NqcMorphoSponsoredLiquidation.sol'
    src['LabSupport.sol']={'content':local.read_text()}
    src['NqcMorphoSponsoredLiquidation.sol']={'content':executor.read_text()}
    provenance['local']={str(f.relative_to(HERE.parent)):sha(f.read_bytes()) for f in (local,executor)}
    compile_('0.8.24',src,{'src/tokens/WETH.sol':['WETH'],'LabSupport.sol':['LabOracle','LabFactory','LabV2Adapter','RejectNative','ForceNative','UnderpayControl'],
        'NqcMorphoSponsoredLiquidation.sol':['NqcMorphoSponsoredLiquidation']},'cancun',200)
    out=HERE/'build';out.mkdir(exist_ok=True)
    (out/'artifacts.json').write_text(json.dumps(artifacts)+'\n')
    report={'classification':'ORIGINAL_SOURCE_LOCAL_BUILD_NOT_DEPLOYED_MAINNET_PARITY','sources':provenance,'compilers':compilers,
        'bytecode_sha256':{n:sha(bytes.fromhex(c['bytecode'][2:])) for n,c in artifacts.items()}}
    (HERE/'evidence/build-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'contracts':list(artifacts),'classification':report['classification']}))

if __name__=='__main__': main()
