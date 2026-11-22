"""Use a private Qdrant sparse index to find exact terms in verified wheel notices."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import re
import select
import subprocess
import sys
import tempfile

from .product_reasoning import EvidenceError
from .product_review import copy_release, sha
from .safe_io import canonical, strict_json

VERSION = '1.20.2'
QDRANT_SHA = '315342e8f783935932e8672c06fcc1a13903c819a82f1263765c3f00a831d893'
TERM = re.compile(r'[a-z0-9]+')
REPLY_LIMIT = 4 * 1024**2


def tokens(text):
    return set(TERM.findall(text.casefold()))


class NoticeCorpus:
    def __init__(self, notices):
        if not notices:
            raise EvidenceError('notice search requires verified wheel notices')
        self.names = sorted(notices)
        self.terms = [tokens(notices[n].decode('utf-8', errors='replace')) for n in self.names]
        vocabulary = sorted(set().union(*self.terms))
        if not vocabulary:
            raise EvidenceError('empty notice vocabulary')
        self.vocab = {word: i for i, word in enumerate(vocabulary)}
        self.hashes = [sha(notices[name]) for name in self.names]

    def sparse(self, terms):
        indices = sorted(self.vocab[word] for word in terms if word in self.vocab)
        return {'indices': indices, 'values': [1] * len(indices)}

    def points(self):
        return [{'id': i, 'vector': {'terms': self.sparse(self.terms[i])},
                 'payload': {'file': name, 'sha256': self.hashes[i]}} for i, name in enumerate(self.names)]

    def validate_matches(self, terms, rows):
        expected = {i: sorted(terms & words) for i, words in enumerate(self.terms) if terms & words}
        found = []
        seen = set()
        for row in rows:
            i = row['id']
            if type(i) is not int or i not in expected or i in seen:
                raise EvidenceError('unexpected or duplicate notice in search response')
            payload = {'file': self.names[i], 'sha256': self.hashes[i]}
            if (row['payload'] != payload or type(row['score']) not in (float, int)
                    or row['score'] != len(expected[i])):
                raise EvidenceError('notice search evidence disagrees with source text')
            seen.add(i)
            found.append({**payload, 'matched_terms': expected[i], 'score': len(expected[i])})
        if seen != expected.keys():
            raise EvidenceError('incomplete notice search results')
        return sorted(found, key=lambda row: (-row['score'], row['file']))


def read_response(worker):
    if not select.select([worker.stdout], [], [], 45)[0]:
        raise EvidenceError('private notice index timed out')
    raw = worker.stdout.readline(REPLY_LIMIT + 1)
    if not raw or len(raw) > REPLY_LIMIT or not raw.endswith(b'\n'):
        raise EvidenceError('private notice index returned an incomplete response')
    return strict_json(raw)


@contextmanager
def open_index(binary, notices):
    corpus = NoticeCorpus(notices)
    with tempfile.TemporaryDirectory(prefix='nqc-notice-index-') as temp:
        work = Path(temp)
        copy_release('Qdrant', binary, work/'qdrant', QDRANT_SHA)
        (work/'points.json').write_bytes(canonical(corpus.points()))
        root = str(Path(__file__).resolve().parents[1])
        entry = ('import sys; sys.path.insert(0, sys.argv[1]); '
                 'from superhunter.product_notice_worker import main; main(int(sys.argv[2]))')
        command = ['/usr/bin/unshare', '--user', '--map-root-user', '--net', '--pid', '--fork', '--kill-child',
                   sys.executable, '-B', '-I', '-c', entry, root, str(os.stat('/proc/self/ns/net').st_ino)]
        with subprocess.Popen(command, cwd=work, env={'HOME': temp, 'PATH': '/usr/bin:/bin'},
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as worker:
            try:
                ready = read_response(worker)
                if ready != {'version': VERSION, 'indexed': len(corpus.names)}:
                    raise EvidenceError('private notice index failed its inventory check')

                def search(text):
                    if len(text) > 512:
                        raise EvidenceError('notice query exceeds 512 characters')
                    terms = tokens(text)
                    vector = corpus.sparse(terms)
                    rows = []
                    if vector['indices']:
                        worker.stdin.write(canonical(vector))
                        worker.stdin.flush()
                        rows = read_response(worker)['hits']
                    return {'terms': sorted(terms), 'matches': corpus.validate_matches(terms, rows)}

                probe = 'redistribution' if 'redistribution' in corpus.vocab else min(corpus.vocab)
                witness = search(probe)
                manifest = dict(zip(corpus.names, corpus.hashes))
                evidence = {'version': VERSION, 'binary_sha256': QDRANT_SHA, 'documents': len(corpus.names),
                            'corpus_sha256': sha(canonical(manifest)), 'terms': len(corpus.vocab),
                            'probe': probe, 'probe_matches': len(witness['matches'])}
                yield search, evidence
                worker.stdin.close()
                if worker.wait(timeout=10):
                    raise EvidenceError('private notice index exited unsuccessfully')
            finally:
                if worker.poll() is None:
                    worker.kill()
                    worker.wait()


def serve_queries(index, keys, qdrant, haystack, notices):
    from .toolkit_index import for_queries
    index = for_queries(index)
    with ExitStack() as stack:
        exact = rank = None
        if qdrant:
            exact, evidence = stack.enter_context(open_index(qdrant, notices))
            index.repos['qdrant/qdrant']['notice_search_evidence'] = evidence
        if haystack:
            from .product_notice_ranking import open_ranker
            rank, evidence = stack.enter_context(open_ranker(haystack, notices))
            index.repos['deepset-ai/haystack']['notice_ranking_evidence'] = evidence
        for key in keys:
            prefix, sep, terms = key.strip().partition(':')
            if not sep or prefix.casefold() != 'notice':
                answer = index.lookup(key)
            elif not (rank or exact):
                raise EvidenceError('notice search requires a verified notice index')
            else:
                answer = rank(terms) if rank else exact(terms)
                if rank and exact:
                    comparison = exact(terms)
                    base = [{k: v for k, v in row.items() if k != 'bm25_score'} for row in answer['matches']]
                    if sorted(base, key=lambda r: r['file']) != sorted(comparison['matches'], key=lambda r: r['file']):
                        raise EvidenceError('Haystack and Qdrant disagree on matching notice identities or terms')
            print(json.dumps(answer, sort_keys=True), flush=True)
