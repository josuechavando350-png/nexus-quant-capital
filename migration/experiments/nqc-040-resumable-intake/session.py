"""Crash-aware local session for the unchanged eight-read NQC038 plan.

This is NOT a distributed quota service. One trusted, persistent session directory
must survive every run. Losing/rolling back/copying it requires stopping, never
creating a replacement budget. No CLI accepts or requests a credential.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
EXPERIMENTS = ROOT.parent
sys.path.insert(0, str(EXPERIMENTS / 'nqc-038-archive-access'))
import triport_intake as t

SCHEMA = 'nqc040-local-session-v1'
FILES = [
    'nqc-037-historical-state/src/verify.py',
    'nqc-037-historical-state/src/intake.py',
    'nqc-037-historical-state/vendor/nqc031/storage_proof.py',
    'nqc-037-historical-state/vendor/nqc031/util.py',
    'nqc-037-historical-state/inputs/TARGET.json',
    'nqc-037-historical-state/inputs/parent-header.json',
    'nqc-037-historical-state/inputs/target-header.json',
    'nqc-037-historical-state/inputs/l1-observations.json',
    'nqc-038-archive-access/triport_intake.py',
    'nqc-040-resumable-intake/session.py',
]


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False, allow_nan=False) + '\n').encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def binding():
    return {'specification_sha256': digest(encoded(t.specification())),
            'files': {name: digest((EXPERIMENTS / name).read_bytes()) for name in FILES}}


def atomic_bytes(path, raw):
    """Commit bytes and directory entry before returning (POSIX filesystem)."""
    fd, temporary = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def initialize(directory):
    """Offline, explicit initialization. Never called automatically by run()."""
    directory = Path(directory)
    directory.mkdir(mode=0o700)  # Existing, lost or ambiguous sessions cannot reset.
    (directory / '.lock').touch(mode=0o600, exist_ok=False)
    journal = {'schema': SCHEMA, 'binding': binding(), 'entries': []}
    atomic_bytes(directory / 'SESSION.json', encoded(journal))
    return directory


@contextmanager
def locked(directory):
    t.v.require(directory.is_dir() and not directory.is_symlink(), 'Session directory missing or unsafe')
    lock = directory / '.lock'
    t.v.require(lock.is_file() and not lock.is_symlink(), 'Session lock missing or unsafe')
    with lock.open('r+b') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise t.v.ValidationError('Session already in use') from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def read_journal(directory):
    path = directory / 'SESSION.json'
    t.v.require(path.is_file() and not path.is_symlink(), 'Session journal missing or unsafe')
    journal = t.v.read_json(path, limit=64 * 1024)
    t.v.require(isinstance(journal, dict) and set(journal) == {'schema', 'binding', 'entries'},
                'Session schema mismatch')
    t.v.require(journal['schema'] == SCHEMA and journal['binding'] == binding(),
                'Session code, input or plan binding mismatch')
    rows = journal['entries']
    t.v.require(isinstance(rows, list) and len(rows) <= 8, 'Session budget invalid')
    for index, row in enumerate(rows, 1):
        t.v.require(isinstance(row, dict) and type(row.get('id')) is int and row['id'] == index,
                    'Session request order invalid')
        status = row.get('status')
        t.v.require(status in {'reserved', 'received', 'verified', 'rejected'}, 'Session status invalid')
        expected = {'id', 'status'}
        if status in {'received', 'verified'} or (status == 'rejected' and 'response_sha256' in row):
            expected.add('response_sha256')
            value = row.get('response_sha256')
            t.v.require(isinstance(value, str) and len(value) == 64 and
                        all(c in '0123456789abcdef' for c in value), 'Session response hash invalid')
        t.v.require(set(row) == expected, 'Session entry schema mismatch')
        t.v.require(index == len(rows) or status == 'verified', 'Session has a nonterminal incomplete step')
    return journal


def response_path(directory, operation):
    return directory / f"{operation['request']['id']:02d}-{operation['purpose']}.json"


def read_response(directory, operation, row):
    path = response_path(directory, operation)
    t.v.require(path.is_file() and not path.is_symlink(), 'Saved response missing or unsafe')
    with path.open('rb') as stream:
        raw = stream.read(t.MAX_RESPONSE + 1)
    t.v.require(len(raw) <= t.MAX_RESPONSE and digest(raw) == row['response_sha256'],
                'Saved response size or digest mismatch')
    return json.loads(raw, object_pairs_hook=t.v.no_duplicate_keys)


def summary(status, journal, verified):
    return {'status': status, 'attempt_slots_reserved': len(journal['entries']),
            'responses_verified': verified,
            'remaining_attempt_slots': 8 - len(journal['entries']),
            'quota_scope': 'one trusted persistent local session; no rollback or alternate directory',
            'gates': t.v.closed_gates()}


def run(directory, fetch=None, *, secret=None, max_new_requests=0):
    """Revalidate cached evidence first; default is offline inspection only.

