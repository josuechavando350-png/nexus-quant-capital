#!/usr/bin/env python3
"""Prepare a bounded, Rust-verified journal import for one Miner database UUID.

Offline only: never connects to a database or executes generated SQL. A fresh
Parquet export retains the verified source bytes. The completion manifest is
written last; a partial directory is not a usable import.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import uuid

from export_parquet import (
    ExportError, _bounded_read, _check_path, _envelopes, _file_sha, _json,
    _owner, _sha, _write_new, export_journal,
)
from archive_collection import new_json, sync_dir

SCHEMA = "nqc-miner-postgres-import-v1"
MAX_BYTES = 4 * 1024 * 1024
MAX_RECORDS = 10_000
OWNER_FIELDS = ("schema", "namespace", "producer", "run_id", "data_class",
                "config_sha256", "code_commit", "cargo_lock_sha256", "build_identity_sha256")


def packed(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def database_uuid(value):
    try:
        parsed = uuid.UUID(value)
    except (ValueError, TypeError, AttributeError) as error:
        raise ExportError("database identity must be a canonical nonzero UUID") from error
    if str(parsed) != value or not parsed.int:
        raise ExportError("database identity must be a canonical nonzero UUID")
    return value


def transaction_sql(request):
    """All variable bytes are hex, never SQL identifiers, strings or commands."""
    encoded = packed(request).hex()
    return ("-- Prepared offline; apply only to the reviewed dedicated Miner instance.\n"
            "BEGIN ISOLATION LEVEL READ COMMITTED;\n"
            "SET LOCAL search_path = pg_catalog;\n"
            "SET LOCAL lock_timeout = '5s';\n"
            "SET LOCAL statement_timeout = '60s';\n"
            "SET LOCAL synchronous_commit = on;\n"
            "SELECT nqc_miner_v1.import_verified_journal(\n"
            f"  convert_from(decode('{encoded}', 'hex'), 'UTF8')::jsonb);\n"
            "COMMIT;\n").encode()


def prepare_import(state: Path, output: Path, verifier: Path, database_id: str, *,
                   maximum_bytes=MAX_BYTES, maximum_records=MAX_RECORDS):
    database_uuid(database_id)
    if (type(maximum_bytes) is not int or type(maximum_records) is not int
            or not 1 <= maximum_bytes <= MAX_BYTES or not 1 <= maximum_records <= MAX_RECORDS):
        raise ExportError("invalid import resource bounds")
    state = _check_path(state)
    output = _check_path(output, must_exist=False)
    if output.exists() or state == output or state in output.parents or output in state.parents:
        raise ExportError("import output must be a new directory outside source state")
    identity = _owner(_json(_bounded_read(state / "owner.json", 65536)))
    if identity["schema"] != "nqc-miner-owner-v2":
        raise ExportError("PostgreSQL imports require a v2 build-bound owner")
    output.mkdir(mode=0o700)
    new_json(output / "import-owner.json", {"schema": SCHEMA, "namespace": "nqc_miner_v1",
        "producer": "nqc-miner", "database_id": database_id, "run_id": identity["run_id"],
        "observer_bridge_enabled": False, "database_applied": False})
    exported = export_journal(state, output / "verified-export", verifier,
                              maximum_bytes=maximum_bytes, maximum_records=maximum_records)
    source = output / "verified-export" / "source"
    original_owner = _bounded_read(source / "owner.json", 65536)
    original_config = _bounded_read(source / "config.json", 1048576)
    owner = _owner(_json(original_owner))
    if owner != identity:
        raise ExportError("source owner changed during import preparation")
    # Rust hashes the struct serialization, not owner.json whitespace/key order.
    canonical_owner = packed({key: owner[key] for key in OWNER_FIELDS})
    owner_hash = _sha(canonical_owner)
    rows = []
    previous = "0" * 64
    for raw, envelope in _envelopes(source / "events.jsonl", maximum_records):
        if envelope["owner_sha256"] != owner_hash or envelope["previous_sha256"] != previous:
            raise ExportError("copied journal no longer matches its verified owner/chain")
        previous = envelope["sha256"]
        rows.append({"sequence": envelope["sequence"], "previous_sha256": envelope["previous_sha256"],
            "envelope_sha256": envelope["sha256"], "raw_line_sha256": _sha(raw),
            "record_kind": envelope["record"]["kind"], "raw_line_hex": raw.hex()})
    if len(rows) != exported["records"] or previous != exported["last_envelope_sha256"]:
        raise ExportError("import count/tip no longer matches Rust-verified export")
    for entry in exported["source_files"]:
        if _file_sha(source / entry["file"], MAX_BYTES) != entry["sha256"]:
            raise ExportError("verified source bytes changed during preparation")
    journal_sha = next(entry["sha256"] for entry in exported["source_files"] if entry["file"] == "events.jsonl")
    request = {"schema": SCHEMA, "database_id": database_id, "owner": owner,
        "owner_sha256": owner_hash, "canonical_owner_hex": canonical_owner.hex(),
        "original_owner_hex": original_owner.hex(), "original_config_hex": original_config.hex(),
        "journal_sha256": journal_sha, "records": rows}
    _write_new(output / "request.json", packed(request) + b"\n")
    _write_new(output / "import.sql", transaction_sql(request))
    installer = Path(__file__).resolve().parents[1] / "infra" / "postgres_import.sql"
    new_json(output / "manifest.json", {"schema": SCHEMA, "namespace": "nqc_miner_v1",
        "producer": "nqc-miner", "database_id": database_id, "run_id": owner["run_id"],
        "data_class": owner["data_class"], "records": len(rows), "journal_sha256": journal_sha,
        "owner_sha256": owner_hash, "original_owner_sha256": _sha(original_owner),
        "original_config_sha256": _sha(original_config), "last_envelope_sha256": previous,
        "request_sha256": _file_sha(output / "request.json", 16 * MAX_BYTES),
        "sql_sha256": _file_sha(output / "import.sql", 32 * MAX_BYTES),
        "installer_sha256": _file_sha(installer, 1024 * 1024),
        "preparer_sha256": _file_sha(Path(__file__), 1024 * 1024),
        "verifier_sha256": exported["verifier_sha256"], "verifier_build": exported["verifier_build"],
        "contains_invalidation": any(row["record_kind"] == "invalidated" for row in rows),
        "integrity_verified": True, "authenticity_verified": False, "database_applied": False,
        "observer_bridge_enabled": False, "delivery_enabled": False, "complete": True})
    sync_dir(output)
    return _json((output / "manifest.json").read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("state", "output", "verifier"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--database-id", required=True)
    args = parser.parse_args()
    try:
        result = prepare_import(args.state, args.output, args.verifier, args.database_id)
    except (ExportError, OSError, ValueError) as error:
        parser.exit(1, f"Miner import preparation rejected: {error}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
