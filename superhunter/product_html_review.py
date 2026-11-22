"""Read the visible content and heading semantics of one fixed, historical NQC HTML report."""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile

from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .review import render_html
from .safe_io import canonical, read_artifact, strict_json

REPOSITORIES = {'microsoft/playwright': 'executable'}
SUPPLY = 'superhunter/product_supply/'
WORKER_SHA = '9549b514ef35283e67b246df0b3535a15c4b2460881bdbd88de7341ffa4f8ddd'
PINS = '4381fc09c4c8eeb8771749a1835599fb191781aae54cab75d57445ae1947afc5'
TITLE = 'SUPERHUNTER — revisión local'
HEADING = 'SUPERHUNTER · Evidencia y pendientes'
CSP = "default-src 'none'; style-src 'unsafe-inline'"
ROW = '| [PR 119](product_supply/native-session-70.json) | 221 | 70 | 58 | 12 |'
CASES = ('canonical', 'missing_row', 'missing_heading')


def inputs():
    raw = read_artifact(ROOT, SUPPLY + 'html-review-pins.json')
    if sha(raw) != PINS:
        raise EvidenceError('HTML review pins differ')
    pins = strict_json(raw)
    markdown = read_artifact(ROOT, SUPPLY + 'html-review-markdown.md')
    if (sha(markdown) != pins['markdown_sha256'] or
            sha(read_artifact(ROOT, SUPPLY + 'html-review-provenance.json')) != pins['provenance_sha256']):
        raise EvidenceError('HTML review source or provenance differs')
    return pins, markdown.decode()


def documents(markdown):
    html = render_html(markdown)
    row = (ROW + '\n').encode()
    heading = ('<h1>' + HEADING + '</h1>').encode()
    if html.count(row) != 1 or html.count(heading) != 1:
        raise EvidenceError('historical HTML control anchors differ')
    return {'canonical': html, 'missing_row': html.replace(row, b''),
            'missing_heading': html.replace(heading, ('<p>' + HEADING + '</p>').encode())}


def reconcile(observations, markdown):
    if type(observations) is not dict or set(observations) != set(CASES):
        raise EvidenceError('missing or unexpected browser observations')
    cases = {}
    html = documents(markdown)
    for name in CASES:
        text = markdown.replace(ROW + '\n', '') if name == 'missing_row' else markdown
        semantic_heading = name != 'missing_heading'
        expected = {'title': TITLE, 'language': 'es', 'heading': [HEADING] if semantic_heading else [],
                    'headingVisible': semantic_heading, 'preCount': 1, 'preVisible': True, 'text': text,
                    'bodyChildren': ['h1' if semantic_heading else 'p', 'pre'], 'activeElements': 0,
                    'requests': [], 'csp': CSP, 'documentURL': 'about:blank'}
        if canonical(observations[name]) != canonical(expected):
            raise EvidenceError('visible HTML content, semantics or isolation differs: ' + name)
        differences = sorted(key for key in expected if observations[name][key] != observations['canonical'][key])
        cases[name] = {'html_sha256': sha(html[name]), 'visible_text_sha256': sha(text.encode()),
                       'visible_text_bytes': len(text.encode()), 'heading_level_one': semantic_heading,
                       'historical_rows_visible': sum(label in text for label in ('[PR 118]', '[PR 119]')),
                       'canonical_view': not differences, 'changed_dom_fields': differences}
    return cases


def unpack_reviewed_archives(root):
    # copy_release first authenticates both complete immutable archives. Only regular
    # members beneath their expected top-level directory are materialized.
    def destination(name, prefix):
        path = Path(name)
        if not path.parts or path.parts[0] != prefix or '..' in path.parts:
            raise EvidenceError('unexpected review runtime archive path')
        output = root / path
        output.parent.mkdir(parents=True, exist_ok=True)
        return output

    with tarfile.open(root/'playwright-core.tgz', 'r:gz') as bundle:
        for entry in bundle:
            path = destination(entry.name, 'package')
            if entry.isdir():
                continue
            if not entry.isfile():
                raise EvidenceError('unsupported driver archive entry')
            with bundle.extractfile(entry) as source, path.open('xb') as dest:
                shutil.copyfileobj(source, dest)
    with zipfile.ZipFile(root/'chrome.zip') as bundle:
        for entry in bundle.infolist():
            path = destination(entry.filename, 'chrome-headless-shell-linux64')
            if entry.is_dir():
                continue
            mode = entry.external_attr >> 16
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                raise EvidenceError('unsupported browser archive entry')
            with bundle.open(entry) as source, path.open('xb') as dest:
                shutil.copyfileobj(source, dest)
            if mode & 0o111:
                path.chmod(0o700)


def run(kit):
    pins, markdown = inputs()
    if os.getuid() == 0:
        raise EvidenceError('HTML review requires an unprivileged account')
    with tempfile.TemporaryDirectory(prefix='nqc-html-review-') as temp:
        root = Path(temp)
        for name, entry in pins['files'].items():
            copy_release(name, Path(kit)/name, root/name, entry['sha256'],
                         limit=entry['bytes'], executable=name == 'node')
        unpack_reviewed_archives(root)
        for name, data in documents(markdown).items():
            (root/(name + '.html')).write_bytes(data)
        worker = read_artifact(ROOT, 'superhunter/product_html_review_worker.cjs')
        if sha(worker) != WORKER_SHA:
            raise EvidenceError('HTML observation worker differs')
        (root/'worker.cjs').write_bytes(worker)
        env = {'HOME': temp, 'TMPDIR': temp, 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'TZ': 'UTC'}
        command = ['/usr/bin/unshare', '--user', '--map-current-user', '--net', str(root/'node'),
                   'worker.cjs']
        proc = subprocess.run(command, cwd=root, env=env, stdin=subprocess.DEVNULL,
                              capture_output=True, timeout=60)
        if proc.returncode or proc.stderr or len(proc.stdout) > 32768:
            raise EvidenceError('offline browser could not produce the fixed review observations')
        cases = reconcile(strict_json(proc.stdout), markdown)
    return {'schema_version': 1, 'query': 'html-review', 'repository': 'microsoft/playwright',
            'revision': '049226728d2da8054db18b04782a9848b755855e', 'pins_sha256': PINS,
            'source_commit': pins['source_commit'], 'source_blob': pins['source_blob'], 'cases': cases,
            'title': TITLE, 'heading': HEADING, 'lang': 'es', 'canonical_views': 1,
            'rejected_altered_views': 2, 'document_requests': 0,
            'scope': 'Three views of a fixed historical report rendered by NQC review.render_html',
            'original_vulnerabilities_confirmed': 0}
