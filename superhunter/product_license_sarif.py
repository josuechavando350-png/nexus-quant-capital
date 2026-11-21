"""Produce a local SARIF report of license evidence gaps and validate it with Microsoft's SDK."""
from __future__ import annotations

import base64
from collections import Counter
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
from zipfile import ZipFile

from . import product_cdxgen
from .product_reasoning import EvidenceError, INPUTS, PIN, python_name
from .product_review import copy_release, sha
from .safe_io import canonical, read_artifact, strict_json

SDK_SHA = 'ad12cf3955185ce31975ea47f0d5b54399c824d6f4aab1cb0de675fda7002478'
SDK_VERSION = '5.8.0+33e5e287d4136acf2b1358c6cee0671126d61e6c'
RUNTIME_SHA = 'eeeccf584ed7f114294eb8feec068f995573c9c2fe058294b5f46df46bbbd10c'
RULES = {'NQC1001': 'Workspace member has no declared license',
         'NQC1002': 'No profile supplies a wheel digest for this pin',
         'NQC1003': 'ScanCode returned no license match for this notice'}
DOCS = 'https://github.com/josuechavando350-png/nexus-quant-capital'


def findings(inputs, packages, profiles, detected, notices):
    rows = []
    manifests = {}
    for path, raw in inputs.items():
        if path.startswith('nqc-census/crates/') and path.endswith('/Cargo.toml'):
            data = tomllib.loads(raw.decode())['package']
            manifests[data['name']] = (path, raw)
    for entry in packages:
        if entry['workspace_member'] and entry['declared_expression'] is None:
            name = entry['name']
            path, raw = manifests[name]
            rows.append(('NQC1001', path, raw, 1, len(raw.splitlines()), name + ' has no declared license.'))
    for name, distributions in profiles.items():
        for record in distributions:
            if record['status'] != 'NO_DIGEST_IN_PRODUCT_PROFILES':
                continue
            version = record['version']
            for profile in record['profiles']:
                path = INPUTS[profile + '/requirements.txt']
                raw = inputs[path]
                matches = [number for number, line in enumerate(raw.decode().splitlines(), 1)
                           if (m := PIN.fullmatch(line.strip())) and (python_name(m[1]), m[2]) == (name, version)]
                if len(matches) != 1:
                    raise EvidenceError('missing or ambiguous Python pin in source')
                message = f'No declared NQC profile provides a SHA-256 wheel digest for {name} {version}.'
                rows.append(('NQC1002', path, raw, matches[0], matches[0], message))
    if detected.keys() != notices.keys():
        raise EvidenceError('SARIF notice inventory differs from ScanCode coverage')
    for filename, row in detected.items():
        raw = notices[filename]
        if sha(raw) != row['sha256']:
            raise EvidenceError('SARIF notice hash differs from ScanCode evidence')
        if not row['detected_expression']:
            rows.append(('NQC1003', 'notices/' + filename, raw, 1, max(1, len(raw.splitlines())),
                         'ScanCode returned no license match in this public notice.'))
    return sorted(rows, key=lambda r: (r[1], r[3], r[0]))


def render(rows):
    files = {}
    results = []
    for rule, uri, raw, first, last, message in rows:
        if uri not in files:
            try:
                contents = {'text': raw.decode('utf-8')}
            except UnicodeDecodeError:
                contents = {'binary': base64.b64encode(raw).decode('ascii')}
            files[uri] = (len(files), {'location': {'uri': uri}, 'length': len(raw),
                                       'hashes': {'sha-256': sha(raw)}, 'contents': contents})
        idx, artifact = files[uri]
        if artifact['hashes']['sha-256'] != sha(raw):
            raise EvidenceError('same SARIF artifact path has different input bytes')
        parts = raw.splitlines(keepends=True)
        if not 1 <= first <= last <= max(1, len(parts)):
            raise EvidenceError('SARIF region is outside its source')
        region = {'startLine': first, 'endLine': last, 'byteOffset': sum(map(len, parts[:first - 1])),
                  'byteLength': sum(map(len, parts[first - 1:last]))}
        location = {'artifactLocation': {'uri': uri, 'index': idx}, 'region': region}
        results.append({'ruleId': rule, 'level': 'warning', 'message': {'text': message},
                        'locations': [{'physicalLocation': location}]})
    driver = {'name': 'NQC license review', 'semanticVersion': '1.0.0', 'informationUri': DOCS,
              'rules': [{'id': key, 'shortDescription': {'text': text}} for key, text in RULES.items()]}
    return {'version': '2.1.0', '$schema': 'https://json.schemastore.org/sarif-2.1.0.json',
            'runs': [{'tool': {'driver': driver}, 'artifacts': [record for _, record in files.values()],
                      'results': results}]}


