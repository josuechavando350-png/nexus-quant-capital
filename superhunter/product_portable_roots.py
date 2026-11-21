"""Verify all 47 deferred commit objects and 34 original dependency declarations entirely offline."""
import base64
import zlib

from . import product_remote_roots as remote
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .repository_boundary import git_object
from .safe_io import canonical, read_artifact, strict_json

ARCHIVE = 'superhunter/product_supply/offline-remote-inputs.json'
ARCHIVE_SHA = 'cd55afcb85905025e2984704b4d51d9015f2f06d8341db40390ac04e315969ab'


def inflate(text):
    decoder = zlib.decompressobj()
    raw = decoder.decompress(base64.b64decode(text, validate=True), 256_001)
    if len(raw) > 256_000 or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise EvidenceError('invalid compressed Git object')
    return raw


def verify_row(identity, tree, obj):
    contents = {}
    commit = inflate(obj['commit_object'])
    files = remote.manifests(tree)
    if (obj['id'] != identity['id'] or git_object('commit', commit) != identity['commit']
            or commit.split(b'\n', 1)[0] != b'tree ' + identity['tree'].encode()
            or set(files) != set(obj['declarations'])):
        raise EvidenceError('offline commit, tree or declaration set differs')
    for name, oid in files.items():
        raw = inflate(obj['declarations'][name])
        if git_object('blob', raw) != oid:
            raise EvidenceError('offline manifest differs from its root tree')
        contents[remote.member_name(obj['id'], name)] = raw
    receipt = {'id': identity['id'], 'repository': identity['repository'], 'commit': identity['commit'],
               'root': identity['tree'], 'commit_bytes_sha256': sha(commit), 'manifest_blobs': files}
    return receipt, contents


def inputs():
    data = read_artifact(ROOT, ARCHIVE)
    if sha(data) != ARCHIVE_SHA:
        raise EvidenceError('offline source evidence archive changed')
    packed = strict_json(data)
    if packed['version'] != 1 or packed['codec'] != 'zlib-base64':
        raise EvidenceError('unrecognized source evidence archive')
    receipts, contents = [], {}
    for (identity, tree), obj in zip(remote.roots(), packed['rows'], strict=True):
        receipt, declared = verify_row(identity, tree, obj)
        receipts.append(receipt)
        contents.update(declared)
    return receipts, contents


def attach(index):
    rows, files = inputs()
    remote.attach(index, read_file=files.__getitem__)
    index.portable_source_proof = {'commits': len(rows), 'root_declarations': len(files),
                                   'archive_sha256': ARCHIVE_SHA, 'receipt_sha256': sha(canonical(rows))}
    for row in rows:
        index.repos[row['repository'].casefold()]['offline_source_proof'] = row
