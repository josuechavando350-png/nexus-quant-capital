#!/usr/bin/env python3
"""Recalculate all delivered individual-call percentiles and corpus hashes, offline."""
import array,gzip,hashlib,json,math,pathlib,sys,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
def stats(v):
    v=sorted(v);n=len(v)
    return {'n':n,**{k:v[math.ceil(n*q)-1] for k,q in [('p50',.5),('p95',.95),('p99',.99),('p99_9',.999)]},'max':v[-1],'min':v[0]}
def values(raw):
    v=array.array('Q');v.frombytes(raw)
    if sys.byteorder!='little':v.byteswap()
    return v
def main():
    p=ROOT/'evidence';m=json.loads((p/'benchmark.json').read_text());groups={}
    with zipfile.ZipFile(p/'raw.zip') as z:
        assert len(z.namelist())==2*len(m['runs'])
        for r in m['runs']:
            b=z.read(r['label']+'.bin');v=values(b);assert hashlib.sha256(b).hexdigest()==r['samples_sha256'];assert stats(v)==r['stats_ns']
            assert stats(values(z.read(r['label']+'_clock.bin')))==r['clock_control_ns']
            groups.setdefault(f'{r["mode"]}|fast{int(r["fast"])}',[]).extend(v)
    assert {k:stats(v) for k,v in groups.items()}==json.loads((p/'summary.json').read_text())
    d=json.loads((p/'differential/results.json').read_text())
    for f,k in [('corpus.txt.gz','corpus_sha256'),('outputs.txt.gz','output_sha256')]:assert hashlib.sha256(gzip.decompress((p/'differential'/f).read_bytes())).hexdigest()==d[k]
    assert all(hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==v for k,v in m['source_sha256'].items())
    assert all(hashlib.sha256((ROOT.parent/k).read_bytes()).hexdigest()==v for k,v in m['parent_source_sha256'].items())
    print(json.dumps({'verified':True,'runs':len(m['runs']),'samples':sum(len(v) for v in groups.values()),'formula_cases':d['cases'],'evm_cases':d['evm']['cases'],'current_source_matches_measurement':True},indent=2))
if __name__=='__main__':main()
