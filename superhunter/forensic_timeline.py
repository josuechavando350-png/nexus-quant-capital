"""Offline, source-bound forensic event timeline with independently replayable evidence.

This is a STRICT NORMALIZED EVENT CONTRACT, not a disk/RAM/PCAP parser or a
claim of verified incident causation. All times, parent links and artifact
hashes are operator-supplied. No target contact, network, execution or repair.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import sys
from typing import Any

from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
SOURCE_FILES = ('forensic_timeline.py', 'safe_io.py', 'privacy.py')
BUNDLE_FILES = {'input.json', 'timeline.json', 'receipt.json', 'REVIEW.md'}
ID = re.compile(r'[a-z0-9][a-z0-9._-]{0,95}\Z')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
KINDS = frozenset({'process', 'file', 'identity', 'network', 'application', 'cloud', 'other'})
MAX_EVENTS = 512
MAX_SOURCES = 64
MAX_UNCERTAINTY_MS = 86_400_000


class TimelineError(ValueError):
    """Error codes only: never include supplied evidence in diagnostics."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise TimelineError(code)


def fields(obj: Any, keys: set[str], code: str) -> None:
    need(type(obj) is dict and set(obj) == keys, code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def ident(value: Any, code: str) -> str:
    need(type(value) is str and ID.fullmatch(value) is not None, code)
    return value


def when(value: Any) -> datetime:
    need(type(value) is str and 10 <= len(value) <= 40 and 'T' in value, 'TIMESTAMP_FORMAT')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise TimelineError('TIMESTAMP_FORMAT') from exc
    need(parsed.tzinfo is not None and parsed.utcoffset() is not None, 'TIMEZONE_REQUIRED')
    try:
        return parsed.astimezone(timezone.utc)
    except OverflowError as exc:
        raise TimelineError('TIMESTAMP_UTC_RANGE') from exc


def source_snapshot() -> dict[str, str]:
    return {name: sha(read_artifact(ROOT, name)) for name in SOURCE_FILES}


def validate(value: Any) -> tuple[list[dict], list[dict], dict[str, int]]:
    fields(value, {'schema_version', 'profile', 'sources', 'events'}, 'ROOT_SCHEMA')
    need(type(value['schema_version']) is int and value['schema_version'] == 1,
         'SCHEMA_VERSION')
    need(value['profile'] == 'normalized-evidence-timeline-v1', 'PROFILE')
    sources, events = value['sources'], value['events']
    need(type(sources) is list and 1 <= len(sources) <= MAX_SOURCES, 'SOURCE_LIMIT')
    need(type(events) is list and 1 <= len(events) <= MAX_EVENTS, 'EVENT_LIMIT')
    uncertainty: dict[str, int] = {}
    for source in sources:
        fields(source, {'source_id', 'clock_uncertainty_ms'}, 'SOURCE_SCHEMA')
        sid = ident(source['source_id'], 'SOURCE_ID')
        need(sid not in uncertainty, 'DUPLICATE_SOURCE')
        delta = source['clock_uncertainty_ms']
        need(type(delta) is int and 0 <= delta <= MAX_UNCERTAINTY_MS, 'CLOCK_UNCERTAINTY')
        uncertainty[sid] = delta
    seen: set[str] = set()
    by_sequence: set[tuple[str, int]] = set()
    for event in events:
        fields(event, {'event_id', 'source_id', 'sequence', 'timestamp', 'kind',
                       'parent_event_id', 'artifact_sha256'}, 'EVENT_SCHEMA')
        eid, sid = ident(event['event_id'], 'EVENT_ID'), ident(event['source_id'], 'SOURCE_ID')
        need(eid not in seen, 'DUPLICATE_EVENT')
        need(sid in uncertainty, 'UNREGISTERED_SOURCE')
        seen.add(eid)
        seq = event['sequence']
        need(type(seq) is int and 0 <= seq < 2**64, 'SEQUENCE_TYPE')
        need((sid, seq) not in by_sequence, 'DUPLICATE_SOURCE_SEQUENCE')
        by_sequence.add((sid, seq))
        when(event['timestamp'])
        need(type(event['kind']) is str and event['kind'] in KINDS, 'EVENT_KIND')
        parent = event['parent_event_id']
        if parent is not None:
            ident(parent, 'PARENT_EVENT_ID')
            need(parent != eid, 'SELF_PARENT')
        digest = event['artifact_sha256']
        need(type(digest) is str and HEX64.fullmatch(digest) is not None, 'ARTIFACT_DIGEST')
    need(all(e['parent_event_id'] is None or e['parent_event_id'] in seen for e in events),
         'MISSING_PARENT')
    return sources, events, uncertainty


def analyze(value: dict) -> dict:
    _, events, clock = validate(value)
    index = {e['event_id']: e for e in events}
    times = {eid: when(row['timestamp']) for eid, row in index.items()}
    # Exact integer microseconds allow uncertainty intervals to extend beyond
    # datetime bounds without overflowing or silently clipping their width.
    origin = datetime(1970, 1, 1, tzinfo=timezone.utc)
    deltas = {eid: value - origin for eid, value in times.items()}
    ticks = {eid: (d.days * 86400 + d.seconds) * 1_000_000 + d.microseconds
             for eid, d in deltas.items()}
    contradictions: list[dict] = []
    uncertain: list[dict] = []
    edges: list[tuple[str, str, str]] = []
    # Explicit parent edges assert a relation. They are not independently
    # authenticated and cannot by themselves prove causal influence.
    for event in events:
        parent = event['parent_event_id']
        if parent is not None:
            edges.append((parent, event['event_id'], 'declared_parent'))
    # Local order is another DECLARED constraint, not a trusted monotonic clock.
    per_source: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        per_source[event['source_id']].append(event)
    for rows in per_source.values():
        rows.sort(key=lambda e: e['sequence'])
        for left, right in zip(rows, rows[1:]):
            edges.append((left['event_id'], right['event_id'], 'declared_source_sequence'))
    # An edge is impossible only if even the claimed clock error bounds cannot
    # explain reversed time. Overlap is INCONCLUSIVE, never an accepted proof.
    for a, b, relation in sorted(edges):
        left, right = index[a], index[b]
        d1, d2 = clock[left['source_id']] * 1000, clock[right['source_id']] * 1000
        if ticks[a] - d1 > ticks[b] + d2:
            contradictions.append({'from': a, 'to': b, 'relation': relation,
                                   'reason': 'TEMPORAL_INVERSION'})
        elif ticks[a] + d1 >= ticks[b] - d2:
            uncertain.append({'from': a, 'to': b, 'relation': relation,
                              'reason': 'OVERLAPPING_CLOCK_INTERVALS'})
    # Kahn's algorithm detects cycles across parent and sequence constraints.
    outgoing: dict[str, set[str]] = {eid: set() for eid in index}
    indegree = {eid: 0 for eid in index}
    for a, b, _ in edges:
        if b not in outgoing[a]:
            outgoing[a].add(b)
            indegree[b] += 1
    ready = sorted(eid for eid, degree in indegree.items() if degree == 0)
    visited = 0
    while ready:
        node = ready.pop(0)
        visited += 1
        for child in sorted(outgoing[node]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
        ready.sort()
    cyclic = sorted(eid for eid, degree in indegree.items() if degree != 0)
    status = ('DECLARED_CONSTRAINT_CONTRADICTION' if contradictions or cyclic else
              'INCONCLUSIVE_ORDER' if uncertain else 'DECLARED_ORDER_CONSISTENT')
    timeline = [{'event_id': e['event_id'], 'source_id': e['source_id'],
                 'sequence': e['sequence'], 'timestamp_utc': times[e['event_id']].isoformat(),
                 'kind': e['kind'], 'parent_event_id': e['parent_event_id'],
                 'artifact_sha256': e['artifact_sha256'],
                 'record_sha256': sha(canonical(e))}
                for e in sorted(events, key=lambda e: (times[e['event_id']], e['event_id']))]
    return {'schema_version': 1, 'profile': 'normalized-evidence-timeline-v1',
            'status': status, 'event_count': len(events), 'source_count': len(clock),
            'declared_edges': len(edges), 'contradictions': contradictions,
            'uncertain_edges': uncertain, 'topologically_unresolved_nodes': cyclic,
            'timeline': timeline, 'claims': {
                'normalized_input_bytes_preserved_in_bundle': True,
                'incident_confirmed': False, 'vulnerability_confirmed': False,
                'evidence_authenticated': False, 'causation_proved': False,
                'raw_disk_ram_pcap_parsed': False}}


def report(result: dict) -> bytes:
    return (f"# SUPERHUNTER — forensic timeline, offline review\n\n"
            f"Estado: **{result['status']}**. "
            f"Eventos: {result['event_count']}; fuentes: {result['source_count']}; "
            f"relaciones declaradas: {result['declared_edges']}.\n\n"
            f"Contradicciones temporales: {len(result['contradictions'])}; "
            f"ordenamientos inciertos: {len(result['uncertain_edges'])}; "
            f"nodos sin orden topológico: {len(result['topologically_unresolved_nodes'])}.\n\n"
            "El archivo input.json conserva los bytes ORIGINALES recibidos. "
            "Eventos, relaciones, marcas de tiempo y hashes de artefactos son "
            "declaraciones del operador; no prueban autenticidad, intrusión ni "
            "causalidad. No se analizaron imágenes de disco/RAM/PCAP.\n").encode('utf-8')


def review(input_file: Path, output: Path) -> dict:
    raw = read_artifact(input_file.parent, input_file.name)
    result = analyze(strict_json(raw))
    receipt = {'schema_version': 1, 'input_sha256': sha(raw),
               'source_snapshot': source_snapshot(), 'result_sha256': sha(canonical(result)),
               'status': result['status']}
    write_new_bundle(output, {'input.json': raw, 'timeline.json': canonical(result),
                              'receipt.json': canonical(receipt), 'REVIEW.md': report(result)})
    return {'status': result['status'], 'events': result['event_count'],
            'incident_confirmed': False, 'vulnerability_confirmed': False}


def verify(bundle: Path) -> dict:
    need(bundle.is_dir() and not bundle.is_symlink(), 'BUNDLE_DIRECTORY')
    need({p.name for p in bundle.iterdir()} == BUNDLE_FILES | {'COMPLETE.json'},
         'BUNDLE_FILE_SET')
    marker = strict_json(read_artifact(bundle, 'COMPLETE.json'))
    fields(marker, {'schema_version', 'sha256'}, 'BUNDLE_MANIFEST_SCHEMA')
    need(type(marker['schema_version']) is int and marker['schema_version'] == 1,
         'BUNDLE_MANIFEST_VERSION')
    need(type(marker['sha256']) is dict and set(marker['sha256']) == BUNDLE_FILES,
         'BUNDLE_MANIFEST_FILES')
    contents = {name: read_artifact(bundle, name) for name in BUNDLE_FILES}
    for name, raw in contents.items():
        need(marker['sha256'][name] == sha(raw), 'ARTIFACT_TAMPERED')
    receipt = strict_json(contents['receipt.json'])
    fields(receipt, {'schema_version', 'input_sha256', 'source_snapshot',
                     'result_sha256', 'status'}, 'RECEIPT_SCHEMA')
    need(type(receipt['schema_version']) is int and receipt['schema_version'] == 1,
         'RECEIPT_VERSION')
    need(receipt['source_snapshot'] == source_snapshot(), 'SOURCE_CHANGED')
    need(receipt['input_sha256'] == sha(contents['input.json']), 'INPUT_TAMPERED')
    actual = analyze(strict_json(contents['input.json']))
    need(contents['timeline.json'] == canonical(actual), 'DERIVED_TIMELINE_MISMATCH')
    need(contents['REVIEW.md'] == report(actual), 'REPORT_MISMATCH')
    need(receipt['result_sha256'] == sha(canonical(actual)) and
         receipt['status'] == actual['status'], 'RECEIPT_MISMATCH')
    return {'status': actual['status'], 'events': actual['event_count'],
            'incident_confirmed': False, 'vulnerability_confirmed': False}


def main(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    p = PrivateArgumentParser(description='Offline normalized forensic evidence timeline')
    subs = p.add_subparsers(dest='command', required=True, parser_class=PrivateArgumentParser)
    a = subs.add_parser('review-forensic-timeline')
    a.add_argument('--input', type=Path, required=True)
    a.add_argument('--out', type=Path, required=True)
    b = subs.add_parser('verify-forensic-timeline')
    b.add_argument('--bundle', type=Path, required=True)
    args = p.parse_args(args_list)
    try:
        result = review(args.input, args.out) if args.command == 'review-forensic-timeline' else verify(args.bundle)
        print(canonical(result).decode().strip())
        return 0
    except (TimelineError, ValueError, OSError) as exc:
        # Never echo user-controlled event payloads, files, URLs or timestamps.
        code = exc.args[0] if type(exc) is TimelineError else 'FORENSIC_TIMELINE_REJECTED'
        print(code, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
