"""Closed local QA telemetry contract. No SDK import, IO or export.

Only declared counters, fixed labels and pinned dependency identities are
accepted. This validates structure, not producer authenticity or confidentiality
of deliberately encoded values in otherwise valid counters or digests.
"""
from __future__ import annotations

from . import otel_dependency_integrity as dependencies
from .safe_io import canonical

SDK_VERSION = "1.42.1"
LEGACY_PROFILE = "owned-local-qa-opentelemetry-sdk-v1"
PROFILE = "owned-local-qa-opentelemetry-sdk-pinned-v2"
MAX_COUNTER = 2**63 - 1
ERROR_CLASSES = (TimeoutError, FileNotFoundError, PermissionError,
                 IsADirectoryError, NotADirectoryError, FileExistsError,
                 OSError, RuntimeError, ValueError, TypeError, KeyError, ImportError)
ERROR_NAMES = frozenset(cls.__name__ for cls in ERROR_CLASSES)


def error_label(exc: BaseException) -> str:
    """Never serialize an exception message or a caller-defined class name."""
    for cls in ERROR_CLASSES:
        if isinstance(exc, cls):
            return cls.__name__
    return "Exception"


def _counter(value: object) -> bool:
    return type(value) is int and 0 <= value <= MAX_COUNTER


def validate(payload: dict) -> None:
    """Reject extra fields and malformed or inconsistent persisted summaries."""
    keys = {"schema_version", "profile", "status", "qa_passed", "qa_reverified_here",
            "tests_run", "source_digest", "elapsed_ns", "spans", "sdk_version",
            "exporter", "network_export", "target_scanned", "vulnerability_confirmed", "error_type"}
    if type(payload) is dict and payload.get('profile') == PROFILE:
        keys |= {'dependency_identity', 'dependency_files_checked', 'process_memory_integrity_proved'}
        if (canonical(payload.get('dependency_identity')) != canonical(dependencies.expected_identity()) or
                payload.get('dependency_files_checked') is not True or
                payload.get('process_memory_integrity_proved') is not False):
            raise ValueError('TELEMETRY_DEPENDENCY_IDENTITY')
    if (type(payload) is not dict or set(payload) != keys or type(payload["schema_version"]) is not int or payload["schema_version"] != 1 or
            payload["profile"] not in (PROFILE, LEGACY_PROFILE) or payload["sdk_version"] != SDK_VERSION or
            payload["exporter"] != "in-memory-only" or payload["network_export"] is not False or
            payload["target_scanned"] is not False or payload["vulnerability_confirmed"] is not False or
            not _counter(payload["elapsed_ns"]) or
            type(payload["qa_passed"]) is not bool or type(payload["qa_reverified_here"]) is not bool or
            payload["qa_passed"] is not payload["qa_reverified_here"] or
            not _counter(payload["tests_run"]) or
            type(payload["spans"]) is not list or not 1 <= len(payload["spans"]) <= 2 or
            any(type(x) is not dict or set(x) != {"name", "duration_ns"} or
                x["name"] not in ("superhunter.qa.run", "superhunter.qa.verify") or
                not _counter(x["duration_ns"])
                for x in payload["spans"])):
        raise ValueError("TELEMETRY_SCHEMA")
    names = [x["name"] for x in payload["spans"]]
    if (names.count("superhunter.qa.run") != 1 or
            names.count("superhunter.qa.verify") != (
                1 if payload["status"] in ("QA_VERIFIED", "QA_VERIFICATION_FAILED") else 0)):
        raise ValueError("TELEMETRY_SPANS")
    if (payload["error_type"] is not None and
            (type(payload["error_type"]) is not str or
             payload["error_type"] not in ERROR_NAMES | {"Exception"})):
        raise ValueError("TELEMETRY_ERROR_LABEL")
    if payload["qa_passed"]:
        digest = payload["source_digest"]
        if (payload["status"] != "QA_VERIFIED" or payload["error_type"] is not None or
                type(digest) is not str or len(digest) != 64 or
                any(c not in "0123456789abcdef" for c in digest) or payload["tests_run"] < 1):
            raise ValueError("TELEMETRY_REQUIRES_QA")
    elif (payload["status"] not in ("QA_FAILED", "QA_VERIFICATION_FAILED") or
          payload["tests_run"] != 0 or payload["source_digest"] is not None):
        raise ValueError("INVALID_FAILURE_STATUS")
