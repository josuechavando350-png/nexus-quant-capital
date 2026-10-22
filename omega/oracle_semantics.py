"""Fail-closed offline oracle-semantics registry for Omega Census.

It distinguishes direct spot-price exposure from exchange-rate accounting only
when semantics are explicitly evidence-bound. It never guesses from token names.
"""
from __future__ import annotations

import copy
import re

from integrity import canonical, digest

SCHEMA = "nqc.omega.oracle-semantics.v1"
SCOPE = "CENSUS_OFFLINE_ORACLE_SEMANTICS_ONLY"
HEX32 = re.compile(r"^[0-9a-f]{64}$")
HASH32 = re.compile(r"^0x[0-9a-f]{64}$")
ORACLE_CLASSES = {"MARKET_PRICE", "EXCHANGE_RATE"}
AUTHORITY_KEYS = {
    "can_sign", "can_broadcast", "can_spend", "phase_advance_authorized",
    "census_closed",
}
TOP_KEYS = {
    "schema", "record_scope", "state_anchor", "oracles", "markets", "authorities",
    "registry_commitment_sha256",
}
ORACLE_KEYS = {
    "oracle_id", "semantic_class", "base_asset_id", "quote_asset_id",
    "source_commitment_sha256",
}
MARKET_KEYS = {
    "market_id", "collateral_oracle_id", "debt_oracle_id",
    "source_commitment_sha256",
}


def _hex32(value: object) -> bool:
    return isinstance(value, str) and HEX32.fullmatch(value) is not None


def _sort_oracles(values: list[dict]) -> list[dict]:
    return sorted((copy.deepcopy(v) for v in values), key=lambda x: x["oracle_id"])


def _sort_markets(values: list[dict]) -> list[dict]:
    return sorted((copy.deepcopy(v) for v in values), key=lambda x: x["market_id"])


def validate_registry(value: object) -> list[str]:
    errors: list[str] = []
    if type(value) is not dict:
        return ["registry_not_object"]
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

    anchor = value.get("state_anchor")
    if type(anchor) is not dict or set(anchor) != {"chain_id", "block_number", "block_hash"}:
        errors.append("anchor_shape_invalid")
    else:
        if type(anchor["chain_id"]) is not int or anchor["chain_id"] <= 0:
            errors.append("chain_id_invalid")
        if type(anchor["block_number"]) is not int or anchor["block_number"] <= 0:
            errors.append("block_number_invalid")
        if not isinstance(anchor["block_hash"], str) or HASH32.fullmatch(anchor["block_hash"]) is None:
            errors.append("block_hash_invalid")

    oracles = value.get("oracles")
    oracle_by_id: dict[str, dict] = {}
    if type(oracles) is not list or not oracles:
        errors.append("oracles_invalid")
    else:
        for oracle in oracles:
            if type(oracle) is not dict or set(oracle) != ORACLE_KEYS:
                errors.append("oracle_shape_invalid")
                continue
            oid = oracle["oracle_id"]
            if not _hex32(oid):
                errors.append("oracle_id_invalid")
            elif oid in oracle_by_id:
                errors.append("duplicate_oracle")
            else:
                oracle_by_id[oid] = oracle
            if oracle["semantic_class"] not in ORACLE_CLASSES:
                errors.append("oracle_semantic_class_invalid")
            if not _hex32(oracle["base_asset_id"]) or not _hex32(oracle["quote_asset_id"]):
                errors.append("oracle_asset_id_invalid")
            if oracle["base_asset_id"] == oracle["quote_asset_id"]:
                errors.append("oracle_asset_pair_invalid")
            if not _hex32(oracle["source_commitment_sha256"]):
                errors.append("oracle_evidence_invalid")
        if all(type(v) is dict and set(v) == ORACLE_KEYS for v in oracles):
            if oracles != _sort_oracles(oracles):
                errors.append("oracles_not_canonically_sorted")

    markets = value.get("markets")
    seen_markets = set()
    if type(markets) is not list:
        errors.append("markets_not_list")
    else:
        for market in markets:
            if type(market) is not dict or set(market) != MARKET_KEYS:
                errors.append("market_shape_invalid")
                continue
            mid = market["market_id"]
            if not _hex32(mid):
                errors.append("market_id_invalid")
            elif mid in seen_markets:
                errors.append("duplicate_market")
            seen_markets.add(mid)
            for key in ("collateral_oracle_id", "debt_oracle_id"):
                oid = market[key]
                if not _hex32(oid):
                    errors.append("market_oracle_id_invalid")
                elif oid not in oracle_by_id:
                    errors.append("market_oracle_unresolved")
            if not _hex32(market["source_commitment_sha256"]):
                errors.append("market_evidence_invalid")
        if all(type(v) is dict and set(v) == MARKET_KEYS for v in markets):
            if markets != _sort_markets(markets):
                errors.append("markets_not_canonically_sorted")

    commitment = value.get("registry_commitment_sha256")
    if _hex32(commitment):
        unsigned = {key: val for key, val in value.items() if key != "registry_commitment_sha256"}
        if commitment != digest(canonical(unsigned)):
            errors.append("registry_commitment_mismatch")
    else:
        errors.append("registry_commitment_invalid")
    return sorted(set(errors))


def seal_registry(state_anchor: dict, oracles: list[dict], markets: list[dict]) -> dict:
    registry = {
        "schema": SCHEMA,
        "record_scope": SCOPE,
        "state_anchor": copy.deepcopy(state_anchor),
        "oracles": _sort_oracles(oracles),
        "markets": _sort_markets(markets),
        "authorities": {
            "can_sign": False,
            "can_broadcast": False,
            "can_spend": False,
            "phase_advance_authorized": False,
            "census_closed": False,
        },
    }
    registry["registry_commitment_sha256"] = digest(canonical(registry))
    errors = validate_registry(registry)
    if errors:
        raise ValueError("invalid_registry:" + ",".join(errors))
    return registry


class OracleSemanticsRegistry:
    def __init__(self, registry: dict):
        errors = validate_registry(registry)
        if errors:
            raise ValueError("invalid_registry:" + ",".join(errors))
        self._registry = copy.deepcopy(registry)
        self._oracles = {item["oracle_id"]: item for item in registry["oracles"]}
        self._markets = {item["market_id"]: item for item in registry["markets"]}

    @property
    def commitment(self) -> str:
        return self._registry["registry_commitment_sha256"]

    def oracle_semantics(self, oracle_id: str) -> dict:
        if oracle_id not in self._oracles:
            raise ValueError("unknown_oracle")
        item = self._oracles[oracle_id]
        semantic = item["semantic_class"]
        return {
            "oracle_id": oracle_id,
            "semantic_class": semantic,
            "spot_depeg_directly_reflected": semantic == "MARKET_PRICE",
            "note": (
                "SPOT_DEPEG_DIRECTLY_REFLECTED"
                if semantic == "MARKET_PRICE"
                else "SPOT_DEPEG_NOT_DIRECTLY_REFLECTED_BY_THIS_ORACLE"
            ),
        }

    def market_depeg_exposure(self, market_id: str) -> dict:
        if market_id not in self._markets:
            raise ValueError("unknown_market")
        market = self._markets[market_id]
        collateral = self.oracle_semantics(market["collateral_oracle_id"])
        debt = self.oracle_semantics(market["debt_oracle_id"])
        return {
            "market_id": market_id,
            "collateral": collateral,
            "debt": debt,
            "any_direct_spot_exposure": (
                collateral["spot_depeg_directly_reflected"]
                or debt["spot_depeg_directly_reflected"]
            ),
        }
