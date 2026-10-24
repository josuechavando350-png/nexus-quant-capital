#!/usr/bin/env python3
"""Prepare bounded pre-event Aave reads from a complete verified Miner journal.

No network. Plans retain exact event/source identity and the original evidence
class. New live configs must be bound separately to the clean reader executable.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path

from archive_collection import new_json, packed, sync_dir
from export_parquet import (ExportError, _binary_json, _bounded_read, _check_path,
                            _envelopes, _file_sha, _json, _owner, _sha, export_journal)

MAX_BYTES = 8 * 1024 * 1024


def prepare(state: Path, output: Path, verifier: Path, lookback: int = 16):
    if type(lookback) is not int or not 1 <= lookback <= 64:
        raise ExportError("lookback must be 1..64 blocks")
    state, verifier = _check_path(state), _check_path(verifier)
    output = _check_path(output, must_exist=False)
    if output.exists() or state == output or state in output.parents or output in state.parents:
        raise ExportError("output must be new and outside source")
    identity = _owner(_json(_bounded_read(state / "owner.json", 65536)))
    if identity["data_class"] not in {"historical", "synthetic"}:
        raise ExportError("retrospective reads cannot admit Shadow")
    if identity["run_id"].startswith("window-") or (state / "collector.json").exists():
        raise ExportError("collection windows require parent revocation context")
    output.mkdir(mode=0o700)
    exported = export_journal(state, output / "verified-export", verifier,
                              maximum_bytes=MAX_BYTES, maximum_records=10_000)
    if exported["owner"] != identity:
        raise ExportError("owner changed during plan preparation")
    source = output / "verified-export" / "source"
    config = _json(_bounded_read(source / "config.json", 1048576))
    verified = _json(_bounded_read(output / "verified-export/verification.json", 65536))
    if (verified["completed_scopes"] != len(config["scopes"]) or verified["invalidated_from"]
            or verified["provisional_events"] or verified["invalidated_events"]):
        raise ExportError("read planning requires complete unrevoked scopes")
    scopes = {s["id"]: s for s in config["scopes"]}
    journal_hash = next(s["sha256"] for s in exported["source_files"] if s["file"] == "events.jsonl")
    entries, seen = [], set()
    for raw, envelope in _envelopes(source / "events.jsonl", 10_000):
        r = envelope["record"]
        if r["kind"] != "observed" or r["decoded"]["kind"] != "liquidation":
            continue
        payload, log = r["decoded"]["payload"], r["log"]
        if payload["family"] != "aave_v3_pool":
            continue
        key = (log["chain_id"], log["transaction_hash"], log["log_index"])
        if key in seen or len(entries) >= 32:
            raise ExportError("duplicate event or more than 32 plans; narrow the source capture")
        seen.add(key)
        scope = scopes[r["scope_id"]]
        entry = {"event_identity": payload["identity"], "source_line_sha256": _sha(raw),
                 "sequence": envelope["sequence"], "scope_id": r["scope_id"]}
        if log["block_number"] <= scope["from_block"]:
            entries.append({**entry, "status": "no_pre_event_block_in_scope"})
            continue
        plan = {"schema_version": 1, "scope_id": r["scope_id"], "borrower": payload["borrower"],
                "assets": sorted({payload["debt_token"], payload["collateral_token"]}),
                "from_block": max(scope["from_block"], log["block_number"] - lookback),
                "to_block": log["block_number"] - 1, "event_block": log["block_number"],
                "event_block_hash": log["block_hash"]}
        plan_file = f"plan-{len(entries):03d}.json"
        new_json(output / plan_file, plan)
        checked = _binary_json(verifier, "validate-aave-plan", "--config", str(source / "config.json"),
                               "--plan", str(output / plan_file))
        if checked != {"valid": True, "plan": plan, "network_used": False, "activation_allowed": False}:
            raise ExportError("Rust plan validation mismatch")
        entries.append({**entry, "status": "prepared_not_executed", "plan_file": plan_file,
                        "plan_sha256": _file_sha(output / plan_file, 65536),
                        "sample_blocks": plan["to_block"] - plan["from_block"] + 1})
    template = copy.deepcopy(config)
    template.update(schema_version=2, run_id="aave-state-" + _sha(packed([journal_hash, lookback, entries]))[:48],
                    code_commit="__FROM_ABOUT__", cargo_lock_sha256="__FROM_ABOUT__",
                    build_identity_sha256="__FROM_ABOUT__")
    new_json(output / "config.template.json", template)
    for entry in exported["source_files"]:
        if _file_sha(source / entry["file"], MAX_BYTES) != entry["sha256"]:
            raise ExportError("verified source changed during planning")
    if _file_sha(verifier, 512 * 1024 * 1024) != exported["verifier_sha256"]:
        raise ExportError("verifier changed during planning")
    manifest = {"schema": "nqc-miner-aave-read-plans-v1", "namespace": "nqc_miner_v1", "producer": "nqc-miner",
                "source_owner": identity, "source_journal_sha256": journal_hash, "data_class": identity["data_class"],
                "lookback_blocks": lookback, "events": entries, "live_reads_executed": False,
                "config_template_sha256": _file_sha(output / "config.template.json", 1048576),
                "verified_export_manifest_sha256": _file_sha(output / "verified-export/manifest.json", 1048576),
                "preparer_sha256": _file_sha(Path(__file__), 1048576), "complete": True,
                "executable_eligibility_verified": False, "economic_certification": False,
                "observer_bridge_enabled": False, "activation_allowed": False}
    new_json(output / "manifest.json", manifest)
    sync_dir(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("state", "output", "verifier"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--lookback", type=int, default=16)
    args = parser.parse_args()
    try:
        result = prepare(args.state, args.output, args.verifier, args.lookback)
    except (ExportError, OSError, KeyError, TypeError) as error:
        parser.exit(1, f"nqc-miner Aave plan rejected: {error}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
