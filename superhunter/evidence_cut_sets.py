"""Offline minimum cut sets for evidence *availability*, never exploit paths.

Given already independently replay-verified and operator-provided source bundles,
compute minimal groups of byte-identical evidence bundles whose joint loss would
leave at least one previously supported declared observation/link unsupported.

This does NOT infer security causation, threat likelihood, criticality, producer
identity, integrity of remote systems, or a real vulnerability.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from typing import Any

from . import critical_chain as triage
from . import evidence_ablation as ablate
from . import evidence_common_mode as common
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = 'offline-minimal-evidence-failure-cuts-v1'
FILES = frozenset({'original-pin.json', 'cut-sets.json', 'receipt.json', 'REVIEW.md'})
SOURCE_FILES = (
    'evidence_cut_sets.py', 'evidence_common_mode.py', 'evidence_ablation.py',
    'chain_path_audit.py', 'critical_chain.py', 'forensic_timeline.py',
    'journal_correlation.py', 'evm_bounded_replay.py', 'evm_forensic_binding.py',
    'evm_opcode_trace.py', 'safe_io.py', 'privacy.py', 'quality.py', '__main__.py',
)


class CutSetError(ValueError):
    """Fixed error codes avoid exposing original evidence in diagnostics."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise CutSetError(code)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def snapshot() -> dict[str, str]:
    return {path: digest(read_artifact(ROOT, path)) for path in SOURCE_FILES}


def minimal_bundle_cut_sets(obligations: list[set[str]], available: set[str]) -> list[list[str]]:
    """Exact inclusion-minimal loss sets; no heuristics or random sampling.

    Each nonempty support set is itself a cut: lose all bundles that can satisfy
    that obligation and the obligation is uncovered. Keep only inclusion-minimal
    such sets. Already unsupported obligations (empty) cannot introduce a NEW gap.
    """
    require(type(available) is set and 1 <= len(available) <= triage.MAX_SOURCE and
            all(type(item) is str and item for item in available), 'BUNDLE_SET')
    require(type(obligations) is list and all(type(item) is set and item <= available
                                              for item in obligations), 'OBLIGATION_INPUT')
    candidates = sorted({frozenset(s) for s in obligations if s},
                        key=lambda s: (len(s), tuple(sorted(s))))
    minimal = []
    for support in candidates:
        if not any(prior <= support for prior in minimal):
            minimal.append(support)
    return [sorted(s) for s in minimal]


def without_bundles(spec: dict, by_source: dict[str, str], missing: set[str]) -> dict:
    affected = {source for source, bundle in by_source.items() if bundle in missing}
    return common.remove_aliases(spec, affected)


