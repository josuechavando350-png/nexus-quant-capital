"""Deterministic review-only retention of a verified explicit archive index."""
from __future__ import annotations

import json
from pathlib import Path
import struct
import zipfile

from . import bundle_recovery as recovery, owned_capture, preserved_index as index, quality
from .privacy import PrivateArgumentParser
from .safe_io import canonical, strict_json, write_new_bundle

PROFILE = 'preserved-archive-retention-review-v1'
POLICY_PROFILE = 'explicit-preserved-retention-v1'
FILES = {'policy.json', 'retention.json', 'REVIEW.md', 'COMPLETE.json'}
LIMITS = {**index.LIMITS, 'files_deleted': False, 'deletion_authorized': False,
          'backup_independence_proved': False, 'physical_disk_savings_proved': False,
          'timestamps_used_for_retention': False}


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def _policy(raw: bytes, policy_anchor: str, ids: set[str]) -> dict:
    owned_capture._digest(policy_anchor)
    need(0 < len(raw) <= index.MAX_MANIFEST_BYTES and quality.sha(raw) == policy_anchor, 'RETENTION_POLICY_ANCHOR')
    value = strict_json(raw)
    need(set(value) == {'schema_version', 'profile', 'minimum_copies_per_archive', 'retain_ids',
                        'maximum_retained_bytes', 'allow_review_of_incomplete_duplicates'} and
         type(value['schema_version']) is int and value['schema_version'] == 1 and
         value['profile'] == POLICY_PROFILE and raw == canonical(value), 'RETENTION_POLICY_SCHEMA')
    count, budget, holds = value['minimum_copies_per_archive'], value['maximum_retained_bytes'], value['retain_ids']
    need(type(count) is int and 1 <= count <= index.MAX_RECORDS, 'RETENTION_MINIMUM_COPIES')
    need(type(budget) is int and 1 <= budget <= index.MAX_TOTAL_BYTES, 'RETENTION_BUDGET')
    need(type(value['allow_review_of_incomplete_duplicates']) is bool, 'RETENTION_INCOMPLETE_POLICY')
    need(type(holds) is list and len(holds) <= index.MAX_RECORDS and
         all(type(item) is str and item in ids for item in holds) and
         holds == sorted(set(holds)), 'RETENTION_RETAIN_IDS')
    return value


def _decisions(rows: list[dict], policy: dict) -> tuple[list[dict], list[dict], dict]:
    """All distinct ZIP anchors are retained; only exact aliases can be reviewed."""
    groups = {}
    for row in rows: groups.setdefault(row['archive_anchor'], []).append(row)
    decisions = {}; shortfalls = []
    for anchor, group in sorted(groups.items()):
        group.sort(key=lambda row: row['id'])
        kept = set()
        for row in group:
            if row['id'] in policy['retain_ids']:
                decisions[row['id']] = 'RETAIN_EXPLICIT_ID'; kept.add(row['id'])
            elif row['captured_input_state'] != 'BUNDLE_BYTES_COMPLETE' and not policy['allow_review_of_incomplete_duplicates']:
                decisions[row['id']] = 'RETAIN_INCOMPLETE_CAPTURE'; kept.add(row['id'])
        for row in group:
            if len(kept) >= policy['minimum_copies_per_archive']: break
            if row['id'] not in kept:
                decisions[row['id']] = 'RETAIN_MINIMUM_COPIES'; kept.add(row['id'])
        for row in group:
            if row['id'] not in kept: decisions[row['id']] = 'REVIEW_EXACT_DUPLICATE'
        if len(group) < policy['minimum_copies_per_archive']:
            shortfalls.append({'archive_anchor': anchor, 'available_entries': len(group),
                               'required_entries': policy['minimum_copies_per_archive'],
                               'missing_entries': policy['minimum_copies_per_archive'] - len(group)})
    result = [{**{key: row[key] for key in ('id', 'archive_anchor', 'input_anchor', 'archive_bytes', 'captured_input_state')},
               'decision': decisions[row['id']]} for row in rows]
    retained = [row for row in result if row['decision'] != 'REVIEW_EXACT_DUPLICATE']
    review = [row for row in result if row['decision'] == 'REVIEW_EXACT_DUPLICATE']
    retained_bytes = sum(row['archive_bytes'] for row in retained)
    summary = {'listed_entries': len(rows), 'retained_entries': len(retained), 'reviewable_duplicate_entries': len(review),
               'retained_listed_bytes': retained_bytes, 'reviewable_listed_bytes': sum(row['archive_bytes'] for row in review),
               'distinct_archives_retained': len({row['archive_anchor'] for row in retained}),
               'distinct_input_inventories_retained': len({row['input_anchor'] for row in retained}),
               'missing_copy_entries': sum(row['missing_entries'] for row in shortfalls),
               'budget_excess_bytes': max(0, retained_bytes - policy['maximum_retained_bytes'])}
    return result, shortfalls, summary


