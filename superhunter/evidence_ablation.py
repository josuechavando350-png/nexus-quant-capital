"""Evidence resilience audit for OFFLINE, operator-provided critical-chain hypotheses.

The engine verifies a private directed-audit package and its original source
bundles, then asks a counterfactual question: which of the *locally verified*
source identities would still support each declared observation and relation
if one source became unavailable? It never changes the original evidence.

This is NOT causal inference, a vulnerability assessment, a security rating, a
probability, or authorization to interact with third-party systems.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from itertools import combinations
from pathlib import Path
import sys
from typing import Any

from . import chain_path_audit as paths
from . import critical_chain as triage
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = 'offline-evidence-source-ablation-v1'
FILES = frozenset({'upstream-pin.json', 'ablation.json', 'receipt.json', 'REVIEW.md'})
SOURCE_FILES = (
    'evidence_ablation.py', 'chain_path_audit.py', 'critical_chain.py',
    'forensic_timeline.py', 'journal_correlation.py', 'evm_bounded_replay.py',
    'evm_forensic_binding.py', 'evm_opcode_trace.py', 'safe_io.py', 'privacy.py',
    'quality.py', '__main__.py',
)


class AblationError(ValueError):
    """Safe diagnostic code; never echo paths, events or observations."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise AblationError(code)


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def exact_fields(value: Any, fields: set[str], code: str) -> None:
    require(type(value) is dict and set(value) == fields, code)


def snapshot() -> dict[str, str]:
    return {name: sha(read_artifact(ROOT, name)) for name in SOURCE_FILES}


def minimum_local_source_cover(
    obligations: list[tuple[str, set[str]]], available: list[str]
) -> list[str] | None:
    """Exact minimum cardinality set-cover, lexical tie-break; <=8 identities.

    Each obligation must have at least one locally verified reference in the
    selected source identities. This DOES NOT attest a source's producer, nor
    imply two source IDs are statistically independent. An empty list means
    no evidence obligations (not an authenticated chain).
    """
    require(len(available) <= triage.MAX_SOURCE and len(set(available)) == len(available),
            'SOURCE_SET_INVALID')
    require(all(type(s) is str for s in available), 'SOURCE_SET_INVALID')
    unique = sorted(available)
    require(all(type(key) is str and type(support) is set and
                support <= set(unique) for key, support in obligations),
            'OBLIGATION_SET_INVALID')
    if any(not support for _, support in obligations):
        return None
    for size in range(len(unique) + 1):
        for subset in combinations(unique, size):
            selected = set(subset)
            if all(selected & support for _, support in obligations):
                return list(subset)
    return None


def filter_source_refs(spec: dict, source_id: str) -> dict:
    """Counterfactual-only in-memory ablation; no source bundle is edited."""
    clone = deepcopy(spec)
    for row in clone['observations'] + clone['links']:
        row['evidence_refs'] = [r for r in row['evidence_refs']
                                if r['source_id'] != source_id]
    return clone