Reservation is durable before fetch. A crash without a committed response is
ambiguous and stops the session permanently. A committed response is revalidated
offline. A rejected step never permits another request, even after restart.
"""
    t.v.require(type(max_new_requests) is int and 0 <= max_new_requests <= 8, 'Invalid per-run budget')
    if max_new_requests:
        t.v.require(callable(fetch) and isinstance(secret, str) and len(secret) >= 16,
                    'A guarded transport is required')
    directory = Path(directory)
    with locked(directory):
        journal = read_journal(directory)
        state = {}
        verified = 0
        sent_this_run = 0
        for operation in t.intake.plan():
            index = operation['request']['id'] - 1
            rows = journal['entries']
            if index < len(rows):
                row = rows[index]
                if row['status'] in {'reserved', 'rejected'}:
                    status = 'BLOCKED_AMBIGUOUS_ATTEMPT' if row['status'] == 'reserved' else 'BLOCKED_REJECTED_STEP'
                    return summary(status, journal, verified)
                response = read_response(directory, operation, row)
            else:
                if sent_this_run >= max_new_requests:
                    return summary('READY_FOR_NEXT_READ', journal, verified)
                row = {'id': index + 1, 'status': 'reserved'}
                rows.append(row)
                # Any write/fsync failure escapes before transport invocation.
                atomic_bytes(directory / 'SESSION.json', encoded(journal))
                sent_this_run += 1
                try:
                    response = fetch(operation)
                    raw = encoded(response)
                    t.v.require(secret.encode() not in raw, 'Credential echo refused')
                    t.v.require(len(raw) <= t.MAX_RESPONSE, 'Response byte limit')
                    t.intake.envelope(response, index + 1)
                except Exception:
                    # Never persist arbitrary exception names/messages or RPC error bodies.
                    row['status'] = 'rejected'
                    atomic_bytes(directory / 'SESSION.json', encoded(journal))
                    return summary('BLOCKED_REJECTED_STEP', journal, verified)
                path = response_path(directory, operation)
                t.v.require(not path.exists(), 'Unexpected existing response')
                atomic_bytes(path, raw)
                row.update(status='received', response_sha256=digest(raw))
                atomic_bytes(directory / 'SESSION.json', encoded(journal))
            try:
                t.intake.validate_step(operation, response, state)
            except Exception:
                row['status'] = 'rejected'
                atomic_bytes(directory / 'SESSION.json', encoded(journal))
                return summary('BLOCKED_REJECTED_STEP', journal, verified)
            verified += 1
            if row['status'] != 'verified':
                row['status'] = 'verified'
                atomic_bytes(directory / 'SESSION.json', encoded(journal))
        report = t.intake.result_report(state)
        report['session'] = summary('COMPLETE_RELATIVE_TO_OBSERVED_ROOTS', journal, verified)
        # Recomputed on every full offline inspection; old RESULTS is never authority.
        atomic_bytes(directory / 'RESULTS.json', encoded(report))
        return report


def collect(key, directory, *, max_new_requests=8):
    """Executor integration only; callers must supply an already authorized key."""
    transport = t.TriportTransport(key)
    return run(directory, transport, secret=key, max_new_requests=max_new_requests)
