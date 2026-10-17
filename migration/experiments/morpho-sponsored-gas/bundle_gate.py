"""Offline, conservative model for a potential Titan/Quasar sponsored bundle.

A pass is NOT a production certificate. A transfer to block.coinbase is not
necessarily builder revenue. The calculated sponsorship requirement is an
upper bound on signer up-front ETH, not a builder-accepted quote.
No signing, networking, RPC, private keys, deployment, or broadcasting.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

UINT256_MAX = 2**256 - 1
SUPPORTED_BUILDERS = frozenset(("TITAN", "QUASAR"))
TX_ORDER = ("DEPLOY_EXECUTOR", "EXECUTE_LIQUIDATION")
REQUIRED = {
    "evidence_type", "chain_id", "prestate_block_hash", "builder", "sender_initial_eth_wei",
    "executor_initial_eth_wei", "builder_advance_wei", "builder_receipts_verified",
    "builder_value_gross_wei", "builder_profit_minimum_wei", "builder_value_measured",
    "route_replayed", "morpho_callback_replayed", "target_tx_competition_replayed",
    "txs", "builder_sponsored_deployment_supported", "coinbase_tip_wei",
}
TX_FIELDS = {"purpose", "from", "nonce", "gas_limit", "max_fee_per_gas_wei", "value_wei"}


def u256(value: object, name: str) -> int:
    if isinstance(value, bool) or not (
        isinstance(value, int) or (isinstance(value, str) and value.isascii() and value.isdecimal())
    ):
        raise ValueError(f"{name}: expected unsigned integer")
    n = int(value)
    if n < 0 or n > UINT256_MAX:
        raise ValueError(f"{name}: outside uint256")
    return n


def address(value: object) -> str:
    if not isinstance(value, str) or len(value) != 42 or not value.startswith("0x"):
        raise ValueError("Invalid EOA address")
    try:
        int(value[2:], 16)
    except ValueError as exc:
        raise ValueError("EOA address must be hexadecimal") from exc
    if int(value[2:], 16) == 0:
        raise ValueError("EOA address cannot be zero")
    return value.lower()


def block_hash(value: object) -> None:
    if not isinstance(value, str) or len(value) != 66 or not value.startswith("0x"):
        raise ValueError("invalid prestate block hash")
    try:
        int(value[2:], 16)
    except ValueError as exc:
        raise ValueError("invalid prestate block hash") from exc


@dataclass(frozen=True)
class BundleGate:
    status: str
    blockers: list[str]
    required_upfront_wei: int
    sponsor_margin_wei: int
    transaction_count: int
    certified: bool = False
    live_executable: bool = False


def check(bundle: dict) -> BundleGate:
    if not isinstance(bundle, dict) or set(bundle) != REQUIRED:
        raise ValueError("bundle fields must match exact schema")
    if bundle["evidence_type"] not in ("SYNTHETIC", "HISTORICAL_BUNDLE_TRACE"):
        raise ValueError("invalid evidence_type")
    if u256(bundle["chain_id"], "chain_id") != 1:
        raise ValueError("currently supports Ethereum mainnet only")
    block_hash(bundle["prestate_block_hash"])
    if bundle["builder"] not in SUPPORTED_BUILDERS:
        raise ValueError("builder is not admitted by this model")
    for key in (
        "builder_receipts_verified", "builder_value_measured", "route_replayed",
        "morpho_callback_replayed", "target_tx_competition_replayed",
        "builder_sponsored_deployment_supported",
    ):
        if type(bundle[key]) is not bool:
            raise ValueError(f"{key}: expected boolean")
    sender_initial = u256(bundle["sender_initial_eth_wei"], "sender_initial_eth_wei")
    contract_initial = u256(bundle["executor_initial_eth_wei"], "executor_initial_eth_wei")
    builder_advance = u256(bundle["builder_advance_wei"], "builder_advance_wei")
    gross = u256(bundle["builder_value_gross_wei"], "builder_value_gross_wei")
    min_builder = u256(bundle["builder_profit_minimum_wei"], "builder_profit_minimum_wei")
    u256(bundle["coinbase_tip_wei"], "coinbase_tip_wei")

    txs = bundle["txs"]
    if not isinstance(txs, list) or len(txs) != 2:
        raise ValueError("exactly DEPLOY_EXECUTOR + EXECUTE_LIQUIDATION are modeled")
    senders = []
    nonces = []
    required = 0
    for idx, tx in enumerate(txs):
        if not isinstance(tx, dict) or set(tx) != TX_FIELDS:
            raise ValueError(f"tx[{idx}]: invalid fields")
        if tx["purpose"] != TX_ORDER[idx]:
            raise ValueError("incorrect bundle execution order")
        senders.append(address(tx["from"]))
        nonces.append(u256(tx["nonce"], "nonce"))
        gas_limit = u256(tx["gas_limit"], "gas_limit")
        gas_cap = u256(tx["max_fee_per_gas_wei"], "max_fee_per_gas_wei")
        value = u256(tx["value_wei"], "value_wei")
        if not gas_limit or not gas_cap:
            raise ValueError("gas_limit and max_fee_per_gas_wei must be nonzero")
        required += gas_limit * gas_cap + value
        if required > UINT256_MAX:
            raise ValueError("sponsor exposure overflows uint256")
    if senders[0] != senders[1]:
        raise ValueError("one zero-ETH signer must control both bundle transactions")
    if nonces[1] != nonces[0] + 1:
        raise ValueError("nonce sequence is not consecutive")

    blockers = []
    if sender_initial or contract_initial:
        blockers.append("NONZERO_OPERATOR_OR_EXECUTOR_CAPITAL")
    if builder_advance < required:
        blockers.append("INSUFFICIENT_SPONSOR_ADVANCE_FOR_BOTH_TRANSACTIONS")
    if gross < builder_advance + min_builder:
        blockers.append("BUILDER_VALUE_INSUFFICIENT_AFTER_SPONSOR_COST")
    if not bundle["builder_sponsored_deployment_supported"]:
        blockers.append("BUILDER_SPONSORED_DEPLOYMENT_NOT_CONFIRMED")
    if not bundle["builder_value_measured"] or not bundle["builder_receipts_verified"]:
        blockers.append("BUILDER_NET_BALANCE_NOT_VERIFIED")
    if not bundle["morpho_callback_replayed"]:
        blockers.append("MORPHO_REAL_CALLBACK_NOT_REPLAYED")
    if not bundle["route_replayed"]:
        blockers.append("DEX_ROUTE_NOT_REPLAYED")
    if not bundle["target_tx_competition_replayed"]:
        blockers.append("CAPTURE_COMPETITION_NOT_REPLAYED")
    if bundle["evidence_type"] == "SYNTHETIC":
        blockers.append("SYNTHETIC_INPUT_NOT_REAL_BUNDLE")
    # The coinbase tip is NEVER added to gross builder value here.
    return BundleGate(
        "BLOCKED" if blockers else "MODEL_SCREEN_PASS_ONLY",
        blockers,
        required,
        gross - builder_advance,
        len(txs),
    )


def main() -> int:
    p = argparse.ArgumentParser(description="NQC zero-ETH bundle model: OFFLINE ONLY")
    p.add_argument("json_path", type=Path)
    args = p.parse_args()
    try:
        gate = check(json.loads(args.json_path.read_text(encoding="utf-8")))
        print(json.dumps(asdict(gate), indent=2, sort_keys=True))
        return 0 if gate.status == "MODEL_SCREEN_PASS_ONLY" else 2
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "INVALID_INPUT", "message": str(exc), "certified": False}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
