"""NQC060: conservative liquidation-retention screening.

Offline, no network, no inferred ETH/loan-token conversion, no commercial admission.
Input amounts are integer base units of one identified *loan* asset. Native
sponsorship obligations stay separate until a verified route prices them.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal, localcontext
from pathlib import Path

_DECIMAL_UINT = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}\Z")
_MARKET = re.compile(r"0x[0-9a-fA-F]{64}\Z")


def uint(value: str | None, label: str) -> int | None:
    """Strict, nonnegative, explicit-decimal integer; never silently accept floats."""
    if value is None:
        return None
    if not isinstance(value, str) or not _DECIMAL_UINT.fullmatch(value):
        raise ValueError(f"{label}: expected decimal base-unit string")
    return int(value)


def safe_bounds(lo: int | None, hi: int | None, name: str) -> None:
    if lo is not None and hi is not None and lo > hi:
        raise ValueError(f"{name}: lower bound exceeds upper bound")


def bounded_loan_cashflow(rec: dict) -> dict:
    """Compute necessary upper and sufficient pre-native lower bound.

    Costs in loan units can be summed only when the record declares they are
    additive/disjoint. Exit-sale amounts must already include DEX fees and
    slippage; never subtract these again. The result is *not* total P&L.
    """
    if rec.get("dex_proceeds_net_of_swap_fees") is not True:
        raise ValueError("only executable sale proceeds after route costs are supported")
    if rec.get("cost_buckets_are_disjoint") is not True:
        raise ValueError("cost categories must be declared non-overlapping")
    fields = (
        "sale_loan_min", "sale_loan_max", "repay_loan_min", "repay_loan_max",
        "loan_fee_min", "loan_fee_max", "bid_loan_min", "bid_loan_max",
    )
    amounts = {k: uint(rec.get(k), k) for k in fields}
    for name in ("sale_loan", "repay_loan", "loan_fee", "bid_loan"):
        safe_bounds(amounts[f"{name}_min"], amounts[f"{name}_max"], name)
    upper = None
    if all(amounts.get(k) is not None for k in (
            "sale_loan_max", "repay_loan_min", "loan_fee_min", "bid_loan_min")):
        upper = (amounts["sale_loan_max"] - amounts["repay_loan_min"]
                 - amounts["loan_fee_min"] - amounts["bid_loan_min"])
    pre_native_lower = None
    if all(amounts.get(k) is not None for k in (
            "sale_loan_min", "repay_loan_max", "loan_fee_max", "bid_loan_max")):
        pre_native_lower = (amounts["sale_loan_min"] - amounts["repay_loan_max"]
                            - amounts["loan_fee_max"] - amounts["bid_loan_max"])
    decision = (
        "SCOPED_NEGATIVE_OR_ZERO_UPPER_BOUND" if upper is not None and upper <= 0
        else "POTENTIAL_MARGIN_ONLY_NO_CLAIM" if upper is not None and upper > 0
        else "INSUFFICIENT_LOAN_LEDGER")
    return {
        "upper_bound_loan_base_units_before_unpriced_native_obligations": str(upper) if upper is not None else None,
        "lower_bound_loan_base_units_before_unpriced_native_obligations": str(pre_native_lower) if pre_native_lower is not None else None,
        "economic_decision": decision,
        "native_ETH_gas_and_sponsor_funding_included": False,
        "net_profit_demonstrated": False,
        "note": "When native obligations are unknown but nonnegative, a <=0 loan-unit upper bound safely rejects this exact route. A positive upper bound does not establish net profit.",
    }


def source_gates(rec: dict) -> dict:
    for k in ("market_id", "loan_token_address"):
        if k not in rec:
            raise ValueError(f"missing {k}")
    if not _MARKET.fullmatch(rec["market_id"]):
        raise ValueError("invalid market id")
    if not _ADDRESS.fullmatch(rec["loan_token_address"]):
        raise ValueError("invalid loan token address")
    if not isinstance(rec.get("chain_id"), int) or isinstance(rec["chain_id"], bool):
        raise ValueError("chain id must be integer")
    if not isinstance(rec.get("loan_decimals"), int) or not 0 <= rec["loan_decimals"] <= 36:
        raise ValueError("bad loan decimals")
    if rec.get("liquidator_gate") not in ("OPEN", "RESTRICTED", "UNKNOWN"):
        raise ValueError("liquidator gate status required")
    ts = uint(rec.get("evaluation_timestamp"), "evaluation_timestamp")
    mat = uint(rec.get("market_maturity_timestamp"), "market_maturity_timestamp")
    debt = uint(rec.get("borrower_debt_raw"), "borrower_debt_raw")
    if rec["chain_id"] != 1:
        eligibility = "NOT_ETHEREUM_1_TITAN_ROUTE"
    elif rec["liquidator_gate"] == "RESTRICTED" and not rec.get("gate_permission_proven"):
        eligibility = "BLOCKED_BY_LIQUIDATOR_GATE"
    elif rec["liquidator_gate"] == "UNKNOWN":
        eligibility = "GATE_STATE_UNKNOWN"
    elif ts is None or mat is None or debt is None:
        eligibility = "MISSING_REQUIRED_CANONICAL_STATE"
    elif ts <= mat:
        eligibility = "NOT_POST_MATURITY_ELIGIBLE_AT_TIME"
    elif debt == 0:
        eligibility = "NO_UNPAID_DEBT"
    else:
        eligibility = "MECHANISM_MAY_APPLY_NEEDS_CANONICAL_PROOF"
    return {
        "eligibility": eligibility,
        "canonical_market_and_state_proven": bool(rec.get("canonical_market_verified") and rec.get("canonical_position_verified")),
        "maturity_strict_gt_checked": ts is not None and mat is not None and ts > mat,
        "outstanding_debt_known_positive": debt is not None and debt > 0,
        "health_factor_required_for_post_maturity": False,
        "liquidator_gate_status": rec["liquidator_gate"],
        "exact_post_maturity_LIF_verified": bool(rec.get("exact_LIF_verified")),
    }


def evaluate(rec: dict) -> dict:
    if rec.get("strategy") != "MORPHO_MIDNIGHT_POST_MATURITY":
        raise ValueError("this adapter only supports Midnight post maturity")
    is_synthetic = rec.get("fixture_only") is True
    gate = source_gates(rec)
    economics = bounded_loan_cashflow(rec["loan_asset_cashflow"])
    if economics["economic_decision"] == "SCOPED_NEGATIVE_OR_ZERO_UPPER_BOUND":
        next_action = "REJECT_THIS_SCOPED_ROUTE"
    elif gate["eligibility"] != "MECHANISM_MAY_APPLY_NEEDS_CANONICAL_PROOF":
        next_action = "RESOLVE_ELIGIBILITY_OR_STOP"
    else:
        next_action = "OBTAIN_PRICE_SELL_ROUTE_NATIVE_SPONSOR_AND_COMPETITION_EVIDENCE"
    # Neither theoretical incentive nor fictional fixtures ever become a commercial gain.
    return {
        "candidate_id": rec.get("candidate_id"),
        "strategy": rec["strategy"],
        "fixture_only": is_synthetic,
        "loan_asset": {"chain_id": rec["chain_id"], "address": rec["loan_token_address"], "decimals": rec["loan_decimals"]},
        "protocol_gates": gate,
        "economics": economics,
        "native_gas_sponsor_terms": "VERIFIED" if rec.get("native_sponsor_terms_verified") else "UNKNOWN",
        "competitive_inclusion_measured": bool(rec.get("competition_prospectively_measured")),
        "next_action": next_action,
        "commercial_admission": False,
        "NQC_realized_profit": None,
        "capture_probability": None,
        "no_personal_recourse_proven": False,
    }


def morpho_blue_benchmark() -> dict:
    """Carry NQC054 *conditional* historical B benchmark; explicit ETH/WETH bridge.

    Values are *inherited*, not newly sourced or recertified here.
    The exact ETH-equivalent WETH->ETH interpretation is only permitted for B's
    pinned historic observed route, never as a general conversion.
    """
    with localcontext() as ctx:
        ctx.prec = 70
        sale_eth = Decimal("26.409680973611")
        debt_eth_equiv = Decimal("26.039738525656992415")
        coinbase_eth = Decimal("0.368092735714237547")
        gas_eth = Decimal("0.000198416195275125")
        margin = sale_eth - debt_eth_equiv
        retained = margin - coinbase_eth - gas_eth
        prima_1bp = debt_eth_equiv / Decimal(10000)
        bid_fraction = coinbase_eth / margin
        return {
            "source": "NQC054/NQC058 case B, historical observed ETH-equivalent conversion only",
            "margin_before_bid_and_gas_ETH": format(margin,"f"),
            "coinbase_payout_ETH": format(coinbase_eth,"f"),
            "coinbase_share_of_sale_debt_margin_pct": format(bid_fraction*100,"f"),
            "observed_residue_before_unseen_obligations_ETH": format(retained,"f"),
            "full_debt_1bp_funding_premium_ETH": format(prima_1bp,"f"),
            "scoped_net_after_full_debt_1bp_premium_ETH": format(retained-prima_1bp,"f"),
            "profit_NQC_proven": False,
        }


def run_offline() -> dict:
    return {
        "schema":"nqc060-retention-evidence-v1",
        "morpho_blue_inherited":morpho_blue_benchmark(),
        "new_live_or_historical_midnight_candidates_authenticated":0,
        "candidate_ranking_by_profit":None,
        "commercial_admission":False,
    }


if __name__ == '__main__':
    print(json.dumps(run_offline(),indent=2,sort_keys=True))
