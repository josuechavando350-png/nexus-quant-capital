"""Fail-closed validator for the Omega Census static implementation assessment."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

EXPECTED_IDS = {1, 6, 7, 8, 10, 24, 25, 29, 32}
ALLOWED_STATUS = {"foundational_partial", "historical_partial", "not_evidenced"}
EXPECTED_SUMMARY = {"components_assessed": 9, "foundational_partial": 5,
                    "historical_partial": 2, "not_evidenced": 2}
BLOB = re.compile(r"^[0-9a-f]{40}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")
ALLOWED_PREFIXES = ("nqc-census/", "ci/nqc-census/", "ci/nqc-protocol-fork/", "omega/evidence/")
ALLOWED_OMEGA_FILES = {
    "omega/opportunity_vault.py",
    "omega/OPPORTUNITY_DOSSIER_CONTRACT.md",
    "omega/AUDIT_H4.md",
    "omega/liquidation_order_book.py",
    "omega/LIQUIDATION_ORDER_BOOK_CONTRACT.md",
    "omega/AUDIT_H5.md",
    "omega/causal_graph.py",
    "omega/CAUSAL_GRAPH_CONTRACT.md",
    "omega/AUDIT_H6.md",
}


def load_strict(path: Path) -> object:
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError(f"duplicate_json_key:{key}")
            out[key] = value
        return out
    def bad_constant(value):
        raise ValueError(f"nonfinite_json_number:{value}")
    return json.loads(path.read_bytes(), object_pairs_hook=pairs, parse_constant=bad_constant)


def verify_assessment(value: object) -> list[str]:
    errors = []
    if type(value) is not dict:
        return ["assessment_not_object"]
    if value.get("schema") != "nqc.omega.census-assessment.v1":
        errors.append("wrong_schema")
    if not COMMIT.fullmatch(str(value.get("as_of_commit", ""))):
        errors.append("invalid_as_of_commit")
    if value.get("assessment_scope") != "STATIC_SOURCE_AND_AUTHENTICATED_HISTORICAL_EVIDENCE_ONLY":
        errors.append("scope_changed")
    if value.get("census_closed") is not False or value.get("certified_components") != 0:
        errors.append("unsupported_certification_claim")
    components = value.get("components")
    if type(components) is not list:
        return sorted(set(errors + ["components_not_list"]))
    if len(components) != 9 or any(type(item) is not dict for item in components):
        return sorted(set(errors + ["component_shape_invalid"]))
    ids = [item.get("id") for item in components]
    if any(type(i) is not int for i in ids) or set(ids) != EXPECTED_IDS or len(ids) != len(set(ids)):
        errors.append("component_ids_invalid")
    statuses = []
    for item in components:
        status = item.get("status")
        statuses.append(status)
        if status not in ALLOWED_STATUS:
            errors.append("status_invalid")
        if item.get("component_certified") is not False:
            errors.append("component_certification_forbidden")
        if not isinstance(item.get("name"), str) or not item["name"].strip():
            errors.append("component_name_missing")
        if not isinstance(item.get("supported_claim"), str) or not item["supported_claim"].strip():
            errors.append("supported_claim_missing")
        missing = item.get("missing_for_omega")
        if type(missing) is not list or not missing or any(not isinstance(x, str) or not x.strip() for x in missing):
            errors.append("missing_requirements_invalid")
        evidence = item.get("evidence")
        if type(evidence) is not list:
            errors.append("evidence_not_list")
            continue
        if status != "not_evidenced" and not evidence:
            errors.append("partial_without_evidence")
        seen = set()
        for source in evidence:
            if type(source) is not dict or set(source) != {"path", "git_blob"}:
                errors.append("evidence_shape_invalid")
                continue
            path = source.get("path")
            blob = source.get("git_blob")
            valid_path = isinstance(path, str) and (
                path.startswith(ALLOWED_PREFIXES) or path in ALLOWED_OMEGA_FILES
            )
            if not valid_path or path.startswith("/") or ".." in Path(path).parts:
                errors.append("evidence_path_invalid")
            if not isinstance(blob, str) or not BLOB.fullmatch(blob):
                errors.append("evidence_blob_invalid")
            key = (path, blob)
            if key in seen:
                errors.append("duplicate_evidence")
            seen.add(key)
    counts = Counter(statuses)
    summary = value.get("summary")
    actual = {"components_assessed": len(components), **{s: counts[s] for s in sorted(ALLOWED_STATUS)}}
    expected = {"components_assessed": 9, **{s: EXPECTED_SUMMARY[s] for s in sorted(ALLOWED_STATUS)}}
    if summary != EXPECTED_SUMMARY or actual != expected:
        errors.append("summary_mismatch")
    return sorted(set(errors))


def main() -> int:
    path = Path(__file__).with_name("census_assessment.json")
    try:
        value = load_strict(path)
        errors = verify_assessment(value)
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        print(f"BLOCK:{exc}")
        return 2
    if errors:
        print("BLOCK:" + ",".join(errors))
        return 1
    print("ASSESSMENT PASS: 9/9 Census components mapped; 6 partial, 3 not evidenced, 0 certified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
