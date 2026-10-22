#!/usr/bin/env python3
"""Read-only proof that this branch changes only the isolated Miner subtree."""
import argparse
import json
import subprocess
from pathlib import Path

PREFIX = "migration/nqc-miner/"
BASE = "16e352225ba8a6a931834c4edf3d86d9a2924b7d"

def check(root: Path, base: str):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).splitlines()
    names = set(git("diff", "--name-only", base, "--"))
    names.update(git("ls-files", "--others", "--exclude-standard"))
    outside = sorted(name for name in names if not name.startswith(PREFIX))
    if outside:
        raise ValueError("changes outside the Miner subtree: " + ", ".join(outside))
    for name in names:
        path = root / name
        if path.is_symlink():
            raise ValueError("symlink in Miner payload")
        if path.is_file() and path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("oversize payload requires separate artifact review: " + name)
    return {"status": "MINER_SCOPE_PASS", "base_commit": base,
            "changed_paths": len(names), "outside_miner": outside,
            "observer_files_changed": 0, "remote_branches_modified_by_this_check": False}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=BASE)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    print(json.dumps(check(root, args.base), indent=2, sort_keys=True))
