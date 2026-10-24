"""Local transactional evidence store with verified export/restore and revocation.

SQLite FULL synchronous commits; immutable objects/batches and hash-linked events.
This provides local durability tests, not distributed consensus, an authenticated
chain view, Rust-store integration, or a certified Evidence Vault.
"""
from __future__ import annotations

import contextlib
import os
from pathlib import Path
import re
import sqlite3
import stat
from urllib.parse import quote

from integrity import canonical, digest, strict_json

SCHEMA = "nqc.omega.evidence-store.v1"
BATCH_V2 = "nqc.omega.dependent-batch.v1"
HEX = re.compile(r"[0-9a-f]{64}\Z")
NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}\Z")
MAX_OBJECT = 2 * 1024 * 1024
MAX_OBJECTS = 256
MAX_TOTAL = 16 * 1024 * 1024
MAX_EVENTS = 10000
ZERO = '0' * 64
DDL = """
CREATE TABLE metadata (schema TEXT NOT NULL);
CREATE TABLE objects (sha256 TEXT PRIMARY KEY, payload BLOB NOT NULL);
CREATE TABLE batches (sha256 TEXT PRIMARY KEY, manifest BLOB NOT NULL);
CREATE TABLE journal (sequence INTEGER PRIMARY KEY, sha256 TEXT UNIQUE NOT NULL, event BLOB NOT NULL);
"""
TRIGGERS = {
    f'immutable_{table}_{action}': f'CREATE TRIGGER immutable_{table}_{action} BEFORE {action} ON {table} '
        "BEGIN SELECT RAISE(ABORT, 'append_only'); END"
    for table in ('metadata','objects','batches','journal') for action in ('UPDATE','DELETE')}
EXPECTED_SQL = {statement.split()[2]: statement.strip() for statement in DDL.strip().split(';')
                if statement.strip()}
EXPECTED_SQL.update(TRIGGERS)


def need(ok, message):
    if not ok:
        raise ValueError(message)


