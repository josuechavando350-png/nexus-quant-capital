"""Replayable offline ingest of journalctl -o json exports.

Parses an EXISTING local export. Does not run journalctl, contact hosts, extract
secrets, or establish provenance/authenticity of the log producer. The raw export
is preserved in a private bounded bundle and cross-checked by independent replay.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re
import sys
from typing import Any

from .forensic_timeline import analyze, ident, source_snapshot as timeline_sources
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
FILES = frozenset({'journal.jsonl', 'metadata.json', 'normalized.json',
                   'timeline.json', 'receipt.json', 'REVIEW.md'})
MAX_RECORDS = 512
MAX_LINE_BYTES = 32_768
MAX_US = 253402300799999999  # UTC 9999-12-31T23:59:59.999999, exact integer.
US_RE = re.compile(r'(?:0|[1-9][0-9]{0,17})\Z')
ORIGIN = datetime(1970, 1, 1, tzinfo=timezone.utc)


class JournalError(ValueError):
    """Public error code, never records or user-controlled paths."""


def need(valid: bool, code: str) -> None:
    if not valid:
        raise JournalError(code)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sources() -> dict[str, str]:
    return {**timeline_sources(), 'journal_ingest.py': digest(read_artifact(ROOT, 'journal_ingest.py'))}


def metadata(source_id: Any, clock_uncertainty_ms: Any) -> dict[str, Any]:
    ident(source_id, 'SOURCE_ID')
    need(type(clock_uncertainty_ms) is int and 0 <= clock_uncertainty_ms <= 86_400_000,
         'CLOCK_UNCERTAINTY')
    return {'schema_version': 1, 'source_id': source_id,
            'clock_uncertainty_ms': clock_uncertainty_ms}


def normalized(raw: bytes, meta: dict) -> tuple[dict, list[dict]]:
    need(type(meta) is dict and set(meta) == {'schema_version', 'source_id', 'clock_uncertainty_ms'}
         and type(meta['schema_version']) is int and meta['schema_version'] == 1,
         'METADATA_SCHEMA')
    meta = metadata(meta['source_id'], meta['clock_uncertainty_ms'])
    need(type(raw) is bytes and raw and len(raw) <= 2_000_000, 'JOURNAL_SIZE')
    need(b'\x00' not in raw, 'NUL_IN_JOURNAL')
    lines = raw.splitlines(keepends=True)
    need(1 <= len(lines) <= MAX_RECORDS, 'JOURNAL_EVENT_LIMIT')
    # splitlines() can treat non-ASCII Unicode line separators, NEL etc. as
    # boundaries only if they are decoded, which we do NOT do. Reject bare CR.
    events = []
    seen_cursors: set[str] = set()
    byte_offset = 0
    line_receipts = []
    for i, line in enumerate(lines):
        need(len(line) <= MAX_LINE_BYTES and b'\r' not in line,
             'JOURNAL_LINE_INVALID')
        payload = line[:-1] if line.endswith(b'\n') else line
        need(payload and payload[:1] == b'{' and payload[-1:] == b'}', 'JOURNAL_JSON_LINE')
        try:
            entry = strict_json(payload)
        except (ValueError, UnicodeError) as exc:
            raise JournalError('JOURNAL_JSON_INVALID') from exc
        # Accept extra journald fields but never emit their contents. If an
        # arbitrary MESSAGE embeds credentials, it remains only in PRIVATE raw.
        ts = entry.get('__REALTIME_TIMESTAMP')
        need(type(ts) is str and US_RE.fullmatch(ts) is not None, 'JOURNAL_TIMESTAMP')
        microseconds = int(ts)
        need(0 <= microseconds <= MAX_US, 'JOURNAL_TIMESTAMP_RANGE')
        time = (ORIGIN + timedelta(microseconds=microseconds)).isoformat()
        # CURSOR is optional; when provided, duplicate cursors reveal a bad
        # export. We never expose cursors in the normalized result.
        if '__CURSOR' in entry:
            cursor = entry['__CURSOR']
            need(type(cursor) is str and 0 < len(cursor) <= 1024, 'CURSOR_INVALID')
            need(cursor not in seen_cursors, 'DUPLICATE_JOURNAL_CURSOR')
            seen_cursors.add(cursor)
        # A journald record with _PID is NOT proof of process creation. Event
        # kind 'application' signifies only that a log record was observed.
        record_sha = digest(line)
        events.append({'event_id': f'j{i:06d}-{record_sha[:16]}',
                       'source_id': meta['source_id'], 'sequence': i,
                       'timestamp': time, 'kind': 'application',
                       'parent_event_id': None, 'artifact_sha256': record_sha})
        line_receipts.append({'sequence': i, 'offset': byte_offset,
                              'length': len(line), 'sha256': record_sha})
        byte_offset += len(line)
    need(byte_offset == len(raw), 'JOURNAL_BYTES_UNACCOUNTED')
    return {'schema_version': 1, 'profile': 'normalized-evidence-timeline-v1',
            'sources': [{'source_id': meta['source_id'],
                         'clock_uncertainty_ms': meta['clock_uncertainty_ms']}],
            'events': events}, line_receipts


def summary(timeline: dict, count: int) -> bytes:
    return (f'# SuperHunter — journal JSONL evidence, offline\n\n'
            f'Rows parsed: {count}. Timeline status: {timeline["status"]}.\n\n'
            'Input is a pre-existing journalctl -o json export. Exact input bytes '
            'are stored privately and are replayed on verification. Clock values, '
            'cursor identities and source identity are NOT externally authenticated. '
            'Order within this file is not proof of causal order or intrusion. '
            'MESSAGE and other potentially sensitive fields are not in the report.\n').encode()


def build(raw: bytes, meta: dict) -> tuple[dict, dict, list, bytes]:
    normalized_input, line_receipts = normalized(raw, meta)
    timeline = analyze(normalized_input)
    return normalized_input, timeline, line_receipts, summary(timeline, len(line_receipts))


def ingest(source_file: Path, source_id: str, clock_uncertainty_ms: int, out: Path) -> dict:
    raw = read_artifact(source_file.parent, source_file.name)
    meta = metadata(source_id, clock_uncertainty_ms)
    obj, timeline, lines, report = build(raw, meta)
    receipt = {'schema_version': 1, 'source_sha256': digest(raw),
               'source_snapshot': sources(), 'normalized_sha256': digest(canonical(obj)),
               'timeline_sha256': digest(canonical(timeline)), 'lines': lines,
               'status': timeline['status']}
    write_new_bundle(out, {'journal.jsonl': raw, 'metadata.json': canonical(meta),
                           'normalized.json': canonical(obj), 'timeline.json': canonical(timeline),
                           'receipt.json': canonical(receipt), 'REVIEW.md': report})
    return {'status': timeline['status'], 'records': len(lines),
            'source_authenticated': False, 'incident_confirmed': False}


def verify(bundle: Path) -> dict:
    need(bundle.is_dir() and not bundle.is_symlink(), 'BUNDLE_DIRECTORY')
    need({f.name for f in bundle.iterdir()} == FILES | {'COMPLETE.json'}, 'BUNDLE_FILES')
    raw_marker = read_artifact(bundle, 'COMPLETE.json')
    manifest = strict_json(raw_marker)
    need(set(manifest) == {'schema_version', 'sha256'} and
         type(manifest['schema_version']) is int and manifest['schema_version'] == 1 and
         type(manifest['sha256']) is dict and set(manifest['sha256']) == FILES,
         'BUNDLE_MANIFEST')
    files = {name: read_artifact(bundle, name) for name in FILES}
    need(all(type(manifest['sha256'][name]) is str and
             manifest['sha256'][name] == digest(files[name]) for name in FILES),
         'ARTIFACT_CHANGED')
    meta, receipt = strict_json(files['metadata.json']), strict_json(files['receipt.json'])
    need(files['metadata.json'] == canonical(meta), 'NONCANONICAL_METADATA')
    need(type(receipt) is dict and
         set(receipt) == {'schema_version', 'source_sha256', 'source_snapshot',
                          'normalized_sha256', 'timeline_sha256', 'lines', 'status'} and
         type(receipt['schema_version']) is int and receipt['schema_version'] == 1,
         'RECEIPT_SCHEMA')
    need(receipt['source_snapshot'] == sources(), 'SOURCE_CHANGED')
    obj, timeline, lines, report = build(files['journal.jsonl'], meta)
    need(receipt['source_sha256'] == digest(files['journal.jsonl']), 'SOURCE_CHANGED')
    need(files['normalized.json'] == canonical(obj) and
         receipt['normalized_sha256'] == digest(canonical(obj)), 'NORMALIZATION_CHANGED')
    need(files['timeline.json'] == canonical(timeline) and
         receipt['timeline_sha256'] == digest(canonical(timeline)), 'TIMELINE_CHANGED')
    need(receipt['lines'] == lines, 'LINE_OFFSETS_CHANGED')
    need(files['REVIEW.md'] == report and receipt['status'] == timeline['status'],
         'REPORT_CHANGED')
    return {'status': timeline['status'], 'records': len(lines),
            'source_authenticated': False, 'incident_confirmed': False}


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Offline journal JSONL evidence ingestion')
    sub = parser.add_subparsers(dest='command', required=True, parser_class=PrivateArgumentParser)
    p = sub.add_parser('ingest-journal')
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--source-id', type=str, required=True)
    p.add_argument('--clock-uncertainty-ms', type=int, required=True)
    p.add_argument('--out', type=Path, required=True)
    v = sub.add_parser('verify-journal')
    v.add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = (ingest(args.input, args.source_id, args.clock_uncertainty_ms, args.out)
                  if args.command == 'ingest-journal' else verify(args.bundle))
        print(canonical(result).decode().strip())
        return 0
    except (JournalError, ValueError, OSError, OverflowError) as exc:
        print(exc.args[0] if type(exc) is JournalError else 'JOURNAL_REJECTED', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
