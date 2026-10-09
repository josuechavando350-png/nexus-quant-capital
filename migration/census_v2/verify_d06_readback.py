#!/usr/bin/env python3
"""Independent bounded read-back of the fixed new-repository D06 artifact.

The caller acquires REST metadata through the authenticated GitHub connection.
Offline JSON cannot prove its own API origin. This consumer authenticates bytes,
final job metadata and replay-output consistency; it does not re-execute Rust or
grant Census, producer-review, live-market or economic authority.
"""
import argparse
import datetime as dt
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "original_d06_source", ROOT / "ci/nqc-census/verify_rmc006_recertification_source.py")
SOURCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SOURCE)
require, equal = SOURCE.require, SOURCE.equal

PIN = {
    "repository": "josuechavando350-png/nexus-quant-capital",
    "repository_id": 1411047452,
    "commit": "eb2547d77e78df0b3f1c7a6d80d73634883c3e70",
    "tree": "abfa5c86588960263454be3c58c60662d1c82c21",
    "branch": "nqc/d06-standalone-certification",
    "workflow_id": 379214346,
    "workflow_path": ".github/workflows/nqc-d06-standalone.yml",
    "run_id": 37893144639,
    "attempt": 1,
    "job_id": 113698359497,
    "artifact_id": 11599957605,
    "artifact_bytes": 13553756,
    "artifact_sha256": "2ca50aa569e85156b3b585f2c396a8f91f3adb9c67c1ae58c6bbdf5aececbdec",
    "index_sha256": "dd3fa4529e7208593fbe6de6d4488fcfb6a9ff6adb3db8484835a988bff925c1",
    "members": 4328,
    "expanded_bytes": 19365712,
}
NEGATIVES = {
    "unknown-schema", "unknown-field", "fabricated-pass", "fabricated-reserve-count",
    "configuration-fingerprint", "missing-provider", "duplicate-provider", "extra-provider",
    "provider-order", "wrong-manifest", "wrong-anchor", "missing-anchor",
    "changed-provider-namespace", "missing-checkpoint", "corrupted-checkpoint",
    "missing-head", "missing-stream", "missing-manifest", "missing-request",
    "missing-response", "missing-chunk", "corrupted-chunk",
}
REQUIRED_STEPS = {
    2: "Checkout exact dedicated-branch push producer",
    3: "Fail closed on any producer or seed substitution",
    4: "Acquire fixed public history and current original metadata only",
    5: "Verify closed standalone composition before dependency acquisition",
    6: "Acquire pinned Rust toolchain and locked dependency cache before disconnecting",
    7: "Materialize immutable historical source in the adapter's enforced disconnected namespace",
    8: "Prepare a separate exact producer build copy without historical refs",
    9: "Disconnected Rust gates and original package authentication",
    10: "Replay through the explicit read-only prospective adapter",
    11: "Bind new evidence to producer identity without claiming final GitHub success",
    12: "Preserve only new evidence and original provenance",
    13: "Report immutable upload identity for separate final read-back",
}


def time(value):
    require(type(value) is str and value.endswith("Z"), "UTC timestamp required")
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.utcoffset() == dt.timedelta(0), "UTC timestamp required")
    return result


