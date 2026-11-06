"""Offline common-mode failure audit for evidence source identities.

Two source IDs may map to one byte-identical signed-*looking* bundle. A hash
proves only content equality, not a signature, producer, custody, or authorized
scope. This audit combines aliases and measures what happens if the common
bundle disappears; it does not operate on any target systems.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy
from pathlib import Path
import sys
from typing import Any

from . import evidence_ablation as ablate
from . import critical_chain as triage
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

PROFILE = 'offline-evidence-common-bundle-failure-v1'
ROOT = Path(__file__).resolve().parent
FILES = frozenset({'parent-pin.json', 'common-mode.json', 'receipt.json', 'REVIEW.md'})
SOURCE_FILES = (
    'evidence_common_mode.py', 'evidence_ablation.py', 'chain_path_audit.py',
    'critical_chain.py', 'forensic_timeline.py', 'journal_correlation.py',
    'evm_bounded_replay.py', 'evm_forensic_binding.py', 'evm_opcode_trace.py',
    'safe_io.py', 'privacy.py', 'quality.py', '__main__.py',
)


class CommonModeError(ValueError):
    """User-private data is never placed into diagnostic codes."""


def require(value: bool, code: str) -> None:
    if not value:
        raise CommonModeError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def snapshot() -> dict[str, str]:
    return {x: sha(read_artifact(ROOT, x)) for x in SOURCE_FILES}


def group_exact_bundles(pins: list[dict]) -> list[dict]:
    """Group by exact COMPLETE bytes (SHA256). Not a producer identity test."""
    groups: dict[str, list[str]] = {}
    ids: set[str] = set()
    for entry in pins:
        require(type(entry) is dict and type(entry.get('source_id')) is str and
                type(entry.get('complete_sha256')) is str and
                len(entry['complete_sha256']) == 64 and
                all(c in '0123456789abcdef' for c in entry['complete_sha256']),
                'SOURCE_PIN_SCHEMA')
        sid = entry['source_id']
        require(sid not in ids, 'DUPLICATE_SOURCE_ID')
        ids.add(sid)
        groups.setdefault(entry['complete_sha256'], []).append(sid)
    require(1 <= len(ids) <= triage.MAX_SOURCE, 'SOURCE_COUNT')
    return sorted(({'bundle_sha256': digest, 'source_ids': sorted(names)}
                   for digest, names in groups.items()),
                  key=lambda row: (row['source_ids'], row['bundle_sha256']))


def remove_aliases(spec: dict, identities: set[str]) -> dict:
    clone = deepcopy(spec)
    for item in clone['observations'] + clone['links']:
        item['evidence_refs'] = [r for r in item['evidence_refs']
                                 if r['source_id'] not in identities]
    return clone


def compute(spec: dict, pins: list[dict], ablation: dict) -> dict:
    groups = group_exact_bundles(pins)
    baseline = triage.validate_and_score(spec, pins)
    original = {r['candidate_id']: r for r in baseline['ranked_candidates']}
    abst = {r['candidate_id']: r for r in ablation['candidates']}
    require(set(original) == set(abst), 'PARENT_CANDIDATE_DRIFT')
    require(all(row['baseline_priority'] == original[cid]['priority_score'] and
                row['baseline_status'] == original[cid]['status']
                for cid, row in abst.items()), 'PARENT_SCORE_DRIFT')
    report = []
    for group in groups:
        ids = group['source_ids']
        # Recompute without ANY alias of one identical bundle. Removing each
        # alias individually could create a false picture of redundancy.
        alternative = triage.validate_and_score(remove_aliases(spec, set(ids)), pins)
        other = {r['candidate_id']: r for r in alternative['ranked_candidates']}
        cases = []
        for cid in sorted(original):
            before, after = original[cid], other[cid]
            require(after['priority_score'] <= before['priority_score'],
                    'NON_MONOTONIC_COMMON_FAILURE')
            single_loss = [a for a in abst[cid]['single_source_ablations']
                           if a['source_id'] in ids]
            require(len(single_loss) == len(ids), 'PARENT_ABLATION_MISSING')
            group_loss = after['missing_evidence_slots'] > before['missing_evidence_slots']
            cases.append({
                'candidate_id': cid,
                'original_priority': before['priority_score'],
                'without_identical_bundle_priority': after['priority_score'],
                'priority_delta': before['priority_score'] - after['priority_score'],
                'original_missing_slots': before['missing_evidence_slots'],
                'without_identical_bundle_missing_slots': after['missing_evidence_slots'],
                'new_evidence_gap': group_loss,
                'single_alias_tests_were_insufficient': (
                    len(ids) > 1 and group_loss and
                    all(not a['introduces_evidence_gap'] for a in single_loss)),
                'verified_producer_independence': False,
                'vulnerability_confirmed': False,
            })
        report.append({
            'bundle_sha256': group['bundle_sha256'],
            'source_ids': ids,
            'identical_bundle_alias_count': len(ids),
            'cases': cases,
        })
    duplicates = [g['source_ids'] for g in groups if len(g['source_ids']) > 1]
    return {
        'schema_version': 1, 'profile': PROFILE,
        'status': 'EXACT_BUNDLE_ALIAS_REVIEW_ONLY',
        'source_identities': len(pins),
        'unique_complete_byte_hashes': len(groups),
        'identical_bundle_alias_groups': duplicates,
        'group_ablations': report,
        'claims': {
            'source_authenticity_established': False,
            'independent_producers_established': False,
            'authorization_authenticated': False,
            'causation_proved': False,
            'critical_impact_confirmed': False,
            'vulnerability_confirmed': False,
            'active_testing_permitted': False,
        },
    }


def text_report(result: dict) -> bytes:
    false_redundancy = sum(
        case['single_alias_tests_were_insufficient']
        for item in result['group_ablations'] for case in item['cases'])
    return (
        '# SUPERHUNTER — offline common-mode evidence analysis\n\n'
        f'Source identities: {result["source_identities"]}; distinct COMPLETE '
        f'byte hashes: {result["unique_complete_byte_hashes"]}; duplicate '
        f'bundle groups: {len(result["identical_bundle_alias_groups"])}; '
        f'candidate/common-bundle false-redundancy situations: {false_redundancy}.\n\n'
        'Equality of COMPLETE bytes means identical *local bundle material*, '
        'NOT producer identity, independent custody, or proof that two different '
        'hashes originate independently. All conclusions are hypotheses for '
        'authorized laboratory investigation. No remote system was touched.\n'
    ).encode('utf-8')


def obtain(ablation_bundle: Path, path_bundle: Path,
           triage_bundle: Path, sources_file: Path) -> tuple[dict, dict]:
    try:
        ablate.verify(ablation_bundle, path_bundle, triage_bundle, sources_file)
        raw = read_artifact(triage_bundle, 'source-pins.json')
        pins = strict_json(b'{"pins":' + raw.strip() + b'}')['pins']
        spec = strict_json(read_artifact(triage_bundle, 'input.json'))
        old_ablation = strict_json(read_artifact(ablation_bundle, 'ablation.json'))
        result = compute(spec, pins, old_ablation)
        pin = {
            'ablation_complete_sha256': sha(read_artifact(ablation_bundle, 'COMPLETE.json')),
            'path_complete_sha256': sha(read_artifact(path_bundle, 'COMPLETE.json')),
            'triage_complete_sha256': sha(read_artifact(triage_bundle, 'COMPLETE.json')),
            'source_pins_sha256': sha(raw),
        }
        return result, pin
    except (ValueError, OSError, TypeError, KeyError, OverflowError, UnicodeError) as exc:
        if type(exc) is CommonModeError:
            raise
        raise CommonModeError('ORIGINAL_EVIDENCE_REPLAY_FAILED') from exc


def summary(result: dict) -> dict:
    return {'status': result['status'],
            'source_identities': result['source_identities'],
            'identical_bundle_groups': len(result['identical_bundle_alias_groups']),
            'vulnerability_confirmed': False, 'critical_impact_confirmed': False}


def review(ablation_bundle: Path, path_bundle: Path, triage_bundle: Path,
           source_map: Path, out: Path) -> dict:
    result, pin = obtain(ablation_bundle, path_bundle, triage_bundle, source_map)
    receipt = {
        'schema_version': 1, 'source_snapshot': snapshot(),
        'parent_pin_sha256': sha(canonical(pin)),
        'result_sha256': sha(canonical(result)),
    }
    write_new_bundle(out, {
        'parent-pin.json': canonical(pin),
        'common-mode.json': canonical(result),
        'receipt.json': canonical(receipt),
        'REVIEW.md': text_report(result),
    })
    return summary(result)


def verify(out: Path, ablation_bundle: Path, path_bundle: Path,
           triage_bundle: Path, source_map: Path) -> dict:
    require(out.is_dir() and not out.is_symlink(), 'BUNDLE_DIRECTORY')
    require({p.name for p in out.iterdir()} == FILES | {'COMPLETE.json'},
            'BUNDLE_FILES')
    marker = strict_json(read_artifact(out, 'COMPLETE.json'))
    require(type(marker) is dict and set(marker) == {'schema_version', 'sha256'} and
            type(marker['schema_version']) is int and marker['schema_version'] == 1 and
            type(marker['sha256']) is dict and set(marker['sha256']) == FILES,
            'MANIFEST_SCHEMA')
    stored = {name: read_artifact(out, name) for name in FILES}
    require(all(type(marker['sha256'][name]) is str and
                marker['sha256'][name] == sha(stored[name]) for name in FILES),
            'BUNDLE_TAMPERED')
    result, pin = obtain(ablation_bundle, path_bundle, triage_bundle, source_map)
    require(stored['parent-pin.json'] == canonical(pin), 'UPSTREAM_PIN_CHANGED')
    require(stored['common-mode.json'] == canonical(result), 'RESULT_CHANGED')
    require(stored['REVIEW.md'] == text_report(result), 'REPORT_CHANGED')
    receipt = strict_json(stored['receipt.json'])
    require(type(receipt) is dict and set(receipt) ==
            {'schema_version','source_snapshot','parent_pin_sha256','result_sha256'} and
            type(receipt['schema_version']) is int and receipt['schema_version'] == 1 and
            receipt['source_snapshot'] == snapshot() and
            receipt['parent_pin_sha256'] == sha(canonical(pin)) and
            receipt['result_sha256'] == sha(canonical(result)),
            'RECEIPT_MISMATCH')
    return summary(result)


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Offline same-bundle source alias analysis')
    sub = parser.add_subparsers(dest='command', required=True,
                                parser_class=PrivateArgumentParser)
    a = sub.add_parser('audit-common-evidence')
    a.add_argument('--ablation', type=Path, required=True)
    a.add_argument('--path-audit', type=Path, required=True)
    a.add_argument('--triage', type=Path, required=True)
    a.add_argument('--sources', type=Path, required=True)
    a.add_argument('--out', type=Path, required=True)
    b = sub.add_parser('verify-common-evidence')
    b.add_argument('--bundle', type=Path, required=True)
    b.add_argument('--ablation', type=Path, required=True)
    b.add_argument('--path-audit', type=Path, required=True)
    b.add_argument('--triage', type=Path, required=True)
    b.add_argument('--sources', type=Path, required=True)
    opts = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = (review(opts.ablation, opts.path_audit, opts.triage, opts.sources, opts.out)
                  if opts.command == 'audit-common-evidence' else
                  verify(opts.bundle, opts.ablation, opts.path_audit,
                         opts.triage, opts.sources))
        print(canonical(result).decode().strip())
        return 0
    except (ValueError, OSError, KeyError, TypeError, UnicodeError, OverflowError) as exc:
        code = exc.args[0] if type(exc) is CommonModeError else 'COMMON_MODE_REJECTED'
        print(code, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
