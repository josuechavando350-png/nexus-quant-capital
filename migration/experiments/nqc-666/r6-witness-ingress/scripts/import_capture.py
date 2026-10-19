"""Local-only integration. R5 baseline default; experiments explicitly selected."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from corpus import ROOT, policy_from
from state_evidence import load_packet, require, MAX_PACKET
from wire_evidence import request_plan, verify_wire_baseline, verify_wire_object, verify_wire
from witness_gateway import StableGateway
from native_math import NativeMath

VARIANTS = {"baseline": verify_wire_baseline, "object": verify_wire_object, "optimized": verify_wire}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--policy",type=Path,required=True)
    p.add_argument("--capture",type=Path)
    p.add_argument("--library",type=Path)
    p.add_argument("--library-sha256")
    p.add_argument("--observed-now",type=int)
    p.add_argument("--assumed-price",type=int)
    p.add_argument("--variant",choices=VARIANTS,default="baseline")
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    policy_raw=a.policy.open("rb").read(65537)
    require(len(policy_raw)<=65536,"policy size")
    raw=None if a.capture is None else a.capture.open("rb").read(MAX_PACKET+1)
    require(raw is None or len(raw)<=MAX_PACKET,"capture size")
    a.out.mkdir(parents=True,exist_ok=False)
    (a.out/"input-policy.json").write_bytes(policy_raw)
    if raw is not None:(a.out/"input-capture.json").write_bytes(raw)
    result={"commercial_admission":False,"canonicality":"unknown","observed_candidate":None,
            "policy_sha256":hashlib.sha256(policy_raw).hexdigest(),
            "capture_sha256":None if raw is None else hashlib.sha256(raw).hexdigest(),
            "variant":a.variant,"scope":"OFFLINE_ROOT_BINDING_ONLY_NOT_AUTHENTICATED_CHAIN_OR_LIVE_ADMISSION"}
    try:
        policy=policy_from(load_packet(policy_raw))
        plan=request_plan(policy)
        (a.out/"requests.json").write_text(json.dumps(plan,indent=2)+"\n")
        if raw is None:
            result["status"]="REQUEST_PLAN_ONLY_NOT_SENT"
            result["root_binding_verified"]=False
        else:
            require(a.library is not None and a.library_sha256 is not None and a.observed_now is not None,
                    "library/hash/observation time required")
            native=NativeMath(a.library,a.library_sha256)
            g=StableGateway(policy,native,verifier=VARIANTS[a.variant])
            t=g.ingest(raw,a.observed_now)
            f=g.facts(t,a.observed_now)
            result.update(status="ROOT_BINDING_VERIFIED",root_binding_verified=True,
                          block_hash=f.anchor.block_hash.hex(),words=f.values(),
                          layout_assurance=f.layout_assurance,oracle_price=None,observed_eligibility=None)
            if a.assumed_price is not None:result["conditional_scenario"]=asdict(g.scenario(t,a.observed_now,a.assumed_price))
            result["authorization"]=g.authorize(t,a.observed_now)
    except Exception as e:
        # No partial facts escape even when a late scenario/authorization fails.
        for key in ("words","block_hash","layout_assurance","oracle_price","observed_eligibility",
                    "conditional_scenario","authorization"):result.pop(key,None)
        result.update(status="REJECTED",root_binding_verified=False,error=type(e).__name__+": "+str(e))
    (a.out/"result.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))
    return 2 if result["status"]=="REJECTED" else 0


if __name__=="__main__":sys.exit(main())
