#!/usr/bin/env python3
"""Bounded historical collector/archive/PostgreSQL worker with durable recovery.

Own workspace only. Every restart reconciles current verified source before any
new RPC poll. No successful local cursor substitutes for PostgreSQL readback.
Does not provision infrastructure, install a service or operate funds.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid

import archive_collection as archive
import sync_postgres_collection as sync
from export_parquet import ExportError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import collection_transport as transport
from bind_run_config import BindError, validate_about

MAX_CAPTURE = 1024 * 1024


def binary_digest(path):
    # Cargo's executable commonly has a second hard link in target/debug/deps.
    # Read-only hashing permits that; private mutable job/config files do not.
    transport.safe_path(path)
    digest = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        transport.need(stat.S_ISREG(before.st_mode) and before.st_size <= 128 * 1024 * 1024,
                       'bounded regular executable required')
        total = 0
        while chunk := stream.read(1024 * 1024):
            total += len(chunk)
            transport.need(total <= 128 * 1024 * 1024, 'executable grew beyond bound')
            digest.update(chunk)
        fingerprint = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        transport.need(fingerprint(before) == fingerprint(os.fstat(stream.fileno()))
                       == fingerprint(path.lstat()), 'executable changed while hashing')
    return digest.hexdigest()


def command(arguments, *, timeout, output=None):
    """Bound and reap only our child process group, including on interruption.

    Capture into temporary files, enforce byte/time limits, retain hashes rather
    than untrusted stderr. The caller chooses whether to persist parsed stdout.
    """
    start = time.monotonic(); limited = False
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        child = subprocess.Popen([str(x) for x in arguments], stdin=subprocess.DEVNULL,
            stdout=out, stderr=err, start_new_session=True)
        try:
            while child.poll() is None:
                if time.monotonic() - start >= timeout or max(os.fstat(out.fileno()).st_size,
                        os.fstat(err.fileno()).st_size) > MAX_CAPTURE:
                    limited = True
                    break
                time.sleep(0.02)
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
            child.wait()
        out.seek(0); err.seek(0)
        stdout = out.read(MAX_CAPTURE + 1); stderr = err.read(MAX_CAPTURE + 1)
        limited = limited or len(stdout) > MAX_CAPTURE or len(stderr) > MAX_CAPTURE
    result = {'exit_code': child.returncode, 'limited': limited,
        'stdout_sha256': transport.sha(stdout), 'stderr_sha256': transport.sha(stderr),
        'elapsed_ms': round((time.monotonic() - start) * 1000)}
    if output is not None:
        archive.new_json(output, result)
    transport.need(not limited, 'bounded command exceeded its limit')
    return result, stdout


def private_directory(path):
    path = transport.safe_path(path)
    info = path.stat()
    transport.need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                   and stat.S_IMODE(info.st_mode) == 0o700, 'private owned directory required')
    return path


@contextmanager
def workspace_lock(path, identity):
    path = transport.safe_path(path, new=True)
    if not path.exists():
        path.mkdir(mode=0o700)
        archive.new_json(path / 'owner.json', identity)
        transport.write_new(path / 'worker.lock', b'nqc-miner-worker-lock-v1\n')
        (path / 'sessions').mkdir(mode=0o700)
        archive.sync_dir(path); archive.sync_dir(path.parent)
    private_directory(path); private_directory(path / 'sessions')
    transport.need(json.dumps(transport.parse(transport.read(path / 'owner.json', 65536)), sort_keys=True)
                   == json.dumps(identity, sort_keys=True),
                   'worker ownership or configuration changed')
    lock = path / 'worker.lock'
    transport.need(transport.read(lock, 64) == b'nqc-miner-worker-lock-v1\n', 'worker lock marker')
    fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
    try:
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc: raise transport.DeliveryError('worker already running') from exc
        info = os.fstat(fd)
        transport.need((info.st_dev, info.st_ino) == (lock.stat().st_dev, lock.stat().st_ino), 'worker lock replaced')
        transport.need(len(list((path / 'sessions').iterdir())) < 1000, 'worker session limit; retain evidence and review a new workspace')
        yield path
    finally:
        os.close(fd)


def validate(state, store, binary, workspace, target):
    state, store, binary = [transport.safe_path(p) for p in [state, store, binary]]
    workspace = transport.safe_path(workspace, new=True)
    paths = [state, store, binary, workspace]
    transport.need(all(a != b and a not in b.parents and b not in a.parents
                   for i, a in enumerate(paths) for b in paths[i+1:]), 'worker paths must be disjoint')
    transport.validate_target(target)
    config = transport.parse(transport.read(state / 'config.json', MAX_CAPTURE))
    transport.need(config.get('schema_version') == 2 and config.get('data_class') == 'historical'
                   and len(config.get('scopes', [])) == 1, 'single historical collector required')
    digest = binary_digest(binary)
    result, raw = command([binary, 'about'], timeout=30)
    transport.need(result['exit_code'] == 0, 'binary identity unavailable')
    about = transport.parse(raw); validate_about(about)
    for key in ['code_commit', 'cargo_lock_sha256', 'build_identity_sha256']:
        transport.need(config.get(key) == about[key], 'collector plan/build mismatch')
    result, raw = command([binary, 'validate-config', '--config', state / 'config.json'], timeout=30)
    transport.need(result['exit_code'] == 0, 'collector plan invalid')
    plan_hash = transport.parse(raw)['config_sha256']
    archive_owner = transport.parse(transport.read(store / 'owner.json', 65536))
    transport.need(archive_owner['archive_id'] == target['archive_id'], 'archive/target mismatch')
    identity = {'schema': 'nqc-miner-collector-worker-v1', 'namespace': 'nqc_miner_v1', 'producer': 'nqc-miner',
        'state': str(state), 'archive': str(store), 'binary': str(binary), 'binary_sha256': digest,
        'plan_sha256': plan_hash, 'config_file_sha256': transport.sha(transport.read(state / 'config.json', MAX_CAPTURE)),
        'target_sha256': transport.sha(transport.packed(target)), 'run_id': config['run_id'],
        'archive_id': target['archive_id'], 'database_id': target['database_id'],
        'observer_bridge_enabled': False, 'signing_enabled': False, 'spending_authorized': False}
    return state, store, binary, workspace, identity


def run(state, store, binary, workspace, target, *, cycles=1, timeout=120):
    transport.need(type(cycles) is int and 1 <= cycles <= 16, 'cycles must be 1..16')
    transport.need(type(timeout) is int and 1 <= timeout <= 600, 'poll timeout must be 1..600 seconds')
    state, store, binary, workspace, identity = validate(state, store, binary, workspace, target)
    with workspace_lock(workspace, identity):
        session = workspace / 'sessions' / str(uuid.uuid4()); session.mkdir(mode=0o700)
        archive.new_json(session / 'attempt.json', {'schema': 'nqc-miner-worker-attempt-v1',
            'owner_sha256': transport.sha(transport.packed(identity)), 'cycles_requested': cycles,
            'poll_timeout_seconds': timeout, 'outcome': 'unknown'})
        archive.sync_dir(session); archive.sync_dir(session.parent)
        result = {'schema': 'nqc-miner-worker-result-v1', 'outcome': 'unknown', 'session': str(session),
            'polls_started': 0, 'cycles_applied': 0, 'last_sync_commit_confirmed': False,
            'observer_bridge_enabled': False, 'spending_authorized': False,
            'economic_certification': False, 'production_integration': False,
            'persistent_service_installed': False}
        started = time.monotonic()
        def stable():
            transport.need(binary_digest(binary) == identity['binary_sha256']
                and transport.sha(transport.read(state / 'config.json', MAX_CAPTURE)) == identity['config_file_sha256'],
                'worker binary or plan changed')
        def reconcile(directory):
            result['last_sync_commit_confirmed'] = False
            stable()
            value = sync.sync_collection(state, store, directory, binary, target, identity['run_id'])
            stable()
            result['last_sync_commit_confirmed'] = value['commit_confirmed']
            result['last_sync_outcome'] = value['outcome']
            result['last_completed_windows'] = value.get('windows')
            return value['outcome']
        try:
            # Always replay from verified source, including after SIGKILL. This
            # propagates parent quarantine before any attempted fresh RPC read.
            outcome = reconcile(session / 'recovery')
            if outcome != 'applied':
                result['outcome'] = outcome
            else:
                for index in range(cycles):
                    if result['last_completed_windows'] is None or result['last_completed_windows'] >= 64:
                        result['outcome'] = 'capacity_reached'
                        break
                    stable()
                    cycle = session / f'cycle-{index:04}'; cycle.mkdir(mode=0o700)
                    archive.sync_dir(session)
                    archive.new_json(cycle / 'attempt.json', {'status': 'unknown', 'poll': index})
                    archive.sync_dir(cycle)
                    result['polls_started'] += 1
                    poll_error = None
                    try:
                        poll, _ = command([binary, 'follow', '--config', state / 'config.json',
                            '--state', state, '--max-polls', '1', '--poll-seconds', '1'],
                            timeout=timeout, output=cycle / 'poll.json')
                        if poll['exit_code'] != 0: poll_error = 'collector_nonzero_exit'
                    except (transport.DeliveryError, OSError) as exc:
                        poll_error = type(exc).__name__
                    # Even a failed poll may have durably written a revocation.
                    # Reconcile it; never advance again after a failed poll.
                    outcome = reconcile(cycle / 'sync')
                    if outcome != 'applied' or poll_error:
                        result['outcome'] = 'quarantined' if outcome == 'quarantined' else 'unknown'
                        if poll_error: result['poll_error'] = poll_error
                        break
                    result['cycles_applied'] += 1
                else:
                    result['outcome'] = 'applied'
        except (ExportError, transport.DeliveryError, BindError, OSError, ValueError, KeyError, TypeError) as exc:
            result.update(outcome='unknown', error_type=type(exc).__name__)
        result['elapsed_ms'] = round((time.monotonic() - started) * 1000)
        archive.new_json(session / 'result.json', result)
        metrics = ''.join(f'nqc_miner_worker_{key} {value}\n' for key, value in {
            'polls_started': result['polls_started'], 'cycles_applied': result['cycles_applied'],
            'applied': int(result['outcome'] == 'applied'), 'quarantined': int(result['outcome'] == 'quarantined'),
            'unknown': int(result['outcome'] == 'unknown'),
            'superseded': int(result['outcome'] == 'superseded'),
            'capacity_reached': int(result['outcome'] == 'capacity_reached'),
            'duration_seconds': result['elapsed_ms'] / 1000}.items())
        transport.write_new(session / 'metrics.prom', metrics.encode()); archive.sync_dir(session)
        return result


def main():
    def terminate(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['state', 'archive', 'binary', 'workspace', 'target']: p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--cycles', type=int, default=1); p.add_argument('--timeout', type=int, default=120)
    args = p.parse_args()
    try:
        result = run(args.state, args.archive, args.binary, args.workspace,
            transport.parse(transport.read(args.target, 65536)), cycles=args.cycles, timeout=args.timeout)
    except (ExportError, transport.DeliveryError, BindError, OSError, ValueError, KeyError, TypeError) as exc:
        result = {'outcome': 'unknown', 'error_type': type(exc).__name__}
    print(json.dumps(result, sort_keys=True))
    return {'applied': 0, 'unknown': 2, 'quarantined': 3, 'superseded': 4, 'capacity_reached': 5}[result['outcome']]


if __name__ == '__main__': raise SystemExit(main())
