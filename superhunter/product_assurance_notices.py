"""Audit upstream notices for the exact three runtime wheel sets used by the owned checks."""
from collections import Counter
from email.parser import BytesHeaderParser
from io import BytesIO
from zipfile import ZipFile

from .product_census_header import pinned
from .product_notices import LOCK_ROW, read_wheel, wheel_notices
from .product_owned_source_checks import LOCK, LOCK_SHA
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_score_comparison import ENGINES, lockfile
from .safe_io import MAX_BYTES, canonical


def distribution(raw, name, version):
    dist = name.replace('-', '_') + '-' + version + '.dist-info/'
    expression, notices = wheel_notices(raw, name, version)
    with ZipFile(BytesIO(raw)) as wheel:
        info = wheel.getinfo(dist + 'METADATA')
        if info.file_size > MAX_BYTES:
            raise EvidenceError('oversized package metadata')
        meta = BytesHeaderParser().parsebytes(wheel.read(info))
    classifiers = [value for value in meta.get_all('Classifier', []) if value.startswith('License ::')]
    declaration = (meta.get('License') or '').strip()
    return {'package': name, 'version': version, 'wheel_sha256': sha(raw), 'expression': expression,
            'classifiers': classifiers,
            'short_license': declaration if len(declaration) <= 150 and '\n' not in declaration else None,
            'license_field_sha256': sha(declaration.encode()) if declaration else None,
            'notices': {path: sha(content) for path, content in notices.items()}}


def audit(bandit, scorers):
    locks = {'bandit': (bandit, LOCK, LOCK_SHA)}
    locks.update({key: (scorers/(key + '-wheels'), lockfile(key), engine['lock']) for key, engine in ENGINES.items()})
    records, counts = {}, Counter()
    for profile, (folder, path, fingerprint) in locks.items():
        seen = set()
        for line in pinned(ROOT, path, fingerprint).decode('ascii').splitlines():
            match = LOCK_ROW.fullmatch(line)
            if not match:
                raise EvidenceError('invalid wheel notice pin')
            name, version, digest = match.groups()
            if name in seen:
                raise EvidenceError('duplicate notice pin in a framework')
            seen.add(name)
            for candidate in sorted(folder.glob(name.replace('-', '_') + '-' + version + '-*.whl')):
                raw = read_wheel(candidate)
                if sha(raw) == digest:
                    break
            else:
                raise EvidenceError('missing verified distribution for ' + name)
            if digest not in records:
                records[digest] = {**distribution(raw, name, version), 'used_by': []}
            records[digest]['used_by'].append(profile)
            counts[profile] += 1
    rows = sorted(records.values(), key=lambda row: (row['package'], row['version']))
    return {'distributions': len(rows), 'by_profile': dict(counts),
            'with_spdx_expression': sum(bool(r['expression']) for r in rows),
            'notice_files': sum(len(r['notices']) for r in rows), 'rows_sha256': sha(canonical(rows)), 'rows': rows}