def safe_path(path):
    path = Path(path).absolute()
    need(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink_store_path')
    if path.exists():
        need(stat.S_ISREG(path.stat().st_mode), 'nonregular_store_path')
        # SQLite may create/open these sidecars; reject preplanted symlinks too.
    for suffix in ('-journal', '-wal', '-shm'):
        sidecar = Path(str(path) + suffix)
        need(not sidecar.is_symlink() and (not sidecar.exists() or sidecar.is_file()),
             'unsafe_store_sidecar')
    return path


def connect(path):
    path = safe_path(path)
    need(path.is_file(), 'store_missing')
    db = sqlite3.connect('file:' + quote(str(path), safe='/') + '?mode=rw',
                         uri=True, timeout=15, isolation_level=None)
    db.execute('PRAGMA trusted_schema=OFF')
    db.execute('PRAGMA synchronous=FULL')
    db.execute('PRAGMA foreign_keys=ON')
    return db


def create(path):
    path = safe_path(path)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    db = connect(path)
    try:
        db.executescript('BEGIN IMMEDIATE;' + DDL)
        db.execute('INSERT INTO metadata VALUES (?)', (SCHEMA,))
        for statement in TRIGGERS.values():
            db.execute(statement)
        db.execute('COMMIT')
    finally:
        db.close()
    parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    return path


def manifest_for(objects, parents=None):
    need(type(objects) is dict and 0 < len(objects) <= MAX_OBJECTS, 'invalid_object_inventory')
    need(all(type(n) is str and NAME.fullmatch(n) for n in objects), 'unsafe_object_name')
    need(all(type(b) is bytes and 0 < len(b) <= MAX_OBJECT for b in objects.values()), 'object_size')
    need(sum(map(len, objects.values())) <= MAX_TOTAL, 'total_size')
    manifest = {'schema': SCHEMA, 'objects': {n: {'sha256': digest(b), 'bytes': len(b)}
                                            for n, b in sorted(objects.items())}}
    if parents is not None:
        need(type(parents) in (list, tuple) and len(parents) <= MAX_OBJECTS,
             'invalid_dependencies')
        need(all(type(p) is str and HEX.fullmatch(p) for p in parents)
             and len(set(parents)) == len(parents), 'invalid_dependencies')
        manifest.update(schema=BATCH_V2, parents=sorted(parents))
    return manifest


def dependency_blocks(order, parents, revoked):
    """Replay a prior-admission DAG; retain all explicit revocation causes."""
    blocked = {}
    for batch in order:
        causes = {batch} if batch in revoked else set()
        for parent in parents[batch]:
            causes.update(blocked[parent])
        blocked[batch] = sorted(causes)
    return blocked


def decode(raw):
    need(type(raw) is bytes and len(raw) <= MAX_OBJECT, 'stored_object_size_or_type')
    value = strict_json(raw)
    need(canonical(value) == raw, 'stored_json_not_canonical')
    return value


def audit_connection(db):
    need(dict(db.execute("SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"))
         == EXPECTED_SQL, 'store_schema_changed')
    need(db.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'sqlite_integrity')
    need(db.execute('SELECT schema FROM metadata').fetchall() == [(SCHEMA,)], 'store_schema')
    # Bound reads before loading payloads from an untrusted local database.
    n, total, longest = db.execute('SELECT count(*),coalesce(sum(length(payload)),0),'
                                  'coalesce(max(length(payload)),0) FROM objects').fetchone()
    need(n <= MAX_OBJECTS and total <= MAX_TOTAL and longest <= MAX_OBJECT, 'store_object_bounds')
    objects = dict(db.execute('SELECT sha256,payload FROM objects'))
    for sha, raw in objects.items():
        need(type(sha) is str and HEX.fullmatch(sha) and type(raw) is bytes
             and raw and digest(raw) == sha, 'stored_object_digest')
    count,size=db.execute('SELECT count(*),coalesce(max(length(manifest)),0) FROM batches').fetchone()
    need(count <= MAX_OBJECTS and size <= MAX_OBJECT, 'batch_bounds')
    batches, parents = {}, {}
    referenced = set()
    for sha, raw in db.execute('SELECT sha256,manifest FROM batches'):
        manifest = decode(raw)
        need(digest(raw) == sha and type(manifest) is dict
             and ((manifest.get('schema') == SCHEMA and set(manifest) == {'schema','objects'})
                  or (manifest.get('schema') == BATCH_V2 and set(manifest) == {'schema','objects','parents'}))
             and type(manifest['objects']) is dict,
             'batch_manifest_invalid')
        need(0 < len(manifest['objects']) <= MAX_OBJECTS, 'batch_empty_or_oversized')
        resolved = {}
        for name, ref in manifest['objects'].items():
            need(type(name) is str and NAME.fullmatch(name) and type(ref) is dict
                 and set(ref) == {'sha256','bytes'} and type(ref['bytes']) is int,
                 'batch_object_reference')
            need(type(ref['sha256']) is str and ref['sha256'] in objects, 'missing_object')
            b = objects[ref['sha256']]
            need(len(b) == ref['bytes'], 'object_length_mismatch')
            referenced.add(ref['sha256'])
            resolved[name] = b
        deps = manifest.get('parents')
        if manifest['schema'] == BATCH_V2:
            need(type(deps) is list, 'invalid_dependencies')
        need(canonical(manifest_for(resolved, deps)) == raw, 'manifest_reconstruction')
        batches[sha] = manifest
        parents[sha] = deps if deps is not None else []
    need(all(p in batches and p != b for b in parents for p in parents[b]),
         'dependency_missing_or_self')
    count,size=db.execute('SELECT count(*),coalesce(max(length(event)),0) FROM journal').fetchone()
    need(count <= MAX_EVENTS and size <= MAX_OBJECT, 'journal_bounds')
    previous, sequence = ZERO, 0
    admitted, revoked = set(), set()
    order, blocked = [], {}
    events = []
    for index, sha, raw in db.execute('SELECT sequence,sha256,event FROM journal ORDER BY sequence'):
        event = decode(raw)
        need(type(event) is dict and set(event) == {'schema','sequence','previous','kind','batch','reason','evidence'},
             'journal_shape')
        sequence += 1
        need(index == sequence and type(event['sequence']) is int and event['sequence'] == index
             and event['previous'] == previous and event['schema'] == SCHEMA and digest(raw) == sha,
             'journal_chain_mismatch')
        batch = event['batch']
        need(type(batch) is str and batch in batches, 'journal_unknown_batch')
        if event['kind'] == 'ADMIT':
            need(batch not in admitted and event['reason'] is None and event['evidence'] is None,
                 'duplicate_or_invalid_admission')
            need(all(p in admitted and not blocked[p] for p in parents[batch]),
                 'dependency_not_active_at_admission')
            admitted.add(batch)
            order.append(batch)
            blocked[batch] = []
        elif event['kind'] == 'REVOKE':
            need(batch in admitted and batch not in revoked and type(event['reason']) is str
                 and 0 < len(event['reason']) <= 200 and type(event['evidence']) is str
                 and event['evidence'] in objects, 'invalid_revocation')
            referenced.add(event['evidence'])
            revoked.add(batch)
            blocked = dependency_blocks(order, parents, revoked)
        else:
            raise ValueError('unknown_journal_event')
        previous = sha
        events.append(event)
    need(admitted == set(batches), 'uncommitted_batch')
    need(referenced == set(objects), 'uncommitted_object')
    result = {'schema': SCHEMA, 'object_count': len(objects), 'batch_count': len(batches),
        'event_count': len(events), 'journal_head': previous,
        'active_batches': sorted(b for b in admitted if not blocked[b]), 'revoked_batches': sorted(revoked),
        'local_integrity_verified': True, 'remote_replication_verified': False,
        'canonical_chain_verified': False, 'census_closed': False}
    if any(m['schema'] == BATCH_V2 for m in batches.values()):
        result.update(dependency_policy='DECLARED_TRANSITIVE_V1', dependencies=parents,
                      invalidated_batches=sorted(b for b in admitted-revoked if blocked[b]),
                      blocking_revocations={b: blocked[b] for b in sorted(admitted) if blocked[b]})
    return result


@contextlib.contextmanager
def transaction(path, write=False):
    db = connect(path)
    try:
        db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        audit_connection(db)
        yield db
        audit_connection(db)
        db.execute('COMMIT')
    except BaseException:
        if db.in_transaction:
            db.execute('ROLLBACK')
        raise
    finally:
        db.close()


def audit_store(path, expected_head=None):
    with transaction(path) as db:
        result = audit_connection(db)
        if expected_head is not None:
            need(result['journal_head'] == expected_head, 'external_checkpoint_mismatch')
        return result


def insert_object(db, raw):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_OBJECT, 'object_size')
    sha = digest(raw)
    old = db.execute('SELECT payload FROM objects WHERE sha256=?', (sha,)).fetchone()
    if old:
        need(old[0] == raw, 'object_collision')
    else:
        db.execute('INSERT INTO objects VALUES (?,?)', (sha, raw))
    return sha


