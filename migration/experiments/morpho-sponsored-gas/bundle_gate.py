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
ARCHITECTURES = {
    "OWN_EXECUTOR": TX_ORDER,
    "OWN_EXECUTOR_AND_ADAPTER": ("DEPLOY_ADAPTER", "DEPLOY_EXECUTOR", "EXECUTE_LIQUIDATION"),
    "DEPLOYED_BUNDLER3": ("EXECUTE_LIQUIDATION",),
}
REQUIRED = {
    "evidence_type", "chain_id", "prestate_block_hash", "builder", "sender_initial_eth_wei",
    "executor_initial_eth_wei", "builder_advance_wei", "builder_receipts_verified",
    "builder_value_gross_wei", "builder_profit_minimum_wei", "builder_value_measured",
    "route_replayed", "morpho_callback_replayed", "target_tx_competition_replayed",
    "txs", "builder_sponsored_deployment_supported", "coinbase_tip_wei",
    "sponsor_refund_recipient", "sponsor_refund_wei",
    "sponsor_topup_gas_limit", "sponsor_topup_max_fee_per_gas_wei",
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
    if any(c not in "0123456789abcdefABCDEF" for c in value[2:]):
        raise ValueError("EOA address must be hexadecimal without whitespace or signs")
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
    if any(c not in "0123456789abcdefABCDEF" for c in value[2:]):
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
    sponsor_refund_wei: int
    sponsor_topup_max_fee_wei: int
    transaction_count: int
    certified: bool = False
    live_executable: bool = False


def check(bundle: dict) -> BundleGate:
    if not isinstance(bundle, dict) or set(bundle) not in (REQUIRED, REQUIRED | {"architecture"}):
        raise ValueError("bundle fields must match exact schema")
    architecture = bundle.get("architecture", "OWN_EXECUTOR")
    if not isinstance(architecture, str) or architecture not in ARCHITECTURES:
        raise ValueError("unsupported architecture")
    order = ARCHITECTURES[architecture]
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
    direct_refund = u256(bundle["sponsor_refund_wei"], "sponsor_refund_wei")
    sponsor_addr = address(bundle["sponsor_refund_recipient"])
    # The builder's advance may itself require a funded transfer transaction.
    topup_gas = u256(bundle["sponsor_topup_gas_limit"], "sponsor_topup_gas_limit")
    topup_cap = u256(bundle["sponsor_topup_max_fee_per_gas_wei"], "sponsor_topup_max_fee_per_gas_wei")
    if not topup_gas or not topup_cap:
        raise ValueError("builder topup gas limit and fee cap must be positive")
    topup_cost = topup_gas * topup_cap
    if topup_cost > UINT256_MAX:
        raise ValueError("sponsor topup gas cost overflow")

    txs = bundle["txs"]
    if not isinstance(txs, list) or len(txs) != len(order):
        raise ValueError("transaction count must match the explicit architecture")
    senders = []
    nonces = []
    required = 0
    for idx, tx in enumerate(txs):
        if not isinstance(tx, dict) or set(tx) != TX_FIELDS:
            raise ValueError(f"tx[{idx}]: invalid fields")
        if tx["purpose"] != order[idx]:
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
    if len(set(senders)) != 1:
        raise ValueError("one zero-ETH signer must control all modeled transactions")
    if any(n != nonces[0] + i for i, n in enumerate(nonces)):
        raise ValueError("nonce sequence is not consecutive")
    if sponsor_addr == senders[0]:
        raise ValueError("operator cannot be its own external sponsor")

    blockers = []
    if sender_initial or contract_initial:
        blockers.append("NONZERO_OPERATOR_OR_EXECUTOR_CAPITAL")
    if builder_advance < required:
        blockers.append("INSUFFICIENT_SPONSOR_ADVANCE_FOR_BOTH_TRANSACTIONS" if len(txs)==2
                        else "INSUFFICIENT_SPONSOR_ADVANCE_FOR_ALL_TRANSACTIONS")
    if gross < builder_advance + topup_cost + min_builder:
        blockers.append("BUILDER_VALUE_INSUFFICIENT_AFTER_SPONSOR_COST")
    if gross <= builder_advance + topup_cost:
        blockers.append("BUILDER_BALANCE_MUST_INCREASE")
    # A block.coinbase tip goes to the block header's fee recipient. Its owner
    # and any subsequent proposer settlement are separate evidence requirements.
    # A direct refund is not confirmed until the builder-controlled recipient
    # and the independently measured receipts are authenticated.
    if direct_refund < builder_advance + topup_cost + min_builder:
        blockers.append("DIRECT_SPONSOR_REPAYMENT_INSUFFICIENT")
    if bundle["builder_value_measured"] and gross < direct_refund:
        blockers.append("DIRECT_REPAYMENT_EXCEEDS_BUILDER_RECEIPT_VALUE")
    if architecture != "DEPLOYED_BUNDLER3" and not bundle["builder_sponsored_deployment_supported"]:
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
        gross - builder_advance - topup_cost,
        direct_refund,
        topup_cost,
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
