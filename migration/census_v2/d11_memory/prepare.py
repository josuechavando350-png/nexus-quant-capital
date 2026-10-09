#!/usr/bin/env python3
"""Apply the pinned research overlay exclusively to a fresh exported build copy."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def prepare(repo, out):
    repo, out = repo.resolve(), out.resolve()
    manifest = json.loads((HERE / "overlay-manifest.json").read_bytes())
    patch = HERE / "memory-overlay.patch"
    if out.exists() or out == repo or repo in out.parents:
        raise ValueError("build must be a new path outside the original repository")
    if digest(patch) != manifest["patch_sha256"]:
        raise ValueError("overlay hash differs from pinned manifest")
    tree = subprocess.check_output(["git", "rev-parse", manifest["base_commit"] + "^{tree}"], cwd=repo).decode().strip()
    if tree != manifest["base_tree"]:
        raise ValueError("base Git tree mismatch")
    out.mkdir(parents=True)
    with tempfile.TemporaryFile() as archive:
        subprocess.run(["git", "archive", "--format=tar", manifest["base_commit"]], cwd=repo, stdout=archive, check=True)
        archive.seek(0)
        subprocess.run(["tar", "-xf", "-", "-C", str(out)], stdin=archive, check=True)
    for item in manifest["changed_files"]:
        path = out / item["path"]
        observed = digest(path) if path.exists() else None
        if observed != item["before_sha256"]:
            raise ValueError("pre-overlay source differs: " + item["path"])
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=out, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=out, check=True)
    for item in manifest["changed_files"]:
        if digest(out / item["path"]) != item["after_sha256"]:
            raise ValueError("post-overlay source differs: " + item["path"])
    (out / "RESEARCH_OVERLAY.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.repo, args.out), sort_keys=True))
