"""Scoped, signed key lifecycle and attestation registration with externally pinned heads."""
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
import re
import secrets
import sqlite3
import stat
from types import MappingProxyType

from .audit import GENESIS
from .codec import Rejected, canonical, decode, fields, identifier, integer
from .dossier_attestation import (backend, check_public, private_parent,
                                 public_bytes, verify_attestation)
from .files import create_local, publish_local, read_local, sha256
from .receipts import hex_digest
from .review_dossier import validate_pins
from .review_policy import reason_text

ORIGIN = {'revision': 0, 'head': GENESIS}
DOMAIN = b'NQC-SIGNER-REGISTRY-v1\x00'
MAX_ROWS = 4096
MAX_KEYS = 64
MAX_EVENT_BYTES = 8192
MAX_BUNDLE = 32 * 1024 * 1024
EVENT_FIELDS = ('schema', 'registry_digest', 'request_id', 'reason', 'action', 'key_id',
                'new_public_key_hex', 'attestation_digest', 'dossier_digest', 'pins')


def checkpoint(value):
    fields(value, ('revision', 'head'))
    integer(value['revision'], 0, MAX_ROWS)
    hex_digest(value['head'])
    if (value['revision'] == 0) != (value['head'] == GENESIS):
        raise Rejected('registry_checkpoint')
    return {'revision': value['revision'], 'head': value['head']}


def public_hex(value):
    if not isinstance(value, str) or re.fullmatch(r'[0-9a-f]{64}', value) is None:
        raise Rejected('registry_public_key_encoding')
    return bytes.fromhex(value)


def configuration(data, digest, authority_digest):
    hex_digest(digest)
    if not isinstance(data, bytes) or len(data) > 4096 or sha256(data) != digest:
        raise Rejected('registry_config_digest')
    value = decode(data, max_bytes=4096)
    fields(value, ('schema', 'nonce', 'tenant', 'asset', 'policy_digest', 'authority_public_key_hex'))
    if value['schema'] != 'nqc-signer-registry-config-v1' or canonical(value) != data:
        raise Rejected('registry_config_schema')
    hex_digest(value['nonce']); identifier(value['tenant']); identifier(value['asset'])
    hex_digest(value['policy_digest'])
    check_public(public_hex(value['authority_public_key_hex']), authority_digest)
    return value


def verify_signature(public_key, signature, message):
    if not isinstance(signature, str) or re.fullmatch(r'[0-9a-f]{128}', signature) is None:
        raise Rejected('registry_signature_encoding')
    _, public_type, invalid, unsupported = backend()
    try:
        public_type.from_public_bytes(public_key).verify(bytes.fromhex(signature), DOMAIN + message)
    except invalid as exc:
        raise Rejected('registry_signature_invalid') from exc
    except unsupported as exc:
        raise Rejected('attestation_algorithm_unavailable') from exc


def signed_row(authority_key, revision, previous, event):
    payload = canonical(event).decode()
    private_type, _, _, unsupported = backend()
    try:
        signature = private_type.from_private_bytes(authority_key).sign(
            DOMAIN + canonical([revision, previous, payload])).hex()
    except unsupported as exc:
        raise Rejected('attestation_algorithm_unavailable') from exc
    return [revision, payload, previous, signature]


def row_head(row):
    try:
        return sha256(canonical(row))
    except (TypeError, ValueError, UnicodeError) as exc:
        raise Rejected('registry_row_encoding') from exc


