"""Verify saved bundle bytes against external anchors without the original.

Read-only verification of a recovery package, not restoration, source lookup,
producer authentication or a statement about the original's current condition.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import bundle_recovery as recovery, owned_capture, quality
from .privacy import PrivateArgumentParser
from .safe_io import MAX_BYTES, canonical, strict_json


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def _original_bytes(saved: dict[str, bytes]) -> dict[str, bytes]:
    report = strict_json(saved['recovery.json'])
    mapping = report.get('mapping')
    need(type(mapping) is list and len(mapping) <= recovery.MAX_FILES, 'COPY_MAPPING')
    original = {}; total = 0
    for index, row in enumerate(mapping):
        need(type(row) is dict and set(row) == {'name', 'saved_as', 'bytes', 'sha256'}, 'COPY_MAPPING')
        name, stored = row['name'], row['saved_as']
        need(recovery._name(name) and name not in original and
             stored == f'observed-{index:03d}.bin', 'COPY_MAPPING')
        need(type(row['bytes']) is int and 0 <= row['bytes'] <= MAX_BYTES, 'COPY_SIZE')
        owned_capture._digest(row['sha256'])
        need(stored in saved, 'COPY_FILE_MISSING')
        raw = saved[stored]
        need(len(raw) == row['bytes'] and quality.sha(raw) == row['sha256'], 'COPY_FILE_CHANGED')
        total += len(raw); need(total <= recovery.MAX_TOTAL_BYTES, 'COPY_TOTAL_BYTES')
        original[name] = raw
    return original


def verify(bundle: Path, *, source_digest: str, input_anchor: str, recovery_anchor: str) -> dict:
    """Reconstruct the observed inventory in memory; never access original paths."""
    for digest in (source_digest, input_anchor, recovery_anchor): owned_capture._digest(digest)
    snapshot = quality.source_snapshot()
    need(quality.sha(canonical(snapshot)) == source_digest, 'COPY_SOURCE')
    saved = recovery._read_recovery(bundle)
    need(quality.sha(saved['COMPLETE.json']) == recovery_anchor, 'COPY_RECOVERY_ANCHOR')
    original = _original_bytes(saved)
    need(recovery.anchor(original) == input_anchor, 'COPY_INPUT_ANCHOR')
    report = recovery._report(original, source_digest)
    expected = {row['saved_as']: original[row['name']] for row in report['mapping']}
    expected.update({'recovery.json': canonical(report), 'REVIEW.md': recovery.render(report)})
    need({name: value for name, value in saved.items() if name != 'COMPLETE.json'} == expected,
         'COPY_PACKAGE_CONTENT')
    need(recovery._read_recovery(bundle) == saved and quality.source_snapshot() == snapshot,
         'COPY_EVIDENCE_CHANGED')
    return {'state': 'PRESERVED_COPY_VERIFIED', 'captured_input_state': report['assessment']['state'],
            'source_digest': source_digest, 'input_anchor': input_anchor, 'recovery_anchor': recovery_anchor,
            'observed_files': len(original), 'observed_bytes': sum(map(len, original.values())),
            'original_current_state_checked': False, 'original_restored': False,
            'producer_authenticated': False, 'execution_authenticated': False,
            'semantic_validation_performed': False}


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Verify saved local bytes without accessing the original')
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--source-digest', required=True)
    parser.add_argument('--input-anchor', required=True)
    parser.add_argument('--recovery-anchor', required=True)
    args = vars(parser.parse_args(argv))
    try:
        result = verify(**args)
        print(json.dumps(result, sort_keys=True))
        return 0 if result['captured_input_state'] == 'BUNDLE_BYTES_COMPLETE' else 1
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        print(json.dumps({'state': 'PRESERVED_COPY_REJECTED'})); return 2


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
