"""Offline importer. A supplied policy pin is NOT proof of canonicality/provenance.

Preserves both original inputs and records rejection without publishing partial facts.
No RPC fetching, wallet, trading, or deployment path exists here.
"""
from dataclasses import asdict
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
R3 = ROOT.parent / "r3-state-evidence"
sys.path[:0] = [str(ROOT / "python"), str(R3 / "scripts"), str(R3 / "src")]
from fixtures import policy_from
from native_math import NativeMath
from stable_gateway import StableGateway
from state_evidence import MAX_PACKET, Rejected, load_packet, require


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--packet", type=Path, required=True)
    p.add_argument("--policy", type=Path, required=True)
    p.add_argument("--library", type=Path, required=True)
    p.add_argument("--library-sha256", required=True)
    p.add_argument("--observed-now", type=int, required=True,
                   help="Explicit replay observation time; this is not live admission")
    p.add_argument("--assumed-price", type=int)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    raw = a.packet.open("rb").read(MAX_PACKET + 1)
    policy_raw = a.policy.open("rb").read(65537)
    require(len(raw) <= MAX_PACKET and len(policy_raw) <= 65536, "input file size")
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out / "input-packet.json").write_bytes(raw)
    (a.out / "input-policy.json").write_bytes(policy_raw)
    result = {"packet_sha256": hashlib.sha256(raw).hexdigest(),
              "policy_sha256": hashlib.sha256(policy_raw).hexdigest(),
              "library_sha256": a.library_sha256, "observation_time_s": a.observed_now,
              "canonicality": "unknown", "commercial_admission": False,
              "scope": "OFFLINE_REPLAY_RELATIVE_TO_OPERATOR_PIN_NOT_LIVE_ADMISSION"}
    try:
        policy = policy_from(load_packet(policy_raw))
        native = NativeMath(a.library, a.library_sha256)
        gateway = StableGateway(policy, native)
        ticket = gateway.ingest(raw, a.observed_now)
        facts = gateway.facts(ticket, a.observed_now)
        result["status"] = "ROOT_BINDING_VERIFIED"
        result["facts"] = {"block_hash": facts.anchor.block_hash.hex(), "block_number": facts.anchor.number,
                           "market_id": facts.market_id.hex(), "borrower": facts.borrower.hex(),
                           "words": facts.values(), "layout_assurance": facts.layout_assurance,
                           "oracle_price": None, "observed_eligibility": None}
        if a.assumed_price is not None:
            result["scenario"] = asdict(gateway.scenario(ticket, a.observed_now, a.assumed_price))
        result["authorization"] = gateway.authorize(ticket, a.observed_now)
    except Exception as e:
        result.pop("facts", None)
        result.pop("scenario", None)
        result["status"] = "REJECTED"
        result["error"] = type(e).__name__ + ": " + str(e)
    (a.out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    return 0 if result["status"] == "ROOT_BINDING_VERIFIED" else 2


if __name__ == "__main__": sys.exit(main())