def metadata(run, artifact, jobs, commit, now):
    expected = {"id": PIN["run_id"], "run_attempt": 1, "event": "push",
                "workflow_id": PIN["workflow_id"], "path": PIN["workflow_path"],
                "name": "NQC Standalone D06 Offline Verification",
                "head_sha": PIN["commit"], "head_branch": PIN["branch"],
                "status": "completed", "conclusion": "success"}
    for key, value in expected.items():
        equal(run.get(key), value, "run " + key)
    for key in ("repository", "head_repository"):
        equal(run[key]["id"], PIN["repository_id"], key + " id")
        equal(run[key]["full_name"], PIN["repository"], key + " name")
    equal(run["head_commit"]["id"], PIN["commit"], "run commit")
    equal(run["head_commit"]["tree_id"], PIN["tree"], "run tree")
    equal(commit["sha"], PIN["commit"], "commit endpoint sha")
    equal(commit["commit"]["tree"]["sha"], PIN["tree"], "commit endpoint tree")
    equal(artifact["id"], PIN["artifact_id"], "artifact id")
    equal(artifact["digest"], "sha256:" + PIN["artifact_sha256"], "artifact digest")
    equal(artifact["size_in_bytes"], PIN["artifact_bytes"], "artifact size")
    equal(artifact["name"], f"nqc-standalone-d06-{PIN['commit']}-{PIN['run_id']}-1", "artifact name")
    equal(artifact["expired"], False, "expired artifact")
    for key, value in {"id": PIN["run_id"], "repository_id": PIN["repository_id"],
                       "head_repository_id": PIN["repository_id"],
                       "head_branch": PIN["branch"], "head_sha": PIN["commit"]}.items():
        equal(artifact["workflow_run"][key], value, "artifact run " + key)
    require(time(run["run_started_at"]) <= time(artifact["created_at"]) <=
            time(run["updated_at"]) <= now < time(artifact["expires_at"]), "run/artifact chronology")
    equal(jobs["total_count"], 1, "job count")
    equal(len(jobs["jobs"]), 1, "job inventory")
    job = jobs["jobs"][0]
    for key, value in {"id": PIN["job_id"], "run_id": PIN["run_id"], "run_attempt": 1,
                       "head_sha": PIN["commit"], "status": "completed", "conclusion": "success",
                       "name": "standalone-d06"}.items():
        equal(job.get(key), value, "job " + key)
    steps = {step["number"]: step for step in job["steps"]}
    equal(len(steps), len(job["steps"]), "duplicate step")
    for number, name in REQUIRED_STEPS.items():
        equal(steps[number]["name"], name, "step name")
    for step in steps.values():
        equal(step["status"], "completed", "step status")
        equal(step["conclusion"], "success", "step conclusion")
    require(time(run["run_started_at"]) <= time(job["started_at"]) <=
            time(job["completed_at"]) <= time(run["updated_at"]), "job chronology")


def inventory(data):
    equal(len(data), PIN["artifact_bytes"], "ZIP size")
    equal(SOURCE.sha256(data), PIN["artifact_sha256"], "ZIP hash")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        equal(len(entries), PIN["members"], "ZIP member count")
        equal(sum(e.file_size for e in entries), PIN["expanded_bytes"], "expanded size")
        names = set()
        for entry in entries:
            name = SOURCE.safe_path(entry.filename)
            equal(entry.orig_filename, name, "ZIP original name")
            require(name.casefold() not in names, "duplicate ZIP member")
            names.add(name.casefold())
            require(not entry.is_dir() and not entry.flag_bits & 1, "directory/encrypted ZIP member")
            mode = entry.external_attr >> 16
            # actions/upload-artifact emits permission-only modes without S_IFREG.
            require(stat.S_IFMT(mode) in (0, stat.S_IFREG), "special ZIP member")
            require(entry.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), "ZIP compression")
        raw = archive.read("evidence-index.json")
        equal(SOURCE.sha256(raw), PIN["index_sha256"], "index hash")
        index = SOURCE.strict_json(raw, "evidence index")
        equal(index["schema"], "nqc-standalone-d06-evidence-index-v1", "index schema")
        listed = set()
        members = {"evidence-index.json": raw}
        for row in index["files"]:
            SOURCE.exact_keys(row, {"path", "size", "sha256"}, "inventory row")
            name = SOURCE.safe_path(row["path"])
            require(name not in listed and name != "evidence-index.json", "duplicate index member")
            listed.add(name)
            content = archive.read(name)
            equal(len(content), row["size"], name + " size")
            equal(SOURCE.sha256(content), row["sha256"], name + " hash")
            members[name] = content
        equal(set(archive.namelist()), listed | {"evidence-index.json"}, "complete inventory")
    return members, index


