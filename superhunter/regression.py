"""Compare actual local QA receipts without executing submitted code or PoCs.

A correction is observed only for unchanged existing test files under the same
pinned QA harness. Evidence integrity is not producer authentication, and a
finite regression suite cannot certify absence of other vulnerabilities.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any

from . import quality
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

HASH = re.compile(r"[0-9a-f]{64}\Z")
SOURCE = re.compile(r"[A-Za-z0-9_.\-/]{1,256}\Z")
TEST = re.compile(r"test[A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){2,6}\Z")
OUTCOMES = {"PASS", "FAIL", "ERROR", "SKIP", "EXPECTED_FAILURE", "UNEXPECTED_SUCCESS", "INCOMPLETE"}
COUNTERS = ("failures", "errors", "skipped", "expected_failures", "unexpected_successes")
# v1 compares only receipts from this verifier's own QA policy/runner generation.
HARNESS = ("quality.py", "quality_worker.py", "safe_io.py", "regression.py", "privacy.py",
           "requirements-local-lab.txt", "capabilities.json")
FILES = {"comparison.json", "comparison.md"}
MAX_TESTS = 5000


def _need(ok: bool, code: str) -> None:
    if not ok:
        # Codes are fixed; never echo input paths, fields, logs or arbitrary values.
        raise ValueError(code)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _hash(value: Any) -> str:
    _need(type(value) is str and HASH.fullmatch(value) is not None, "INVALID_SHA256")
    return value


def _snapshot(value: Any) -> dict:
    _need(type(value) is dict and 0 < len(value) <= 500, "INVALID_SNAPSHOT")
    for path, digest in value.items():
        _need(type(path) is str and SOURCE.fullmatch(path) is not None, "INVALID_SOURCE_PATH")
        _need(not PurePosixPath(path).is_absolute() and
              all(part not in ("", ".", "..") for part in path.split("/")), "INVALID_SOURCE_PATH")
        _hash(digest)
    return value


def _receipt(value: dict, snapshot: dict) -> dict[str, str]:
    required = {"schema_version", "sources_before", "sources_after", "discovered", "tests", "tests_run", "python", *COUNTERS}
    _need(type(value) is dict and required <= set(value) and
          not set(value) - required - {"log_privacy"}, "INVALID_RECEIPT_SCHEMA")
    _need(type(value["schema_version"]) is int and value["schema_version"] == 1, "INVALID_RECEIPT_VERSION")
    _need(canonical(value["sources_before"]) == canonical(snapshot) == canonical(value["sources_after"]),
          "SOURCE_CHANGED_DURING_RUN")
    _need(value["python"] == sys.version.split()[0], "PYTHON_VERSION_NOT_COMPARABLE")
    rows, discovered = value["tests"], value["discovered"]
    _need(type(rows) is list and 0 < len(rows) <= MAX_TESTS and type(discovered) is list,
          "INVALID_TEST_COLLECTION")
    _need(type(value["tests_run"]) is int and value["tests_run"] == len(rows), "INVALID_TEST_COUNT")
    for name in COUNTERS:
        _need(type(value[name]) is int and 0 <= value[name] <= MAX_TESTS * 100, "INVALID_OUTCOME_COUNTER")
    result = {}
    for row in rows:
        _need(type(row) is dict and set(row) == {"id", "outcome"}, "INVALID_TEST_RECORD")
        name, outcome = row["id"], row["outcome"]
        _need(type(name) is str and len(name) <= 512 and TEST.fullmatch(name) is not None, "INVALID_TEST_ID")
        _need(name not in result, "DUPLICATE_TEST_ID")
        _need(type(outcome) is str and outcome in OUTCOMES, "UNKNOWN_TEST_OUTCOME")
        _need("tests/" + name.split(".")[0] + ".py" in snapshot, "MISSING_TEST_SOURCE")
        result[name] = outcome
    _need(all(type(name) is str for name in discovered) and
          len(discovered) == len(set(discovered)) and set(discovered) == set(result), "DISCOVERY_RESULT_MISMATCH")
    if all(outcome == "PASS" for outcome in result.values()):
        _need(all(value[key] == 0 for key in COUNTERS), "COUNTERS_CONTRADICT_PASS")
    return result


@dataclass(frozen=True)
class Run:
    snapshot: dict[str, str]
    outcomes: dict[str, str]
    source_digest: str
    receipt_digest: str
    manifest_digest: str
    qa_passed: bool


def load_run(directory: Path, expected_source_digest: str) -> Run:
    """Validate a QA bundle under the same current harness, without importing it."""
    expected_source_digest = _hash(expected_source_digest)
    marker_raw = read_artifact(directory, "COMPLETE.json")
    marker = strict_json(marker_raw)
    _need(set(marker) == {"schema_version", "sha256"} and type(marker["schema_version"]) is int and
          marker["schema_version"] == 1 and type(marker["sha256"]) is dict and
          set(marker["sha256"]) == quality.FILES, "INVALID_QA_MANIFEST")
    raw_files = {}
    for name in sorted(quality.FILES):
        raw = read_artifact(directory, name)
        _need(_sha(raw) == _hash(marker["sha256"][name]), "QA_ARTIFACT_HASH_MISMATCH")
        raw_files[name] = raw
    snapshot = _snapshot(strict_json(raw_files["source-snapshot.json"]))
    digest = _sha(canonical(snapshot))
    _need(digest == expected_source_digest, "UNEXPECTED_SOURCE_DIGEST")
    current = quality.source_snapshot()
    _need(all(path in snapshot and snapshot[path] == current.get(path) for path in HARNESS),
          "QA_HARNESS_NOT_COMPARABLE")
    receipt = strict_json(raw_files["receipt.json"])
    outcomes = _receipt(receipt, snapshot)
    # Recompute all mandatory-test, component-ownership and source-stability gates.
    recomputed = quality.assess(receipt, snapshot)
    _need(canonical(recomputed) == raw_files["quality.json"], "QA_VERDICT_NOT_REPRODUCIBLE")
    _need(quality.checklist(quality.catalog(), recomputed).encode() == raw_files["CHECKLIST.md"],
          "QA_CHECKLIST_NOT_BOUND")
    return Run(snapshot, outcomes, digest, _sha(raw_files["receipt.json"]), _sha(marker_raw),
               recomputed["status"] == "LOCAL_QA_PASS")


def compare_runs(before: Run, after: Run) -> dict:
    """Compare validated per-test observations; never infer an exploit or payout."""
    old, new = before.outcomes, after.outcomes
    common = sorted(set(old) & set(new))
    removed = sorted(set(old) - set(new))
    added = sorted(set(new) - set(old))
    changed = []
    for path in sorted(set(before.snapshot) | set(after.snapshot)):
        b, a = before.snapshot.get(path), after.snapshot.get(path)
        if b != a:
            changed.append({"path": path, "before": b, "after": a,
                            "kind": "added" if b is None else "removed" if a is None else "modified"})
    # Whole existing test files are conservative comparison units. Renaming,
    # deleting, weakening an assertion or changing a shared test helper blocks.
    oracle_changes = [row["path"] for row in changed
                      if row["path"].startswith("tests/") and row["before"] is not None]
    regressions = [name for name in common if old[name] == "PASS" and new[name] in ("FAIL", "ERROR")]
    fixes = [name for name in common if old[name] == "FAIL" and new[name] == "PASS"]
    resolved_errors = [name for name in common if old[name] == "ERROR" and new[name] == "PASS"]
    not_passed = [name for name in sorted(new) if new[name] != "PASS"]
    runtime_changed = any(not row["path"].startswith("tests/") for row in changed)
    blockers = []
    if removed:
        blockers.append("BASELINE_TESTS_REMOVED")
    if oracle_changes:
        blockers.append("TEST_ORACLE_CHANGED")
    if not after.qa_passed or not_passed:
        blockers.append("CANDIDATE_QA_NOT_GREEN")
    if (fixes or resolved_errors) and not runtime_changed:
        blockers.append("OUTCOME_CHANGED_WITHOUT_CODE_CHANGE")
    if regressions:
        status = "REGRESSION_DETECTED"
    elif blockers:
        status = "COMPARISON_BLOCKED"
    elif fixes:
        status = "LOCAL_FIX_OBSERVED"
    else:
        status = "NO_REGRESSION_OBSERVED"
    return {
        "schema_version": 1, "status": status,
        "scope": "local-package-tests-only", "vulnerability_confirmed": False,
        "production_certified": False, "producer_authenticated": False,
        "before": {"source_digest": before.source_digest, "receipt_sha256": before.receipt_digest,
                   "manifest_sha256": before.manifest_digest, "qa_passed": before.qa_passed},
        "after": {"source_digest": after.source_digest, "receipt_sha256": after.receipt_digest,
                  "manifest_sha256": after.manifest_digest, "qa_passed": after.qa_passed},
        "comparison_engine_sha256": _sha(read_artifact(quality.ROOT, "regression.py")),
        "source_changes": changed, "unchanged_test_definitions": not oracle_changes,
        "tests": {"before_count": len(old), "after_count": len(new), "common_count": len(common),
                  "added": added, "removed": removed, "regressions": regressions,
                  "fail_to_pass": fixes, "error_to_pass": resolved_errors,
                  "not_passed_after": not_passed, "changed_oracle_files": oracle_changes},
        "fix_observed": status == "LOCAL_FIX_OBSERVED", "blockers": blockers,
        "limits": ["Only recorded tests and pinned source identities are compared.",
                   "Unmodeled behavior, external services and production safety are not certified.",
                   "Equality of test files does not prove all transitive reference behavior unchanged.",
                   "Hashes do not authenticate a producer controlling both code and artifacts."]}


def compare(before: Path, after: Path, expected_before: str, expected_after: str) -> dict:
    return compare_runs(load_run(before, expected_before), load_run(after, expected_after))


def render(result: dict) -> bytes:
    rows = result["tests"]
    lines = ["# SUPERHUNTER — comparación local de regresiones", "",
             "Estado: **" + result["status"] + "**.", "",
             "Las observaciones no certifican vulnerabilidades, seguridad total ni elegibilidad bounty.", "",
             "Código anterior: `" + result["before"]["source_digest"] + "`.",
             "Código posterior: `" + result["after"]["source_digest"] + "`.", "",
             f"Pruebas antes/después: {rows['before_count']}/{rows['after_count']}.",
             f"FAIL → PASS: {len(rows['fail_to_pass'])}; regresiones: {len(rows['regressions'])}; "
             f"eliminadas: {len(rows['removed'])}; oráculos cambiados: {len(rows['changed_oracle_files'])}.", ""]
    for group in ("fail_to_pass", "regressions", "removed", "changed_oracle_files", "not_passed_after"):
        if rows[group]:
            lines += ["## " + group, ""] + ["- `" + value + "`" for value in rows[group]] + [""]
    lines += ["## Límites", "", *result["limits"], ""]
    return "\n".join(lines).encode()


def run_comparison(before: Path, after: Path, expected_before: str, expected_after: str, out: Path) -> dict:
    if out.exists() or out.is_symlink():
        raise FileExistsError("COMPARISON_REQUIRES_NEW_DIRECTORY")
    result = compare(before, after, expected_before, expected_after)
    write_new_bundle(out, {"comparison.json": canonical(result), "comparison.md": render(result)})
    return result


def verify_comparison(bundle: Path, before: Path, after: Path, expected_before: str, expected_after: str) -> dict:
    marker = strict_json(read_artifact(bundle, "COMPLETE.json"))
    _need(set(marker) == {"schema_version", "sha256"} and type(marker["schema_version"]) is int and
          marker["schema_version"] == 1 and type(marker["sha256"]) is dict and set(marker["sha256"]) == FILES,
          "INVALID_COMPARISON_MANIFEST")
    contents = {}
    for name in sorted(FILES):
        raw = read_artifact(bundle, name)
        _need(_sha(raw) == _hash(marker["sha256"][name]), "COMPARISON_ARTIFACT_HASH_MISMATCH")
        contents[name] = raw
    result = compare(before, after, expected_before, expected_after)
    _need(contents["comparison.json"] == canonical(result) and contents["comparison.md"] == render(result),
          "COMPARISON_NOT_REPRODUCIBLE")
    return result


def main(argv: list[str], *, verify: bool = False) -> int:
    parser = PrivateArgumentParser(description="Compare this package's local QA receipts; never execute target code")
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--expect-before", required=True)
    parser.add_argument("--expect-after", required=True)
    parser.add_argument("--bundle" if verify else "--out", required=True, type=Path, dest="output")
    args = parser.parse_args(argv)
    try:
        if verify:
            result = verify_comparison(args.output, args.before, args.after, args.expect_before, args.expect_after)
        else:
            result = run_comparison(args.before, args.after, args.expect_before, args.expect_after, args.output)
        print(json.dumps({"status": result["status"], "fix_observed": result["fix_observed"],
                          "vulnerability_confirmed": False,
                          "regressions": len(result["tests"]["regressions"]),
                          "removed_tests": len(result["tests"]["removed"])}))
        return 0 if result["status"] in ("LOCAL_FIX_OBSERVED", "NO_REGRESSION_OBSERVED") else 1
    except (ValueError, OSError, TypeError, KeyError, AttributeError, RecursionError):
        print(json.dumps({"status": "COMPARISON_ERROR", "vulnerability_confirmed": False}))
        return 2
