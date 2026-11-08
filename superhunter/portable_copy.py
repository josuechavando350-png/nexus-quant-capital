"""Bounded private ZIP transport for a preserved copy, without extraction.

Accept only this deterministic ZIP_STORED profile. This is not a general ZIP
importer, publication tool, encryption layer or restoration/execution service.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import re
import stat
import struct
import zipfile

from . import bundle_recovery as recovery, owned_capture, preserved_copy, quality
from .privacy import PrivateArgumentParser
from .safe_io import MAX_BYTES, canonical

PROFILE = 'private-preserved-copy-zip-stored-v1'
MAX_ENTRIES = recovery.MAX_FILES + 3
MAX_PACKAGE_BYTES = recovery.MAX_TOTAL_BYTES + MAX_BYTES
MAX_ARCHIVE_BYTES = MAX_PACKAGE_BYTES + 131_072
STAMP = (1980, 1, 1, 0, 0, 0)


def need(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def _name(name: str) -> bool:
    return type(name) is str and (name in recovery.BASE_FILES | {'COMPLETE.json'} or
                                  re.fullmatch(r'observed-[0-9]{3}\.bin', name) is not None)


def _snapshot(source_digest: str) -> dict:
    snapshot = quality.source_snapshot()
    need(quality.sha(canonical(snapshot)) == source_digest, 'ARCHIVE_SOURCE')
    return snapshot


def _anchors(source_digest: str, input_anchor: str, recovery_anchor: str,
             preserved_source_digest: str | None = None) -> dict:
    for value in (source_digest, input_anchor, recovery_anchor): owned_capture._digest(value)
    preserved = source_digest if preserved_source_digest is None else preserved_source_digest
    owned_capture._digest(preserved)
    return {'source_digest': preserved, 'input_anchor': input_anchor, 'recovery_anchor': recovery_anchor}


def _encode(saved: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for name, raw in sorted(saved.items()):
            item = zipfile.ZipInfo(name, date_time=STAMP)
            item.create_system = 3; item.external_attr = (stat.S_IFREG | 0o600) << 16
            item.compress_type = zipfile.ZIP_STORED
            archive.writestr(item, raw)
    value = out.getvalue(); need(len(value) <= MAX_ARCHIVE_BYTES, 'ARCHIVE_BYTES')
    return value


def _decode(raw: bytes) -> dict[str, bytes]:
    need(22 <= len(raw) <= MAX_ARCHIVE_BYTES, 'ARCHIVE_BYTES')
    # Bound the directory BEFORE ZipFile allocates an entry list. No ZIP64,
    # disk splitting, comments, suffixes or unbounded central-directory records.
    signature, disk, start_disk, here, entries, size, offset, comment = struct.unpack('<4s4H2LH', raw[-22:])
    need(signature == b'PK\x05\x06' and disk == start_disk == comment == 0 and here == entries and
         3 <= entries <= MAX_ENTRIES and 0 < size <= MAX_ENTRIES * 78 and
         offset + size + 22 == len(raw), 'ARCHIVE_DIRECTORY')
    saved = {}; total = 0
    with zipfile.ZipFile(io.BytesIO(raw), 'r', allowZip64=False) as archive:
        items = archive.infolist(); need(len(items) == entries, 'ARCHIVE_INVENTORY')
        for item in items:
            need(_name(item.filename) and item.orig_filename == item.filename and item.filename not in saved,
                 'ARCHIVE_INVENTORY')
            need(item.compress_type == zipfile.ZIP_STORED and item.compress_size == item.file_size and
                 item.flag_bits == 0 and item.create_system == 3 and item.date_time == STAMP and
                 item.external_attr == (stat.S_IFREG | 0o600) << 16 and not item.extra and not item.comment and
                 0 <= item.file_size <= MAX_BYTES, 'ARCHIVE_ENTRY')
            total += item.file_size; need(total <= MAX_PACKAGE_BYTES, 'ARCHIVE_TOTAL_BYTES')
            # ZIP_STORED only; bounded before read; no extraction or decompression.
            with archive.open(item) as stream:
                value = stream.read(MAX_BYTES + 1)
            need(len(value) == item.file_size, 'ARCHIVE_ENTRY_BYTES'); saved[item.filename] = value
    need(recovery.BASE_FILES | {'COMPLETE.json'} <= set(saved), 'ARCHIVE_INVENTORY')
    marker = {'schema_version': 1, 'sha256': {name: quality.sha(value) for name, value in saved.items()
                                          if name != 'COMPLETE.json'}}
    need(saved['COMPLETE.json'] == canonical(marker), 'ARCHIVE_MANIFEST')
    need(_encode(saved) == raw, 'ARCHIVE_NONCANONICAL')
    return saved


def _path(path: Path, *, new: bool) -> None:
    need(not path.resolve().is_relative_to(owned_capture.ROOT) and
         not owned_capture.ROOT.is_relative_to(path.resolve()), 'ARCHIVE_REPOSITORY_OVERLAP')
    for candidate in (path.absolute(), *path.absolute().parents):
        need(not candidate.is_symlink(), 'ARCHIVE_SYMLINK')
    need(path.parent.is_dir(), 'ARCHIVE_PARENT_DIRECTORY')
    need(not path.exists() if new else path.is_file(), 'ARCHIVE_NEW_FILE' if new else 'ARCHIVE_FILE')


def _identity(info) -> tuple:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read(path: Path) -> tuple[bytes, tuple]:
    _path(path, new=False)
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parent_identity = os.fstat(parent)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and 22 <= before.st_size <= MAX_ARCHIVE_BYTES, 'ARCHIVE_BYTES')
            with os.fdopen(fd, 'rb', closefd=False) as stream: raw = stream.read(MAX_ARCHIVE_BYTES + 1)
            need(len(raw) == before.st_size and _identity(before) == _identity(os.fstat(fd)) ==
                 _identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)), 'ARCHIVE_CHANGED')
            current_parent = path.parent.stat()
            need((parent_identity.st_dev, parent_identity.st_ino) ==
                 (current_parent.st_dev, current_parent.st_ino), 'ARCHIVE_CHANGED')
        finally:
            os.close(fd)
    finally:
        os.close(parent)
    return raw, _identity(before)


def _result(result: dict, archive_anchor: str, source_digest: str, *, exported: bool) -> dict:
    return {**result, 'state': 'PRESERVED_ARCHIVE_EXPORTED' if exported else 'PRESERVED_ARCHIVE_VERIFIED',
            'source_digest': source_digest, 'preserved_source_digest': result['source_digest'],
            'profile': PROFILE, 'archive_anchor': archive_anchor, 'private_original_bytes_included': True,
            'encrypted': False, 'redacted': False, 'source_bundle_current_state_checked': exported}


def verify(archive: Path, *, source_digest: str, input_anchor: str, recovery_anchor: str,
           archive_anchor: str, preserved_source_digest: str | None = None) -> dict:
    args = _anchors(source_digest, input_anchor, recovery_anchor, preserved_source_digest)
    owned_capture._digest(archive_anchor)
    snapshot = _snapshot(source_digest); raw, identity = _read(archive)
    need(quality.sha(raw) == archive_anchor, 'ARCHIVE_ANCHOR')
    result = preserved_copy._verify_saved(_decode(raw), **args)
    need(_read(archive) == (raw, identity) and quality.source_snapshot() == snapshot, 'ARCHIVE_EVIDENCE_CHANGED')
    return _result(result, archive_anchor, source_digest, exported=False)


def export(bundle: Path, out: Path, *, source_digest: str, input_anchor: str, recovery_anchor: str,
           include_private_bytes: bool = False, preserved_source_digest: str | None = None) -> dict:
    need(include_private_bytes is True, 'ARCHIVE_PRIVATE_BYTES_ACK_REQUIRED')
    args = _anchors(source_digest, input_anchor, recovery_anchor, preserved_source_digest)
    _path(out, new=True)
    need(not out.resolve().is_relative_to(bundle.resolve()), 'ARCHIVE_OUTPUT_OVERLAP')
    snapshot = _snapshot(source_digest); saved = recovery._read_recovery(bundle)
    result = preserved_copy._verify_saved(saved, **args); raw = _encode(saved)
    need(recovery._read_recovery(bundle) == saved and quality.source_snapshot() == snapshot,
         'ARCHIVE_SOURCE_CHANGED')
    parent = os.open(out.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(out.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as stream:
            need(stream.write(raw) == len(raw), 'ARCHIVE_SHORT_WRITE'); stream.flush(); os.fsync(stream.fileno())
        os.fsync(parent)
    finally:
        os.close(parent)
    archive_anchor = quality.sha(raw)
    verify(out, source_digest=source_digest, input_anchor=input_anchor, recovery_anchor=recovery_anchor,
           preserved_source_digest=args['source_digest'], archive_anchor=archive_anchor)
    need(recovery._read_recovery(bundle) == saved and quality.source_snapshot() == snapshot,
         'ARCHIVE_SOURCE_CHANGED_AFTER_WRITE')
    return _result(result, archive_anchor, source_digest, exported=True)


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Export or verify a private preserved-copy archive')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('export-preserved-copy'); check = sub.add_parser('verify-preserved-archive')
    for command in (make, check):
        command.add_argument('--source-digest', required=True)
        command.add_argument('--input-anchor', required=True)
        command.add_argument('--recovery-anchor', required=True)
        command.add_argument('--preserved-source-digest')
    make.add_argument('--bundle', type=Path, required=True); make.add_argument('--out', type=Path, required=True)
    make.add_argument('--include-private-bytes', action='store_true')
    check.add_argument('--archive', type=Path, required=True); check.add_argument('--archive-anchor', required=True)
    args = vars(parser.parse_args(argv)); command = args.pop('command')
    try:
        result = export(**args) if command == 'export-preserved-copy' else verify(**args)
        print(json.dumps(result, sort_keys=True))
        return 0 if result['captured_input_state'] == 'BUNDLE_BYTES_COMPLETE' else 1
    except (OSError, ValueError, TypeError, KeyError, RecursionError, OverflowError,
            zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, NotImplementedError, EOFError, struct.error):
        print(json.dumps({'state': 'PRESERVED_ARCHIVE_REJECTED'})); return 2


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
