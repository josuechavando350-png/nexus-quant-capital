"""Read-only classification and byte salvage of bounded flat local bundles.

Never repair the input or synthesize its missing completion marker. A salvage
package's own COMPLETE describes only the new package, not the input's success.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat

from . import owned_capture, quality
from .privacy import PrivateArgumentParser
from .safe_io import PENDING_MARKER, canonical, read_artifact, strict_json, write_new_bundle

PROFILE = 'local-flat-bundle-byte-salvage-v1'
MAX_FILES = 128
MAX_TOTAL_BYTES = 32 * 1024**2
BASE_FILES = {'recovery.json', 'REVIEW.md'}
LIMITS = {'input_repaired': False, 'semantic_validation_performed': False,
          'producer_authenticated': False, 'execution_authenticated': False,
          'power_loss_durability_proved': False, 'writer_idle_proved': False}


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def _name(name: str) -> bool:
    return (type(name) is str and 0 < len(name) <= 255 and Path(name).name == name and
            name not in ('.', '..') and not any(c in name for c in ('\\', ':', '\0')))


def _identity(path: Path) -> tuple:
    info = path.lstat()
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _capture(root: Path) -> tuple[dict[str, bytes], dict]:
    owned_capture._path(root, new=False)
    original_root = _identity(root)
    raw = {}; identities = {}; total = 0
    for index, path in enumerate(root.iterdir()):
        need(index < MAX_FILES and _name(path.name), 'RECOVERY_INVENTORY')
        before = _identity(path)
        need(stat.S_ISREG(before[2]), 'RECOVERY_REGULAR_FILES_ONLY')
        value = read_artifact(root, path.name)
        after = _identity(path)
        need(after == before and len(value) == before[3], 'RECOVERY_INPUT_CHANGED')
        total += len(value); need(total <= MAX_TOTAL_BYTES, 'RECOVERY_TOTAL_BYTES')
        raw[path.name] = value; identities[path.name] = before
    need(_identity(root) == original_root and set(p.name for p in root.iterdir()) == set(raw), 'RECOVERY_INPUT_CHANGED')
    return dict(sorted(raw.items())), {'root': original_root, 'files': identities}


def _inventory(raw: dict[str, bytes]) -> list[dict]:
    return [{'name': name, 'bytes': len(value), 'sha256': quality.sha(value)} for name, value in sorted(raw.items())]


def anchor(raw: dict[str, bytes]) -> str:
    return quality.sha(canonical({'profile': PROFILE, 'files': _inventory(raw)}))


def _manifest(raw: bytes) -> dict[str, str]:
    value = strict_json(raw)
    need(set(value) == {'schema_version', 'sha256'} and type(value['schema_version']) is int and
         value['schema_version'] == 1, 'RECOVERY_MARKER_SCHEMA')
    hashes = value['sha256']
    need(type(hashes) is dict and 0 < len(hashes) <= MAX_FILES and
         all(_name(name) and name not in ('COMPLETE.json', PENDING_MARKER) and
             type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest) for name, digest in hashes.items()),
         'RECOVERY_MARKER_SCHEMA')
    need(raw == canonical(value), 'RECOVERY_MARKER_CANONICAL')
    return hashes


def classify(raw: dict[str, bytes]) -> dict:
    """Describe observed bytes; absence of COMPLETE cannot distinguish a live writer."""
    expected = None; mismatches = []; missing = []; extra = []
    if 'COMPLETE.json' not in raw:
        state = 'INCOMPLETE_NO_MARKER'
    else:
        try:
            expected = _manifest(raw['COMPLETE.json'])
        except (ValueError, TypeError, RecursionError):
            state = 'INVALID_MARKER'
        else:
            present = set(raw) - {'COMPLETE.json', PENDING_MARKER}
            missing = sorted(set(expected) - present); extra = sorted(present - set(expected))
            mismatches = sorted(name for name in set(expected) & present if quality.sha(raw[name]) != expected[name])
            if missing or extra or mismatches:
                state = 'CONTENT_MISMATCH'
            elif PENDING_MARKER in raw:
                state = 'COMMIT_CLEANUP_PENDING' if raw[PENDING_MARKER] == raw['COMPLETE.json'] else 'PENDING_MARKER_CONFLICT'
            else:
                state = 'BUNDLE_BYTES_COMPLETE'
    return {'state': state, 'marker_present': 'COMPLETE.json' in raw,
            'pending_marker_present': PENDING_MARKER in raw,
            'expected_payload_files': len(expected) if expected is not None else None,
            'missing_files': missing, 'unexpected_files': extra, 'mismatched_files': mismatches,
            'files_observed': len(raw), 'bytes_observed': sum(map(len, raw.values()))}


def inspect(source: Path) -> dict:
    raw, identities = _capture(source)
    result = {'schema_version': 1, 'profile': PROFILE, 'input_anchor': anchor(raw),
              'assessment': classify(raw), 'inventory': _inventory(raw), 'limitations': dict(LIMITS)}
    need(_capture(source) == (raw, identities), 'RECOVERY_INPUT_CHANGED')
    return result


def _report(raw: dict[str, bytes], source_digest: str) -> dict:
    return {'schema_version': 1, 'profile': PROFILE, 'status': 'INPUT_BYTES_PRESERVED',
            'source_digest': source_digest, 'input_anchor': anchor(raw), 'assessment': classify(raw),
            'mapping': [{'name': name, 'saved_as': f'observed-{index:03d}.bin',
                         'bytes': len(value), 'sha256': quality.sha(value)}
                        for index, (name, value) in enumerate(sorted(raw.items()))], 'limitations': dict(LIMITS)}


def render(result: dict) -> bytes:
    assessment = result['assessment']
    return (f"# Salvamento de bytes observados\n\nEstado del original: {assessment['state']}.\n"
            f"Archivos conservados: {assessment['files_observed']}; bytes: {assessment['bytes_observed']}.\n\n"
            'Se copian bytes a un expediente nuevo; el original no se repara ni se altera.\n'
            'El marcador COMPLETE de este salvamento describe solo la copia y su reporte.\n'
            'No completa el expediente original ni aprueba su contenido o ejecución.\n'
            'Sin marcador no se distingue un escritor activo de uno interrumpido.\n'
            'Dos lecturas estables no prueban inactividad, autenticidad ni resistencia a pérdida de energía.\n').encode()


def _separate(source: Path, out: Path, *, new: bool) -> None:
    owned_capture._path(source, new=False); owned_capture._path(out, new=new)
    a, b = source.resolve(), out.resolve()
    need(not a.is_relative_to(b) and not b.is_relative_to(a), 'RECOVERY_OVERLAP')


def preserve(source: Path, out: Path, *, source_digest: str, input_anchor: str) -> dict:
    owned_capture._digest(source_digest); owned_capture._digest(input_anchor)
    _separate(source, out, new=True)
    snapshot = quality.source_snapshot()
    need(quality.sha(canonical(snapshot)) == source_digest, 'RECOVERY_SOURCE')
    raw, identities = _capture(source)
    need(anchor(raw) == input_anchor, 'RECOVERY_INPUT_ANCHOR')
    result = _report(raw, source_digest)
    files = {row['saved_as']: raw[row['name']] for row in result['mapping']}
    need(_capture(source) == (raw, identities) and quality.source_snapshot() == snapshot, 'RECOVERY_INPUT_CHANGED')
    write_new_bundle(out, {**files, 'recovery.json': canonical(result), 'REVIEW.md': render(result)})
    need(_capture(source) == (raw, identities) and quality.source_snapshot() == snapshot, 'RECOVERY_INPUT_CHANGED_AFTER_WRITE')
    return {**result, 'recovery_anchor': quality.sha(read_artifact(out, 'COMPLETE.json'))}


def _read_recovery(root: Path) -> dict[str, bytes]:
    owned_capture._path(root, new=False)
    names = set()
    for index, item in enumerate(root.iterdir()):
        need(index < MAX_FILES + 3 and (item.name in BASE_FILES | {'COMPLETE.json'} or
             re.fullmatch(r'observed-[0-9]{3}\.bin', item.name)), 'RECOVERY_PACKAGE_INVENTORY')
        names.add(item.name)
    need(BASE_FILES | {'COMPLETE.json'} <= names, 'RECOVERY_PACKAGE_INVENTORY')
    raw = {name: read_artifact(root, name) for name in names}
    need(sum(map(len, raw.values())) <= MAX_TOTAL_BYTES + 2_000_000, 'RECOVERY_PACKAGE_BUDGET')
    marker = {'schema_version': 1, 'sha256': {name: quality.sha(raw[name]) for name in names - {'COMPLETE.json'}}}
    need(raw['COMPLETE.json'] == canonical(marker), 'RECOVERY_PACKAGE_MANIFEST')
    return raw


def verify(source: Path, bundle: Path, *, source_digest: str, input_anchor: str, recovery_anchor: str) -> dict:
    for digest in (source_digest, input_anchor, recovery_anchor): owned_capture._digest(digest)
    _separate(source, bundle, new=False)
    snapshot = quality.source_snapshot()
    need(quality.sha(canonical(snapshot)) == source_digest, 'RECOVERY_SOURCE')
    original, identities = _capture(source); saved = _read_recovery(bundle)
    need(anchor(original) == input_anchor and quality.sha(saved['COMPLETE.json']) == recovery_anchor, 'RECOVERY_ANCHOR')
    result = _report(original, source_digest)
    expected = {row['saved_as']: original[row['name']] for row in result['mapping']}
    expected.update({'recovery.json': canonical(result), 'REVIEW.md': render(result)})
    need({name: value for name, value in saved.items() if name != 'COMPLETE.json'} == expected, 'RECOVERY_PACKAGE_CONTENT')
    need(_capture(source) == (original, identities) and _read_recovery(bundle) == saved and
         quality.source_snapshot() == snapshot, 'RECOVERY_EVIDENCE_CHANGED')
    return {**result, 'recovery_anchor': recovery_anchor}


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Inspect and preserve bytes of an interrupted local flat bundle')
    sub = parser.add_subparsers(dest='command', required=True)
    scan = sub.add_parser('inspect-local-bundle'); make = sub.add_parser('preserve-local-bundle')
    check = sub.add_parser('verify-preserved-bundle')
    for command in (scan, make, check): command.add_argument('--source', type=Path, required=True)
    for command in (make, check):
        command.add_argument('--source-digest', required=True); command.add_argument('--input-anchor', required=True)
    make.add_argument('--out', type=Path, required=True)
    check.add_argument('--bundle', type=Path, required=True); check.add_argument('--recovery-anchor', required=True)
    args = vars(parser.parse_args(argv)); command = args.pop('command')
    try:
        result = inspect(**args) if command == 'inspect-local-bundle' else preserve(**args) if command == 'preserve-local-bundle' else verify(**args)
        print(json.dumps({'state': result['assessment']['state'], 'input_anchor': result['input_anchor'],
                          **({'recovery_anchor': result['recovery_anchor']} if 'recovery_anchor' in result else {})}, sort_keys=True))
        return 0 if result['assessment']['state'] == 'BUNDLE_BYTES_COMPLETE' else 1
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError):
        print(json.dumps({'state': 'RECOVERY_REJECTED'})); return 2


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