def semantics(members, index, run):
    load = lambda name: SOURCE.strict_json(members[name], name)
    producer = index["producer"]
    for key in ("repository", "repository_id", "commit", "tree", "workflow_path"):
        equal(producer[key], PIN[key], "producer " + key)
    equal(producer["run_id"], str(PIN["run_id"]), "producer run")
    equal(producer["run_attempt"], "1", "producer attempt")
    equal(producer["ref"], "refs/heads/" + PIN["branch"], "producer ref")
    equal(producer["event"], "push", "producer event")
    equal(producer["push_context"]["after"], PIN["commit"], "push after")
    for key in ("forced", "deleted"):
        equal(producer["push_context"][key], False, "push " + key)
    equal(index["local_gates_succeeded"], True, "local gates")
    for key in ("canonical_recertification", "certification_transfer", "downstream_acceptance",
                "final_github_run_verified", "immutable_artifact_metadata_verified",
                "reviewed_producer_authorization_verified"):
        equal(index[key], False, "producer non-claim " + key)
    proof = load("offline-verification.json")
    for key in ("source_unchanged", "current_replay_byte_identical",
                "history_replay_byte_identical", "closeout_byte_identical"):
        equal(proof[key], True, "replay proof " + key)
    equal(proof["canonical_recertification"], False, "replay non-claim")
    equal(proof["code_commit"], PIN["commit"], "proof commit")
    equal(proof["code_tree"], PIN["tree"], "proof tree")
    source_pin = SOURCE.load_pin()
    original, _ = SOURCE.authenticate_archive(source_pin, members["original-seed/source.zip"])
    equal(proof["source_store_root"], source_pin["store_evidence_root"], "original store root")
    equal(proof["result_store_root"], source_pin["store_evidence_root"], "replayed store root")
    for name, content in original.items():
        if name.startswith("store/"):
            equal(members[name], content, "unchanged original store " + name)
    for first, second in (("current.json", "current-rerun.json"),):
        equal(members[first], members[second], "independent replay output comparison")
    closeouts = {name for name in members if name.startswith("closeout/")}
    require(bool(closeouts), "missing closeout")
    equal({name.replace("closeout-rerun/", "closeout/", 1) for name in members
           if name.startswith("closeout-rerun/")}, closeouts, "closeout inventory")
    for name in closeouts:
        equal(members[name], members[name.replace("closeout/", "closeout-rerun/", 1)], "closeout replay bytes")
    negative = load("negative-tests/results.json")
    equal(negative["schema"], "nqc-rmc006-replay-negatives-v1", "negative schema")
    equal(len(negative["cases"]), 22, "negative count")
    equal({row["case"] for row in negative["cases"]}, NEGATIVES, "negative inventory")
    for row in negative["cases"]:
        equal(row["rejected"], True, "negative rejected")
        equal(row["store_unchanged"], True, "negative preserved store")
    require(time(run["run_started_at"]) <= time(proof["verification_started_at"]) <=
            time(proof["verification_completed_at"]) <= time(index["indexed_at"]) <=
            time(run["updated_at"]), "verification chronology")
    equal(proof["original_observation_at"], "2026-10-01T05:23:35Z", "historical observation time")
    return {"source_indexed_members": len(original) - 1, "new_indexed_members": len(members) - 1,
            "negative_cases": 22, "closeout_files_compared": len(closeouts),
            "original_anchor": source_pin["anchor"], "original_store_root": source_pin["store_evidence_root"]}


def verify(archive, snapshots):
    now = dt.datetime.now(dt.timezone.utc)
    parsed = {k: SOURCE.strict_json(v, k) for k, v in snapshots.items()}
    metadata(*(parsed[k] for k in ("run", "artifact", "jobs", "commit")), now=now)
    members, index = inventory(archive)
    details = semantics(members, index, parsed["run"])
    return {"schema": "nqc-d06-independent-readback-v1",
            "verifier_source_sha256": SOURCE.sha256(Path(__file__).read_bytes()),
            "original_consumer_sha256": SOURCE.sha256(Path(SPEC.origin).read_bytes()),
            "status": "EXACT_ARTIFACT_AND_REPLAY_OUTPUT_READBACK_PASS",
            "verified_at": now.isoformat().replace("+00:00", "Z"), "pin": PIN,
            "metadata_trust_basis": "CALLER_ACQUIRED_AUTHENTICATED_GITHUB_API_RESPONSES",
            "metadata_sha256": {k: SOURCE.sha256(v) for k, v in snapshots.items()},
            "verified": details, "canonical_recertification": False,
            "semantic_replay_reexecuted_by_this_consumer": False,
            "reviewed_producer_authorization_verified": False,
            "downstream_acceptance": False, "real_market_census_closed": False,
            "non_claims": ["NO_NEW_MARKET_OBSERVATION", "NO_CAPITAL_OR_ECONOMIC_AUTHORITY",
                           "NO_INHERITED_CERTIFICATION", "NO_LIVE_EXECUTION_AUTHORITY"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--metadata-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = SOURCE.read_regular(args.archive, 20 * 1024 * 1024)
    snapshots = {k: SOURCE.read_regular(args.metadata_dir / (k + ".json"), 2 * 1024 * 1024)
                 for k in ("run", "artifact", "jobs", "commit")}
    result = verify(raw, snapshots)
    with args.output.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    print(result["status"])


if __name__ == "__main__":
    main()
