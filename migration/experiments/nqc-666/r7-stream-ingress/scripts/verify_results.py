"""Recompute timings and output digests from raw samples and Python integer math."""
import argparse
import array
import hashlib
import json
from pathlib import Path
import random
import sys
import zipfile
from inputs import ROOT, R3, cases
from gateway import Conditional

VARIANTS=("r6_join","r7_stream")
PHASES=("assembly","verification","scenario","authorization","total")
PROFILES={"single":0,"4096":4096,"257":257}


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def unpack(raw):
    a=array.array("Q");a.frombytes(raw)
    if sys.byteorder!="little":a.byteswap()
    return list(a)


def distribution(values):
    v=sorted(values);n=len(v)
    return {"n":n,"min":v[0],"max":v[-1],**{k:v[(n*p+q-1)//q-1]
        for k,p,q in (("p50",1,2),("p95",95,100),("p99",99,100),("p99_9",999,1000))}}


def expected_outputs():
    records=json.loads((R3/"fixtures/synthetic-index.json").read_text());inputs=cases();outputs=[]
    for index in range(208):
        row=records[index//13];v=row["words"];mask=2**128-1;price=(1+index%13)*10**35
        a,s,shares,coll=v["borrow"]&mask,v["borrow"]>>128,v["position"]&mask,v["position"]>>128
        numerator=shares*(a+1)+(s+10**6)-1
        assert 0<=numerator<2**256 and coll*price<2**256
        debt=numerator//(s+10**6);value=coll*price//10**36
        assert value*v["lltv"]<2**256
        cap=value*v["lltv"]//10**18
        conditional=Conditional(debt,cap,debt>cap,price,row["policy"]["anchor"]["timestamp"])
        auth={"commercial_admission":False,"observed_candidate":None,
              "missing":("canonical_chain_evidence","runtime_layout_attestation","oracle_execution_and_freshness",
                         "full_execution_simulation","financial_and_nonrecourse_authorization")}
        outputs.append(repr((conditional,auth,hashlib.sha256(inputs[index//13][0]).hexdigest())).encode())
    return outputs


def check(path):
    meta=json.loads((path/"result.json").read_text())
    assert meta["raw_sha256"]==sha(path/"raw.zip")
    for name,digest in meta["source_sha256"].items():assert sha(ROOT/name)==digest,name
    for name,digest in meta["baseline_sha256"].items():assert sha(ROOT.parent/name)==digest,name
    assert meta["input_sha256"]==[hashlib.sha256(raw).hexdigest() for raw,_ in cases()]
    assert meta["pairs_per_run"]==2048 and meta["repetitions"]==3 and meta["profiles"]==PROFILES
    assert len(meta["runs"])==9
    combined={p:{v:{phase:[] for phase in PHASES} for v in VARIANTS} for p in PROFILES}
    drops_by_variant={v:0 for v in VARIANTS};expected=expected_outputs();seen=set()
    with zipfile.ZipFile(path/"raw.zip") as z:
        assert len(z.namelist())==126 and len(set(z.namelist()))==126
        for run in meta["runs"]:
            profile,rep,label=run["profile"],run["rep"],run["label"]
            assert profile in PROFILES and rep in range(3) and (profile,rep) not in seen
            seen.add((profile,rep));assert label==f"{profile}-rep{rep}"
            assert run["seed"]==666701+rep*3+list(PROFILES).index(profile)
            sequence=[i%208 for i in range(2048)];random.Random(run["seed"]).shuffle(sequence)
            assert unpack(z.read(label+"-indices.bin"))==sequence
            clocks=unpack(z.read(label+"-clock.bin"));assert len(clocks)==2048 and distribution(clocks)==run["clock_ns"]
            timings={};statuses={};distinct=set()
            for variant in VARIANTS:
                statuses[variant]=z.read(label+"-"+variant+"-status.bin")
                assert len(statuses[variant])==2048 and set(statuses[variant])<={0,1}
                timings[variant]={}
                for phase in PHASES:
                    raw=z.read(label+"-"+variant+"-"+phase+".bin");values=unpack(raw)
                    assert len(values)==2048 and hashlib.sha256(raw).hexdigest()==run["sample_sha256"][variant][phase]
                    assert distribution(values)==run["stats_ns"][variant][phase]
                    timings[variant][phase]=values;combined[profile][variant][phase].extend(values)
                assert all(sum(timings[variant][p][i] for p in PHASES[:4])==timings[variant]["total"][i] for i in range(2048))
                output=hashlib.sha256()
                for i,index in enumerate(sequence):
                    if not statuses[variant][i]:
                        output.update(expected[index]);distinct.add(hashlib.sha256(expected[index]).hexdigest())
                assert output.hexdigest()==run["output_sha256"][variant],"observable output mismatch"
            assert run["distinct_outputs"]==len(distinct)>1
            drops={(v,i) for v,s in statuses.items() for i,status in enumerate(s) if status}
            assert len(drops)==len(run["drops"])
            assert drops=={(d["variant"],d["pair"]) for d in run["drops"]}
            for d in run["drops"]:
                assert "deadline" in d["reason"] or "expired" in d["reason"]
                assert d["elapsed_ns"]==timings[d["variant"]]["total"][d["pair"]]
                drops_by_variant[d["variant"]]+=1
    aggregate={p:{v:{phase:distribution(x) for phase,x in phases.items()} for v,phases in vs.items()} for p,vs in combined.items()}
    assert aggregate==meta["aggregate_ns"]
    return {"raw_distributions_verified":True,"phase_sums_verified":True,"observable_outputs_verified_against_python_integer_reference":True,
            "individual_windows":36864,"all_attempts_retained":True,"late_drops_by_variant":drops_by_variant,
            "engine_default":"R5","optimization_promoted":False,"whole_bot_stabilized":False,
            "authentic_witness_integrated":False,"network_builder_e2e_measured":False,"commercial_admission":False}


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("path",type=Path);a=p.parse_args()
    print(json.dumps(check(a.path),indent=2))
