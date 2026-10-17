"""Fail-closed, zero-network screening for proposed Morpho + sponsored-bundle economics.

All assets use unsigned integer smallest units. Values are a model, NEVER
proof of market capture, builder acceptance, or a payable opportunity.
No RPC calls, private keys, signatures, or transactions.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path

REQUIRED = (
    "evidence_type", "chain_id", "block_number", "block_hash", "prestate_observed",
    "morpho_code_proven", "executor_deployed", "zero_operator_eth", "zero_operator_tokens",
    "morpho_liquidatable", "collateral_compatibility_proven", "route_simulated_exact_state",
    "repaid_loan_units", "seized_collateral_units", "collateral_loan_out_units",
    "loan_spent_to_obtain_eth_units", "native_eth_out_wei", "builder_tip_wei",
    "gas_limit", "max_fee_per_gas_wei", "effective_gas_price_wei", "gas_used",
    "builder_sponsor_advance_wei", "builder_revenue_wei", "builder_revenue_measured",
    "minimum_builder_profit_wei", "minimum_operator_profit_loan_units",
    "competition_evidence_proven",
)
NUMS = (
    "chain_id", "block_number", "repaid_loan_units", "seized_collateral_units",
    "collateral_loan_out_units", "loan_spent_to_obtain_eth_units", "native_eth_out_wei",
    "builder_tip_wei", "gas_limit", "max_fee_per_gas_wei", "effective_gas_price_wei",
    "gas_used", "builder_sponsor_advance_wei", "builder_revenue_wei",
    "minimum_builder_profit_wei", "minimum_operator_profit_loan_units",
)
FLAGS = (
    "prestate_observed", "morpho_code_proven", "executor_deployed", "zero_operator_eth",
    "zero_operator_tokens", "morpho_liquidatable", "collateral_compatibility_proven",
    "route_simulated_exact_state", "builder_revenue_measured", "competition_evidence_proven",
)

@dataclass(frozen=True)
class GateResult:
    status: str
    blockers: list[str]
    operator_profit_loan_units: int | None
    builder_margin_wei: int | None
    sponsor_minimum_upfront_wei: int | None
    gas_actual_wei: int | None
    evidence_type: str
    certification: str = "NOT_CERTIFIED"
    is_live_executable: bool = False
    is_capture_proven: bool = False


def unsigned(x: object, name: str) -> int:
    if isinstance(x, bool) or not (isinstance(x, int) or (
        isinstance(x, str) and x.isascii() and x.isdecimal()
    )):
        raise ValueError(f"{name}: use a non-negative integer or decimal integer string")
    value = int(x)
    if value < 0 or value > 2**256 - 1:
        raise ValueError(f"{name}: out of uint256 range")
    return value


def check(obs: dict) -> GateResult:
    if not isinstance(obs, dict):
        raise ValueError("expected a JSON object")
    missing = set(REQUIRED) - set(obs)
    unknown = set(obs) - set(REQUIRED)
    if missing or unknown:
        raise ValueError(f"missing={sorted(missing)} unknown={sorted(unknown)}")
    if obs["evidence_type"] not in ("SYNTHETIC", "HISTORICAL_REPLAY"):
        raise ValueError("evidence_type must be SYNTHETIC or HISTORICAL_REPLAY")
    if not isinstance(obs["block_hash"], str) or len(obs["block_hash"]) != 66 or not obs["block_hash"].startswith("0x"):
        raise ValueError("block_hash must be a 32-byte hex string")
    try:
        int(obs["block_hash"][2:], 16)
    except ValueError as exc:
        raise ValueError("block_hash must be hexadecimal") from exc
    for name in FLAGS:
        if type(obs[name]) is not bool:
            raise ValueError(f"{name}: expected boolean")
    n = {name: unsigned(obs[name], name) for name in NUMS}
    blockers: list[str] = []
    if n["chain_id"] != 1:
        blockers.append("UNSUPPORTED_CHAIN_ONLY_ETHEREUM_MAINNET_MODEL")
    if n["repaid_loan_units"] == 0 or n["seized_collateral_units"] == 0:
        blockers.append("INVALID_LIQUIDATION_SIZE")
    for flag, reason in (
        ("prestate_observed", "PRESTATE_NOT_AUTHENTICATED"),
        ("morpho_code_proven", "MORPHO_RUNTIME_CODE_UNPROVEN"),
        ("executor_deployed", "EXECUTOR_NOT_DEPLOYED_OR_SPONSORED_DEPLOYMENT_UNPROVEN"),
        ("zero_operator_eth", "EXTERNAL_ETH_SUBSIDY_PRESENT"),
        ("zero_operator_tokens", "EXTERNAL_TOKEN_SUBSIDY_PRESENT"),
        ("morpho_liquidatable", "POSITION_NOT_LIQUIDATABLE_AT_PRESTATE"),
        ("collateral_compatibility_proven", "COLLATERAL_EXECUTION_COMPATIBILITY_UNPROVEN"),
        ("route_simulated_exact_state", "REAL_DEX_ROUTE_NOT_SIMULATED"),
        ("builder_revenue_measured", "BUILDER_REVENUE_NOT_MEASURED"),
        ("competition_evidence_proven", "CAPTURE_COMPETITION_UNPROVEN"),
    ):
        if not obs[flag]:
            blockers.append(reason)

    if n["gas_used"] > n["gas_limit"] or n["gas_limit"] == 0:
        blockers.append("GAS_EXCEEDS_LIMIT_OR_ZERO")
    if n["effective_gas_price_wei"] > n["max_fee_per_gas_wei"] or n["max_fee_per_gas_wei"] == 0:
        blockers.append("INVALID_EIP1559_GAS_FEES")
    sponsor_minimum = n["gas_limit"] * n["max_fee_per_gas_wei"]
    actual_gas = n["gas_used"] * n["effective_gas_price_wei"]
    if n["builder_sponsor_advance_wei"] < sponsor_minimum:
        blockers.append("SPONSOR_CANNOT_PREPAY_GAS_LIMIT")
    if n["native_eth_out_wei"] < n["builder_tip_wei"] or n["builder_tip_wei"] == 0:
        blockers.append("BUILDER_TIP_NOT_FUNDED_WITH_ETH")
    if n["loan_spent_to_obtain_eth_units"] == 0:
        blockers.append("ETH_CONVERSION_NOT_SPECIFIED")
    if n["builder_revenue_wei"] < n["builder_sponsor_advance_wei"] + n["minimum_builder_profit_wei"]:
        blockers.append("BUILDER_NOT_REPAID_WITH_MARGIN")
    operator_profit = (
        n["collateral_loan_out_units"] - n["repaid_loan_units"]
        - n["loan_spent_to_obtain_eth_units"]
    )
    if operator_profit < n["minimum_operator_profit_loan_units"] or operator_profit <= 0:
        blockers.append("OPERATOR_NET_PROFIT_NON_POSITIVE")
    # No assumption that block.coinbase payments accrue to builder.
    if obs["evidence_type"] == "SYNTHETIC":
        blockers.append("SYNTHETIC_ONLY_NOT_HISTORICAL_PROOF")
    return GateResult(
        status="BLOCKED" if blockers else "MODEL_SCREEN_PASS_ONLY",
        blockers=blockers,
        operator_profit_loan_units=operator_profit,
        builder_margin_wei=n["builder_revenue_wei"] - n["builder_sponsor_advance_wei"],
        sponsor_minimum_upfront_wei=sponsor_minimum,
        gas_actual_wei=actual_gas,
        evidence_type=obs["evidence_type"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="NQC Morpho sponsored-bundle preflight (OFFLINE ONLY)")
    parser.add_argument("observation", type=Path)
    args = parser.parse_args()
    try:
        observation = json.loads(args.observation.read_text(encoding="utf-8"))
        result = check(observation)
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
        return 0 if result.status == "MODEL_SCREEN_PASS_ONLY" else 2
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "INVALID_INPUT", "message": str(error), "certification": "NOT_CERTIFIED"}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
