"""Single entry point for this repo's fixed defensive checks and truthful status.

There is no dynamic plugin loader, target discovery, payload generation, remote
execution, or automatic reporting. This connects the safe components that exist,
not the fifty unimplemented capabilities listed in the planning registry.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .bounded_capacity import run_bounded, verify_bounded
from .capability_status import load_registry, validate_registry, render_checklist
from .evidence_links import digest, exact
from .local_lab import BUNDLE_FILES, execute_local, verify_local_values
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
CODE_FILES = (
    "__init__.py", "__main__.py", "bridge.py", "integration.py", "safe_io.py",
    "native_runtime.py", "local_lab.py", "evidence_links.py", "bounded_capacity.py",
    "capability_status.py", "system_check.py", "lab_worker.py", "lab_cli.py", "capabilities.json",
)
EXTRA_FILES = {"finite-domain.json", "capability-plan.json", "capability-status.json",
               "current-code.json", "system-result.json", "CHECKLIST.md"}


def current_code() -> dict:
    return {name: hashlib.sha256(read_artifact(ROOT, name)).hexdigest() for name in CODE_FILES}


def _verdict(local: dict, certificate: dict, plan: dict, code: dict) -> dict:
    parents = {"local_circuit": local["evidence_root_sha256"], "finite_domain": digest(certificate),
               "capability_registry": digest(plan), "current_code": digest(code)}
    body = {"schema_version": 1, "status": "LOCAL_DEFENSIVE_CHECKS_PASS", "run_id": local["run_id"],
            "parents": parents, "circuit_nodes": local["linked_nodes"],
            "cases_checked": certificate["cases_checked"], "capabilities": validate_registry(plan),
            "vulnerability_confirmed": False, "universal_security_proof": False,
            "producer_authenticated": False}
    return {**body, "root_sha256": digest(body)}


def run_system(out: Path) -> dict:
    if out.exists() or out.is_symlink():
        raise FileExistsError("system check requires a new output directory")
    plan, code = load_registry(), current_code()
    files = execute_local()
    local = verify_local_values({name: strict_json(raw) for name, raw in files.items()})
    certificate = run_bounded()
    verify_bounded(certificate)
    # Abort rather than mix code versions if local files changed during the run.
    exact(current_code(), code, "code changed during execution")
    verdict = _verdict(local, certificate, plan, code)
    files.update({
        "finite-domain.json": canonical(certificate), "capability-plan.json": canonical(plan),
        "capability-status.json": canonical(validate_registry(plan)), "current-code.json": canonical(code),
        "system-result.json": canonical(verdict),
        "CHECKLIST.md": render_checklist(plan, local["evidence_root_sha256"], certificate["cases_checked"]).encode(),
    })
    write_new_bundle(out, files)
    return verify_system(out)


def verify_system(root: Path) -> dict:
    """Recalculate independent reference and check all mandatory links."""
    marker = strict_json(read_artifact(root, "COMPLETE.json"))
    if (set(marker) != {"schema_version", "sha256"} or type(marker["schema_version"]) is not int or
            marker["schema_version"] != 1 or type(marker["sha256"]) is not dict or
            set(marker["sha256"]) != BUNDLE_FILES | EXTRA_FILES):
        raise ValueError("incomplete system bundle")
    raw = {}
    for name, expected in marker["sha256"].items():
        raw[name] = read_artifact(root, name)
        if hashlib.sha256(raw[name]).hexdigest() != expected:
            raise ValueError("system artifact digest mismatch")
    local = verify_local_values({name: strict_json(raw[name]) for name in BUNDLE_FILES})
    cert = strict_json(raw["finite-domain.json"])
    verify_bounded(cert)
    plan, code = load_registry(), current_code()
    exact(strict_json(raw["capability-plan.json"]), plan, "capability plan changed")
    exact(strict_json(raw["current-code.json"]), code, "current code changed")
    exact(strict_json(raw["capability-status.json"]), validate_registry(plan), "capability status")
    verdict = _verdict(local, cert, plan, code)
    exact(strict_json(raw["system-result.json"]), verdict, "system result")
    expected = render_checklist(plan, local["evidence_root_sha256"], cert["cases_checked"]).encode()
    if raw["CHECKLIST.md"] != expected:
        raise ValueError("checklist does not match verified evidence")
    return {"status": verdict["status"], "run_id": local["run_id"], "root_sha256": verdict["root_sha256"],
            "linked_nodes": local["linked_nodes"], "bounded_cases": cert["cases_checked"],
            "capabilities": verdict["capabilities"], "vulnerability_confirmed": False,
            "universal_security_proof": False, "producer_authenticated": False}