def advance_state(state, event, revision):
    fields(event, EVENT_FIELDS)
    if event['schema'] != 'nqc-signer-registry-event-v1' or event['registry_digest'] != state['registry_digest']:
        raise Rejected('registry_event_binding')
    identifier(event['request_id']); reason_text(event['reason']); hex_digest(event['key_id'])
    if event['request_id'] in state['requests']:
        raise Rejected('registry_duplicate_request')
    key_id, action, keys = event['key_id'], event['action'], state['keys']
    if action in ('activate', 'rotate'):
        public_key = public_hex(event['new_public_key_hex']); new_id = sha256(public_key)
        if new_id in keys or new_id == state['authority_digest']:
            raise Rejected('registry_key_reuse')
        if len(keys) >= MAX_KEYS:
            raise Rejected('registry_key_capacity')
        if any(event[name] is not None for name in ('attestation_digest', 'dossier_digest', 'pins')):
            raise Rejected('registry_event_fields')
        if action == 'activate':
            if state['active_key'] is not None or key_id != new_id:
                raise Rejected('registry_activation_state')
        else:
            if state['active_key'] != key_id or key_id not in keys or keys[key_id]['status'] != 'active':
                raise Rejected('registry_rotation_state')
            keys[key_id]['status'] = 'retired'; keys[key_id]['retired_revision'] = revision
        keys[new_id] = {'public_key_hex': public_key.hex(), 'status': 'active', 'activated_revision': revision,
                        'retired_revision': None, 'revoked_revision': None}
        state['active_key'] = new_id
    elif action == 'revoke':
        if any(event[name] is not None for name in ('new_public_key_hex', 'attestation_digest', 'dossier_digest', 'pins')):
            raise Rejected('registry_event_fields')
        if key_id not in keys or keys[key_id]['status'] == 'revoked':
            raise Rejected('registry_revocation_state')
        keys[key_id]['status'] = 'revoked'; keys[key_id]['revoked_revision'] = revision
        if state['active_key'] == key_id:
            state['active_key'] = None
    elif action == 'record':
        if state['active_key'] != key_id or key_id not in keys or keys[key_id]['status'] != 'active':
            raise Rejected('registry_signer_not_active')
        if event['new_public_key_hex'] is not None:
            raise Rejected('registry_event_fields')
        hex_digest(event['attestation_digest']); hex_digest(event['dossier_digest']); validate_pins(event['pins'])
        if any(event['pins'][name] != state['config'][name] for name in ('tenant', 'asset', 'policy_digest')):
            raise Rejected('registry_scope')
        if event['attestation_digest'] in state['records']:
            raise Rejected('registry_attestation_already_recorded')
        state['records'][event['attestation_digest']] = {'revision': revision, 'event': event}
    else:
        raise Rejected('registry_action')
    state['requests'][event['request_id']] = {'revision': revision, 'event': event}


def verify_rows(config_data, registry_digest, authority_digest, rows, expected):
    """Pure replay of authority-signed records. The expected head must come from outside."""
    expected = checkpoint(expected)
    config = configuration(config_data, registry_digest, authority_digest)
    if type(rows) not in (list, tuple) or len(rows) > MAX_ROWS:
        raise Rejected('registry_row_count')
    state = {'config': config, 'registry_digest': registry_digest, 'authority_digest': authority_digest,
             'checkpoint': dict(ORIGIN), 'keys': {}, 'active_key': None, 'records': {}, 'requests': {}}
    public_key = public_hex(config['authority_public_key_hex'])
    for number, row in enumerate(rows, 1):
        if type(row) not in (list, tuple) or len(row) != 4:
            raise Rejected('registry_row_shape')
        revision, payload, previous, signature = row
        integer(revision, 1, MAX_ROWS)
        if revision != number or previous != state['checkpoint']['head']:
            raise Rejected('registry_row_sequence')
        if not isinstance(payload, str):
            raise Rejected('registry_payload')
        try:
            encoded = payload.encode('utf-8')
        except UnicodeError as exc:
            raise Rejected('registry_payload') from exc
        if len(encoded) > MAX_EVENT_BYTES:
            raise Rejected('registry_payload')
        verify_signature(public_key, signature, canonical([revision, previous, payload]))
        event = decode(encoded, max_bytes=MAX_EVENT_BYTES)
        if canonical(event).decode() != payload:
            raise Rejected('registry_payload_canonical')
        advance_state(state, event, revision)
        head = row_head(list(row)); state['checkpoint'] = {'revision': revision, 'head': head}
        state['requests'][event['request_id']]['head'] = head
        if event['action'] == 'record':
            state['records'][event['attestation_digest']]['head'] = head
    if state['checkpoint'] != expected:
        raise Rejected('registry_checkpoint_mismatch')
    return state


def bundle_bytes(config, rows):
    data = canonical({'schema': 'nqc-signer-registry-bundle-v1', 'config': config, 'rows': [list(row) for row in rows]})
    if len(data) > MAX_BUNDLE:
        raise Rejected('registry_bundle_size')
    return data


def verify_bundle(data, digest, registry_digest, authority_digest, expected):
    hex_digest(digest)
    if not isinstance(data, bytes) or len(data) > MAX_BUNDLE:
        raise Rejected('registry_bundle_size')
    if sha256(data) != digest:
        raise Rejected('registry_bundle_digest')
    value = decode(data, max_bytes=MAX_BUNDLE, max_nodes=32768)
    fields(value, ('schema', 'config', 'rows'))
    if value['schema'] != 'nqc-signer-registry-bundle-v1' or canonical(value) != data:
        raise Rejected('registry_bundle_schema')
    return verify_rows(canonical(value['config']), registry_digest, authority_digest, value['rows'], expected)


