"""Evidence-driven, bounded property fuzzing of the actual NQC capacity solver.

DIABLO's pinned scope and audit components gate and journal *every* case.
The deliberately independent exhaustive oracle and metamorphic properties
verify NQC's results. This is NOT EVM/transaction fuzzing, exploitation,
or a bounty finding; all inputs are synthetic numerical records.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import random
from pathlib import Path
import uuid

from .native_runtime import load_components, source_inventory
from .local_lab import independent_reference, _check_native_result, _row, WAD
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

MAX_CASES = 256
ARTIFACT_FILES = {"fuzz-result.json", "fuzz-cases.json", "diablo-fuzz-audit.json", "fuzz-provenance.json"}
KINDS = ("PROTOCOL_MARKET_CAP", "FLASH_CAPITAL", "DEX_LIQUIDITY", "GAS_FUNDING")


def validate_parameters(seed: int, cases: int) -> None:
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError("seed must be an unsigned 64-bit integer")
    if type(cases) is not int or not 1 <= cases <= MAX_CASES:
        raise ValueError(f"cases must be in [1, {MAX_CASES}]")


def make_case(seed: int, index: int) -> list[dict]:
    """Stateless PRNG by case index; replay does not depend on execution order."""
    if type(index) is not int or index < 0:
        raise ValueError("case index must be nonnegative")
    validate_parameters(seed, 1)
    payload = seed.to_bytes(8, "big") + index.to_bytes(8, "big")
    rng = random.Random(int.from_bytes(hashlib.sha256(b"SH-FUZZ-1" + payload).digest(), "big"))
    n = rng.randint(1, 8)
    resources = rng.randint(1, 4)
    caps = {(KINDS[k % len(KINDS)], f"resource-{k}"): rng.randint(2, 20)
            for k in range(resources)}
    result = []
    for i in range(n):
        start = rng.randint(0, 6)
        end = rng.randint(start + 1, 10)
        size = rng.randint(1, min(resources, 3))
        keys = rng.sample(list(caps), size)
        claims = [{"resource_kind": kind, "resource_id": rid,
                   "amount": rng.randint(1, caps[(kind, rid)]), "capacity": caps[(kind, rid)]}
                  for kind, rid in keys]
        # Deliberate ties, zero values and large exact integers.
        value = rng.choice((0, 1, 2, 5, 10, 100, 10**9)) * WAD + rng.randint(0, 3)
        result.append({"opportunity_id": f"case{index:04d}-job{i:02d}",
                       "start_order": start, "end_order": end,
                       "success_path_value_usd_wad": value, "claims": claims})
    return result


def _invariants(solver, rows: list[dict], output: dict) -> dict:
    """Independent oracle + determinism + order-invariance + linearity."""
    oracle = independent_reference(rows)
    _check_native_result(output, oracle)
    permuted = solver(list(reversed(rows)))
    if permuted != output:
        raise ValueError("permutation invariance failed")
    scaled = [dict(row, success_path_value_usd_wad=row["success_path_value_usd_wad"] * 3)
              for row in rows]
    scaled_output = solver(scaled)
    scaled_oracle = independent_reference(scaled)
    _check_native_result(scaled_output, scaled_oracle)
    if (scaled_output["selected_opportunity_ids"] != output["selected_opportunity_ids"] or
        int(scaled_output["success_path_capacity_usd_wad"]) !=
            3 * int(output["success_path_capacity_usd_wad"])):
        raise ValueError("positive value scaling invariance failed")
    return oracle


def _negative_controls(solver) -> list[str]:
    baseline = _row("bad", 0, 1, WAD, 2)
    cases = {
        "duplicate-id": [baseline, dict(baseline)],
        "conflicting-cap": [baseline, dict(_row("other", 0, 1, WAD, 1), claims=[{"resource_kind": "PROTOCOL_MARKET_CAP", "resource_id": "fixture-capital", "amount": 1, "capacity": 11}])],
        "unsupported-kind": [dict(baseline, claims=[dict(baseline["claims"][0], resource_kind="UNKNOWN")])],
        "negative-value": [dict(baseline, success_path_value_usd_wad=-1)],
        "zero-interval": [dict(baseline, end_order=0)],
        "over-capacity": [dict(baseline, claims=[dict(baseline["claims"][0], amount=100)])],
        "empty-claims": [dict(baseline, claims=[])],
    }
    rejected = []
    for name, rows in cases.items():
        try:
            solver(rows)
        except ValueError:
            rejected.append(name)
        else:
            raise ValueError(f"NQC accepted invalid case: {name}")
    return rejected


def execute(seed: int, cases: int) -> dict[str, bytes]:
    validate_parameters(seed, cases)
    native = load_components()
    audit = native.audit.AuditLog()
    scope = native.scope.ScopeGuard(in_scope=["*.lab.invalid"],
                                   out_scope=["blocked.lab.invalid"], audit_log=audit)
    started = datetime.now(timezone.utc).isoformat()
    run_id = str(uuid.uuid4())
    audit.append("fuzz.start", {"id": run_id, "seed": seed, "cases": cases, "fixture_only": True})
    records = []
    for index in range(cases):
        rows = make_case(seed, index)
        target = native.models.Target(value=f"case-{index:04d}.lab.invalid",
                                      kind="fixture", chain="offline")
        scope.assert_allowed(target)
        audit.append("fuzz.case.start", {"case": index,
                                          "input_sha256": hashlib.sha256(canonical(rows)).hexdigest()})
        result = native.capacity.solve(rows)
        oracle = _invariants(native.capacity.solve, rows, result)
        records.append({"index": index, "input": rows, "nqc": result, "reference": oracle})
        audit.append("fuzz.case.pass", {"case": index,
                                         "nqc_commitment": result["commitment"],
                                         "reference_sha256": hashlib.sha256(canonical(oracle)).hexdigest()})
    denied = not scope.check(native.models.Target(value="blocked.lab.invalid", kind="fixture",
                                                 chain="offline")).allowed
    if not denied:
        raise ValueError("excluded synthetic scope admitted")
    negative = _negative_controls(native.capacity.solve)
    audit.append("fuzz.complete", {"id": run_id, "cases": cases,
                                   "negative_controls": negative, "vulnerability_confirmed": False})
    audit.assert_intact()
    summary = {
        "schema_version": 1, "status": "LOCAL_FUZZ_PASS", "run_id": run_id,
        "seed": seed, "cases": cases, "tested": cases, "failed": 0,
        "negative_controls": negative, "scope_negative_passed": True,
        "permutation_checks": cases, "scaling_checks": cases, "oracle_checks": cases,
        "started_at": started, "completed_at": datetime.now(timezone.utc).isoformat(),
        "vulnerability_confirmed": False, "execution_verified": False,
        "fixture_only": True, "forge_executed": False, "live_rpc_used": False,
        "audit_count": len(audit), "audit_head": audit.head,
        "source": "DIABLO.ScopeGuard+AuditLog/NQC.RMC016.solve",
    }
    return {
        "fuzz-result.json": canonical(summary),
        "fuzz-cases.json": canonical({"cases": records}),
        "diablo-fuzz-audit.json": canonical({"entries": [asdict(e) for e in audit.entries]}),
        "fuzz-provenance.json": canonical({"sources": source_inventory()}),
    }


def run_fuzz(out: Path, seed: int, cases: int) -> dict:
    if out.exists() or out.is_symlink():
        raise FileExistsError("fuzz output directory must not exist")
    payload = execute(seed, cases)
    write_new_bundle(out, payload)
    return verify_fuzz(out)


def verify_fuzz(root: Path) -> dict:
    """Recalculate every case with NQC and the independent oracle.

    SHA integrity alone cannot establish trustworthy computation: the verifier
    checks exact seeded inputs, recorded results and DIABLO's entire hash chain.
    """
    completion = strict_json(read_artifact(root, "COMPLETE.json"))
    if completion.get("schema_version") != 1 or set(completion.get("sha256", {})) != ARTIFACT_FILES:
        raise ValueError("incomplete fuzz bundle")
    parsed = {}
    for name, digest in completion["sha256"].items():
        raw = read_artifact(root, name)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("fuzz bundle hash mismatch")
        parsed[name] = strict_json(raw)
    meta = parsed["fuzz-result.json"]
    if (meta.get("status") != "LOCAL_FUZZ_PASS" or meta.get("fixture_only") is not True or
        meta.get("vulnerability_confirmed") is not False or
        meta.get("execution_verified") is not False or
        meta.get("forge_executed") is not False or meta.get("live_rpc_used") is not False):
        raise ValueError("synthetic lab cannot assert a live finding")
    seed, cases = meta.get("seed"), meta.get("cases")
    validate_parameters(seed, cases)
    if (meta.get("tested") != cases or meta.get("failed") != 0 or
        any(meta.get(k) != cases for k in ("permutation_checks", "scaling_checks", "oracle_checks"))):
        raise ValueError("fuzz summary coverage mismatch")
    native = load_components()
    if parsed["fuzz-provenance.json"] != {"sources": source_inventory()}:
        raise ValueError("fuzz source provenance mismatch")
    records = parsed["fuzz-cases.json"].get("cases")
    if type(records) is not list or len(records) != cases:
        raise ValueError("fuzz case count mismatch")
    for index, item in enumerate(records):
        rows = make_case(seed, index)
        if item.get("index") != index or item.get("input") != rows:
            raise ValueError("fuzz seeded input mismatch")
        current = native.capacity.solve(rows)
        reference = _invariants(native.capacity.solve, rows, current)
        if item.get("nqc") != current or item.get("reference") != reference:
            raise ValueError("fuzz computed result mismatch")
    negative = _negative_controls(native.capacity.solve)
    if (meta.get("negative_controls") != negative or meta.get("scope_negative_passed") is not True):
        raise ValueError("fuzz negative controls mismatch")
    entries = parsed["diablo-fuzz-audit.json"].get("entries")
    if type(entries) is not list or len(entries) != 3 * cases + 3 or meta.get("audit_count") != len(entries):
        raise ValueError("fuzz audit length mismatch")
    previous = "0" * 64
    for idx, item in enumerate(entries):
        event = native.audit.AuditEntry(**item)
        if event.index != idx or event.prev_hash != previous or event.recompute() != event.hash:
            raise ValueError("fuzz audit chain mismatch")
        previous = event.hash
    if (previous != meta.get("audit_head") or entries[0]["event"] != "fuzz.start" or
        entries[0]["data"] != {"id": meta["run_id"], "seed": seed, "cases": cases, "fixture_only": True} or
        entries[-1]["event"] != "fuzz.complete" or entries[-1]["data"].get("id") != meta["run_id"]):
        raise ValueError("fuzz audit envelope mismatch")
    for index, item in enumerate(records):
        checks = entries[1 + index * 3: 1 + (index + 1) * 3]
        if ([x["event"] for x in checks] != ["scope.check", "fuzz.case.start", "fuzz.case.pass"] or
            checks[0]["data"].get("decision") != "ALLOW" or
            checks[0]["data"].get("target") != f"case-{index:04d}.lab.invalid" or
            checks[1]["data"] != {"case": index, "input_sha256": hashlib.sha256(canonical(item["input"])).hexdigest()} or
            checks[2]["data"] != {"case": index, "nqc_commitment": item["nqc"]["commitment"],
                                  "reference_sha256": hashlib.sha256(canonical(item["reference"])).hexdigest()}):
            raise ValueError("fuzz audit case mismatch")
    if (entries[-2]["event"] != "scope.check" or entries[-2]["data"].get("decision") != "DENY" or
        entries[-2]["data"].get("target") != "blocked.lab.invalid"):
        raise ValueError("fuzz scope negative evidence mismatch")
    if entries[-1]["data"].get("negative_controls") != negative:
        raise ValueError("fuzz negative audit mismatch")
    return {"status": "LOCAL_FUZZ_PASS", "seed": seed, "cases_verified": cases,
            "oracle_checks": cases, "vulnerability_confirmed": False,
            "verification_level": "recomputed-native-and-independent-reference"}
