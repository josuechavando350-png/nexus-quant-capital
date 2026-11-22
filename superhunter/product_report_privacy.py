"""Publish a minimized view of the two public QA input manifests using pinned redactors."""
from pathlib import Path
import re
import sys
import tempfile

from .product_languages_batch import run
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_sources import git
from .repository_boundary import git_object
from .safe_io import canonical, read_artifact, strict_json

DIRSEARCH = 'maurosoria/dirsearch'
PROWLER = 'prowler-cloud/prowler'
SOURCES = {
    DIRSEARCH: ('052-dirsearch', '461705af2688ab6644b1f2bf738c46c55ee4d3da',
                'c0ccc9f75c90005af909c270db249caff9bcd4d9', 'lib/utils/command.py',
                '4d2c21ec412c1f95abc59119bf70591c0121b7eb'),
    PROWLER: ('075-prowler', '02d631d3a5db2c8676e9703aec286c7723a32e6f',
              'aaa6cfdc9973fdd65a40d6247daf816bb16a859b', 'prowler/lib/check/redact.py',
              'b70a6ecf0292b1c526df79df621caa2cef3864d7'),
}
DOSSIER = 'superhunter/product_supply/consolidated-acceptance-html-review'
MANIFESTS = {
    'first': '03efab53411de35f7084c810e8c8c7ad0438da8b63e6dabbf8016148c1200fe0',
    'second': 'a4f87360d22c91f30df195689d8d912678a2acc18f39589c27b8538e753e57cc',
}
# These controls are literal fabricated QA markers, never read from a machine or environment.
COMMAND_CONTROLS = {
    'separate': (['--header', 'NQC-FIXTURE-HEADER'], ['--header', '<redacted>']),
    'equals': (['--cookie=NQC-FIXTURE-COOKIE'], ['--cookie=<redacted>']),
    'attached': (['-HNQC-FIXTURE-SHORT'], ['-H<redacted>']),
    'benign': (['--threads', '2'], ['--threads', '2']),
}
COMMAND_WORKER = """import json, runpy, sys
redact = runpy.run_path('upstream.py')['redact_command']
print(json.dumps({k: redact(v) for k, v in json.load(sys.stdin).items()}))
"""
FIELDS_WORKER = """import json, runpy, sys
redact = runpy.run_path('upstream.py')['redact_sensitive_fields']
class Run:
    sensitive_fields = frozenset({'input_fingerprints', 'files'})
print(json.dumps({k: redact(Run(), v) for k, v in json.load(sys.stdin).items()}))
"""


def input_manifests():
    records = {}
    for label, digest in MANIFESTS.items():
        raw = read_artifact(ROOT, f'{DOSSIER}/{label}/run-inputs.json')
        if sha(raw) != digest:
            raise EvidenceError('unexpected QA input manifest for public privacy view')
        records[label] = strict_json(raw)
    return records


def commands(argv):
    cases = {'recorded': argv}
    expected = {'recorded': ' '.join(argv)}
    for label, (suffix, sanitized) in COMMAND_CONTROLS.items():
        cases[label] = [*argv, *suffix]
        expected[label] = ' '.join([*argv, *sanitized])
    return cases, expected


def project(record):
    # Fixed names prevent a free-form file name or fingerprint from becoming a public key.
    files = record['prepared_files']
    if not files or any(not re.fullmatch('[0-9a-f]{64}', value) for value in files.values()):
        raise EvidenceError('expected a file digest in the QA manifest')
    return {
        'producer': {key: record[key] for key in ('commit', 'tree', 'git_source_tree', 'checkout_clean_before')},
        'input_fingerprints': [record[key] for key in ('native_manifest_sha256', 'kit_manifest_sha256',
                                                      'raw_run_inputs_sha256', 'native_contract_sha256')],
        'files': [{'path': path, 'sha256': files[path]} for path in sorted(files)],
    }


def public_view(record, masked, command):
    expected = project(record)
    if (set(masked) != set(expected) or canonical(masked['producer']) != canonical(expected['producer'])
            or masked['input_fingerprints'] != ['REDACTED'] * len(expected['input_fingerprints'])
            or masked['files'] != [{'path': 'REDACTED', 'sha256': 'REDACTED'}] * len(expected['files'])):
        raise EvidenceError('public QA view leaked input metadata or lost producer evidence')
    return {'producer': masked['producer'], 'command': command, 'prepared_file_count': len(masked['files']),
            'input_fingerprints_masked': len(masked['input_fingerprints'])}


def upstream(source_root, name):
    directory, revision, tree, path, blob = SOURCES[name]
    repo = source_root / directory
    if repo.is_symlink() or git(repo, 'rev-parse', 'HEAD', 'HEAD^{tree}').decode().splitlines() != [revision, tree]:
        raise EvidenceError('unexpected upstream privacy producer')
    entry = git(repo, 'ls-tree', revision, '--', path)
    raw = git(repo, 'cat-file', 'blob', blob)
    if entry != f'100644 blob {blob}\t{path}\n'.encode() or git_object('blob', raw) != blob:
        raise EvidenceError('privacy producer source differs from pinned commit and blob')
    return raw


def produce(source, worker, payload):
    # Both modules use only the standard library. No project package is installed or imported.
    with tempfile.TemporaryDirectory(prefix='nqc-report-privacy-') as tmp:
        work = Path(tmp)
        (work / 'upstream.py').write_bytes(source)
        return strict_json(run(work, [sys.executable, '-I', '-S', '-B', '-c', worker], canonical(payload)))


def review(source_root):
    records = input_manifests()
    sources = {name: upstream(source_root, name) for name in SOURCES}
    if (records['first']['argv'] != records['second']['argv']
            or records['first']['native_manifest_sha256'] == records['second']['native_manifest_sha256']):
        raise EvidenceError('QA privacy inputs lack the expected shared command and distinct native manifests')
    cases, expected = commands(records['first']['argv'])
    observed = produce(sources[DIRSEARCH], COMMAND_WORKER, cases)
    if observed != expected:
        raise EvidenceError('QA command privacy filter changed a public argument or exposed a synthetic marker')
    projected = {slot: project(record) for slot, record in records.items()}
    masked = produce(sources[PROWLER], FIELDS_WORKER, projected)
    if set(masked) != set(records):
        raise EvidenceError('missing QA privacy case')
    views = {slot: public_view(record, masked[slot], observed['recorded']) for slot, record in records.items()}
    if views['first'] != views['second']:
        raise EvidenceError('public view discloses a difference in confidential input metadata')
    results = {
        DIRSEARCH: ('Publish the recorded QA command and verify credential-bearing argument controls.', {
            'public_command': observed['recorded'], 'controls': sorted(COMMAND_CONTROLS),
            'redacted_control_count': sum(before != after for before, after in COMMAND_CONTROLS.values())}),
        PROWLER: ('Publish the same minimized QA view for two separately recorded runs.', {
            'public_view': views['first'], 'distinct_native_input_fingerprints': True, 'equal_minimized_views': True}),
    }
    return {name: {'revision': SOURCES[name][1], 'role': 'executable', 'operation': operation,
                   'upstream_tree': SOURCES[name][2], 'upstream_path': SOURCES[name][3],
                   'upstream_blob': SOURCES[name][4], 'upstream_sha256': sha(sources[name]),
                   'source_manifests': MANIFESTS, 'result': result}
            for name, (operation, result) in results.items()}
