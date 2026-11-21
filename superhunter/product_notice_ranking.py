"""Rank verified public license notices with Haystack BM25+ and check scores from the source text."""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import math
from pathlib import Path
import subprocess
import sys
import tempfile

from .product_notice_search import TERM, read_response, tokens
from .product_notices import LOCK_ROW, read_wheel
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .safe_io import canonical, read_artifact

LOCK = 'superhunter/product_supply/haystack-linux-py312.txt'
LOCK_SHA = '35095efc6decb18e556c5a41149f879bb268f705f5e72961cba6fbab4214b8a1'
ISOLATE = ['/usr/bin/unshare', '--user', '--map-current-user', '--net']


class RankingCorpus:
    def __init__(self, notices):
        self.docs = {}
        self.freq = {}
        self.df = Counter()
        for name, raw in sorted(notices.items()):
            words = TERM.findall(raw.decode('utf-8', errors='replace').casefold())
            self.docs[name] = {'text': ' '.join(words), 'sha256': sha(raw)}
            self.freq[name] = Counter(words)
            self.df.update(self.freq[name].keys())
        self.lengths = {name: counts.total() for name, counts in self.freq.items()}
        if not self.df:
            raise EvidenceError('notice ranking requires verified notices with text')
        self.mean_length = sum(self.lengths.values()) / len(self.docs)

    def validate(self, terms, rows):
        total = len(self.docs)
        weights = {word: math.log1p((total - self.df[word] + .5) / (self.df[word] + .5))
                   for word in terms if word in self.df}
        expected = {}
        for name, counts in self.freq.items():
            found = sorted(weights.keys() & counts.keys())
            if found:
                normalizer = 1.5 * (.25 + .75 * self.lengths[name] / self.mean_length)
                score = sum(weights[t] * (1 + 2.5 * counts[t] / (counts[t] + normalizer)) for t in found)
                expected[name] = (found, score)
        matches = []
        seen = set()
        previous = math.inf
        for row in rows:
            name = row['file']
            if name not in expected or name in seen or row['sha256'] != self.docs[name]['sha256']:
                raise EvidenceError('Haystack returned an unexpected notice identity')
            seen.add(name)
            found, score = expected[name]
            native = row['score']
            if (type(native) not in (int, float) or not math.isclose(native, score, rel_tol=1e-10)
                    or native > previous + 1e-10):
                raise EvidenceError('Haystack rank or BM25 score differs from public notice text')
            previous = native
            matches.append({'file': name, 'sha256': row['sha256'], 'matched_terms': found,
                            'score': len(found), 'bm25_score': round(native, 10)})
        if seen != expected.keys():
            raise EvidenceError('Haystack omitted a matching public notice')
        return sorted(matches, key=lambda row: (-row['bm25_score'], row['file']))


def install_wheels(wheelhouse, work, env):
    lock = read_artifact(ROOT, LOCK)
    if sha(lock) != LOCK_SHA:
        raise EvidenceError('Haystack dependency lock digest mismatch')
    dest = work/'wheels'
    dest.mkdir()
    for line in lock.decode('ascii').splitlines():
        match = LOCK_ROW.fullmatch(line)
        if not match:
            raise EvidenceError('invalid Haystack dependency pin')
        name, version, digest = match.groups()
        for candidate in sorted(wheelhouse.glob(name.replace('-', '_') + '-' + version + '-*.whl')):
            raw = read_wheel(candidate)
            if sha(raw) == digest:
                (dest/candidate.name).write_bytes(raw)
                break
        else:
            raise EvidenceError('missing digest-matched Haystack wheel: ' + name)
    (work/'requirements.txt').write_bytes(lock)
    subprocess.run([*ISOLATE, sys.executable, '-I', '-m', 'pip', '--isolated', '--disable-pip-version-check',
                    'install', '--no-index', '--no-deps', '--no-compile', '--no-cache-dir', '--require-hashes',
                    '--only-binary=:all:', '--find-links', 'wheels', '--target', 'lib', '-r', 'requirements.txt'],
                   cwd=work, env=env, stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=120)


@contextmanager
def open_ranker(wheelhouse, notices):
    if sys.version_info[:2] != (3, 12):
        raise EvidenceError('the locked Haystack wheel inventory requires CPython 3.12')
    corpus = RankingCorpus(notices)
    with tempfile.TemporaryDirectory(prefix='nqc-notice-ranking-') as temp:
        work = Path(temp)
        env = {'HOME': temp, 'PATH': '/usr/bin:/bin', 'TMPDIR': temp, 'HAYSTACK_TELEMETRY_ENABLED': 'false',
               'OPENBLAS_NUM_THREADS': '1'}
        install_wheels(wheelhouse, work, env)
        (work/'documents.json').write_bytes(canonical(corpus.docs))
        script = Path(__file__).with_name('product_ranking_worker.py')
        with subprocess.Popen([*ISOLATE, sys.executable, '-B', '-I', str(script)], cwd=work, env=env,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as worker:
            try:
                if read_response(worker) != {'version': '3.5.0', 'documents': len(corpus.docs)}:
                    raise EvidenceError('Haystack failed its corpus inventory check')

                def rank(text):
                    if len(text) > 512:
                        raise EvidenceError('notice query exceeds 512 characters')
                    terms = tokens(text)
                    worker.stdin.write(canonical({'terms': sorted(terms)}))
                    worker.stdin.flush()
                    rows = read_response(worker)['hits']
                    return {'terms': sorted(terms), 'matches': corpus.validate(terms, rows)}

                probe = 'redistribution' if 'redistribution' in corpus.df else min(corpus.df)
                witness = rank(probe)
                manifest = {name: doc['sha256'] for name, doc in corpus.docs.items()}
                yield rank, {'version': '3.5.0', 'algorithm': 'BM25Plus', 'wheel_lock_sha256': LOCK_SHA,
                             'documents': len(corpus.docs), 'corpus_sha256': sha(canonical(manifest)),
                             'probe': probe, 'probe_matches': len(witness['matches'])}
                worker.stdin.close()
                if worker.wait(timeout=10):
                    raise EvidenceError('Haystack ranking worker failed')
            finally:
                if worker.poll() is None:
                    worker.kill()
                    worker.wait()
