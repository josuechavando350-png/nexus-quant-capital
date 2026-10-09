#!/usr/bin/env python3
"""Classify every pinned D12 pair with explicit V2 evidence and own-gas limits.

This is a historical research ledger, not a current execution signal or an
economic certificate. A declared peso budget is not an authenticated native
balance. The old no-own-capital producer is never rewritten or relabeled.
"""
import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path

from gas_budget import AUTHORIZATION_DATE, MAX_CENTAVOS, POLICY, canonical, replay, timestamp
from verify_historical_inputs import equal, parse, require
from verify_terminal_recovery import legacy

UNKNOWN_TREATMENTS = {
    "TOKEN_TRANSFER_BEHAVIOR_UNPROVEN": {"required": "Pinned runtime/proxy state, transfer semantics and adversarial fork tests for each required underlying", "falsifier": "Any unsupported fee, rebase, hook, upgrade or balance behavior invalidates the route"},
    "EXTERNAL_PRINCIPAL_AND_REPAYMENT_UNPROVEN": {"required": "Admissible exact provider and atomic repayment cashflow including premium and every non-gas obligation", "falsifier": "Insufficient principal, repayment shortfall or operator principal/collateral/guarantee obligation"},
    "NATIVE_GAS_FUNDING_UNAUTHENTICATED": {"required": "Authenticated wallet, native balance, acquisition cost basis, nonce exclusivity and gas reservation within cumulative MXN 2000", "falsifier": "Budget breach, reused funding proof, insufficient native balance or stale/future funding witness"},
    "FULL_COSTS_AND_MONETIZABLE_ROUTE_UNPROVEN": {"required": "Exact route and all swap/slippage/gas/MEV/funding/failure/infrastructure costs with realizable repayment and proceeds", "falsifier": "Any omitted cost, unmonetizable inventory or nonpositive conservative net margin"},
    "COMPETITION_AND_INCLUSION_UNPROVEN": {"required": "Decision-time competitor/inclusion evidence and calibrated capture estimates", "falsifier": "Future-data leakage or unsupported claim of winning inclusion"},
    "DECISION_TIME_AVAILABILITY_UNPROVEN": {"required": "Authenticated receive-time ledger from original observations", "falsifier": "Any feature received only after the historical decision"},
    "INDEPENDENT_AUTHORITY_PENDING": {"required": "Separate authority reviewing exact producer/consumer commits, trees, input bytes and declared scope", "falsifier": "Self-certification, failed reproduction or material source mismatch"},
}


def validate_policy(raw):
    p = parse(raw)
    equal(p["policy_id"], POLICY, "gas policy identity")
    equal(p["operator_gas_budget_centavos"], MAX_CENTAVOS, "gas budget")
    equal(p["authorization_date"], AUTHORIZATION_DATE.isoformat(), "authorization date")
    equal(p["allowed_operator_purposes"], ["NATIVE_NETWORK_GAS"], "operator purpose")
    for key in ("operator_principal_centavos", "operator_collateral_centavos", "operator_guarantees_centavos", "operator_additional_contingent_liability_centavos"):
        equal(p[key], 0, key)
    return p


