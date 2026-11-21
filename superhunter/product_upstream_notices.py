"""Cross-reference one pinned public license artifact per catalog identity with a local product session."""
from collections import defaultdict
from urllib.parse import quote

from .repository_boundary import git_object
from .product_reasoning import EvidenceError
from .product_review import CATALOG, CATALOG_SHA, ROOT, repositories, sha
from .product_supply_review import IDENTITIES, identity_rows
from .safe_io import canonical, read_artifact, strict_json

LOCK = 'superhunter/product_supply/upstream-notices.json'
LOCK_SHA = 'e5d0c69236e63edfcb9acc80048ec86eb113152ed380ed9fe7142aa98cd32b46'


def sources():
    raw = read_artifact(ROOT, LOCK)
    if sha(raw) != LOCK_SHA:
        raise EvidenceError('unexpected upstream notice inventory')
    lock = strict_json(raw)
    catalog = repositories()
    identities = identity_rows(read_artifact(ROOT, IDENTITIES), catalog, read_artifact(ROOT, CATALOG))
    rows = lock['sources']
    if lock['schema_version'] != 1 or lock['catalog_sha256'] != CATALOG_SHA or len(rows) != len(identities):
        raise EvidenceError('upstream notice catalog mismatch')
    for row, identity in zip(rows, identities, strict=True):
        if (row['id'], row['github_id'], row['repository']) != (
                identity['id'], identity['github_id'], identity['full_name']):
            raise EvidenceError('upstream notice identity mismatch')
    return rows


def filename(row):
    return f"upstream-{row['id']:03}-license.txt"


def document_hash(row):
    notice = row['notice']
    return notice.get('selected_sha256', notice['sha256'])


def select_document(row, raw):
    notice = row['notice']
    if (len(raw) != notice['bytes'] or sha(raw) != notice['sha256']
            or git_object('blob', raw) != notice['git_blob']):
        raise EvidenceError(f"upstream file at catalog ID {row['id']} differs from its pin")
    if 'line' in notice:
        raw = raw.splitlines(keepends=True)[notice['line'] - 1]
    if sha(raw) != document_hash(row):
        raise EvidenceError('selected notice differs from pinned excerpt')
    return raw


def attach(index, folder):
    rows = sources()
    expected = {filename(r): document_hash(r) for r in rows}
    marker = canonical({'schema_version': 1, 'sha256': expected})
    if {p.name for p in folder.iterdir()} != set(expected) | {'COMPLETE.json'}:
        raise EvidenceError('upstream notices missing or unexpected')
    if read_artifact(folder, 'COMPLETE.json') != marker:
        raise EvidenceError('upstream notice bundle differs from product lock')
    corpus = {}
    groups = defaultdict(list)
    for row in rows:
        name = filename(row)
        raw = read_artifact(folder, name)
        if sha(raw) != expected[name]:
            raise EvidenceError('upstream notice content mismatch')
        corpus[name] = raw
        groups[expected[name]].append(row['id'])
    for row in rows:
        name = filename(row)
        notice = row['notice']
        uri = f"https://github.com/{row['repository']}/blob/{row['revision']}/{quote(notice['path'])}"
        if 'line' in notice:
            uri += f"#L{notice['line']}"
        index.repos[row['repository'].casefold()]['upstream_notice'] = {
            'source_url': uri, 'github_id': row['github_id'], 'revision': row['revision'], 'document': name,
            'source_sha256': notice['sha256'], 'document_sha256': expected[name],
            'identical_document_ids': groups[expected[name]]}
    index.upstream_notices = {'repositories': len(rows), 'distinct_documents': len(groups),
                              'corpus_sha256': sha(canonical(expected)), 'lock_sha256': LOCK_SHA}
    return corpus
