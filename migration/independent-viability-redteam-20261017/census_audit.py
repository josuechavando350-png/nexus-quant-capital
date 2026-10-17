#!/usr/bin/env python3
"""Independent, finite, offline audit of pinned Morpho JSON observations.

No network, wallet, signing, transaction construction, imports from Astra, or EVM.
All token amounts remain exact integers. Counts describe saved API observations.
Usage: python3 census_audit.py
Optional: --input-dir PATH --output PATH
Retrieve the immutable URLs in temporal_sources.json externally if input files
are absent; this script never downloads missing data or substitutes current state.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import sys


M = "2026-10-17-monthly/"
P = "2026-10-17-prospective-recovered/"
B_RECEIPT = "2026-10-17-profitability/b-receipt.json"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
MORPHO = "0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb"
LIQ_TOPIC = "0xa4946ede45d0c6f06a0f5ce92c9ad3b4751452d2fe0e25010783bcab57a67e41"
AMOUNTS = ("repaidAssets", "repaidShares", "seizedAssets", "badDebtAssets", "badDebtShares")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def uint(value):
    require(type(value) is int or isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]*", value),
            "Lossy, negative or noncanonical integer")
    n = int(value)
    require(0 <= n < 2**256, "Integer out of uint256 range")
    return n


def hexvalue(value):
    require(isinstance(value, str) and re.fullmatch(r"0x[0-9a-fA-F]+", value), "Invalid hex")
    return int(value, 16)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def micros(iso):
    d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    require(d.tzinfo is not None, "Timezone missing")
    delta = d.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def iso_at(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def ratio(n, d):
    if d == 0:
        return {"numerator": n, "denominator": d, "fraction": None, "percent": None}
    with localcontext() as ctx:
        ctx.prec = 40
        pct = (Decimal(n) * 100 / Decimal(d)).quantize(Decimal("0.000001"))
    return {"numerator": n, "denominator": d, "fraction": str(Fraction(n, d)), "percent": str(pct)}


def key(e):
    return (uint(e["chain"]["id"]), e["txHash"].lower(), uint(e["logIndex"]))


def bad(e):
    return any(uint(e["data"][a]) > 0 for a in ("badDebtAssets", "badDebtShares"))


def day(e):
    return datetime.fromtimestamp(uint(e["timestamp"]), timezone.utc).strftime("%Y-%m-%d")


def normalize(rows, selection):
    normalized = {}
    for row in rows:
        require(row["type"] == "Liquidation" and row["data"]["__typename"] == "MarketTransactionLiquidationData",
                "Unexpected event type")
        require(key(row)[0] == selection["chain_id"], "Unexpected chain")
        require(selection["start_30d"] <= uint(row["timestamp"]) < selection["end_exclusive"], "Outside frozen window")
        for x in ("blockNumber", "txIndex", "logIndex", "timestamp"):
            uint(row[x])
        for x in AMOUNTS:
            uint(row["data"][x])
        uint(row["market"]["lltv"])
        for asset in ("loanAsset", "collateralAsset"):
            a = row["market"][asset]
            require(re.fullmatch(r"0x[0-9a-fA-F]{40}", a["address"]), "Invalid asset address")
            require(uint(a["decimals"]) <= 255, "Invalid decimals")
        require(re.fullmatch(r"0x[0-9a-fA-F]{64}", row["txHash"]), "Invalid txHash")
        require(key(row) not in normalized, "Duplicate event identity")
        normalized[key(row)] = row
    return normalized


def statistics(rows, start, end):
    tx = Counter(e["txHash"].lower() for e in rows)
    liquidators = Counter(e["data"]["liquidator"].lower() for e in rows)
    loan_groups = defaultdict(list)
    collateral_groups = defaultdict(list)
    for e in rows:
        loan_groups[e["market"]["loanAsset"]["address"].lower()].append(e)
        collateral_groups[e["market"]["collateralAsset"]["address"].lower()].append(e)
    loan_assets = []
    for addr, group in sorted(loan_groups.items(), key=lambda it: (-len(it[1]), it[0])):
        meta = {(uint(e["market"]["loanAsset"]["decimals"]), e["market"]["loanAsset"]["symbol"]) for e in group}
        require(len(meta) == 1, "Conflicting debt asset metadata")
        decimals, symbol = next(iter(meta))
        loan_assets.append({"address": addr, "symbol_label": symbol, "decimals": decimals,
                            "events": len(group), "transactions": len({e["txHash"].lower() for e in group}),
                            "bad_debt_events": sum(bad(e) for e in group),
                            "repaid_raw": str(sum(uint(e["data"]["repaidAssets"]) for e in group)),
                            "bad_debt_raw": str(sum(uint(e["data"]["badDebtAssets"]) for e in group)),
                            "share_of_observed_events": ratio(len(group), len(rows)),
                            "usd_value": None, "profit": None})
    daily = {datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"): 0 for t in range(start, end, 86400)}
    daily.update(Counter(day(e) for e in rows))
    per_liquidator = []
    for addr, n in sorted(liquidators.items(), key=lambda it: (-it[1], it[0])):
        group = [e for e in rows if e["data"]["liquidator"].lower() == addr]
        per_liquidator.append({"address": addr, "events": n,
                               "transactions": len({e["txHash"].lower() for e in group}),
                               "bad_debt_events": sum(bad(e) for e in group),
                               "event_share": ratio(n, len(rows))})
    return {"events": len(rows), "transactions": len(tx), "markets": len({e["market"]["marketId"].lower() for e in rows}),
            "liquidator_addresses": len(liquidators), "debt_token_addresses": len(loan_groups),
            "collateral_token_addresses": len(collateral_groups),
            "bad_debt_events": sum(bad(e) for e in rows),
            "transactions_with_any_bad_debt": len({e["txHash"].lower() for e in rows if bad(e)}),
            "debt_assets": loan_assets, "liquidators": per_liquidator,
            "collateral_assets": [{"address": addr,
                "symbol_label": group[0]["market"]["collateralAsset"]["symbol"], "events": len(group),
                "bad_debt_events": sum(bad(e) for e in group)}
                for addr, group in sorted(collateral_groups.items(), key=lambda it: (-len(it[1]), it[0]))],
            "daily_events": daily, "zero_record_days": [d for d, n in daily.items() if n == 0],
            "multi_event_transactions": {h:n for h,n in sorted(tx.items()) if n > 1},
            "sum_does_not_represent_profit": True}


def audit(input_dir):
    def read(path):
        return json.loads((input_dir / path).read_text(encoding="utf-8"))

    manifests = read("source-metadata.json")
    verified = []
    for source in manifests:
        if source.get("source_type") == "web_documentation":
            continue
        raw = (input_dir / source["path"]).read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        require(blob == source["git_blob_sha"], "Git byte mismatch: " + source["path"])
        require(hashlib.sha256(raw).hexdigest() == source["local_sha256"], "SHA256 mismatch: " + source["path"])
        verified.append({"id": source["id"], "path": source["path"], "sha256": source["local_sha256"], "git_blob_sha": blob})

    selection = read(M + "selection.json")
    envelopes = [read(M + f"page-{i:03d}.json") for i in range(3)]
    reverse = [read(M + f"reverse-{i:03d}.json") for i in range(2)]
    seven = read(M + "seven-day.json")

    def items(envelope):
        require(envelope["http_status"] == 200 and "errors" not in envelope["response"], "Failed API envelope")
        return envelope["response"]["data"]["marketTransactions"]["items"]

    rows = [r for env in envelopes for r in items(env)]
    fwd = normalize(rows, selection)
    rev = normalize([r for env in reverse for r in items(env)], selection)
    require(fwd == rev, "Forward/reverse content mismatch")
    require(items(envelopes[-1]) == [], "No terminal forward page")
    require(reverse[0]["response"]["data"]["marketTransactions"]["pageInfo"]["countTotal"] == len(rows), "Initial API count mismatch")
    for env in envelopes + reverse + [seven]:
        require(micros(selection["frozen_at_utc"]) < micros(env["retrieved_at_utc"]), "Selection after response")
    rows7 = [e for e in rows if e["timestamp"] >= selection["start_7d"]]
    require(normalize(items(seven), selection) == normalize(rows7, selection), "Separate seven-day query differs")

    stats30 = statistics(rows, selection["start_30d"], selection["end_exclusive"])
    stats7 = statistics(rows7, selection["start_7d"], selection["end_exclusive"])
    stored = read(M + "monthly-census.json")
    checks = {"forward_reverse_same_records": True, "terminal_forward_page_empty": True,
              "api_initial_count_agrees": True, "seven_day_subset_same_records": True,
              "selection_saved_before_api_responses": True, "all_input_copy_hashes_match": True,
              "source_json_amounts_strict_integer": True}
    for win, own in (("30d", stats30), ("7d", stats7)):
        for own_key, saved_key in (("events", "observed_events"), ("transactions", "observed_transactions"),
                                   ("markets", "observed_markets"), ("liquidator_addresses", "observed_liquidator_addresses")):
            require(own[own_key] == stored["windows"][win][saved_key], "Saved report total differs")
    checks["totals_independently_recomputed_agree_with_saved_report"] = True

    tx_counts = Counter(e["txHash"].lower() for e in rows)
    first_per_asset = {}
    reasons = defaultdict(set)
    for e in sorted(rows, key=lambda e: (e["timestamp"], e["txHash"].lower(), e["logIndex"])):
        addr = e["market"]["loanAsset"]["address"].lower()
        h = e["txHash"].lower()
        if addr not in first_per_asset:
            first_per_asset[addr] = h
            reasons[h].add("first chronological event per debt-token address")
        if addr == WETH:
            reasons[h].add("all WETH-debt transactions")
        if tx_counts[h] > 1:
            reasons[h].add("all transactions with multiple liquidation events")
    receipt_selection = read(M + "receipt-selection.json")
    saved_reasons = {r["tx_hash"].lower(): set(r["reasons"]) for r in receipt_selection["transactions"]}
    require(saved_reasons == dict(reasons), "Diagnostic selection is not exactly the declared rule")
    checks["diagnostic_selection_independently_rederived"] = True
    nulls = []
    for f in sorted((input_dir / M).glob("receipt-[0-9][0-9].json")):
        env = json.loads(f.read_text())
        require(env["request"]["method"] == "eth_getTransactionReceipt", "Wrong receipt method")
        h = env["request"]["params"][0].lower()
        require(h in saved_reasons and h not in nulls, "Unselected/duplicated receipt")
        require(env["http_status"] == 200 and env["response"]["result"] is None, "Unexpected receipt outcome")
        require(micros(receipt_selection["frozen_at_utc"]) < micros(env["retrieved_at_utc"]), "Receipt selected retrospectively")
        nulls.append(h)
    b_env = read(B_RECEIPT)
    b = b_env["response"]["result"]
    b_hash = b["transactionHash"].lower()
    require(set(nulls) | {b_hash} == set(saved_reasons) and b_hash not in nulls, "Incomplete receipt accounting")
    b_rows = [e for e in rows if e["txHash"].lower() == b_hash]
    control = read(M + "b-morpho-logs.json")
    require(control["request"]["method"] == "eth_getLogs", "Wrong control method")
    params = control["request"]["params"][0]
    matching = [l for l in b["logs"] if l["address"].lower() == MORPHO and l["topics"][0] == LIQ_TOPIC]
    require(len(matching) == len(b_rows) == 1, "Unexpected B event multiplicity")
    log, event = matching[0], b_rows[0]
    require(params["blockHash"] == b["blockHash"] == log["blockHash"] and params["address"].lower() == MORPHO
            and params["topics"] == [LIQ_TOPIC], "Control does not cover known positive")
    require(hexvalue(log["logIndex"]) == event["logIndex"] and hexvalue(b["blockNumber"]) == event["blockNumber"], "B identity differs")
    words = [int(log["data"][2:][i:i+64], 16) for i in range(0, len(log["data"])-2, 64)]
    require(len(words) == 5 and words == [uint(event["data"][a]) for a in AMOUNTS], "B amounts differ")
    require(log["topics"][1].lower() == event["market"]["marketId"].lower(), "B market differs")
    require("0x" + log["topics"][2][-40:] == event["data"]["liquidator"].lower(), "B liquidator differs")
    require(control["http_status"] == 200 and control["response"]["result"] == [], "Control not empty")
    checks["b_saved_receipt_matches_api_identity_and_amounts"] = True
    checks["getlogs_control_matches_known_positive_scope_but_is_empty"] = True

    bad_tx = {e["txHash"].lower() for e in rows if bad(e)}
    filters = {}
    for name, filtered in (
        ("all_records", rows),
        ("only_events_without_reported_bad_debt", [e for e in rows if not bad(e)]),
        ("remove_entire_transactions_with_any_bad_debt", [e for e in rows if e["txHash"].lower() not in bad_tx]),
        ("diagnostic_receipt_selection", [e for e in rows if e["txHash"].lower() in saved_reasons]),
        ("WETH_debt", [e for e in rows if e["market"]["loanAsset"]["address"].lower() == WETH]),
        ("WETH_debt_without_reported_bad_debt", [e for e in rows if e["market"]["loanAsset"]["address"].lower() == WETH and not bad(e)]),
        ("without_2026_09_26_for_sensitivity_only", [e for e in rows if day(e) != "2026-09-26"])):
        filters[name] = {"events": len(filtered), "transactions": len({e["txHash"].lower() for e in filtered}),
                         "bad_debt_events": sum(bad(e) for e in filtered), "eligible_count": None, "profit_positive_count": None}

    series = {}
    required_receipts = []
    for name in ("market", "position", "oracle"):
        env = read(P + "sample-00/" + name + ".json")
        height = uint(env["response"]["data"]["last_indexed_block"])
        header = read(P + f"sample-00/header-{height}.json")
        block = header["response"]["result"]
        require(hexvalue(block["number"]) == height, "Header height mismatch")
        required_receipts += [env["received_at_utc"], header["received_at_utc"]]
        series[name] = {"reported_block": height, "header_hash_saved": block["hash"],
                        "block_timestamp_seconds": hexvalue(block["timestamp"]),
                        "request_start_utc": env["started_at_utc"], "response_received_utc": env["received_at_utc"],
                        "header_received_utc": header["received_at_utc"],
                        "wall_clock_request_elapsed_us": micros(env["received_at_utc"])-micros(env["started_at_utc"]),
                        "block_to_response_wall_offset_us": micros(env["received_at_utc"])-hexvalue(block["timestamp"])*1_000_000,
                        "network_latency_us": None, "monotonic_duration_us": None,
                        "provider_publication_time": None, "utc_offset_uncertainty_us": None,
                        "state_authenticated_against_root": False, "finality_verified": False}
    config = read(P + "sample-00/config.json")
    required_receipts.append(config["received_at_utc"])
    completed = max(required_receipts, key=micros)
    require(micros(completed) == micros(read(P + "final-prospective.json")["complete_data_received_at_utc"]), "Completion time differs")
    checks["complete_data_time_includes_last_header"] = True
    follow_selection = read(P + "followup-selection.json")
    follow = read(P + "followup-events.json")
    follow_records = items(follow)
    interval_start = follow_selection["start_inclusive"] * 1_000_000
    interval_end = follow_selection["end_exclusive"] * 1_000_000
    temporal = {"observations": series, "complete_data_received_utc": completed,
                "state_blocks_equal": len({x["reported_block"] for x in series.values()}) == 1,
                "liquidatability": None, "time_eligible": None,
                "classification": "TEMPORALIDAD_NO_DEMOSTRADA",
                "followup": {"start_inclusive_utc": iso_at(follow_selection["start_inclusive"]),
                    "end_exclusive_utc": iso_at(follow_selection["end_exclusive"]),
                    "interval_us": interval_end-interval_start, "returned_records": len(follow_records),
                    "selection_saved_utc": follow_selection["saved_at_utc"],
                    "selection_before_request": micros(follow_selection["saved_at_utc"]) < micros(follow["started_at_utc"]),
                    "selection_before_interval_start": micros(follow_selection["saved_at_utc"]) < interval_start,
                    "selection_after_interval_end_us": micros(follow_selection["saved_at_utc"])-interval_end,
                    "complete_data_after_interval_start_us": micros(completed)-interval_start,
                    "time_remaining_in_window_after_all_inputs_us": interval_end-micros(completed),
                    "absence_of_onchain_events_proved": False,
                    "indexing_delay_bound": None, "frequency_estimate": None}}

    peak = max(stats30["daily_events"], key=stats30["daily_events"].get)
    peak_rows = [e for e in rows if day(e) == peak]
    leader = stats30["liquidators"][0]
    leader_rows = [e for e in rows if e["data"]["liquidator"].lower() == leader["address"]]
    derived = {"peak_day": peak, "peak_day_events": len(peak_rows),
               "peak_day_bad_debt_events": sum(bad(e) for e in peak_rows),
               "peak_day_fraction_of_bad_debt": ratio(sum(bad(e) for e in peak_rows), stats30["bad_debt_events"]),
               "leader_address": leader["address"], "leader_all_bad_debt": all(bad(e) for e in leader_rows),
               "leader_event_dates": sorted({day(e) for e in leader_rows}),
               "leader_collateral_tokens": sorted({e["market"]["collateralAsset"]["address"].lower() for e in leader_rows}),
               "top_two_liquidator_event_share": ratio(sum(x["events"] for x in stats30["liquidators"][:2]), len(rows)),
               "bad_debt_event_share": ratio(stats30["bad_debt_events"], len(rows))}

    funnel = [{"layer": 1, "label": "Eventos observados", "events": len(rows), "transactions": stats30["transactions"],
               "chain_population_complete": False}]
    for i, label in enumerate(("Estados auténticos reproducidos", "Rutas ejecutables", "P&L completo positivo",
                               "Financiación sin recurso", "Acceso previo e inclusión ganable"), 2):
        funnel.append({"layer": i, "label": label, "population_count": None,
                       "population_count_label": "DESCONOCIDO", "certified_nqc_operations": 0,
                       "zero_certifications_proves_nonexistence": False})

    return {"schema": 1, "analysis": "Independent offline recomputation; no onchain authentication or economic forecast",
            "source_commit": "0f26557c1f83e12efcf364ece6cebd8505d2e2c2", "inputs": verified,
            "record_set_sha256": hashlib.sha256(canonical([fwd[k] for k in sorted(fwd)])).hexdigest(),
            "checks": checks, "windows": {"30d": stats30, "7d": stats7},
            "window_overlap_warning": "7d is a subset of 30d; never add these populations",
            "filter_sensitivity": filters, "concentration_findings": derived,
            "diagnostic_receipts": {"selected_transactions": len(saved_reasons), "selected_events": filters["diagnostic_receipt_selection"]["events"],
                "available_saved_receipts": 1, "new_null_receipts": len(nulls),
                "selection_is_random": False, "null_is_failed_transaction": False, "null_is_zero_gas": False,
                "null_fraction_of_diagnostic_transactions": ratio(len(nulls),len(saved_reasons)),
                "available_fraction_of_all_observed_transactions": ratio(1,stats30["transactions"]),
                "b_gas_units": hexvalue(b["gasUsed"]), "b_effective_gas_price_wei": str(hexvalue(b["effectiveGasPrice"])),
                "b_gas_wei": str(hexvalue(b["gasUsed"])*hexvalue(b["effectiveGasPrice"])), "population_profit_distribution": None},
            "coverage_control": {"status": "KNOWN_POSITIVE_OMISSION_OR_CONFLICT", "saved_receipt_matching_events": len(matching),
                "saved_getlogs_events": len(control["response"]["result"]), "can_certify_complete_population": False,
                "claim_boundary": "Conflict between pinned saved provider outputs, not a new chain query"},
            "temporal": temporal, "six_layer_funnel": funnel,
            "bound": {"form": "sum of nonnegative assumed upper margins for a fixed observed transaction set",
                "homogeneous_example": "T <= N*m_max - F - L is necessary under the explicitly stated closed-set assumptions",
                "N_in_observed_set": stats30["transactions"], "m_max_measured": None, "F_measured": None, "L_measured": None,
                "forecast": False},
            "economic_admission": "UNKNOWN_NOT_TRUE", "realized_nqc_profit_certifications": 0,
            "network_calls_performed_by_this_script": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve().parent
    parser.add_argument("--input-dir", default=here / "evidence" / "census_inputs", type=Path)
    parser.add_argument("--output", default=here / "evidence" / "census_audit_results.json", type=Path)
    args = parser.parse_args()
    result = audit(args.input_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"audit": "PASS_OFFLINE_RECOMPUTATION", "checks_passed": len(result["checks"]),
                      "input_git_blobs_verified": len(result["inputs"]), "events": result["windows"]["30d"]["events"],
                      "transactions": result["windows"]["30d"]["transactions"],
                      "temporal_classification": result["temporal"]["classification"],
                      "economic_admission": result["economic_admission"], "network_calls": 0}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, FileNotFoundError, json.JSONDecodeError) as exc:
        print("AUDIT_FAILED: " + str(exc), file=sys.stderr)
        sys.exit(1)