def compute(spec: dict, pins: list[dict], previous_ablation: dict,
            previous_common: dict) -> dict:
    require(common.compute(spec, pins, previous_ablation) == previous_common,
            'PARENT_COMMON_MODE_DRIFT')
    groups = common.group_exact_bundles(pins)
    by_source = {sid: group['bundle_sha256'] for group in groups
                 for sid in group['source_ids']}
    bundles = set(by_source.values())
    usable_sources = {p['source_id'] for p in pins
                      if p['status'] != 'DECLARED_CONSTRAINT_CONTRADICTION'}
    baseline = triage.validate_and_score(spec, pins)
    original_scores = {r['candidate_id']: r for r in baseline['ranked_candidates']}
    observations = {row['observation_id']: row for row in spec['observations']}
    relations = {(r['from'], r['to']): r for r in spec['links']}
    cached_alternatives: dict[tuple[str, ...], dict[str, dict]] = {}
    output = []
    for case in sorted(spec['candidates'], key=lambda c: c['candidate_id']):
        cid = case['candidate_id']
        selected = set(case['observation_ids'])
        obligations = []
        for oid in sorted(selected):
            row = observations[oid]
            support = {by_source[r['source_id']] for r in row['evidence_refs']
                       if r['source_id'] in usable_sources}
            obligations.append((f'observation:{oid}', support))
        for (start, end), row in sorted(relations.items()):
            if start in selected and end in selected:
                support = {by_source[r['source_id']] for r in row['evidence_refs']
                           if r['source_id'] in usable_sources}
                obligations.append((f'link:{start}->{end}', support))
        preexisting = sorted(name for name, support in obligations if not support)
        cuts = minimal_bundle_cut_sets([support for _, support in obligations], bundles)
        results = []
        for cut in cuts:
            key = tuple(cut)
            if key not in cached_alternatives:
                changed = triage.validate_and_score(
                    without_bundles(spec, by_source, set(cut)), pins)
                cached_alternatives[key] = {r['candidate_id']: r
                                            for r in changed['ranked_candidates']}
            before, after = original_scores[cid], cached_alternatives[key][cid]
            newly_unsupported = sorted(name for name, support in obligations
                                       if support and support <= set(cut))
            require(bool(newly_unsupported), 'CUT_WITHOUT_NEW_UNCOVERED_OBLIGATION')
            require(after['priority_score'] <= before['priority_score'],
                    'NON_MONOTONIC_SCORE')
            results.append({
                'bundle_sha256_set': cut,
                'lost_distinct_bundles': len(cut),
                'newly_unsupported_obligations': newly_unsupported,
                'original_priority': before['priority_score'],
                'priority_without_bundle_set': after['priority_score'],
                'priority_delta': before['priority_score'] - after['priority_score'],
                'new_evidence_gap_in_triage': (
                    after['missing_evidence_slots'] > before['missing_evidence_slots']),
                'causation_proved': False,
                'vulnerability_confirmed': False,
            })
        output.append({
            'candidate_id': cid,
            'preexisting_uncovered_obligations': preexisting,
            'supported_obligation_count': len(obligations) - len(preexisting),
            'minimum_cut_cardinality': min((len(c) for c in cuts), default=None),
            'minimal_bundle_failure_cut_sets': results,
            'independent_producer_identity_proved': False,
            'critical_impact_confirmed': False,
        })
    return {
        'schema_version': 1, 'profile': PROFILE,
        'status': 'OFFLINE_EVIDENCE_AVAILABILITY_CUTS_ONLY',
        'declared_source_ids': len(pins),
        'distinct_bundle_hashes': len(bundles),
        'candidates': output,
        'claims': {
            'source_authenticity_established': False,
            'independent_producers_established': False,
            'causation_proved': False,
            'critical_impact_confirmed': False,
            'vulnerability_confirmed': False,
            'active_testing_permitted': False,
        },
    }


def report(result: dict) -> bytes:
    n = sum(len(c['minimal_bundle_failure_cut_sets']) for c in result['candidates'])
    return (
        '# SUPERHUNTER — Minimum bundle failure sets (offline)\n\n'
        f'Candidates: {len(result["candidates"])}; distinct COMPLETE byte hashes: '
        f'{result["distinct_bundle_hashes"]}; inclusion-minimal cut sets: {n}.\n\n'
        'Cuts describe operator-provided evidence availability, not attacker paths. '
        'Claims of vulnerability, severity, producer independence, causation or '
        'authorization remain false. Only private, previously verified inputs '
        'were inspected; no system was contacted.\n'
    ).encode('utf-8')


def obtain(common_bundle: Path, ablation_bundle: Path, path_bundle: Path,
           triage_bundle: Path, sources: Path) -> tuple[dict, dict]:
    try:
        common.verify(common_bundle, ablation_bundle, path_bundle, triage_bundle, sources)
        pin_bytes = read_artifact(triage_bundle, 'source-pins.json')
        pins = strict_json(b'{"pins":' + pin_bytes.strip() + b'}')['pins']
        spec = strict_json(read_artifact(triage_bundle, 'input.json'))
        ablation = strict_json(read_artifact(ablation_bundle, 'ablation.json'))
        previous = strict_json(read_artifact(common_bundle, 'common-mode.json'))
        result = compute(spec, pins, ablation, previous)
        pin = {
            'common_complete_sha256': digest(read_artifact(common_bundle, 'COMPLETE.json')),
            'ablation_complete_sha256': digest(read_artifact(ablation_bundle, 'COMPLETE.json')),
            'path_complete_sha256': digest(read_artifact(path_bundle, 'COMPLETE.json')),
            'triage_complete_sha256': digest(read_artifact(triage_bundle, 'COMPLETE.json')),
            'source_pins_sha256': digest(pin_bytes),
        }
        return result, pin
    except (ValueError, KeyError, OSError, UnicodeError, TypeError, OverflowError) as exc:
        if type(exc) is CutSetError:
            raise
        raise CutSetError('UPSTREAM_EVIDENCE_REPLAY_FAILED') from exc