def classify(actions, promotions, tokens, gas, observed_at, anchor_time):
    observed = timestamp(observed_at)
    require(observed.date() >= AUTHORIZATION_DATE, "recovery cannot predate this policy")
    require(observed >= dt.datetime.fromtimestamp(anchor_time, dt.timezone.utc), "recovery receipt predates state")
    ids, keys, candidate_ids, by_id = set(), set(), set(), {}
    for p in promotions:
        key = p["actionable_candidate_id"]
        require(key not in by_id, "duplicate capital candidate")
        by_id[key] = p
    rows = []
    for a in sorted(actions, key=lambda x: x["pair_id"]):
        require(a["pair_id"] not in ids and a["pair_key"] not in keys, "duplicate pair identity/key")
        ids.add(a["pair_id"])
        keys.add(a["pair_key"])
        require(a["status"] in ("ADMITTED", "REJECTED"), "unknown protocol disposition")
        row = {"pair_id": a["pair_id"], "pair_key": a["pair_key"], "borrower": a["borrower"],
               "debt_asset": a["debt_asset"], "collateral_asset": a["collateral_asset"],
               "protocol_disposition": a["status"], "pft_account_snapshot": a["pft_account_snapshot"],
               "pft_market_snapshot": a["pft_market_snapshot"],
               "admitted_executable_value_mxn_centavos": 0, "net_profit_estimate_mxn_centavos": None,
               "scope": "PINNED_HISTORICAL_PAIR_ONLY", "current_execution_permitted": False,
               "policy_id": POLICY, "gas_journal_chain_sha256": gas["event_chain_sha256"],
               "decision_time": {"state_timestamp": anchor_time,
                                 "classified_in_this_recovery_at": observed_at,
                                 "original_received_at": None,
                                 "available_to_nexus_at_original_decision": "UNPROVEN",
                                 "later_gas_authorization_applied_to_historical_state": False}}
        if a["status"] == "REJECTED":
            # Only these observed reasons are conclusive within this producer's
            # scope. Unknown/unsupported states must never become impossibility.
            require(a["reason"] in {"COLLATERAL_NOT_ENABLED", "PFT_MATH_REJECTED"}, "unhandled protocol rejection")
            row.update(classification="NON_EXECUTABLE", reasons=[a["reason"]],
                       rejection_scope="COLLATERAL_DISABLED_OR_ZERO_SIZED_LIQUIDATION_AT_PINNED_STATE",
                       material_unknowns_treatment="UPSTREAM_PROTOCOL_REJECTION_DOMINATES_THIS_PAIR_ONLY")
        else:
            key = a["candidate_id"]
            require(key not in candidate_ids, "duplicate actionable candidate")
            candidate_ids.add(key)
            require(key in by_id, "missing capital disposition")
            p = by_id[key]
            equal(p["debt_asset"], a["debt_asset"], "capital debt asset")
            equal(int(p["principal"], 16), int(a["debt_to_liquidate"]), "capital principal amount")
            equal(int(p["repayment_principal"], 16), int(a["debt_to_liquidate"]), "repayment principal amount")
            equal(int(p["flash_premium"], 16), int(a["flash_loan_premium"]), "premium amount")
            equal(p["capital_status"], "REJECTED", "historical capital status")
            equal(p["rejection_reason"], "EXECUTION_BLOCKED", "historical capital rejection")
            equal(p["allocations"], [], "no original allocation")
            equal(p["gas_funding_certified"], False, "historical gas claim")
            evidence = {}
            for role in ("debt_asset", "collateral_asset"):
                require(a[role] in tokens, "missing required token")
                token = tokens[a[role]]["AAVE_RESERVE_UNDERLYING"]
                equal(token["status"], "BLOCKED", "original token compatibility")
                require(bool(token["blockers"]), "empty token blocking evidence")
                evidence[role] = {"asset": a[role], "blockers": token["blockers"]}
            row.update(candidate_id=key, requirement_id=p["requirement_id"],
                       portfolio_candidate_id=p["portfolio_candidate_id"],
                       classification="INSUFFICIENT_EVIDENCE", reasons=list(UNKNOWN_TREATMENTS),
                       original_capital_rejection="EXECUTION_BLOCKED", token_evidence=evidence,
                       material_unknowns_treatment="NO_POSITIVE_EXECUTABLE_VALUE_OR_OPERATIONAL_PROMOTION")
        rows.append(row)
    equal(set(by_id), candidate_ids, "orphan or missing capital candidates")
    return rows


def build(d08, d12, policy_path, gas_events_path, observed_at, out):
    require(not out.exists(), "output already exists")
    original = legacy()
    summary, actions, promotions = original.read_d12(d12)
    required, _, _, _ = original.parse_actionability(actions, promotions)
    tokens, _, token_sha = original.scan_d08_tokens(d08, required)
    policy_raw = policy_path.read_bytes()
    validate_policy(policy_raw)
    event_raw = gas_events_path.read_bytes()
    gas = replay(parse(event_raw))
    require(gas["event_count"] == 0 or timestamp(observed_at) >= timestamp(parse(event_raw)[-1]["at"]), "future gas journal")
    rows = classify(actions, promotions, tokens, gas, observed_at, summary["anchor"]["timestamp"])
    equal(len(rows), 474, "complete scoped pair population")
    equal(len({r["borrower"] for r in rows}), 400, "complete scoped borrowers")
    raw = b"".join(canonical(r) for r in rows)
    report = {"schema": "nqc-historical-candidate-classification-v1", "scope": "ALL_474_D12_PAIRS_OF_400_BELOW_ONE_AAVE_BORROWERS_AT_ANCHOR_ONLY",
              "anchor": summary["anchor"], "classified_at": observed_at,
              "classification_counts": dict(Counter(r["classification"] for r in rows)),
              "protocol_rejection_counts": dict(Counter(a["reason"] for a in actions if a["status"] == "REJECTED")),
              "candidate_count": len(rows), "unknown_treatments": UNKNOWN_TREATMENTS,
              "scope_pair_conservation_verified": True, "outside_scope_completeness_claimed": False,
              "source_sha256": {"d08_zip": original.D08_OUTER_SHA, "d08_token_admission": token_sha,
                                "d12_zip": original.D12_OUTER_SHA, "d12_records": original.D12_ACTION_SHA,
                                "d12_promotions": original.D12_PROMOTION_SHA,
                                "capital_policy": hashlib.sha256(policy_raw).hexdigest(),
                                "gas_events": hashlib.sha256(event_raw).hexdigest()},
              "gas_accounting": gas, "own_gas_budget_is_native_balance": False,
              "all_pair_classifications_sha256": hashlib.sha256(raw).hexdigest(),
              "admitted_executable_value_mxn_centavos": 0, "realized_pnl_mxn_centavos": None,
              "historical_decision_time_evidence_available": False,
              "new_producer_independently_certified": False, "real_market_census_closed": False,
              "classifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    out.mkdir(parents=True)
    (out / "candidate-classifications.jsonl").write_bytes(raw)
    (out / "classification-summary.json").write_bytes(canonical(report))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("d08", "d12", "policy", "gas-events", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--observed-at", required=True, help="Actual recovery classification time; never the historical block time")
    a = p.parse_args()
    r = build(a.d08, a.d12, a.policy, a.gas_events, a.observed_at, a.out)
    print(json.dumps(r["classification_counts"], sort_keys=True))
