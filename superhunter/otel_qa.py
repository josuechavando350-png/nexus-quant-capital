"""Optional, offline OpenTelemetry SDK instrumentation for owned SuperHunter QA.

This adapter observes the EXISTING local QA gate. It does not run scanners,
export telemetry to the network, or reinterpret a failed QA run as PASS.
It is not an OpenTelemetry Collector deployment or a security finding.
"""
from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import time

from . import quality, otel_dependency_integrity as dependencies, otel_qa_schema as schema
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

SDK_VERSION = schema.SDK_VERSION
LEGACY_PROFILE = schema.LEGACY_PROFILE
PROFILE = schema.PROFILE
FILES = {"telemetry.json", "PROFILE.md"}
CHECKOUT = Path(__file__).resolve().parent.parent


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def readiness() -> dict:
    """Read local version metadata and exact files; never import the SDK here."""
    versions = {}
    for name in ("opentelemetry-api", "opentelemetry-sdk"):
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = None
    ready = all(x == SDK_VERSION for x in versions.values())
    identity, reason = None, None
    if ready:
        try:
            identity = dependencies.verify_dependencies()
        except (PackageNotFoundError, OSError, ValueError, KeyError, TypeError):
            ready, reason = False, 'PINNED_DEPENDENCY_INTEGRITY_FAILED'
    return {"status": "READY" if ready else "BLOCKED_DEPENDENCY",
            "packages": versions, "offline_only": True,
            "dependency_identity": identity, "reason": reason,
            "process_memory_integrity_proved": False}


def _outside_checkout(path: Path) -> bool:
    """Reject outputs inside code checkout, to keep its source digest stable."""
    return not path.resolve().is_relative_to(CHECKOUT)


def _spans_snapshot(exporter, expected_names: tuple[str, ...]) -> list[dict]:
    result = []
    for span in exporter.get_finished_spans():
        if span.name not in expected_names or span.start_time is None or span.end_time is None:
            raise ValueError("UNEXPECTED_SPAN")
        duration = span.end_time - span.start_time
        if duration < 0:
            raise ValueError("INVALID_SPAN_DURATION")
        result.append({"name": span.name, "duration_ns": duration})
    if sorted(x["name"] for x in result) != sorted(expected_names):
        raise ValueError("MISSING_SPAN")
    return sorted(result, key=lambda x: x["name"])


