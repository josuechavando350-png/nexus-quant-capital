"""Bounded, offline joint-loss experiments over exact verified evidence bundles.

Every input is an operator-supplied research hypothesis. This module does NOT
establish producer independence, causation, authorization or a vulnerability.
It verifies all parent evidence and recalculates a triage assessment for every
subset of distinct COMPLETE byte hashes, up to the explicitly declared order.
"""
from __future__ import annotations

from itertools import combinations
import hashlib
from pathlib import Path
import sys
from typing import Any

from . import critical_chain as triage
from . import evidence_common_mode as common
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = 'offline-joint-bundle-evidence-failure-v1'
FILES = frozenset({'upstream-pin.json', 'joint-failure.json', 'receipt.json', 'REVIEW.md'})
SOURCE_FILES = ('evidence_joint_failure.py', 'evidence_common_mode.py',
                'evidence_ablation.py', 'chain_path_audit.py',
                'critical_chain.py', 'forensic_timeline.py',
                'journal_correlation.py', 'evm_bounded_replay.py',
                'evm_forensic_binding.py', 'evm_opcode_trace.py',
                'safe_io.py', 'privacy.py', 'quality.py', '__main__.py')
MAX_ORDER = 3


class JointFailureError(ValueError):
    """Fixed diagnostic codes; never expose private paths or identifiers."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise JointFailureError(code)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def snapshot() -> dict[str, str]:
    return {name: digest(read_artifact(ROOT, name)) for name in SOURCE_FILES}


def compute(spec: dict, pins: list[dict], baseline: dict,
            previous_common: dict, limit: int) -> dict:
    """Enumerate exactly all <=limit distinct-bundle failure sets.

    'Minimal' means subset-minimal among newly uncovered EVIDENCE SLOTS, not
    min severity, causal proof, or financial impact. Higher-order cuts beyond
    the requested limit remain UNKNOWN when the limit is smaller than the
    number of distinct byte hashes.
    """
    need(type(limit) is int and 1 <= limit <= MAX_ORDER, 'FAILURE_ORDER_LIMIT')
    need(type(pins) is list, 'SOURCE_PIN_LIST')
    groups = common.group_exact_bundles(pins)
    need(type(previous_common) is dict and
         previous_common.get('identical_bundle_alias_groups') ==
         [group['source_ids'] for group in groups if len(group['source_ids']) > 1]
         and previous_common.get('unique_complete_byte_hashes') == len(groups),
         'PARENT_GROUP_DRIFT')
    need(triage.validate_and_score(spec, pins) == baseline, 'PARENT_TRIAGE_DRIFT')
    before = {row['candidate_id']: row for row in baseline['ranked_candidates']}
    need(len(before) == len(spec['candidates']), 'PARENT_CANDIDATE_DRIFT')
    order = min(limit, len(groups))
    scenarios: list[dict[str, Any]] = []
    for n in range(1, order + 1):
        for indices in combinations(range(len(groups)), n):
            removed = set(sid for index in indices for sid in groups[index]['source_ids'])
            after = triage.validate_and_score(common.remove_aliases(spec, removed), pins)
            rec = {row['candidate_id']: row for row in after['ranked_candidates']}
            need(set(rec) == set(before), 'CANDIDATE_DRIFT')
            cases = []
            for cid in sorted(before):
                original, alternative = before[cid], rec[cid]
                need(alternative['priority_score'] <= original['priority_score'],
                     'NON_MONOTONIC_JOINT_FAILURE')
                cases.append({
                    'candidate_id': cid,
                    'new_evidence_gap': alternative['missing_evidence_slots'] >
                                        original['missing_evidence_slots'],
                    'lost_priority': original['priority_score'] - alternative['priority_score'],
                    'missing_slots_after': alternative['missing_evidence_slots'],
                })
            scenarios.append({
                'lost_bundle_hashes': [groups[i]['bundle_sha256'] for i in indices],
                'lost_source_ids': sorted(removed),
                'cases': cases,
            })
    candidates = []
    for cid in sorted(before):
        cuts: list[set[str]] = []
        minimal: list[dict] = []
        for scenario in scenarios:
            lost = set(scenario['lost_bundle_hashes'])
            case = next(x for x in scenario['cases'] if x['candidate_id'] == cid)
            if case['new_evidence_gap'] and not any(cut <= lost for cut in cuts):
                cuts.append(lost)
                minimal.append({'lost_bundle_hashes': scenario['lost_bundle_hashes'],
                                'lost_source_ids': scenario['lost_source_ids'],
                                'priority_loss': case['lost_priority']})
        candidates.append({
            'candidate_id': cid,
            'baseline_priority': before[cid]['priority_score'],
            'baseline_missing_slots': before[cid]['missing_evidence_slots'],
            'minimal_new_gap_failure_sets_up_to_order': minimal,
            'failure_order_fully_exhaustive': order == len(groups),
            'producer_independence_proved': False,
            'critical_impact_confirmed': False,
            'vulnerability_confirmed': False,
        })
    return {
        'schema_version': 1, 'profile': PROFILE,
        'status': 'OFFLINE_BOUNDED_JOINT_EVIDENCE_DEPENDENCE_ONLY',
        'distinct_complete_byte_hashes': len(groups),
        'source_identities': len(pins),
        'tested_failure_orders': list(range(1, order + 1)),
        'entire_bundle_power_set_examined': order == len(groups),
        'scenarios_evaluated': len(scenarios),
        'candidates': candidates,
        'claims': {
            'producer_independence_proved': False,
            'authorization_authenticated': False,
            'causation_proved': False,
            'vulnerability_confirmed': False,
            'critical_impact_confirmed': False,
            'active_testing_permitted': False,
        },
    }


def report(result: dict) -> bytes:
    return (
        '# SUPERHUNTER — bounded joint evidence-loss study\n\n'
        f'Distinct COMPLETE byte hashes: {result["distinct_complete_byte_hashes"]}; '
        f'source IDs: {result["source_identities"]}; '
        f'failure subsets assessed: {result["scenarios_evaluated"]}; '
        f'complete power set: {result["entire_bundle_power_set_examined"]}.\n\n'
        'Evidence sources and their clocks are operator-supplied and reverified '
        'only for local byte integrity. Distinct COMPLETE hashes do NOT prove '
        'independent producers. A minimal gap set identifies a declared '
        'evidence-dependency, NOT a vulnerability or exploit path. Failures of '
        'more bundles than the tested order remain unknown. No external '
        'systems are contacted.\n'
    ).encode('utf-8')


def obtain(common_bundle: Path, ablation_bundle: Path, path_bundle: Path,
           triage_bundle: Path, source_map: Path, order: int) -> tuple[dict, dict]:
    try:
        common.verify(common_bundle, ablation_bundle, path_bundle, triage_bundle,
                      source_map)
        pins = strict_json(b'{"pins":' +
                           read_artifact(triage_bundle, 'source-pins.json').strip() + b'}')['pins']
        spec = strict_json(read_artifact(triage_bundle, 'input.json'))
        baseline = strict_json(read_artifact(triage_bundle, 'assessment.json'))
        earlier = strict_json(read_artifact(common_bundle, 'common-mode.json'))
        value = compute(spec, pins, baseline, earlier, order)
        refs = {
            'common_complete_sha256': digest(read_artifact(common_bundle, 'COMPLETE.json')),
            'ablation_complete_sha256': digest(read_artifact(ablation_bundle, 'COMPLETE.json')),
            'path_complete_sha256': digest(read_artifact(path_bundle, 'COMPLETE.json')),
            'triage_complete_sha256': digest(read_artifact(triage_bundle, 'COMPLETE.json')),
            'source_map_sha256': digest(read_artifact(source_map.parent, source_map.name)),
        }
        return value, refs
    except (ValueError, OSError, TypeError, KeyError, UnicodeError, OverflowError) as exc:
        if type(exc) is JointFailureError:
            raise
        raise JointFailureError('ORIGINAL_REPLAY_FAILED') from exc


def summary(result: dict) -> dict:
    return {'status': result['status'],
            'scenarios_evaluated': result['scenarios_evaluated'],
            'candidates': len(result['candidates']),
            'vulnerability_confirmed': False}


def review(common_bundle: Path, ablation_bundle: Path, path_bundle: Path,
           triage_bundle: Path, source_map: Path, order: int, out: Path) -> dict:
    result, sources = obtain(common_bundle, ablation_bundle, path_bundle,
                             triage_bundle, source_map, order)
    receipt = {'schema_version': 1, 'source_snapshot': snapshot(),
               'parent_sha256': digest(canonical(sources)),
               'result_sha256': digest(canonical(result))}
    write_new_bundle(out, {'upstream-pin.json': canonical(sources),
                           'joint-failure.json': canonical(result),
                           'receipt.json': canonical(receipt),
                           'REVIEW.md': report(result)})
    return summary(result)


def verify(bundle: Path, common_bundle: Path, ablation_bundle: Path,
           path_bundle: Path, triage_bundle: Path, source_map: Path) -> dict:
    need(bundle.is_dir() and not bundle.is_symlink(), 'BUNDLE_DIRECTORY')
    need({p.name for p in bundle.iterdir()} == FILES | {'COMPLETE.json'},
         'BUNDLE_FILES')
    marker = strict_json(read_artifact(bundle, 'COMPLETE.json'))
    need(type(marker) is dict and set(marker) == {'schema_version','sha256'} and
         type(marker['schema_version']) is int and marker['schema_version'] == 1 and
         type(marker['sha256']) is dict and set(marker['sha256']) == FILES,
         'MANIFEST_SCHEMA')
    stored = {name: read_artifact(bundle, name) for name in FILES}
    need(all(type(marker['sha256'][name]) is str and
             marker['sha256'][name] == digest(stored[name]) for name in FILES),
         'ARTIFACT_TAMPERED')
    actual = strict_json(stored['joint-failure.json'])
    need(type(actual) is dict and type(actual.get('tested_failure_orders')) is list
         and actual['tested_failure_orders']
         and all(type(n) is int and 1 <= n <= MAX_ORDER for n in actual['tested_failure_orders'])
         and actual['tested_failure_orders'] ==
         list(range(1, actual['tested_failure_orders'][-1] + 1)),
         'FAILURE_ORDER_RECEIPT')
    order = actual['tested_failure_orders'][-1]
    result, sources = obtain(common_bundle, ablation_bundle, path_bundle,
                             triage_bundle, source_map, order)
    need(stored['upstream-pin.json'] == canonical(sources), 'UPSTREAM_CHANGED')
    need(stored['joint-failure.json'] == canonical(result), 'RESULT_CHANGED')
    need(stored['REVIEW.md'] == report(result), 'REPORT_CHANGED')
    receipt = strict_json(stored['receipt.json'])
    need(type(receipt) is dict and set(receipt) ==
         {'schema_version','source_snapshot','parent_sha256','result_sha256'} and
         type(receipt['schema_version']) is int and receipt['schema_version'] == 1 and
         receipt['source_snapshot'] == snapshot() and
         receipt['parent_sha256'] == digest(canonical(sources)) and
         receipt['result_sha256'] == digest(canonical(result)), 'RECEIPT_CHANGED')
    return summary(result)


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Offline bounded joint evidence-loss audit')
    sub = parser.add_subparsers(dest='command', required=True,
                                parser_class=PrivateArgumentParser)
    a = sub.add_parser('audit-joint-evidence')
    a.add_argument('--common', type=Path, required=True)
    a.add_argument('--ablation', type=Path, required=True)
    a.add_argument('--path-audit', type=Path, required=True)
    a.add_argument('--triage', type=Path, required=True)
    a.add_argument('--sources', type=Path, required=True)
    a.add_argument('--max-failure-order', type=int, default=2)
    a.add_argument('--out', type=Path, required=True)
    b = sub.add_parser('verify-joint-evidence')
    b.add_argument('--bundle', type=Path, required=True)
    b.add_argument('--common', type=Path, required=True)
    b.add_argument('--ablation', type=Path, required=True)
    b.add_argument('--path-audit', type=Path, required=True)
    b.add_argument('--triage', type=Path, required=True)
    b.add_argument('--sources', type=Path, required=True)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        value = (review(args.common, args.ablation, args.path_audit,
                        args.triage, args.sources, args.max_failure_order, args.out)
                 if args.command == 'audit-joint-evidence' else
                 verify(args.bundle, args.common, args.ablation, args.path_audit,
                        args.triage, args.sources))
        print(canonical(value).decode().strip())
        return 0
    except (ValueError, OSError, TypeError, KeyError, OverflowError, UnicodeError) as exc:
        print(exc.args[0] if type(exc) is JointFailureError else
              'JOINT_EVIDENCE_REJECTED', file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
