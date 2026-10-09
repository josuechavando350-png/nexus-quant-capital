#!/usr/bin/env python3
"""Offline, source-bound competitor cost evidence. Never an NQC admission gate.

All 127 archived winners remain insufficient evidence. Receipt gas is counted
once per transaction; unobserved costs are null, not zero. Flash logs are a
historical observation, not permission, funding capacity or a balance proof.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re

from verify_winner_recovery import (
    PINS, archive, canonical, need, parse, rpc_records, sha, transport,
    authenticated_drpc_checkpoint, receipt_normalized, PROVIDERS,
)
from rmc016_aave_event_legs import decode, POOL, TOPIC
from rmc016_weth_cashflow_audit import WETH, reconcile_legs
from typed_observation_vectors import keccak256

HERE = Path(__file__).resolve().parent
HASH = re.compile(r"0x[0-9a-f]{64}\Z")
ADDRESS = re.compile(r"0x[0-9a-f]{40}\Z")
HEXQ = re.compile(r"0x(?:0|[1-9a-f][0-9a-f]*)\Z")
WORD = re.compile(r"[0-9a-f]{64}\Z")
BALANCER = "0xba12222222228d8ba445958a75a0704d566bf2c8"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
AAVE_FLASH = "0xefefaba5e921573100900a3ad9cf29f222d995fb3b6045797eaea7521bd8d6f0"
BALANCER_FLASH = "0x0d7d75e01ab95780d3cd1c8ec0dd6c2ce19e3a20427eec8bf53283b6fb8e95f0"
RPC_PINS = {
    "blockpi": (123, "6b5c7f5789b99e6afb00a1b3b3a5c4ab4c638d6b1101dab70c4dc5751eb42129"),
    "drpc": (87, "3c0da0c9a317306796f9e9b925abcd483b66b5d91c29a2526de830c2c3f3343e"),
}
UNKNOWN_COSTS = {
    "liquidation_protocol_fee": "RECONCILE_DEPLOYED_LOGIC_AND_TREASURY_TRANSFERS_AVOID_DOUBLE_SUBTRACTION",
    "complete_flash_fees": "DECODED_AAVE_BALANCER_EVENTS_ARE_NOT_ALL_FINANCING_ROUTES",
    "swap_fees": "REPLAY_ROUTE_AND_POOL_STATE_AVOID_DOUBLE_COUNTING_REALIZED_OUTPUT",
    "slippage_price_impact": "BIND_DECISION_TIME_QUOTE_AND_ACTUAL_ROUTE_OUTPUT",
    "builder_mev_payment": "RECONCILE_NATIVE_TRACES_COINBASE_TRANSFERS_AND_OFFCHAIN_PAYMENTS",
    "financier_payment": "AUTHENTICATE_AGREEMENT_AND_SETTLEMENT",
    "hedging_inventory_conversion": "RECONCILE_BALANCES_CONVERSIONS_AND_COST_BASIS",
    "attributed_failed_transactions": "RECOVER_FAILED_CENSORED_AND_DROPPED_TRANSACTION_UNIVERSE",
    "infrastructure": "AUTHENTICATE_ATTRIBUTABLE_COST_RECORDS",
    "other_costs_and_liabilities": "RECONCILE_COMPLETE_OBLIGATIONS_AND_COST_SCOPE",
}
GAPS = {
    "PRESTATE": "EXACT_TRANSACTION_PRESTATE_AND_DEPLOYED_CODE_PARITY_UNPROVEN",
    "CAPITAL": "NQC_EXTERNAL_PRINCIPAL_FEES_AND_OBLIGATIONS_UNAUTHENTICATED",
    "GAS": "NQC_GAS_BALANCE_COST_BASIS_AND_EXECUTOR_PERMISSION_UNAUTHENTICATED",
    "COSTS": "COMPLETE_COSTS_ROUTES_AND_TOKEN_BALANCES_UNRECONCILED",
    "CAPTURE": "COMPETITION_AND_NQC_INCLUSION_UNCALIBRATED",
    "TIME": "ORIGINAL_DECISION_TIME_OBSERVATION_UNPROVEN",
}


def abi_binding():
    directory = HERE/"evidence/economics/abi"
    doc = parse((directory/"sources.json").read_bytes())
    expected = {
        "aave-interface.sol.txt": "d708ba2c3cf29fe81083b7b8127ef61b7d750dc017399ebaa2951d6f61a93dda",
        "balancer-interface.sol.txt": "95ff30b5a5a72ec7287a734738231422e4688052daeab0a18f2a2a6129f0300a",
    }
    need({s["file"] for s in doc["sources"]} == set(expected) and len(doc["sources"]) == 2,
         "ABI reference inventory drift")
    for source in doc["sources"]:
        raw = (directory/source["file"]).read_bytes()
        need(sha(raw) == expected[source["file"]] == source["sha256"] and len(raw) == source["bytes"],
             "ABI reference bytes drift")
    for signature, topic in (
        ("FlashLoan(address,address,address,uint256,uint8,uint256,uint16)", AAVE_FLASH),
        ("FlashLoan(address,address,uint256,uint256)", BALANCER_FLASH),
        ("Transfer(address,address,uint256)", TRANSFER),
    ):
        need("0x" + keccak256(signature.encode()).hex() == topic, "event signature hash mismatch")
    return doc


def quantity(x):
    need(type(x) is str and HEXQ.fullmatch(x) is not None, "invalid canonical hex quantity")
    n = int(x, 16)
    need(n < 2**256, "quantity over uint256")
    return n


def address_word(x):
    need(type(x) is str and WORD.fullmatch(x) and x[:24] == "0" * 24,
         "noncanonical ABI address padding")
    return "0x" + x[24:]


def semantic_receipt(raw, normalized):
    """Bind every log, including non-liquidation logs, before interpreting it."""
    need(type(raw.get("logs")) is list, "receipt logs missing")
    for key in ("from", "to"):
        need(type(raw.get(key)) is str and ADDRESS.fullmatch(raw[key]), "receipt actor malformed")
    logs, last = [], -1
    for log in raw["logs"]:
        need(type(log) is dict and type(log.get("address")) is str
             and ADDRESS.fullmatch(log["address"]), "log emitter malformed")
        need(log.get("transactionHash") == normalized["transaction_hash"]
             and log.get("blockHash") == normalized["block_hash"]
             and quantity(log.get("blockNumber")) == normalized["block_number"]
             and quantity(log.get("transactionIndex")) == normalized["transaction_index"]
             and log.get("removed") is False, "log identity or reorg mismatch")
        index = quantity(log.get("logIndex"))
        need(index > last, "duplicate or out-of-order log")
        last = index
        topics = log.get("topics")
        need(type(topics) is list and len(topics) <= 4
             and all(type(t) is str and HASH.fullmatch(t) for t in topics), "log topic shape")
        data = log.get("data")
        need(type(data) is str and re.fullmatch(r"0x(?:[0-9a-f]{2})*", data), "log data shape")
        # Optional provider-added blockTimestamp is not part of the EVM log.
        logs.append({k: log[k] for k in ("address", "topics", "data", "blockNumber", "blockHash",
                                       "transactionHash", "transactionIndex", "logIndex", "removed")})
    return {"from": raw["from"], "to": raw["to"], "receipt": normalized, "logs": logs}


def flash_event(log):
    topics = log["topics"]
    if not topics:
        return None
    if (log["address"], topics[0]) not in ((POOL, AAVE_FLASH), (BALANCER, BALANCER_FLASH)):
        return None
    aave = log["address"] == POOL
    count = 4 if aave else 2
    need(len(topics) == (4 if aave else 3) and len(log["data"]) == 2 + 64 * count,
         "recognized flash event malformed")
    words = [log["data"][2+i*64:2+(i+1)*64] for i in range(count)]
    need(all(WORD.fullmatch(w) for w in words), "flash data malformed")
    receiver, token = address_word(topics[1][2:]), address_word(topics[2][2:])
    if aave:
        initiator = address_word(words[0])
        amount, mode, fee = (int(words[n], 16) for n in (1, 2, 3))
        referral = int(topics[3], 16)
        need(mode in (0, 1, 2) and referral < 2**16, "flash enum/referral outside ABI domain")
    else:
        initiator, mode, referral = None, None, None
        amount, fee = map(lambda w: int(w, 16), words)
    return {"transaction_hash": log["transactionHash"], "block_hash": log["blockHash"],
            "block_number": quantity(log["blockNumber"]), "log_index": quantity(log["logIndex"]),
            "protocol": "AAVE_V3" if aave else "BALANCER_V2", "emitter": log["address"],
            "receiver": receiver, "initiator": initiator, "asset": token,
            "principal_raw": str(amount), "event_fee_raw": str(fee),
            "interest_rate_mode": mode, "referral_code": referral,
            "scope": "DECODED_EVENT_NOT_BALANCE_OR_NQC_FUNDING_PROOF",
            "log_sha256": sha(canonical(log))}


def token_flows(logs):
    """ERC20-shaped log deltas by actor/token; never balance deltas or profit."""
    totals, count, ambiguous = defaultdict(int), 0, 0
    for log in logs:
        topics = log["topics"]
        if not topics or topics[0] != TRANSFER:
            continue
        if len(topics) != 3 or len(log["data"]) != 66:
            ambiguous += 1  # E.g. ERC721 shares this signature, different ABI.
            continue
        sender, recipient = address_word(topics[1][2:]), address_word(topics[2][2:])
        amount = int(log["data"][2:], 16)
        totals[(sender, log["address"])] -= amount
        totals[(recipient, log["address"])] += amount
        count += 1
    return totals, count, ambiguous


def sources(archive_root, metadata, rpc_root):
    contents, refs = {}, []
    for pin in PINS:
        path = archive_root / pin[2]
        refs.append(transport(pin, parse((metadata/f"{pin[0]}.json").read_bytes()), path.read_bytes()))
        contents[pin[2]] = archive(path)
    receipts, events, ids = authenticated_drpc_checkpoint(
        archive_root/"winner-receipts-partial-original.zip", archive_root/"winner-events-original.zip")
    legs = reconcile_legs(events, ids, contents["winner-legs-original.zip"]["decoded-liquidation-legs.jsonl"],
                          parse(contents["winner-legs-original.zip"]["decoded-legs-report.json"]))
    leg_lookup = {(x["transaction_hash"], x["log_index"]): x for x in legs}
    observed, witnesses, manifests = defaultdict(dict), defaultdict(list), []
    for provider, (expected_count, expected_hash) in RPC_PINS.items():
        directory = rpc_root/f"historical-rpc-{provider}-receipts-resumed"
        need(sha((directory/"manifest.json").read_bytes()) == expected_hash, "raw RPC manifest pin drift")
        records = rpc_records(directory, allow_partial=True)
        need(len(records) == expected_count + 1 and records[-1][0]["status"] == "FAILED",
             "partial acquisition boundary drift")
        operator = next(p for p in PROVIDERS if p[0] == provider)
        seen = []
        for row, request, raw in records:
            need(row["provider_id"] == provider and row["operator"] == operator[1]
                 and row["url"] == operator[2] and request["method"] == "eth_getTransactionReceipt"
                 and len(request["params"]) == 1, "RPC provenance/method mismatch")
            if raw is None:
                continue
            tx = request["params"][0]
            need(tx in receipts and tx not in seen, "receipt outside source or duplicated")
            seen.append(tx)
            rec = receipt_normalized(tx, events[tx], raw)
            need(rec == receipts[tx], "raw receipt/checkpoint mismatch")
            sem = semantic_receipt(raw, rec)
            for log in sem["logs"]:
                if log["address"] == POOL and log["topics"] and log["topics"][0] == TOPIC:
                    decoded = decode(log)
                    need(decoded == leg_lookup.get((tx, decoded["log_index"])), "raw liquidation leg drift")
            observed[tx][provider] = sem
            witnesses[tx].append({"provider_id": provider, "operator": operator[1],
                                  "sequence": row["sequence"], "received_at": row["received_at"],
                                  "request_sha256": row["request_sha256"],
                                  "response_sha256": row["response_sha256"],
                                  "semantic_receipt_sha256": sha(canonical(sem))})
        need(seen == ids[:expected_count], "partial source order/count drift")
        manifests.append({"directory": directory.name, "sha256": expected_hash,
                          "receipt_count": expected_count, "last_failed_request": records[-1][0]})
    for tx, providers in observed.items():
        need(all(x == next(iter(providers.values())) for x in providers.values()),
             "full receipt/log cross-operator semantic mismatch: " + tx)
    priced = parse(contents["winner-weth-prices-original.zip"]["top-two-weth-prices.json"])
    digest = priced.pop("report_sha256")
    need(digest == sha(canonical(priced)) and priced["real_market_census_closed"] is False
         and priced["exact_intratransaction_price_proven"] is False, "oracle report commitment/scope")
    return receipts, legs, observed, witnesses, priced["transactions"], refs, manifests


def weth_reference(legs, receipts, prices):
    """Independent integer calculation, preserving all nine selected cases."""
    groups = defaultdict(list)
    for leg in legs:
        if leg["collateral_asset"] == leg["debt_asset"] == WETH:
            groups[leg["transaction_hash"]].append(leg)
    need(len(groups) == 9 and sum(map(len, groups.values())) == 9, "same-token population changed")
    price_by = {x["transaction_hash"]: x for x in prices}
    need(len(prices) == len(price_by) == 2, "price source duplicate/count")
    out = []
    for tx, group in groups.items():
        rec = receipts[tx]
        need(all(x["block_hash"] == rec["block_hash"] and x["block_number"] == rec["block_number"]
                 and x["receive_a_token"] is False for x in group), "WETH leg binding")
        debt = sum(int(x["debt_to_cover_raw"]) for x in group)
        collateral = sum(int(x["collateral_liquidated_raw"]) for x in group)
        gas = int(rec["total_gas_paid_wei"])
        illustrative_fee = (debt * 5 + 9999) // 10000
        after_gas = collateral - debt - gas
        row = {"transaction_hash": tx, "block_number": rec["block_number"], "block_hash": rec["block_hash"],
               "debt_weth_wei": str(debt), "collateral_weth_wei": str(collateral),
               "competitor_whole_transaction_gas_wei": str(gas),
               "collateral_minus_debt_minus_competitor_gas_wei": str(after_gas),
               "illustrative_5bps_fee_wei_ceil": str(illustrative_fee),
               "conditional_remainder_before_other_costs_wei": str(after_gas - illustrative_fee),
               "illustrative_fee_is_observed_or_admissible_quote": False,
               "preblock_usd_reference": None, "full_net_profit": None,
               "classification": "INSUFFICIENT_EVIDENCE", "admitted_nqc_value_usd_wad": "0"}
        if tx in price_by:
            p = price_by[tx]
            pre, end = p["preblock"], p["block_end"]
            need(pre["block"] == rec["block_number"] - 1 and end["block"] == rec["block_number"]
                 and end["hash"] == rec["block_hash"] and HASH.fullmatch(pre["hash"])
                 and p["historical_winner_gas_wei"] == str(gas)
                 and p["two_operator_preblock_oracle_consensus"] is True
                 and p["exact_transaction_prestate_proven"] is False, "oracle/receipt anchor mismatch")
            price = int(pre["oracle_usd_base_1e8"])
            need(price > 0, "invalid oracle price")
            remaining = after_gas - illustrative_fee
            signed = (1 if remaining >= 0 else -1) * (abs(remaining) * price // 10**8)
            row["preblock_usd_reference"] = {"block_number": pre["block"], "block_hash": pre["hash"],
                "price_usd_1e8": str(price), "conditional_remainder_usd_wad": str(signed),
                "exact_transaction_prestate": False, "nqc_decision_time_available": False}
        out.append(row)
    need(set(price_by).issubset(groups), "price outside selected population")
    out.sort(key=lambda r: (-int(r["collateral_minus_debt_minus_competitor_gas_wei"]), r["transaction_hash"]))
    for i, row in enumerate(out, 1):
        row["retrospective_rank"] = i
    return out


def reconcile(archive_root, metadata, rpc_root):
    abi = abi_binding()
    receipts, legs, observed, witnesses, prices, refs, manifests = sources(archive_root, metadata, rpc_root)
    by_tx = defaultdict(list)
    for leg in legs:
        by_tx[leg["transaction_hash"]].append(leg)
    rows, flashes, actor_flows = [], [], []
    transfer_count = ambiguous_count = 0
    for tx in sorted(receipts):
        rec, group = receipts[tx], by_tx[tx]
        sem = next(iter(observed[tx].values())) if tx in observed else None
        tx_flashes = []
        actors = set()
        if sem is not None:
            actors.update((sem["from"], sem["to"]))
            for log in sem["logs"]:
                flash = flash_event(log)
                if flash is not None:
                    flash["raw_witnesses"] = witnesses[tx]
                    tx_flashes.append(flash)
                    actors.add(flash["receiver"])
                if log["address"] == POOL and log["topics"] and log["topics"][0] == TOPIC:
                    actors.add(address_word(log["data"][130:194]))
            flows, n, ambiguous = token_flows(sem["logs"])
            transfer_count += n
            ambiguous_count += ambiguous
            for (actor, token), amount in sorted(flows.items()):
                if actor in actors:
                    actor_flows.append({"transaction_hash": tx, "actor": actor, "asset": token,
                                        "transfer_log_net_raw": str(amount),
                                        "scope": "ERC20_SHAPED_LOGS_ONLY_NOT_BALANCES_OR_BENEFICIAL_OWNERSHIP"})
        flashes.extend(tx_flashes)
        asset_totals = defaultdict(lambda: [0, 0])
        for leg in group:
            asset_totals[leg["debt_asset"]][0] += int(leg["debt_to_cover_raw"])
            asset_totals[leg["collateral_asset"]][1] += int(leg["collateral_liquidated_raw"])
        rows.append({"transaction_hash": tx, "chain_id": 1, "block_number": rec["block_number"],
            "block_hash": rec["block_hash"], "transaction_index": rec["transaction_index"],
            "conflict_set_id": "ethereum:" + tx, "liquidation_log_indices": sorted(x["log_index"] for x in group),
            "event_commitments": sorted(x["original_event_commitment_sha256"] for x in group),
            "asset_legs": [{"asset": asset, "debt_repaid_raw": str(values[0]),
                            "collateral_received_event_raw": str(values[1]),
                            "event_difference_raw": str(values[1]-values[0])}
                           for asset, values in sorted(asset_totals.items())],
            "historical_gas": {"whole_transaction_wei": rec["total_gas_paid_wei"],
                "execution_wei": rec["execution_gas_wei"], "blob_wei": rec["blob_gas_wei"],
                "gas_used": rec["gas_used"], "effective_gas_price_wei": rec["effective_gas_price_wei"],
                "base_priority_split_wei": None, "counted_times": 1,
                "payer": None if sem is None else sem["from"], "is_nqc_gas": False},
            "raw_receipt_witnesses": witnesses.get(tx, []),
            "raw_log_operator_count": len(observed.get(tx, {})),
            "recognized_flash_log_indices": [f["log_index"] for f in tx_flashes],
            "flash_observation_status": ("RAW_RECEIPT_UNAVAILABLE" if sem is None else
                "OBSERVED_EVENTS_PARTIAL_COST_COVERAGE" if tx_flashes else "NO_RECOGNIZED_EVENT_NOT_ZERO_COST"),
            "unresolved_costs": {name: None for name in UNKNOWN_COSTS},
            "estimated_opportunity_cost": None, "pending_obligations": None,
            "complete_realized_net_usd_wad": None, "nqc_capture_probability": None,
            "classification": "INSUFFICIENT_EVIDENCE", "gap_ids": sorted(GAPS),
            "admitted_nqc_executable_value_usd_wad": "0",
            "original_decision_time_observation_proven": False})
    weth = weth_reference(legs, receipts, prices)
    policy = parse((HERE/"capital-policy.json").read_bytes())
    need(policy["operator_gas_budget_centavos"] == 200000 and policy["operator_principal_centavos"] == 0,
         "capital policy scope changed")
    report = {"schema": "nqc-historical-economic-reconciliation-v1", "status": "PARTIAL_COST_EVIDENCE_RECONCILED",
        "scope": {"chain_id": 1, "start_block": 25880316, "end_block": 26095351,
                  "population": "127_ARCHIVED_COMPETITOR_WINNERS_NOT_D09_474_CANDIDATE_PAIRS",
                  "liquidation_events": len(legs), "winner_transactions": len(rows)},
        "source_archives": refs, "raw_manifests": manifests, "abi_references": abi,
        "classification_counts": {"EXECUTABLE": 0, "NON_EXECUTABLE": 0, "INSUFFICIENT_EVIDENCE": len(rows)},
        "raw_receipt_transactions": len(observed),
        "raw_receipt_selection": "LEXICOGRAPHIC_TRANSACTION_HASH_PREFIX_NOT_RANDOM_OR_TIME_REPRESENTATIVE",
        "two_operator_full_log_matches": sum(len(v) == 2 for v in observed.values()),
        "raw_receipts_missing": sorted(set(receipts)-set(observed)),
        "historical_whole_transaction_gas_wei": str(sum(int(x["total_gas_paid_wei"]) for x in receipts.values())),
        "recognized_flash_events": len(flashes),
        "recognized_flash_transactions": len({x["transaction_hash"] for x in flashes}),
        "flash_events_by_protocol": dict(sorted(Counter(x["protocol"] for x in flashes).items())),
        "flash_event_witness_operator_counts": dict(sorted(Counter(str(len(x["raw_witnesses"])) for x in flashes).items())),
        "flash_event_zero_fee_count": sum(x["event_fee_raw"] == "0" for x in flashes),
        "erc20_shaped_transfer_events": transfer_count, "ambiguous_transfer_events": ambiguous_count,
        "selected_actor_token_flow_rows": len(actor_flows), "unknown_cost_treatments": UNKNOWN_COSTS, "material_gaps": GAPS,
        "weth_same_asset_winner_count": len(weth),
        "weth_positive_after_competitor_gas": sum(int(x["collateral_minus_debt_minus_competitor_gas_wei"]) > 0 for x in weth),
        "weth_positive_after_illustrative_5bps": sum(int(x["conditional_remainder_before_other_costs_wei"]) > 0 for x in weth),
        "weth_source_priced_retrospective_ranks": [x["retrospective_rank"] for x in weth if x["preblock_usd_reference"]],
        "retrospective_selection_is_out_of_sample": False,
        "capital_policy_id": policy["policy_id"], "capital_policy_sha256": sha((HERE/"capital-policy.json").read_bytes()),
        "gas_authorization_applies_to_historical_window": False, "gas_spent_by_this_run_wei": "0",
        "full_historical_costs_reconciled": False, "unrecognized_financing_is_absent": False,
        "failed_censored_opportunity_population_complete": False, "flash_events_prove_nqc_admissible_capital": False,
        "transfer_logs_are_balance_proof": False, "native_internal_transfers_reconstructed": False,
        "actual_nqc_pnl_proven": False, "positive_nqc_executable_value": False,
        "independent_certification_issued": False, "real_market_census_closed": False,
        "mismatches": [], "verifier_sha256": sha(Path(__file__).read_bytes())}
    output = {"winner-economic-ledger.jsonl": b"".join(canonical(x) for x in rows),
              "observed-flash-events.jsonl": b"".join(canonical(x) for x in flashes),
              "selected-actor-token-flows.jsonl": b"".join(canonical(x) for x in actor_flows),
              "weth-cost-reference.jsonl": b"".join(canonical(x) for x in weth)}
    report["output_files"] = {name: {"sha256": sha(raw), "bytes": len(raw), "rows": len(raw.splitlines())}
                              for name, raw in output.items()}
    output["reconciliation.json"] = canonical(report)
    return output, report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive-root", type=Path, required=True)
    p.add_argument("--metadata", type=Path, default=HERE/"evidence/winner-api")
    p.add_argument("--rpc-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    need(not a.output.exists(), "output must be a fresh directory")
    out, report = reconcile(a.archive_root, a.metadata, a.rpc_root)
    a.output.mkdir(parents=True)
    for name, raw in out.items():
        (a.output/name).write_bytes(raw)
    print(json.dumps({k: report[k] for k in ("status", "raw_receipt_transactions", "two_operator_full_log_matches",
                                            "recognized_flash_events", "real_market_census_closed")}, sort_keys=True))


if __name__ == "__main__":
    main()
