"""One bounded local quality gate tying source, tests, native execution and status.

Not a research scheduler or exploit runner. Only fixed project regressions and
native numeric fixtures execute. Receipts prove consistency, not remote identity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
import uuid

from .capabilities import checklist, render_checklist
from .local_lab import BUNDLE_FILES, verify_local_bundle
from .native_runtime import source_inventory
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

PACKAGE = Path(__file__).resolve().parent
STAGES = (
    ("source_pins", ()),
    ("regressions", ("source_pins",)),
    ("native_execution", ("source_pins", "regressions")),
    ("independent_check", ("native_execution",)),
    ("capability_checklist", ("regressions", "independent_check")),
)
STAGE_OUTPUTS = {
    "source_pins": ("source-snapshot.json", "native-sources.json"),
    "regressions": ("test-results.json", "tests.log"),
    "native_execution": tuple(sorted(BUNDLE_FILES)) + ("lab-manifest.json", "execution-summary.json"),
    "independent_check": ("independent-check.json",),
    "capability_checklist": ("capability-status.json", "CHECKLIST.md"),
}
ENV = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0"}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def snapshot() -> dict:
    files = {}
    for path in sorted(PACKAGE.rglob("*")):
        if path.suffix != ".py" and path.name != "requirements-local-lab.txt":
            continue
        name = path.relative_to(PACKAGE).as_posix()
        files[name] = sha(read_artifact(PACKAGE, name))
    if not files:
        raise ValueError("empty source snapshot")
    return {"files": files, "sha256": sha(canonical(files))}


def verify_tests(value: dict) -> list[dict]:
    fields = {"schema_version", "status", "tests_run", "expected_count", "records", "failures", "errors",
              "skipped", "expected_failures", "unexpected_successes"}
    if type(value) is not dict or set(value) != fields or type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("invalid test receipt schema")
    rows = value["records"]
    if type(rows) is not list or not rows or value["status"] != "PASS":
        raise ValueError("regression suite did not pass")
    ids = []
    for row in rows:
        if (type(row) is not dict or set(row) != {"id", "outcome"} or type(row["id"]) is not str
                or not row["id"].startswith("test_") or row["outcome"] != "PASS"):
            raise ValueError("incomplete, failed or skipped regression")
        ids.append(row["id"])
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate test result")
    for key in ("tests_run", "expected_count"):
        if type(value[key]) is not int or value[key] != len(rows):
            raise ValueError("test count mismatch")
    for key in ("failures", "errors", "skipped", "expected_failures", "unexpected_successes"):
        if type(value[key]) is not int or value[key] != 0:
            raise ValueError("nonzero failed or skipped regression count")
    return rows


def _fixed_worker(mode: str, directory: Path):
    if mode == "tests":
        command = [sys.executable, "-I", "-B", str(PACKAGE / "qa_worker.py"), "--out", str(directory)]
        timeout = 120
    elif mode in ("run", "verify"):
        command = [sys.executable, "-I", "-B", str(PACKAGE / "lab_worker.py"), mode, str(directory)]
        timeout = 30
    else:
        raise ValueError("unknown fixed worker")
    proc = subprocess.run(command, cwd=PACKAGE.parent, env=ENV, timeout=timeout,
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise ValueError(f"{mode} worker failed with exit {proc.returncode}")
    if mode == "tests":
        value = strict_json(read_artifact(directory, "test-results.json"))
        verify_tests(value)
        return value
    value = strict_json(proc.stdout)
    if value.get("status") != "LOCAL_INTEGRATION_PASS" or value.get("vulnerability_confirmed") is not False:
        raise ValueError("invalid local worker verdict")
    return value


def _node(name, dependencies, nodes, source_sha, outputs, files):
    parents = {p: nodes[p]["sha256"] for p in dependencies}
    if any(nodes[p]["status"] != "PASS" for p in dependencies):
        raise ValueError("stage prerequisite did not pass")
    body = {"name": name, "status": "PASS", "source_sha256": source_sha, "parents": parents,
            "outputs": {path: sha(files[path]) for path in outputs}}
    return {**body, "sha256": sha(canonical(body))}


def verify_stage_links(receipt: dict, files: dict[str, bytes]) -> None:
    nodes = receipt.get("stages")
    if type(nodes) is not list or len(nodes) != len(STAGES):
        raise ValueError("incomplete stage graph")
    known = {}
    for node, (name, deps) in zip(nodes, STAGES):
        if (type(node) is not dict or set(node) != {"name", "status", "source_sha256", "parents", "outputs", "sha256"}
                or node["name"] != name or node["status"] != "PASS" or node["source_sha256"] != receipt["source_sha256"]):
            raise ValueError("stage identity mismatch")
        if node["parents"] != {dep: known[dep]["sha256"] for dep in deps}:
            raise ValueError("stage dependency mismatch")
        if type(node["outputs"]) is not dict or set(node["outputs"]) != set(STAGE_OUTPUTS[name]):
            raise ValueError("stage evidence missing")
        for path, expected in node["outputs"].items():
            if path not in files or sha(files[path]) != expected:
                raise ValueError("stage artifact mismatch")
        body = {k: v for k, v in node.items() if k != "sha256"}
        if sha(canonical(body)) != node["sha256"]:
            raise ValueError("stage digest mismatch")
        known[name] = node


def run_assurance(out: Path) -> dict:
    if out.exists() or out.is_symlink():
        raise FileExistsError("verification requires a new private output directory")
    before = snapshot()
    files = {"source-snapshot.json": canonical(before)}
    nodes = {}
    current = "source_pins"
    started = datetime.now(timezone.utc).isoformat()
    run_id = str(uuid.uuid4())
    try:
        with tempfile.TemporaryDirectory(prefix="superhunter-quality-") as td:
            work = Path(td)
            files["native-sources.json"] = canonical({"sources": source_inventory()})
            nodes[current] = _node(current, (), nodes, before["sha256"], ("source-snapshot.json", "native-sources.json"), files)
            current = "regressions"
            try:
                tests = _fixed_worker("tests", work / "tests")
            except (ValueError, OSError, subprocess.TimeoutExpired):
                for name in ("test-results.json", "tests.log"):
                    try:
                        files[name] = read_artifact(work / "tests", name)
                    except (ValueError, OSError):
                        pass  # No substitute evidence is generated.
                raise
            records = verify_tests(tests)
            for name in ("test-results.json", "tests.log"):
                files[name] = read_artifact(work / "tests", name)
            nodes[current] = _node(current, STAGES[1][1], nodes, before["sha256"], ("test-results.json", "tests.log"), files)
            current = "native_execution"
            execution = _fixed_worker("run", work / "lab")
            files["execution-summary.json"] = canonical(execution)
            for name in BUNDLE_FILES:
                files[name] = read_artifact(work / "lab", name)
            files["lab-manifest.json"] = read_artifact(work / "lab", "COMPLETE.json")
            nodes[current] = _node(current, STAGES[2][1], nodes, before["sha256"], tuple(sorted(BUNDLE_FILES)) + ("lab-manifest.json", "execution-summary.json"), files)
            current = "independent_check"
            verification = _fixed_worker("verify", work / "lab")
            # Also check the semantic linkage in the parent, not only stdout.
            direct = verify_local_bundle(work / "lab")
            if verification != direct or execution["run_id"] != direct["run_id"]:
                raise ValueError("independent execution/verification mismatch")
            files["independent-check.json"] = canonical(verification)
            nodes[current] = _node(current, STAGES[3][1], nodes, before["sha256"], ("independent-check.json",), files)
            current = "capability_checklist"
            value = checklist(records, True)
            if not all(f["verified_this_run"] for f in value["foundations"]):
                raise ValueError("required foundation tests missing")
            files["capability-status.json"] = canonical(value)
            files["CHECKLIST.md"] = render_checklist(value).encode()
            nodes[current] = _node(current, STAGES[4][1], nodes, before["sha256"], ("capability-status.json", "CHECKLIST.md"), files)
            if snapshot() != before:
                raise ValueError("source changed during verification")
        receipt = {"schema_version": 1, "status": "LOCAL_QUALITY_PASS", "run_id": run_id,
                   "started_at": started, "completed_at": datetime.now(timezone.utc).isoformat(),
                   "source_sha256": before["sha256"], "stages": list(nodes.values()),
                   "vulnerability_confirmed": False, "production_certified": False,
                   "tests_passed": len(records), "local_cases": 5,
                   "python": sys.version.split()[0]}
        verify_stage_links(receipt, files)
        files["assurance.json"] = canonical(receipt)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        # No failed stage or unsigned caller assertion may become a green check.
        receipt = {"schema_version": 1, "status": "BLOCKED", "run_id": run_id,
                   "source_sha256": before["sha256"], "failed_stage": current,
                   "completed_stages": list(nodes.values()), "error_type": type(exc).__name__,
                   "reason": str(exc)[:240], "vulnerability_confirmed": False, "production_certified": False}
        files["assurance.json"] = canonical(receipt)
        value = checklist([], False)
        files["capability-status.json"] = canonical(value)
        files["CHECKLIST.md"] = render_checklist(value).encode()
    write_new_bundle(out, files)
    return receipt


def verify_assurance(root: Path) -> dict:
    marker = strict_json(read_artifact(root, "COMPLETE.json"))
    if (set(marker) != {"schema_version", "sha256"} or type(marker["schema_version"]) is not int
            or marker["schema_version"] != 1 or type(marker["sha256"]) is not dict):
        raise ValueError("invalid quality manifest")
    required_files = {"assurance.json"} | {name for outputs in STAGE_OUTPUTS.values() for name in outputs}
    if set(marker["sha256"]) != required_files:
        raise ValueError("quality package files mismatch")
    files = {}
    for name, digest in marker["sha256"].items():
        raw = read_artifact(root, name)
        if sha(raw) != digest:
            raise ValueError("quality artifact mismatch")
        files[name] = raw
    receipt = strict_json(files["assurance.json"])
    required_receipt = {"schema_version", "status", "run_id", "started_at", "completed_at", "source_sha256",
                        "stages", "vulnerability_confirmed", "production_certified", "tests_passed", "local_cases", "python"}
    if (set(receipt) != required_receipt or type(receipt["schema_version"]) is not int or receipt["schema_version"] != 1
            or type(receipt["local_cases"]) is not int or receipt["local_cases"] != 5):
        raise ValueError("quality receipt schema mismatch")
    if type(receipt["run_id"]) is not str or str(uuid.UUID(receipt["run_id"])) != receipt["run_id"]:
        raise ValueError("quality run identity mismatch")
    if (receipt.get("status") != "LOCAL_QUALITY_PASS" or receipt.get("vulnerability_confirmed") is not False
            or receipt.get("production_certified") is not False):
        raise ValueError("quality run is not a local pass")
    current = snapshot()
    if strict_json(files["source-snapshot.json"]) != current or receipt["source_sha256"] != current["sha256"]:
        raise ValueError("evidence refers to a different source snapshot")
    verify_stage_links(receipt, files)
    if strict_json(files["native-sources.json"]) != {"sources": source_inventory()}:
        raise ValueError("native source inventory mismatch")
    records = verify_tests(strict_json(files["test-results.json"]))
    if type(receipt.get("tests_passed")) is not int or receipt["tests_passed"] != len(records):
        raise ValueError("quality test count mismatch")
    expected = checklist(records, True)
    if not all(f["verified_this_run"] for f in expected["foundations"]):
        raise ValueError("required foundation tests missing")
    if strict_json(files["capability-status.json"]) != expected or files["CHECKLIST.md"] != render_checklist(expected).encode():
        raise ValueError("unsupported capability promotion")
    with tempfile.TemporaryDirectory(prefix="superhunter-recheck-") as td:
        lab = Path(td) / "lab"
        lab.mkdir()
        for name in BUNDLE_FILES:
            (lab / name).write_bytes(files[name])
        (lab / "COMPLETE.json").write_bytes(files["lab-manifest.json"])
        verified = verify_local_bundle(lab)
        if (strict_json(files["independent-check.json"]) != verified or
                strict_json(files["execution-summary.json"]) != verified):
            raise ValueError("local case linkage mismatch")
    return {"status": "QUALITY_BUNDLE_CONSISTENT", "run_id": receipt["run_id"],
            "tests_passed": len(records), "completed_requested_capabilities": 0,
            "remote_producer_authenticated": False, "production_certified": False}


def main(argv, *, verify=False):
    parser = argparse.ArgumentParser(description="Fixed local project quality gate, not a security scanner")
    parser.add_argument("--bundle" if verify else "--out", dest="directory", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_assurance(args.directory) if verify else run_assurance(args.directory)
        print(json.dumps({k: result[k] for k in ("status", "run_id", "tests_passed") if k in result}))
        return 0 if result["status"] != "BLOCKED" else 1
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "BLOCKED", "error_type": type(exc).__name__}))
        return 2
