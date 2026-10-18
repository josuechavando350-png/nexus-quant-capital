"""Self-contained solc input and ABI check. Never installs tools or submits transactions."""
from __future__ import annotations
import argparse, hashlib, json, shutil, subprocess
from pathlib import Path
from abi_migration import SIG_OLD, SIG_NEW, selector, validate_compiler_abi
ROOT=Path(__file__).resolve().parent
ORIGINAL='NqcMorphoSponsoredLiquidation.sol'
PROPOSAL='NqcMorphoSponsoredLiquidationPaymentLayout.sol'
LOCK={ORIGINAL:'b305c52d06538a20dd4cef1769475d5e47059711122130363508b3ad6e33c9a1',
      PROPOSAL:'221a93b5b075c4daad50bf02bd7c2fb13339f13f8e6dd9e29a6261823078045a'}

def write_json(path,obj):
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n',encoding='utf8')

def prepare(out: Path, solc: str|None=None, expected_sha256: str|None=None)->dict:
    out=out.resolve();out.mkdir(parents=True,exist_ok=False)
    source={}
    for name,h in LOCK.items():
        data=(ROOT/'source'/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=h: raise ValueError('changed pinned source: '+name)
        source[name]={'content':data.decode('utf8')}
    inp={'language':'Solidity','sources':source,'settings':{'optimizer':{'enabled':True,'runs':200},
         'viaIR':False,'evmVersion':'cancun',
         'outputSelection':{'*':{'*':['abi','evm.bytecode.object','evm.deployedBytecode.object','evm.methodIdentifiers']}}}}
    write_json(out/'standard_input.json',inp)
    status={'source_sha256':LOCK,'old_signature':SIG_OLD,'new_signature':SIG_NEW,
            'old_selector':'0x'+selector(SIG_OLD).hex(),'new_selector':'0x'+selector(SIG_NEW).hex(),
            'compiled':False,'evm_executed':False,'commercial_admission':False,'publication':'NOT_PUBLISHED'}
    resolved=solc or shutil.which('solc')
    if not resolved or not Path(resolved).is_file():
        status['status']='BLOCKED_MISSING_COMPILER';write_json(out/'status.json',status);return status
    executable=Path(resolved).resolve()
    h=hashlib.sha256(executable.read_bytes()).hexdigest()
    if not expected_sha256 or h!=expected_sha256: raise ValueError('compiler executable SHA must be explicitly pinned')
    version=subprocess.run([str(executable),'--version'],capture_output=True,text=True,timeout=10,check=True)
    (out/'compiler_version.txt').write_text(version.stdout+version.stderr)
    if '0.8.24+commit.e11b9ed9' not in version.stdout: raise ValueError('requires solc 0.8.24+commit.e11b9ed9')
    result=subprocess.run([str(executable),'--standard-json'],input=json.dumps(inp),capture_output=True,text=True,timeout=45)
    (out/'compiler_stdout.json').write_text(result.stdout);(out/'compiler_stderr.txt').write_text(result.stderr)
    status.update(compiler_sha256=h,compiler_exit_code=result.returncode)
    if result.returncode: status['status']='COMPILATION_FAILED'
    else:
        output=json.loads(result.stdout)
        errors=[e for e in output.get('errors',[]) if e['severity']=='error']
        if errors:
            status.update(status='COMPILATION_FAILED',errors=errors)
        else:
            contracts={}
            for file,name,new in [(ORIGINAL,ORIGINAL[:-4],False),(PROPOSAL,PROPOSAL[:-4],True)]:
                c=output['contracts'][file][name]
                validate_compiler_abi(c['abi'],c['evm']['methodIdentifiers'],new=new)
                bytecode=c['evm']['bytecode']['object']
                if not bytecode or '__' in bytecode: raise ValueError('missing/unlinked creation bytecode')
                contracts[name]={'abi':c['abi'],'bytecode':'0x'+bytecode,
                  'method_identifiers':c['evm']['methodIdentifiers'],
                  'creation_sha256':hashlib.sha256(bytes.fromhex(bytecode)).hexdigest(),
                  'runtime_size':len(c['evm']['deployedBytecode']['object'])//2}
            write_json(out/'compiled_contracts.json',contracts)
            status.update(status='COMPILE_AND_ABI_PASS_ONLY',compiled=True)
    write_json(out/'status.json',status)
    return status

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--solc');p.add_argument('--solc-sha256')
    a=p.parse_args();r=prepare(a.out,a.solc,a.solc_sha256);print(json.dumps(r,ensure_ascii=False,indent=2))
    raise SystemExit(0 if r['compiled'] else 2)
