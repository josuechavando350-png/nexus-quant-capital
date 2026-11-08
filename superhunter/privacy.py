"""Deterministic redaction for local review outputs, never credential validation.

Finite text rules are a safety aid, not proof that a document contains no secrets.
Original source evidence is read-only; exported text is explicitly a derivative.
No network, LLM, secret database, shell, or arbitrary plug-in is used.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import re
from typing import Any

from .safe_io import MAX_BYTES, canonical

POLICY_ID = "superhunter-local-redaction-v1"
REPLACEMENT = "[REDACTED]"
MAX_NODES = 50_000
MAX_DEPTH = 40
_NAME = (r"api[_ -]?key|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|"
         r"private[_ -]?key|secret[_ -]?key|password|passwd|secret|token|"
         r"mnemonic|seed[_ -]?phrase|recovery[_ -]?phrase")
_PREFIX = r"(?i)(?<![\w-])[\"']?(?:" + _NAME + r")[\"']?\s*[:=]\s*"
_RULES = (
    ("secret-field", re.compile(_PREFIX + r'''(?P<value>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')''')),
    ("secret-field", re.compile(_PREFIX + r"(?P<value>[^\s\"'&,;<>\[\]{}]+)")),
    ("recovery-phrase", re.compile(r"(?im)(?<![\w-])(?:mnemonic|seed[_ -]?phrase|recovery[_ -]?phrase)\s*[:=]\s*(?P<value>[^\r\n]+)")),
    ("authorization", re.compile(r"(?im)\b(?:authorization|proxy-authorization)\s*:\s*(?P<value>[^\r\n]+)")),
    ("bearer-token", re.compile(r"(?i)\bbearer\s+(?P<value>[A-Za-z0-9._~+/-]{8,}=*)")),
    ("session-cookie", re.compile(r"(?im)\b(?:cookie|set-cookie)\s*:\s*(?P<value>[^\r\n]+)")),
    ("url-userinfo", re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://(?P<value>[^\s/@]+)@")),
    ("jwt-shaped", re.compile(r"(?<![A-Za-z0-9_-])(?P<value>eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,})(?![A-Za-z0-9_-])")),
)
_PRIVATE_START = re.compile(r"-----BEGIN (?P<label>(?:(?:RSA|EC|DSA|OPENSSH|ENCRYPTED) )?PRIVATE KEY)-----")
_SECRET_KEY = re.compile(r"(?i)^(?:" + _NAME + r"|authorization|proxy[_-]?authorization|cookie|set[_-]?cookie)$")
_PUBLIC_TOKEN_ADDRESS = re.compile(r"0x[a-fA-F0-9]{40}\Z")


class PrivateArgumentParser(argparse.ArgumentParser):
    """Do not echo unknown options, filenames or values from command arguments."""

    def error(self, message: str) -> None:
        self.exit(2, "Invalid arguments. Use --help; input values are not echoed.\n")


@dataclass(frozen=True)
class Redaction:
    text: str
    counts: dict[str, int]

    def summary(self) -> dict:
        return {"policy": POLICY_ID, "matches_by_rule": dict(sorted(self.counts.items())),
                "redactions_present": bool(self.counts), "manual_review_required": True,
                "all_secrets_detected": False}


def _already_redacted(value: str) -> bool:
    return value.strip().strip("\"'") == REPLACEMENT


def redact_text(text: str) -> Redaction:
    """Redact recognizable fields/spans without retaining their values or hashes."""
    if type(text) is not str or len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("redaction requires bounded UTF-8 text")
    spans: list[tuple[int, int, str]] = []
    counts: Counter = Counter()
    for rule, pattern in _RULES:
        for match in pattern.finditer(text):
            value = match.group("value")
            if not _already_redacted(value):
                spans.append((*match.span("value"), rule))
    for match in _PRIVATE_START.finditer(text):
        end_marker = "-----END " + match.group("label") + "-----"
        end = text.find(end_marker, match.end())
        # Truncated private-key blocks are concealed through EOF, not ignored.
        spans.append((match.start(), len(text) if end < 0 else end + len(end_marker), "private-key-block"))
    if not spans:
        return Redaction(text, {})
    merged: list[tuple[int, int]] = []
    for start, end, rule in sorted(spans):
        counts[rule] += 1
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    parts, offset = [], 0
    for start, end in merged:
        parts.extend((text[offset:start], REPLACEMENT))
        offset = end
    parts.append(text[offset:])
    return Redaction("".join(parts), dict(counts))


def redact_record(value: Any) -> tuple[Any, dict]:
    """Copy a JSON-like record; mask sensitive keys and recognized text patterns.

    A token contract address is public evidence, not an authentication token.
    Unrecognized secrets can remain. No redaction changes the input object.
    """
    if len(canonical(value)) > MAX_BYTES:
        raise ValueError("record exceeds redaction limit")
    counts: Counter = Counter()
    visited = 0

    def text(raw: str) -> str:
        result = redact_text(raw)
        counts.update(result.counts)
        return result.text

    def walk(node, depth):
        nonlocal visited
        visited += 1
        if visited > MAX_NODES or depth > MAX_DEPTH:
            raise ValueError("redaction structure limit exceeded")
        if type(node) is str:
            return text(node)
        if node is None or type(node) in (bool, int, float):
            return node
        if type(node) is list:
            return [walk(child, depth + 1) for child in node]
        if type(node) is dict:
            result = {}
            for key, child in node.items():
                if type(key) is not str:
                    raise ValueError("redaction keys must be text")
                clean_key = text(key)
                if clean_key in result:
                    raise ValueError("redaction would collide record keys")
                public_address = key.lower() == "token" and type(child) is str and _PUBLIC_TOKEN_ADDRESS.fullmatch(child)
                if _SECRET_KEY.fullmatch(key) and not public_address:
                    if child != REPLACEMENT:
                        counts["sensitive-record-field"] += 1
                    result[clean_key] = REPLACEMENT
                else:
                    result[clean_key] = walk(child, depth + 1)
            return result
        raise ValueError("unsupported redaction record type")

    clean = walk(value, 0)
    return clean, Redaction("", dict(counts)).summary()


def text_export(raw: bytes) -> dict[str, bytes]:
    """Build a review derivative without copying original text into the export."""
    if type(raw) is not bytes or len(raw) > MAX_BYTES:
        raise ValueError("log exceeds redaction limit")
    result = redact_text(raw.decode("utf-8", errors="strict"))
    clean = result.text.encode("utf-8")
    receipt = {"schema_version": 1, "status": "REDACTED_REVIEW_ONLY", **result.summary(),
               "original_evidence_included": False, "redacted_sha256": hashlib.sha256(clean).hexdigest()}
    # Deliberately no original secret values, match excerpts or secret fingerprints.
    return {"redacted.txt": clean, "redaction.json": canonical(receipt)}
