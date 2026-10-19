"""NQC049: READ-ONLY bridge from NQC048 GitHub receipt files to pinned NQC037.

No RPC, credentials, remote writes, auto-resume, or budget initialization.
Validation is relative to the pinned observations, NOT consensus or Nitro replay.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import importlib
import json
from pathlib import Path
import re
import sys

SOURCE_FILES = {
    "nqc-037-historical-state/src/intake.py": "c36d60ce83e73d246496bd0b72bc6cbe00d5893e",
    "nqc-037-historical-state/src/verify.py": "a417a48eaf4dbabc36ded493730e6ce97cecb4e8",
    "nqc-037-historical-state/vendor/nqc031/storage_proof.py": "24aba8c6454409b038868c7a3359172e905d7b6d",
    "nqc-037-historical-state/vendor/nqc031/util.py": "4e639cbebda0ddf5d612fdaf5007a28bd76117f0",
    "nqc-037-historical-state/inputs/TARGET.json": "7756f744f6b387481ab3a973bf74d6b8bbc2bade",
    "nqc-037-historical-state/inputs/parent-header.json": "d8576f0e73000d4ab993d69134ff0713ef70ca16",
    "nqc-037-historical-state/inputs/target-header.json": "8445e1f2744b7ab5888755613760da6c7897eeb6",
    "nqc-037-historical-state/inputs/l1-observations.json": "13214c6eb0f45cd4cea8e16fd149f7af6dca8545",
    "nqc-038-archive-access/triport_intake.py": "94fa75fc528caa04569ef87be58807eb9e8e7e8b",
    "nqc-038-archive-access/TRIPORT_PLAN.json": "e6ba1ce643ff3f9596870044c99aab8f3cbbb15b",
    "nqc-040-resumable-intake/session.py": "b6ede8fe84c892e99bae64537a2b0cae7460076d",
}
PLAN_DIGEST = "6148b4248555043ec3276f3887e008974643ccff64f755b8b6ed986f8537d2f7"
SPEC_DIGEST = "fe1bd67bfedd84372e76da84840cd0d52db1906a461a668684b3388a8c006034"
SCOPE = "nqc048:dryrun:4663:66744161:txindex1:fixed8"
SCHEMA = "nqc048-chunked-dryrun-v1"
CHUNK_BYTES = 256 * 1024
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 650_000
RECEIPTS = "nqc-048-durable-chunked-receipts/evidence"


class Blocked(ValueError):
    """Only local diagnostic codes; never include input, RPC payload or secrets."""


def require(condition, code):
    if not condition:
        raise Blocked(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def git_blob_sha(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def read_limited(path, maximum):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "MISSING_OR_UNSAFE_FILE")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    require(len(raw) <= maximum, "FILE_TOO_LARGE")
    return raw


def no_duplicates(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "DUPLICATE_JSON_KEY")
        value[key] = item
    return value


def reject_constant(_):
    raise Blocked("NON_JSON_CONSTANT")


def decode_json(raw):
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=no_duplicates,
                          parse_constant=reject_constant)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        if isinstance(exc, Blocked):
            raise
        raise Blocked("INVALID_JSON") from None


def canonical_json(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def source_bindings(experiments):
    for relative, expected in SOURCE_FILES.items():
        raw = read_limited(experiments / relative, MAX_JSON_BYTES)
        require(git_blob_sha(raw) == expected, "PINNED_SOURCE_MISMATCH")


def check_plan(spec):
    require(isinstance(spec, dict) and digest(canonical_json(spec)) == SPEC_DIGEST,
            "TRIPORT_SPEC_DIGEST_MISMATCH")
    plan = spec.get("logical_requests")
    require(isinstance(plan, list) and len(plan) == 8, "PLAN_LENGTH")
    require(digest(canonical_json(plan)) == PLAN_DIGEST, "PLAN_DIGEST_MISMATCH")
    require(spec.get("endpoint") == "https://triport.io/rpc/robinhood" and
            spec.get("maximum_requests") == 8, "ENDPOINT_OR_BUDGET_CHANGED")
    for i, row in enumerate(plan, 1):
        require(isinstance(row, dict) and isinstance(row.get("request"), dict) and
                type(row["request"].get("id")) is int and row["request"]["id"] == i,
                "PLAN_ORDER")
    return plan


def check_journal(journal, plan):
    root_keys = {"schema", "mode", "scope", "plan_sha256", "spec_sha256",
                 "max_requests", "commercial_admission", "entries"}
    require(isinstance(journal, dict) and set(journal) == root_keys, "JOURNAL_FIELDS")
    require(journal["schema"] == SCHEMA and journal["mode"] == "DRY_RUN" and
            journal["scope"] == SCOPE and journal["plan_sha256"] == PLAN_DIGEST and
            journal["spec_sha256"] == SPEC_DIGEST and
            type(journal["max_requests"]) is int and journal["max_requests"] == 8 and
            journal["commercial_admission"] is False, "JOURNAL_BINDING")
    rows = journal["entries"]
    require(isinstance(rows, list) and len(rows) <= 8, "JOURNAL_BUDGET")
    for index, row in enumerate(rows):
        require(isinstance(row, dict) and row.get("status") in
                ("RESERVED", "RECEIVED", "VERIFIED", "REJECTED"), "JOURNAL_STATUS")
        state = row["status"]
        expected = {"id", "purpose", "status", "receipt"} if state in ("RECEIVED", "VERIFIED") else {"id", "purpose", "status"}
        require(set(row) == expected and type(row["id"]) is int and row["id"] == index + 1 and
                row["purpose"] == plan[index]["purpose"], "JOURNAL_ORDER")
        require(index == len(rows) - 1 or state == "VERIFIED", "JOURNAL_PREFIX")
        if "receipt" in row:
            receipt = row["receipt"]
            require(isinstance(receipt, dict) and set(receipt) == {"sha256", "byte_length", "parts"},
                    "RECEIPT_FIELDS")
            require(isinstance(receipt["sha256"], str) and
                    re.fullmatch("[0-9a-f]{64}", receipt["sha256"]) and
                    type(receipt["byte_length"]) is int and 1 <= receipt["byte_length"] <= MAX_JSON_BYTES,
                    "RECEIPT_SCHEMA")
            parts = receipt["parts"]
            require(isinstance(parts, list) and 1 <= len(parts) <= 64, "RECEIPT_PART_COUNT")
            sizes = 0
            for i, part in enumerate(parts):
                require(isinstance(part, dict) and set(part) == {"b64_sha256", "bytes"} and
                        isinstance(part["b64_sha256"], str) and
                        re.fullmatch("[0-9a-f]{64}", part["b64_sha256"]) and
                        type(part["bytes"]) is int and 1 <= part["bytes"] <= CHUNK_BYTES,
                        "RECEIPT_PART_FIELDS")
                require(i == len(parts) - 1 or part["bytes"] == CHUNK_BYTES,
                        "RECEIPT_NONFINAL_PART")
                sizes += part["bytes"]
            require(sizes == receipt["byte_length"], "RECEIPT_TOTAL_BYTES")
    return rows


def load_receipt(evidence_dir, row):
    receipt = row["receipt"]
    length = 0
    chunks = []
    for index, entry in enumerate(receipt["parts"]):
        path = evidence_dir / "receipts" / f"{row['id']:02d}" / f"part-{index:03d}.b64"
        # Hard cap on encoded bytes; do not follow symlinks or read oversized payloads.
        encoded = read_limited(path, 4 * ((CHUNK_BYTES + 2) // 3))
        require(digest(encoded) == entry["b64_sha256"], "CHUNK_SHA_MISMATCH")
        try:
            decoded = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            raise Blocked("CHUNK_BASE64_INVALID") from None
        require(base64.b64encode(decoded) == encoded and len(decoded) == entry["bytes"],
                "CHUNK_ENCODING_OR_SIZE")
        length += len(decoded)
        chunks.append(decoded)
    raw = b"".join(chunks)
    require(length == receipt["byte_length"] and len(raw) <= MAX_JSON_BYTES and
            digest(raw) == receipt["sha256"], "RECEIPT_SHA_MISMATCH")
    response = decode_json(raw)
    require(isinstance(response, dict) and response.get("jsonrpc") == "2.0" and
            type(response.get("id")) is int and response["id"] == row["id"] and
            "result" in response and response["result"] is not None and "error" not in response,
            "RPC_ENVELOPE_INVALID")
    return response


def replay_snapshot(evidence_dir, journal, plan, validate_step):
    """Internal read-only reducer; tests inject a fake validator, LIVE cannot call it."""
    rows = check_journal(journal, plan)
    state = {}
    verified = 0
    for row in rows:
        if row["status"] in ("RESERVED", "REJECTED"):
            return {"status": "BLOCKED_PENDING_RESERVATION" if row["status"] == "RESERVED" else "BLOCKED_REJECTED_STEP",
                    "responses_validated": verified, "attempt_slots_reserved": len(rows), "commercial_admission": False}
        response = load_receipt(evidence_dir, row)
        operation = plan[row["id"] - 1]
        try:
            validate_step(operation, response, state)
        except Exception:
            # Ignore third-party verifier exception text. No trial of next step.
            return {"status": "BLOCKED_NQC037_VALIDATION", "responses_validated": verified,
                    "attempt_slots_reserved": len(rows), "commercial_admission": False}
        verified += 1
        if row["status"] == "RECEIVED":
            return {"status": "BLOCKED_RECEIVED_REVIEW_REQUIRED", "responses_validated": verified,
                    "attempt_slots_reserved": len(rows), "commercial_admission": False}
    return {"status": "OFFLINE_VERIFIED_PREFIX_ONLY_NO_DISPATCH", "responses_validated": verified,
            "attempt_slots_reserved": len(rows), "commercial_admission": False}


def audit_repository(repo_root):
    """Only supported entry: exact pinned NQC037 source, no network or writes."""
    experiments = Path(repo_root) / "migration" / "experiments"
    try:
        source_bindings(experiments)
        spec = decode_json(read_limited(experiments / "nqc-038-archive-access/TRIPORT_PLAN.json", MAX_JSON_BYTES))
        plan = check_plan(spec)
        evidence = experiments / RECEIPTS
        journal = decode_json(read_limited(evidence / "JOURNAL.json", MAX_MANIFEST_BYTES))
        check_journal(journal, plan)
    except (OSError, Blocked):
        return {"status": "BLOCKED_PIN_OR_INPUT", "commercial_admission": False}
    source_folder = str(experiments / "nqc-037-historical-state" / "src")
    sys.path.insert(0, source_folder)
    try:
        try:
            intake = importlib.import_module("intake")
        except (ImportError, ModuleNotFoundError):
            return {"status": "BLOCKED_VERIFIER_DEPENDENCY", "commercial_admission": False}
        # No stub verifier can substitute for the original binding in this entry.
        if Path(intake.__file__).resolve() != (Path(source_folder) / "intake.py").resolve():
            return {"status": "BLOCKED_VERIFIER_ORIGIN", "commercial_admission": False}
        if intake.plan() != plan:
            return {"status": "BLOCKED_PLAN_VERIFIER_MISMATCH", "commercial_admission": False}
        return replay_snapshot(evidence, journal, plan, intake.validate_step)
    except (Blocked, OSError):
        return {"status": "BLOCKED_INPUT_INTEGRITY", "commercial_admission": False}
    finally:
        sys.path.remove(source_folder)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True,
                        help="Read-only local checkout; no RPC or credential accepted")
    args = parser.parse_args()
    result = audit_repository(args.repo_root)
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "OFFLINE_VERIFIED_PREFIX_ONLY_NO_DISPATCH":
        sys.exit(2)
