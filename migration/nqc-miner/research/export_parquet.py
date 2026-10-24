#!/usr/bin/env python3
"""Export one verified Miner journal to new, immutable local Parquet batches.

Copies the source before verification; never writes locks or changes to original
state. Rust remains the authority for journal/ABI/hash-chain validation. The
result preserves every original JSONL byte, including newlines and invalidations.
This is an offline research utility, not the critical ingestion path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any, Iterator

import polars as pl

NAMESPACE = "nqc_miner_v1"
PRODUCER = "nqc-miner"
CLASSES = {"synthetic", "historical", "shadow"}
MAX_SEGMENT = 512 * 1024 * 1024
MAX_LINE = 1024 * 1024 + 1
MAX_RECORDS = 1_000_000
ZERO_HASH = "0" * 64


class ExportError(ValueError):
    """Invalid input, changed evidence, foreign ownership or unsafe output."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ExportError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _json(data: bytes) -> Any:
    try:
        return json.loads(data, object_pairs_hook=_unique_object,
                          parse_constant=lambda value: (_ for _ in ()).throw(ExportError(f"nonfinite JSON: {value}")))
    except (ValueError, UnicodeError) as error:
        raise ExportError(f"invalid JSON: {error}") from error


def _check_path(path: Path, *, must_exist: bool = True) -> Path:
    path = Path(os.path.abspath(path))
    for component in (path, *path.parents):
        try:
            info = component.lstat()
        except FileNotFoundError:
            if component == path and not must_exist:
                continue
            raise ExportError(f"missing path component: {component}")
        if stat.S_ISLNK(info.st_mode):
            raise ExportError("symlinks are not allowed in input, verifier or output paths")
    return path


