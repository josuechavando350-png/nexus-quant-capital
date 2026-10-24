#!/usr/bin/env python3
"""Archive verified Miner collections locally, with atomic publication and revocation.

The archive is private to Miner. There is no remote upload, broker or database.
A receipt publishes an immutable snapshot only after all its files are durable.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import uuid

from export_parquet import (
    ExportError, MAX_SEGMENT, _binary_json, _bounded_read, _check_path,
    _copy_bounded, _file_sha, _json, _owner, _sha, _write_new, export_journal,
)

OWNER_SCHEMA = "nqc-miner-local-archive-v2"
SNAPSHOT_SCHEMA = "nqc-miner-collection-snapshot-v1"
RECEIPT_SCHEMA = "nqc-miner-archive-receipt-v2"
ROOT_FILES = {"owner.json": 65536, "config.json": 1048576,
              "collector.json": 65536, "events.jsonl": MAX_SEGMENT}
WINDOW_FILES = {k: v for k, v in ROOT_FILES.items() if k != "collector.json"}
LOCK_MAGIC = b"nqc-miner-archive-kernel-lock-v1\n"
MAX_RECEIPTS = 10000


def packed(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def new_json(path, value):
    _write_new(path, packed(value) + b"\n")


def init_archive(path: Path, archive_id: str):
    if str(uuid.UUID(archive_id)) != archive_id:
        raise ExportError("archive_id must be a canonical UUID")
    path = _check_path(path, must_exist=False)
    path.mkdir(mode=0o700, exist_ok=False)
    new_json(path / "owner.json", {"schema": OWNER_SCHEMA, "namespace": "nqc_miner_v1",
        "producer": "nqc-miner", "archive_id": archive_id, "observer_bridge_enabled": False,
        "remote_upload_enabled": False})
    _write_new(path / "writer.lock", LOCK_MAGIC)
    for name in ("objects", "commits", "staging"):
        (path / name).mkdir(mode=0o700)
    sync_dir(path)
    sync_dir(path.parent)


@contextmanager
def archive_lock(path):
    path = _check_path(path)
    owner = _json(_bounded_read(path / "owner.json", 65536))
    if not isinstance(owner, dict) or not isinstance(owner.get("archive_id"), str):
        raise ExportError("foreign archive owner")
    expected = {"schema": OWNER_SCHEMA, "namespace": "nqc_miner_v1", "producer": "nqc-miner",
        "archive_id": owner.get("archive_id"), "observer_bridge_enabled": False, "remote_upload_enabled": False}
    if (owner != expected or str(uuid.UUID(owner["archive_id"])) != owner["archive_id"]
            or owner["observer_bridge_enabled"] is not False or owner["remote_upload_enabled"] is not False):
        raise ExportError("foreign archive owner")
    if {p.name for p in path.iterdir()} != {"owner.json", "writer.lock", "objects", "commits", "staging"}:
        raise ExportError("unexpected archive entry")
    for name in ("objects", "commits", "staging"):
        if not _check_path(path / name).is_dir():
            raise ExportError("archive directory missing")
    fd = os.open(path / "writer.lock", os.O_RDWR | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or os.read(fd, 128) != LOCK_MAGIC:
            raise ExportError("invalid archive lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ExportError("archive is busy") from error
        yield path
    finally:
        os.close(fd)


@contextmanager
def shared_source_lock(directory):
    """Honor the Rust writer's existing kernel lock without changing source bytes."""
    _check_path(directory / "writer.lock")
    fd = os.open(directory / "writer.lock", os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or os.read(fd, 128) != b"nqc-miner-kernel-lock-v1\n"):
            raise ExportError("source requires the persistent Miner kernel lock")
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ExportError("source writer is active; archive after a durable pause") from error
        yield
    finally:
        os.close(fd)


def inventory(state, *, control_only=False):
    """Only collection-owned, explicitly named regular files enter a snapshot."""
    state = _check_path(state)
    entries = {p.name for p in state.iterdir()}
    windows = sorted(name for name in entries if re.fullmatch(r"window-[0-9]{20}", name))
    if len(windows) > 10000 or entries - set(windows) - set(ROOT_FILES) - {"writer.lock"}:
        raise ExportError("unexpected collection entry")
    if not control_only and [int(name[7:]) for name in windows] != list(range(len(windows))):
        raise ExportError("noncontiguous collection windows")
    files = dict(ROOT_FILES)
    if not control_only:
        for name in windows:
            directory = _check_path(state / name)
            if not directory.is_dir() or {p.name for p in directory.iterdir()} - set(WINDOW_FILES) - {"writer.lock"}:
                raise ExportError("unexpected window entry")
            files.update({f"{name}/{file}": limit for file, limit in WINDOW_FILES.items()})
    for relative in files:
        _check_path(state / relative)
    return files, windows


