"""Compare verified notices to each other with pgvector in a disposable single-user PostgreSQL database."""
from __future__ import annotations

from collections import defaultdict
import csv
from io import StringIO
from itertools import combinations
import math
from pathlib import Path
import subprocess
import tempfile

from .product_notice_ranking import RankingCorpus
from .product_reasoning import EvidenceError
from .product_review import copy_release, sha
from .safe_io import canonical, read_artifact

PACKAGES = {'postgresql-17_17.12-0+deb13u1_amd64.deb': '72443dcedfa0bdfa79dafdf414c18498b89929eeee1555e987c87154f3082fea',
            'postgresql-17-pgvector_0.8.0-1_amd64.deb': '6e8a457eb252617b66cf7b2908c736127eae43703fffec94492ac131ca921515'}
ISOLATE = ['/usr/bin/unshare', '--user', '--map-current-user', '--net']


def weights(corpus):
    names = sorted(corpus.docs)
    dimensions = {term: i for i, term in enumerate(sorted(corpus.df), 1)}
    inverse = {term: 1 + math.log((len(names) + 1) / (df + 1)) for term, df in corpus.df.items()}
    return [{dimensions[t]: (1 + math.log(n)) * inverse[t] for t, n in corpus.freq[name].items()}
            for name in names]


def compare(corpus, vectors, pairs):
    names = sorted(corpus.docs)
    expected = set(combinations([i for i, vector in enumerate(vectors) if vector], 2))
    seen = set()
    neighbors = defaultdict(list)
    norms = [math.sqrt(sum(x*x for x in v.values())) for v in vectors]
    identical = 0
    for left, right, score in pairs:
        if (left, right) not in expected or (left, right) in seen:
            raise EvidenceError('unbound or repeated pgvector notice pair')
        seen.add((left, right))
        a, b = vectors[left], vectors[right]
        dot = sum(weight * b.get(term, 0) for term, weight in a.items())
        if not math.isclose(score, dot / (norms[left] * norms[right]), abs_tol=2e-6):
            raise EvidenceError('pgvector cosine differs from the verified notice texts')
        same = corpus.docs[names[left]]['sha256'] == corpus.docs[names[right]]['sha256']
        identical += same
        for source, target in [(left, right), (right, left)]:
            name = names[target]
            neighbors[names[source]].append({'file': name, 'sha256': corpus.docs[name]['sha256'],
                                             'cosine': round(score, 8), 'same_bytes': same})
    if seen != expected:
        raise EvidenceError('incomplete pgvector comparison')
    results = {}
    for i, name in enumerate(names):
        ranked = sorted(neighbors[name], key=lambda row: (-row['cosine'], row['file']))
        results[name] = {'file': name, 'sha256': corpus.docs[name]['sha256'], 'compared': len(ranked),
                         'has_terms': bool(vectors[i]), 'nearest': ranked[:5]}
    return results, identical


def build(packages, notices):
    corpus = RankingCorpus(notices)
    vectors = weights(corpus)
    names = sorted(corpus.docs)
    ids = [(i, corpus.docs[n]['sha256']) for i, n in enumerate(names) if vectors[i]]
    if len(ids) < 2:
        raise EvidenceError('pgvector comparison requires at least two nonempty notices')
    with tempfile.TemporaryDirectory(prefix='nqc-notice-pg-') as temp:
        work = Path(temp)
        env = {'HOME': temp, 'LC_ALL': 'C', 'PATH': '/usr/bin:/bin', 'TZ': 'UTC'}
        for filename, digest in PACKAGES.items():
            copy_release('PostgreSQL package', packages/filename, work/filename, digest, executable=False)
            subprocess.run([*ISOLATE, '/usr/bin/dpkg-deb', '-x', filename, 'root'], cwd=work, env=env,
                           stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=60)
        bin_dir = work/'root/usr/lib/postgresql/17/bin'
        subprocess.run([*ISOLATE, str(bin_dir/'initdb'), '-L', str(work/'root/usr/share/postgresql/17'),
                        '--no-locale', '--no-sync', '-E', 'UTF8', '-A', 'reject', '-D', 'data'], cwd=work,
                       env=env, stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=60)
        data = work/'data'
        with (data/'notice-input.csv').open('w', newline='') as f:
            writer = csv.writer(f)
            for i, digest in ids:
                sparse = ','.join(f'{t}:{x:.17g}' for t, x in sorted(vectors[i].items()))
                writer.writerow([i, digest, '{' + sparse + '}/' + str(len(corpus.df))])
        def output(name):
            return "'" + str(work/name).replace("'", "''") + "'"
        sql = '\n'.join([
            'BEGIN;', 'CREATE EXTENSION vector;',
            'CREATE TEMP TABLE notices (id integer PRIMARY KEY, digest text NOT NULL, v sparsevec NOT NULL);',
            "COPY notices FROM 'notice-input.csv' WITH (FORMAT csv);",
            "COPY (SELECT extversion, current_setting('server_version') FROM pg_extension WHERE extname='vector') "
            + 'TO ' + output('version.csv') + ' WITH (FORMAT csv);',
            'COPY (SELECT id, digest FROM notices ORDER BY id) TO ' + output('ids.csv') + ' WITH (FORMAT csv);',
            'COPY (SELECT a.id, b.id, 1 - (a.v <=> b.v) FROM notices a JOIN notices b ON a.id < b.id '
            + 'ORDER BY a.id, b.id) TO ' + output('pairs.csv') + ' WITH (FORMAT csv);', 'COMMIT;', ''])
        # Single-user mode executes SQL via stdin. No server, port or socket is created.
        run = subprocess.run([*ISOLATE, str(bin_dir/'postgres'), '--single', '-D', str(data), 'postgres'],
                             cwd=work, env=env, input=sql.encode(), capture_output=True, check=True, timeout=60)
        if b'ERROR:' in run.stderr or b'FATAL:' in run.stderr:
            raise EvidenceError('PostgreSQL rejected the notice inventory')
        def rows(name):
            return csv.reader(StringIO(read_artifact(work, name).decode()))
        version, = rows('version.csv')
        if version != ['0.8.0', '17.12 (Debian 17.12-0+deb13u1)'] or [(int(i), h) for i, h in rows('ids.csv')] != ids:
            raise EvidenceError('pgvector version or notice identities differ')
        pairs = [(int(i), int(j), float(score)) for i, j, score in rows('pairs.csv')]
    results, identical = compare(corpus, vectors, pairs)
    summary = {'version': version[0], 'postgres_version': version[1], 'package_sha256': PACKAGES,
               'corpus_sha256': sha(canonical({n: corpus.docs[n]['sha256'] for n in names})),
               'documents': len(names), 'compared_documents': len(ids), 'compared_pairs': len(pairs),
               'identical_byte_pairs': identical}
    return summary, results
