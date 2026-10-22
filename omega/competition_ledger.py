"""Offline per-transaction competitor/margin ledger for Omega Census.

Records historical market winners and observed economics without attributing
their outcomes to NQC. Unknown monetary fields remain null, never implicit zero.
"""
from __future__ import annotations

import copy
import re

from integrity import canonical, digest

SCHEMA = "nqc.omega.competition-ledger.v1"
SCOPE = "CENSUS_HISTORICAL_MARKET_LEDGER_ONLY"
HEX32 = re.compile(r"^[0-9a-f]{64}$")
HASH32 = re.compile(r"^0x[0-9a-f]{64}$")
ADDRESS = re.compile(r"^0x[0-9a-f]{40}$")
UINT = re.compile(r"^(?:0|[1-9][0-9]*)$")
WAD = 10**18
TOP_KEYS = {
    "schema", "record_scope", "records", "authorities",
    "ledger_commitment_sha256",
}
RECORD_KEYS = {
    "transaction_hash", "subject_id", "winner_address", "oracle_update_block",
    "winner_block", "liquidation_bonus_usd_wad", "builder_payment_usd_wad",
    "winner_gas_usd_wad", "other_observed_costs_usd_wad",
    "observed_costs_complete", "evidence_sha256",
}
AUTHORITY_KEYS = {
    "can_sign", "can_broadcast", "can_spend", "phase_advance_authorized",
    "census_closed", "nqc_profitability_proven",
}


def _hex32(value: object) -> bool:
    return isinstance(value, str) and HEX32.fullmatch(value) is not None


def _uint(value: object) -> bool:
    return isinstance(value, str) and UINT.fullmatch(value) is not None


def _canonical_records(records: list[dict]) -> list[dict]:
    return sorted((copy.deepcopy(r) for r in records), key=lambda r: r["transaction_hash"])


def validate_ledger(value: object) -> list[str]:
    errors: list[str] = []
    if type(value) is not dict:
        return ["ledger_not_object"]
    if set(value) != TOP_KEYS:
        errors.append("top_level_shape_invalid")
    if value.get("schema") != SCHEMA:
        errors.append("wrong_schema")
    if value.get("record_scope") != SCOPE:
        errors.append("wrong_scope")

    authorities = value.get("authorities")
    if type(authorities) is not dict or set(authorities) != AUTHORITY_KEYS:
        errors.append("authorities_shape_invalid")
    elif any(authorities[key] is not False for key in AUTHORITY_KEYS):
        errors.append("authority_forbidden")

    records = value.get("records")
    seen = set()
    if type(records) is not list or not records:
        errors.append("records_invalid")
    else:
        for record in records:
            if type(record) is not dict or set(record) != RECORD_KEYS:
                errors.append("record_shape_invalid")
                continue
            tx = record["transaction_hash"]
            if not isinstance(tx, str) or HASH32.fullmatch(tx) is None:
                errors.append("transaction_hash_invalid")
            elif tx in seen:
                errors.append("duplicate_transaction")
            seen.add(tx)
            if not _hex32(record["subject_id"]):
                errors.append("subject_id_invalid")
            if not isinstance(record["winner_address"], str) or ADDRESS.fullmatch(record["winner_address"]) is None:
                errors.append("winner_address_invalid")
            oracle_block = record["oracle_update_block"]
            winner_block = record["winner_block"]
            if type(oracle_block) is not int or oracle_block <= 0:
                errors.append("oracle_update_block_invalid")
            if type(winner_block) is not int or winner_block <= 0:
                errors.append("winner_block_invalid")
            if type(oracle_block) is int and type(winner_block) is int and winner_block < oracle_block:
                errors.append("winner_before_oracle")
            if type(record["observed_costs_complete"]) is not bool:
                errors.append("observed_costs_complete_invalid")
            for key in (
                "liquidation_bonus_usd_wad", "builder_payment_usd_wad",
                "winner_gas_usd_wad", "other_observed_costs_usd_wad",
            ):
                amount = record[key]
                if amount is not None and not _uint(amount):
                    errors.append(key + "_invalid")
            if record["observed_costs_complete"]:
                if any(record[key] is None for key in (
                    "liquidation_bonus_usd_wad", "builder_payment_usd_wad",
                    "winner_gas_usd_wad", "other_observed_costs_usd_wad",
                )):
                    errors.append("complete_record_missing_cost")
            if not _hex32(record["evidence_sha256"]):
                errors.append("evidence_invalid")
        if all(type(item) is dict and set(item) == RECORD_KEYS for item in records):
            if records != _canonical_records(records):
                errors.append("records_not_canonically_sorted")

    commitment = value.get("ledger_commitment_sha256")
    if _hex32(commitment):
        unsigned = {key: val for key, val in value.items() if key != "ledger_commitment_sha256"}
        if commitment != digest(canonical(unsigned)):
            errors.append("ledger_commitment_mismatch")
    else:
        errors.append("ledger_commitment_invalid")
    return sorted(set(errors))


