"""Run the seven legacy suites with their exact historical inputs in fresh copies.

This does not make generic discovery on the current catalog green. Catalogs are
read from pinned original Git blobs; source code and assertions stay unchanged.
Provide downloaded original archives and API snapshots; this tool downloads none.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys

from integrity import canonical, digest, git_blob
from isolation import project_repository, verify_repository

ROOT = Path(__file__).resolve().parents[1]
CASES = (
    ("original_debt", "test_rmc011_original_d08_debt_producer.py", "6754a74c5c1e348c0c731618332ba8feba96834e", 20),
    ("original_native", "test_rmc011_original_d08_native_flash_import.py", "c1b9f136a13f220af9dceaae50e5caa3105121eb", 20),
    ("four_native", "test_rmc011_four_native_original_source_join.py", "c1b9f136a13f220af9dceaae50e5caa3105121eb", 21),
    ("seven", "test_rmc011_independent_seven_bounded_rejections.py", "c1b9f136a13f220af9dceaae50e5caa3105121eb", 22),
    ("thirteen", "test_rmc011_independent_thirteen_source_pins.py", "9dee5fe5035fad450ede25462728eba26beffb49", 22),
    ("discovery", "test_rmc011_independent_discovery_admission.py", None, 49),
    ("two_debt", "test_rmc011_independent_two_debt_pins.py", "c1b9f136a13f220af9dceaae50e5caa3105121eb", 20),
)


def case_arguments(name, evidence):
    def meta(role, kind):
        suffix = "artifacts" if kind == "artifact" else kind
        return str(evidence / f"historical-{role}-{suffix}.json")

    def role(prefix, label):
        return [f"--{prefix}-zip", str(evidence / f"historical-{label}.zip"),
                f"--{prefix}-run", meta(label, "run"),
                f"--{prefix}-artifact", meta(label, "artifact")]

    return {
        "original_debt": [], "original_native": [],
        "four_native": role("d08", "d08") + role("dual", "dual"),
        "seven": ["--archive", str(evidence / "historical-seven.zip"),
                  "--run-meta", meta("seven", "run"), "--artifact-meta", meta("seven", "artifact")],
        "thirteen": role("new", "new") + role("d08", "d08") + role("dual", "dual"),
        "discovery": ["--zip", str(evidence / "historical-discovery.zip"),
                      "--run", meta("discovery", "run"), "--artifact", meta("discovery", "artifact"),
                      "--commit", meta("discovery", "commit")],
        "two_debt": ["--original-zip", str(evidence / "historical-debt.zip"),
                     "--run-meta", meta("debt", "run"), "--artifact-meta", meta("debt", "artifact"),
                     "--commit-meta", meta("debt", "commit"),
                     "--original-upstream-dir", str(evidence / "upstream")],
    }[name]


def check_outcome(returncode, log, expected):
    counts = re.findall(r"^Ran (\d+) tests? in .+$", log, re.MULTILINE)
    return (returncode == 0 and counts == [str(expected)]
            and re.search(r"^OK\s*\Z", log, re.MULTILINE) is not None)


def run(root, source_git, evidence, work):
    root, source_git, evidence = (path.resolve(strict=True) for path in (root, source_git, evidence))
    work = work.resolve()
    if work.exists() or any(work.is_relative_to(path) or path.is_relative_to(work)
                            for path in (root, source_git, evidence)):
        raise ValueError("work_must_be_new_and_separate")
    isolation = verify_repository(root, source_git)
    work.mkdir(parents=True, exist_ok=False)
    results = []
    for name, test, pin, expected in CASES:
        case = work / name
        project_repository(root, case)
        catalog = case / "ci/nqc-census/rmc011-capital-source-universe.json"
        current_blob = git_blob(catalog.read_bytes())
        if pin is not None:
            raw = subprocess.check_output(["git", "-C", str(source_git), "cat-file", "blob", pin])
            if git_blob(raw) != pin:
                raise ValueError("historical_catalog_blob_mismatch")
            catalog.write_bytes(raw)
        command = [sys.executable, "ci/nqc-census/" + test, *case_arguments(name, evidence)]
        log = work / (name + ".log")
        with log.open("xb") as stream:
            # This is an explicitly synthetic output label, never a claim of CI execution.
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", GITHUB_WORKFLOW="LOCAL_OFFLINE_TEST_NOT_CI")
            result = subprocess.run(command, cwd=case, env=env, stdout=stream, stderr=subprocess.STDOUT)
        raw_log = log.read_bytes()
        passed = check_outcome(result.returncode, raw_log.decode(errors="replace"), expected)
        results.append({"case": name, "test": test, "expected_tests": expected,
                        "pass": passed, "returncode": result.returncode,
                        "test_sha256": hashlib.sha256((case / "ci/nqc-census" / test).read_bytes()).hexdigest(),
                        "current_catalog_git_blob": current_blob,
                        "fixture_catalog_git_blob": git_blob(catalog.read_bytes()),
                        "catalog_replaced_in_disposable_copy": pin is not None,
                        "log_sha256": digest(raw_log)})
        print(name, "PASS" if passed else "FAILED", flush=True)
    report = {"schema": "nqc.omega.historical-harness.v1", "cases": results,
              "historical_tests_pass": all(row["pass"] for row in results),
              "historical_test_count": sum(row["expected_tests"] for row in results if row["pass"]),
              "isolation": isolation, "current_aggregate_pass": False,
              "canonical_recertification": False, "census_closed": False,
              "phase_advance_authorized": False}
    report["report_commitment_sha256"] = digest(canonical(report))
    (work / "report.json").write_bytes(canonical(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--source-git", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.root, args.source_git, args.evidence, args.work)
    return 0 if report["historical_tests_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