def summary(result: dict) -> dict:
    return {'status': result['status'], 'candidates': len(result['candidates']),
            'distinct_bundle_hashes': result['distinct_bundle_hashes'],
            'critical_impact_confirmed': False, 'vulnerability_confirmed': False}


def review(common_bundle: Path, ablation_bundle: Path, path_bundle: Path,
           triage_bundle: Path, sources: Path, out: Path) -> dict:
    result, pin = obtain(common_bundle, ablation_bundle, path_bundle, triage_bundle, sources)
    receipt = {'schema_version': 1, 'source_snapshot': snapshot(),
               'parent_pin_sha256': digest(canonical(pin)),
               'result_sha256': digest(canonical(result))}
    write_new_bundle(out, {'original-pin.json': canonical(pin),
                           'cut-sets.json': canonical(result),
                           'receipt.json': canonical(receipt),
                           'REVIEW.md': report(result)})
    return summary(result)


def verify(out: Path, common_bundle: Path, ablation_bundle: Path,
           path_bundle: Path, triage_bundle: Path, sources: Path) -> dict:
    require(out.is_dir() and not out.is_symlink(), 'BUNDLE_DIRECTORY')
    require({f.name for f in out.iterdir()} == FILES | {'COMPLETE.json'}, 'BUNDLE_FILE_SET')
    manifest = strict_json(read_artifact(out, 'COMPLETE.json'))
    require(type(manifest) is dict and set(manifest) == {'schema_version', 'sha256'}
            and type(manifest['schema_version']) is int and manifest['schema_version'] == 1
            and type(manifest['sha256']) is dict and set(manifest['sha256']) == FILES,
            'MANIFEST_SCHEMA')
    data = {name: read_artifact(out, name) for name in FILES}
    require(all(type(manifest['sha256'][name]) is str and
                manifest['sha256'][name] == digest(data[name]) for name in FILES),
            'ARTIFACT_TAMPERED')
    result, pin = obtain(common_bundle, ablation_bundle, path_bundle, triage_bundle, sources)
    require(data['original-pin.json'] == canonical(pin), 'ORIGINALS_CHANGED')
    require(data['cut-sets.json'] == canonical(result), 'CUT_SET_MISMATCH')
    require(data['REVIEW.md'] == report(result), 'REPORT_MISMATCH')
    receipt = strict_json(data['receipt.json'])
    require(type(receipt) is dict and set(receipt) ==
            {'schema_version','source_snapshot','parent_pin_sha256','result_sha256'} and
            type(receipt['schema_version']) is int and receipt['schema_version'] == 1 and
            receipt['source_snapshot'] == snapshot() and
            receipt['parent_pin_sha256'] == digest(canonical(pin)) and
            receipt['result_sha256'] == digest(canonical(result)), 'RECEIPT_MISMATCH')
    return summary(result)


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Offline minimal evidence bundle cut-set study')
    sub = parser.add_subparsers(dest='command', required=True,
                                parser_class=PrivateArgumentParser)
    for cmd in ('audit-evidence-cuts', 'verify-evidence-cuts'):
        p = sub.add_parser(cmd)
        if cmd == 'audit-evidence-cuts':
            p.add_argument('--out', required=True, type=Path)
        else:
            p.add_argument('--bundle', required=True, type=Path)
        for key in ('common', 'ablation', 'path-audit', 'triage', 'sources'):
            p.add_argument('--'+key, required=True, type=Path)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        values = (args.common, args.ablation, args.path_audit, args.triage, args.sources)
        result = review(*values, args.out) if args.command == 'audit-evidence-cuts' else verify(args.bundle, *values)
        print(canonical(result).decode().strip())
        return 0
    except (ValueError, KeyError, OSError, UnicodeError, TypeError, OverflowError) as exc:
        code = exc.args[0] if type(exc) is CutSetError else 'EVIDENCE_CUT_SET_REJECTED'
        print(code, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