def copied_files(state, destination, files, maximum_bytes):
    result, total = {}, 0
    for name, bound in sorted(files.items()):
        target = destination / name
        if target.parent != destination:
            target.parent.mkdir(mode=0o700, exist_ok=True)
        info = _copy_bounded(state / name, target, min(bound, maximum_bytes - total))
        total += info["bytes"]
        if total > maximum_bytes:
            raise ExportError("collection byte bound exceeded")
        result[name] = {"bytes": info["bytes"], "sha256": info["sha256"]}
    return result


def file_map(root):
    result = {}
    for path in sorted(root.rglob("*")):
        _check_path(path)
        if path.is_dir():
            continue
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ExportError("snapshot requires ordinary private files")
        relative = path.relative_to(root).as_posix()
        result[relative] = {"bytes": info.st_size, "sha256": _file_sha(path, MAX_SEGMENT)}
    return result


def read_object(root, digest):
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ExportError("invalid snapshot address")
    directory = _check_path(root / "objects" / digest)
    raw = _bounded_read(directory / "snapshot.json", 16 * 1024 * 1024)
    if _sha(raw) != digest:
        raise ExportError("snapshot manifest hash mismatch")
    manifest = _json(raw)
    if (not isinstance(manifest, dict) or manifest.get("schema") != SNAPSHOT_SCHEMA
            or manifest.get("status") not in {"verified_historical_snapshot", "quarantined"}
            or any(manifest.get(key) is not False for key in ("observer_bridge_enabled", "remote_upload_enabled",
                                                             "economic_certification", "authenticity_verified"))):
        raise ExportError("foreign snapshot schema")
    identity = _owner(manifest["owner"])
    if (identity["data_class"] != "historical" or identity["schema"] != "nqc-miner-owner-v2"
            or manifest["collection_key"] != _sha(packed([identity["namespace"],identity["data_class"],identity["run_id"]]))):
        raise ExportError("foreign collection identity")
    actual = file_map(directory)
    actual.pop("snapshot.json")
    if actual != manifest["files"]:
        raise ExportError("sealed snapshot bytes changed")
    return manifest


def receipts(root):
    archive_id = _json(_bounded_read(root / "owner.json", 65536))["archive_id"]
    entries = sorted((root / "commits").iterdir())
    if len(entries) > MAX_RECEIPTS:
        raise ExportError("archive receipt bound exceeded")
    result, previous, latest = [], "0" * 64, {}
    for index, path in enumerate(entries):
        if path.name != f"{index:020}.json":
            raise ExportError("receipt sequence gap or foreign file")
        value = _json(_bounded_read(_check_path(path), 65536))
        fields = {k: v for k, v in value.items() if k != "sha256"}
        if (set(value) != {"schema", "archive_id", "sequence", "previous_sha256", "collection_key", "snapshot_sha256",
                          "status", "published_at_utc", "sha256"}
                or fields["schema"] != RECEIPT_SCHEMA or fields["archive_id"] != archive_id
                or type(fields["sequence"]) is not int
                or fields["sequence"] != index or fields["previous_sha256"] != previous
                or _sha(packed(fields)) != value["sha256"]):
            raise ExportError("receipt integrity failure")
        manifest = read_object(root, value["snapshot_sha256"])
        if manifest["collection_key"] != value["collection_key"] or manifest["status"] != value["status"]:
            raise ExportError("receipt does not match its snapshot")
        key = manifest["collection_key"]
        if key in latest:
            transition(latest[key], manifest)
        latest[key] = manifest
        previous = value["sha256"]
        result.append(value)
    return result


def transition(previous, candidate):
    if previous["owner"] != candidate["owner"] or any(
            previous["source_files"][name] != candidate["source_files"][name]
            for name in ("owner.json", "config.json", "collector.json")):
        raise ExportError("collection identity was reused with different provenance")
    if previous["status"] == "quarantined":
        if candidate["status"] != "quarantined":
            raise ExportError("collection revocation is permanent; a new run is required")
        return
    if candidate["status"] == "quarantined":
        return
    for name, value in previous["source_files"].items():
        if candidate["source_files"].get(name) != value:
            raise ExportError("completed collection history changed or regressed")


