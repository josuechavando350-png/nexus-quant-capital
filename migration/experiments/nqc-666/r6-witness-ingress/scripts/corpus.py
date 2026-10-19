"""Synthetic transport wrappers for the existing R3 fixtures, not RPC evidence."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
R3 = ROOT.parent / "r3-state-evidence"
R5 = ROOT.parent / "r5-proof-traversal"
R4 = ROOT.parent / "r4-stable-ingress"
sys.path[:0] = [str(ROOT / "python"), str(R3 / "scripts"), str(R3 / "src"), str(R4 / "python"), str(R5 / "python")]
from fixtures import policy_from
from wire_evidence import request_plan, encode


def wrap(packet, policy):
    return {"schema": "nqc666-rpc-capture-v1", "statePoint": "end_of_block",
            "requests": request_plan(policy),
            "responses": [{"jsonrpc": "2.0", "id": i, "result": packet[key]}
                          for i,key in ((1,"chainId"), (2,"header"), (3,"code"), (4,"account"))]}


def cases():
    index = json.loads((R3 / "fixtures/synthetic-index.json").read_text())
    return [(encode(wrap(json.loads((R3 / "fixtures" / row["packet"]).read_bytes()),
                         policy_from(row["policy"]))), policy_from(row["policy"])) for row in index]
