"""Replay one local capture as fragments. No RPC, HTTP or builder connection."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
from inputs import policy_from, StreamIngress, NativeMath, chunks
from state_evidence import require, MAX_PACKET, load_packet


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--policy",type=Path,required=True)
    p.add_argument("--capture",type=Path,required=True)
    p.add_argument("--library",type=Path,required=True)
    p.add_argument("--library-sha256",required=True)
    p.add_argument("--observed-now",type=int,required=True)
    p.add_argument("--chunk-bytes",type=int,default=4096)
    p.add_argument("--assumed-price",type=int)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    require(1<=a.chunk_bytes<=MAX_PACKET,"chunk width")
    with a.policy.open("rb") as f:policy_raw=f.read(65537)
    with a.capture.open("rb") as f:raw=f.read(MAX_PACKET+1)
    require(len(policy_raw)<=65536 and len(raw)<=MAX_PACKET,"input size")
    a.out.mkdir(parents=True,exist_ok=False)
    (a.out/"input-policy.json").write_bytes(policy_raw)
    (a.out/"input-capture.json").write_bytes(raw)
    result={"scope":"OFFLINE_IMMEDIATE_FRAGMENT_REPLAY_NO_NETWORK",
            "engine":"R5 via R6 baseline", "canonicality":"unknown", "authentic_witness_integrated":False,
            "commercial_admission":False,"observed_candidate":None,
            "policy_sha256":hashlib.sha256(policy_raw).hexdigest(),
            "capture_sha256":hashlib.sha256(raw).hexdigest()}
    start=None
    try:
        policy=policy_from(load_packet(policy_raw))
        native=NativeMath(a.library,a.library_sha256)
        g=StreamIngress(policy,native)
        pieces=chunks(raw,a.chunk_bytes)
        require(bool(pieces),"empty capture")
        start=time.monotonic_ns()
        h=g.begin(policy,a.observed_now,pieces[0]);offset=len(pieces[0])
        for part in pieces[1:]:
            g.feed(h,offset,part,a.observed_now);offset+=len(part)
        receipt=g.finish(h,a.observed_now)
        facts=g.facts(receipt,a.observed_now)
        conditional=None if a.assumed_price is None else asdict(g.scenario(receipt,a.observed_now,a.assumed_price))
        authorization=g.authorize(receipt,a.observed_now)
        result.update(status="RELATIVE_ROOT_BINDING_VERIFIED",receipt=asdict(receipt),
                      words=facts.values(),conditional_scenario=conditional,authorization=authorization,
                      layout_assurance=facts.layout_assurance)
    except Exception as e:
        result.update(status="REJECTED",error=type(e).__name__+": "+str(e))
    finally:
        result["local_replay_elapsed_ns"]=None if start is None else time.monotonic_ns()-start
    (a.out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))
    return 2 if result["status"]=="REJECTED" else 0


if __name__=="__main__":raise SystemExit(main())
