#!/usr/bin/env python3
"""Offline NQC V2 migration integrity checker; does not access network or execute trading."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFIX = "migration/engine-v2-20261015/"
IGNORE = {
    PREFIX + "README.md",
    PREFIX + "MANIFEST.json",
    PREFIX + "verify_import.py",
}
UNTOUCHED = (".gitignore", "AGENTS.md", "README.md", "ci", "nqc-census")

def git(*args):
    proc = subprocess.run(
        ["git", *args], cwd=ROOT, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr.decode(errors="replace"))
    return proc.stdout

def tree(ref):
    out = {}
    for item in git("ls-tree", "-r", "-z", ref).split(b"\0"):
        if not item:
            continue
        attributes, path = item.split(b"\t", 1)
        mode, object_type, sha = attributes.split(b" ")
        if object_type != b"blob":
            continue
        out[path.decode("utf-8")] = (mode.decode(), sha.decode())
    return out

def main():
    manifest = json.loads((ROOT / PREFIX / "MANIFEST.json").read_text())
    head = tree("HEAD")
    expected = {}
    for item in manifest["files"]:
        path = item["path"]
        if path in expected:
            raise ValueError("Duplicate manifest path: " + path)
        if not path.startswith(PREFIX):
            raise ValueError("Unexpected path: " + path)
        expected[path] = (item["mode"], item["sha"])
    actual = {p: v for p, v in head.items() if p.startswith(PREFIX) and p not in IGNORE}
    missing, extra = set(expected) - set(actual), set(actual) - set(expected)
    mismatch = [p for p in expected.keys() & actual.keys() if expected[p] != actual[p]]
    if missing or extra or mismatch:
        raise ValueError("Manifest mismatch; missing=%s extra=%s mismatches=%s" %
                         (sorted(missing), sorted(extra), sorted(mismatch)))
    active = [p for p in head if p.startswith(".github/workflows/")]
    if active:
        raise ValueError("ACTIVE_WORKFLOWS_DETECTED: " + repr(active))
    undelimited = [p for p in actual if "/workflows-disabled/" in p and not p.endswith(".disabled")]
    if undelimited:
        raise ValueError("Workflow without disabled suffix: " + repr(undelimited))
    base = manifest["baseline_commit"]
    for path in UNTOUCHED:
        if git("rev-parse", "HEAD:" + path).strip() != git("rev-parse", base + ":" + path).strip():
            raise ValueError("Original code modified: " + path)
    print("PASS: %d migration source blobs SHA/mode matched, 0 active workflows, base untouched" % len(expected))
    print("Scope: archival transfer only; no CI, no runtime certification, no commercial P&L proof")

if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print("FAIL:", err, file=sys.stderr)
        sys.exit(1)
