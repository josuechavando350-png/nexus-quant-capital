"""Fail-closed, read-only reconciliation of one observed Morpho liquidation.

This is a *historical winner of another operator*. Blockscout-provided
transaction metadata and ERC-20 transfers do not reveal all native/internal
transfers, nor the prestate and competing bids. Accordingly, this module can
NEVER output a certified profit, an NQC capture, or builder-sponsorship proof.
It intentionally does not use network, signing, RPC, or external dependencies.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

PIN = {
    "chain_id": 1,
    "morpho_address": "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb",
    "transaction_hash": "0x46300e9614c547118ecdd524bc7218208088cc4ae9e5bd534e62055d38f9925b",
    "block_number": 26190955,
    "block_hash": "0x5d499e63c5d119293a906036f369d8d75f9560618efec0ff916e4fefa33dfda8",
    "parent_hash": "0xf57a30121eac97b983cad86fcb3107787a9d400ca4d69d5a96a4b1b618ac65dc",
    "morpho_internal_liquidate_method_id": "0xd8eabcb8",
}
REQUIRED_AMOUNTS = (
    "ezeth_seized_raw",
    "ezeth_sent_onward_raw",
    "weth_minted_raw",
    "weth_repaid_to_morpho_raw",
    "weth_unwrapped_raw",
    "weth_unexplained_transfer_gap_raw",
    "gas_used",
    "gas_price_wei",
    "gas_fee_wei",
    "base_fee_per_gas_wei",
    "priority_fee_wei",
)
BLOCKERS = (
    "EXTERNAL_WINNER_NOT_NQC",
    "NO_AUTHENTICATED_NATIVE_INTERNAL_TRANSFERS",
    "WETH_TRANSFER_GAP_HAS_UNKNOWN_BENEFICIARY",
    "NO_NQC_DECISION_TIME_PRESTATE_OR_ORDERING",
    "NO_NQC_REAL_DEX_EXECUTION_OR_PROFIT",
    "BUILDER_SPONSORSHIP_AND_BUILDER_REVENUE_UNPROVEN",
    "NO_BUNDLE_INCLUSION_OR_CAPTURE_PROOF",
)


def amount(value: object, field: str) -> int:
    if type(value) is int:
        out = value
    elif isinstance(value, str) and value.isascii() and value.isdecimal():
        out = int(value)
    else:
        raise ValueError(f"{field}: exact nonnegative integer required")
    if out < 0 or out >= 2**256:
        raise ValueError(f"{field}: outside uint256")
    return out


@dataclass(frozen=True)
class HistoricalGate:
    status: str
    transaction_hash: str
    observed_gas_fee_wei: int
    reconciled_weth_residual_raw: int
    ethers_received_by_nqc_wei: None
    profit_estimate: None
    blockers: tuple[str, ...]
    live_executable: bool = False
    certified: bool = False


def inspect(record: dict) -> HistoricalGate:
    if not isinstance(record, dict):
        raise ValueError("record must be an object")
    for key, expected in PIN.items():
        if key not in record or record[key] != expected:
            raise ValueError(f"pinned external observation mismatch: {key}")
    if record.get("scope") != "EXTERNAL_HISTORICAL_WINNER_NOT_NQC_NOT_SPONSORED_PROOF":
        raise ValueError("source/scope identity mismatch")
    if record.get("status") != "success":
        raise ValueError("transaction not confirmed successful")
    if record.get("timestamp_utc") != "2026-10-14T13:11:35Z":
        raise ValueError("unexpected historical timestamp")
    values = {key: amount(record.get(key), key) for key in REQUIRED_AMOUNTS}
    if any(values[k] == 0 for k in ("ezeth_seized_raw", "gas_used", "gas_price_wei")):
        raise ValueError("empty historical transfer/gas")
    if values["ezeth_seized_raw"] != values["ezeth_sent_onward_raw"]:
        raise ValueError("EZETH transfer flow does not reconcile")
    weth_residual = (values["weth_minted_raw"] - values["weth_repaid_to_morpho_raw"]
                     - values["weth_unwrapped_raw"])
    if weth_residual < 0 or weth_residual != values["weth_unexplained_transfer_gap_raw"]:
        raise ValueError("WETH transfer flow does not reconcile")
    if values["gas_used"] * values["gas_price_wei"] != values["gas_fee_wei"]:
        raise ValueError("Ethereum gas fee does not reconcile")
    if values["gas_price_wei"] < values["base_fee_per_gas_wei"]:
        raise ValueError("gas price below base fee")
    if (values["gas_price_wei"] - values["base_fee_per_gas_wei"]) * values["gas_used"] != values["priority_fee_wei"]:
        raise ValueError("priority fee does not reconcile")
    if record.get("reference") != f"https://eth.blockscout.com/tx/{PIN['transaction_hash']}":
        raise ValueError("observation reference mismatch")
    return HistoricalGate(
        status="RECEIPT_RECONCILED_INCOMPLETE_NO_PROFIT_AUTHORITY",
        transaction_hash=PIN["transaction_hash"],
        observed_gas_fee_wei=values["gas_fee_wei"],
        reconciled_weth_residual_raw=weth_residual,
        ethers_received_by_nqc_wei=None,
        profit_estimate=None,
        blockers=BLOCKERS,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only historical Morpho receipt gate")
    parser.add_argument("json_path", type=Path)
    args = parser.parse_args()
    try:
        result = inspect(json.loads(args.json_path.read_text(encoding="utf-8")))
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
        return 2  # Incomplete receipt is never admissible for a live transaction.
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "INVALID_INPUT", "reason": str(exc), "certified": False}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
