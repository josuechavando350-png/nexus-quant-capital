"""Exact offline liquidation-threshold index for Omega Census.

The index consumes already-derived threshold evidence. It does not invent oracle
prices, compute protocol liquidation math, sign, broadcast, spend, or close Census.
"""
from __future__ import annotations

import bisect
import copy
import re
from fractions import Fraction
from math import gcd

from integrity import canonical, digest

SCHEMA = "nqc.omega.liquidation-order-book.v1"
SCOPE = "CENSUS_OFFLINE_INDEX_ONLY"
HEX32 = re.compile(r"^[0-9a-f]{64}$")
HASH32 = re.compile(r"^0x[0-9a-f]{64}$")
UINT = re.compile(r"^(?:0|[1-9][0-9]*)$")
DIRECTIONS = {"AT_OR_BELOW", "AT_OR_ABOVE"}
AUTHORITY_KEYS = {
    "can_sign", "can_broadcast", "can_spend", "phase_advance_authorized",
    "census_closed",
}
TOP_KEYS = {
    "schema", "record_scope", "state_anchor", "entries", "authorities",
    "book_commitment_sha256",
}
ENTRY_KEYS = {
    "position_id", "oracle_id", "direction", "threshold_numerator",
    "threshold_denominator", "source_commitment_sha256",
}


def _uint(value: object, *, positive: bool = False) -> bool:
    if not isinstance(value, str) or UINT.fullmatch(value) is None:
        return False
    return not positive or int(value) > 0


def _hex32(value: object) -> bool:
    return isinstance(value, str) and HEX32.fullmatch(value) is not None


