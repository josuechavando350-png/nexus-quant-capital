#!/usr/bin/env python3
"""Build a portable source/claim index from four unmodified local JSON modules.

No network, wallet, signing, source rewriting, or duplicated raw snapshots.
All original data remains resolvable through module SHA256 and JSON Pointer.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys


MODULES = (
    ("root", "evidence/root_sources.json"),
    ("sponsor", "evidence/sponsor_sources.json"),
    ("accounting", "evidence/sources_ledger.json"),
    ("temporal", "evidence/temporal_sources.json"),
)

EXTRA_SECTIONS = {
    "version_resolution": "version_resolution",
    "retrieval_failures": "retrieval_failure",
    "model_evidence": "local_model_evidence",
    "test_evidence": "local_test_evidence",
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def escape(token):
    return str(token).replace("~", "~0").replace("/", "~1")


def walk(value, pointer=""):
    yield pointer, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, pointer + "/" + escape(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, pointer + "/" + str(index))


def first(record, fields):
    for field in fields:
        if field in record and record[field] is not None:
            return record[field], field
    return None, None


def selected_fields(record, predicate):
    return {k: v for k, v in record.items() if predicate(k)}


def leaf_fields(record, predicate):
    return {p: v for p, v in walk(record) if p and not isinstance(v, (dict, list)) and predicate(p.rsplit("/", 1)[-1], v)}


def make_entry(module, relative_path, module_sha, pointer, record, kind, context):
    original_id = record.get("id")
    index_key = module + "#" + pointer
    entry_id = original_id if original_id is not None else "IDX:" + index_key
    assertion, assertion_field = first(record, ("claim", "assertion", "verified", "supports", "aseveracion"))
    unit, unit_field = first(record, ("unit", "units", "unidad"))
    method, method_field = first(record, ("method", "retrieval_method", "metodo"))
    dates = selected_fields(record, lambda k: bool(re.search(r"utc|date|timestamp|time|fecha|hora", k, re.I)))
    nested_dates = leaf_fields(record, lambda k, v: bool(re.search(r"utc|date|timestamp|fecha|hora", k, re.I)))
    status_fields = selected_fields(record, lambda k: bool(re.search(r"classification|evidence_class|access_status|source_type|version_status|reported_not_reproduced|status|estado", k, re.I)))
    rejections = selected_fields(record, lambda k: bool(re.search(r"rejection|failure|error|absence|absent|http_status|tool_result|retry|access_status", k, re.I)))
    missing = selected_fields(record, lambda k: bool(re.search(r"missing|unknown|blockers|would_change_conclusion|unavailable", k, re.I)))
    urls = leaf_fields(record, lambda k, v: isinstance(v, str) and v.startswith(("https://", "http://")))
    paths = selected_fields(record, lambda k: bool(re.search(r"path|pointer", k, re.I)))
    hashes = leaf_fields(record, lambda k, v: (bool(re.search(r"sha|hash|commit", k, re.I)) or k == "ref")
                        and (v is None or isinstance(v, str) and bool(re.fullmatch(r"(?:0x)?(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", v))))
    source_ids = record.get("source_ids", [])
    if source_ids is None:
        source_ids = []
    if not isinstance(source_ids, list):
        source_ids = [source_ids]

    classification_text = " ".join(str(v) for v in status_fields.values()).upper()
    if kind in ("local_model_evidence", "local_test_evidence") or "HIPOTESIS" in classification_text or "HYPOTHETICAL" in classification_text:
        evidence_scope = "LOCAL_MODEL_OR_TEST"
    elif kind == "retrieval_failure":
        evidence_scope = "RETRIEVAL_RESULT"
    elif kind == "version_resolution":
        evidence_scope = "VERSION_REFERENCE"
    elif "REPRODUCIDO_LOCALMENTE" in classification_text:
        evidence_scope = "LOCAL_CALCULATION_OR_VERIFICATION"
    elif "DOCUMENTAL" in classification_text or record.get("source_type") == "web_documentation":
        evidence_scope = "DOCUMENTATION_TEXT"
    elif record.get("source_type") == "pinned_repository_file" or "ARCHIVO_GITHUB" in classification_text or record.get("git_blob_sha"):
        evidence_scope = "PINNED_FILE_CONTENT"
    elif isinstance(method, str) and "Lectura de la fuente indicada" in method:
        evidence_scope = "SOURCE_REVIEW_OR_REPORTED_RESULT"
    else:
        evidence_scope = "NOT_NORMALIZED_FROM_DECLARED_FIELDS"

    has_nonnull_hash = any(v is not None for v in hashes.values())
    unknown_fields = []
    for name, missing_value in (
        ("assertion", assertion is None), ("unit", unit is None), ("method", method is None),
        ("source_or_event_date", not any(v is not None for v in dates.values()) and not any(v is not None for v in nested_dates.values())),
        ("source_hash", not has_nonnull_hash),
        ("source_status", not status_fields),
        ("explicit_missing_evidence", not missing),
        ("source_url_or_source_path", not urls and not paths),
    ):
        if missing_value:
            unknown_fields.append(name)

    return {
        "id": entry_id,
        "original_id": original_id,
        "index_key": index_key,
        "record_kind": kind,
        "module": module,
        "assertion": assertion,
        "assertion_original_field": assertion_field,
        "title": record.get("title"),
        "status": {"declared_fields": status_fields, "evidence_scope": evidence_scope,
                   "real_world_or_nqc_economic_verification": "NOT_ESTABLISHED_BY_THIS_INDEX"},
        "locator": {"source_urls": urls, "source_paths_or_pointers": paths,
                    "original_record_locator": relative_path + "#" + pointer},
        "sha": {"source_reported_hash_fields": hashes,
                "original_record_canonical_sha256": digest(record),
                "original_module_file_sha256": module_sha,
                "boundary": "File, commit, transaction and record hashes retain their declared types. None is automatically a state proof or economic certification."},
        "date": {"declared_fields": dates, "nested_declared_date_fields": nested_dates,
                 "module_context": context,
                 "boundary": "Capture, recording, publication, event date and window bounds are not interchangeable; no missing date is synthesized."},
        "unit": unit,
        "unit_original_field": unit_field,
        "method": method,
        "method_original_field": method_field,
        "chain": selected_fields(record, lambda k: k in ("chain", "chain_id", "network", "red")),
        "block": selected_fields(record, lambda k: k in ("block", "block_number", "block_hash", "transaction_index")),
        "rejection_or_absence": {"declared_fields": rejections,
                                 "boundary": "An omitted or null rejection field is not evidence that access succeeded or that no rejection occurred."},
        "missing_evidence": missing,
        "declared_limitations": selected_fields(record, lambda k: bool(re.search(r"limit|boundary|correction|capture_precision|capture_time_quality|capture_recorded_precision", k, re.I))),
        "source_id_references": source_ids,
        "normalization_fields_not_provided": unknown_fields,
        "original_record": {"module_path": relative_path, "json_pointer": pointer,
                            "canonical_sha256": digest(record), "data_retention": "All fields remain in the unmodified module; no raw snapshot is duplicated here."},
    }


def build(root):
    modules = []
    entries = []
    read_hashes = {}
    original_occurrences = []
    for module, relative_path in MODULES:
        path = root / relative_path
        raw = path.read_bytes()
        file_sha = hashlib.sha256(raw).hexdigest()
        read_hashes[relative_path] = file_sha
        obj = json.loads(raw)
        if not isinstance(obj, (dict, list)):
            raise ValueError("Unexpected module root: " + relative_path)
        context = selected_fields(obj, lambda k: bool(re.search(r"utc|date|time|capture|scope|unknown|hash|audit_revision", k, re.I))) if isinstance(obj, dict) else {}
        context_refs = {k: {"value": v, "json_pointer": "/" + escape(k)} for k, v in context.items() if not isinstance(v, list)}
        collected = {}
        for pointer, value in walk(obj):
            if isinstance(value, dict) and value.get("id") is not None:
                kind = "claim" if pointer.startswith("/claims/") or "claim" in value else "source" if pointer.startswith("/sources/") else "identified_record"
                collected[pointer] = (value, kind)
                original_occurrences.append((value["id"], module, pointer))
        if isinstance(obj, dict):
            for name, kind in EXTRA_SECTIONS.items():
                value = obj.get(name)
                if isinstance(value, dict):
                    collected.setdefault("/" + escape(name), (value, kind))
                elif isinstance(value, list):
                    for index, row in enumerate(value):
                        if isinstance(row, dict):
                            collected.setdefault("/" + escape(name) + "/" + str(index), (row, kind))
        for pointer, (record, kind) in sorted(collected.items()):
            entries.append(make_entry(module, relative_path, file_sha, pointer, record, kind, context_refs))
        modules.append({
            "module": module, "path": relative_path, "sha256": file_sha, "size_bytes": len(raw),
            "record_count_in_index": len(collected),
            "root_structure": list(obj.keys()) if isinstance(obj, dict) else {"list_length": len(obj)},
            "module_capture_and_scope_context": context_refs,
            "original_module": {"path": relative_path, "sha256": file_sha, "json_pointer": "",
                                "retention": "Full original module remains unmodified. Metadata and unindexed nested data are preserved at this location."},
        })

    id_locations = defaultdict(list)
    for ident, module, pointer in original_occurrences:
        id_locations[str(ident)].append({"module": module, "json_pointer": pointer})
    missing_counts = Counter(field for e in entries for field in e["normalization_fields_not_provided"])
    unresolved = []
    for entry in entries:
        for source_id in entry["source_id_references"]:
            if str(source_id) not in id_locations:
                unresolved.append({"index_key": entry["index_key"], "source_id": source_id})

    for relative_path, before in read_hashes.items():
        if hashlib.sha256((root / relative_path).read_bytes()).hexdigest() != before:
            raise ValueError("Module changed while building index: " + relative_path)
    if len({e["index_key"] for e in entries}) != len(entries):
        raise ValueError("Nonunique index key")

    return {
        "schema_version": "1.0",
        "title": "NQC Directiva 002 - Unified source, claim and evidence ledger",
        "generated_by": "build_source_ledger.py",
        "network_calls": 0,
        "normalization_rules": [
            "Original IDs are retained verbatim. ID-less evidence objects receive IDX:module#pointer identifiers that do not replace an original source ID.",
            "Every record resolves to an unmodified module and JSON Pointer; SHA256 covers both the original module bytes and a sorted-key UTF-8 JSON form of the individual record.",
            "Source/claim status comes from declared fields. Documentary verification, saved observations, local calculations and synthetic tests are not promoted to real NQC execution or income.",
            "Null or absent source dates, blocks, units, methods and evidence remain unknown. A module capture timestamp is context, not a substitute for an event timestamp.",
            "Intervals and explicitly limited clock precision are preserved as reported; no point capture time is fabricated.",
            "All original metadata, retrieval failures, limitations and model details remain available in the four referenced modules. Raw snapshots are not copied into this index.",
            "Missing normalized fields count absence of an explicit field, not an economic failure. Many source-only references have no applicable numerical unit or assertion.",
        ],
        "provenance_modules": modules,
        "summary": {
            "index_records": len(entries),
            "original_id_occurrences": len(original_occurrences),
            "unique_original_ids": len(id_locations),
            "generated_idless_record_ids": sum(e["original_id"] is None for e in entries),
            "unique_index_keys": len({e["index_key"] for e in entries}),
            "unique_entry_ids_including_generated": len({str(e["id"]) for e in entries}),
            "duplicate_original_ids": {k: v for k, v in id_locations.items() if len(v) > 1},
            "records_by_module": dict(Counter(e["module"] for e in entries)),
            "records_by_kind": dict(Counter(e["record_kind"] for e in entries)),
            "records_by_evidence_scope": dict(Counter(e["status"]["evidence_scope"] for e in entries)),
            "normalization_fields_not_provided_counts": dict(sorted(missing_counts.items())),
            "unresolved_source_id_references": unresolved,
            "real_nqc_operations_certified_by_index": 0,
            "real_nqc_operations_population_inferred": False,
        },
        "original_id_index": dict(sorted(id_locations.items())),
        "entries": entries,
    }


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=here)
    parser.add_argument("--output", type=Path, default=here / "SOURCE_LEDGER.json")
    args = parser.parse_args()
    ledger = build(args.root)
    args.output.write_text(json.dumps(ledger, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(ledger["summary"], ensure_ascii=False, indent=2))
    print("SOURCE_LEDGER_SHA256=" + hashlib.sha256(args.output.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, FileNotFoundError, json.JSONDecodeError) as exc:
        print("SOURCE_LEDGER_BUILD_FAILED: " + str(exc), file=sys.stderr)
        sys.exit(1)