def compute(spec: dict, pins: list[dict], baseline: dict, audit: dict) -> dict:
    require(triage.validate_and_score(spec, pins) == baseline, 'UPSTREAM_TRIAGE_DRIFT')
    require(paths.compute(spec, pins, baseline) == audit, 'UPSTREAM_AUDIT_DRIFT')
    source_ids = sorted(p['source_id'] for p in pins)
    require(len(set(source_ids)) == len(source_ids), 'DUPLICATE_SOURCE_IDS')
    usable = {p['source_id'] for p in pins
              if p['status'] != 'DECLARED_CONSTRAINT_CONTRADICTION'}
    observations = {row['observation_id']: row for row in spec['observations']}
    links = {(row['from'], row['to']): row for row in spec['links']}
    before = {row['candidate_id']: row for row in baseline['ranked_candidates']}
    audits = {row['candidate_id']: row for row in audit['candidates']}

    # Compute one completely revalidated alternative assessment per source.
    # We never pretend that a missing source was independently authenticated.
    alternatives: dict[str, dict[str, dict]] = {}
    for sid in source_ids:
        modified = filter_source_refs(spec, sid)
        alt = triage.validate_and_score(modified, pins)
        alternatives[sid] = {r['candidate_id']: r for r in alt['ranked_candidates']}

    candidates = []
    for candidate in sorted(spec['candidates'], key=lambda x: x['candidate_id']):
        cid = candidate['candidate_id']
        selected = set(candidate['observation_ids'])
        obligations: list[tuple[str, set[str]]] = []
        for oid in sorted(selected):
            sources = {r['source_id'] for r in observations[oid]['evidence_refs']} & usable
            obligations.append((f'observation:{oid}', sources))
        for (start, end), link in sorted(links.items()):
            if start in selected and end in selected:
                sources = {r['source_id'] for r in link['evidence_refs']} & usable
                obligations.append((f'link:{start}->{end}', sources))
        uncovered = sorted(name for name, support in obligations if not support)
        cover = minimum_local_source_cover(obligations, source_ids)
        original = before[cid]
        cases = []
        for sid in source_ids:
            after = alternatives[sid][cid]
            require(after['priority_score'] <= original['priority_score'],
                    'NON_MONOTONIC_ABLATION')
            cases.append({
                'source_id': sid,
                'baseline_priority': original['priority_score'],
                'without_source_priority': after['priority_score'],
                'priority_delta': original['priority_score'] - after['priority_score'],
                'baseline_missing_slots': original['missing_evidence_slots'],
                'without_source_missing_slots': after['missing_evidence_slots'],
                'baseline_status': original['status'],
                'without_source_status': after['status'],
                'introduces_evidence_gap': (
                    after['missing_evidence_slots'] > original['missing_evidence_slots']),
                'severity_confirmed': False,
                'independent_source_authentication_established': False,
            })
        candidates.append({
            'candidate_id': cid,
            'claimed_potential_impact': candidate['potential_impact'],
            'baseline_status': original['status'],
            'baseline_priority': original['priority_score'],
            'structural_witness': audits[cid]['directional_witness'],
            'obligation_count': len(obligations),
            'locally_supported_slots': len(obligations) - len(uncovered),
            'unsupported_slots': uncovered,
            'minimum_cover_locally_verified_source_ids': cover,
            'source_identity_diversity_not_producer_independence': len(cover) if cover is not None else None,
            'single_source_ablations': cases,
            'impact_confirmed': False,
            'causation_proved': False,
            'vulnerability_confirmed': False,
        })
    return {
        'schema_version': 1, 'profile': PROFILE,
        'status': 'OFFLINE_COUNTERFACTUAL_EVIDENCE_DEPENDENCE_ONLY',
        'source_identity_count': len(source_ids),
        'candidates': candidates,
        'claims': {
            'critical_impact_confirmed': False,
            'vulnerability_confirmed': False,
            'causation_proved': False,
            'source_producers_authenticated': False,
            'source_independence_proved': False,
            'authorization_authenticated': False,
            'active_testing_permitted': False,
        },
    }


def document(result: dict) -> bytes:
    incomplete = sum(c['minimum_cover_locally_verified_source_ids'] is None
                     for c in result['candidates'])
    fragile = sum(any(a['introduces_evidence_gap'] for a in c['single_source_ablations'])
                  for c in result['candidates'])
    return (
        '# SUPERHUNTER — evidence-source ablation, offline\n\n'
        f'Candidates: {len(result["candidates"])}; source identities: '
        f'{result["source_identity_count"]}; cases with incomplete local '
        f'evidence: {incomplete}; cases fragile to one source loss: {fragile}.\n\n'
        'Each source-removal scenario recomputes the original triage score. '
        'The minimum-source cover uses an exact bounded enumeration over '
        'locally verified *source IDs*. It does not establish independent '
        'producers, causal links, an actual vulnerability, CVSS severity or '
        'authorization. No external system was contacted or tested. '
        'The original path audit, triage and source map remain required for '
        'independent re-verification.\n'
    ).encode('utf-8')


def obtain(path_audit: Path, triage_bundle: Path, source_map: Path) -> tuple[dict, dict]:
    try:
        paths.verify(path_audit, triage_bundle, source_map)
        spec = strict_json(read_artifact(triage_bundle, 'input.json'))
        pins = strict_json(b'{"pins":' + read_artifact(triage_bundle, 'source-pins.json').strip() + b'}')['pins']
        require(type(pins) is list, 'SOURCE_PIN_LIST')
        baseline = strict_json(read_artifact(triage_bundle, 'assessment.json'))
        audit = strict_json(read_artifact(path_audit, 'path-audit.json'))
        result = compute(spec, pins, baseline, audit)
        pin = {
            'schema_version': 1,
            'path_audit_complete_sha256': sha(read_artifact(path_audit, 'COMPLETE.json')),
            'triage_complete_sha256': sha(read_artifact(triage_bundle, 'COMPLETE.json')),
            'path_audit_sha256': sha(read_artifact(path_audit, 'path-audit.json')),
            'triage_assessment_sha256': sha(read_artifact(triage_bundle, 'assessment.json')),
        }
        return result, pin
    except (ValueError, OSError, KeyError, TypeError, OverflowError, UnicodeError) as exc:
        if type(exc) is AblationError:
            raise
        raise AblationError('UPSTREAM_REPLAY_REJECTED') from exc