def profile_owned_qa(qa_out: Path, telemetry_out: Path) -> dict:
    """Run genuine local quality gate and verify it; store ONLY summary timings.

    The reported timing is observational, not proof that QA's producer is
    genuine. An in-memory exporter cannot leak traces to an OTLP endpoint.
    """
    if (qa_out.resolve() == telemetry_out.resolve() or qa_out.exists() or telemetry_out.exists() or
            not _outside_checkout(qa_out) or not _outside_checkout(telemetry_out) or
            not _outside_checkout(qa_out.parent) or not _outside_checkout(telemetry_out.parent)):
        raise ValueError("OUTPUT_UNSAFE_OR_EXISTS")
    admitted = readiness()
    if admitted["status"] != "READY":
        raise ValueError("OPENTELEMETRY_DEPENDENCY_MISSING_OR_DIFFERENT")
    # Import SDK only AFTER the installed-byte check. No global provider.
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.sampling import ALWAYS_ON
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = TracerProvider(sampler=ALWAYS_ON, resource=Resource({}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("superhunter.owned.qa", SDK_VERSION)
    began = time.monotonic_ns()
    status, error_type = "QA_FAILED", None
    qa_verified, tests_run, source_digest = False, 0, None
    expected = ["superhunter.qa.run"]
    try:
        with tracer.start_as_current_span("superhunter.qa.run", record_exception=False,
                                          set_status_on_exception=False):
            try:
                result = quality.run_check(qa_out)
                if type(result) is not dict or result.get("status") != "LOCAL_QA_PASS":
                    status = "QA_FAILED"
                else:
                    expected.append("superhunter.qa.verify")
                    try:
                        with tracer.start_as_current_span("superhunter.qa.verify", record_exception=False,
                                                          set_status_on_exception=False):
                            checked = quality.verify_bundle(qa_out)
                        if (type(checked) is dict and checked.get("status") == "LOCAL_QA_PASS" and
                                checked.get("source_digest") == result.get("source_digest") and
                                type(checked.get("tests_run")) is int and checked["tests_run"] > 0 and
                                checked["tests_run"] == result.get("tests_run")):
                            status, qa_verified = "QA_VERIFIED", True
                            source_digest = checked["source_digest"]
                            tests_run = checked["tests_run"]
                        else:
                            status = "QA_VERIFICATION_FAILED"
                    except (OSError, RuntimeError, ValueError, TypeError, KeyError) as exc:
                        status, error_type = "QA_VERIFICATION_FAILED", schema.error_label(exc)
            except (OSError, RuntimeError, ValueError, TypeError, KeyError, TimeoutError) as exc:
                error_type, status = schema.error_label(exc), "QA_FAILED"
    finally:
        elapsed = time.monotonic_ns() - began
        try:
            spans = _spans_snapshot(exporter, tuple(expected))
        finally:
            provider.shutdown()
    outcome = {"schema_version": 1, "profile": PROFILE, "status": status,
               "qa_passed": qa_verified, "qa_reverified_here": qa_verified,
               "tests_run": tests_run, "source_digest": source_digest,
               "elapsed_ns": elapsed, "spans": spans,
               "sdk_version": SDK_VERSION, "exporter": "in-memory-only",
               "network_export": False, "target_scanned": False,
               "vulnerability_confirmed": False, "error_type": error_type,
               "dependency_identity": admitted['dependency_identity'],
               "dependency_files_checked": True, "process_memory_integrity_proved": False}
    # Detect ordinary file changes across the run; an unchanged version string
    # alone cannot retain the byte-integrity claim.
    if dependencies.verify_dependencies() != admitted['dependency_identity']:
        raise ValueError('OPENTELEMETRY_DEPENDENCIES_CHANGED')
    schema.validate(outcome)
    review = _review(outcome)
    write_new_bundle(telemetry_out, {"telemetry.json": canonical(outcome),
                                     "PROFILE.md": review.encode("utf-8")})
    return verify_profile(telemetry_out, qa_out if qa_verified else None)


def _review(payload: dict) -> str:
    text = ("# SuperHunter owned QA — telemetry offline\n\n"
            f"QA verdict: {payload['status']}; reverified: {payload['qa_passed']}.\n"
            f"Tests: {payload['tests_run']}; elapsed_ns: {payload['elapsed_ns']}.\n"
            "OpenTelemetry SDK in-memory exporter; no network export. "
            "Telemetry is NOT independent authentication or an incident finding.\n")
    if payload['profile'] == PROFILE:
        text += ("Eight fixed wheel-derived dependencies checked before SDK import and after QA. "
                 "File integrity does not prove process-memory integrity or producer authenticity.\n")
    return text


def verify_profile(bundle: Path, qa_bundle: Path | None = None) -> dict:
    marker = strict_json(read_artifact(bundle, "COMPLETE.json"))
    if (type(marker) is not dict or set(marker) != {"schema_version", "sha256"} or
            marker["schema_version"] != 1 or type(marker["schema_version"]) is not int or
            type(marker["sha256"]) is not dict or set(marker["sha256"]) != FILES):
        raise ValueError("TELEMETRY_MANIFEST")
    files = {p: read_artifact(bundle, p) for p in FILES}
    if any(_sha(files[p]) != marker["sha256"][p] for p in FILES):
        raise ValueError("TELEMETRY_HASH_MISMATCH")
    payload = strict_json(files["telemetry.json"])
    schema.validate(payload)
    if payload["qa_passed"]:
        if qa_bundle is None:
            raise ValueError("TELEMETRY_REQUIRES_QA")
        fresh = quality.verify_bundle(qa_bundle)
        if (fresh["status"] != "LOCAL_QA_PASS" or fresh["source_digest"] != payload["source_digest"] or
                fresh["tests_run"] != payload["tests_run"]):
            raise ValueError("QA_EVIDENCE_DIVERGES")
    expected_review = _review(payload)
    if files["PROFILE.md"] != expected_review.encode("utf-8"):
        raise ValueError("TELEMETRY_REVIEW_MISMATCH")
    return payload


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description="Instrument owned QA offline using OpenTelemetry SDK")
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("doctor-otel-qa")
    make = sub.add_parser("profile-owned-qa")
    make.add_argument("--qa-out", required=True, type=Path)
    make.add_argument("--telemetry-out", required=True, type=Path)
    check = sub.add_parser("verify-owned-qa-profile")
    check.add_argument("--bundle", required=True, type=Path)
    check.add_argument("--qa-bundle", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.operation == "doctor-otel-qa":
            result = readiness()
            print(json.dumps(result, sort_keys=True))
            return 0 if result["status"] == "READY" else 2
        outcome = (profile_owned_qa(args.qa_out, args.telemetry_out)
                   if args.operation == "profile-owned-qa" else
                   verify_profile(args.bundle, args.qa_bundle))
        print(json.dumps({"status": outcome["status"], "qa_passed": outcome["qa_passed"],
                          "profile": outcome['profile'],
                          "dependency_files_checked": outcome.get('dependency_files_checked', False),
                          "tests_run": outcome["tests_run"], "network_export": False,
                          "vulnerability_confirmed": False}, sort_keys=True))
        return 0 if outcome["qa_passed"] else 1
    except (ValueError, OSError, TypeError, KeyError, RuntimeError, ImportError) as exc:
        print(json.dumps({"status": "OTEL_PROFILE_ERROR", "error_type": schema.error_label(exc),
                          "qa_passed": False, "vulnerability_confirmed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main(__import__('sys').argv[1:]))
