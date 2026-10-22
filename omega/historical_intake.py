"""Replay authentic RMC-016 event/receipt artifacts into a partial market ledger.

This is an offline, reviewed capture. Remote origin is anchored by the pinned
metadata captured through GitHub, never asserted by arbitrary self-hashed JSON.
Gas is charged once per transaction, including transactions with several events.
Missing economic/position/oracle fields remain unknown. No new chain acquisition.
"""
from __future__ import annotations

import argparse
import builtins
import copy
import io
import json
from datetime import datetime
from pathlib import Path
import re
import stat
import sys
import tempfile
from types import ModuleType
import zipfile

from integrity import canonical, digest, git_blob, read_regular, strict_json

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "omega/evidence"
PIN_SHA256 = "b249194b3274abc42ecc936a3581e1b4fb6658d716880b57ffa5934d421b4bb0"
SCHEMA = "nqc.omega.historical-receipt-ledger.v1"
SOURCE = "josuechavando350-png/nexus-engine"
SOURCE_ID = 1333360261
API = "https://api.github.com/repos/" + SOURCE
MAX_ARCHIVE = 128 * 1024
MAX_MEMBER = 128 * 1024
MAX_EXPANDED = 256 * 1024
GAS_TOTAL = 448369976498898050
PINS = {
    "events": {"run": 37718661409, "artifact": 11524139188,
        "commit": "abe54f1f23bd7bff8c37871200f7da7c59c45ac3",
        "tree": "c74f8d9d2c317a011284398643b2d4aa6de06e83",
        "branch": "nqc/rmc016-full-liquidation-ledger-20261008",
        "workflow": ".github/workflows/nqc-rmc016-full-liquidation-discovery.yml",
        "workflow_id": 378020686, "conclusion": "success",
        "name": "rmc016-full-liquidation-events-abe54f1f23bd7bff8c37871200f7da7c59c45ac3",
        "sha256": "6b4098c1acf153106ac5b67d2c5c7db5cd0295a16c782ad8c34ae75303306204"},
    "receipts": {"run": 37719091371, "artifact": 11524199698,
        "commit": "569d4aaeecb3d066389c054efed695be02e3ef40",
        "tree": "ba648214fb5cb1cdca1db1f42f28059054d78e63",
        "branch": "nqc/rmc016-dual-receipt-parity-20261008",
        "workflow": ".github/workflows/nqc-rmc016-dual-receipt-parity.yml",
        "workflow_id": 378024555, "conclusion": "failure",
        "name": "rmc016-dual-winner-receipts-569d4aaeecb3d066389c054efed695be02e3ef40",
        "sha256": "182b5e81b00ca04e53c9193c1496a725dc152ade9a17d3ab2dfaeb5045ac86b6"},
    "legs": {"run": 37722878737, "artifact": 11525823668,
        "commit": "b02e7c5a4ff9a8c38898ab35e46777f9af35d192",
        "tree": "9cb8e4fe11792eb4afb0fc604c886bbff5919fee",
        "branch": "nqc/rmc016-authenticated-liquidation-legs-20261008",
        "workflow": ".github/workflows/nqc-rmc016-aave-event-legs.yml",
        "workflow_id": 378049145, "conclusion": "success",
        "name": "rmc016-integer-liquidation-legs-b02e7c5a4ff9a8c38898ab35e46777f9af35d192",
        "sha256": "b5927f49a5099a9fe8971df82f1ea5fa2c4a169b11a846f2f3c2671b1efa71ee"},
}
SOURCE_BLOBS = {
    "rmc016_probe_historical_rpc": "a53b49abe988d365a16c3317fa7ae974f5595e01",
    "rmc016_collect_winner_events": "8d4a612a64580bf440885cd558f9219db2a75927",
    "rmc016_two_operator_receipts": "e46b9dfcb337bca67af6921fcc3d59a26cc61845",
    "rmc016_resume_verified_receipts": "2ad29a28b93674582359626c2fab0be46d38353c",
    "rmc016_weth_cashflow_audit": "ba76320980627d052d73a5afc26f9ae15140fdcb",
}
AUTHORITIES = {key: False for key in (
    "can_sign", "can_broadcast", "can_spend", "phase_advance_authorized",
    "census_closed", "nqc_execution_proven", "nqc_profitability_proven",
    "canonical_recertification", "current_market_coverage_proven")}
