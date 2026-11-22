"""Resumable first-party QA inventory for the currently checked-out Git revision."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

from .quality import is_qa_source, sha, source_snapshot
from .safe_io import canonical, read_artifact


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def manifest(repo, commit):
    items = {}
    raw = git(repo, "ls-tree", "-r", "-z", "--full-tree", commit, "--", "superhunter")
    for record in raw.split(b"\0"):
        if not record:
            continue
        header, name = record.split(b"\t", 1)
        mode, kind, oid = header.decode().split()
        rel = name.decode().removeprefix("superhunter/")
        if not is_qa_source(rel):
            continue
        if kind != "blob" or mode not in ("100644", "100755"):
            raise ValueError(f"unexpected source type: {rel}")
        items[rel] = oid
    if not items:
        raise ValueError("empty Git inventory")
    return items


def verified_digest(root, rel, oid, algorithm):
    raw = read_artifact(root, rel)
    blob = hashlib.new(algorithm, b"blob " + str(len(raw)).encode() + b"\0" + raw)
    if blob.hexdigest() != oid:
        raise ValueError(f"file differs from the pinned revision: {rel}")
    return sha(raw)


def inspect(repo, state, batch_size, max_batches, status_only=False):
    if batch_size < 1 or (max_batches is not None and max_batches < 1):
        raise ValueError("batch sizes must be positive")
    repo = repo.resolve(strict=True)
    if state.resolve().is_relative_to(repo):
        raise ValueError("store the progress database outside the checkout")
    head = git(repo, "rev-parse", "--verify", "HEAD").decode().strip()
    entries = manifest(repo, head)
    root = repo / "superhunter"
    if root.is_symlink():
        raise ValueError("source root symlink rejected")
    algorithm = git(repo, "rev-parse", "--show-object-format").decode().strip()
    # Changes to the detector or eligible paths start a separate work list.
    run = sha(canonical([head, entries, 1]))
    db = sqlite3.connect(state, timeout=60)
    try:
        with db:
            db.execute("CREATE TABLE IF NOT EXISTS files "
                       "(run TEXT, path TEXT, digest TEXT NOT NULL, PRIMARY KEY(run,path))")
        batches = 0
        while True:
            db.execute("BEGIN IMMEDIATE")
            done = dict(db.execute("SELECT path,digest FROM files WHERE run=?", (run,)))
            if not done.keys() <= entries.keys():
                raise ValueError("unknown path in saved progress")
            pending = sorted(entries.keys() - done.keys())
            if not pending or status_only or (max_batches is not None and batches >= max_batches):
                break
            for rel in pending[:batch_size]:
                digest = verified_digest(root, rel, entries[rel], algorithm)
                db.execute("INSERT INTO files VALUES(?,?,?)", (run, rel, digest))
            db.commit()
            batches += 1
        if not pending:
            expected = {rel: verified_digest(root, rel, oid, algorithm) for rel, oid in entries.items()}
            if done != expected or expected != source_snapshot(root):
                raise ValueError("completed inventory differs from the pinned files or filesystem snapshot")
        if git(repo, "rev-parse", "--verify", "HEAD").decode().strip() != head:
            raise ValueError("checkout changed during inventory")
        return {"commit": head, "status": "partial" if pending else "complete",
                "total": len(entries), "reviewed_count": len(done),
                "reviewed": sorted(done), "pending": pending,
                "snapshot_sha256": None if pending else sha(canonical(done))}
    finally:
        db.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = inspect(args.repo, args.state, args.batch_size, args.max_batches, args.status)
    except (ValueError, OSError, sqlite3.Error, subprocess.CalledProcessError) as exc:
        parser.exit(2, f"inventory incomplete: {exc}\n")
    print(json.dumps(report, sort_keys=True))
    return 0