class SignerRegistry:
    def __init__(self, root, registry_digest, authority_digest):
        self.root = Path(root).absolute(); self.path = self.root/'registry.sqlite3'
        self.digest, self.authority_digest = registry_digest, authority_digest
        self._check_files()
        self.config_data = read_local(self.root, 'config.json', 4096)
        self.config = configuration(self.config_data, registry_digest, authority_digest)

    @classmethod
    def create(cls, root, authority_public_key, authority_digest, tenant, asset, policy_digest):
        check_public(authority_public_key, authority_digest)
        identifier(tenant); identifier(asset); hex_digest(policy_digest)
        config = {'schema': 'nqc-signer-registry-config-v1', 'nonce': secrets.token_hex(32),
                  'tenant': tenant, 'asset': asset, 'policy_digest': policy_digest,
                  'authority_public_key_hex': authority_public_key.hex()}
        root = Path(root).absolute(); root.mkdir(mode=0o700, exist_ok=False)
        data = canonical(config); create_local(root, 'config.json', data); create_local(root, 'registry.sqlite3', b'')
        result = cls(root, sha256(data), authority_digest)
        with result.connection(write=True) as db:
            db.execute('CREATE TABLE entries (revision INTEGER PRIMARY KEY, payload TEXT NOT NULL, previous TEXT NOT NULL, signature TEXT NOT NULL)')
        return result

    def _check_files(self):
        private_parent(self.root)
        info = self.path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o077:
            raise Rejected('registry_database_permissions')

    @contextmanager
    def connection(self, write=False):
        self._check_files()
        if read_local(self.root, 'config.json', 4096) != self.config_data:
            raise Rejected('registry_configuration_changed')
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
        rows = db.execute('SELECT revision,payload,previous,signature FROM entries ORDER BY revision LIMIT ?', (MAX_ROWS+1,)).fetchall()
        head = {'revision': rows[-1][0], 'head': row_head(list(rows[-1]))} if rows else dict(ORIGIN)
        state = verify_rows(self.config_data, self.digest, self.authority_digest, rows, expected if expected is not None else head)
        return state, rows

    def administrator(self, key):
        if sha256(public_bytes(key)) != self.authority_digest:
            raise Rejected('registry_administrator_required')

    def status(self, expected=None):
        with self.connection() as db:
            state, _ = self._load(db, expected)
        return {'registry_digest': self.digest, 'checkpoint': state['checkpoint'], 'active_key': state['active_key'],
                'keys': state['keys'], 'registered_attestations': len(state['records']),
                'external_checkpoint_checked': expected is not None, 'independent_freshness': False}

    def _event(self, action, key_id, request_id, reason, public_key=None, attestation_digest=None, dossier_digest=None, pins=None):
        return {'schema': 'nqc-signer-registry-event-v1', 'registry_digest': self.digest, 'request_id': request_id,
                'reason': reason, 'action': action, 'key_id': key_id,
                'new_public_key_hex': public_key.hex() if public_key is not None else None,
                'attestation_digest': attestation_digest, 'dossier_digest': dossier_digest, 'pins': pins}

    def _append(self, db, key, state, rows, event, expected):
        expected = checkpoint(expected)
        previous_request = state['requests'].get(event['request_id'])
        if previous_request is not None:
            revision = previous_request['revision']
            previous = {'revision': revision-1, 'head': rows[revision-1][2]}
            if canonical(previous_request['event']) != canonical(event) or previous != expected:
                raise Rejected('registry_request_conflict')
            return {'applied': False, 'idempotent_retry': True,
                    'receipt': {'revision': revision, 'head': previous_request['head']},
                    'current_checkpoint': state['checkpoint']}
        if state['checkpoint'] != expected:
            raise Rejected('registry_checkpoint_mismatch')
        if len(rows) >= MAX_ROWS:
            raise Rejected('registry_capacity')
        row = signed_row(key, len(rows)+1, expected['head'], event)
        target = {'revision': row[0], 'head': row_head(row)}
        # Verify both transition and serialized capacity before committing a new record.
        verify_rows(self.config_data, self.digest, self.authority_digest, rows+[row], target)
        bundle_bytes(self.config, rows+[row])
        db.execute('INSERT INTO entries VALUES(?,?,?,?)', row)
        return {'applied': True, 'idempotent_retry': False, 'receipt': target, 'current_checkpoint': target}

    def change(self, authority_key, action, key_id, request_id, reason, expected, new_public_key=None):
        self.administrator(authority_key); checkpoint(expected); identifier(request_id); reason_text(reason)
        if action not in ('activate', 'rotate', 'revoke'):
            raise Rejected('registry_action')
        if new_public_key is not None:
            if not isinstance(new_public_key, bytes) or len(new_public_key) != 32:
                raise Rejected('registry_public_key_encoding')
        event = self._event(action, key_id, request_id, reason, new_public_key)
        with self.connection(write=True) as db:
            state, rows = self._load(db)
            return self._append(db, authority_key, state, rows, event, expected)

    def record(self, authority_key, data, digest, dossier, dossier_digest, pins, key_id, request_id, reason, expected):
        self.administrator(authority_key); checkpoint(expected); identifier(request_id); reason_text(reason); hex_digest(key_id)
        event = self._event('record', key_id, request_id, reason, attestation_digest=digest, dossier_digest=dossier_digest, pins=pins)
        with self.connection(write=True) as db:
            state, rows = self._load(db)
            if key_id not in state['keys']:
                raise Rejected('registry_unknown_key')
            public_key = public_hex(state['keys'][key_id]['public_key_hex'])
            verify_attestation(data, digest, dossier, dossier_digest, pins, public_key, key_id)
            return self._append(db, authority_key, state, rows, event, expected)

    def export(self, expected):
        checkpoint(expected)
        with self.connection() as db:
            _, rows = self._load(db, expected)
            data = bundle_bytes(self.config, rows)
        verify_bundle(data, sha256(data), self.digest, self.authority_digest, expected)
        return data

    def publish(self, output, expected):
        data = self.export(expected); output = Path(output).absolute(); private_parent(output.parent)
        publish_local(output.parent, output.name, data)
        persisted = read_local(output.parent, output.name, MAX_BUNDLE)
        if persisted != data:
            raise Rejected('registry_publication_changed')
        verify_bundle(persisted, sha256(data), self.digest, self.authority_digest, expected)
        return {'published': True, 'bundle_digest': sha256(data), 'checkpoint': expected, 'registry_digest': self.digest}