def summary(result: dict) -> dict:
    return {'status': result['status'], 'candidates': len(result['candidates']),
            'source_identities': result['source_identity_count'],
            'critical_impact_confirmed': False, 'vulnerability_confirmed': False}


def review(path_audit: Path, triage_bundle: Path, source_map: Path, out: Path) -> dict:
    result, pin = obtain(path_audit, triage_bundle, source_map)
    receipt = {
        'schema_version': 1, 'source_snapshot': snapshot(),
        'upstream_pin_sha256': sha(canonical(pin)),
        'ablation_sha256': sha(canonical(result)),
    }
    write_new_bundle(out, {
        'upstream-pin.json': canonical(pin),
        'ablation.json': canonical(result),
        'receipt.json': canonical(receipt),
        'REVIEW.md': document(result),
    })
    return summary(result)


def verify(bundle: Path, path_audit: Path, triage_bundle: Path, source_map: Path) -> dict:
    require(bundle.is_dir() and not bundle.is_symlink(), 'BUNDLE_DIRECTORY')
    require({p.name for p in bundle.iterdir()} == FILES | {'COMPLETE.json'},
            'BUNDLE_FILES')
    marker = strict_json(read_artifact(bundle, 'COMPLETE.json'))
    exact_fields(marker, {'schema_version', 'sha256'}, 'MANIFEST_SCHEMA')
    require(type(marker['schema_version']) is int and marker['schema_version'] == 1 and
            type(marker['sha256']) is dict and set(marker['sha256']) == FILES,
            'MANIFEST_CONTENTS')
    stored = {name: read_artifact(bundle, name) for name in FILES}
    require(all(type(marker['sha256'][name]) is str and
                marker['sha256'][name] == sha(stored[name]) for name in FILES),
            'BUNDLE_TAMPERED')
    result, pin = obtain(path_audit, triage_bundle, source_map)
    require(stored['upstream-pin.json'] == canonical(pin), 'UPSTREAM_SOURCE_CHANGED')
    require(stored['ablation.json'] == canonical(result), 'ABLATION_RESULT_CHANGED')
    require(stored['REVIEW.md'] == document(result), 'DOCUMENT_CHANGED')
    receipt = strict_json(stored['receipt.json'])
    exact_fields(receipt, {'schema_version', 'source_snapshot',
                           'upstream_pin_sha256', 'ablation_sha256'}, 'RECEIPT_SCHEMA')
    require(type(receipt['schema_version']) is int and receipt['schema_version'] == 1
            and receipt['source_snapshot'] == snapshot()
            and receipt['upstream_pin_sha256'] == sha(canonical(pin))
            and receipt['ablation_sha256'] == sha(canonical(result)), 'RECEIPT_MISMATCH')
    return summary(result)


def main(argv: list[str] | None = None) -> int:
    p = PrivateArgumentParser(description='Offline evidence-source ablation laboratory audit')
    sub = p.add_subparsers(dest='command', required=True, parser_class=PrivateArgumentParser)
    a = sub.add_parser('audit-source-ablation')
    a.add_argument('--path-audit', type=Path, required=True)
    a.add_argument('--triage', type=Path, required=True)
    a.add_argument('--sources', type=Path, required=True)
    a.add_argument('--out', type=Path, required=True)
    b = sub.add_parser('verify-source-ablation')
    b.add_argument('--bundle', type=Path, required=True)
    b.add_argument('--path-audit', type=Path, required=True)
    b.add_argument('--triage', type=Path, required=True)
    b.add_argument('--sources', type=Path, required=True)
    args = p.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = (review(args.path_audit, args.triage, args.sources, args.out)
                  if args.command == 'audit-source-ablation' else
                  verify(args.bundle, args.path_audit, args.triage, args.sources))
        print(canonical(result).decode().strip())
        return 0
    except (ValueError, OSError, KeyError, TypeError, UnicodeError, OverflowError) as exc:
        code = exc.args[0] if type(exc) is AblationError else 'ABLATION_REJECTED'
        print(code, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