UNKNOWN_FIELDS = (
    "subject_id", "winner_address", "oracle_update_block", "blocks_from_oracle_to_winner",
    "liquidation_bonus_usd_wad", "builder_payment_usd_wad", "winner_gas_usd_wad",
    "other_observed_costs_usd_wad", "observed_winner_net_margin_usd_wad",
    "nqc_realized_pnl_usd_wad")


def need(condition, message):
    if not condition:
        raise ValueError(message)


def same(actual, expected, message):
    need(canonical(actual) == canonical(expected), message)


def fields(value, expected, label):
    need(type(value) is dict, label + "_not_object")
    for key, wanted in expected.items():
        need(key in value, label + "_missing_" + key)
        same(value[key], wanted, label + "_" + key)


def utc(value):
    need(type(value) is str and re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?Z", value), "invalid_time")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def verify_metadata(meta, name, pin):
    """Validate captured producer identity without promoting its authority."""
    p = PINS[name]
    run, commit, artifact = (meta[k] for k in ("run", "commit", "artifact"))
    fields(run, {"id": p["run"], "head_sha": p["commit"], "head_branch": p["branch"],
        "run_attempt": 1, "status": "completed", "conclusion": p["conclusion"],
        "path": p["workflow"], "workflow_id": p["workflow_id"],
        "url": API + f"/actions/runs/{p['run']}"}, "run")
    for key in ("repository", "head_repository"):
        fields(run[key], {"id": SOURCE_ID, "full_name": SOURCE, "private": False}, key)
    fields(run["head_commit"], {"id": p["commit"], "tree_id": p["tree"]}, "head_commit")
    fields(commit, {"sha": p["commit"], "url": API + "/git/commits/" + p["commit"]}, "commit")
    fields(commit["tree"], {"sha": p["tree"]}, "tree")
    fields(artifact, {"id": p["artifact"], "name": p["name"], "expired": False,
        "size_in_bytes": pin["archive_bytes"], "digest": "sha256:" + p["sha256"],
        "url": API + f"/actions/artifacts/{p['artifact']}",
        "archive_download_url": API + f"/actions/artifacts/{p['artifact']}/zip"}, "artifact")
    fields(artifact["workflow_run"], {"id": p["run"], "repository_id": SOURCE_ID,
        "head_repository_id": SOURCE_ID, "head_branch": p["branch"],
        "head_sha": p["commit"]}, "artifact_run")
    need(utc(run["created_at"]) <= utc(run["run_started_at"])
         <= utc(artifact["created_at"]) <= utc(run["updated_at"])
         <= utc(meta["retrieved_at"]) < utc(artifact["expires_at"]), "capture_time_order")
    return {"repository": SOURCE, "repository_id": SOURCE_ID, "run_id": p["run"],
        "run_attempt": 1, "producer_commit": p["commit"], "producer_tree": p["tree"],
        "workflow_conclusion": p["conclusion"], "artifact_id": p["artifact"],
        "artifact_sha256": p["sha256"], "metadata_capture_at": meta["retrieved_at"],
        "authentication_basis": "REVIEWED_RETAINED_API_CAPTURE_NOT_FRESH_QUERY"}


def unpack(raw, manifest):
    need(len(raw) <= MAX_ARCHIVE, "archive_size_limit")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        infos = z.infolist()
        names = [i.filename for i in infos]
        need(len(names) == len(set(names)) and set(names) == set(manifest), "archive_inventory")
        need(not z.comment and sum(i.file_size for i in infos) <= MAX_EXPANDED, "archive_bounds")
        data = {}
        for i in infos:
            need(re.fullmatch(r"[a-zA-Z0-9._-]+", i.filename) and stat.S_ISREG(i.external_attr >> 16)
                 and not i.is_dir() and not i.extra and not i.comment and not i.flag_bits & 1,
                 "unsafe_archive_member")
            need(i.compress_type in (0, 8) and 0 <= i.file_size <= MAX_MEMBER, "member_bounds")
            with z.open(i) as f:
                b = f.read(MAX_MEMBER + 1)
            same(manifest[i.filename], {"bytes": len(b), "sha256": digest(b)}, "member_digest")
            need(len(b) == i.file_size, "member_length")
            data[i.filename] = b
    return data


def original_validator(root=ROOT):
    """Freeze and verify all original imports; never mutate source/sys.modules."""
    raw = {name: read_regular(root / "ci/nqc-census" / (name + ".py")) for name in SOURCE_BLOBS}
    for name, b in raw.items():
        need(git_blob(b) == SOURCE_BLOBS[name], "original_source_changed:" + name)
    modules = {}

    def pinned_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in raw:
            need(level == 0, "relative_pinned_import")
            return load(name)
        return builtins.__import__(name, globals, locals, fromlist, level)

    def load(name):
        if name not in modules:
            module = ModuleType(name)
            module.__file__ = str(root / "ci/nqc-census" / (name + ".py"))
            module.__dict__["__builtins__"] = {**vars(builtins), "__import__": pinned_import}
            modules[name] = module
            exec(compile(raw[name], module.__file__, "exec"), module.__dict__)
        return modules[name]

    return load("rmc016_weth_cashflow_audit")


def load_sources(directory=EVIDENCE, root=ROOT):
    directory, root = Path(directory), Path(root)
    pin_raw = read_regular(directory / "historical-intake-pin.json")
    need(digest(pin_raw) == PIN_SHA256, "intake_pin_changed")
    pin = strict_json(pin_raw)
    need(canonical(pin) == pin_raw, "pin_not_canonical")
    raw, members, provenance = {}, {}, {}
    for name in PINS:
        p = pin["sources"][name]
        raw[name] = read_regular(directory / f"rmc016-{name}.zip", MAX_ARCHIVE)
        need(digest(raw[name]) == p["archive_sha256"] == PINS[name]["sha256"]
             and len(raw[name]) == p["archive_bytes"], "source_archive_changed")
        metadata = read_regular(directory / f"rmc016-{name}-metadata.json")
        need(digest(metadata) == p["metadata_sha256"], "source_metadata_changed")
        provenance[name] = verify_metadata(strict_json(metadata), name, p)
        members[name] = unpack(raw[name], p["members"])
    validator = original_validator(root)
    with tempfile.TemporaryDirectory(prefix="omega-intake-") as tmp:
        files = {name: Path(tmp) / (name + ".zip") for name in raw}
        for name, path in files.items():
            path.write_bytes(raw[name])
        receipts, events, ids = validator.authenticated_drpc_checkpoint(files["receipts"], files["events"])
        legs = validator.reconcile_legs(events, ids, members['legs']['decoded-liquidation-legs.jsonl'],
                    strict_json(members['legs']['decoded-legs-report.json']))
    # Independent strict parsing prevents implicit bool/int and duplicate-key admission.
    for name, files in members.items():
        for filename, b in files.items():
            if filename.endswith(".json"):
                strict_json(b)
            if filename.endswith(".jsonl"):
                for line in b.splitlines():
                    need(canonical(strict_json(line)).rstrip(b"\n") == line, "noncanonical_source_row")
    return receipts, events, ids, provenance, legs


def build_ledger(directory=EVIDENCE, root=ROOT):
    receipts, events, ids, provenance, legs = load_sources(directory, root)
    by_tx = {tx: [] for tx in ids}
    for leg in legs:
        by_tx[leg['transaction_hash']].append(leg)
    rows = []
    for tx in ids:
        r = receipts[tx]
        row = {"transaction_hash": tx, "chain_id": 1, "block_number": r["block_number"],
            "block_hash": r["block_hash"], "transaction_index": r["transaction_index"],
            "events": copy.deepcopy(events[tx]),
            "liquidation_legs": copy.deepcopy(by_tx[tx]),
            "same_asset_gross_deltas": [{
                "log_index": leg['log_index'], "asset": leg['debt_asset'],
                "collateral_minus_debt_raw": str(int(leg['collateral_liquidated_raw'])
                                                   - int(leg['debt_to_cover_raw'])),
                "unit": "TOKEN_BASE_UNITS_NOT_USD_NOT_NET_PROFIT",
            } for leg in by_tx[tx] if leg['debt_asset'] == leg['collateral_asset']],
            "receipt": copy.deepcopy(r), "receipt_operator": "dRPC",
            "event_operator": "Blockscout", "receipt_parity_complete": False,
            "observed_costs_complete": False, **dict.fromkeys(UNKNOWN_FIELDS),
            "nqc_execution": False}
        row["record_commitment_sha256"] = digest(canonical(row))
        rows.append(row)
    report = {"schema": SCHEMA, "scope": "HISTORICAL_SINGLE_RECEIPT_OPERATOR_PARTIAL_LEDGER",
        "source_provenance": provenance, "original_validator_blobs": SOURCE_BLOBS,
        "historical_window": {"chain_id": 1, "start_block": 25880316, "end_block": 26095351},
        "records": rows, "summary": {"event_count": sum(len(r["events"]) for r in rows),
            "transaction_count": len(rows), "receipt_count": len(receipts),
            "decoded_liquidation_leg_count": len(legs),
            "distinct_asset_pair_count": len({(r['collateral_asset'],r['debt_asset']) for r in legs}),
            "same_asset_event_count": sum(r['collateral_asset']==r['debt_asset'] for r in legs),
            "gas_paid_wei": str(sum(int(r["receipt"]["total_gas_paid_wei"]) for r in rows)),
            "gas_accounting_unit": "ONCE_PER_TRANSACTION_NOT_PER_EVENT",
            "known_winner_count": 0, "known_oracle_delay_count": 0,
            "complete_cost_transaction_count": 0,
            "observed_winner_net_margin_usd_wad": None, "nqc_realized_pnl_usd_wad": None},
        "blockers": ["COMPLETE_ECONOMICS_NOT_OBSERVED", "INDEPENDENT_EVENT_COVERAGE_NOT_PROVEN",
            "ORACLE_TO_WINNER_LINKS_MISSING", "POSITION_IDENTITIES_MISSING",
            "SECOND_RECEIPT_OPERATOR_INCOMPLETE", "WINNER_ADDRESSES_MISSING"],
        "new_acquisition_performed": False, "authorities": AUTHORITIES}
    need(report["summary"]["event_count"] == 139 and len(rows) == 127
         and report["summary"]["gas_paid_wei"] == str(GAS_TOTAL), "conservation_failed")
    report["ledger_commitment_sha256"] = digest(canonical(report))
    return report


def verify_ledger(ledger, directory=EVIDENCE, root=ROOT):
    """Recompute from pinned originals, not just a caller's replacement checksum."""
    expected = build_ledger(directory, root)
    same(ledger, expected, "ledger_differs_from_authenticated_sources")
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-directory", type=Path, default=EVIDENCE)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = build_ledger(args.evidence_directory)
        if args.ledger:
            same(strict_json(read_regular(args.ledger, 2 * 1024 * 1024)), result, "ledger_mismatch")
        if args.output:
            with args.output.open("xb") as f:
                f.write(canonical(result))
        print(json.dumps({"status": "HISTORICAL_PARTIAL_LEDGER_VERIFIED", **result["summary"],
            "ledger_commitment_sha256": result["ledger_commitment_sha256"],
            "certified_components": 0, "census_closed": False}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        print(json.dumps({"status": "HISTORICAL_INTAKE_BLOCKED", "reason": str(error),
                          "census_closed": False}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
