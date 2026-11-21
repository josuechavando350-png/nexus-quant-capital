"""Native, network-isolated license observations over the verified NQC inventory."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import tomllib

from . import product_cdxgen, product_review
from .product_reasoning import EvidenceError
from .safe_io import MAX_BYTES, read_artifact, strict_json

SCAN_SHA = '638adcd0af576d1f4d5b64dde228724b3ca4fdee2c4de20d88e4356be353f027'
DENY_SHA = '8ba0f5bf9771837ec22538dee295ddf460a9c6887c14305ed9a741ea6d969d63'
REGISTRY = 'registry+https://github.com/rust-lang/crates.io-index'
ISOLATE = ['/usr/bin/unshare', '--user', '--map-current-user', '--net']


def scan_result(report, notices):
    header, = report['headers']
    if (header['tool_name'], header['tool_version']) != ('scancode-toolkit', '32.5.0') or header['errors']:
        raise EvidenceError('ScanCode version or run errors')
    results = {}
    for row in report['files']:
        if row['scan_errors']:
            raise EvidenceError('ScanCode reported a resource error')
        if row['type'] == 'directory' and row['path'] == 'notices':
            continue
        name = row['name']
        if (name not in notices or name in results or row['type'] != 'file'
                or row['path'] != 'notices/' + name or row['sha256'] != product_review.sha(notices[name])):
            raise EvidenceError('ScanCode input differs from pinned notice')
        matches = []
        lines = len(notices[name].splitlines())
        for detection in row['license_detections']:
            for m in detection['matches']:
                if m['from_file'] != row['path'] or not 1 <= m['start_line'] <= m['end_line'] <= lines:
                    raise EvidenceError('ScanCode match outside its notice')
                matches.append({k: m[k] for k in ('license_expression_spdx', 'rule_identifier', 'start_line', 'end_line')})
        expression = row['detected_license_expression_spdx']
        if bool(expression) != bool(matches):
            raise EvidenceError('ScanCode expression and match evidence disagree')
        results[name] = {'sha256': row['sha256'], 'detected_expression': expression, 'matches': matches}
    if results.keys() != notices.keys():
        raise EvidenceError('incomplete ScanCode coverage')
    return {'version': '32.5.0', 'release_sha256': SCAN_SHA, 'notices': results}


def scan(release, notices):
    with tempfile.TemporaryDirectory(prefix='nqc-scancode-') as temp:
        work = Path(temp)
        package = work/'release.tar.gz'
        product_review.copy_release('ScanCode', release, package, SCAN_SHA, limit=256 * 1024**2, executable=False)
        with tarfile.open(package, 'r:gz') as archive:
            archive.extractall(work, filter='data')
        executable = work/'scancode-toolkit-v32.5.0/scancode'
        folder = work/'notices'
        folder.mkdir()
        for name, data in notices.items():
            (folder/name).write_bytes(data)
        subprocess.run([*ISOLATE, str(executable.resolve(strict=True)), '--license', '--info', '--processes', '1',
                        '--json', str(work/'scan.json'), str(folder)], cwd=executable.parent,
                       env={'HOME': temp, 'PATH': str(Path(sys.executable).parent) + ':/usr/bin:/bin',
                            'PIP_NO_INDEX': '1', 'PYTHONDONTWRITEBYTECODE': '1'},
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                       timeout=300, check=True)
        return scan_result(strict_json(read_artifact(work, 'scan.json')), notices)


def registry_license(pkg, cache):
    name, version = pkg['name'], pkg['version']
    stem = f'{name}-{version}'
    files = sorted(cache.glob('*/' + stem + '.crate'))
    for path in files:
        raw = read_artifact(path.parent, path.name)
        if product_review.sha(raw) == pkg['checksum']:
            break
    else:
        raise EvidenceError('missing checksum-matched crate archive for ' + name)
    with tarfile.open(fileobj=BytesIO(raw), mode='r:gz') as archive:
        member = archive.getmember(stem + '/Cargo.toml')
        if not member.isfile() or member.size > MAX_BYTES:
            raise EvidenceError('invalid registry manifest')
        manifest = tomllib.load(archive.extractfile(member))['package']
    if (manifest['name'], manifest['version']) != (name, version):
        raise EvidenceError('registry manifest identity mismatch')
    return manifest['license']


def alternatives(expression):
    # The pinned workspace uses only identifiers, OR and Cargo's historical slash syntax.
    if expression is None:
        return []
    parts = re.split(r'\s+OR\s+|/', expression)
    if not all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+-]*', part) for part in parts):
        raise EvidenceError('unsupported license expression in pinned Cargo inventory')
    return sorted(set(parts))


def cargo_result(report, inputs, workspace, cache):
    lock = inputs['nqc-census/Cargo.lock']
    ws = tomllib.loads(inputs['nqc-census/Cargo.toml'].decode())['workspace']
    members = {}
    for member in ws['members']:
        pkg = tomllib.loads(inputs[f'nqc-census/{member}/Cargo.toml'].decode())['package']
        members[pkg['name']] = (member, pkg)
    expected = {}
    rows = []
    for pkg in tomllib.loads(lock.decode())['package']:
        name, version = pkg['name'], pkg['version']
        if 'source' in pkg:
            if pkg['source'] != REGISTRY:
                raise EvidenceError('unsupported Cargo source')
            source = REGISTRY
            expression = registry_license(pkg, cache)
        else:
            member, local = members[name]
            source = 'path+' + (workspace/member).as_uri()
            expression = local.get('license')
            if expression == {'workspace': True}:
                expression = ws['package']['license']
            if 'license-file' in local:
                raise EvidenceError('license-file needs independent file verification')
        key = f'{name} {version} {source}'
        expected[key] = alternatives(expression)
        rows.append({'name': name, 'version': version, 'declared_expression': expression,
                     'licenses': expected[key], 'workspace_member': 'source' not in pkg})
    if expected != {key: sorted(row['licenses']) for key, row in report.items()}:
        raise EvidenceError('cargo-deny disagrees with locked package identities or licenses')
    return {'version': '0.22.0', 'binary_sha256': DENY_SHA, 'lock_sha256': product_review.sha(lock), 'packages': rows}


def check_cargo(executable, rust_bin, cargo_home, product):
    inputs = product_cdxgen.capture(product)
    workspace = product_review.ROOT/'nqc-census'
    cargo_home = cargo_home.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='nqc-cargo-deny-') as temp:
        binary = Path(temp)/'cargo-deny'
        product_review.copy_release('cargo-deny', executable, binary, DENY_SHA)
        env = {'HOME': temp, 'CARGO_HOME': str(cargo_home), 'CARGO_NET_OFFLINE': 'true',
               'CARGO_TARGET_DIR': temp + '/target', 'PATH': str(rust_bin.resolve(strict=True)) + ':/usr/bin:/bin'}
        run = subprocess.run([*ISOLATE, str(binary), '--manifest-path', str(workspace/'Cargo.toml'),
                              '--frozen', 'list', '--layout', 'crate', '--format', 'json'],
                             cwd=temp, env=env, stdin=subprocess.DEVNULL, capture_output=True,
                             check=True, timeout=120)
    result = cargo_result(strict_json(run.stdout), inputs, workspace, cargo_home/'registry/cache')
    if product_cdxgen.capture(product) != inputs:
        raise EvidenceError('workspace changed during license review')
    return result
