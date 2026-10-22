"""Offline three-way truth parity engine for Omega Census.

It compares independently evidenced event/storage reconstruction, direct
contract reads and EVM replay at one exact state anchor. It cannot certify PFT,
trade, sign, broadcast, spend, close Census or advance phases.
"""
from __future__ import annotations

import copy
import re

from integrity import canonical, digest

SCHEMA = "nqc.omega.truth-triad.v1"
SCOPE = "CENSUS_OFFLINE_THREE_WAY_PARITY_ONLY"
HEX32 = re.compile(r"^[0-9a-f]{64}$")
HASH32 = re.compile(r"^0x[0-9a-f]{64}$")
LANES = ("EVENT_STORAGE_RECONSTRUCTION", "DIRECT_CONTRACT_READ", "EVM_REPLAY")
TOP_KEYS = {
    "schema", "record_scope", "subject_id", "state_anchor",
    "semantics_commitment_sha256", "lanes", "authorities",
    "triad_commitment_sha256",
}
LANE_KEYS = {
    "lane", "result_commitment_sha256", "source_commitment_sha256",
    "producer_commitment_sha256",
}
AUTHORITY_KEYS = {
    "can_sign", "can_broadcast", "can_spend", "phase_advance_authorized",
    "census_closed", "protocol_fork_truth_certified",
}


def _hex32(value: object) -> bool:
    return isinstance(value, str) and HEX32.fullmatch(value) is not None


def _canonical_lanes(values: list[dict]) -> list[dict]:
    order = {lane: index for index, lane in enumerate(LANES)}
    return sorted((copy.deepcopy(v) for v in values), key=lambda item: order.get(item.get("lane"), 999))


def validate_triad(value: object) -> list[str]:
    errors: list[str] = []
    if type(value) is not dict:
        return ["triad_not_object"]
    if set(value) != TOP_KEYS:
        errors.append("top_level_shape_invalid")
    if value.get("schema") != SCHEMA:
        errors.append("wrong_schema")
    if value.get("record_scope") != SCOPE:
        errors.append("wrong_scope")
    if not _hex32(value.get("subject_id")):
        errors.append("subject_id_invalid")
    if not _hex32(value.get("semantics_commitment_sha256")):
        errors.append("semantics_commitment_invalid")

    anchor = value.get("state_anchor")
    if type(anchor) is not dict or set(anchor) != {"chain_id", "block_number", "block_hash", "state_root"}:
        errors.append("anchor_shape_invalid")
    else:
        if type(anchor["chain_id"]) is not int or anchor["chain_id"] <= 0:
            errors.append("chain_id_invalid")
        if type(anchor["block_number"]) is not int or anchor["block_number"] <= 0:
            errors.append("block_number_invalid")
        for key in ("block_hash", "state_root"):
            if not isinstance(anchor[key], str) or HASH32.fullmatch(anchor[key]) is None:
                errors.append(key + "_invalid")

    authorities = value.get("authorities")
    if type(authorities) is not dict or set(authorities) != AUTHORITY_KEYS:
        errors.append("authorities_shape_invalid")
    elif any(authorities[key] is not False for key in AUTHORITY_KEYS):
        errors.append("authority_forbidden")

    lanes = value.get("lanes")
    seen = set()
    source_commitments = set()
    producer_commitments = set()
    if type(lanes) is not list or len(lanes) != 3:
        errors.append("exactly_three_lanes_required")
    else:
        for lane in lanes:
            if type(lane) is not dict or set(lane) != LANE_KEYS:
                errors.append("lane_shape_invalid")
                continue
            name = lane["lane"]
            if name not in LANES:
                errors.append("lane_name_invalid")
            elif name in seen:
                errors.append("duplicate_lane")
            seen.add(name)
            for key in ("result_commitment_sha256", "source_commitment_sha256", "producer_commitment_sha256"):
                if not _hex32(lane[key]):
                    errors.append(key + "_invalid")
            source_commitments.add(lane.get("source_commitment_sha256"))
            producer_commitments.add(lane.get("producer_commitment_sha256"))
        if seen != set(LANES):
            errors.append("lane_set_incomplete")
        if len(source_commitments) != 3:
            errors.append("source_independence_not_proven")
        if len(producer_commitments) != 3:
            errors.append("producer_independence_not_proven")
        if all(type(item) is dict and set(item) == LANE_KEYS for item in lanes):
            if lanes != _canonical_lanes(lanes):
                errors.append("lanes_not_canonically_sorted")

    commitment = value.get("triad_commitment_sha256")
    if _hex32(commitment):
        unsigned = {key: val for key, val in value.items() if key != "triad_commitment_sha256"}
        if commitment != digest(canonical(unsigned)):
            errors.append("triad_commitment_mismatch")
    else:
        errors.append("triad_commitment_invalid")
    return sorted(set(errors))


