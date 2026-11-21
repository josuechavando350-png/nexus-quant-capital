"""Bind wheel-license decisions and contextual citations to verified public notice bytes."""
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from .product_notice_ranking import install_wheels
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .safe_io import canonical, strict_json

LOCK = 'superhunter/product_supply/license-review-linux-py312.txt'
DIGEST = 'c6847c036a6f23f04f227af648fd275714600bc89ed2d04313a871df08d24722'


def collect_records(supply, profiles, scan):
    wheels = {}
    def add(name, row, source):
        digest = row.get('wheel_sha256')
        key = f"{name}=={row['version']}:{digest or 'unverified'}"
        observed = []
        for notice in row['notices']:
            match = scan['notices'][notice['file']]
            if match['sha256'] != notice['sha256']:
                raise EvidenceError('ScanCode notice differs from the verified wheel record')
            observed.append(match['detected_expression'])
        record = {'digest': digest, 'declaration': row.get('declared_license_expression'), 'observed': observed,
                  'notices': [n['file'] for n in row['notices']]}
        if key in wheels:
            if {k: wheels[key][k] for k in record} != record:
                raise EvidenceError('inconsistent metadata for one wheel digest')
            wheels[key]['sources'].append(source)
        else:
            wheels[key] = {**record, 'sources': [source]}
    for name, row in (supply or {}).items():
        add(name, row, 'supply')
    for name, group in profiles.items():
        for row in group:
            for source in row['profiles']:
                add(name, row, source)
    return wheels


def expected(row):
    declared = ' '.join((row['declaration'] or '').split())
    found = {' '.join((s or '').split()) for s in row['observed']}
    if not row['digest']:
        return 'wheel_unverified'
    if not declared:
        return 'declaration_absent'
    if not found - {''}:
        return 'notice_expression_absent'
    if found - {'', declared}:
        return 'different_text_review'
    return 'partial_text_match' if '' in found else 'same_text'


def spans(text):
    lines = text.split('\n')
    paragraphs = []
    start = None
    for i, line in enumerate([*lines, '']):
        if line.strip():
            if start is None:
                start = i
        elif start is not None:
            paragraphs.append((start + 1, i, '\n'.join(lines[start:i]).strip()))
            start = None
    return paragraphs


class CitationIndex:
    def __init__(self, texts, windows):
        if texts.keys() != windows.keys():
            raise EvidenceError('incomplete LlamaIndex notice corpus')
        self.docs = {}
        all_windows = {}
        for name, text in texts.items():
            rows = spans(text)
            computed = []
            for i, (_, _, paragraph) in enumerate(rows):
                adjacent = rows[max(0, i-1):i+2]
                computed.append([name, sha(paragraph.encode()), sha(' '.join(r[2] for r in adjacent).encode())])
            if windows[name] != computed:
                raise EvidenceError('LlamaIndex context windows differ from verified notice paragraphs')
            self.docs[name] = rows
            all_windows[name] = computed
        self.summary = {'documents': len(texts), 'paragraphs': sum(map(len, self.docs.values())),
                        'windows_sha256': sha(canonical(all_windows))}

    def lookup(self, key):
        name, sep, line = key.rpartition('@')
        if not sep or not line.isdecimal() or len(line) > 9 or not int(line):
            raise EvidenceError('notice context requires filename@line, starting at line 1')
        rows = self.docs.get(name, [])
        for i, (start, end, text) in enumerate(rows):
            if start <= int(line) <= end:
                window = rows[max(0, i-1):i+2]
                return {'file': name, 'start_line': start, 'end_line': end, 'paragraph': text,
                        'context': [{'start_line': a, 'end_line': b, 'text': t} for a, b, t in window]}
        return None


def build(wheelhouse, notices, wheels):
    texts = {n: raw.decode('utf-8', errors='replace').replace('\r\n', '\n').replace('\r', '\n') for n, raw in notices.items()}
    with tempfile.TemporaryDirectory(prefix='nqc-notice-decisions-') as temp:
        work = Path(temp)
        env = {'HOME': temp, 'PATH': '/usr/bin:/bin', 'PIP_NO_INDEX': '1', 'HF_HUB_OFFLINE': '1',
               'LANGCHAIN_TRACING_V2': 'false', 'LC_ALL': 'C.UTF-8', 'TOKENIZERS_PARALLELISM': 'false'}
        install_wheels(wheelhouse, work, env, lock_path=LOCK, lock_digest=DIGEST, producer='notice review')
        (work/'input.json').write_bytes(canonical({'texts': texts, 'wheels': wheels}))
        subprocess.run(['/usr/bin/unshare', '--user', '--map-current-user', '--net', sys.executable, '-I', '-B',
                        str(ROOT/'superhunter/product_notice_review_worker.py')], cwd=work, env=env,
                       stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=150)
        output = strict_json((work/'output.json').read_bytes())
    versions = {'llama-index-core': '0.14.26', 'langgraph': '1.2.24'}
    if output['versions'] != versions or output['decisions'] != {key: expected(row) for key, row in wheels.items()}:
        raise EvidenceError('LangGraph wheel decisions differ from verified declarations and observations')
    index = CitationIndex(texts, output['windows'])
    records = {key: {**row, 'decision': output['decisions'][key]} for key, row in wheels.items()}
    counts = dict(sorted(Counter(output['decisions'].values()).items()))
    return index, {**index.summary, 'version': versions['llama-index-core'], 'wheel_lock_sha256': DIGEST}, {
        'version': versions['langgraph'], 'wheel_lock_sha256': DIGEST, 'counts': counts, 'records': records}