def normalize_entry(entry: dict) -> dict:
    """Return a canonical reduced rational threshold."""
    if type(entry) is not dict or set(entry) != ENTRY_KEYS:
        raise ValueError("entry_shape_invalid")
    if not _hex32(entry["position_id"]):
        raise ValueError("position_id_invalid")
    if not _hex32(entry["oracle_id"]):
        raise ValueError("oracle_id_invalid")
    if entry["direction"] not in DIRECTIONS:
        raise ValueError("direction_invalid")
    if not _uint(entry["threshold_numerator"], positive=True):
        raise ValueError("threshold_numerator_invalid")
    if not _uint(entry["threshold_denominator"], positive=True):
        raise ValueError("threshold_denominator_invalid")
    if not _hex32(entry["source_commitment_sha256"]):
        raise ValueError("source_commitment_invalid")
    numerator = int(entry["threshold_numerator"])
    denominator = int(entry["threshold_denominator"])
    common = gcd(numerator, denominator)
    out = copy.deepcopy(entry)
    out["threshold_numerator"] = str(numerator // common)
    out["threshold_denominator"] = str(denominator // common)
    return out


def _fraction(entry: dict) -> Fraction:
    return Fraction(int(entry["threshold_numerator"]), int(entry["threshold_denominator"]))


def _price(numerator: object, denominator: object) -> Fraction:
    if not _uint(numerator, positive=True) or not _uint(denominator, positive=True):
        raise ValueError("price_rational_invalid")
    return Fraction(int(numerator), int(denominator))


def validate_book(value: object) -> list[str]:
    errors: list[str] = []
    if type(value) is not dict:
        return ["book_not_object"]
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

    entries = value.get("entries")
    if type(entries) is not list:
        errors.append("entries_not_list")
    else:
        normalized = []
        positions = set()
        for entry in entries:
            try:
                item = normalize_entry(entry)
            except (ValueError, TypeError):
                errors.append("entry_invalid")
                continue
            if item != entry:
                errors.append("entry_not_canonical")
            if item["position_id"] in positions:
                errors.append("duplicate_position")
            positions.add(item["position_id"])
            normalized.append(item)
        expected = sorted(
            normalized,
            key=lambda e: (
                e["oracle_id"],
                e["direction"],
                _fraction(e),
                e["position_id"],
            ),
        )
        if entries != expected:
            errors.append("entries_not_canonically_sorted")

    commitment = value.get("book_commitment_sha256")
    if _hex32(commitment):
        unsigned = {key: val for key, val in value.items() if key != "book_commitment_sha256"}
        if commitment != digest(canonical(unsigned)):
            errors.append("book_commitment_mismatch")
    else:
        errors.append("book_commitment_invalid")
    return sorted(set(errors))


def seal_book(state_anchor: dict, entries: list[dict]) -> dict:
    normalized = [normalize_entry(entry) for entry in entries]
    normalized.sort(
        key=lambda e: (e["oracle_id"], e["direction"], _fraction(e), e["position_id"])
    )
    book = {
        "schema": SCHEMA,
        "record_scope": SCOPE,
        "state_anchor": copy.deepcopy(state_anchor),
        "entries": normalized,
        "authorities": {
            "can_sign": False,
            "can_broadcast": False,
            "can_spend": False,
            "phase_advance_authorized": False,
            "census_closed": False,
        },
    }
    book["book_commitment_sha256"] = digest(canonical(book))
    errors = validate_book(book)
    if errors:
        raise ValueError("invalid_book:" + ",".join(errors))
    return book


class LiquidationOrderBook:
    def __init__(self, book: dict):
        errors = validate_book(book)
        if errors:
            raise ValueError("invalid_book:" + ",".join(errors))
        self._book = copy.deepcopy(book)
        self._groups: dict[tuple[str, str], list[tuple[Fraction, str, dict]]] = {}
        for entry in book["entries"]:
            key = (entry["oracle_id"], entry["direction"])
            self._groups.setdefault(key, []).append((_fraction(entry), entry["position_id"], entry))
        for values in self._groups.values():
            values.sort(key=lambda item: (item[0], item[1]))

    @property
    def commitment(self) -> str:
        return self._book["book_commitment_sha256"]

    def active_at(self, oracle_id: str, numerator: str, denominator: str) -> list[str]:
        if not _hex32(oracle_id):
            raise ValueError("oracle_id_invalid")
        price = _price(numerator, denominator)
        out = []
        below = self._groups.get((oracle_id, "AT_OR_BELOW"), [])
        above = self._groups.get((oracle_id, "AT_OR_ABOVE"), [])
        for threshold, position, _ in below:
            if price <= threshold:
                out.append(position)
        for threshold, position, _ in above:
            if price >= threshold:
                out.append(position)
        return sorted(out)

    def crossed(self, oracle_id: str, previous_numerator: str, previous_denominator: str,
                current_numerator: str, current_denominator: str) -> list[str]:
        """Return newly crossed positions in the exact encounter order."""
        if not _hex32(oracle_id):
            raise ValueError("oracle_id_invalid")
        previous = _price(previous_numerator, previous_denominator)
        current = _price(current_numerator, current_denominator)
        if current == previous:
            return []
        if current < previous:
            values = self._groups.get((oracle_id, "AT_OR_BELOW"), [])
            # Newly liquidatable: current <= threshold < previous.
            hits = [(threshold, position) for threshold, position, _ in values
                    if current <= threshold < previous]
            hits.sort(key=lambda item: (item[0], item[1]), reverse=True)
            return [position for _, position in hits]
        values = self._groups.get((oracle_id, "AT_OR_ABOVE"), [])
        # Newly liquidatable: previous < threshold <= current.
        hits = [(threshold, position) for threshold, position, _ in values
                if previous < threshold <= current]
        hits.sort(key=lambda item: (item[0], item[1]))
        return [position for _, position in hits]

    def thresholds(self, oracle_id: str, direction: str) -> list[dict]:
        if not _hex32(oracle_id):
            raise ValueError("oracle_id_invalid")
        if direction not in DIRECTIONS:
            raise ValueError("direction_invalid")
        return [copy.deepcopy(entry) for _, _, entry in self._groups.get((oracle_id, direction), [])]
