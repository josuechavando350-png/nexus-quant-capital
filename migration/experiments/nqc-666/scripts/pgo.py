#!/usr/bin/env python3
"""Optional PGO experiment. Separate training (different seed) and evaluation.
Uses only synthetic corpora; improvement is not evidence of production representativeness.
Run AFTER reproduce.py, with no benchmark processes running concurrently.
"""
import argparse, json, os, pathlib, random, subprocess
from reproduce import ROOT,run,sha,samples,stats
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=pathlib.Path,required=True)
    p.add_argument('--matrix',type=pathlib.Path,required=True);p.add_argument('--baseline',type=pathlib.Path,required=True)
    a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    baseline=a.baseline.resolve();matrix=a.matrix.resolve()
    sysroot=pathlib.Path(subprocess.check_output(['rustc','--print','sysroot'],text=True).strip())
    profdata=sysroot/'lib/rustlib/x86_64-unknown-linux-gnu/bin/llvm-profdata'
    if not profdata.is_file():raise SystemExit('rustup component add llvm-tools --toolchain 1.90.0 required')
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    env=os.environ.copy();env['CARGO_TARGET_DIR']=str(out/'instrumented');env['RUSTFLAGS']=f'-C profile-generate={out}/profiles'
    run(['cargo','build','--locked','--offline','--profile','fat'],ROOT,out/'build-generate.log',env)
    binary=out/'instrumented/fat/bench'
    for mode,corpus in [('screen','mixed_16'),('event_final','warm_16'),('compact','warm_16')]:
        run([binary,baseline/'inputs'/f'{corpus}.txt',mode,'20000','666019',out/f'train-{mode}','0','1'],
            ROOT,out/f'train-{mode}.json',env)
    run([profdata,'merge','-o',out/'merged.profdata',*sorted((out/'profiles').glob('*.profraw'))],ROOT,out/'merge.log')
    env['CARGO_TARGET_DIR']=str(out/'use');env['RUSTFLAGS']=f'-C profile-use={out}/merged.profdata -C llvm-args=-pgo-warn-missing-function'
    run(['cargo','build','--locked','--offline','--profile','fat'],ROOT,out/'build-use.log',env)
    run(['cargo','test','--locked','--offline','--profile','fat'],ROOT,out/'test-use.log',env)
    run(['python3','tests/run_checks.py','--binary',out/'use/fat/eval','--output','pgo-checks.json'],baseline,out/'differential.log')
    binaries={'fat':matrix/'fat/fat/bench','pgo':out/'use/fat/bench'}
    tasks=[(rep,v,mode,tsc,batch) for rep in range(3) for v in binaries for mode,tsc,batch in
           [('event_final',0,1),('compact',1,128),('screen',0,1)]]
    random.Random(666019).shuffle(tasks);(out/'raw').mkdir()
    result={'training_seed':666019,'evaluation_seeds':[190000,190001,190002],
        'training_corpora':'synthetic NQC019 mixed_16 + warm_16','production_representative':False,
        'binary_sha256':{k:sha(v) for k,v in binaries.items()},'profile_sha256':sha(out/'merged.profdata'),'runs':[]}
    for rep,variant,mode,tsc,batch in tasks:
        label=f'{variant}-{mode}-{rep}';prefix=out/'raw'/label
        cmd=[binaries[variant],baseline/'inputs/warm_16.txt',mode,str(10000 if batch==128 else 200000),str(190000+rep),prefix,str(tsc),str(batch)]
        info=json.loads(subprocess.check_output(list(map(str,cmd)),text=True))
        ratio=sorted(info['tsc_ticks_per_ns'])[2] if tsc else 1
        s=samples(prefix.with_suffix('.bin'));ns=[v/ratio/batch for v in s]
        result['runs'].append({'label':label,'variant':variant,'mode':mode,'rep':rep,'metadata':info,
            'stats_ns':stats(ns),'raw_stats':stats(s),'raw_clock_control':stats(samples(pathlib.Path(str(prefix)+'_clock.bin'))),
            'metric':'dependency_chain_batch_mean_ns' if batch>1 else 'individual_call_ns',
            'samples_sha256':sha(prefix.with_suffix('.bin'))})
        (out/'pgo.json').write_text(json.dumps(result,indent=2)+'\n');print(label,stats(ns),flush=True)
if __name__=='__main__':main()
