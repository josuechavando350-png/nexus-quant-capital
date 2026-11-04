"""Fixed local regression circuit: DIABLO scope -> NQC solve -> DIABLO audit.

No target, PoC, RPC or external-program input. Monetary values are synthetic
integer USD-wad fixtures, never live prices, loss estimates or bounty claims.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from itertools import combinations
from pathlib import Path
import uuid

from .native_runtime import load_components, source_inventory
from .audit_links import verify_audit_links
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

WAD = 10**18
BUNDLE_FILES = {"lab-result.json", "nqc-results.json", "diablo-audit.json", "source-provenance.json"}


def _row(name: str, start: int, end: int, value: int, amount: int, resource: str = "fixture-capital") -> dict:
    return {"opportunity_id": name, "start_order": start, "end_order": end,
            "success_path_value_usd_wad": value,
            "claims": [{"resource_kind": "PROTOCOL_MARKET_CAP", "resource_id": resource,
                        "amount": amount, "capacity": 10}]}


def fixture_cases() -> dict[str, list[dict]]:
    """Fresh built-in inputs; deliberately not an API for user-supplied targets."""
    return {
        "overlap": [_row("a", 0, 3, 110*WAD, 8), _row("b", 0, 3, 80*WAD, 6), _row("c", 0, 3, 70*WAD, 4)],
        "adjacent": [_row("a", 0, 1, 7*WAD, 10), _row("b", 1, 2, 9*WAD, 10)],
        "tie": [_row("a", 0, 2, 5*WAD, 10), _row("b", 0, 2, 5*WAD, 10)],
        "large-integers": [_row("a", 0, 1, 10**36+17, 10), _row("b", 0, 1, 10**36+18, 10)],
        "resources": [_row("a", 0, 2, 2*WAD, 10, "x"), _row("b", 0, 2, 3*WAD, 10, "y"),
                      _row("c", 0, 2, WAD, 10, "x")],
    }


def independent_reference(rows: list[dict]) -> dict:
    """Small exhaustive reference, independent of NQC parsing/feasibility code."""
    if type(rows) is not list or not 1 <= len(rows) <= 8:
        raise ValueError("reference limited to 1..8 local numerical records")
    names, caps = set(), {}
    for row in rows:
        name = row["opportunity_id"]
        if type(name) is not str or not name or name in names:
            raise ValueError("nonunique local record")
        names.add(name)
        for key in ("start_order", "end_order", "success_path_value_usd_wad"):
            if type(row[key]) is not int or row[key] < 0:
                raise ValueError("unsigned exact integer required")
        if row["end_order"] <= row["start_order"] or not row["claims"]:
            raise ValueError("invalid interval or missing claims")
        seen = set()
        for claim in row["claims"]:
            key = (claim["resource_kind"], claim["resource_id"])
            if key in seen:
                raise ValueError("duplicate resource")
            seen.add(key)
            a, cap = claim["amount"], claim["capacity"]
            if type(a) is not int or type(cap) is not int or not 0 < a <= cap:
                raise ValueError("invalid exact capacity")
            if key in caps and caps[key] != cap:
                raise ValueError("inconsistent capacity")
            caps[key] = cap
    times = sorted({r[t] for r in rows for t in ("start_order", "end_order")})
    best_value, best_names = 0, ()
    for count in range(len(rows)+1):
        for subset in combinations(rows, count):
            feasible = True
            for t in times:
                use = {}
                for row in subset:
                    if row["start_order"] <= t < row["end_order"]:
                        for claim in row["claims"]:
                            key = (claim["resource_kind"], claim["resource_id"])
                            use[key] = use.get(key, 0) + claim["amount"]
                if any(amount > caps[key] for key, amount in use.items()):
                    feasible = False
                    break
            if feasible:
                value = sum(r["success_path_value_usd_wad"] for r in subset)
                ids = tuple(sorted(r["opportunity_id"] for r in subset))
                if value > best_value or (value == best_value and ids < best_names):
                    best_value, best_names = value, ids
    return {"selected_opportunity_ids": list(best_names), "success_path_capacity_usd_wad": str(best_value)}


def _check_native_result(result: dict, reference: dict) -> None:
    if any(result.get(k) != v for k, v in reference.items()):
        raise ValueError("native NQC/reference disagreement")
    body = {k: v for k, v in result.items() if k != "commitment"}
    if result.get("commitment") != "0x" + hashlib.sha256(canonical(body)).hexdigest():
        raise ValueError("NQC commitment mismatch")
    if (result.get("status") != "RMC016_CAPACITY_FOUNDATION_VALID" or
            result.get("global_optimum_claimed") is not True or
            result.get("capture_probability") != "UNCALIBRATED" or
            result.get("selected_opportunity_count") != len(reference["selected_opportunity_ids"])):
        raise ValueError("unexpected native result semantics")


def execute_local() -> dict[str, bytes]:
    """Execute real pinned functions on fixed benign fixtures; no artifact inputs."""
    native = load_components()
    started = datetime.now(timezone.utc).isoformat()
    run_id = str(uuid.uuid4())
    audit = native.audit.AuditLog()
    guard = native.scope.ScopeGuard(in_scope=["*.lab.invalid"], out_scope=["blocked.lab.invalid"], audit_log=audit)
    results = []
    audit.append("lab.start", {"run_id": run_id, "fixture_only": True})
    for name, rows in fixture_cases().items():
        target = native.models.Target(value=name + ".lab.invalid", kind="fixture", chain="offline")
        guard.assert_allowed(target)
        audit.append("lab.nqc.start", {"case": name, "input_sha256": hashlib.sha256(canonical(rows)).hexdigest()})
        output = native.capacity.solve(deepcopy(rows))  # actual NQC function, not a supplied attestation
        reference = independent_reference(rows)
        _check_native_result(output, reference)
        audit.append("lab.nqc.finish", {"case": name, "output_commitment": output["commitment"]})
        results.append({"case": name, "inputs": rows, "nqc": output, "independent": reference, "match": True})
    denied = not guard.check(native.models.Target(value="blocked.lab.invalid", kind="fixture", chain="offline")).allowed
    if not denied:
        raise ValueError("DIABLO excluded target was admitted")
    invalid = fixture_cases()["tie"]
    invalid[1]["opportunity_id"] = invalid[0]["opportunity_id"]
    try:
        native.capacity.solve(invalid)
    except ValueError as exc:
        if "duplicate opportunity_id" not in str(exc):
            raise
        duplicate_rejected = True
    else:
        raise ValueError("NQC accepted duplicate numerical records")
    audit.append("lab.completed", {"run_id": run_id, "cases": len(results), "vulnerability_confirmed": False})
    audit.assert_intact()
    verdict = {
        "schema_version": 1, "status": "LOCAL_INTEGRATION_PASS", "run_id": run_id,
        "started_at": started, "completed_at": datetime.now(timezone.utc).isoformat(),
        "verification_level": "pinned-native-local-regression", "local_component_execution": True,
        "fixture_only": True, "vulnerability_confirmed": False, "forge_executed": False,
        "mainnet_connected": False, "program_scope_verified": False,
        "cases_passed": len(results), "scope_negative_passed": denied,
        "duplicate_negative_passed": duplicate_rejected,
        "audit_head": audit.head, "audit_count": len(audit),
        "native_functions": ["DIABLO.ScopeGuard.assert_allowed", "DIABLO.AuditLog.append/verify", "NQC.RMC016.solve"],
    }
    return {"lab-result.json": canonical(verdict), "nqc-results.json": canonical({"cases": results}),
            "diablo-audit.json": canonical({"entries": [asdict(e) for e in audit.entries]}),
            "source-provenance.json": canonical({"sources": list(native.provenance)})}


def run_local(out: Path) -> dict:
    # Check before executing; an existing output is not a resumable run.
    if out.exists() or out.is_symlink():
        raise FileExistsError("local lab requires a new output directory")
    files = execute_local()
    write_new_bundle(out, files)
    return verify_local_bundle(out)


def verify_local_bundle(root: Path) -> dict:
    """Integrity/recalculation check, NOT authentication of an external producer."""
    marker = strict_json(read_artifact(root, "COMPLETE.json"))
    if marker.get("schema_version") != 1 or set(marker.get("sha256", {})) != BUNDLE_FILES:
        raise ValueError("incomplete or unexpected lab bundle")
    values = {}
    for name, expected in marker["sha256"].items():
        raw = read_artifact(root, name)
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("lab artifact digest mismatch")
        values[name] = strict_json(raw)
    result = values["lab-result.json"]
    if (result.get("status") != "LOCAL_INTEGRATION_PASS" or result.get("fixture_only") is not True or
            result.get("vulnerability_confirmed") is not False or result.get("forge_executed") is not False or
            result.get("mainnet_connected") is not False or result.get("program_scope_verified") is not False):
        raise ValueError("local evidence cannot become a production finding")
    if values["source-provenance.json"] != {"sources": source_inventory()}:
        raise ValueError("source provenance mismatch")
    cases = values["nqc-results.json"].get("cases")
    fixtures = fixture_cases()
    if type(cases) is not list or len(cases) != len(fixtures) or [c.get("case") for c in cases] != list(fixtures):
        raise ValueError("lab case coverage mismatch")
    for case in cases:
        rows = fixtures[case["case"]]
        reference = independent_reference(rows)
        if case["inputs"] != rows or case["independent"] != reference or case.get("match") is not True:
            raise ValueError("local input/reference mismatch")
        _check_native_result(case["nqc"], reference)
    native = load_components()
    entries = values["diablo-audit.json"].get("entries")
    if type(entries) is not list or len(entries) != result.get("audit_count") or len(entries) != 18:
        raise ValueError("audit length mismatch")
    previous = "0" * 64
    for i, row in enumerate(entries):
        entry = native.audit.AuditEntry(**row)
        if entry.index != i or entry.prev_hash != previous or entry.recompute() != entry.hash:
            raise ValueError("audit chain mismatch")
        previous = entry.hash
    if previous != result.get("audit_head") or entries[0]["data"].get("run_id") != result.get("run_id"):
        raise ValueError("audit anchor mismatch")
    if entries[-1]["event"] != "lab.completed" or entries[-1]["data"].get("run_id") != result.get("run_id"):
        raise ValueError("audit completion mismatch")
    if result.get("cases_passed") != 5 or result.get("scope_negative_passed") is not True or result.get("duplicate_negative_passed") is not True:
        raise ValueError("lab acceptance mismatch")
    verify_audit_links(entries, result, cases)
    return {"status": result["status"], "run_id": result["run_id"], "cases_passed": 5,
            "verification_level": "artifact-integrity-and-reference-recalculation",
            "vulnerability_confirmed": False}
