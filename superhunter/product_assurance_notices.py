"""Audit upstream notices for the exact three runtime wheel sets used by the owned checks."""
from collections import Counter
from email.parser import BytesHeaderParser
from io import BytesIO
from pathlib import Path
import subprocess
import sys
import tempfile
from zipfile import ZipFile

from .product_census_header import pinned
from .product_notices import LOCK_ROW, read_wheel, wheel_notices
from .product_owned_source_checks import LOCK, LOCK_SHA
from .product_reasoning import EvidenceError, python_name
from .product_notice_ranking import ISOLATE
from .product_review import ROOT, sha
from .product_score_comparison import ENGINES, lockfile
from .safe_io import MAX_BYTES, canonical, strict_json


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
            'classifiers': classifiers, 'requires_dist': sorted(meta.get_all('Requires-Dist', [])),
            'short_license': declaration if len(declaration) <= 150 and '\n' not in declaration else None,
            'license_field_sha256': sha(declaration.encode()) if declaration else None,
            'notices': {path: sha(content) for path, content in notices.items()}}


def resolve_profile(profile, distribution_name, wheelhouse, pins, versions):
    with tempfile.TemporaryDirectory(prefix='nqc-wheel-resolution-') as temp:
        root = Path(temp)
        approved = root/'wheels'
        approved.mkdir()
        for name, (filename, digest) in pins.items():
            raw = read_wheel(wheelhouse/filename)
            if sha(raw) != digest:
                raise EvidenceError('wheel changed before dependency resolution')
            (approved/filename).write_bytes(raw)
        command = [*ISOLATE, sys.executable, '-I', '-B', '-m', 'pip', '--isolated', '--disable-pip-version-check',
                   'install', '--ignore-installed', '--dry-run', '--no-cache-dir', '--no-index', '--only-binary=:all:',
                   '--find-links', 'wheels', '--report', 'report.json', distribution_name + '==' + versions[distribution_name]]
        options = {'cwd': root, 'env': {'HOME': temp, 'TMPDIR': temp, 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C.UTF-8'},
                   'capture_output': True, 'timeout': 90, 'stdin': subprocess.DEVNULL}
        subprocess.run(command, check=True, **options)
        report = strict_json((root/'report.json').read_bytes())
        selected = {}
        for item in report['install']:
            name = python_name(item['metadata']['name'])
            if name not in pins or name in selected:
                raise EvidenceError('resolver returned an unexpected package identity')
            version = item['metadata']['version']
            digest = item['download_info']['archive_info']['hashes']['sha256']
            if version != versions[name] or digest != pins[name][1]:
                raise EvidenceError('resolved artifact differs from verified wheel')
            selected[name] = {'version': version, 'sha256': digest}
        if distribution_name not in selected:
            raise EvidenceError('resolver omitted the root distribution')
        result = {'root': distribution_name, 'version': versions[distribution_name], 'pip': report['pip_version'],
                  'selected': sorted(selected), 'closure_sha256': sha(canonical(selected)),
                  'locked_outside_default_closure': sorted(set(pins) - set(selected))}
        if profile == 'bandit':
            (approved/pins['stevedore'][0]).unlink()
            rejected = subprocess.run(command, **options)
            if rejected.returncode == 0 or b'No matching distribution found for stevedore' not in rejected.stderr:
                raise EvidenceError('missing required wheel did not produce the expected resolution failure')
            result['negative_control'] = {'absent_required_distribution': 'stevedore', 'result': 'REJECTED'}
        return result


def audit(bandit, scorers):
    locks = {'bandit': (bandit, LOCK, LOCK_SHA)}
    locks.update({key: (scorers/(key + '-wheels'), lockfile(key), engine['lock']) for key, engine in ENGINES.items()})
    records, counts, resolutions = {}, Counter(), {}
    root_names = {'bandit': 'bandit', 'dspy': 'dspy', 'inspect': 'inspect-ai'}
    for profile, (folder, path, fingerprint) in locks.items():
        pins, versions = {}, {}
        for line in pinned(ROOT, path, fingerprint).decode('ascii').splitlines():
            match = LOCK_ROW.fullmatch(line)
            if not match:
                raise EvidenceError('invalid wheel notice pin')
            name, version, digest = match.groups()
            if name in pins:
                raise EvidenceError('duplicate notice pin in a framework')
            for candidate in sorted(folder.glob(name.replace('-', '_') + '-' + version + '-*.whl')):
                raw = read_wheel(candidate)
                if sha(raw) == digest:
                    break
            else:
                raise EvidenceError('missing verified distribution for ' + name)
            pins[name] = (candidate.name, digest)
            versions[name] = version
            if digest not in records:
                records[digest] = {**distribution(raw, name, version), 'used_by': []}
            records[digest]['used_by'].append(profile)
            counts[profile] += 1
        resolutions[profile] = resolve_profile(profile, root_names[profile], folder, pins, versions)
    rows = sorted(records.values(), key=lambda row: (row['package'], row['version']))
    return {'distributions': len(rows), 'by_profile': dict(counts),
            'with_spdx_expression': sum(bool(r['expression']) for r in rows),
            'default_dependency_resolution': resolutions,
            'notice_files': sum(len(r['notices']) for r in rows), 'rows_sha256': sha(canonical(rows)), 'rows': rows}
