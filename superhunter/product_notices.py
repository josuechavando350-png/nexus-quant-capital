"""Read public license notices from the exact wheels linked to NQC's supply review."""
from __future__ import annotations

from email.parser import BytesHeaderParser
from io import BytesIO
import os
import re
import stat
from zipfile import BadZipFile, ZipFile

from .product_reasoning import EvidenceError, INPUTS, PIN, PROFILES, python_name
from .product_review import sha
from .safe_io import MAX_BYTES

LOCK_ROW = re.compile(r'([A-Za-z0-9_.-]+)==([A-Za-z0-9.+!_-]+) --hash=sha256:([a-f0-9]{64})')


def wheel_notices(raw, name, version):
    dist = name.replace('-', '_') + '-' + version + '.dist-info/'
    with ZipFile(BytesIO(raw)) as wheel:
        members = set(wheel.namelist())
        if len(members) != len(wheel.infolist()):
            raise EvidenceError('duplicate member in supply wheel')

        def read_member(path):
            if path not in members or wheel.getinfo(path).file_size > MAX_BYTES:
                raise EvidenceError('missing or oversized wheel documentation')
            return wheel.read(path)

        meta = BytesHeaderParser().parsebytes(read_member(dist + 'METADATA'))
        if python_name(meta.get('Name', '')) != name or meta.get('Version') != version:
            raise EvidenceError('wheel metadata disagrees with supply lock')
        paths = []
        for entry in meta.get_all('License-File', []):
            if any(part in ('', '.', '..') for part in entry.split('/')) or '\\' in entry:
                raise EvidenceError('invalid License-File entry')
            candidates = [p for p in (dist + 'licenses/' + entry, dist + entry) if p in members]
            if len(candidates) != 1 or candidates[0] in paths:
                raise EvidenceError('ambiguous or missing declared notice')
            paths.append(candidates[0])
        if not paths:
            paths = [dist + n for n in ('LICENSE', 'COPYING', 'NOTICE') if dist + n in members]
        if not paths:
            # PEP 639 layout can also occur in older wheels without a License-File header.
            paths = [p for p in members if p.startswith(dist + 'licenses/') and
                     p.rsplit('/', 1)[-1].split('.')[0].upper() in ('LICENSE', 'LICENCE', 'COPYING', 'NOTICE')]
        if not paths:
            raise EvidenceError('no public notice in wheel metadata')
        return meta.get('License-Expression'), {p: read_member(p) for p in sorted(paths)}


def read_wheel(path):
    limit = 64 * 1024**2
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise EvidenceError('expected a size-limited regular wheel')
        raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise EvidenceError('supply wheel exceeds size limit')
        return raw


def inspect_wheel(wheels, name, version, digest):
    prefix = name.replace('-', '_') + '-' + version + '-'
    for path in wheels:
        if path.name.startswith(prefix):
            raw = read_wheel(path)
            if sha(raw) == digest:
                break
    else:
        raise EvidenceError('missing digest-matched wheel for ' + name)
    try:
        expression, members = wheel_notices(raw, name, version)
    except BadZipFile as error:
        raise EvidenceError('invalid supply wheel archive') from error
    notices = {}
    records = []
    for index, (member, content) in enumerate(members.items(), start=1):
        filename = f'{name}-{version}-{index}.txt'
        notices[filename] = content
        records.append({'wheel_member': member, 'file': filename, 'sha256': sha(content)})
    return {'version': version, 'wheel_sha256': digest,
            'declared_license_expression': expression, 'notices': records}, notices


def collect(wheelhouse, lock):
    packages = {}
    notices = {}
    wheels = sorted(wheelhouse.glob('*.whl'))
    for line in lock.decode().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        match = LOCK_ROW.fullmatch(line)
        if not match:
            raise EvidenceError('unsupported supply wheel pin')
        name, version, digest = match.groups()
        name = python_name(name)
        if name in packages:
            raise EvidenceError('duplicate supply wheel pin')
        record, files = inspect_wheel(wheels, name, version, digest)
        packages[name] = record
        notices.update(files)
    if not packages:
        raise EvidenceError('empty supply wheel lock')
    return packages, notices


def collect_profiles(wheelhouse, inputs):
    """Keep every name/version/profile even when none of its pins specify a wheel digest."""
    distributions = {}
    for scope in PROFILES:
        for line in inputs[INPUTS[scope + '/requirements.txt']].decode().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            match = PIN.fullmatch(line)
            if not match:
                raise EvidenceError('unsupported profile requirement')
            key = (python_name(match[1]), match[2])
            record = distributions.setdefault(key, {'profiles': [], 'digest_sources': {}, 'notices': []})
            record['profiles'].append(scope)
            if '--hash=' in line:
                digest = LOCK_ROW.fullmatch(line)
                if not digest:
                    raise EvidenceError('unsupported profile digest')
                record['digest_sources'][scope] = digest[3]

    wheels = sorted(wheelhouse.glob('*.whl'))
    packages = {}
    notices = {}
    for (name, version), record in sorted(distributions.items()):
        digests = set(record['digest_sources'].values())
        if len(digests) > 1:
            raise EvidenceError('ambiguous wheel digest across profiles')
        record['version'] = version
        if digests:
            result, files = inspect_wheel(wheels, name, version, digests.pop())
            record.update(result, status='WHEEL_VERIFIED')
            notices.update(files)
        else:
            record['status'] = 'NO_DIGEST_IN_PRODUCT_PROFILES'
        packages.setdefault(name, []).append(record)
    return packages, notices
