"""Verify an explicit bounded archive collection without treating copies as trials."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import struct
import zipfile

from . import bundle_recovery as recovery, owned_capture, portable_copy as portable, quality
from .privacy import PrivateArgumentParser
from .safe_io import canonical, strict_json, write_new_bundle

PROFILE = 'private-preserved-archive-index-v1'
MANIFEST_PROFILE = 'explicit-preserved-archives-v1'
MAX_RECORDS = 64
MAX_MANIFEST_BYTES = 65_536
MAX_TOTAL_BYTES = 512 * 1024**2
FILES = {'inputs.json', 'index.json', 'REVIEW.md', 'COMPLETE.json'}
PINS = {'preserved_source_digest', 'input_anchor', 'recovery_anchor', 'archive_anchor'}
LIMITS = {'independent_experiments_proved': False, 'producer_authenticated': False,
          'execution_authenticated': False, 'semantic_validation_performed': False,
          'original_current_state_checked': False, 'original_restored': False,
          'writer_idle_proved': False, 'power_loss_durability_proved': False}


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def _snapshot(source_digest: str) -> dict:
    owned_capture._digest(source_digest)
    snapshot = quality.source_snapshot()
    need(quality.sha(canonical(snapshot)) == source_digest, 'INDEX_SOURCE')
    return snapshot


def _read_manifest(path: Path) -> tuple[bytes, tuple]:
    portable._path(path, new=False)
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parent_info = os.fstat(parent)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_MANIFEST_BYTES, 'INDEX_MANIFEST_BYTES')
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                raw = stream.read(MAX_MANIFEST_BYTES + 1)
            identity = portable._identity(before)
            need(len(raw) == before.st_size and identity == portable._identity(os.fstat(fd)) ==
                 portable._identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)), 'INDEX_MANIFEST_CHANGED')
            current_parent = path.parent.stat()
            need((parent_info.st_dev, parent_info.st_ino) == (current_parent.st_dev, current_parent.st_ino),
                 'INDEX_MANIFEST_CHANGED')
        finally:
            os.close(fd)
    finally:
        os.close(parent)
    return raw, identity


def _manifest(raw: bytes, manifest_anchor: str) -> dict:
    owned_capture._digest(manifest_anchor)
    need(0 < len(raw) <= MAX_MANIFEST_BYTES and quality.sha(raw) == manifest_anchor, 'INDEX_MANIFEST_ANCHOR')
    value = strict_json(raw)
    need(set(value) == {'schema_version', 'profile', 'archives'} and
         type(value['schema_version']) is int and value['schema_version'] == 1 and
         value['profile'] == MANIFEST_PROFILE and raw == canonical(value), 'INDEX_MANIFEST_SCHEMA')
    records = value['archives']
    need(type(records) is list and 1 <= len(records) <= MAX_RECORDS, 'INDEX_RECORD_LIMIT')
    ids = set(); names = set()
    for row in records:
        need(type(row) is dict and set(row) == {'id', 'file'} | PINS, 'INDEX_RECORD_SCHEMA')
        need(type(row['id']) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', row['id']) is not None,
             'INDEX_RECORD_ID')
        need(type(row['file']) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.zip', row['file']) is not None,
             'INDEX_RECORD_FILE')
        need(row['id'] not in ids and row['file'] not in names, 'INDEX_DUPLICATE_RECORD')
        for name in PINS: owned_capture._digest(row[name])
        ids.add(row['id']); names.add(row['file'])
    need(records == sorted(records, key=lambda row: row['id']), 'INDEX_RECORD_ORDER')
    return value


def _stamp(path: Path) -> tuple[str, tuple]:
    raw, identity = portable._read(path)
    return quality.sha(raw), identity


def _stable(root: Path, stamps: dict[str, tuple], snapshot: dict) -> None:
    for name, stamp in stamps.items():
        need(_stamp(root / name) == stamp, 'INDEX_ARCHIVES_CHANGED')
    need(quality.source_snapshot() == snapshot, 'INDEX_SOURCE_CHANGED')


def _collect(manifest: dict, root: Path, source_digest: str) -> tuple[list[dict], dict]:
    rows = []; stamps = {}; total = 0; verified = {}
    for entry in manifest['archives']:
        path = root / entry['file']
        stamp = _stamp(path)
        total += stamp[1][3]
        need(total <= MAX_TOTAL_BYTES, 'INDEX_TOTAL_BYTES')
        need(stamp[0] == entry['archive_anchor'], 'INDEX_ARCHIVE_ANCHOR')
        # Reuse only within this call and for the entire pinned context. Every
        # alias still gets its own byte hash, identity, budget and final recheck.
        key = (source_digest, *(entry[name] for name in sorted(PINS)))
        if key not in verified:
            verified[key] = portable.verify(path, source_digest=source_digest, **{name: entry[name] for name in PINS})
        result = verified[key]
        need(_stamp(path) == stamp, 'INDEX_ARCHIVES_CHANGED')
        stamps[entry['file']] = stamp
        rows.append({**entry, 'archive_bytes': stamp[1][3],
                     'captured_input_state': result['captured_input_state'],
                     'observed_files': result['observed_files'], 'observed_bytes': result['observed_bytes']})
    return rows, stamps


def _groups(rows: list[dict], key: str) -> list[dict]:
    groups = {}
    for row in rows: groups.setdefault(row[key], []).append(row['id'])
    return [{'anchor': anchor, 'ids': sorted(ids)} for anchor, ids in sorted(groups.items())]


def _report(rows: list[dict], manifest_anchor: str, index_source_digest: str) -> dict:
    archives = _groups(rows, 'archive_anchor'); inputs = _groups(rows, 'input_anchor')
    unique = {row['archive_anchor']: row for row in rows}
    complete = sum(row['captured_input_state'] == 'BUNDLE_BYTES_COMPLETE' for row in unique.values())
    counts = {'entries': len(rows), 'unique_archives': len(archives), 'unique_input_inventories': len(inputs),
              'duplicate_archive_entries': len(rows) - len(archives),
              'complete_unique_archives': complete, 'incomplete_unique_archives': len(unique) - complete,
              'listed_archive_bytes': sum(row['archive_bytes'] for row in rows),
              'unique_archive_bytes': sum(row['archive_bytes'] for row in unique.values())}
    return {'schema_version': 1, 'profile': PROFILE, 'index_source_digest': index_source_digest,
            'manifest_anchor': manifest_anchor, 'state': 'ARCHIVE_COLLECTION_CHECKED',
            'counts': counts, 'archives': rows, 'archive_groups': archives, 'input_groups': inputs,
            'limitations': dict(LIMITS)}


def render(report: dict) -> bytes:
    c = report['counts']
    return (f"# Índice privado de archivos preservados\n\nEntradas: {c['entries']}. "
            f"Archivos ZIP distintos: {c['unique_archives']}. "
            f"Inventarios originales distintos: {c['unique_input_inventories']}.\n"
            f"Entradas duplicadas: {c['duplicate_archive_entries']}. "
            f"Archivos con captura completa: {c['complete_unique_archives']}; "
            f"con captura incompleta o inválida: {c['incomplete_unique_archives']}.\n\n"
            'Cada archivo se verificó contra anclas externas explícitas. Los duplicados permanecen visibles.\n'
            'Archivos o inventarios distintos no demuestran experimentos independientes.\n'
            'El índice no autentica productores, ejecuciones, fechas, semántica ni durabilidad.\n'
            'No repara originales, no ejecuta contenido y no autoriza purgas.\n').encode()


def _saved(bundle: Path, index_anchor: str) -> tuple[dict[str, bytes], dict]:
    owned_capture._digest(index_anchor)
    raw, identities = recovery._capture(bundle)
    need(set(raw) == FILES, 'INDEX_BUNDLE_INVENTORY')
    marker = canonical({'schema_version': 1, 'sha256': {name: quality.sha(value) for name, value in raw.items()
                                                     if name != 'COMPLETE.json'}})
    need(raw['COMPLETE.json'] == marker and quality.sha(marker) == index_anchor, 'INDEX_BUNDLE_ANCHOR')
    return raw, identities


def _result(report: dict, index_anchor: str, source_digest: str, *, built: bool) -> dict:
    return {'state': 'PRESERVED_INDEX_BUILT' if built else 'PRESERVED_INDEX_VERIFIED',
            'profile': PROFILE, 'source_digest': source_digest, 'index_source_digest': report['index_source_digest'],
            'manifest_anchor': report['manifest_anchor'], 'index_anchor': index_anchor,
            'counts': report['counts'], **LIMITS}


def build(manifest: Path, archive_root: Path, out: Path, *, source_digest: str, manifest_anchor: str) -> dict:
    snapshot = _snapshot(source_digest)
    raw, identity = _read_manifest(manifest); value = _manifest(raw, manifest_anchor)
    owned_capture._path(out, new=True)
    need(not manifest.resolve().is_relative_to(out.resolve()), 'INDEX_OUTPUT_OVERLAP')
    for entry in value['archives']:
        need(not (archive_root / entry['file']).resolve().is_relative_to(out.resolve()), 'INDEX_OUTPUT_OVERLAP')
    rows, stamps = _collect(value, archive_root, source_digest)
    report = _report(rows, manifest_anchor, source_digest)
    payload = {'inputs.json': raw, 'index.json': canonical(report), 'REVIEW.md': render(report)}
    _stable(archive_root, stamps, snapshot)
    need(_read_manifest(manifest) == (raw, identity), 'INDEX_MANIFEST_CHANGED')
    write_new_bundle(out, payload)
    marker = canonical({'schema_version': 1, 'sha256': {name: quality.sha(data) for name, data in payload.items()}})
    index_anchor = quality.sha(marker)
    saved, unused = _saved(out, index_anchor)
    need(saved == {**payload, 'COMPLETE.json': marker}, 'INDEX_OUTPUT_CHANGED')
    _stable(archive_root, stamps, snapshot)
    need(_read_manifest(manifest) == (raw, identity), 'INDEX_MANIFEST_CHANGED_AFTER_WRITE')
    return _result(report, index_anchor, source_digest, built=True)


def verify(bundle: Path, archive_root: Path, *, source_digest: str, manifest_anchor: str,
           index_anchor: str, index_source_digest: str | None = None) -> dict:
    snapshot = _snapshot(source_digest)
    producer = source_digest if index_source_digest is None else index_source_digest
    owned_capture._digest(producer)
    saved, identities = _saved(bundle, index_anchor)
    manifest = _manifest(saved['inputs.json'], manifest_anchor)
    rows, stamps = _collect(manifest, archive_root, source_digest)
    report = _report(rows, manifest_anchor, producer)
    need(saved['index.json'] == canonical(report) and saved['REVIEW.md'] == render(report), 'INDEX_CONTENT')
    _stable(archive_root, stamps, snapshot)
    need(_saved(bundle, index_anchor) == (saved, identities), 'INDEX_BUNDLE_CHANGED')
    return _result(report, index_anchor, source_digest, built=False)


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Build or verify an explicit local archive index')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('index-preserved-archives'); check = sub.add_parser('verify-preserved-index')
    for command in (make, check):
        command.add_argument('--source-digest', required=True)
        command.add_argument('--manifest-anchor', required=True)
        command.add_argument('--archive-root', type=Path, required=True)
    make.add_argument('--manifest', type=Path, required=True); make.add_argument('--out', type=Path, required=True)
    check.add_argument('--bundle', type=Path, required=True); check.add_argument('--index-anchor', required=True)
    check.add_argument('--index-source-digest')
    args = vars(parser.parse_args(argv)); command = args.pop('command')
    try:
        result = build(**args) if command == 'index-preserved-archives' else verify(**args)
        print(json.dumps(result, sort_keys=True))
        return 0 if result['counts']['incomplete_unique_archives'] == 0 else 1
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError,
            zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, NotImplementedError, EOFError, struct.error):
        print(json.dumps({'state': 'PRESERVED_INDEX_REJECTED'})); return 2


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