@dataclass(frozen=True, init=False, slots=True, weakref_slot=True)
class VerifiedRegistry:
    """Immutable result of full replay. Reuse only for this exact, externally pinned snapshot."""
    registry_digest: str
    authority_digest: str
    bundle_digest: str
    _checkpoint: tuple = field(repr=False)
    _keys: object = field(repr=False)
    _records: object = field(repr=False)

    def __init__(self):
        raise TypeError('VerifiedRegistry.from_bundle is required')

    @classmethod
    def from_bundle(cls, data, digest, registry_digest, authority_digest, expected):
        state = verify_bundle(data, digest, registry_digest, authority_digest, expected)
        result = object.__new__(cls)
        values = {'registry_digest': registry_digest, 'authority_digest': authority_digest, 'bundle_digest': digest,
                  '_checkpoint': (state['checkpoint']['revision'], state['checkpoint']['head']),
                  '_keys': MappingProxyType({identifier: (key['public_key_hex'], key['status'])
                                            for identifier, key in state['keys'].items()}),
                  '_records': MappingProxyType({digest: (entry['revision'], entry['head'], entry['event']['key_id'],
                        entry['event']['dossier_digest'], canonical(entry['event']['pins']))
                        for digest, entry in state['records'].items()})}
        for name, value in values.items():
            object.__setattr__(result, name, value)
        return result

    @property
    def checkpoint(self):
        return {'revision': self._checkpoint[0], 'head': self._checkpoint[1]}

    def verify(self, receipt, data, digest, dossier, dossier_digest, pins):
        receipt = checkpoint(receipt); hex_digest(digest)
        entry = self._records.get(digest)
        if entry is None or {'revision': entry[0], 'head': entry[1]} != receipt:
            raise Rejected('registry_attestation_not_recorded')
        _, _, key_id, expected_dossier, expected_pins = entry
        public_key_hex, status = self._keys[key_id]
        if status == 'revoked':
            raise Rejected('registry_signer_revoked')
        if expected_dossier != dossier_digest or expected_pins != canonical(pins):
            raise Rejected('registry_record_binding')
        report = verify_attestation(data, digest, dossier, dossier_digest, pins, public_hex(public_key_hex), key_id)
        return {'schema': 'nqc-registered-dossier-report-v1', 'registry_accepted': True,
                'registry_digest': self.registry_digest, 'registry_checkpoint': self.checkpoint, 'registration_receipt': receipt,
                'signer_status_at_checkpoint': status, 'signature_report': report,
                'limits': {'revocation_checked_at_supplied_checkpoint': True, 'independent_freshness': False,
                           'historical_issuance_time_attested': False, 'report_is_issuer_assertion': True,
                           'independent_custody': False, 'authority_key_rotation': False}}


def verify_registered(bundle, bundle_digest, registry_digest, authority_digest, current_checkpoint, receipt,
                      data, digest, dossier, dossier_digest, pins):
    """Fully replay a supplied snapshot, then verify the registered dossier against it."""
    checkpoint(receipt); hex_digest(digest)
    verified = VerifiedRegistry.from_bundle(bundle, bundle_digest, registry_digest, authority_digest, current_checkpoint)
    return verified.verify(receipt, data, digest, dossier, dossier_digest, pins)