def journal_event(db, kind, batch, reason=None, evidence=None):
    last = db.execute('SELECT sequence,sha256 FROM journal ORDER BY sequence DESC LIMIT 1').fetchone()
    index, prev = (last[0]+1, last[1]) if last else (1, ZERO)
    event = {'schema': SCHEMA, 'sequence': index, 'previous': prev, 'kind': kind,
             'batch': batch, 'reason': reason, 'evidence': evidence}
    raw = canonical(event)
    db.execute('INSERT INTO journal VALUES (?,?,?)', (index, digest(raw), raw))


def admit(path, objects, *, parents=None, _fault=None):
    """Publish under one lock. parents=None preserves legacy batch-local identity.

    An explicit list (including []) creates a dependency-aware manifest. The
    caller declares logical dependence; shared bytes alone do not infer it.
    """
    manifest = canonical(manifest_for(objects, parents))
    batch = digest(manifest)
    with transaction(path, write=True) as db:
        status = audit_connection(db)
        need(batch not in status['revoked_batches'], 'cannot_readmit_revoked_batch')
        need(batch not in status.get('invalidated_batches', []), 'cannot_readmit_invalidated_batch')
        if parents is not None:
            need(all(p in status['active_batches'] for p in parents), 'dependency_inactive_or_missing')
        if batch in status['active_batches']:
            return batch
        for raw in objects.values():
            insert_object(db, raw)
        if _fault:
            _fault('objects_written')
        db.execute('INSERT INTO batches VALUES (?,?)', (batch, manifest))
        journal_event(db, 'ADMIT', batch)
        if _fault:
            _fault('before_commit')
    if _fault:
        _fault('after_commit')
    return batch


