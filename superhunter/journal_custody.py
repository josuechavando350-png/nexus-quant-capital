"""Verify existing local journal bytes, custody and declared clock context.

No acquisition, signing, remote inputs or execution. Custody cannot establish
log authenticity, causal order or an incident. Uncertainty is never promoted.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import custody, journal_ingest as journal, quality
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

PROFILE = 'local-journal-custody-temporal-context-v1'
FILES = {'report.json', 'REVIEW.md'}
ROOT = Path(__file__).resolve().parent.parent
STATES = {'DECLARED_ORDER_CONSISTENT': 'CUSTODY_VERIFIED_DECLARED_ORDER_CONSISTENT',
          'INCONCLUSIVE_ORDER': 'CUSTODY_VERIFIED_INCONCLUSIVE_ORDER',
          'DECLARED_CONSTRAINT_CONTRADICTION': 'CUSTODY_VERIFIED_CONTRADICTION'}
LIMITS = {'source_authenticated': False, 'execution_authenticated': False,
          'clock_bound_authenticated': False, 'causation_proved': False,
          'incident_confirmed': False, 'vulnerability_confirmed': False}


def need(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _capture(root: Path, files: set[str]) -> dict[str, bytes]:
    custody._regular_root(root)
    names = set()
    for index, entry in enumerate(root.iterdir()):
        need(index <= len(files), 'JOURNAL_CUSTODY_INVENTORY')
        names.add(entry.name)
    need(names == files | {'COMPLETE.json'}, 'JOURNAL_CUSTODY_INVENTORY')
    values = {name: read_artifact(root, name) for name in names}
    expected = {'schema_version': 1, 'sha256': {name: quality.sha(values[name]) for name in files}}
    need(canonical(strict_json(values['COMPLETE.json'])) == canonical(expected), 'JOURNAL_CUSTODY_MANIFEST')
    return values


def _separate(bundle: Path, seal: Path, trust: Path) -> None:
    a, b = bundle.resolve(), seal.resolve()
    need(not a.is_relative_to(b) and not b.is_relative_to(a), 'JOURNAL_CUSTODY_OVERLAP')
    need(not trust.resolve().is_relative_to(a) and not trust.resolve().is_relative_to(b),
         'JOURNAL_CUSTODY_EXTERNAL_TRUST_REQUIRED')
    custody._regular_root(trust.parent)


def collect(journal_bundle: Path, seal: Path, trust: Path, *, source_digest: str,
            journal_anchor: str, seal_anchor: str, case_id: str, producer_id: str,
            expected_source_id: str, expected_clock_uncertainty_ms: int) -> dict:
    for value in (source_digest, journal_anchor, seal_anchor):
        custody.hex_bytes(value, 32)
    expected_meta = journal.metadata(expected_source_id, expected_clock_uncertainty_ms)
    custody.case_uuid(case_id); custody.producer(producer_id)
    _separate(journal_bundle, seal, trust)
    snapshot = quality.source_snapshot()
    need(quality.sha(canonical(snapshot)) == source_digest, 'JOURNAL_CUSTODY_SOURCE')
    raw = _capture(journal_bundle, set(journal.FILES)); signed = _capture(seal, custody.SEAL_FILES)
    policy = read_artifact(trust.parent, trust.name)
    need(sum(map(len, raw.values())) + sum(map(len, signed.values())) + len(policy) <= custody.MAX_TOTAL_BYTES,
         'JOURNAL_CUSTODY_TOTAL_BYTES')
    need(quality.sha(raw['COMPLETE.json']) == journal_anchor and
         quality.sha(signed['COMPLETE.json']) == seal_anchor, 'JOURNAL_CUSTODY_ANCHOR')
    need(raw['metadata.json'] == canonical(expected_meta), 'JOURNAL_CUSTODY_TEMPORAL_CONTEXT')
    signature = custody.verify_seal(journal_bundle, seal, trust, case_id=case_id, producer_id=producer_id)
    need(signature['signature_valid'] is True, 'JOURNAL_CUSTODY_SIGNATURE_REQUIRED')
    checked = journal.verify(journal_bundle)
    timeline = strict_json(raw['timeline.json'])
    receipt = strict_json(raw['receipt.json'])
    need(checked['status'] in STATES and checked['status'] == timeline['status'] and
         checked['records'] == timeline['event_count'], 'JOURNAL_CUSTODY_TIMELINE_IDENTITY')
    events = timeline['timeline']
    result = {'schema_version': 1, 'profile': PROFILE, 'status': STATES[checked['status']],
              'timeline_status': checked['status'], 'source_digest': source_digest,
              'case_id': case_id, 'producer_id': producer_id, 'key_id': signature['key_id'],
              'records': checked['records'], 'source_id': expected_source_id,
              'clock_uncertainty_ms': expected_clock_uncertainty_ms,
              'declared_edges': timeline['declared_edges'],
              'contradictions': timeline['contradictions'], 'uncertain_edges': timeline['uncertain_edges'],
              'unresolved_nodes': timeline['topologically_unresolved_nodes'],
              'first_observed_timestamp_utc': events[0]['timestamp_utc'],
              'last_observed_timestamp_utc': events[-1]['timestamp_utc'],
              'raw_journal_sha256': receipt['source_sha256'],
              'line_receipts_sha256': quality.sha(canonical({'lines': receipt['lines']})),
              'anchors': {'journal_complete_sha256': journal_anchor, 'seal_complete_sha256': seal_anchor,
                          'trust_sha256': quality.sha(policy)},
              'custody_signature_verified': True, 'journal_semantics_recomputed': True,
              'limitations': dict(LIMITS)}
    need(_capture(journal_bundle, set(journal.FILES)) == raw and _capture(seal, custody.SEAL_FILES) == signed,
         'JOURNAL_CUSTODY_EVIDENCE_CHANGED')
    need(read_artifact(trust.parent, trust.name) == policy, 'JOURNAL_CUSTODY_TRUST_CHANGED')
    need(quality.source_snapshot() == snapshot, 'JOURNAL_CUSTODY_SOURCE_CHANGED')
    return result


def render(result: dict) -> bytes:
    return (f"# Journal local con custodia\n\nEstado: {result['status']}.\n"
            f"Registros: {result['records']}; incertidumbre declarada: {result['clock_uncertainty_ms']} ms.\n"
            f"Relaciones inciertas: {len(result['uncertain_edges'])}; contradicciones: {len(result['contradictions'])}.\n\n"
            'La firma valida custodia de bytes bajo la política externa aportada.\n'
            'Identidad de fuente, timestamps y margen de error siguen siendo declaraciones.\n'
            'Orden coherente no prueba causalidad; orden incierto o contradictorio no se aprueba.\n'
            'Los mensajes originales permanecen solo en el expediente de entrada privado.\n').encode()


def _output(out: Path, bundle: Path, seal: Path, trust: Path, *, new: bool) -> None:
    resolved = out.resolve()
    need(not out.is_symlink() and not resolved.is_relative_to(ROOT) and (not new or not out.exists()),
         'JOURNAL_CUSTODY_OUTPUT')
    for parent in out.absolute().parents:
        need(not parent.is_symlink(), 'JOURNAL_CUSTODY_OUTPUT_SYMLINK')
    for other in (bundle.resolve(), seal.resolve()):
        need(not resolved.is_relative_to(other) and not other.is_relative_to(resolved),
             'JOURNAL_CUSTODY_OUTPUT_OVERLAP')
    need(not trust.resolve().is_relative_to(resolved), 'JOURNAL_CUSTODY_TRUST_IN_OUTPUT')


def create(journal_bundle: Path, seal: Path, trust: Path, out: Path, **context) -> dict:
    _output(out, journal_bundle, seal, trust, new=True)
    result = collect(journal_bundle, seal, trust, **context)
    write_new_bundle(out, {'report.json': canonical(result), 'REVIEW.md': render(result)})
    return result


def verify(journal_bundle: Path, seal: Path, trust: Path, bundle: Path, *, report_anchor: str, **context) -> dict:
    custody.hex_bytes(report_anchor, 32)
    _output(bundle, journal_bundle, seal, trust, new=False)
    raw = _capture(bundle, FILES)
    need(quality.sha(raw['COMPLETE.json']) == report_anchor, 'JOURNAL_CUSTODY_REPORT_ANCHOR')
    result = collect(journal_bundle, seal, trust, **context)
    need(raw['report.json'] == canonical(result) and raw['REVIEW.md'] == render(result),
         'JOURNAL_CUSTODY_REPORT_MISMATCH')
    need(_capture(bundle, FILES) == raw, 'JOURNAL_CUSTODY_REPORT_CHANGED')
    return result


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Verify custody and declared temporal context of a local journal')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('review-journal-custody'); check = sub.add_parser('verify-journal-custody')
    for command in (make, check):
        for name in ('journal-bundle', 'seal', 'trust'):
            command.add_argument('--'+name, required=True, type=Path)
        for name in ('source-digest', 'journal-anchor', 'seal-anchor', 'case-id', 'producer-id', 'expected-source-id'):
            command.add_argument('--'+name, required=True)
        command.add_argument('--expected-clock-uncertainty-ms', required=True, type=int)
    make.add_argument('--out', required=True, type=Path)
    check.add_argument('--bundle', required=True, type=Path); check.add_argument('--report-anchor', required=True)
    args = vars(parser.parse_args(argv)); command = args.pop('command')
    try:
        result = create(**args) if command == 'review-journal-custody' else verify(**args)
        print(json.dumps({key: result[key] for key in ('status', 'records', 'custody_signature_verified')}))
        return 0 if result['timeline_status'] == 'DECLARED_ORDER_CONSISTENT' else 1
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        print(json.dumps({'status': 'JOURNAL_CUSTODY_REJECTED', 'custody_signature_verified': False}))
        return 2


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
