"""Offline consumer of one independently captured H2 run; never certification.

The reviewed pin is the trust anchor for bytes obtained through the connected
GitHub API. Local JSON does not prove its own remote origin. This verifies the
retained capture, not a fresh API query, a new execution, or a GitHub artifact.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import re
import stat
import subprocess
import sys
import zipfile

sys.dont_write_bytecode = True

from h2_actions import BRANCH, WORKFLOW, compare_forks
from integrity import canonical, digest, read_regular, strict_json
from pft_source_binding import (DESTINATION, DESTINATION_ID, FALSE_AUTHORITY,
                                git, require, verify_commit)

ROOT = Path(__file__).resolve().parents[1]
PIN_PATH = ROOT / "omega/evidence/h2-ci-capture-pin.json"
ARCHIVE_PATH = ROOT / "omega/evidence/h2-ci-capture.zip"
PIN_SHA256 = "dc616afdad494a479d808dba7eacfa215dcb687a003871bba19c53895d135635"
PRODUCER = "e21d528dabd83d7f14e7f236b9e6d4e3fc1706f7"
TREE = "9964778862574102ac2cbe907d0f40ae6c78b847"
RUN = 39859932654
WORKFLOW_ID = 393369697
JOBS = {"forks": 120107692904, "replay": 120107692521}
API = "https://api.github.com/repos/" + DESTINATION
WORKFLOW_DIGEST = "a2d101c69a6ce5aa0dc46065429547dbafec79c0d253afffce6c57231d755f16"
STORE_ROOT = "e3d2b0739d3e5affea6b337540cf3cb9b2caaedd438656d2759105d39dacba03"
MEMBERS = frozenset({"run.json", "jobs.json", "artifacts.json", "commit.json",
                     "forks.log", "replay.log", "workflow.yml"})
MAX_ARCHIVE = 256 * 1024
MAX_MEMBER = 1024 * 1024
MAX_EXPANDED = 2 * 1024 * 1024
LOG_LINE = re.compile(r"^\ufeff?(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?Z) (.*)$")


def exact(actual, expected, label):
    """Do not admit bool/int or int/float substitutions, even when equal."""
    require(type(actual) is type(expected), label + ": wrong_type")
    if isinstance(expected, dict):
        require(set(actual) == set(expected), label + ": fields")
        for key in expected:
            exact(actual[key], expected[key], label + "." + key)
    elif isinstance(expected, list):
        require(len(actual) == len(expected), label + ": length")
        for a, b in zip(actual, expected):
            exact(a, b, label)
    else:
        require(actual == expected, label + ": mismatch")


def fields(value, expected, label):
    require(type(value) is dict, label + ": object_required")
    for key, wanted in expected.items():
        exact(value.get(key), wanted, label + "." + key)


def utc(value):
    require(type(value) is str and re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,9})?Z", value) is not None,
        "invalid_utc_time")
    return datetime.fromisoformat(value[:-1] + "+00:00")


def load_pin(path=PIN_PATH):
    raw = read_regular(path)
    require(digest(raw) == PIN_SHA256, "capture_pin_changed")
    pin = strict_json(raw)
    require(raw == canonical(pin), "pin_not_canonical")
    fields(pin, {"schema": "nqc.omega.ci-capture-pin.v1", "producer_commit": PRODUCER,
                 "producer_tree": TREE, "run_id": RUN, "run_attempt": 1}, "pin")
    exact(sorted(pin["members"]), sorted(MEMBERS), "pin_members")
    return pin


def unpack(raw, manifest):
    """Bounded in-memory ZIP reading; no filesystem extraction or path trust."""
    require(len(raw) <= MAX_ARCHIVE, "archive_size_limit")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        require(len(infos) == len(MEMBERS) and len(set(names)) == len(names)
                and set(names) == MEMBERS, "archive_inventory")
        require(not archive.comment, "archive_comment")
        require(sum(i.file_size for i in infos) <= MAX_EXPANDED, "expanded_size_limit")
        result = {}
        for info in infos:
            require(not info.is_dir() and stat.S_ISREG(info.external_attr >> 16)
                    and not (info.flag_bits & 1) and not info.extra and not info.comment,
                    "nonregular_archive_member")
            require(info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                    and 0 <= info.file_size <= MAX_MEMBER, "member_size_or_compression")
            with archive.open(info) as stream:
                data = stream.read(MAX_MEMBER + 1)
            require(len(data) == info.file_size and len(data) <= MAX_MEMBER, "member_size")
            fields(manifest[info.filename], {"bytes": len(data), "sha256": digest(data)},
                   "member_digest." + info.filename)
            result[info.filename] = data
    return result


def verify_metadata(members, pin):
    run, jobs, artifacts, commit = [strict_json(members[n + ".json"])
                                  for n in ("run", "jobs", "artifacts", "commit")]
    fields(run, {"id": RUN, "run_attempt": 1, "head_sha": PRODUCER,
        "head_branch": BRANCH, "event": "push", "status": "completed",
        "conclusion": "success", "path": WORKFLOW, "workflow_id": WORKFLOW_ID,
        "url": API + f"/actions/runs/{RUN}",
        "workflow_url": API + f"/actions/workflows/{WORKFLOW_ID}"}, "run")
    for key in ("repository", "head_repository"):
        fields(run.get(key), {"id": DESTINATION_ID, "full_name": DESTINATION,
                             "private": False}, "run." + key)
    fields(run.get("head_commit"), {"id": PRODUCER, "tree_id": TREE}, "run.head_commit")
    fields(commit, {"sha": PRODUCER, "url": API + "/git/commits/" + PRODUCER}, "commit")
    fields(commit.get("tree"), {"sha": TREE}, "commit.tree")
    fields(artifacts, {"total_count": 0, "artifacts": []}, "artifact_inventory")
    fields(jobs, {"total_count": 2}, "jobs")
    require(type(jobs.get("jobs")) is list and len(jobs["jobs"]) == 2, "jobs_inventory")
    require(utc(run["created_at"]) <= utc(run["run_started_at"])
            <= utc(run["updated_at"]) <= utc(pin["retrieved_at"])
            <= datetime.now(timezone.utc), "run_time_order")
    by_stage = {}
    for stage, job_id in JOBS.items():
        selected = [j for j in jobs["jobs"] if j.get("id") == job_id]
        require(len(selected) == 1, "job_missing_or_duplicate")
        job = selected[0]
        fields(job, {"id": job_id, "name": "audit (" + stage + ")", "run_id": RUN,
            "run_attempt": 1, "head_sha": PRODUCER, "head_branch": BRANCH,
            "status": "completed", "conclusion": "success", "labels": ["ubuntu-24.04"],
            "runner_group_name": "GitHub Actions", "url": API + f"/actions/jobs/{job_id}",
            "run_url": API + f"/actions/runs/{RUN}"}, "job." + stage)
        require(utc(run["run_started_at"]) <= utc(job["started_at"])
                <= utc(job["completed_at"]) <= utc(run["updated_at"]), "job_time_order")
        require(type(job.get("steps")) is list and len(job["steps"]) == 5, "job_steps")
        exact([s["name"] for s in job["steps"]], ["Set up job",
            "Checkout exact producer without persisted credentials", "Execute audited physical gate",
            "Post Checkout exact producer without persisted credentials", "Complete job"], "step_inventory")
        for step in job["steps"]:
            fields(step, {"status": "completed", "conclusion": "success"}, "step")
            require(utc(job["started_at"]) <= utc(step["started_at"])
                    <= utc(step["completed_at"]) <= utc(job["completed_at"]), "step_time_order")
        by_stage[stage] = job
    require(digest(members["workflow.yml"]) == WORKFLOW_DIGEST, "workflow_bytes")
    return by_stage


def producer():
    return {"artifact_id": None, "canonical_recertification": False,
        "commit": PRODUCER, "tree": TREE, "repository": DESTINATION,
        "repository_id": DESTINATION_ID, "run_id": RUN, "run_attempt": 1,
        "workflow_path": WORKFLOW, "workflow_sha": PRODUCER,
        "identity_basis": "RUNNER_CONTEXT_PENDING_INDEPENDENT_API_READBACK"}


def commitment(value, key="report_commitment_sha256"):
    require(type(value) is dict and key in value, "missing_inner_commitment")
    require(value[key] == digest(canonical({k: v for k, v in value.items() if k != key})),
            "inner_commitment_mismatch")


def reject_authority(value):
    if type(value) is dict:
        for key, item in value.items():
            if key in FALSE_AUTHORITY:
                exact(item, False, "authority." + key)
            if key == "certified_components":
                exact(item, 0, "authority.certified_components")
            reject_authority(item)
    elif type(value) is list:
        for item in value:
            reject_authority(item)


def parse_log(raw, job):
    require(len(raw) <= MAX_MEMBER, "log_size_limit")
    records, steps, bodies = [], [], []
    for line in raw.decode("utf-8").splitlines():
        match = LOG_LINE.fullmatch(line)
        require(match is not None, "malformed_log_line")
        timestamp, body = match.groups()
        bodies.append(body)
        if not body.startswith("OMEGA_H2_"):
            continue
        require(utc(job["started_at"]) <= utc(timestamp) <= utc(job["completed_at"]),
                "evidence_outside_job_window")
        if body.startswith("OMEGA_H2_EVIDENCE "):
            record = strict_json(body.removeprefix("OMEGA_H2_EVIDENCE "))
            require(type(record) is dict and set(record) == {"name", "sha256", "value"}
                    and type(record["name"]) is str and type(record["value"]) is dict,
                    "evidence_envelope")
            require(record["sha256"] == digest(canonical(record["value"])), "evidence_digest")
            reject_authority(record["value"])
            records.append(record)
        elif body.startswith("OMEGA_H2_REPLAY_STEP "):
            steps.append(strict_json(body.removeprefix("OMEGA_H2_REPLAY_STEP ")))
        elif not body.startswith("OMEGA_H2_COMMAND "):
            raise ValueError("failed_or_unknown_runner_marker")
    return records, steps, bodies


def verify_log(raw, job, stage):
    records, steps, bodies = parse_log(raw, job)
    common = {"producer": 1, "isolation-before": 1, "isolation-after": 1,
              "runner-unit-tests": 1, "stage-complete": 1}
    expected = {**common, **({"command": 17, "download": 2, "rpc-preflight": 1,
        "source-binding": 1, "blastapi-public": 1, "mevblocker-rpc": 1, "historical-forks": 1}
        if stage == "forks" else {"command": 14, "download": 4,
                                 "network-isolation": 1, "disconnected-replay": 1})}
    exact(dict(Counter(r["name"] for r in records)), expected, "evidence_inventory")
    require(records[0]["name"] == "producer" and records[-1]["name"] == "stage-complete",
            "evidence_order")
    values = {r["name"]: r["value"] for r in records if expected[r["name"]] == 1}
    exact(values["producer"], producer(), "producer")
    for record in records:
        if record["name"] == "command":
            fields(record["value"], {"exit_code": 0}, "command")
    isolation = values["isolation-before"]
    exact(values["isolation-after"], isolation, "isolation_changed")
    fields(isolation, {"status": "OMEGA_OFFLINE_ISOLATION_PASS", "active_omega_workflows": 1,
        "active_workflow_sha256": WORKFLOW_DIGEST, "extension_file_count": 76,
        "canonical_recertification": False, "phase_advance_authorized": False}, "isolation")
    fields(isolation.get("legacy_result"), {"status": "ISOLATED_SOURCE_IDENTITY_PASS",
        "active_workflows": 0, "disabled_workflows": 106, "original_objects_checked": True,
        "source_files": 531, "destination_repository_id": DESTINATION_ID,
        "canonical_recertification": False,
        "source_commit": "e259739c9f75fedcd1061d2f78d6b8852e7a3060"}, "legacy_isolation")
    tests = values["runner-unit-tests"]
    commitment(tests)
    fields(tests, {"tests_run": 41, "strict_pass": True, "unittest_successful": True,
        "status": "TESTS_PASS", "issues": [], "skipped": [], "expected_failures": [],
        "canonical_recertification": False, "census_closed": False,
        "phase_advance_authorized": False}, "runner_tests")
    exact(tests["discovered"], tests["successes"], "runner_test_coverage")
    require(len(tests["successes"]) == 41 and len(set(tests["successes"])) == 41,
            "runner_test_count")
    rust = [tuple(map(int, m.groups())) for b in bodies if (m := re.fullmatch(
        r"test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored; (\d+) measured; (\d+) filtered out; finished in .+", b))]
    require(bool(rust) and all(r[1:] == (0, 0, 0, 0) for r in rust), "rust_nonpass")
    exact(sum(r[0] for r in rust), 56 if stage == "forks" else 528, "rust_count")
    if stage == "forks":
        require(not steps, "unexpected_replay_steps")
        a, b = values["blastapi-public"], values["mevblocker-rpc"]
        result = compare_forks(a["positive"], b["positive"], a["negative"], b["negative"])
        exact(values["historical-forks"], result, "fork_result")
        for name in ("testFork_ExecutorSettlesHistoricalWethUsdcLiquidation()",
                     "testFork_ExecutorRejectsOriginalUnprofitableRouteAtomically()"):
            require(sum(b.startswith("[PASS] " + name) for b in bodies) == 2, "fork_case_count")
        suites = [int(m.group(1)) for b in bodies if (m := re.fullmatch(
            r"Ran .+: (\d+) tests passed, 0 failed, 0 skipped \(\d+ total tests\)", b))]
        exact(suites, [14, 2, 2], "solidity_counts")
        binding = values["source-binding"]
        commitment(binding)
        fields(binding, {"producer_commit": PRODUCER, "producer_tree": TREE,
            "producer_repository": DESTINATION, "producer_repository_id": DESTINATION_ID,
            "original_ancestry_gate_preserved": True,
            **{k: False for k in FALSE_AUTHORITY}}, "source_binding")
        fields(values["rpc-preflight"], {"canonical_recertification": False}, "rpc_preflight")
        require(len(values["rpc-preflight"]["providers"]) == 2, "provider_count")
        for p in values["rpc-preflight"]["providers"]:
            fields(p, {"status": "PASS", "block_number": 25252136}, "provider_preflight")
    else:
        verify_replay_steps(steps)
        result = values["disconnected-replay"]
        fields(result, {"schema": "nqc-rmc006-offline-verification-v1",
            "code_commit": PRODUCER, "code_tree": TREE, "canonical_recertification": False,
            "source_unchanged": True, "current_replay_byte_identical": True,
            "history_replay_byte_identical": True, "closeout_byte_identical": True,
            "source_store_root": STORE_ROOT, "result_store_root": STORE_ROOT,
            "source_commit": "a33a012591cd6625ddb921d995bb1bd95b4a5406",
            "source_artifact_id": 11143129177, "source_run_id": 36820687233,
            "source_artifact_digest": "sha256:1cdb46fca52ebf1e0e2094b1c14b19384ecb7beceb50229b967592ab7a0308b4",
            "original_observation_at": "2026-10-01T05:23:35Z",
            "original_observation_time_basis": "ORIGINAL_SOURCE_ANCHOR_BLOCK_TIMESTAMP",
            "verification_time_basis": "NEW_VERIFICATION_SYSTEM_UTC_CLOCK"}, "replay")
        require(utc(job["started_at"]) <= utc(result["verification_started_at"])
                < utc(result["verification_completed_at"]) <= utc(job["completed_at"]),
                "replay_time_window")
        network = values["network-isolation"]
        fields(network, {"interfaces": ["lo"], "routable_network": False}, "network")
        for k in ("network_namespace", "parent_network_namespace"):
            require(type(network.get(k)) is str and re.fullmatch(r"net:\[[0-9]+\]", network[k]),
                    "network_namespace_type")
        require(network["network_namespace"] != network["parent_network_namespace"], "shared_namespace")
    exact(values["stage-complete"], {"stage": stage, "status": "PHYSICAL_GATE_PASS",
        "producer": producer(), "result_sha256": digest(canonical(result)),
        "certified_components": 0, **{k: False for k in FALSE_AUTHORITY}}, "stage_complete")
    return {"job_id": job["id"], "commitments_verified": len(records),
            "rust_tests": sum(r[0] for r in rust), "runner_tests": 41,
            "result_sha256": digest(canonical(result)), "log_sha256": digest(raw),
            "replay_steps": len(steps) // 2, "physical_stage": "PASS_AS_CAPTURED"}


def verify_replay_steps(steps):
    require(len(steps) == 32, "replay_step_count")
    for i in range(0, len(steps), 2):
        start, end = steps[i:i+2]
        require(type(start) is dict and set(start) == {"state", "argv", "log"}, "replay_start")
        require(type(end) is dict and set(end) == {"state", "argv", "elapsed_seconds"}, "replay_end")
        exact(start["state"], "STARTED", "replay_start_state")
        exact(end["state"], "VERIFIED", "replay_end_state")
        require(type(start["argv"]) is list and bool(start["argv"])
                and all(type(a) is str for a in start["argv"]), "replay_argv")
        exact(end["argv"], start["argv"], "replay_pair")
        elapsed = end["elapsed_seconds"]
        require(type(elapsed) in (int, float) and 0 <= elapsed <= 3000, "replay_elapsed")


def verify_capture(archive=ARCHIVE_PATH, pin_path=PIN_PATH, expected_producer=PRODUCER, repo=ROOT):
    exact(expected_producer, PRODUCER, "wrong_expected_producer")
    pin = load_pin(pin_path)
    raw = read_regular(archive, limit=MAX_ARCHIVE)
    require(len(raw) == pin["archive_bytes"] and digest(raw) == pin["archive_sha256"], "archive_digest")
    members = unpack(raw, pin["members"])
    jobs = verify_metadata(members, pin)
    verify_commit(repo, PRODUCER, TREE)
    require(git(repo, "show", PRODUCER + ":" + WORKFLOW) == members["workflow.yml"], "git_workflow_mismatch")
    stages = {stage: verify_log(members[stage + ".log"], jobs[stage], stage) for stage in JOBS}
    report = {"schema": "nqc.omega.ci-capture-verification.v1", "status": "PINNED_CI_CAPTURE_VERIFIED",
        "producer_commit": PRODUCER, "producer_tree": TREE, "repository": DESTINATION,
        "repository_id": DESTINATION_ID, "run_id": RUN, "run_attempt": 1,
        "retrieved_at": pin["retrieved_at"], "archive_sha256": digest(raw),
        "consumer_source_sha256": digest(read_regular(Path(__file__))), "stages": stages,
        "trust_basis": "REVIEWED_PIN_FROM_CONNECTED_GITHUB_CAPTURE",
        "new_execution_performed": False, "new_acquisition_performed": False,
        "source_seed_reauthenticated": False, "artifact_authenticated": False, "artifact_id": None,
        "certified_components": 0, "scope": "HISTORICAL_H2_LOGS_AND_API_READBACK_ONLY",
        **{k: False for k in FALSE_AUTHORITY}}
    report["report_commitment_sha256"] = digest(canonical(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ARCHIVE_PATH)
    parser.add_argument("--pin", type=Path, default=PIN_PATH)
    parser.add_argument("--expected-producer", default=PRODUCER)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        report = verify_capture(args.archive, args.pin, args.expected_producer, args.repo)
        if args.report:
            with args.report.open("xb") as handle:
                handle.write(canonical(report))
        print(json.dumps(report, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RecursionError, UnicodeError,
            zipfile.BadZipFile, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "CI_CAPTURE_REJECTED", "reason": str(error),
                          **{k: False for k in FALSE_AUTHORITY}}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
