"""Offline cross-bundle comparison for two completed OWNED Slither pair runs.

Both bundles are independently re-parsed by the existing source-bound verifier.
External SHA-256 anchors are REQUIRED; self-consistent hashes alone do not
authenticate scanner execution, producer identity, or host independence.

No tool execution, package installation, target enumeration or network IO.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys

from . import slither_control_pair as pair, static_review
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

SHA256 = re.compile(r"[0-9a-f]{64}\Z")
PROFILE = "owned-slither-pair-offline-replay-comparison-v1"
FILES = {"comparison.json", "REVIEW.md"}
ROOT = Path(__file__).resolve().parent.parent
# All these fields come from recomputation of source-bound Slither JSON.
# Exclude only raw report hashes and timestamps: those are not semantic output.
FIELDS = (
    "status", "raw_alert_count", "unique_alert_count", "duplicate_count",
    "source_bound_alerts", "unbound_alerts", "tool_impact_counts", "alerts",
    "source_sha256", "repository_declared", "scope_id_declared",
    "tool_declared", "detectors_declared", "normalization_complete",
    "input_kind", "scanner_execution_verified", "producer_authenticated",
    "repository_commit_verified", "scope_authorization_verified",
    "vulnerability_confirmed",
)


class ReplayComparisonError(ValueError):
    """Fixed diagnostic codes; never echo paths or raw scanner evidence."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _anchors(first: str, second: str) -> None:
    if (type(first) is not str or SHA256.fullmatch(first) is None or
            type(second) is not str or SHA256.fullmatch(second) is None):
        raise ReplayComparisonError("EXTERNAL_SHA256_ANCHORS_REQUIRED")


def _distinct(first: Path, second: Path) -> None:
    if (first.is_symlink() or second.is_symlink() or
            not first.is_dir() or not second.is_dir() or
            first.resolve() == second.resolve() or
            first.resolve().is_relative_to(second.resolve()) or
            second.resolve().is_relative_to(first.resolve())):
        raise ReplayComparisonError("TWO_DISTINCT_PAIR_DIRECTORIES_REQUIRED")


def _profile(bundle: Path, commit: str) -> dict:
    result = {}
    normalized = {}
    for name, expected_positive in (("positive", True), ("clean", False)):
        record = static_review.verify_report(bundle / name)
        pair.accept(record, expected_positive)
        if any(field not in record for field in FIELDS):
            raise ReplayComparisonError("MISSING_RECOMPUTED_PROFILE_FIELD")
        result[name] = {k: record[k] for k in FIELDS}
        normalized[name] = record
    pair.check_context(normalized["positive"], normalized["clean"], commit)
    return result


def compare(first: Path, second: Path, expected_first: str, expected_second: str) -> dict:
    """Re-check the two pairs and compare normalized observations exactly."""
    _anchors(expected_first, expected_second)
    _distinct(first, second)
    sha1 = digest(read_artifact(first, "COMPLETE.json"))
    sha2 = digest(read_artifact(second, "COMPLETE.json"))
    if sha1 != expected_first or sha2 != expected_second:
        raise ReplayComparisonError("EXTERNAL_ANCHOR_MISMATCH")
    first_summary = pair.verify_pair(first)
    second_summary = pair.verify_pair(second)
    if canonical(first_summary) != canonical(second_summary):
        raise ReplayComparisonError("PAIR_SUMMARY_DIVERGENCE")
    original = _profile(first, first_summary["declared_commit"])
    repeated = _profile(second, second_summary["declared_commit"])
    if canonical(original) != canonical(repeated):
        raise ReplayComparisonError("SLITHER_OBSERVATION_DIVERGENCE")
    return {
        "schema_version": 1,
        "profile": PROFILE,
        "status": "TWO_SLITHER_PAIRS_AGREE_UNAUTHENTICATED",
        "original_complete_sha256": sha1,
        "repeat_complete_sha256": sha2,
        "semantic_snapshot_sha256": digest(canonical(original)),
        "declared_commit": first_summary["declared_commit"],
        "scanner_version": first_summary["scanner_version"],
        "positive_cases": 1,
        "clean_cases": 1,
        "report_pairs_reevaluated": 2,
        "network_access_performed": False,
        "scanner_executed_here": False,
        "separate_host_proven": False,
        "producer_authenticated": False,
        "independent_execution_proven": False,
        "vulnerability_confirmed": False,
    }


