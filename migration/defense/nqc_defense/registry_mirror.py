"""A local public-data receiver that preserves an accepted registry prefix across updates."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import stat

from .codec import Rejected, canonical, decode, fields, integer
from .dossier_attestation import private_parent
from .files import create_local, publish_local, read_local, sha256
from .receipts import hex_digest
from .signer_registry import (MAX_BUNDLE, ORIGIN, bundle_bytes, checkpoint, row_head,
                              VerifiedRegistry)

EMPTY = {'generation': 0, 'registry_checkpoint': dict(ORIGIN), 'bundle_digest': ORIGIN['head']}


def receipt(value):
    fields(value, ('generation', 'registry_checkpoint', 'bundle_digest'))
    integer(value['generation'], 0, 2**63-1)
    checkpoint(value['registry_checkpoint']); hex_digest(value['bundle_digest'])
    if value['generation'] == 0:
        if canonical(value) != canonical(EMPTY):
            raise Rejected('mirror_receipt')
    elif value['registry_checkpoint']['revision'] == 0 or value['bundle_digest'] == ORIGIN['head']:
        raise Rejected('mirror_receipt')
    return value


class RegistryMirror:
    def __init__(self, root, registry_digest, authority_digest):
        hex_digest(registry_digest); hex_digest(authority_digest)
        self.root = Path(root).absolute(); self.path = self.root/'mirror.sqlite3'
        self.registry_digest, self.authority_digest = registry_digest, authority_digest
        self.identity = canonical({'schema': 'nqc-registry-mirror-identity-v1',
                                   'registry_digest': registry_digest, 'authority_digest': authority_digest})
        self._cache = None
        self._check_files()

    @classmethod
    def create(cls, root, registry_digest, authority_digest):
        hex_digest(registry_digest); hex_digest(authority_digest)
        root = Path(root).absolute(); root.mkdir(mode=0o700, exist_ok=False)
        identity = canonical({'schema': 'nqc-registry-mirror-identity-v1',
                              'registry_digest': registry_digest, 'authority_digest': authority_digest})
        create_local(root, 'identity.json', identity); create_local(root, 'mirror.sqlite3', b'')
        mirror = cls(root, registry_digest, authority_digest)
        with mirror.connection(write=True) as db:
            db.execute('CREATE TABLE snapshot (id INTEGER PRIMARY KEY CHECK(id=1), generation INTEGER NOT NULL, '
                       'bundle BLOB, bundle_digest TEXT NOT NULL, previous BLOB)')
            db.execute('INSERT INTO snapshot VALUES(1,0,NULL,?,NULL)', (ORIGIN['head'],))
        return mirror

    def _check_files(self):
        private_parent(self.root)
        info = self.path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077:
            raise Rejected('mirror_database_permissions')
        if read_local(self.root, 'identity.json', 4096) != self.identity:
            raise Rejected('mirror_identity_changed')

    @contextmanager
    def connection(self, write=False):
        self._check_files()
        db = sqlite3.connect(self.path.as_uri()+'?mode=rw', uri=True, timeout=5, isolation_level=None)
        try:
            db.execute('PRAGMA synchronous=FULL'); db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _load(self, db, expected=None):
        rows = db.execute('SELECT id,generation,bundle,bundle_digest,previous FROM snapshot LIMIT 2').fetchall()
        if len(rows) != 1 or rows[0][0] != 1:
            raise Rejected('mirror_snapshot_missing')
        cached = self._cache
        if cached is not None and rows[0] == cached[0]:
            return self._loaded(cached, expected)
        _, generation, data, digest, previous = rows[0]
        integer(generation, 0, 2**63-1); hex_digest(digest)
        if generation == 0:
            if data is not None or previous is not None or digest != ORIGIN['head']:
                raise Rejected('mirror_initial_state')
            current = {'generation': 0, 'registry_checkpoint': dict(ORIGIN), 'bundle_digest': ORIGIN['head']}
            value = state = None; prior = None
        else:
            value = decode(data, max_bytes=MAX_BUNDLE, max_nodes=32768)
            fields(value, ('schema', 'config', 'rows'))
            if type(value['rows']) is not list or not value['rows']:
                raise Rejected('mirror_snapshot_empty')
            final_row = value['rows'][-1]
            if type(final_row) is not list or len(final_row) != 4:
                raise Rejected('registry_row_shape')
            target = {'revision': final_row[0], 'head': row_head(final_row)}
            state = VerifiedRegistry.from_bundle(data, digest, self.registry_digest, self.authority_digest, target)
            current = {'generation': generation, 'registry_checkpoint': target, 'bundle_digest': digest}
            prior = receipt(decode(previous, max_bytes=4096))
            if prior['generation'] != generation-1 or prior['registry_checkpoint']['revision'] >= target['revision']:
                raise Rejected('mirror_previous_receipt')
            if prior['generation']:
                number = prior['registry_checkpoint']['revision']
                if row_head(value['rows'][number-1]) != prior['registry_checkpoint']['head']:
                    raise Rejected('mirror_previous_prefix')
                prefix = bundle_bytes(value['config'], value['rows'][:number])
                if sha256(prefix) != prior['bundle_digest']:
                    raise Rejected('mirror_previous_digest')
        cached = (rows[0], canonical(current), data, state, canonical(prior) if prior is not None else None)
        self._cache = cached
        return self._loaded(cached, expected)

    @staticmethod
    def _loaded(cached, expected):
        current = decode(cached[1], max_bytes=4096)
        if expected is not None:
            receipt(expected)
            if canonical(current) != canonical(expected):
                raise Rejected('mirror_receipt_mismatch')
        return {'receipt': current, 'data': cached[2], 'state': cached[3],
                'previous': decode(cached[4], max_bytes=4096) if cached[4] is not None else None}

    def clear_cache(self):
        """Drop the one retained public snapshot; the next read performs full replay again."""
        self._cache = None

    def status(self, expected=None):
        with self.connection() as db:
            snapshot = self._load(db, expected)
        return {'receipt': snapshot['receipt'], 'initialized': snapshot['data'] is not None,
                'external_receipt_checked': expected is not None, 'independent_freshness': False}

    def accept(self, data, digest, target, expected):
        receipt(expected); checkpoint(target)
        incoming = VerifiedRegistry.from_bundle(data, digest, self.registry_digest, self.authority_digest, target)
        value = decode(data, max_bytes=MAX_BUNDLE, max_nodes=32768)
        with self.connection(write=True) as db:
            stored = self._load(db); current = stored['receipt']
            if (stored['data'] == data and current['bundle_digest'] == digest and
                    current['registry_checkpoint'] == target and expected in (current, stored['previous'])):
                return {'accepted': True, 'advanced': False, 'idempotent_retry': True, 'receipt': current}
            if canonical(current) != canonical(expected):
                raise Rejected('mirror_receipt_mismatch')
            old = current['registry_checkpoint']
            if target['revision'] <= old['revision']:
                raise Rejected('mirror_not_forward')
            if old['revision'] and row_head(value['rows'][old['revision']-1]) != old['head']:
                raise Rejected('mirror_fork')
            generation = integer(current['generation']+1, 1, 2**63-1)
            new_receipt = {'generation': generation, 'registry_checkpoint': target, 'bundle_digest': digest}
            db.execute('UPDATE snapshot SET generation=?,bundle=?,bundle_digest=?,previous=? WHERE id=1',
                       (generation, data, digest, canonical(current)))
        # Every future use still rereads SQLite and requires exact equality of all row fields.
        self._cache = ((1, generation, data, digest, canonical(current)), canonical(new_receipt),
                       data, incoming, canonical(current))
        return {'accepted': True, 'advanced': True, 'idempotent_retry': False, 'receipt': new_receipt}

    def export(self, expected):
        receipt(expected)
        with self.connection() as db:
            snapshot = self._load(db, expected)
        if snapshot['data'] is None:
            raise Rejected('mirror_not_initialized')
        return snapshot['data']

    def publish(self, output, expected):
        data = self.export(expected); output = Path(output).absolute(); private_parent(output.parent)
        publish_local(output.parent, output.name, data)
        if read_local(output.parent, output.name, MAX_BUNDLE) != data:
            raise Rejected('mirror_publication_changed')
        return {'published': True, 'bundle_digest': sha256(data), 'receipt': expected}

    def verify(self, expected, registration_receipt, data, digest, dossier, dossier_digest, pins):
        receipt(expected)
        # Serialize adoption of revocations and verification against the receiver's accepted view.
        with self.connection(write=True) as db:
            snapshot = self._load(db, expected)
            if snapshot['data'] is None:
                raise Rejected('mirror_not_initialized')
            current = snapshot['receipt']
            report = snapshot['state'].verify(registration_receipt, data, digest, dossier, dossier_digest, pins)
        return {'mirror_receipt': current, 'registry_report': report,
                'limits': {'uses_locally_accepted_registry_snapshot': True, 'network_sync_implemented': False,
                           'independent_freshness': False, 'whole_database_rollback_requires_external_receipt': True}}