def seal_triad(subject_id: str, state_anchor: dict, semantics_commitment_sha256: str,
               lanes: list[dict]) -> dict:
    triad = {
        "schema": SCHEMA,
        "record_scope": SCOPE,
        "subject_id": subject_id,
        "state_anchor": copy.deepcopy(state_anchor),
        "semantics_commitment_sha256": semantics_commitment_sha256,
        "lanes": _canonical_lanes(lanes),
        "authorities": {
            "can_sign": False,
            "can_broadcast": False,
            "can_spend": False,
            "phase_advance_authorized": False,
            "census_closed": False,
            "protocol_fork_truth_certified": False,
        },
    }
    triad["triad_commitment_sha256"] = digest(canonical(triad))
    errors = validate_triad(triad)
    if errors:
        raise ValueError("invalid_triad:" + ",".join(errors))
    return triad


def evaluate_triad(triad: dict) -> dict:
    errors = validate_triad(triad)
    if errors:
        raise ValueError("invalid_triad:" + ",".join(errors))
    results = {lane["lane"]: lane["result_commitment_sha256"] for lane in triad["lanes"]}
    unique = sorted(set(results.values()))
    parity = len(unique) == 1
    mismatch = [] if parity else [
        {"lane": lane, "result_commitment_sha256": results[lane]}
        for lane in LANES
    ]
    return {
        "subject_id": triad["subject_id"],
        "state_anchor": copy.deepcopy(triad["state_anchor"]),
        "parity": parity,
        "verdict": "PARITY" if parity else "MISMATCH",
        "agreed_result_commitment_sha256": unique[0] if parity else None,
        "mismatch_ledger": mismatch,
        "certification_claimed": False,
        "phase_advance_authorized": False,
    }


def evaluate_batch(triads: list[dict], expected_subject_ids: list[str]) -> dict:
    if type(triads) is not list or type(expected_subject_ids) is not list or not expected_subject_ids:
        raise ValueError("batch_inputs_invalid")
    if any(not _hex32(item) for item in expected_subject_ids):
        raise ValueError("expected_subject_id_invalid")
    if len(expected_subject_ids) != len(set(expected_subject_ids)):
        raise ValueError("duplicate_expected_subject")
    by_subject = {}
    results = []
    for triad in triads:
        result = evaluate_triad(triad)
        subject = result["subject_id"]
        if subject in by_subject:
            raise ValueError("duplicate_subject_triad")
        by_subject[subject] = result
        results.append(result)
    expected = set(expected_subject_ids)
    actual = set(by_subject)
    if actual != expected:
        raise ValueError("batch_coverage_mismatch")
    results.sort(key=lambda item: item["subject_id"])
    failures = [item["subject_id"] for item in results if not item["parity"]]
    return {
        "subjects": results,
        "all_parity": not failures,
        "failed_subject_ids": failures,
        "coverage_complete": True,
        "certification_claimed": False,
        "phase_advance_authorized": False,
    }
