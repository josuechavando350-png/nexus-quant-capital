"""Offline Pareto research prioritizer for Omega Census long-tail discovery.

This module ranks *research coverage* only. It does not estimate profit, capture
probability, GO/NO-GO, or authorize signing, broadcasting, spending, or phases.
"""
from __future__ import annotations

import copy
import re
from integrity import canonical, digest

SCHEMA = "nqc.omega.long-tail-prioritizer.v1"
SCOPE = "CENSUS_OFFLINE_RESEARCH_PRIORITY_ONLY"
HEX32 = re.compile(r"^[0-9a-f]{64}$")
UINT = re.compile(r"^(?:0|[1-9][0-9]*)$")
AUTHORITY_KEYS = {
    "can_sign", "can_broadcast", "can_spend", "phase_advance_authorized",
    "census_closed",
}
TOP_KEYS = {
    "schema", "record_scope", "candidates", "authorities",
    "priority_commitment_sha256",
}
CANDIDATE_KEYS = {
    "market_id", "chain_id", "is_l2", "market_age_blocks",
    "market_size_usd_wad", "route_complexity_steps",
    "source_commitment_sha256",
}


def _hex32(value: object) -> bool:
    return isinstance(value, str) and HEX32.fullmatch(value) is not None


def _uint(value: object, *, positive: bool = False) -> bool:
    if not isinstance(value, str) or UINT.fullmatch(value) is None:
        return False
    return not positive or int(value) > 0


def _canonical_candidates(values: list[dict]) -> list[dict]:
    return sorted((copy.deepcopy(v) for v in values), key=lambda item: item["market_id"])


def validate_priority_set(value: object) -> list[str]:
    errors: list[str] = []
    if type(value) is not dict:
        return ["priority_set_not_object"]
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

    candidates = value.get("candidates")
    seen = set()
    if type(candidates) is not list or not candidates:
        errors.append("candidates_invalid")
    else:
        for candidate in candidates:
            if type(candidate) is not dict or set(candidate) != CANDIDATE_KEYS:
                errors.append("candidate_shape_invalid")
                continue
            market_id = candidate["market_id"]
            if not _hex32(market_id):
                errors.append("market_id_invalid")
            elif market_id in seen:
                errors.append("duplicate_market")
            seen.add(market_id)
            if type(candidate["chain_id"]) is not int or candidate["chain_id"] <= 0:
                errors.append("chain_id_invalid")
            if type(candidate["is_l2"]) is not bool:
                errors.append("is_l2_invalid")
            if not _uint(candidate["market_age_blocks"]):
                errors.append("market_age_blocks_invalid")
            if not _uint(candidate["market_size_usd_wad"]):
                errors.append("market_size_invalid")
            if not _uint(candidate["route_complexity_steps"], positive=True):
                errors.append("route_complexity_invalid")
            if not _hex32(candidate["source_commitment_sha256"]):
                errors.append("source_commitment_invalid")
        if all(type(item) is dict and set(item) == CANDIDATE_KEYS for item in candidates):
            if candidates != _canonical_candidates(candidates):
                errors.append("candidates_not_canonically_sorted")

    commitment = value.get("priority_commitment_sha256")
    if _hex32(commitment):
        unsigned = {key: val for key, val in value.items() if key != "priority_commitment_sha256"}
        if commitment != digest(canonical(unsigned)):
            errors.append("priority_commitment_mismatch")
    else:
        errors.append("priority_commitment_invalid")
    return sorted(set(errors))


def seal_priority_set(candidates: list[dict]) -> dict:
    payload = {
        "schema": SCHEMA,
        "record_scope": SCOPE,
        "candidates": _canonical_candidates(candidates),
        "authorities": {
            "can_sign": False,
            "can_broadcast": False,
            "can_spend": False,
            "phase_advance_authorized": False,
            "census_closed": False,
        },
    }
    payload["priority_commitment_sha256"] = digest(canonical(payload))
    errors = validate_priority_set(payload)
    if errors:
        raise ValueError("invalid_priority_set:" + ",".join(errors))
    return payload


def _favours(left: dict, right: dict) -> tuple[bool, bool]:
    """Return (at_least_as_good, strictly_better) under declared research axes."""
    # Smaller/newer age and market size are favored; L2 and more route steps are
    # favored. These are research-discovery axes, not economic value estimates.
    comparisons = (
        int(left["market_age_blocks"]) <= int(right["market_age_blocks"]),
        int(left["market_size_usd_wad"]) <= int(right["market_size_usd_wad"]),
        int(left["route_complexity_steps"]) >= int(right["route_complexity_steps"]),
        int(left["is_l2"]) >= int(right["is_l2"]),
    )
    strict = (
        int(left["market_age_blocks"]) < int(right["market_age_blocks"])
        or int(left["market_size_usd_wad"]) < int(right["market_size_usd_wad"])
        or int(left["route_complexity_steps"]) > int(right["route_complexity_steps"])
        or int(left["is_l2"]) > int(right["is_l2"])
    )
    return all(comparisons), strict


def dominates(left: dict, right: dict) -> bool:
    at_least, strict = _favours(left, right)
    return at_least and strict


class LongTailPrioritizer:
    def __init__(self, priority_set: dict):
        errors = validate_priority_set(priority_set)
        if errors:
            raise ValueError("invalid_priority_set:" + ",".join(errors))
        self._set = copy.deepcopy(priority_set)
        self._by_id = {item["market_id"]: item for item in priority_set["candidates"]}

    @property
    def commitment(self) -> str:
        return self._set["priority_commitment_sha256"]

    def pareto_fronts(self) -> list[list[str]]:
        """Return deterministic non-dominated research layers, no scalar score."""
        remaining = dict(self._by_id)
        fronts: list[list[str]] = []
        while remaining:
            front = []
            ids = sorted(remaining)
            for market_id in ids:
                item = remaining[market_id]
                if not any(
                    other_id != market_id and dominates(remaining[other_id], item)
                    for other_id in ids
                ):
                    front.append(market_id)
            if not front:
                raise ValueError("pareto_progress_failure")
            fronts.append(front)
            for market_id in front:
                del remaining[market_id]
        return fronts

    def research_queue(self) -> list[dict]:
        queue = []
        for rank, front in enumerate(self.pareto_fronts(), start=1):
            for market_id in front:
                item = self._by_id[market_id]
                queue.append({
                    "pareto_layer": rank,
                    "market_id": market_id,
                    "chain_id": item["chain_id"],
                    "research_only": True,
                    "economic_score": None,
                    "profitability_claimed": False,
                })
        return queue

    def explain_pair(self, left_id: str, right_id: str) -> dict:
        if left_id not in self._by_id or right_id not in self._by_id:
            raise ValueError("unknown_market")
        if left_id == right_id:
            raise ValueError("distinct_markets_required")
        left = self._by_id[left_id]
        right = self._by_id[right_id]
        return {
            "left_dominates_right": dominates(left, right),
            "right_dominates_left": dominates(right, left),
            "axes": {
                "newer_market": "lower_market_age_blocks_is_favored",
                "smaller_market": "lower_market_size_usd_wad_is_favored",
                "l2": "true_is_favored",
                "route_complexity": "higher_route_complexity_steps_is_favored",
            },
            "economic_score": None,
        }
