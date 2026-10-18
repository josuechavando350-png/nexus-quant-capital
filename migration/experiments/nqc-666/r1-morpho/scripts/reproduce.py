#!/usr/bin/env python3
"""Build, prove and measure offline. Preinstall Rust 1.90, pinned solc and py-evm tools; no network here."""
import argparse,array,hashlib,json,math,os,pathlib,platform,random,subprocess,sys,tarfile,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(cmd,out,env):
    with out.open('w') as f:subprocess.run(list(map(str,cmd)),cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
def stats(v):
    v=sorted(v);n=len(v)
    return {'n':n,**{k:v[math.ceil(n*q)-1] for k,q in [('p50',.5),('p95',.95),('p99',.99),('p99_9',.999)]},'max':v[-1],'min':v[0]}
def read(p):
    v=array.array('Q');v.frombytes(p.read_bytes())
    if sys.byteorder!='little':v.byteswap()
    return v
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True);p.add_argument('--solc',type=pathlib.Path,required=True);p.add_argument('--evm-python',type=pathlib.Path,required=True);a=p.parse_args();a.out=a.out.resolve()
    assert not a.out.is_relative_to(ROOT.parents[3]),'output must be outside this repository'
    a.out.mkdir(parents=True,exist_ok=False);env=os.environ.copy();env['CARGO_TARGET_DIR']=str(a.out/'target');env['PYTHONDONTWRITEBYTECODE']='1';env['RUSTFLAGS']=''
    run(['cargo','fmt','--all','--','--check'],a.out/'fmt.log',env)
    run(['cargo','clippy','--all-targets','--locked','--offline','--','-D','warnings'],a.out/'clippy.log',env)
    run(['cargo','test','--locked','--offline'],a.out/'rust-tests.log',env)
    run(['cargo','build','--release','--locked','--offline'],a.out/'build.log',env)
    binary=a.out/'target/release/bench';evaluator=a.out/'target/release/eval'
    run([a.evm_python,ROOT/'scripts/differential.py','--eval',evaluator,'--solc',a.solc,'--out',a.out/'differential'],a.out/'differential.log',env)
    run([a.evm_python,'-m','pip','freeze'],a.out/'evm-requirements.txt',env)
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu});(a.out/'raw').mkdir()
    sources={str(x.relative_to(ROOT)):sha(x) for name in ['src','tests','scripts','reference'] for x in sorted((ROOT/name).rglob('*')) if x.is_file() and '__pycache__' not in x.parts}
    meta={'scope':'SYNTHETIC_POST_ACCRUAL_MATH_AND_LOCAL_ENGINE_NOT_NETWORK','cpu':subprocess.check_output(['lscpu'],text=True),'cpuinfo':pathlib.Path('/proc/cpuinfo').read_text(),'affinity':sorted(os.sched_getaffinity(0)),'platform':platform.platform(),'rustc':subprocess.check_output(['rustc','-vV'],text=True),'profile':'release O3 fat LTO codegen-units=1 overflow-checks=true RUSTFLAGS=empty','frequency_policy':'uncontrolled KVM host; no kernel/turbo/IRQ/governor changes','clock':'CLOCK_MONOTONIC_RAW, no overhead subtraction, individual calls','binary_sha256':sha(binary),'evaluator_sha256':sha(evaluator),'source_sha256':sources,'parent_source_sha256':{str(x.relative_to(ROOT.parent)):sha(x) for x in sorted((ROOT.parent/'src').rglob('*.rs'))},'solc_sha256':sha(a.solc),'runs':[]}
    tasks=[(r,m,fast) for r in range(3) for m in ['math','adapter','pipeline'] for fast in [0,1]];random.Random(666023).shuffle(tasks);groups={};checks={}
    for rep,mode,fast in tasks:
        label=f'{mode}-fast{fast}-{rep}';prefix=a.out/'raw'/label
        info=json.loads(subprocess.check_output([str(binary),mode,str(fast),'200000',str(666100+rep),str(prefix)],text=True,env=env))
        values=read(prefix.with_suffix('.bin'));clock=read(pathlib.Path(str(prefix)+'_clock.bin'))
        row={'label':label,'mode':mode,'fast':bool(fast),'rep':rep,'metadata':info,'stats_ns':stats(values),'clock_control_ns':stats(clock),'samples_sha256':sha(prefix.with_suffix('.bin'))}
        meta['runs'].append(row);groups.setdefault(f'{mode}|fast{fast}',[]).extend(values);checks[(rep,mode,fast)]=info
        (a.out/'benchmark.json').write_text(json.dumps(meta,indent=2)+'\n');print(label,row['stats_ns'],flush=True)
    for rep in range(3):
        for mode in ['math','adapter','pipeline']:assert checks[(rep,mode,0)]==checks[(rep,mode,1)],'different observed results'
    (a.out/'summary.json').write_text(json.dumps({k:stats(v) for k,v in groups.items()},indent=2)+'\n')
    with zipfile.ZipFile(a.out/'raw.zip','w',zipfile.ZIP_DEFLATED) as z:
        for f in sorted((a.out/'raw').glob('*.bin')):z.write(f,f.name)
    with tarfile.open(a.out/'source-snapshot.tar.gz','w:gz') as t:
        for name in ['src','tests','scripts','reference','Cargo.toml','Cargo.lock','PRE_REGISTER.md']:
            t.add(ROOT/name,arcname=name,filter=lambda i:None if '__pycache__' in i.name else i)
    run(['objdump','-Cd',binary],a.out/'disassembly.txt',env)
    with zipfile.ZipFile(a.out/'disassembly.zip','w',zipfile.ZIP_DEFLATED) as z:z.write(a.out/'disassembly.txt','disassembly.txt')
    print('COMPLETE',a.out)
if __name__=='__main__':main()
