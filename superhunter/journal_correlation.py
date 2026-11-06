"""Replayable cross-source journal evidence and *declared* temporal hypotheses.

Uses exclusively pre-existing, locally supplied journalctl exports previously
validated by journal_ingest. Original log bytes remain in a private bundle.
No sensor, network, exploitation, incident attribution or causal certification.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import hashlib
import sys
from typing import Any

from . import forensic_timeline as ft
from . import journal_ingest as journal
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = 'cross-source-journal-hypotheses-v1'
MAX_SOURCES = 8
MAX_EVENTS = 512
MAX_HYPOTHESES = 128
BASE_FILES = {'hypotheses.json', 'case.json', 'receipt.json', 'REVIEW.md'}


class CorrelationError(ValueError):
    """Safe error codes, never raw source data, locations or identifiers."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise CorrelationError(code)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sources() -> dict[str, str]:
    names = ('safe_io.py', 'privacy.py', 'forensic_timeline.py',
             'journal_ingest.py', 'journal_correlation.py')
    return {name: digest(read_artifact(ROOT, name)) for name in names}


def source_names(index: int) -> tuple[str, str]:
    return f'journal-{index:02d}.jsonl', f'journal-{index:02d}.metadata.json'


def validate_hypotheses(raw: bytes, event_source: dict[str, str]) -> list[dict]:
    try:
        obj = strict_json(raw)
    except (ValueError, UnicodeError) as exc:
        raise CorrelationError('HYPOTHESES_JSON_INVALID') from exc
    require(set(obj) == {'schema_version', 'profile', 'hypotheses'} and
            type(obj['schema_version']) is int and obj['schema_version'] == 1 and
            obj['profile'] == PROFILE, 'HYPOTHESES_SCHEMA')
    hypotheses = obj['hypotheses']
    require(type(hypotheses) is list and 1 <= len(hypotheses) <= MAX_HYPOTHESES,
            'HYPOTHESES_LIMIT')
    seen: set[tuple[str, str]] = set()
    for edge in hypotheses:
        require(type(edge) is dict and
                set(edge) == {'from_event_id', 'to_event_id'}, 'HYPOTHESIS_SCHEMA')
        left, right = edge['from_event_id'], edge['to_event_id']
        require(type(left) is str and type(right) is str and
                left in event_source and right in event_source, 'UNKNOWN_EVENT')
        require(left != right and event_source[left] != event_source[right],
                'CROSS_SOURCE_REQUIRED')
        key = (left, right)
        require(key not in seen, 'DUPLICATE_HYPOTHESIS')
        seen.add(key)
    return sorted(hypotheses, key=lambda edge: (edge['from_event_id'], edge['to_event_id']))


