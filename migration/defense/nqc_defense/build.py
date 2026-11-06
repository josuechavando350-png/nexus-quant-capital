"""M76's archive subset: deterministic byte-for-byte ZIP artifacts and verification."""

import hashlib
import io
import zipfile

from .codec import Rejected, canonical, decode
from .files import relative_parts

MANIFEST = "CONTENTS.sha256.json"


def archive(entries):
    if not entries or len(entries) > 1000 or MANIFEST in entries:
        raise Rejected("archive_entries")
    if sum(len(v) for v in entries.values()) > 64 * 1024 * 1024:
        raise Rejected("archive_size")
    for name, value in entries.items():
        relative_parts(name)
        if not isinstance(value, bytes):
            raise Rejected("archive_bytes")
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(entries.items())}
    payloads = {**entries, MANIFEST: canonical(manifest)}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as stream:
        for name, data in sorted(payloads.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            stream.writestr(info, data)
    return output.getvalue()


def verify_archive(data):
    if len(data) > 65 * 1024 * 1024:
        raise Rejected("archive_size")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as stream:
            infos = stream.infolist()
            names = [item.filename for item in infos]
            if len(names) != len(set(names)) or not 2 <= len(names) <= 1001 or MANIFEST not in names:
                raise Rejected("archive_membership")
            if sum(i.file_size for i in infos) > 65 * 1024 * 1024:
                raise Rejected("archive_expanded_size")
            for item in infos:
                relative_parts(item.filename)
                if item.compress_type != zipfile.ZIP_STORED or item.is_dir() or item.file_size > 64 * 1024 * 1024:
                    raise Rejected("archive_format")
            manifest = decode(stream.read(MANIFEST))
            if type(manifest) is not dict or set(manifest) != set(names) - {MANIFEST}:
                raise Rejected("archive_manifest")
            for name, expected in manifest.items():
                if hashlib.sha256(stream.read(name)).hexdigest() != expected:
                    raise Rejected("archive_integrity")
            return manifest
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise Rejected("archive_invalid") from exc