def seal_ledger(records: list[dict]) -> dict:
    ledger = {
        "schema": SCHEMA,
        "record_scope": SCOPE,
        "records": _canonical_records(records),
        "authorities": {
            "can_sign": False,
            "can_broadcast": False,
            "can_spend": False,
            "phase_advance_authorized": False,
            "census_closed": False,
            "nqc_profitability_proven": False,
        },
    }
    ledger["ledger_commitment_sha256"] = digest(canonical(ledger))
    errors = validate_ledger(ledger)
    if errors:
        raise ValueError("invalid_ledger:" + ",".join(errors))
    return ledger


def transaction_metrics(record: dict) -> dict:
    probe = seal_ledger([record])["records"][0]
    delay = probe["winner_block"] - probe["oracle_update_block"]
    bonus = probe["liquidation_bonus_usd_wad"]
    builder = probe["builder_payment_usd_wad"]
    share = None
    if bonus is not None and builder is not None and int(bonus) > 0:
        share = str((int(builder) * WAD) // int(bonus))
    net = None
    if probe["observed_costs_complete"]:
        net = (
            int(probe["liquidation_bonus_usd_wad"])
            - int(probe["builder_payment_usd_wad"])
            - int(probe["winner_gas_usd_wad"])
            - int(probe["other_observed_costs_usd_wad"])
        )
        net = str(net)
    return {
        "transaction_hash": probe["transaction_hash"],
        "winner_address": probe["winner_address"],
        "blocks_from_oracle_to_winner": delay,
        "builder_payment_share_of_bonus_wad": share,
        "observed_winner_net_margin_usd_wad": net,
        "observed_costs_complete": probe["observed_costs_complete"],
        "nqc_execution": False,
        "nqc_realized_pnl_usd_wad": None,
    }


class CompetitionLedger:
    def __init__(self, ledger: dict):
        errors = validate_ledger(ledger)
        if errors:
            raise ValueError("invalid_ledger:" + ",".join(errors))
        self._ledger = copy.deepcopy(ledger)
        self._by_tx = {record["transaction_hash"]: record for record in ledger["records"]}

    @property
    def commitment(self) -> str:
        return self._ledger["ledger_commitment_sha256"]

    def metrics(self, transaction_hash: str) -> dict:
        if transaction_hash not in self._by_tx:
            raise ValueError("unknown_transaction")
        return transaction_metrics(self._by_tx[transaction_hash])

    def summary(self) -> dict:
        rows = [transaction_metrics(record) for record in self._ledger["records"]]
        complete = [row for row in rows if row["observed_costs_complete"]]
        shares = [int(row["builder_payment_share_of_bonus_wad"]) for row in rows
                  if row["builder_payment_share_of_bonus_wad"] is not None]
        delays = [row["blocks_from_oracle_to_winner"] for row in rows]
        return {
            "transaction_count": len(rows),
            "complete_cost_transaction_count": len(complete),
            "builder_share_observation_count": len(shares),
            "min_blocks_from_oracle_to_winner": min(delays) if delays else None,
            "max_blocks_from_oracle_to_winner": max(delays) if delays else None,
            "mean_builder_share_wad": str(sum(shares) // len(shares)) if shares else None,
            "nqc_profitability_proven": False,
            "current_market_claimed": False,
        }
