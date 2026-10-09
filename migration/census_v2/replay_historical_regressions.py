#!/usr/bin/env python3
"""Run blocked historical regressions in exact, separate catalog contexts.

No download, RPC, producer dispatch, source mutation or certification. Original
tests retain their assertions. Synthetic unit fixtures stay distinct from the
real archive integration. Missing required bytes are errors, never skips.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
EVIDENCE = HERE / "evidence/historical-regressions"
PINNED_BASE = "0848d9946dda2b7f66b3715635db0c6239832033"
CATALOG = "ci/nqc-census/rmc011-capital-source-universe.json"
SEVEN = "6754a74c5c1e348c0c731618332ba8feba96834e"
NINE = "c1b9f136a13f220af9dceaae50e5caa3105121eb"
FILES = (
    "rmc011_original_d08_debt_producer.py",
    "test_rmc011_original_d08_debt_producer.py",
    "rmc011_original_d08_native_flash_import.py",
    "test_rmc011_original_d08_native_flash_import.py",
    "rmc011_independent_two_debt_pins.py",
    "test_rmc011_independent_two_debt_pins.py",
    "rmc011_historical_source_compatibility.py",
    "rmc011-real-source-inputs.json",
    "rmc011-external-capital-provider-registry.json",
    "rmc011-permissionless-debt-facility-catalog.json",
    "rmc011-collateral-funding-path-catalog.json",
    "final-census-authority-lock.json",
    "test_rmc006_recertification_source.py",
    "verify_rmc006_recertification_source.py",
    "rmc006-recertification-source.json",
)
ARCHIVES = {
    "d06-original.zip": "1cdb46fca52ebf1e0e2094b1c14b19384ecb7beceb50229b967592ab7a0308b4",
    "original-five-stage-authority.zip": "151847cdf85b1b49298d59b41d1bf939f6854d4556060a03ab7dd5a2e1359916",
}


def need(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(doc):
    return (json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def original_files():
    paths = ["ci/nqc-census/" + n for n in FILES] + [CATALOG]
    result = {}
    for path in paths:
        raw = (REPO / path).read_bytes()
        expected = subprocess.check_output(["git", "-C", str(REPO), "rev-parse", PINNED_BASE + ":" + path], text=True).strip()
        need(blob(raw) == expected, "imported source changed: " + path)
        result[path] = raw
    return result


def catalog_compatibility(raw, expected_blob, current, expected_count):
    need(blob(raw) == expected_blob, "historical catalog blob changed")
    old, new = json.loads(raw), json.loads(current)
    need(len(old["families"]) == len(new["families"]) == 13, "family population changed")
    old_rows = {r["id"]: r for r in old["families"]}
    new_rows = {r["id"]: r for r in new["families"]}
    need(len(old_rows) == len(new_rows) == 13 and set(old_rows) == set(new_rows), "family identity changed")
    resolved = sorted(k for k, r in old_rows.items() if r["terminally_resolved"] is True)
    need(len(resolved) == expected_count, "historical resolved count changed")
    for key in resolved:
        need(canonical(old_rows[key]) == canonical(new_rows[key]), "historical family binding changed: " + key)
    return {"historical_git_blob": expected_blob, "current_git_blob": blob(current),
            "unchanged_historical_resolved_rows": resolved,
            "current_unresolved_rows_authenticated": False,
            "current_global_discovery_authenticated": False,
            "current_capital_admission_changed": False}


def create_copy(root, originals, catalog):
    root.mkdir(parents=True, exist_ok=False)
    for path, raw in originals.items():
        dest = root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(catalog if path == CATALOG else raw)
    return root


def metadata_identity(raw_run, raw_artifact, raw_commit, pin):
    run, artifact, commit = map(json.loads, (raw_run, raw_artifact, raw_commit))
    for value in (run, artifact, commit):
        need(type(value) is dict, "metadata must be objects")
    need(type(run.get("id")) is int and run["id"] == pin["run_id"]
         and run.get("head_sha") == pin["head_sha"]
         and run.get("status") == "completed" and run.get("conclusion") == "success"
         and run.get("repository", {}).get("full_name") == "josuechavando350-png/nexus-engine",
         "source run identity changed")
    need(commit.get("sha") == pin["head_sha"]
         and re.fullmatch(r"[0-9a-f]{40}", commit.get("tree", {}).get("sha", "")) is not None
         and commit["tree"]["sha"] == run.get("head_commit", {}).get("tree_id")
         and run["head_commit"].get("id") == pin["head_sha"], "source commit/tree identity changed")
    need(type(artifact.get("id")) is int and artifact["id"] == pin["artifact_id"]
         and artifact.get("digest") == pin["artifact_digest"]
         and artifact.get("workflow_run", {}).get("id") == pin["run_id"]
         and artifact["workflow_run"].get("head_sha") == pin["head_sha"], "source artifact identity changed")
    return {"run_id": run["id"], "commit": commit["sha"], "tree": commit["tree"]["sha"],
            "artifact_id": artifact["id"], "artifact_digest": artifact["digest"]}


def test_count(raw, class_name=None):
    tree = ast.parse(raw)
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)
               and (class_name is None or n.name == class_name)]
    count = sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")
                for cls in classes for n in cls.body)
    need(count > 0, "empty test selection")
    return count


def run(archive_root, out):
    archive_root, out = archive_root.resolve(), out.resolve()
    need(not out.exists(), "append-only output directory required")
    need(not out.is_relative_to(REPO) and not REPO.is_relative_to(out), "replay must be outside repository")
    originals = original_files()
    archive_refs = []
    for name, digest in ARCHIVES.items():
        p = archive_root / name
        need(p.is_file() and not p.is_symlink(), "missing/nonregular original archive: " + name)
        raw = p.read_bytes()
        need(sha(raw) == digest, "original archive hash changed: " + name)
        archive_refs.append({"name": name, "bytes": len(raw), "sha256": digest})
    seven = (EVIDENCE / "universe-seven.json").read_bytes()
    nine = (EVIDENCE / "universe-nine.json").read_bytes()
    compatibility = [catalog_compatibility(raw, pin, originals[CATALOG], count)
                     for raw, pin, count in ((seven, SEVEN, 7), (nine, NINE, 9))]
    # Local API snapshots are provenance records, not self-authenticating remote authorities.
    meta = {}
    for key in ("d06", "d07", "d08", "d09", "d10"):
        for label in ("run", "artifact"):
            meta[key + "." + label + ".json"] = (HERE / "evidence/historical-api" / key / (label + ".json")).read_bytes()
        meta[key + ".commit.json"] = (EVIDENCE / (key + "-git-commit.json")).read_bytes()
    for label in ("run", "artifact", "commit"):
        meta["debt." + label + ".json"] = (EVIDENCE / ("debt-" + label + ".json")).read_bytes()
    stage_pins = json.loads(originals["ci/nqc-census/rmc011-real-source-inputs.json"])
    debt_pin = {"run_id": 37832286518, "head_sha": "5b79e7be1c185cbb4924d592991b9c990fc0465a",
                "artifact_id": 11573678487,
                "artifact_digest": "sha256:" + ARCHIVES["original-five-stage-authority.zip"]}
    bindings = [metadata_identity(*(meta[key + "." + label + ".json"] for label in ("run", "artifact", "commit")), pin)
                for key, pin in [(k, stage_pins[k]) for k in ("d06", "d07", "d08", "d09", "d10")] + [("debt", debt_pin)]]
    out.mkdir(parents=True)
    metadata = out / "metadata"
    metadata.mkdir()
    for name, raw in meta.items():
        (metadata / name).write_bytes(raw)
    roots = {"seven": create_copy(out / "seven", originals, seven),
             "nine": create_copy(out / "nine", originals, nine),
             "current": create_copy(out / "current", originals, originals[CATALOG])}
    debt_args = ["--original-zip", str(archive_root / "original-five-stage-authority.zip"),
                 "--run-meta", str(metadata / "debt.run.json"),
                 "--artifact-meta", str(metadata / "debt.artifact.json"),
                 "--commit-meta", str(metadata / "debt.commit.json"),
                 "--original-upstream-dir", str(metadata)]
    d06_env = {"RMC006_SOURCE_ARCHIVE": str(archive_root / "d06-original.zip"),
               **{"RMC006_SOURCE_" + k.upper() + "_METADATA": str(metadata / ("d06." + k + ".json"))
                  for k in ("run", "artifact", "commit")}}
    tasks = [
        ("debt-unit", "seven", "test_rmc011_original_d08_debt_producer.py", [], {}, None, "SYNTHETIC_ADVERSARIAL_UNIT_FIXTURES"),
        ("native-unit", "nine", "test_rmc011_original_d08_native_flash_import.py", [], {}, None, "SYNTHETIC_ADVERSARIAL_UNIT_FIXTURES"),
        ("debt-real", "nine", "test_rmc011_independent_two_debt_pins.py", debt_args, {}, None, "ORIGINAL_ARCHIVE_WITH_ADVERSARIAL_MUTATIONS"),
        ("d06-integration", "current", "test_rmc006_recertification_source.py", ["OriginalPackageIntegrationTests"], d06_env, "OriginalPackageIntegrationTests", "ORIGINAL_ARCHIVE_INTEGRATION"),
    ]
    checks = []
    for name, context, script, args, extra, selected, scope in tasks:
        command = [sys.executable, "ci/nqc-census/" + script, *args, "-v"]
        started = datetime.now(timezone.utc).isoformat()
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME") and not k.startswith("RMC006_SOURCE_")}
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONHASHSEED="0", **extra)
        result = subprocess.run(command, cwd=roots[context], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (out / (name + ".log")).write_bytes(result.stdout)
        expected = test_count(originals["ci/nqc-census/" + script], selected)
        log = result.stdout.decode("utf-8")
        counts = re.findall(r"^Ran (\d+) tests? in .+$", log, re.M)
        complete = result.returncode == 0 and counts == [str(expected)] and re.search(r"^OK$", log, re.M) is not None
        check = {"name": name, "scope": scope, "context": context, "command": command,
                 "environment_overrides": extra, "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(),
                 "expected_test_count": expected, "reported_test_counts": counts, "exit_code": result.returncode,
                 "status": "PASS" if complete else "FAIL", "log_file": name + ".log", "log_sha256": sha(result.stdout)}
        checks.append(check)
        (out / "partial-checks.json").write_bytes(canonical(checks))
        print(name, check["status"], "expected_tests", expected, flush=True)
        need(complete, "historical suite failed; preserve log: " + name)
    need(original_files() == originals, "imported source mutated during replay")
    for context, root in roots.items():
        catalog = {"seven": seven, "nine": nine, "current": originals[CATALOG]}[context]
        for path, raw in originals.items():
            need((root / path).read_bytes() == (catalog if path == CATALOG else raw), "replay source mutated")
    report = {"schema": "nqc-historical-regression-replay-v1", "status": "SELECTED_HISTORICAL_REGRESSIONS_PASS_NOT_CENSUS_CERTIFICATION",
              "pinned_imported_source_commit": PINNED_BASE, "runner_sha256": sha(Path(__file__).read_bytes()),
              "source_files": [{"path": p, "git_blob": blob(raw), "sha256": sha(raw)} for p, raw in sorted(originals.items())],
              "archives": archive_refs, "metadata": [{"name": n, "sha256": sha(raw)} for n, raw in sorted(meta.items())],
              "run_commit_tree_artifact_bindings": bindings, "catalog_compatibility": compatibility, "checks": checks,
              "tests_passed": sum(x["expected_test_count"] for x in checks), "skipped": 0, "failures": 0,
              "original_setup_errors_resolved_in_selected_replays": 3, "original_skipped_tests_now_executed": 3,
              "original_broad_result_relabelled": False, "remaining_broad_setup_suites_without_archives": 4,
              "source_modified": False, "network_requests_by_runner": 0,
              "capital_admission_changed": False, "own_gas_policy_applied_retroactively": False,
              "independent_certification_issued": False, "real_market_census_closed": False}
    (out / "report.json").write_bytes(canonical(report))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.archive_root, args.out)
    print(result["status"], "tests", result["tests_passed"])