def publish_receipt(root, manifest, snapshot_hash, prior):
    if len(prior) >= MAX_RECEIPTS:
        raise ExportError("archive requires reviewed rotation")
    fields = {"schema": RECEIPT_SCHEMA,
        "archive_id": _json(_bounded_read(root / "owner.json", 65536))["archive_id"], "sequence": len(prior),
        "previous_sha256": prior[-1]["sha256"] if prior else "0" * 64,
        "collection_key": manifest["collection_key"], "snapshot_sha256": snapshot_hash,
        "status": manifest["status"], "published_at_utc": datetime.now(timezone.utc).isoformat()}
    value = dict(fields, sha256=_sha(packed(fields)))
    # Both paths are inside the locked private archive. Hardlink publication cannot
    # replace another receipt. A killed publisher can leave only an unreferenced file.
    pending = root / "staging" / ("receipt-" + uuid.uuid4().hex)
    new_json(pending, value)
    os.link(pending, root / "commits" / f"{len(prior):020}.json", follow_symlinks=False)
    sync_dir(root / "commits")
    pending.unlink()
    sync_dir(root / "staging")
    return value


def archive_collection(state, archive, verifier, *, maximum_bytes=64*1024*1024, maximum_records=100000):
    if (type(maximum_bytes) is not int or not 1 <= maximum_bytes <= MAX_SEGMENT
            or type(maximum_records) is not int or not 1 <= maximum_records <= 1000000):
        raise ExportError("invalid collection resource bounds")
    state, verifier = _check_path(state), _check_path(verifier)
    archive = _check_path(archive)
    if state == archive or state in archive.parents or archive in state.parents:
        raise ExportError("source and archive must be separate directories")
    verifier_hash = _file_sha(verifier, MAX_SEGMENT)
    about = _binary_json(verifier, "about")
    if (about.get("name") != "nqc-miner" or about.get("namespace") != "nqc_miner_v1"
            or about.get("observer_bridge_enabled") is not False or about.get("signing_enabled") is not False):
        raise ExportError("foreign verifier")
    with archive_lock(archive) as root, ExitStack() as locks:
        locks.enter_context(shared_source_lock(state))
        prior = receipts(root)
        stage = root / "staging" / ("snapshot-" + uuid.uuid4().hex)
        stage.mkdir(mode=0o700)
        copied = stage / "source"
        copied.mkdir(mode=0o700)
        control_files, _ = inventory(state, control_only=True)
        fingerprints = copied_files(state, copied, control_files, maximum_bytes)
        owner = _owner(_json(_bounded_read(copied / "owner.json", 65536)))
        config = _json(_bounded_read(copied / "config.json", 1048576))
        marker = _json(_bounded_read(copied / "collector.json", 65536))
        if (owner["schema"] != "nqc-miner-owner-v2" or owner["data_class"] != "historical"
                or len(config["scopes"]) != 1 or marker != {"schema":"nqc-miner-collector-v1", "plan_sha256":owner["config_sha256"]}):
            raise ExportError("not a supported Miner historical collection")
        control = _binary_json(verifier, "verify-journal", "--state", str(copied))
        if control["owner"] != owner or control["integrity_verified"] is not True:
            raise ExportError("unverified control journal")
        revoked = bool(control["invalidated_from"])
        exports = []
        if revoked:
            records = [_json(line)["record"] for line in (copied / "events.jsonl").read_bytes().splitlines()]
            if any(r["kind"] != "invalidated" or r["chain_id"] != config["scopes"][0]["chain_id"]
                   or r["from_block"] != config["scopes"][0]["from_block"] for r in records):
                raise ExportError("unexpected collection revocation records")
            status = {"status": "quarantined", "control": control}
            files, windows = control_files, []
        else:
            files, windows = inventory(state)
            for name in windows:
                locks.enter_context(shared_source_lock(state / name))
            remaining = {name: bound for name, bound in files.items() if name not in control_files}
            used = sum(item["bytes"] for item in fingerprints.values())
            fingerprints.update(copied_files(state, copied, remaining, maximum_bytes-used))
            status = _binary_json(verifier, "verify-collector", "--config", str(copied / "config.json"), "--state", str(copied))
            if (status.get("incomplete_window") is not False or status.get("completed_windows") != len(windows)
                    or not windows or status.get("plan_sha256") != owner["config_sha256"]
                    or status.get("integrity_verified") is not True):
                raise ExportError("collection is empty or incomplete")
            (stage / "parquet").mkdir(mode=0o700)
            count = 0
            for name in windows:
                result = export_journal(copied / name, stage / "parquet" / name, verifier,
                    maximum_bytes=maximum_bytes, maximum_records=maximum_records-count)
                count += result["records"]
                exports.append({"window": name, "records": result["records"],
                    "manifest_sha256": _file_sha(stage / "parquet" / name / "manifest.json", MAX_SEGMENT)})
        # Verify the live source again without locking or writing it. A source that
        # grows, changes owner or gains an invalidation during the copy is rejected.
        final_files, final_windows = inventory(state, control_only=revoked)
        if final_files != files or (not revoked and final_windows != windows):
            raise ExportError("collection changed during archiving")
        for name, fingerprint in fingerprints.items():
            if _file_sha(state / name, files[name]) != fingerprint["sha256"]:
                raise ExportError("collection bytes changed during archiving")
        if _file_sha(verifier, MAX_SEGMENT) != verifier_hash:
            raise ExportError("verifier changed during archiving")
        key = _sha(packed([owner["namespace"], owner["data_class"], owner["run_id"]]))
        manifest = {"schema": SNAPSHOT_SCHEMA, "collection_key": key, "owner": owner,
            "status": "quarantined" if revoked else "verified_historical_snapshot",
            "source_files": fingerprints, "verification": status, "exports": exports,
            "verifier_sha256": verifier_hash, "verifier_build": about,
            "implementation_sha256": _sha(packed({name: _file_sha(Path(__file__).with_name(name), MAX_SEGMENT)
                for name in ("archive_collection.py", "export_parquet.py")})),
            "files": file_map(stage), "observer_bridge_enabled": False, "remote_upload_enabled": False,
            "economic_certification": False, "authenticity_verified": False}
        previous = next((r for r in reversed(prior) if r["collection_key"] == key), None)
        if previous:
            transition(read_object(root, previous["snapshot_sha256"]), manifest)
        manifest_bytes = packed(manifest) + b"\n"
        if len(manifest_bytes) > 16 * 1024 * 1024:
            raise ExportError("snapshot manifest exceeds its readable bound")
        _write_new(stage / "snapshot.json", manifest_bytes)
        snapshot_hash = _file_sha(stage / "snapshot.json", MAX_SEGMENT)
        for directory in sorted((p for p in stage.rglob("*") if p.is_dir()), key=lambda p:len(p.parts), reverse=True):
            sync_dir(directory)
        sync_dir(stage)
        target = root / "objects" / snapshot_hash
        if os.path.lexists(target):
            if read_object(root, snapshot_hash) != manifest:
                raise ExportError("existing snapshot does not match")
            shutil.rmtree(stage)  # Only this invocation's private, redundant staging copy.
        else:
            os.rename(stage, target)
            sync_dir(root / "objects")
        if previous and previous["snapshot_sha256"] == snapshot_hash:
            return {"receipt": previous, "idempotent": True}
        return {"receipt": publish_receipt(root, manifest, snapshot_hash, prior), "idempotent": False}


