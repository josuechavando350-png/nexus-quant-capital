#!/usr/bin/env python3
"""One bounded capture/verification/delivery cycle for a paused Miner collector.

Each attempt uses a new durable directory. No local cursor can skip a revocation
or substitute for the database acknowledgment; retry re-verifies current sources.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import time

import archive_collection as archive
import prepare_postgres_collection as collection
from export_parquet import ExportError, _bounded_read, _check_path, _file_sha, _json, _sha

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import collection_transport as transport


def sync_collection(state, store, output, verifier, target, run_id):
    started = time.monotonic()
    state, store, verifier = map(_check_path, [state, store, verifier])
    output = _check_path(output, must_exist=False)
    transport.validate_target(target)
    transport.need(not output.exists() and all(output != p and p not in output.parents
                   and output not in p.parents for p in [state, store, verifier]), 'new disjoint job directory required')
    owner = _json(_bounded_read(state / 'owner.json', 65536))
    transport.need(owner['run_id'] == run_id and owner['namespace'] == 'nqc_miner_v1'
                   and owner['producer'] == 'nqc-miner' and owner['data_class'] == 'historical', 'source run identity')
    with archive.archive_lock(store) as locked:
        identity = _json(_bounded_read(locked / 'owner.json', 65536))
        transport.need(identity['archive_id'] == target['archive_id'], 'archive target mismatch')
    output.mkdir(mode=0o700)
    archive.new_json(output / 'job.json', {'schema': 'nqc-miner-collection-sync-job-v1',
        'parent_run_id': run_id, 'archive_id': target['archive_id'], 'database_id': target['database_id'],
        'target_sha256': _sha(transport.packed(target)), 'outcome': 'unknown',
        'observer_bridge_enabled': False, 'spending_authorized': False})
    archive.sync_dir(output); archive.sync_dir(output.parent)
    result = {'schema': 'nqc-miner-collection-sync-v1', 'outcome': 'unknown',
              'commit_confirmed': False, 'parent_run_id': run_id,
              'observer_bridge_enabled': False, 'spending_authorized': False}
    try:
        captured = archive.archive_collection(state, store, verifier,
            maximum_bytes=collection.MAX_SOURCE_BYTES, maximum_records=10000)
        archive.new_json(output / 'capture.json', captured)
        manifest = collection.prepare_collection(store, output / 'bundle', verifier,
            target['archive_id'], target['database_id'], run_id)
        # Lock order matches archive capture: archive, root, then children.
        # Hold these cooperative locks through delivery so the selected receipt
        # and live source cannot advance between freshness check and submission.
        with archive.archive_lock(store) as locked, ExitStack() as locks:
            history = archive.receipts(locked)
            key = _sha(archive.packed(['nqc_miner_v1', 'historical', run_id]))
            latest = next((r for r in reversed(history) if r['collection_key'] == key), None)
            transport.need(latest is not None and latest['sha256'] == manifest['receipt_sha256'], 'receipt superseded before delivery')
            locks.enter_context(archive.shared_source_lock(state))
            revoked = manifest['status'] == 'quarantined'
            files, windows = archive.inventory(state, control_only=revoked)
            if not revoked:
                for name in windows:
                    locks.enter_context(archive.shared_source_lock(state / name))
            def source_matches():
                current_files, _ = archive.inventory(state, control_only=revoked)
                transport.need(current_files == files and set(files) == set(manifest['source_files']), 'source inventory changed')
                for name, bound in files.items():
                    fingerprint = manifest['source_files'][name]
                    transport.need((state / name).stat().st_size == fingerprint['bytes'] and
                        _file_sha(state / name, bound) == fingerprint['sha256'], 'source changed before or during delivery')
            source_matches()
            delivered = transport.apply_bundle(output / 'bundle', target, output / 'delivery')
            # A noncooperating writer is outside the lock contract. Preserve the
            # committed delivery receipt but do not certify a current source.
            result.update(commit_confirmed=delivered['commit_confirmed'])
            source_matches()
            result.update(outcome=delivered['outcome'], receipt_sha256=manifest['receipt_sha256'],
                receipt_sequence=manifest['receipt_sequence'], request_sha256=manifest['request_sha256'],
                source_stable_through_delivery=True, windows=manifest['windows'], records=manifest['records'])
    except (ExportError, transport.DeliveryError, OSError, ValueError, KeyError, TypeError) as error:
        result['error_type'] = type(error).__name__
    result['elapsed_ms'] = round((time.monotonic() - started) * 1000)
    archive.new_json(output / 'result.json', result)
    metrics = ('# One bounded attempt; no long-running service is implied.\n'
               f'nqc_miner_sync_commit_confirmed {int(result["commit_confirmed"])}\n'
               f'nqc_miner_sync_applied {int(result["outcome"] == "applied")}\n'
               f'nqc_miner_sync_quarantined {int(result["outcome"] == "quarantined")}\n'
               f'nqc_miner_sync_unknown {int(result["outcome"] == "unknown")}\n'
               f'nqc_miner_sync_duration_seconds {result["elapsed_ms"] / 1000:.3f}\n')
    transport.write_new(output / 'metrics.prom', metrics.encode())
    archive.sync_dir(output)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['state', 'archive', 'output', 'verifier', 'target']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    try:
        result = sync_collection(args.state, args.archive, args.output, args.verifier,
                                 transport.parse(transport.read(args.target, 65536)), args.run_id)
    except (ExportError, transport.DeliveryError, OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'outcome': 'unknown', 'error_type': type(error).__name__}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return {'applied': 0, 'unknown': 2, 'quarantined': 3, 'superseded': 4}[result['outcome']]


if __name__ == '__main__':
    raise SystemExit(main())
