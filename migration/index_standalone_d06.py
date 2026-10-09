#!/usr/bin/env python3
"""Index successful local gates without claiming final GitHub/certification status."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

REPOSITORY = "josuechavando350-png/nexus-quant-capital"
REPOSITORY_ID = "1411047452"
WORKFLOW = ".github/workflows/nqc-d06-standalone.yml"
PRODUCER_EVENT = "push"
PRODUCER_REF = "refs/heads/nqc/d06-standalone-certification"
SOURCE_COMMIT = "e259739c9f75fedcd1061d2f78d6b8852e7a3060"
SOURCE_ARCHIVE_SHA256 = "1cdb46fca52ebf1e0e2094b1c14b19384ecb7beceb50229b967592ab7a0308b4"
SOURCE_ARCHIVE_SIZE = 6709740
NEGATIVES = {
    "unknown-schema", "unknown-field", "fabricated-pass", "fabricated-reserve-count",
    "configuration-fingerprint", "missing-provider", "duplicate-provider",
    "extra-provider", "provider-order", "wrong-manifest", "wrong-anchor", "missing-anchor",
    "changed-provider-namespace", "missing-checkpoint", "corrupted-checkpoint",
    "missing-head", "missing-stream", "missing-manifest", "missing-request",
    "missing-response", "missing-chunk", "corrupted-chunk",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path):
    require(stat.S_ISREG(path.lstat().st_mode), "nonregular evidence input")
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    def constant(_value):
        raise ValueError("non-finite JSON number")
    return json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=constant)


def producer_context(environment, head, tree, event):
    require(all(re.fullmatch("[0-9a-f]{40}", value) for value in (head, tree)),
            "expected exact producer identity")
    require(environment.get("GITHUB_EVENT_NAME") == PRODUCER_EVENT, "dedicated-branch push required")
    require(environment.get("GITHUB_REF") == PRODUCER_REF and
            environment.get("GITHUB_REF_TYPE") == "branch", "dedicated producer branch differs")
    require(environment.get("GITHUB_REPOSITORY") == REPOSITORY and
            environment.get("GITHUB_REPOSITORY_ID") == REPOSITORY_ID, "producer repository changed")
    require(environment.get("GITHUB_SHA") == head and
            environment.get("GITHUB_WORKFLOW_SHA") == head, "workflow/producer head differs")
    reference = environment.get("GITHUB_WORKFLOW_REF", "")
    require(reference == REPOSITORY + "/" + WORKFLOW + "@" + PRODUCER_REF,
            "workflow path/ref differs")
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        require(re.fullmatch("[1-9][0-9]*", environment.get(key, "")), "invalid run identity")
    require(event.get("ref") == PRODUCER_REF and event.get("after") == head and
            event.get("head_commit", {}).get("id") == head, "push payload ref/head differs")
    require(type(event.get("before")) is str and re.fullmatch("[0-9a-f]{40}", event["before"]),
            "push before identity differs")
    require(type(event.get("created")) is bool and
            event["created"] == (event["before"] == "0" * 40), "push creation context differs")
    require(event.get("forced") is False and event.get("deleted") is False,
            "forced or deleted push rejected")
    repository = event.get("repository", {})
    require(type(repository.get("id")) is int and repository["id"] == int(REPOSITORY_ID) and
            repository.get("full_name") == REPOSITORY, "push payload repository differs")
    return {"repository": REPOSITORY, "repository_id": int(REPOSITORY_ID),
            "commit": head, "tree": tree, "event": PRODUCER_EVENT, "ref": PRODUCER_REF,
            "tree_basis": "CHECKED_EXACT_EVENT_COMMIT_TREE", "workflow_path": WORKFLOW,
            "workflow_ref": reference, "workflow_sha": head,
            "run_id": environment["GITHUB_RUN_ID"],
            "run_attempt": environment["GITHUB_RUN_ATTEMPT"],
            "push_context": {key: event[key] for key in ("before", "after", "created", "deleted", "forced")}}


def make_index(repo, root, head, tree, environment=os.environ):
    repo, root = Path(repo).absolute(), Path(root).absolute()
    require(repo.resolve() == repo and root.resolve() == root, "evidence or repo path aliases")
    require(not root.is_relative_to(repo), "evidence must be outside producer")
    producer = producer_context(environment, head, tree, load(Path(environment["GITHUB_EVENT_PATH"])))
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()
    require(git("rev-parse", "HEAD") == head and git("rev-parse", "HEAD^{tree}") == tree,
            "producer checkout identity differs")
    require(not git("status", "--porcelain=v1", "--untracked-files=all"), "producer checkout dirty")
    proof = load(root / "offline-verification.json")
    require(proof["code_commit"] == head and proof["code_tree"] == tree,
            "offline producer identity differs")
    require(proof["source_commit"] == "a33a012591cd6625ddb921d995bb1bd95b4a5406" and
            proof["source_run_id"] == 36820687233 and proof["source_artifact_id"] == 11143129177,
            "original seed identity changed")
    for key in ("source_unchanged", "current_replay_byte_identical",
                "history_replay_byte_identical", "closeout_byte_identical"):
        require(proof.get(key) is True, "missing successful replay check: " + key)
    require(proof.get("canonical_recertification") is False, "unexpected canonical claim")
    times = [datetime.fromisoformat(proof[key].replace("Z", "+00:00")) for key in
             ("original_observation_at", "verification_started_at", "verification_completed_at")]
    require(all(value.tzinfo is not None and value.utcoffset().total_seconds() == 0 for value in times),
            "verification times must be actual UTC timestamps")
    require(times[0] <= times[1] <= times[2] <= datetime.now(timezone.utc), "verification chronology differs")
    network = load(root / "network-isolation.json")
    require(network["routable_network"] is False and network["interfaces"] == ["lo"] and
            network["network_namespace"] != network["parent_network_namespace"], "missing disconnected proof")
    negative = load(root / "negative-tests/results.json")
    cases = negative.get("cases", [])
    require(negative["schema"] == "nqc-rmc006-replay-negatives-v1" and
            len(cases) == len(NEGATIVES) and {row["case"] for row in cases} == NEGATIVES and
            all(row["rejected"] is True and row["store_unchanged"] is True for row in cases),
            "incomplete or failed real replay negative matrix")
    adapter = load(root / "historical-source/HISTORICAL-ADAPTER.json")
    require(adapter["schema"] == "nqc-standalone-historical-materialization-v1" and
            adapter["status"] == "HISTORICAL_SOURCE_MATERIALIZED_CONSUMER_BOUND",
            "historical adapter did not complete")
    require(adapter["historical_source"]["commit"] == SOURCE_COMMIT, "historical source changed")
    consumer = adapter["consumer"]
    require(consumer["commit"] == head and consumer["tree"] == tree and
            consumer["repository"] == REPOSITORY and consumer["repository_id"] == int(REPOSITORY_ID),
            "historical adapter consumer identity differs")
    for key in ("canonical_recertification", "certification_transferred",
                "new_consumer_is_original_descendant", "live_network_fallback", "production_authority"):
        require(adapter["truth_boundaries"].get(key) is False, "historical authority expanded")
    materialization = root / "historical-source/effective-source/MATERIALIZATION.json"
    require(hashlib.sha256(materialization.read_bytes()).hexdigest() ==
            adapter["historical_materialization_receipt"]["sha256"] and
            adapter["historical_materialization_receipt"]["preserved_unchanged"] is True,
            "original materialization receipt was changed")
    original = load(root / "original-seed/source-provenance-after.json")
    require(original["original_repository"] == {
                "full_name": "josuechavando350-png/nexus-engine", "id": 1333360261} and
            original["original_run"]["id"] == 36820687233 and
            original["original_artifact"]["id"] == 11143129177 and
            original["canonical_recertification"] is False and
            original["extracted_source_rechecked"] is True, "original seed provenance changed")
    archive = root / "original-seed/source.zip"
    require(archive.stat().st_size == SOURCE_ARCHIVE_SIZE and
            hashlib.sha256(archive.read_bytes()).hexdigest() == SOURCE_ARCHIVE_SHA256,
            "preserved original archive changed")
    files = []
    for path in sorted(root.rglob("*")):
        mode = path.lstat().st_mode
        require(stat.S_ISDIR(mode) or stat.S_ISREG(mode), "nonregular evidence output")
        if stat.S_ISDIR(mode):
            continue
        require(path.name != "evidence-index.json" or path.parent != root,
                "index must be a new file")
        data = path.read_bytes()
        files.append({"path": path.relative_to(root).as_posix(), "size": len(data),
                      "sha256": hashlib.sha256(data).hexdigest()})
    index = {"schema": "nqc-standalone-d06-evidence-index-v1", "producer": producer,
             "indexed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
             "local_gates_succeeded": True, "final_github_run_verified": False,
             "reviewed_producer_authorization_verified": False,
             "immutable_artifact_metadata_verified": False, "canonical_recertification": False,
             "certification_transfer": False, "downstream_acceptance": False,
             "new_artifact_id": None, "authority": "PENDING_INDEPENDENT_EXACT_HEAD_GITHUB_READBACK",
             "files": files}
    with (root / "evidence-index.json").open("x") as stream:
        json.dump(index, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    return index


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-tree", required=True)
    args = parser.parse_args()
    make_index(args.repo, args.evidence, args.expected_commit, args.expected_tree)
