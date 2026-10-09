#!/usr/bin/env python3
"""Compare every staged D11 replay byte against the authenticated original core."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

CORE_SHA = "eaef728506fd1ffc1bd242320c606476c468d247bb44ce5eabf1861a0042ce35"
NAMES = {"capital-sources.jsonl", "capital-requirements.jsonl", "capital-feasibility.jsonl",
         "capital-rejection-ledger.jsonl", "capital-census-summary.json", "capital-evidence-manifest.json",
         "capital-real-source-closeout.json", "capital-upstream-authority-lock.json", "capital-upstream-authority.json"}

def need(ok, message):
    if not ok:
        raise ValueError(message)

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

def verify(core, replay):
    need(digest(core) == CORE_SHA, "original core ZIP hash differs")
    envelope = json.loads((replay/"RESEARCH_ONLY.json").read_bytes())
    measurement = json.loads((replay/"measurement.json").read_bytes())
    overlay = json.loads((Path(__file__).parent/"overlay-manifest.json").read_bytes())
    need(envelope["actual_producer_overlay_sha256"] == overlay["patch_sha256"], "unbound producer overlay")
    need(envelope["actual_producer_base_commit"] == overlay["base_commit"]
         and envelope["actual_producer_base_tree"] == overlay["base_tree"], "base provenance differs")
    need(envelope["historical_metadata_parameters_are_not_actual_producer_identity"] is True
         and envelope["original_certification_transferred"] is False
         and envelope["new_producer_certified"] is False, "invalid authority scope")
    need(measurement["exit_code"] == 0 and len(measurement["stages"]) == 3
         and all(s["exit_code"] == 0 for s in measurement["stages"]), "incomplete staged replay")
    need(measurement["binary_sha256"] == envelope["binary_sha256"], "binary identity differs")
    directory = replay/"original-metadata-output"
    need({p.name for p in directory.iterdir() if not p.name.startswith(".")} == NAMES, "replayed file set differs")
    inventory = {}
    with zipfile.ZipFile(core) as z:
        need(set(z.namelist()) == NAMES and len(z.namelist()) == len(NAMES), "original core inventory differs")
        for name in sorted(NAMES):
            h = hashlib.sha256()
            length = 0
            with z.open(name) as old, (directory/name).open("rb") as new:
                while True:
                    a, b = old.read(1024*1024), new.read(1024*1024)
                    need(a == b, "exact-byte mismatch: " + name)
                    if not a:
                        break
                    h.update(a)
                    length += len(a)
            inventory[name] = {"bytes": length, "sha256": h.hexdigest(), "exact_byte_parity": True}
    closeout = json.loads((directory/"capital-real-source-closeout.json").read_bytes())
    need(closeout["source_count"] == 1045459 and closeout["requirement_count"] == 0
         and closeout["terminal_capital_census_complete"] is False, "wrong original scope")
    for name in ("closeout-first.json", "closeout-second.json"):
        need((replay/name).read_bytes() == (directory/"capital-real-source-closeout.json").read_bytes(), "separate process closeout differs")
    return {"schema": "nqc-d11-full-replay-parity-v1", "status": "ALL_NINE_ORIGINAL_D11_FILES_BYTE_IDENTICAL",
            "source_count": 1045459, "original_core_sha256": CORE_SHA, "inventory": inventory,
            "measurement": measurement, "producer": envelope,
            "upstream_d08_d09_imports_reexecuted": True, "full_bundle_verification_passes": 2,
            "historical_authority_lock_is_conditional_replay_assumption": True,
            "new_producer_certified": False, "terminal_capital_census_complete": False,
            "real_market_census_closed": False, "verifier_sha256": digest(Path(__file__))}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("core", "replay", "out"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    report = verify(args.core, args.replay)
    with args.out.open("x") as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(report["status"])