def render(data: dict) -> bytes:
    return (
        "# SuperHunter — comparación offline de dos pares OWNED Slither\n\n"
        f"Estado: {data['status']}.\n"
        f"Commit declarado: {data['declared_commit']}; Slither: {data['scanner_version']}.\n"
        f"Resumen semántico SHA-256: {data['semantic_snapshot_sha256']}.\n"
        "Ambos paquetes se verificaron contra hashes SHA-256 recibidos por separado.\n"
        "Esto no autentica productores, entornos separados, ejecución original, "
        "vulnerabilidades o permisos de terceros.\n"
    ).encode("utf-8")


def create(first: Path, second: Path, expected_first: str, expected_second: str,
           output: Path) -> dict:
    _distinct(first, second)
    if (output.exists() or output.is_symlink() or
            output.resolve().is_relative_to(ROOT) or
            output.resolve().is_relative_to(first.resolve()) or
            output.resolve().is_relative_to(second.resolve()) or
            first.resolve().is_relative_to(output.resolve()) or
            second.resolve().is_relative_to(output.resolve())):
        raise ReplayComparisonError("UNSAFE_OUTPUT_LOCATION")
    result = compare(first, second, expected_first, expected_second)
    write_new_bundle(output, {"comparison.json": canonical(result),
                              "REVIEW.md": render(result)})
    return verify(output, first, second, expected_first, expected_second)


def verify(output: Path, first: Path, second: Path, expected_first: str,
           expected_second: str) -> dict:
    if output.is_symlink() or not output.is_dir():
        raise ReplayComparisonError("INVALID_COMPARISON_BUNDLE")
    manifest = strict_json(read_artifact(output, "COMPLETE.json"))
    if (set(manifest) != {"schema_version", "sha256"} or
            type(manifest["schema_version"]) is not int or
            manifest["schema_version"] != 1 or
            type(manifest["sha256"]) is not dict or
            set(manifest["sha256"]) != FILES or
            {p.name for p in output.iterdir()} != FILES | {"COMPLETE.json"}):
        raise ReplayComparisonError("INVALID_COMPARISON_MANIFEST")
    saved = {name: read_artifact(output, name) for name in FILES}
    if any(type(manifest["sha256"][name]) is not str or
           digest(saved[name]) != manifest["sha256"][name] for name in FILES):
        raise ReplayComparisonError("COMPARISON_HASH_MISMATCH")
    result = compare(first, second, expected_first, expected_second)
    if (saved["comparison.json"] != canonical(result) or
            saved["REVIEW.md"] != render(result)):
        raise ReplayComparisonError("COMPARISON_CONTENT_DIVERGENCE")
    return result


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(
        description="Compare OWNED Slither pair bundles offline with external SHA256 anchors")
    modes = parser.add_subparsers(dest="command", required=True)
    for cmd in ("compare-owned-slither-pairs", "verify-owned-slither-comparison"):
        p = modes.add_parser(cmd)
        p.add_argument("--first", required=True, type=Path)
        p.add_argument("--second", required=True, type=Path)
        p.add_argument("--expected-first-sha256", required=True)
        p.add_argument("--expected-second-sha256", required=True)
        p.add_argument("--bundle" if cmd.startswith("verify-") else "--out",
                       required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = (verify(args.bundle, args.first, args.second,
                         args.expected_first_sha256, args.expected_second_sha256)
                  if args.command == "verify-owned-slither-comparison" else
                  create(args.first, args.second, args.expected_first_sha256,
                         args.expected_second_sha256, args.out))
        print(json.dumps({
            "status": result["status"], "report_pairs_reevaluated": 2,
            "producer_authenticated": False, "vulnerability_confirmed": False,
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(json.dumps({
            "status": "SLITHER_COMPARISON_BLOCKED",
            "error_type": type(exc).__name__, "vulnerability_confirmed": False,
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