def _report(index_report: dict, policy: dict, *, source_digest: str, index_anchor: str, policy_anchor: str) -> dict:
    rows, shortfalls, summary = _decisions(index_report['archives'], policy)
    satisfied = summary['missing_copy_entries'] == summary['budget_excess_bytes'] == 0
    return {'schema_version': 1, 'profile': PROFILE, 'retention_source_digest': source_digest,
            'index_source_digest': index_report['index_source_digest'], 'index_anchor': index_anchor,
            'manifest_anchor': index_report['manifest_anchor'], 'policy_anchor': policy_anchor,
            'state': 'RETENTION_REQUIREMENTS_SATISFIED' if satisfied else 'RETENTION_REQUIREMENTS_UNMET',
            'input_counts': index_report['counts'], 'summary': summary, 'decisions': rows,
            'copy_shortfalls': shortfalls, 'limitations': dict(LIMITS)}


def render(report: dict) -> bytes:
    s = report['summary']
    return (f"# Revisión de conservación de archivos\n\nEstado: {report['state']}.\n"
            f"Entradas a conservar: {s['retained_entries']}; duplicados exactos revisables: {s['reviewable_duplicate_entries']}.\n"
            f"Copias faltantes según política: {s['missing_copy_entries']}; exceso de bytes listados: {s['budget_excess_bytes']}.\n\n"
            'Cada ZIP distinto conserva al menos una entrada disponible. Una retención explícita siempre prevalece.\n'
            'Un presupuesto insuficiente queda incumplido; no elimina copias requeridas para aparentar cumplimiento.\n'
            'Las copias se cuentan por entradas declaradas, no por dispositivos, hosts ni respaldos independientes.\n'
            'No usa fechas ZIP, no borra archivos y no autoriza una purga. Los bytes listados no prueban ahorro físico.\n').encode()


def _collect(bundle: Path, archive_root: Path, raw_policy: bytes, *, source_digest: str, manifest_anchor: str,
             index_anchor: str, policy_anchor: str, index_source_digest: str | None,
             retention_source_digest: str) -> tuple[dict, dict, dict, tuple]:
    snapshot = index._snapshot(source_digest)
    saved, identities = index._saved(bundle, index_anchor)
    manifest = index._manifest(saved['inputs.json'], manifest_anchor)
    policy = _policy(raw_policy, policy_anchor, {row['id'] for row in manifest['archives']})
    stamps = {}; total = 0
    for row in manifest['archives']:
        stamp = index._stamp(archive_root / row['file']); total += stamp[1][3]
        need(total <= index.MAX_TOTAL_BYTES, 'RETENTION_TOTAL_BYTES')
        stamps[row['file']] = stamp
    index.verify(bundle, archive_root, source_digest=source_digest, manifest_anchor=manifest_anchor,
                 index_anchor=index_anchor, index_source_digest=index_source_digest)
    need(index._saved(bundle, index_anchor) == (saved, identities), 'RETENTION_INDEX_CHANGED')
    report = _report(strict_json(saved['index.json']), policy, source_digest=retention_source_digest,
                     index_anchor=index_anchor, policy_anchor=policy_anchor)
    index._stable(archive_root, stamps, snapshot)
    return report, stamps, snapshot, (saved, identities)


def _output(out: Path, bundle: Path, policy: Path | None, *, new: bool) -> None:
    owned_capture._path(out, new=new)
    a, b = out.resolve(), bundle.resolve()
    need(not a.is_relative_to(b) and not b.is_relative_to(a), 'RETENTION_OUTPUT_OVERLAP')
    if policy is not None:
        need(not policy.resolve().is_relative_to(a) and not policy.resolve().is_relative_to(b),
             'RETENTION_EXTERNAL_POLICY_REQUIRED')


def _saved(bundle: Path, report_anchor: str) -> tuple[dict[str, bytes], dict]:
    owned_capture._digest(report_anchor)
    raw, identities = recovery._capture(bundle)
    need(set(raw) == FILES, 'RETENTION_BUNDLE_INVENTORY')
    marker = canonical({'schema_version': 1, 'sha256': {name: quality.sha(value) for name, value in raw.items()
                                                     if name != 'COMPLETE.json'}})
    need(raw['COMPLETE.json'] == marker and quality.sha(marker) == report_anchor, 'RETENTION_REPORT_ANCHOR')
    return raw, identities