def resolve_collection(archive, run_id):
    key = _sha(packed(["nqc_miner_v1", "historical", run_id]))
    with archive_lock(archive) as root:
        history = receipts(root)
        latest = next((r for r in reversed(history) if r["collection_key"] == key), None)
        if latest is None:
            raise ExportError("collection has no published receipt")
        manifest = read_object(root, latest["snapshot_sha256"])
        if manifest["status"] == "quarantined":
            raise ExportError("collection is quarantined; historical objects are forensic only")
        return {"receipt": latest, "snapshot": manifest, "live_chain_revalidated": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--archive", type=Path, required=True)
    init.add_argument("--archive-id", required=True)
    capture = commands.add_parser("capture")
    capture.add_argument("--archive", type=Path, required=True)
    capture.add_argument("--state", type=Path, required=True)
    capture.add_argument("--verifier", type=Path, required=True)
    capture.add_argument("--maximum-bytes", type=int, default=64*1024*1024)
    capture.add_argument("--maximum-records", type=int, default=100000)
    resolve = commands.add_parser("resolve")
    resolve.add_argument("--archive", type=Path, required=True)
    resolve.add_argument("--run-id", required=True)
    args = parser.parse_args()
    try:
        if args.command == "init":
            init_archive(args.archive, args.archive_id)
            value = {"initialized": True, "archive_id": args.archive_id}
        elif args.command == "capture":
            value = archive_collection(args.state,args.archive,args.verifier,
                maximum_bytes=args.maximum_bytes,maximum_records=args.maximum_records)
        else:
            value = resolve_collection(args.archive,args.run_id)
        print(json.dumps(value,indent=2,sort_keys=True))
        return 0
    except (ExportError, OSError, ValueError, KeyError, TypeError) as error:
        # Data/endpoint strings from malformed input are never reflected by the CLI.
        print(json.dumps({"status":"rejected","error_type":type(error).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
