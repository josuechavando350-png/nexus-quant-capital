"""Individual full-local-replay timings; no network or authentic witness claim."""
import argparse
import array
import gc
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import random
import resource
import subprocess
import sys
import time
import zipfile
from inputs import ROOT, R6, R3, R4, R5, cases, chunks, StreamIngress, StableGateway, NativeMath
from state_evidence import Rejected

PROFILES = {"single":0,"4096":4096,"257":257}
VARIANTS = ("r6_join", "r7_stream")
PHASES = ("assembly","verification","scenario","authorization","total")


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def stats(values):
    v=sorted(values);n=len(v)
    return {"n":n,**{k:v[math.ceil(n*q)-1] for k,q in
                    (("p50",.5),("p95",.95),("p99",.99),("p99_9",.999))},"min":v[0],"max":v[-1]}


def packed(values):
    a=array.array("Q",values)
    if sys.byteorder!="little":a.byteswap()
    return a.tobytes()


def main():
    p=argparse.ArgumentParser();p.add_argument("--library",type=Path,required=True)
    p.add_argument("--library-sha256",required=True);p.add_argument("--out",type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    allowed=sorted(os.sched_getaffinity(0));os.sched_setaffinity(0,{allowed[0]})
    assert gc.isenabled()
    dependencies={n:version(n) for n in ("trie","rlp","eth-hash","pycryptodome")}
    assert dependencies=={"trie":"4.0.0","rlp":"5.0.0","eth-hash":"0.8.0","pycryptodome":"3.24.1"}
    native=NativeMath(a.library,a.library_sha256)
    inputs=cases();now=max(policy.anchor.timestamp for _,policy in inputs)
    files=sorted(f for d in ("python","scripts","tests") for f in (ROOT/d).glob("*.py"))+[ROOT/"PRE_REGISTER.md"]
    sources={str(f.relative_to(ROOT)):sha(f) for f in files}
    baseline_files=[R6/"python/wire_evidence.py",R6/"python/witness_gateway.py",R5/"python/state_evidence_fast.py",
                    R5/"python/proof_traversal.py",R3/"src/state_evidence.py",R4/"python/native_math.py",R4/"src/lib.rs"]
    meta={"scope":"SYNTHETIC_IMMEDIATE_FRAGMENT_REPLAY_NOT_NETWORK_E2E","pairs_per_run":2048,"repetitions":3,
          "cpu":subprocess.check_output(["lscpu"],text=True),"cpuinfo":Path("/proc/cpuinfo").read_text(),
          "platform":platform.platform(),"python":sys.version,"dependencies":dependencies,
          "affinity":sorted(os.sched_getaffinity(0)),"allowed_affinity":allowed,"gc_enabled":gc.isenabled(),
          "conditions":"KVM; host frequency/load/IRQ uncontrolled; no governor/priority changes",
          "clock":"CLOCK_MONOTONIC_RAW; no subtraction/trimming", "source_sha256":sources,
          "baseline_sha256":{str(f.relative_to(ROOT.parent)):sha(f) for f in baseline_files},
          "library_sha256":sha(a.library),"input_sha256":[hashlib.sha256(raw).hexdigest() for raw,_ in inputs],
          "profiles":PROFILES,"budgets_ns":{"capture":50_000_000,"scenario":5_000_000},
          "started_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"runs":[]}
    clock=lambda:time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)
    aggregated={profile:{variant:{phase:[] for phase in PHASES} for variant in VARIANTS} for profile in PROFILES}
    with zipfile.ZipFile(a.out/"raw.zip","w",zipfile.ZIP_DEFLATED) as z:
        for rep in range(3):
            for profile,width in PROFILES.items():
                pieces=[chunks(raw,width or len(raw)) for raw,_ in inputs]
                baseline=StableGateway(inputs[0][1],native)
                stream=StreamIngress(inputs[0][1],native)
                def call(variant,index):
                    parts=pieces[index//13];policy=inputs[index//13][1];price=(index%13+1)*10**35
                    marks=[clock()];result=None;reason=None
                    try:
                        if variant=="r6_join":
                            baseline.reset(policy);raw=b"".join(parts)
                            marks.append(clock())
                            digest=hashlib.sha256(raw).hexdigest();ticket=baseline.ingest(raw,now)
                            marks.append(clock())
                            scenario=baseline.scenario(ticket,now,price);marks.append(clock())
                            auth=baseline.authorize(ticket,now)
                        else:
                            handle=stream.begin(policy,now,parts[0]);offset=len(parts[0])
                            for part in parts[1:]:
                                stream.feed(handle,offset,part,now);offset+=len(part)
                            marks.append(clock())
                            receipt=stream.finish(handle,now);digest=receipt.capture_sha256
                            marks.append(clock())
                            scenario=stream.scenario(receipt,now,price);marks.append(clock())
                            auth=stream.authorize(receipt,now)
                        result=(scenario,auth,digest)
                    except Rejected as e:
                        reason=str(e)
                    end=clock()
                    marks.extend([end]*(5-len(marks)))
                    values=[b-a for a,b in zip(marks,marks[1:])]+[end-marks[0]]
                    assert sum(values[:4])==values[4]
                    return result,reason,values
                for i in range(64):
                    b,be,_=call("r6_join",i);s,se,_=call("r7_stream",i)
                    assert be is se is None and b==s
                seed=666701+rep*3+list(PROFILES).index(profile)
                sequence=[i%208 for i in range(2048)];random.Random(seed).shuffle(sequence)
                values={v:{phase:[] for phase in PHASES} for v in VARIANTS}
                statuses={v:bytearray() for v in VARIANTS};checks={v:hashlib.sha256() for v in VARIANTS}
                calibration=[];drops=[];distinct=set();usage0=resource.getrusage(resource.RUSAGE_SELF)
                for pair,index in enumerate(sequence):
                    c0=clock();c1=clock();calibration.append(c1-c0)
                    results={}
                    for variant in VARIANTS[::1 if pair%2==0 else -1]:
                        result,reason,times=call(variant,index)
                        for phase,value in zip(PHASES,times):values[variant][phase].append(value)
                        statuses[variant].append(int(reason is not None))
                        if reason is not None:
                            assert "deadline" in reason or "expired" in reason,reason
                            drops.append({"pair":pair,"variant":variant,"reason":reason,"elapsed_ns":times[-1]})
                        else:
                            encoded=repr(result).encode();checks[variant].update(encoded)
                            distinct.add(hashlib.sha256(encoded).hexdigest());results[variant]=result
                    if len(results)==2:assert results["r6_join"]==results["r7_stream"]
                usage1=resource.getrusage(resource.RUSAGE_SELF);label=f"{profile}-rep{rep}"
                z.writestr(label+"-indices.bin",packed(sequence));z.writestr(label+"-clock.bin",packed(calibration))
                for variant in VARIANTS:
                    z.writestr(label+"-"+variant+"-status.bin",statuses[variant])
                    for phase in PHASES:
                        z.writestr(label+"-"+variant+"-"+phase+".bin",packed(values[variant][phase]))
                        aggregated[profile][variant][phase].extend(values[variant][phase])
                meta["runs"].append({"label":label,"profile":profile,"rep":rep,"seed":seed,
                    "stats_ns":{v:{p:stats(x) for p,x in ps.items()} for v,ps in values.items()},
                    "clock_ns":stats(calibration),"drops":drops,"distinct_outputs":len(distinct),
                    "output_sha256":{v:h.hexdigest() for v,h in checks.items()},
                    "context_switches":{"voluntary":usage1.ru_nvcsw-usage0.ru_nvcsw,"involuntary":usage1.ru_nivcsw-usage0.ru_nivcsw},
                    "sample_sha256":{v:{p:hashlib.sha256(packed(x)).hexdigest() for p,x in ps.items()} for v,ps in values.items()}})
                print(label+" complete",flush=True)
    assert sources=={str(f.relative_to(ROOT)):sha(f) for f in files}
    meta["aggregate_ns"]={profile:{v:{p:stats(x) for p,x in ps.items()} for v,ps in vs.items()} for profile,vs in aggregated.items()}
    meta["finished_utc"]=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime());meta["raw_sha256"]=sha(a.out/"raw.zip")
    (a.out/"result.json").write_text(json.dumps(meta,indent=2)+"\n")
    print(json.dumps({"total_ns":{p:{v:x["total"] for v,x in vs.items()} for p,vs in meta["aggregate_ns"].items()},
                      "drops":sum(len(r["drops"]) for r in meta["runs"])}))


if __name__=="__main__":main()