def validate(sdk, runtime, report):
    raw = canonical(report)
    with tempfile.TemporaryDirectory(prefix='nqc-license-sarif-') as temp:
        work = Path(temp)
        copy_release('SARIF SDK', sdk, work/'sdk.nupkg', SDK_SHA, executable=False)
        copy_release('.NET runtime', runtime, work/'runtime.tgz', RUNTIME_SHA, executable=False)
        with tarfile.open(work/'runtime.tgz') as archive:
            archive.extractall(work/'runtime', filter='data')
        with ZipFile(work/'sdk.nupkg') as archive:
            prefix = 'tools/net8.0/any/'
            for member in archive.infolist():
                if member.is_dir() or not member.filename.startswith(prefix):
                    continue
                rel = PurePosixPath(member.filename[len(prefix):])
                if rel.is_absolute() or '..' in rel.parts:
                    raise EvidenceError('invalid path in SARIF SDK package')
                dest = work/'sdk'/rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as src, dest.open('xb') as dst:
                    shutil.copyfileobj(src, dst)
        schema_digest = sha(read_artifact(work/'sdk', 'sarif-2.1.0.json'))
        (work/'review.sarif').write_bytes(raw)
        cmd = ['/usr/bin/unshare', '--user', '--map-current-user', '--net', './runtime/dotnet',
               'sdk/Sarif.Multitool.dll', 'validate', 'review.sarif', '-j', 'sdk/sarif-2.1.0.json',
               '--output', 'validated.sarif', '--quiet']
        proc = subprocess.run(cmd, cwd=work, env={'HOME': temp, 'PATH': '/usr/bin:/bin',
                              'DOTNET_CLI_TELEMETRY_OPTOUT': '1', 'DOTNET_NOLOGO': '1',
                              'DOTNET_EnableDiagnostics': '0'}, stdin=subprocess.DEVNULL,
                              capture_output=True, timeout=60)
        if proc.returncode:
            raise EvidenceError('SARIF Multitool rejected the license report')
        validation = read_artifact(work, 'validated.sarif')
        if raw != read_artifact(work, 'review.sarif'):
            raise EvidenceError('SARIF input changed during validation')
    schema = strict_json(validation)
    run, = schema['runs']
    invocation, = run['invocations']
    driver = run['tool']['driver']
    if (schema['version'] != '2.1.0' or driver['name'] != 'Sarif.Multitool'
            or driver['semanticVersion'] != SDK_VERSION or invocation['executionSuccessful'] is not True
            or invocation.get('toolExecutionNotifications') or run['results']):
        raise EvidenceError('SARIF Multitool produced validation diagnostics')
    counts = Counter(r['ruleId'] for r in report['runs'][0]['results'])
    summary = {'validator_version': SDK_VERSION, 'sdk_sha256': SDK_SHA, 'runtime_archive_sha256': RUNTIME_SHA,
               'schema_sha256': schema_digest, 'sarif_sha256': sha(raw), 'validator_findings': 0,
               'findings_by_rule': {rule: counts[rule] for rule in RULES}}
    return summary, {'license-review.sarif': raw, 'native-validation.sarif': validation,
                     'validation.json': canonical(summary)}


def build(sdk, runtime, product, cargo, profiles, scan, files):
    rows = findings(product_cdxgen.capture(product), cargo['packages'], profiles, scan['notices'], files)
    return validate(sdk, runtime, render(rows))