def read_batch(path, batch, *, include_revoked=False):
    """Default excludes all blocked batches; forensic override includes descendants."""
    need(type(batch) is str and HEX.fullmatch(batch), 'invalid_batch_id')
    with transaction(path) as db:
        status = audit_connection(db)
        need(batch in status['active_batches'] or
             (include_revoked and batch in status['revoked_batches'] + status.get('invalidated_batches', [])),
             'batch_inactive_or_missing')
        manifest = decode(db.execute('SELECT manifest FROM batches WHERE sha256=?',(batch,)).fetchone()[0])
        return {name: db.execute('SELECT payload FROM objects WHERE sha256=?',(ref['sha256'],)).fetchone()[0]
                for name, ref in manifest['objects'].items()}


def revoke(path, batch, reason, evidence, *, _fault=None):
    """Exclude a batch locally; supplied evidence does not establish chain truth."""
    need(type(reason) is str and 0 < len(reason) <= 200, 'invalid_revocation_reason')
    need(type(batch) is str and HEX.fullmatch(batch), 'invalid_batch_id')
    with transaction(path, write=True) as db:
        status = audit_connection(db)
        need(batch in status['active_batches'] + status.get('invalidated_batches', []),
             'batch_inactive_or_missing')
        proof = insert_object(db, evidence)
        if _fault: _fault('proof_written')
        journal_event(db, 'REVOKE', batch, reason, proof)
        if _fault: _fault('before_commit')
    if _fault: _fault('after_commit')


def export_store(path):
    """Deterministic inventory, includes inactive evidence and its original journal."""
    with transaction(path) as db:
        export = {'schema': SCHEMA, 'objects': [
            {'sha256': sha, 'hex': raw.hex()} for sha, raw in db.execute('SELECT sha256,payload FROM objects ORDER BY sha256')],
            'batches': [decode(raw) for raw, in db.execute('SELECT manifest FROM batches ORDER BY sha256')],
            'journal': [decode(raw) for raw, in db.execute('SELECT event FROM journal ORDER BY sequence')]}
    export['snapshot_sha256'] = digest(canonical(export))
    return export


def restore_store(path, snapshot):
    """Restore to a new file; verify every byte and journal link before publishing."""
    need(type(snapshot) is dict and set(snapshot) == {'schema','objects','batches','journal','snapshot_sha256'},
         'snapshot_shape')
    need(snapshot['schema'] == SCHEMA and snapshot['snapshot_sha256'] == digest(canonical(
         {k:v for k,v in snapshot.items() if k != 'snapshot_sha256'})), 'snapshot_digest')
    need(all(type(snapshot[k]) is list for k in ('objects','batches','journal')), 'snapshot_list_required')
    need(len(snapshot['objects']) <= MAX_OBJECTS and len(snapshot['batches']) <= MAX_OBJECTS
         and len(snapshot['journal']) <= MAX_EVENTS, 'snapshot_bounds')
    need(all(type(o) is dict and type(o.get('hex')) is str for o in snapshot['objects'])
         and sum(len(o['hex']) for o in snapshot['objects']) <= MAX_TOTAL*2, 'snapshot_total_bounds')
    path = safe_path(path)
    need(not path.exists(), 'restore_destination_exists')
    # Build under a unique sibling, then link without replacing any existing file.
    import tempfile
    fd, name = tempfile.mkstemp(prefix='.omega-restore-', dir=path.parent)
    os.close(fd)
    temp = Path(name)
    temp.unlink()
    try:
        create(temp)
        with transaction(temp, write=True) as db:
            seen = set()
            for obj in snapshot['objects']:
                need(type(obj) is dict and set(obj) == {'sha256','hex'} and type(obj['hex']) is str
                     and len(obj['hex']) <= MAX_OBJECT*2, 'snapshot_object')
                raw = bytes.fromhex(obj['hex'])
                need(raw.hex() == obj['hex'] and digest(raw) == obj['sha256']
                     and obj['sha256'] not in seen, 'snapshot_object_digest_or_duplicate')
                seen.add(obj['sha256'])
                insert_object(db, raw)
            for manifest in snapshot['batches']:
                raw = canonical(manifest)
                db.execute('INSERT INTO batches VALUES (?,?)', (digest(raw), raw))
            for event in snapshot['journal']:
                raw = canonical(event)
                db.execute('INSERT INTO journal VALUES (?,?,?)', (event['sequence'], digest(raw), raw))
        need(canonical(export_store(temp)) == canonical(snapshot), 'snapshot_not_canonical_inventory')
        os.link(temp, path)
        parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    finally:
        temp.unlink(missing_ok=True)
    return audit_store(path)