def _result(report: dict, report_anchor: str, source_digest: str, *, built: bool) -> dict:
    return {key: report[key] for key in ('profile', 'retention_source_digest', 'index_source_digest', 'index_anchor',
                                       'manifest_anchor', 'policy_anchor', 'state', 'input_counts', 'summary')} | {
        'operation': 'RETENTION_REVIEW_BUILT' if built else 'RETENTION_REVIEW_VERIFIED',
        'source_digest': source_digest, 'report_anchor': report_anchor, **LIMITS}


def create(bundle: Path, archive_root: Path, policy: Path, out: Path, *, source_digest: str,
           manifest_anchor: str, index_anchor: str, policy_anchor: str, index_source_digest: str | None = None) -> dict:
    _output(out, bundle, policy, new=True)
    raw, identity = index._read_manifest(policy)
    report, stamps, snapshot, saved_index = _collect(bundle, archive_root, raw, source_digest=source_digest,
        manifest_anchor=manifest_anchor, index_anchor=index_anchor, policy_anchor=policy_anchor,
        index_source_digest=index_source_digest, retention_source_digest=source_digest)
    need(index._read_manifest(policy) == (raw, identity), 'RETENTION_POLICY_CHANGED')
    payload = {'policy.json': raw, 'retention.json': canonical(report), 'REVIEW.md': render(report)}
    write_new_bundle(out, payload)
    marker = canonical({'schema_version': 1, 'sha256': {name: quality.sha(value) for name, value in payload.items()}})
    report_anchor = quality.sha(marker)
    saved, unused = _saved(out, report_anchor)
    need(saved == {**payload, 'COMPLETE.json': marker}, 'RETENTION_OUTPUT_CHANGED')
    index._stable(archive_root, stamps, snapshot)
    need(index._saved(bundle, index_anchor) == saved_index, 'RETENTION_INDEX_CHANGED')
    need(index._read_manifest(policy) == (raw, identity), 'RETENTION_POLICY_CHANGED_AFTER_WRITE')
    return _result(report, report_anchor, source_digest, built=True)


def verify(bundle: Path, archive_root: Path, report: Path, *, source_digest: str, manifest_anchor: str,
           index_anchor: str, policy_anchor: str, report_anchor: str, index_source_digest: str | None = None,
           retention_source_digest: str | None = None) -> dict:
    _output(report, bundle, None, new=False)
    producer = source_digest if retention_source_digest is None else retention_source_digest
    owned_capture._digest(producer)
    saved, identities = _saved(report, report_anchor)
    fresh, stamps, snapshot, saved_index = _collect(bundle, archive_root, saved['policy.json'], source_digest=source_digest,
        manifest_anchor=manifest_anchor, index_anchor=index_anchor, policy_anchor=policy_anchor,
        index_source_digest=index_source_digest, retention_source_digest=producer)
    need(saved['retention.json'] == canonical(fresh) and saved['REVIEW.md'] == render(fresh), 'RETENTION_CONTENT')
    index._stable(archive_root, stamps, snapshot)
    need(index._saved(bundle, index_anchor) == saved_index, 'RETENTION_INDEX_CHANGED')
    need(_saved(report, report_anchor) == (saved, identities), 'RETENTION_REPORT_CHANGED')
    return _result(fresh, report_anchor, source_digest, built=False)


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Review explicit retention requirements without deleting files')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('review-preserved-retention'); check = sub.add_parser('verify-preserved-retention')
    for command in (make, check):
        for name in ('bundle', 'archive-root'): command.add_argument('--' + name, type=Path, required=True)
        for name in ('source-digest', 'manifest-anchor', 'index-anchor', 'policy-anchor'):
            command.add_argument('--' + name, required=True)
        command.add_argument('--index-source-digest')
    make.add_argument('--policy', type=Path, required=True); make.add_argument('--out', type=Path, required=True)
    check.add_argument('--report', type=Path, required=True); check.add_argument('--report-anchor', required=True)
    check.add_argument('--retention-source-digest')
    args = vars(parser.parse_args(argv)); command = args.pop('command')
    try:
        result = create(**args) if command == 'review-preserved-retention' else verify(**args)
        print(json.dumps(result, sort_keys=True))
        return 0 if result['state'] == 'RETENTION_REQUIREMENTS_SATISFIED' and result['input_counts']['incomplete_unique_archives'] == 0 else 1
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError,
            zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, NotImplementedError, EOFError, struct.error):
        print(json.dumps({'state': 'PRESERVED_RETENTION_REJECTED'})); return 2


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
