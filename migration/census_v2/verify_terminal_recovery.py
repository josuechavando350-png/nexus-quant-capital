#!/usr/bin/env python3
"""Pinned D11 core / D12 recovery and conditional replay, never certification.

API snapshots must be acquired independently. This consumer authenticates bytes
and checks provenance consistency; it cannot authenticate its own API provenance
or transfer original authority to the new repository.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

from verify_historical_inputs import ROOT, digest, equal, parse, require, safe, transport

REPOSITORY = "josuechavando350-png/nexus-engine"
PINS = {
    "d11": {"run_id": 37701875199, "artifact_id": 11518151377,
            "head_sha": "83395dc182cb7fd31293887f4de86fcd022b4b6d",
            "tree": "1ab7d599776babd5aeb3478d44c3c692fb9ad5d8",
            "workflow_name": "NQC RMC-011 Real Source Certification",
            "artifact_name": "rmc011-core-bundle-83395dc182cb7fd31293887f4de86fcd022b4b6d",
            "artifact_digest": "sha256:eaef728506fd1ffc1bd242320c606476c468d247bb44ce5eabf1861a0042ce35"},
    "d12": {"run_id": 37704109137, "artifact_id": 11519153831,
            "head_sha": "9368ec833ee26d0bf8f8203ce2ca1ef09ae004a2",
            "tree": "0aa1df487271739f9620b641466bb72bad1eea10",
            "workflow_name": "NQC RMC-012 Terminal Actionability Authority",
            "artifact_name": "rmc012-terminal-actionability-9368ec833ee26d0bf8f8203ce2ca1ef09ae004a2",
            "artifact_digest": "sha256:bbe6a6365d563eb41125d9fcdba79ac384c21182f31f6761897e0ce2ee8fa3b8"},
}
SOURCE_SHA = "b97cf0d8cb1dfcaaae7f2b79a3eef40e20b7cd9d7a7c996ab15960153adefb48"
VIEW_SHA = "d6d17bd9799043d6d869ddf389ee6d6eefa26ef21e072d14ce9748a891982a1c"
LOCK_SHA = "7f48d35f0373785ff2fbd6f84b385efe58dbb831f6c3cc7953adb50e3c999d95"
NEW_COMMIT = "dfc259fca3b3144b0623461cb46346e2e960dce1"
NEW_TREE = "b25947022554a9ba5b50faa3a77831f16010d201"


def legacy():
    spec = importlib.util.spec_from_file_location("legacy_d12_diagnostic", ROOT / "ci/nqc-census/rmc012_execution_blocker_root_cause.py")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def api(stage, directory):
    blobs = {k: (directory / (stage + "-" + k + ".json")).read_bytes() for k in ("run", "artifact", "commit")}
    artifact, tree, event = transport(PINS[stage], blobs, REPOSITORY)
    equal(tree, PINS[stage]["tree"], "pinned tree")
    equal(event, "push", "producer event")
    return artifact, {k: hashlib.sha256(v).hexdigest() for k, v in blobs.items()}


def outer(path, stage, artifact):
    require(path.is_file() and not path.is_symlink(), "regular archive required")
    with path.open("rb") as f:
        sha, size = digest(f)
    equal("sha256:" + sha, PINS[stage]["artifact_digest"], stage + " ZIP digest")
    equal(size, artifact["size_in_bytes"], stage + " ZIP bytes")


def replay_parity(archive, replay):
    with zipfile.ZipFile(archive) as z:
        old = {n: z.read(n) for n in ("actionability-records.jsonl", "capital-promotions.jsonl", "portfolio-capacity.json", "actionability-summary.json")}
    parity = {}
    for n in ("actionability-records.jsonl", "capital-promotions.jsonl"):
        raw = (replay / n).read_bytes()
        equal(raw, old[n], n + " actual Rust replay")
        parity[n] = hashlib.sha256(raw).hexdigest()
    a, b = parse(old["portfolio-capacity.json"]), parse((replay / "portfolio-capacity.json").read_bytes())
    differences = {k: {"original": a.get(k), "replay": b.get(k)} for k in a.keys() | b.keys() if a.get(k) != b.get(k)}
    equal(set(differences), {"code_commit", "code_tree", "portfolio_commitment"}, "portfolio mismatch inventory")
    equal(b["code_commit"], NEW_COMMIT, "replay source commit")
    equal(b["code_tree"], NEW_TREE, "replay source tree")
    s = parse((replay / "actionability-summary.json").read_bytes())
    for k, v in {"code_commit": NEW_COMMIT, "code_tree": NEW_TREE,
                 "d11_capital_source_count": 67, "d11_capital_sources_sha256": VIEW_SHA,
                 "upstream_authority_lock_sha256": LOCK_SHA, "expected_pairs": 474,
                 "admitted": 432, "rejected": 42, "principal_capital_feasible": 0,
                 "gas_funding_certified": False}.items():
        equal(s[k], v, "replay " + k)
    return {"exact_byte_parity": parity, "portfolio_differences": differences,
            "portfolio_claims_resources_conflicts_equal": True,
            "new_producer_certified": False, "legacy_authority_flags_are_replay_assumptions": True}


def verify(d11, d12, metadata, replay):
    arts, meta = {}, {}
    for stage, archive in (("d11", d11), ("d12", d12)):
        arts[stage], meta[stage] = api(stage, metadata)
        outer(archive, stage, arts[stage])
    required = {"capital-sources.jsonl", "capital-requirements.jsonl", "capital-feasibility.jsonl",
                "capital-rejection-ledger.jsonl", "capital-census-summary.json",
                "capital-evidence-manifest.json", "capital-real-source-closeout.json",
                "capital-upstream-authority-lock.json", "capital-upstream-authority.json"}
    inventory = {}
    with zipfile.ZipFile(d11) as z:
        equal(set(z.namelist()), required, "D11 core inventory")
        equal(len(z.namelist()), len(required), "D11 member uniqueness")
        for info in z.infolist():
            equal(info.filename, safe(info.filename), "safe path")
            require(not info.is_dir() and info.file_size <= 3_800_000_000, "D11 member bounds")
            with z.open(info) as stream:
                sha, size = digest(stream)
            equal(size, info.file_size, "D11 member length")
            inventory[info.filename] = {"sha256": sha, "bytes": size}
        manifest = parse(z.read("capital-evidence-manifest.json"))
        closeout = parse(z.read("capital-real-source-closeout.json"))
        listed = set()
        for row in manifest["artifacts"]:
            name = row["name"]
            require(name in required and name not in listed, "D11 manifest duplicate/extra")
            equal(inventory[name], {"sha256": row["sha256"], "bytes": row["size_bytes"]}, "D11 manifest content")
            listed.add(name)
        equal(len(listed), 6, "D11 manifested count")
        for doc in (manifest, closeout):
            equal(doc["code_commit"], PINS["d11"]["head_sha"], "D11 provenance")
            equal(doc["code_tree"], PINS["d11"]["tree"], "D11 tree")
        equal(inventory["capital-sources.jsonl"], {"sha256": SOURCE_SHA, "bytes": 3757728513}, "full capital source pin")
        equal(inventory["capital-upstream-authority-lock.json"]["sha256"], LOCK_SHA, "D11 authority lock bytes")
        equal(closeout["source_count"], 1045459, "D11 source count")
        equal(closeout["terminal_capital_census_complete"], False, "D11 terminal scope")
    original = legacy()
    summary, actions, promotions = original.read_d12(d12)
    original.parse_actionability(actions, promotions)
    with zipfile.ZipFile(d12) as z:
        cert = parse(z.read("terminal-actionability-certification.json"))
    equal(cert["code_commit"], PINS["d12"]["head_sha"], "D12 provenance")
    equal(cert["code_tree"], PINS["d12"]["tree"], "D12 tree")
    equal(cert["d11"]["real_source_closeout_sha256"], inventory["capital-real-source-closeout.json"]["sha256"], "D12 refers to exact recovered D11 closeout")
    equal(cert["d11_capital_sources_sha256"], SOURCE_SHA, "D12 full source binding")
    equal(summary["anchor"], manifest["observation_anchor"], "D11/D12 anchor")
    return {"schema": "nqc-terminal-recovery-readback-v1", "status": "PINNED_CORE_AND_ACTIONABILITY_REPLAY_VERIFIED",
            "pins": PINS, "api_snapshot_sha256": meta, "d11_inventory": inventory,
            "observation_anchor": summary["anchor"], "d11_terminal_capital_census_complete": False,
            "d11_main_envelope_downloaded": False, "d11_main_envelope_limit_bytes": 536870912,
            "d11_main_envelope_claims_transferred": False, "replay": replay_parity(d12, replay),
            "scope": "HISTORICAL_AAVE_ACTIONABILITY_AND_D11_CORE_READBACK_ONLY",
            "decision_time_availability_proven": False, "independent_certification": False,
            "real_market_census_closed": False,
            "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("d11", "d12", "metadata", "replay", "output"):
        p.add_argument("--" + arg, type=Path, required=True)
    a = p.parse_args()
    result = verify(a.d11, a.d12, a.metadata, a.replay)
    with a.output.open("x") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")
    print(result["status"])
