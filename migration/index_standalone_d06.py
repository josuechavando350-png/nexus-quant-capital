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


def verify_privilege_isolation(network):
    require(network.get('isolation_mode') == 'sudo-drop', 'explicit privilege-drop mode required')
    require(network.get('routable_network') is False and network.get('interfaces') == ['lo'] and
            all(type(network.get(key)) is str and re.fullmatch(r'net:\[[0-9]+\]', network[key])
                for key in ('network_namespace', 'parent_network_namespace')) and
            network['network_namespace'] != network['parent_network_namespace'],
            'missing disconnected privilege-drop proof')
    require(all(type(network.get(key)) is str and re.fullmatch(r'mnt:\[[0-9]+\]', network[key])
                for key in ('mount_namespace', 'parent_mount_namespace')) and
            network['mount_namespace'] != network['parent_mount_namespace'],
            'missing separate mount namespace proof')
    proof = network.get('privilege_drop', {})
    require(set(proof) == {'schema', 'caller_uid', 'caller_gid', 'uids', 'gids', 'groups',
                          'capabilities', 'no_new_privs'} and
            proof['schema'] == 'nqc-privilege-drop-v1', 'privilege proof schema differs')
    uid, gid = proof['caller_uid'], proof['caller_gid']
    require(type(uid) is int and uid > 0 and type(gid) is int and gid > 0,
            'privilege proof caller differs')
    require(proof['uids'] == [uid] * 4 and proof['gids'] == [gid] * 4 and
            all(type(value) is int for key in ('uids', 'gids') for value in proof[key]) and
            proof['groups'] == [] and type(proof['no_new_privs']) is int and proof['no_new_privs'] == 1,
            'privilege proof identities or no-new-privs differ')
    caps = proof['capabilities']
    require(set(caps) == {'CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb'} and
            all(type(value) is int and value == 0 for value in caps.values()),
            'privilege proof capabilities retained')
    return uid, gid



def verify_prospective_runner(repo, receipt, adapter_name, original_name):
    method = 'fd-pinned-detached-readonly-mount-then-sudo-drop-v1'
    require(set(receipt) == {'schema', 'method', 'original_runner_byte_identical', 'certification_inherited',
                            'original_path', 'original_sha256', 'adapter_path', 'adapter_sha256', 'source_mount',
                            'boundary_path', 'boundary_sha256', 'root_setup_sha256'},
            'prospective runner receipt fields differ')
    require(receipt['schema'] == 'nqc-prospective-d06-runner-v1' and receipt['method'] == method and
            receipt['original_runner_byte_identical'] is False and receipt['certification_inherited'] is False,
            'prospective runner authority differs')
    for prefix, path in (('original', 'ci/nqc-census/' + original_name), ('adapter', 'migration/' + adapter_name)):
        require(receipt[prefix + '_path'] == path and
                receipt[prefix + '_sha256'] == hashlib.sha256((repo / path).read_bytes()).hexdigest(),
                'prospective runner byte identity differs')
    import ast
    boundary = repo / 'migration/premounted_d06.py'
    definitions = {node.targets[0].id: node.value for node in ast.parse(boundary.read_bytes()).body
                   if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)}
    root_setup = ast.literal_eval(definitions['MOUNT_SETUP']) + ast.literal_eval(definitions['ROOT_SETUP'].right)
    require(receipt['boundary_path'] == 'migration/premounted_d06.py' and
            receipt['boundary_sha256'] == hashlib.sha256(boundary.read_bytes()).hexdigest() and
            receipt['root_setup_sha256'] == hashlib.sha256(root_setup.encode()).hexdigest(),
            'privileged setup byte identity differs')
    proof = receipt['source_mount']
    require(set(proof) == {'schema', 'method', 'read_only', 'write_open_errno', 'probe',
                          'probe_creates_or_truncates', 'mount_flags', 'descendant_mounts', 'private_mount', 'premount_id', 'readonly_mount_id'} and
            proof['schema'] == 'nqc-premounted-source-v1' and proof['method'] == method and
            proof['read_only'] is True and type(proof['write_open_errno']) is int and proof['write_open_errno'] == 30 and
            proof['probe'] == 'evidence-index.json' and proof['probe_creates_or_truncates'] is False and
            proof['descendant_mounts'] is False and proof['private_mount'] is True and
            type(proof['premount_id']) is int and proof['premount_id'] > 0 and
            type(proof['readonly_mount_id']) is int and proof['readonly_mount_id'] > 0 and
            proof['premount_id'] != proof['readonly_mount_id'] and
            type(proof['mount_flags']) is list and all(type(flag) is str for flag in proof['mount_flags']) and
            'ro' in proof['mount_flags'] and 'rw' not in proof['mount_flags'],
            'genuine read-only source proof missing')

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
    materializer_ids = verify_privilege_isolation(adapter['network_isolation'])
    build_ids = verify_privilege_isolation(load(root / 'code-gates/build-network-isolation.json'))
    require(materializer_ids == build_ids, 'materializer/build original runner identity differs')
    replay_network = load(root / 'code-gates/replay-network-isolation.json')
    replay_ids = verify_privilege_isolation(replay_network)
    require(replay_ids == build_ids, 'replay/build original runner identity differs')
    require(all(network[key] == replay_network[key] for key in ('network_namespace', 'parent_network_namespace')),
            'replay network proof differs')
    verify_prospective_runner(repo, load(root / 'runner-identity.json'),
                              'run_premounted_d06_v1.py', 'run_rmc006_recertification.py')
    verify_prospective_runner(repo, load(root / 'negative-tests/runner-identity.json'),
                              'test_premounted_d06_replay_v1.py', 'test_rmc006_recertification_replay.py')
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
             "runner_method": "fd-pinned-detached-readonly-mount-then-sudo-drop-v1",
             "original_runner_byte_identical": False,
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
