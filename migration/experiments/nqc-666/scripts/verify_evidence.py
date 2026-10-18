#!/usr/bin/env python3
"""Recompute recorded percentiles from ALL raw samples, without filtering/subtraction.
Run from this experiment: python3 scripts/verify_evidence.py
"""
import array, hashlib, json, math, pathlib, statistics, sys, zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
def stats(values):
    s=sorted(values);n=len(s)
    return {'n':n,**{name:s[math.ceil(n*q)-1] for name,q in [('p50',.5),('p95',.95),('p99',.99),('p99_9',.999)]},'max':s[-1],'min':s[0]}
def decode(raw):
    a=array.array('Q');a.frombytes(raw)
    if sys.byteorder!='little':a.byteswap()
    return a
def verify(directory):
    meta=json.loads((directory/'benchmark.json').read_text());groups={};total=0
    with zipfile.ZipFile(directory/'raw.zip') as z:
        assert len(z.namelist())==2*len(meta['runs'])
        for r in meta['runs']:
            label=r['label'];raw=z.read(label+'.bin')
            assert hashlib.sha256(raw).hexdigest()==r['samples_sha256'],label
            ticks=decode(raw);assert stats(ticks)==r['raw_stats'],label
            assert stats(decode(z.read(label+'_clock.bin')))==r['raw_clock_control'],label
            m=r['metadata'];batch=m['batch_size'];ratio=statistics.median(m['tsc_ticks_per_ns']) if m['tsc'] else 1
            ns=[v/ratio/batch for v in ticks];assert stats(ns)==r['stats_ns'],label
            key='|'.join([r['variant'],r['mode'],r.get('corpus','warm_16'),r['metric'],'tsc' if m['tsc'] else 'raw'])
            groups.setdefault(key,[]).extend(ns);total+=len(ticks)
    summary={key:{**stats(v),'above_3000_ns':sum(x>3000 for x in v)} for key,v in groups.items()}
    return {'runs':len(meta['runs']),'timed_samples':total,'groups':summary}
def main():
    result={}
    for p in sorted((ROOT/'evidence').glob('run*')):
        if p.is_dir() and (p/'raw.zip').exists():result[p.name]=verify(p)
    assert result,'no evidence found'
    expected=ROOT/'evidence/summary.json'
    if expected.exists():assert json.loads(expected.read_text())==result,'summary mismatch'
    else:expected.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'verified':True,'runs':sum(x['runs'] for x in result.values()),
        'timed_samples':sum(x['timed_samples'] for x in result.values()),'summaries':list(result)},indent=2))
if __name__=='__main__':main()
