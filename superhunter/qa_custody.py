"""Join current QA semantics, original worker bytes and external custody trust.

Read-only evidence verification. No key generation/signing, subprocess launch,
network, arbitrary targets or claim that signed receipts authenticate execution.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import custody, quality
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

PROFILE = 'owned-qa-custody-report-v1'
FILES = {'report.json', 'REVIEW.md'}
ROOT = Path(__file__).resolve().parent.parent
WORKER_FILES = {'receipt.json', 'tests.log'}
LIMITS = {'execution_authenticated': False, 'human_identity_verified': False,
          'trusted_timestamp': False, 'independent_producer_proved': False,
          'vulnerability_confirmed': False, 'platform_complete': False}


def need(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _names(root: Path, expected: set[str]) -> None:
    custody._regular_root(root)
    names = set()
    for index, path in enumerate(root.iterdir()):
        need(index < len(expected), 'QA_CUSTODY_INVENTORY')
        names.add(path.name)
    need(names == expected, 'QA_CUSTODY_INVENTORY')


def _capture(root: Path, files: set[str]) -> dict[str, bytes]:
    _names(root, files | {'COMPLETE.json'})
    values = {name: read_artifact(root, name) for name in sorted(files | {'COMPLETE.json'})}
    expected = {'schema_version': 1, 'sha256': {name: quality.sha(values[name]) for name in files}}
    need(canonical(strict_json(values['COMPLETE.json'])) == canonical(expected), 'QA_CUSTODY_MANIFEST')
    return values


def _separate(roots: tuple[Path, ...], trust: Path) -> None:
    for index, first in enumerate(roots):
        for second in roots[index+1:]:
            a, b = first.resolve(), second.resolve()
            need(not a.is_relative_to(b) and not b.is_relative_to(a), 'QA_CUSTODY_OVERLAPPING_INPUTS')
        need(not trust.resolve().is_relative_to(first.resolve()), 'QA_CUSTODY_EXTERNAL_TRUST_REQUIRED')
    custody._regular_root(trust.parent)


def collect(qa: Path, workers: Path, seal: Path, trust: Path, *, source_digest: str,
            qa_anchor: str, seal_anchor: str, case_id: str, producer_id: str) -> dict:
    for value in (source_digest, qa_anchor, seal_anchor):
        custody.hex_bytes(value, 32)
    custody.case_uuid(case_id); custody.producer(producer_id)
    _separate((qa, workers, seal), trust)
    snapshot = quality.source_snapshot()
    need(quality.sha(canonical(snapshot)) == source_digest, 'QA_CUSTODY_SOURCE')
    trust_bytes = read_artifact(trust.parent, trust.name)
    custody.validate_trust(strict_json(trust_bytes))
    qa_bytes, seal_bytes = _capture(qa, quality.FILES), _capture(seal, custody.SEAL_FILES)
    need(quality.sha(qa_bytes['COMPLETE.json']) == qa_anchor and
         quality.sha(seal_bytes['COMPLETE.json']) == seal_anchor, 'QA_CUSTODY_ANCHOR')
    signature = custody.verify_seal(qa, seal, trust, case_id=case_id, producer_id=producer_id)
    need(signature['signature_valid'] is True and signature['trusted_key_scope_matched'] is True,
         'QA_CUSTODY_SIGNATURE_REQUIRED')
    qa_result = quality.verify_bundle(qa)
    need(qa_result['status'] == 'LOCAL_QA_PASS' and qa_result['source_digest'] == source_digest,
         'QA_CUSTODY_QA_NOT_PASS')
    receipt = quality.expand_partition_receipt(strict_json(qa_bytes['receipt.json']), snapshot)
    partitions = receipt.get('partition_receipts')
    need(type(partitions) is list and len(partitions) == quality.PARTITION_COUNT,
         'QA_CUSTODY_PARTITIONED_QA_REQUIRED')
    expected_workers = {f'worker-{i}' for i in range(quality.PARTITION_COUNT)}
    _names(workers, expected_workers)
    saved, logs, counts = {}, [], []
    total = len(trust_bytes) + sum(map(len, qa_bytes.values())) + sum(map(len, seal_bytes.values()))
    for index, row in enumerate(partitions):
        need(type(row['partition_index']) is int and row['partition_index'] == index,
             'QA_CUSTODY_WORKER_ORDER')
        raw = _capture(workers/f'worker-{index}', WORKER_FILES)
        total += sum(map(len, raw.values()))
        need(total <= custody.MAX_TOTAL_BYTES, 'QA_CUSTODY_TOTAL_BYTES')
        need(canonical(strict_json(raw['receipt.json'])) == canonical(row), 'QA_CUSTODY_WORKER_MISMATCH')
        logs.append(f'=== FIXED QA PARTITION {index+1}/8 ===\n'.encode()+raw['tests.log'])
        saved[index] = raw
        counts.append({'partition_index': index, 'tests_run': row['tests_run'],
                       'receipt_sha256': quality.sha(raw['receipt.json']),
                       'log_sha256': quality.sha(raw['tests.log'])})
    need(b'\n'.join(logs) == qa_bytes['tests.log'], 'QA_CUSTODY_LOG_RECONSTRUCTION')
    result = {'schema_version': 1, 'profile': PROFILE, 'status': 'QA_RECEIPTS_AND_CUSTODY_VERIFIED',
              'source_digest': source_digest, 'case_id': case_id, 'producer_id': producer_id,
              'key_id': signature['key_id'], 'tests_run': qa_result['tests_run'],
              'workers': counts, 'qa_semantics_recomputed': True,
              'custody_signature_verified': True, 'aggregate_log_reconstructed': True,
              'anchors': {'qa_complete_sha256': qa_anchor, 'seal_complete_sha256': seal_anchor,
                          'trust_sha256': quality.sha(trust_bytes)},
              'limitations': dict(LIMITS)}
    need(_capture(qa, quality.FILES) == qa_bytes and _capture(seal, custody.SEAL_FILES) == seal_bytes,
         'QA_CUSTODY_EVIDENCE_CHANGED')
    _names(workers, expected_workers)
    for index, raw in saved.items():
        need(_capture(workers/f'worker-{index}', WORKER_FILES) == raw, 'QA_CUSTODY_WORKER_CHANGED')
    need(read_artifact(trust.parent, trust.name) == trust_bytes, 'QA_CUSTODY_TRUST_CHANGED')
    need(quality.source_snapshot() == snapshot, 'QA_CUSTODY_SOURCE_CHANGED')
    return result


def render(result: dict) -> bytes:
    return (f'# QA y custodia comprobados\n\n'
            f"Pruebas declaradas y revalidadas: {result['tests_run']}.\n"
            f"Recibos originales cotejados: {len(result['workers'])}.\n\n"
            'Se recalcularon las condiciones del QA, se verificó la firma con confianza\n'
            'externa al expediente y se reconstruyó el log agregado desde ocho originales.\n'
            'La firma atribuye custodia de bytes a la clave confiada para este caso.\n'
            'No autentica ejecución, identidad humana, tiempo, independencia de productor\n'
            'ni vulnerabilidades. No se ejecutaron pruebas o procesos desde este revisor.\n').encode()


def _output(out: Path, qa: Path, workers: Path, seal: Path, trust: Path, *, new: bool) -> None:
    resolved = out.resolve()
    need(not out.is_symlink() and not resolved.is_relative_to(ROOT) and
         (not new or not out.exists()), 'QA_CUSTODY_OUTPUT')
    for parent in out.absolute().parents:
        need(not parent.is_symlink(), 'QA_CUSTODY_OUTPUT_SYMLINK')
    for input_root in (qa, workers, seal):
        other = input_root.resolve()
        need(not resolved.is_relative_to(other) and not other.is_relative_to(resolved),
             'QA_CUSTODY_OUTPUT_OVERLAP')
    need(not trust.resolve().is_relative_to(resolved), 'QA_CUSTODY_TRUST_IN_OUTPUT')


def create(qa: Path, workers: Path, seal: Path, trust: Path, out: Path, **context) -> dict:
    _output(out, qa, workers, seal, trust, new=True)
    result = collect(qa, workers, seal, trust, **context)
    write_new_bundle(out, {'report.json': canonical(result), 'REVIEW.md': render(result)})
    return result


def verify(qa: Path, workers: Path, seal: Path, trust: Path, bundle: Path, *,
           report_anchor: str, **context) -> dict:
    custody.hex_bytes(report_anchor, 32)
    _output(bundle, qa, workers, seal, trust, new=False)
    raw = _capture(bundle, FILES)
    need(quality.sha(raw['COMPLETE.json']) == report_anchor, 'QA_CUSTODY_REPORT_ANCHOR')
    fresh = collect(qa, workers, seal, trust, **context)
    need(raw['report.json'] == canonical(fresh) and raw['REVIEW.md'] == render(fresh),
         'QA_CUSTODY_REPORT_MISMATCH')
    need(_capture(bundle, FILES) == raw, 'QA_CUSTODY_REPORT_CHANGED')
    return fresh


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Join local QA receipts with externally trusted custody')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('review-qa-custody')
    check = sub.add_parser('verify-qa-custody')
    for command in (make, check):
        for name in ('qa', 'workers', 'seal', 'trust'):
            command.add_argument('--'+name, required=True, type=Path)
        for name in ('source-digest', 'qa-anchor', 'seal-anchor', 'case-id', 'producer-id'):
            command.add_argument('--'+name, required=True)
    make.add_argument('--out', required=True, type=Path)
    check.add_argument('--bundle', required=True, type=Path)
    check.add_argument('--report-anchor', required=True)
    args = vars(parser.parse_args(argv)); command = args.pop('command')
    try:
        result = create(**args) if command == 'review-qa-custody' else verify(**args)
        print(json.dumps({key: result[key] for key in ('status', 'tests_run', 'custody_signature_verified')}))
        return 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        print(json.dumps({'status': 'QA_CUSTODY_REJECTED', 'custody_signature_verified': False}))
        return 2


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