def _bounded_read(path: Path, limit: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ExportError("input is not a bounded regular file")
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise ExportError("input grew beyond its bound")
        return data


def _write_new(path: Path, data: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _file_sha(path: Path, limit: int) -> str:
    hasher = hashlib.sha256()
    count = 0
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ExportError("digest input is not a regular file")
        while chunk := stream.read(64 * 1024):
            count += len(chunk)
            if count > limit:
                raise ExportError("digest input exceeds bound")
            hasher.update(chunk)
    return hasher.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    _write_new(path, (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())


def _copy_bounded(source: Path, destination: Path, limit: int) -> dict[str, Any]:
    """Copy exact bytes with descriptor-based size/change checks; no source mutation."""
    _check_path(source)
    fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    hasher = hashlib.sha256()
    total = 0
    with os.fdopen(fd, "rb") as src, destination.open("xb") as dst:
        before = os.fstat(src.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise ExportError("source is not a bounded regular file")
        while chunk := src.read(min(64 * 1024, limit - total + 1)):
            total += len(chunk)
            if total > limit:
                raise ExportError("source exceeds configured byte bound")
            hasher.update(chunk)
            dst.write(chunk)
        after = os.fstat(src.fileno())
        if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ExportError("source changed while being copied; retry after writer finishes")
        dst.flush()
        os.fsync(dst.fileno())
    return {"file": destination.name, "bytes": total, "sha256": hasher.hexdigest()}


def _binary_json(binary: Path, *args: str) -> dict[str, Any]:
    try:
        result = subprocess.run([str(binary), *args], capture_output=True, check=False, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ExportError(f"Rust verification could not run: {error}") from error
    if len(result.stdout) > 1024 * 1024 or len(result.stderr) > 1024 * 1024:
        raise ExportError("verifier output exceeded bound")
    if result.returncode:
        raise ExportError("Rust verifier rejected copied evidence: " + result.stderr.decode(errors="replace")[:2000])
    value = _json(result.stdout)
    if not isinstance(value, dict):
        raise ExportError("verifier output is not an object")
    return value


def _owner(value: Any) -> dict[str, Any]:
    expected = {"schema", "namespace", "producer", "run_id", "data_class", "config_sha256", "code_commit", "cargo_lock_sha256"}
    if isinstance(value, dict) and value.get("schema") == "nqc-miner-owner-v2":
        expected.add("build_identity_sha256")
    if not isinstance(value, dict) or set(value) != expected or any(not isinstance(item, str) for item in value.values()):
        raise ExportError("unexpected journal owner schema")
    if value["schema"] not in {"nqc-miner-owner-v1", "nqc-miner-owner-v2"} or value["namespace"] != NAMESPACE or value["producer"] != PRODUCER:
        raise ExportError("foreign namespace or producer")
    if value["data_class"] not in CLASSES or not re.fullmatch(r"[a-z0-9_-]{1,96}", value["run_id"]):
        raise ExportError("invalid run or evidence class; realized data is not an ingestion class")
    for key, length in (("config_sha256", 64), ("cargo_lock_sha256", 64), ("code_commit", 40)):
        if not isinstance(value[key], str) or not re.fullmatch(rf"[0-9a-f]{{{length}}}", value[key]):
            raise ExportError("invalid owner provenance")
    if "build_identity_sha256" in value and not re.fullmatch(r"[0-9a-f]{64}", value["build_identity_sha256"]):
        raise ExportError("invalid owner build identity")
    return value


def _envelopes(path: Path, maximum_records: int) -> Iterator[tuple[bytes, dict[str, Any]]]:
    with path.open("rb") as stream:
        count = 0
        while raw := stream.readline(MAX_LINE + 1):
            if len(raw) > MAX_LINE or not raw.endswith(b"\n"):
                raise ExportError("oversized or torn journal record")
            if count >= maximum_records:
                raise ExportError("record count bound exceeded")
            envelope = _json(raw)
            if not isinstance(envelope, dict) or set(envelope) != {"sequence", "owner_sha256", "previous_sha256", "record", "sha256"}:
                raise ExportError("unexpected journal envelope")
            if type(envelope["sequence"]) is not int or envelope["sequence"] != count:
                raise ExportError("noncontiguous journal sequence")
            yield raw, envelope
            count += 1


def _scan_states(path: Path, maximum_records: int) -> tuple[dict[int, int], dict[str, list[tuple[int, int]]], dict[str, tuple[int, int, int]]]:
    invalidations: dict[int, int] = {}
    chunks: dict[str, list[tuple[int, int]]] = {}
    scopes: dict[str, tuple[int, int, int]] = {}
    for _, envelope in _envelopes(path, maximum_records):
        record = envelope["record"]
        kind = record["kind"]
        if kind == "invalidated":
            chain = record["chain_id"]
            invalidations[chain] = min(record["from_block"], invalidations.get(chain, record["from_block"]))
        elif kind == "chunk_completed":
            chunks.setdefault(record["scope_id"], []).append((record["from_block"], record["to_block"]))
        elif kind == "scope_completed":
            scopes[record["scope_id"]] = (record["chain_id"], record["from_block"], record["to_block"])
        elif kind != "observed":
            raise ExportError("unsupported record kind; exporter version must be upgraded explicitly")
    return invalidations, chunks, scopes


PARQUET_SCHEMA = {
    "namespace": pl.String, "producer": pl.String, "run_id": pl.String, "data_class": pl.String,
    "code_commit": pl.String, "config_sha256": pl.String, "cargo_lock_sha256": pl.String,
    "source_journal_sha256": pl.String, "owner_sha256": pl.String, "sequence": pl.UInt64,
    "previous_sha256": pl.String, "envelope_sha256": pl.String, "record_kind": pl.String,
    "scope_id": pl.String, "chain_id": pl.UInt64, "block_number": pl.UInt64,
    "block_hash": pl.String, "transaction_hash": pl.String, "log_index": pl.UInt32,
    "event_state": pl.String, "raw_line_sha256": pl.String, "raw_line": pl.Binary,
}


def export_journal(state: Path, output: Path, verifier: Path, *, batch_rows: int = 5000,
                   maximum_bytes: int = 64 * 1024 * 1024, maximum_records: int = 100_000) -> dict[str, Any]:
    """Create a new export; refuse existing paths and any foreign or mixed evidence."""
    if any(type(value) is not int for value in (batch_rows, maximum_bytes, maximum_records)) or not (
            1 <= batch_rows <= 10_000 and 1 <= maximum_bytes <= MAX_SEGMENT and 1 <= maximum_records <= MAX_RECORDS):
        raise ExportError("invalid export resource bounds")
    state = _check_path(state)
    output = _check_path(output, must_exist=False)
    verifier = _check_path(verifier)
    if not state.is_dir() or not verifier.is_file() or not os.access(verifier, os.X_OK):
        raise ExportError("state must be a directory and verifier an executable regular file")
    if output.exists() or state == output or state in output.parents or output in state.parents:
        raise ExportError("output must be a new directory outside the source state")
    owner = _owner(_json(_bounded_read(state / "owner.json", 64 * 1024)))
    config = _json(_bounded_read(state / "config.json", 1024 * 1024))
    if not isinstance(config, dict) or any(config.get(k) != owner[k] for k in ("namespace", "producer", "run_id", "data_class", "code_commit", "cargo_lock_sha256")):
        raise ExportError("configuration has mixed run, class or namespace")
    if config.get("build_identity_sha256") != owner.get("build_identity_sha256"):
        raise ExportError("configuration has mixed build identity")
    verifier_hash = _file_sha(verifier, 512 * 1024 * 1024)
    about = _binary_json(verifier, "about")
    if about.get("name") != PRODUCER or about.get("namespace") != NAMESPACE or about.get("signing_enabled") is not False or about.get("observer_bridge_enabled") is not False:
        raise ExportError("verifier is not the isolated Miner binary")

    # Atomic creation and x-mode files make accidental overwrite impossible.
    # On failure the owned directory remains incomplete, without a manifest.json.
    output.mkdir(mode=0o700)
    _write_json(output / "export-owner.json", {"schema": "nqc-miner-parquet-export-owner-v1", "namespace": NAMESPACE,
                                               "producer": PRODUCER, "run_id": owner["run_id"], "data_class": owner["data_class"]})
    copied = output / "source"
    copied.mkdir(mode=0o700)
    sources = []
    for name, limit in (("owner.json", 64 * 1024), ("config.json", 1024 * 1024), ("events.jsonl", maximum_bytes)):
        sources.append(_copy_bounded(state / name, copied / name, limit))
    copied_owner = _owner(_json(_bounded_read(copied / "owner.json", 64 * 1024)))
    if copied_owner != owner:
        raise ExportError("source owner changed during snapshot")
    summary = _binary_json(verifier, "verify-journal", "--state", str(copied))
    if summary.get("owner") != owner or summary.get("integrity_verified") is not True:
        raise ExportError("Rust verifier did not certify integrity for this exact owner")
    if summary.get("authenticity_verified") is not False:
        raise ExportError("unexpected verifier authenticity contract; review before upgrading exporter")
    if type(summary.get("records")) is not int or not 0 <= summary["records"] <= maximum_records:
        raise ExportError("verified record count exceeds bound")
    # The verifier's ephemeral lock must be gone; copied data bytes must be unchanged.
    for source in sources:
        if _file_sha(copied / source["file"], MAX_SEGMENT) != source["sha256"]:
            raise ExportError("copied evidence changed during verification")
    _write_json(output / "verification.json", summary)
    journal_hash = next(item["sha256"] for item in sources if item["file"] == "events.jsonl")
    states = _scan_states(copied / "events.jsonl", maximum_records)
    invalidations, chunks, scopes = states
    rows: list[dict[str, Any]] = []
    batches: list[dict[str, Any]] = []
    total_rows = 0
    previous = ZERO_HASH
    expected_owner_digest: str | None = None
    batch_raw_bytes = 0

    def flush() -> None:
        nonlocal batch_raw_bytes
        if not rows:
            return
        filename = f"part-{len(batches):05d}.parquet"
        destination = output / filename
        frame = pl.DataFrame(rows, schema=PARQUET_SCHEMA, strict=True)
        with destination.open("xb") as stream:
            frame.write_parquet(stream, compression="zstd", statistics=True, row_group_size=batch_rows)
            stream.flush()
            os.fsync(stream.fileno())
        # Independent format roundtrip verifies lossless binary preservation and row order.
        recovered = pl.read_parquet(destination)
        if recovered.schema != frame.schema or recovered.to_dicts() != rows:
            raise ExportError("Parquet roundtrip did not preserve exact rows")
        original = b"".join(row["raw_line"] for row in rows)
        batches.append({"file": filename, "rows": len(rows), "first_sequence": rows[0]["sequence"],
                        "last_sequence": rows[-1]["sequence"], "raw_bytes_sha256": _sha(original),
                        "parquet_sha256": _file_sha(destination, MAX_SEGMENT),
                        "bytes": destination.stat().st_size})
        rows.clear()
        batch_raw_bytes = 0

    for raw, envelope in _envelopes(copied / "events.jsonl", maximum_records):
        if envelope["previous_sha256"] != previous:
            raise ExportError("copied chain changed after Rust verification")
        previous = envelope["sha256"]
        if expected_owner_digest is None:
            expected_owner_digest = envelope["owner_sha256"]
        if envelope["owner_sha256"] != expected_owner_digest:
            raise ExportError("mixed journal owners")
        record = envelope["record"]
        kind = record["kind"]
        log = record.get("log", {})
        chain = log.get("chain_id", record.get("chain_id"))
        block = log.get("block_number")
        scope_id = record.get("scope_id")
        event_state = None
        if kind == "observed":
            if chain in invalidations and block >= invalidations[chain]:
                event_state = "invalidated"
            elif scope_id in scopes and (chain not in invalidations or scopes[scope_id][2] < invalidations[chain]):
                event_state = "scope_completed"
            elif any(first <= block <= last for first, last in chunks.get(scope_id, [])):
                event_state = "chunk_committed"
            else:
                event_state = "provisional"
        row = {k: owner[k] for k in ("namespace", "producer", "run_id", "data_class", "code_commit", "config_sha256", "cargo_lock_sha256")}
        row.update(source_journal_sha256=journal_hash, owner_sha256=envelope["owner_sha256"], sequence=envelope["sequence"],
                   previous_sha256=envelope["previous_sha256"], envelope_sha256=envelope["sha256"], record_kind=kind,
                   scope_id=scope_id, chain_id=chain, block_number=block, block_hash=log.get("block_hash"),
                   transaction_hash=log.get("transaction_hash"), log_index=log.get("log_index"), event_state=event_state,
                   raw_line_sha256=_sha(raw), raw_line=raw)
        # Bound raw payload memory independently of row count.
        if rows and batch_raw_bytes + len(raw) > 16 * 1024 * 1024:
            flush()
        rows.append(row)
        batch_raw_bytes += len(raw)
        total_rows += 1
        if len(rows) >= batch_rows:
            flush()
    flush()
    if total_rows != summary["records"] or previous != summary["last_sha256"]:
        raise ExportError("export counts or final hash disagree with verified journal")
    for source in sources:
        if _file_sha(copied / source["file"], MAX_SEGMENT) != source["sha256"]:
            raise ExportError("copied evidence changed during export")
    if _file_sha(verifier, 512 * 1024 * 1024) != verifier_hash:
        raise ExportError("verifier executable changed during export")
    manifest = {"schema": "nqc-miner-parquet-export-v1", "namespace": NAMESPACE, "producer": PRODUCER,
                "run_id": owner["run_id"], "data_class": owner["data_class"], "owner": owner,
                "source_files": sources, "records": total_rows, "last_envelope_sha256": previous,
                "batches": batches, "polars_version": pl.__version__, "verifier_sha256": verifier_hash,
                "verifier_build": about, "integrity_verified": True, "authenticity_verified": False,
                "uploaded": False, "complete": True}
    _write_json(output / "manifest.json", manifest)  # completion marker is always last
    fd = os.open(output, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verifier", type=Path, required=True)
    parser.add_argument("--batch-rows", type=int, default=5000)
    parser.add_argument("--maximum-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--maximum-records", type=int, default=100_000)
    args = parser.parse_args()
    try:
        manifest = export_journal(args.state, args.output, args.verifier, batch_rows=args.batch_rows,
                                  maximum_bytes=args.maximum_bytes, maximum_records=args.maximum_records)
    except (ExportError, OSError, subprocess.SubprocessError, pl.exceptions.PolarsError) as error:
        parser.exit(1, f"nqc-miner export rejected: {error}\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
