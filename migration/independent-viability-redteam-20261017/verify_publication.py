#!/usr/bin/env python3
"""Offline publication check: preserve base leaves and verify exact added blobs.
This checks Git tree identity, not the original import isolation verifier,
economic admission, EVM execution, or remote HEADs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

PREFIX = "migration/independent-viability-redteam-20261017/"
HEX40 = re.compile(r"^[0-9a-f]{40}$")

def blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()

def leaves(tree):
    if tree.get("truncated") is not False:
        raise ValueError("Tree must explicitly be non-truncated")
    result = {}
    for item in tree["tree"]:
        if item["type"] == "tree":
            continue
        path = item["path"]
        if path in result or not HEX40.fullmatch(item["sha"]):
            raise ValueError("Duplicate path or malformed object hash")
        if path.startswith("/") or ".." in path.split("/"):
            raise ValueError("Unsafe tree path")
        result[path] = (item["mode"], item["type"], item["sha"])
    return result

def verify(base_tree, candidate_tree, manifest_path):
    package = manifest_path.parent
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {}
    total = 0
    for row in manifest["files"]:
        rel = row["path"]
        if rel.startswith("/") or ".." in rel.split("/") or PREFIX + rel in expected or rel == manifest_path.name:
            raise ValueError("Unsafe or duplicate manifest path")
        path = package / rel
        if path.is_symlink() or not path.is_file():
            raise ValueError("Non-regular payload: " + rel)
        data = path.read_bytes()
        if (len(data), hashlib.sha256(data).hexdigest(), blob_sha(data)) != (
                row["bytes"], row["sha256"], row["git_blob_sha1"]):
            raise ValueError("Local payload changed: " + rel)
        expected[PREFIX + rel] = ("100644", "blob", row["git_blob_sha1"])
        total += len(data)
    data = manifest_path.read_bytes()
    expected[PREFIX + manifest_path.name] = ("100644", "blob", blob_sha(data))
    total += len(data)
    before, after = leaves(base_tree), leaves(candidate_tree)
    modified_or_missing = [path for path, entry in before.items() if after.get(path) != entry]
    additions = {path: entry for path, entry in after.items() if path not in before}
    active_workflows = [path for path in after if path.startswith(".github/workflows/")]
    if modified_or_missing:
        raise ValueError("Original files modified or missing: " + repr(modified_or_missing))
    if additions != expected:
        missing = sorted(set(expected) - set(additions))
        unexpected = sorted(set(additions) - set(expected))
        wrong = sorted(path for path in set(expected) & set(additions) if expected[path] != additions[path])
        raise ValueError("Addition mismatch: " + repr({"missing": missing, "unexpected": unexpected, "wrong": wrong}))
    if active_workflows:
        raise ValueError("Active workflow files present: " + repr(active_workflows))
    return {
        "status": "PASS_TREE_IDENTITY_AND_EXACT_ADDITIONS",
        "base_query_sha_field": base_tree.get("sha"),
        "candidate_tree_sha_field": candidate_tree.get("sha"),
        "original_leaves_preserved": len(before),
        "added_files": len(additions),
        "added_bytes": total,
        "modified_or_deleted_original_files": 0,
        "unexpected_additions": 0,
        "active_workflow_files": 0,
        "allowed_prefix": PREFIX,
        "original_isolation_verifier_status": "BLOCKED_INPUTS_SEPARATE_CONTROL",
        "economic_admission": "NOT_CERTIFIED",
        "network_calls_by_this_script": 0
    }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-tree", type=Path, required=True)
    parser.add_argument("--candidate-tree", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(json.loads(args.base_tree.read_text(encoding="utf-8")),
                    json.loads(args.candidate_tree.read_text(encoding="utf-8")),
                    args.manifest)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
