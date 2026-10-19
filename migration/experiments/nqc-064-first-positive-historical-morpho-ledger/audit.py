"""NQC064: narrowly scoped, exact-amount historical Morpho Blue transaction ledger.

Uses published token transfers and internal ETH traces as hypotheses for
transaction-local flows, not a canonical state-proof or NQC revenue record.
No I/O beyond reading the bundled case.json; no provider calls or secrets.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, localcontext
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
WAD = 10**18
USDC_UNIT = 10**6
GWEI = 10**9


def units(s: str, places: int) -> int:
    if not isinstance(s, str) or not s or "e" in s.lower():
        raise ValueError("fixed-point decimal string required")
    v = Decimal(s)
    if not v.is_finite() or v < 0 or v.as_tuple().exponent < -places:
        raise ValueError("invalid precision, sign, or magnitude")
    raw = v * 10**places
    if raw != raw.to_integral_exact():
        raise ValueError("sub-unit value")
    return int(raw)


def fixed(raw: int, places: int) -> str:
    if raw < 0:
        return "-" + fixed(-raw, places)
    s = str(raw).rjust(places + 1, "0")
    return s[:-places] + "." + s[-places:] if places else s


def analyze(case: dict) -> dict:
    if case.get("chain_id") != 1 or case.get("protocol") != "Morpho Blue":
        raise ValueError("wrong chain/protocol")
    if case.get("weth_token", "").lower() != "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2":
        raise ValueError("unverified WETH identity")
    recv_weth = units(case["weth_received_from_uniswap_v3"], 18)
    sent_weth = units(case["weth_sent_to_uniswap_v2"], 18)
    unwrap_weth = units(case["weth_withdrawal"], 18)
    pay_builder = units(case["eth_transfer_to_beaverbuild"], 18)
    if unwrap_weth != pay_builder:
        raise ValueError("cannot link WETH withdrawal to ETH payment")
    swap_spread = recv_weth - sent_weth
    if swap_spread < unwrap_weth:
        raise ValueError("reported outflows exceed swap spread")
    retained_weth = swap_spread - unwrap_weth
    # Gas is a separate account: conditional economic consolidation only.
    gas_used = int(case["gas_used"])
    gas_price_wei = units(case["effective_gas_price_gwei"], 9)
    gas_fee_wei = units(case["effective_gas_paid_eth"], 18)
    if gas_used * gas_price_wei != gas_fee_wei:
        raise ValueError("gasUsed * effectiveGasPrice != actual ETH fee")
    usdc_dust = units(case["usdc_received_from_uniswap_v2"], 6) - units(case["usdc_repaid_to_morpho"], 6)
    if usdc_dust < 0:
        raise ValueError("USDC settlement deficit")
    if units(case["uni_seized_from_morpho"], 18) != units(case["uni_sold_to_uniswap_v3"], 18):
        raise ValueError("unexplained UNI inventory difference")
    # WETH withdrawal and ETH payment are one paired settlement: do not subtract twice.
    equivalent_after_gas = retained_weth - gas_fee_wei
    if equivalent_after_gas < 0:
        raise ValueError("same-actor post-gas equivalent not positive")
    if case["NQC_executed"] or case["flash_loan_verified"] or case["builder_advance_verified"]:
        raise ValueError("unsupported attribution/financing in this case")
    # Counterfactual flash-financing of the initial WETH outflow, excluding extra gas.
    illustrative_five_bp_premium = sent_weth * 5 // 10000
    after_five_bp = equivalent_after_gas - illustrative_five_bp_premium
    with localcontext() as ctx:
        ctx.prec = 60
        headroom_bps = (Decimal(equivalent_after_gas) * 10000 / Decimal(sent_weth)).quantize(
            Decimal("0.000001"), rounding=ROUND_DOWN
        )
    return {
        "classification": "OBSERVED_THIRD_PARTY_POSITIVE_TRANSACTION_LOCAL_RESIDUAL_CONDITIONAL",
        "transaction_hash": case["tx_hash"],
        "block": case["block_number"],
        "gas_eoa": case["gas_payer_eoa"],
        "executor_contract": case["executor_contract"],
        "WETH_trade_spread": fixed(swap_spread, 18),
        "ETH_builder_transfer_backed_by_WETH_withdrawal": fixed(pay_builder, 18),
        "WETH_retained_in_executor_token_flow": fixed(retained_weth, 18),
        "USDC_dust_separately": fixed(usdc_dust, 6),
        "ETH_gas_paid_by_different_EOA": fixed(gas_fee_wei, 18),
        "ETH_equivalent_post_listed_builder_and_gas_IF_economic_owner_same": fixed(equivalent_after_gas, 18),
        "WETH_required_at_first_observed_swap_without_same_tx_inbound": fixed(sent_weth, 18),
        "counterfactual_flash_extra_cost_max_bps_BEFORE_incremental_gas_sponsor_losses": format(headroom_bps, "f"),
        "counterfactual_flash_5bp_fee_only_WETH": fixed(illustrative_five_bp_premium, 18),
        "counterfactual_residual_after_5bp_and_no_other_incremental_costs_ETH_equiv": fixed(after_five_bp, 18),
        "actual_flash_loan_or_sponsor_verified": False,
        "ownership_gas_EOA_executor_proven": False,
        "historical_bundle_capturable_by_NQC": None,
        "NQC_actual_profit": None,
        "ETH_equivalent_requires_explicit_WETH_1_to_1_unwrap_and_owner_consolidation": True,
        "commercial_admission": False,
        "new_RPC_requests": 0,
        "Triport_lifetime_requests_used": 0,
        "scope": "Etherscan event/trace transcription; missing prestate, account ownership, flash and sponsor terms, other costs and ex-ante competitive capture."
    }


def run() -> dict:
    case = json.loads((HERE / "case.json").read_text(encoding="utf-8"))
    return analyze(case)


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
