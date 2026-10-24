#!/usr/bin/env python3
"""Offline, exact-integer Ethereum fee measurements linked to a verified journal.

Blockscout is auxiliary indexer evidence, never a receipt proof or an admission
gate. Transaction costs are stored once, not once per liquidation log. Missing
membership, prices, eligibility, traces and economic outcomes remain unknown.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from archive_collection import new_json, sync_dir
from export_parquet import (
    ExportError, _bounded_read, _check_path, _copy_bounded, _envelopes,
    _file_sha, _json, _owner, _sha, export_journal,
)

INPUT_SCHEMA = "nqc-miner-blockscout-fee-input-v1"
OUTPUT_SCHEMA = "nqc-miner-gas-measurement-v1"
MAX_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 10_000
MAX_CALLS = 256


def require(condition, reason):
    if not condition:
        raise ExportError(reason)


def obj(value):
    require(isinstance(value, dict), "expected object")
    return value


def integer(value, *, maximum=(1 << 64) - 1):
    require(type(value) is int and 0 <= value <= maximum, "invalid unsigned integer")
    return value


def decimal(value):
    require(isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]{0,77}", value) is not None,
            "fee quantity must be a canonical decimal string")
    result = int(value)
    require(result < 1 << 256, "fee quantity exceeds uint256")
    return result


def hash32(value):
    require(isinstance(value, str) and re.fullmatch(r"0x[0-9a-f]{64}", value) is not None,
            "invalid canonical hash")
    return value


def timestamp(value):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.0{1,6})?Z", value) is not None,
            "timestamp must be an integral UTC second")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ExportError("invalid timestamp") from error
    return int((dt - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds())


def index_calls(bundle, data_class):
    expected = {"schema", "namespace", "producer", "data_class", "source", "server_version", "calls"}
    require(set(obj(bundle)) == expected and bundle["schema"] == INPUT_SCHEMA
            and bundle["namespace"] == "nqc_miner_v1" and bundle["producer"] == "nqc-miner"
            and bundle["data_class"] == data_class and bundle["source"] == "blockscout-mcp"
            and bundle["server_version"] == "0.19.0", "foreign or unsupported fee input")
    require(isinstance(bundle["calls"], list) and len(bundle["calls"]) <= MAX_CALLS, "too many source calls")
    transactions, blocks = {}, {}
    for call in bundle["calls"]:
        require(set(obj(call)) == {"tool", "params", "response"}, "unexpected call fields")
        params = obj(call["params"])
        response = obj(call["response"])
        data = obj(response.get("data"))
        require(response.get("pagination") is None, "paginated response is not a scalar fee observation")
        if call["tool"] == "get_transaction_info":
            require(set(params) == {"chain_id", "transaction_hash"}, "unexpected transaction request")
            key = hash32(params["transaction_hash"])
            dest = transactions
            if "hash" in data:
                require(data["hash"] == key, "transaction response identity mismatch")
        elif call["tool"] == "get_block_info":
            require(set(params) == {"chain_id", "number_or_hash", "include_transactions"}
                    and params["include_transactions"] is True, "block membership must be requested")
            key = hash32(params["number_or_hash"])
            require(obj(data.get("block_details")).get("hash") == key, "block response identity mismatch")
            dest = blocks
        else:
            raise ExportError("unsupported source tool")
        require(params["chain_id"] == "1", "only Ethereum mainnet fee semantics are supported")
        require(key not in dest, "duplicate source request")
        dest[key] = data
    return transactions, blocks


def transaction_measurement(events, tx, block):
    """Validate indexer fields against canonical event locations, then measure."""
    first = events[0]
    log = first["log"]
    reference = {"chain_id": log["chain_id"], "block_hash": log["block_hash"],
                 "transaction_hash": log["transaction_hash"]}
    result = {**reference, "block_number": log["block_number"],
              "block_timestamp": first["block_timestamp"], "event_count": len(events),
              "status": "missing_source", "native_currency": "ETH" if log["chain_id"] == 1 else None,
              "execution_gas_used": None, "effective_gas_price_wei": None,
              "execution_fee_wei": None, "base_fee_burn_wei": None, "priority_fee_wei": None,
              "direct_builder_payment_wei": None, "fee_microusd": None,
              "gas_allocation_to_events": None, "net_profit_microusd": None}
    require(all(e["log"]["block_hash"] == log["block_hash"]
                and e["log"]["block_number"] == log["block_number"]
                and e["block_timestamp"] == first["block_timestamp"] for e in events),
            "conflicting transaction location")
    if log["chain_id"] != 1:
        result["status"] = "unsupported_chain"
        return result
    if tx is None or block is None:
        return result
    details = obj(block.get("block_details"))
    if "block_hash" in tx:
        require(tx["block_hash"] == log["block_hash"], "transaction block hash mismatch")
    require(details.get("hash") == log["block_hash"]
            and integer(details.get("height")) == log["block_number"]
            and integer(tx.get("block_number")) == log["block_number"], "block location mismatch")
    require(timestamp(details.get("timestamp")) == first["block_timestamp"]
            and timestamp(tx.get("timestamp")) == first["block_timestamp"], "block timestamp mismatch")
    require(details.get("type") == "block" and details.get("is_pending_update") is False
            and tx.get("is_pending_update") is False, "pending or noncanonical indexer observation")
    require(tx.get("result") == "success" and tx.get("status") == "ok", "failed transaction cannot contain liquidation")
    count = integer(details.get("transactions_count"))
    position = integer(tx.get("position"))
    require(position < count, "transaction position exceeds block")
    members = block.get("transaction_hashes")
    require(isinstance(members, list) and len(members) <= count
            and len(members) <= 100_000, "invalid block membership list")
    require(len({hash32(h) for h in members}) == len(members), "duplicate block membership")
    if log["transaction_hash"] not in members:
        require(len(members) < count, "complete block excludes transaction")
        result["status"] = "membership_not_returned"
        return result
    # A partial list proves presence only; absence never proves non-inclusion.
    # No assumption that a returned page starts at transaction index zero.
    tx_type = integer(tx.get("type"), maximum=255)
    if tx_type != 2:
        result["status"] = "unsupported_transaction_type"
        return result
    gas = decimal(tx.get("gas_used"))
    limit = decimal(tx.get("gas_limit"))
    price = decimal(tx.get("gas_price"))
    base = decimal(details.get("base_fee_per_gas"))
    cap = decimal(tx.get("max_fee_per_gas"))
    tip_cap = decimal(tx.get("max_priority_fee_per_gas"))
    require(0 < gas <= limit <= decimal(details.get("gas_limit")), "invalid execution gas")
    require(gas <= decimal(details.get("gas_used")), "transaction gas exceeds block gas")
    require(decimal(tx.get("base_fee_per_gas")) == base and cap >= base and tip_cap <= cap
            and price == base + min(tip_cap, cap - base), "effective fee does not match EIP-1559 caps")
    fee = gas * price
    burn = gas * base
    priority = fee - burn
    require(fee < 1 << 256, "execution fee exceeds uint256")
    actual = obj(tx.get("fee"))
    require(actual.get("type") == "actual" and decimal(actual.get("value")) == fee
            and decimal(tx.get("transaction_burnt_fee")) == burn
            and decimal(tx.get("priority_fee")) == priority, "fee accounting mismatch")
    # Reject schema drift that could add a separate fee to this supported type.
    require(all(tx.get(k) is None for k in ("l1_fee", "blob_gas_used", "blob_gas_price")),
            "additional fee model requires an explicit adapter")
    result.update(status="auxiliary_measured", execution_gas_used=str(gas),
                  effective_gas_price_wei=str(price), execution_fee_wei=str(fee),
                  base_fee_burn_wei=str(burn), priority_fee_wei=str(priority))
    return result


def measure(state: Path, evidence: Path, output: Path, verifier: Path):
    state, evidence = _check_path(state), _check_path(evidence)
    output = _check_path(output, must_exist=False)
    require(not output.exists() and state != output and state not in output.parents
            and output not in state.parents and output not in evidence.parents,
            "output must be new and outside source inputs")
    owner = _owner(_json(_bounded_read(state / "owner.json", 65536)))
    require(owner["data_class"] in {"historical", "synthetic"}, "retrospective measurement cannot admit Shadow")
    require(not owner["run_id"].startswith("window-") and not (state / "collector.json").exists(),
            "collection windows require parent revocation verification; use standalone capture")
    output.mkdir(mode=0o700)
    source_copy = _copy_bounded(evidence, output / "source-evidence.json", MAX_BYTES)
    bundle = _json(_bounded_read(output / "source-evidence.json", MAX_BYTES))
    txs, blocks = index_calls(bundle, owner["data_class"])
    exported = export_journal(state, output / "verified-export", verifier,
                              maximum_bytes=MAX_BYTES, maximum_records=MAX_RECORDS)
    require(exported["owner"] == owner, "journal owner changed")
    source = output / "verified-export" / "source"
    verification = _json(_bounded_read(output / "verified-export" / "verification.json", 65536))
    config = _json(_bounded_read(source / "config.json", 1048576))
    require(verification["completed_scopes"] == len(config["scopes"])
            and verification["provisional_events"] == 0 and verification["invalidated_events"] == 0
            and not verification["invalidated_from"], "measurement requires complete unrevoked scopes")
    groups, event_rows, seen = {}, [], set()
    observed = 0
    for raw, envelope in _envelopes(source / "events.jsonl", MAX_RECORDS):
        record = envelope["record"]
        if record["kind"] != "observed":
            continue
        observed += 1
        if record["decoded"]["kind"] != "liquidation":
            continue
        log = record["log"]
        key = (log["chain_id"], log["transaction_hash"], log["log_index"])
        require(key not in seen, "duplicate liquidation event")
        seen.add(key)
        groups.setdefault(key[:2], []).append(record)
        event_rows.append({"identity": record["decoded"]["payload"]["identity"],
                           "scope_id": record["scope_id"], "sequence": envelope["sequence"],
                           "source_line_sha256": _sha(raw), "market_id": record["decoded"]["payload"]["market_id"],
                           "first_eligible_block": None, "gross_bonus_microusd": None,
                           "direct_builder_payment_microusd": None, "net_profit_microusd": None})
    require(observed == verification["canonical_events"], "canonical count mismatch")
    used_txs = {tx for (chain, tx) in groups if chain == 1}
    used_blocks = {e["log"]["block_hash"] for key, events in groups.items() if key[0] == 1 for e in events}
    require(set(txs) <= used_txs and set(blocks) <= used_blocks, "source includes unrelated transactions or blocks")
    transactions = [transaction_measurement(events, txs.get(key[1]), blocks.get(events[0]["log"]["block_hash"]))
                    for key, events in sorted(groups.items())]
    measured = [t for t in transactions if t["status"] == "auxiliary_measured"]
    report = {"schema": OUTPUT_SCHEMA, "namespace": "nqc_miner_v1", "producer": "nqc-miner",
              "owner": owner, "data_class": owner["data_class"], "events": event_rows,
              "transactions": transactions, "canonical_liquidations": len(event_rows),
              "unique_transactions": len(transactions), "measured_transactions": len(measured),
              "measured_execution_fee_wei": str(sum(int(t["execution_fee_wei"]) for t in measured)) if measured else None,
              "aggregate_scope": "measured Ethereum transactions only; each counted once",
              "all_transaction_fees_measured": bool(transactions) and len(measured) == len(transactions),
              "source_scope_count": len(config["scopes"]), "auxiliary_only": True,
              "authenticity_verified": False, "event_logs_rechecked_by_auxiliary_source": False,
              "complete_economic_measurement": False, "economic_certification": False,
              "activation_allowed": False, "observer_bridge_enabled": False}
    new_json(output / "measurement.json", report)
    for entry in exported["source_files"]:
        require(_file_sha(source / entry["file"], MAX_BYTES) == entry["sha256"], "source changed during measurement")
    require(_file_sha(output / "source-evidence.json", MAX_BYTES) == source_copy["sha256"], "fee evidence changed")
    manifest = {"schema": OUTPUT_SCHEMA, "namespace": "nqc_miner_v1", "producer": "nqc-miner",
                "source_evidence": source_copy, "verified_export_manifest_sha256": _file_sha(output / "verified-export" / "manifest.json", MAX_BYTES),
                "measurement_sha256": _file_sha(output / "measurement.json", MAX_BYTES),
                "implementation_sha256": _file_sha(Path(__file__), MAX_BYTES),
                "complete": True, "complete_economic_measurement": False}
    new_json(output / "manifest.json", manifest)
    sync_dir(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("state", "evidence", "output", "verifier"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    try:
        report = measure(args.state, args.evidence, args.output, args.verifier)
    except (ExportError, OSError, KeyError, TypeError) as error:
        parser.exit(1, f"nqc-miner fee measurement rejected: {error}\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