def graph_cycles(events: list[dict], hypotheses: list[dict]) -> list[str]:
    """Cycles in source-file order + operator-supplied precedence constraints."""
    children = {e['event_id']: set() for e in events}
    indegree = {event_id: 0 for event_id in children}
    per_source: dict[str, list[dict]] = {}
    for event in events:
        per_source.setdefault(event['source_id'], []).append(event)
    edges = []
    for rows in per_source.values():
        ordered = sorted(rows, key=lambda row: row['sequence'])
        edges.extend((a['event_id'], b['event_id'])
                     for a, b in zip(ordered, ordered[1:]))
    edges += [(e['from_event_id'], e['to_event_id']) for e in hypotheses]
    for a, b in edges:
        if b not in children[a]:
            children[a].add(b)
            indegree[b] += 1
    queue = sorted(key for key, count in indegree.items() if count == 0)
    while queue:
        node = queue.pop(0)
        for nxt in sorted(children[node]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
        queue.sort()
    return sorted(key for key, count in indegree.items() if count)


def calculate(raws: list[bytes], metadata: list[bytes], hypotheses_raw: bytes) -> dict:
    require(type(raws) is list and type(metadata) is list and
            2 <= len(raws) <= MAX_SOURCES and len(raws) == len(metadata),
            'SOURCE_COUNT')
    normalized_sources = []
    events = []
    receipts = []
    seen_source_ids: set[str] = set()
    for index, (raw, meta_bytes) in enumerate(zip(raws, metadata)):
        require(type(raw) is bytes and type(meta_bytes) is bytes,
                'SOURCE_BYTES_REQUIRED')
        try:
            meta = strict_json(meta_bytes)
            normalized, _local_timeline, offsets, _ = journal.build(raw, meta)
        except (ValueError, UnicodeError, OverflowError) as exc:
            raise CorrelationError('INVALID_SOURCE_EVIDENCE') from exc
        source = normalized['sources'][0]
        source_id = source['source_id']
        require(source_id not in seen_source_ids, 'DUPLICATE_SOURCE_ID')
        seen_source_ids.add(source_id)
        normalized_sources.append(source)
        # Each record is tied to its source's exact raw byte segment; the
        # digest is not a producer signature, and file position is not a
        # trusted monotonic timestamp.
        for row, offset in zip(normalized['events'], offsets):
            eid = f's{index:02d}-{row["event_id"]}'
            events.append({**row, 'event_id': eid})
            receipts.append({'event_id': eid, 'source_id': source_id,
                             'source_index': index, 'offset': offset['offset'],
                             'length': offset['length'], 'sha256': offset['sha256']})
        require(len(events) <= MAX_EVENTS, 'TOTAL_EVENT_LIMIT')
    require(len(receipts) == len(events), 'SOURCE_EVENT_COUNT')
    projection = {'schema_version': 1, 'profile': 'normalized-evidence-timeline-v1',
                  'sources': normalized_sources, 'events': events}
    try:
        timeline = ft.analyze(projection)
    except (ValueError, UnicodeError) as exc:
        raise CorrelationError('COMBINED_TIMELINE_INVALID') from exc
    event_source = {e['event_id']: e['source_id'] for e in events}
    hypotheses = validate_hypotheses(hypotheses_raw, event_source)
    index = {e['event_id']: e for e in events}
    clock = {e['source_id']: timedelta(milliseconds=e['clock_uncertainty_ms'])
             for e in normalized_sources}
    outcomes = []
    for edge in hypotheses:
        a, b = edge['from_event_id'], edge['to_event_id']
        from_time = ft.when(index[a]['timestamp'])
        to_time = ft.when(index[b]['timestamp'])
        from_delta, to_delta = clock[index[a]['source_id']], clock[index[b]['source_id']]
        if from_time - from_delta > to_time + to_delta:
            result = 'TEMPORALLY_CONTRADICTED'
        elif from_time + from_delta >= to_time - to_delta:
            result = 'TEMPORAL_ORDER_INCONCLUSIVE'
        else:
            result = 'TEMPORALLY_FEASIBLE_UNPROVEN'
        outcomes.append({'from_event_id': a, 'to_event_id': b,
                         'status': result, 'causation_established': False})
    cyclic = graph_cycles(events, hypotheses)
    status = ('DECLARED_CONSTRAINT_CONTRADICTION'
              if cyclic or timeline['status'] == 'DECLARED_CONSTRAINT_CONTRADICTION'
              or any(e['status'] == 'TEMPORALLY_CONTRADICTED' for e in outcomes)
              else 'INCONCLUSIVE_ORDER'
              if timeline['status'] == 'INCONCLUSIVE_ORDER'
              or any(e['status'] == 'TEMPORAL_ORDER_INCONCLUSIVE' for e in outcomes)
              else 'TEMPORALLY_FEASIBLE_UNVERIFIED')
    return {'schema_version': 1, 'profile': PROFILE, 'status': status,
            'source_count': len(raws), 'event_count': len(events),
            'hypothesis_count': len(outcomes),
            'source_proofs': [
                {'source_id': normalized_sources[i]['source_id'],
                 'raw_sha256': digest(raws[i]), 'metadata_sha256': digest(metadata[i]),
                 'record_count': sum(p['source_index'] == i for p in receipts)}
                for i in range(len(raws))],
            'event_proofs': receipts,
            'timeline': timeline, 'hypotheses': outcomes,
            'unresolved_cycle_nodes': cyclic,
            'claims': {'source_authenticated': False, 'causation_established': False,
                       'incident_confirmed': False, 'vulnerability_confirmed': False,
                       'cross_source_evidence_verified_against_raw_bytes': True}}


def report(result: dict) -> bytes:
    conditions = result['hypotheses']
    contradicted = sum(x['status'] == 'TEMPORALLY_CONTRADICTED' for x in conditions)
    inconclusive = sum(x['status'] == 'TEMPORAL_ORDER_INCONCLUSIVE' for x in conditions)
    feasible = sum(x['status'] == 'TEMPORALLY_FEASIBLE_UNPROVEN' for x in conditions)
    return (f'# SuperHunter — cross-source forensic journal correlation\n\n'
            f'Status: **{result["status"]}**. Sources: {result["source_count"]}, '
            f'events: {result["event_count"]}, hypotheses: {result["hypothesis_count"]}.\n\n'
            f'Contradicted: {contradicted}; inconclusive: {inconclusive}; '
            f'temporally feasible but unproven: {feasible}; '
            f'cycle nodes: {len(result["unresolved_cycle_nodes"])}.\n\n'
            'All source journal bytes remain PRIVATE in the case bundle. '
            'Inputs came from individually replay-verified offline journal bundles; '
            'the private case verifier recalculates every event, byte offset, '
            'hash and graph claim. Source identities, clock bounds and cross-source '
            'precedence links are operator assertions, not independently '
            'authenticated facts. Temporal feasibility does not establish '
            'causation, security incidents or vulnerabilities.\n').encode('utf-8')


def result_summary(result: dict) -> dict:
    return {'status': result['status'], 'sources': result['source_count'],
            'records': result['event_count'], 'hypotheses': result['hypothesis_count'],
            'causation_established': False, 'incident_confirmed': False,
            'vulnerability_confirmed': False}


def correlate(bundles: list[Path], hypotheses_file: Path, output: Path) -> dict:
    require(type(bundles) is list and 2 <= len(bundles) <= MAX_SOURCES, 'SOURCE_COUNT')
    raws, metas = [], []
    for path in bundles:
        try:
            journal.verify(path)
            raws.append(read_artifact(path, 'journal.jsonl'))
            metas.append(read_artifact(path, 'metadata.json'))
        except (ValueError, OSError) as exc:
            raise CorrelationError('UNVERIFIED_JOURNAL_SOURCE') from exc
    hypotheses = read_artifact(hypotheses_file.parent, hypotheses_file.name)
    result = calculate(raws, metas, hypotheses)
    payload: dict[str, bytes] = {'hypotheses.json': hypotheses, 'case.json': canonical(result),
                                 'REVIEW.md': report(result)}
    for index, (raw, meta) in enumerate(zip(raws, metas)):
        source_file, meta_file = source_names(index)
        payload[source_file] = raw
        payload[meta_file] = meta
    receipt = {'schema_version': 1, 'source_count': len(raws),
               'hypotheses_sha256': digest(hypotheses),
               'source_snapshot': sources(),
               'case_sha256': digest(canonical(result))}
    payload['receipt.json'] = canonical(receipt)
    write_new_bundle(output, payload)
    return result_summary(result)


def verify(bundle: Path, expected_complete_sha256: str | None = None) -> dict:
    require(bundle.is_dir() and not bundle.is_symlink(), 'BUNDLE_DIRECTORY')
    marker_bytes = read_artifact(bundle, 'COMPLETE.json')
    if expected_complete_sha256 is not None:
        require(type(expected_complete_sha256) is str and
                ft.HEX64.fullmatch(expected_complete_sha256) is not None,
                'EXPECTED_COMMITMENT_FORMAT')
        require(digest(marker_bytes) == expected_complete_sha256,
                'EXTERNAL_COMMITMENT_MISMATCH')
    manifest = strict_json(marker_bytes)
    receipt_raw = read_artifact(bundle, 'receipt.json')
    receipt = strict_json(receipt_raw)
    require(type(receipt) is dict and
            set(receipt) == {'schema_version', 'source_count', 'hypotheses_sha256',
                             'source_snapshot', 'case_sha256'} and
            type(receipt['schema_version']) is int and receipt['schema_version'] == 1 and
            type(receipt['source_count']) is int and
            2 <= receipt['source_count'] <= MAX_SOURCES,
            'RECEIPT_SCHEMA')
    files = BASE_FILES.copy()
    for i in range(receipt['source_count']):
        names = source_names(i)
        files.update(names)
    require({f.name for f in bundle.iterdir()} == files | {'COMPLETE.json'}, 'BUNDLE_FILES')
    require(type(manifest) is dict and
            set(manifest) == {'schema_version', 'sha256'} and
            type(manifest['schema_version']) is int and manifest['schema_version'] == 1 and
            type(manifest['sha256']) is dict and set(manifest['sha256']) == files,
            'BUNDLE_MANIFEST')
    stored = {name: read_artifact(bundle, name) for name in files}
    require(all(type(manifest['sha256'][name]) is str and
                manifest['sha256'][name] == digest(stored[name]) for name in files),
            'ARTIFACT_TAMPERED')
    require(stored['receipt.json'] == canonical(receipt), 'RECEIPT_NOT_CANONICAL')
    require(receipt['source_snapshot'] == sources(), 'SOURCE_SNAPSHOT_CHANGED')
    raws = [stored[source_names(i)[0]] for i in range(receipt['source_count'])]
    metas = [stored[source_names(i)[1]] for i in range(receipt['source_count'])]
    hypotheses = stored['hypotheses.json']
    require(receipt['hypotheses_sha256'] == digest(hypotheses), 'HYPOTHESES_CHANGED')
    result = calculate(raws, metas, hypotheses)
    require(stored['case.json'] == canonical(result) and
            receipt['case_sha256'] == digest(canonical(result)), 'CASE_RESULT_CHANGED')
    require(stored['REVIEW.md'] == report(result), 'REPORT_CHANGED')
    return result_summary(result)


def main(argv: list[str] | None = None) -> int:
    p = PrivateArgumentParser(description='Offline correlation of authenticated-by-replay journal bundles')
    sub = p.add_subparsers(dest='command', required=True, parser_class=PrivateArgumentParser)
    a = sub.add_parser('correlate-journals')
    a.add_argument('--bundle', type=Path, action='append', required=True)
    a.add_argument('--hypotheses', type=Path, required=True)
    a.add_argument('--out', type=Path, required=True)
    v = sub.add_parser('verify-journal-correlations')
    v.add_argument('--bundle', type=Path, required=True)
    v.add_argument('--expected-complete-sha256', type=str, default=None)
    args = p.parse_args(argv)
    try:
        result = (correlate(args.bundle, args.hypotheses, args.out)
                  if args.command == 'correlate-journals'
                  else verify(args.bundle, args.expected_complete_sha256))
        print(canonical(result).decode().strip())
        return 0
    except (ValueError, OSError, OverflowError) as exc:
        code = exc.args[0] if type(exc) is CorrelationError else 'JOURNAL_CORRELATION_REJECTED'
        print(code, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
