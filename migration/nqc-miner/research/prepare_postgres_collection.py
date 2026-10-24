#!/usr/bin/env python3
"""Prepare the latest published collection, including permanent revocations.

Offline only. Never accepts an arbitrary child export or an unpublished object.
The archive UUID and target database UUID must both be supplied explicitly.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

import archive_collection as archive
import prepare_postgres_import as journal
from export_parquet import (ExportError, _binary_json, _bounded_read, _check_path,
                            _file_sha, _json, _sha, _write_new)

SCHEMA = 'nqc-miner-postgres-collection-v1'
MAX_WINDOWS = 64
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_REQUEST_BYTES = 32 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024


def transaction_sql(request):
    encoded = journal.packed(request).hex()
    return ("-- Offline collection bundle; inspect the returned status and COMMIT quarantine.\n"
            "BEGIN ISOLATION LEVEL READ COMMITTED;\n"
            "SET LOCAL search_path = pg_catalog;\n"
            "SET LOCAL lock_timeout = '5s';\n"
            "SET LOCAL statement_timeout = '90s';\n"
            "SET LOCAL synchronous_commit = on;\n"
            "SELECT nqc_miner_v1.import_verified_collection(\n"
            f"  convert_from(decode('{encoded}', 'hex'), 'UTF8')::jsonb);\n"
            "COMMIT;\n").encode()


def prepare_collection(store: Path, output: Path, verifier: Path, archive_id: str,
                       database_id: str, run_id: str):
    journal.database_uuid(archive_id)
    journal.database_uuid(database_id)
    if not isinstance(run_id, str) or not re.fullmatch(r'[a-z0-9_-]{1,96}', run_id):
        raise ExportError('invalid collection run id')
    store, verifier = _check_path(store), _check_path(verifier)
    output = _check_path(output, must_exist=False)
    if output.exists() or output == store or store in output.parents or output in store.parents:
        raise ExportError('collection output must be new and outside archive')
    verifier_hash = _file_sha(verifier, archive.MAX_SEGMENT)
    with archive.archive_lock(store) as locked:
        identity = _json(_bounded_read(locked / 'owner.json', 65536))
        if identity['archive_id'] != archive_id:
            raise ExportError('archive UUID mismatch')
        history = archive.receipts(locked)
        key = _sha(archive.packed(['nqc_miner_v1', 'historical', run_id]))
        receipt = next((r for r in reversed(history) if r['collection_key'] == key), None)
        if receipt is None:
            raise ExportError('collection has no published receipt')
        snapshot = archive.read_object(locked, receipt['snapshot_sha256'])
        object_dir = locked / 'objects' / receipt['snapshot_sha256']
        snapshot_raw = _bounded_read(object_dir / 'snapshot.json', MAX_SNAPSHOT_BYTES)
        receipt_raw = _bounded_read(locked / 'commits' / f"{receipt['sequence']:020}.json", 65536)
        revoked = snapshot['status'] == 'quarantined'
        windows = [e['window'] for e in snapshot['exports']]
        if (len(windows) > MAX_WINDOWS or windows != [f'window-{i:020}' for i in range(len(windows))]
                or (revoked and windows) or (not revoked and not windows)):
            raise ExportError('unsupported collection window inventory')
        files = dict(archive.ROOT_FILES)
        for name in windows:
            files.update({f'{name}/{f}': bound for f, bound in archive.WINDOW_FILES.items()})
        if set(snapshot['source_files']) != set(files):
            raise ExportError('snapshot source inventory differs')
        if sum(v['bytes'] for v in snapshot['source_files'].values()) > MAX_SOURCE_BYTES:
            raise ExportError('collection source byte bound exceeded')
        if sum(v['bytes'] for n, v in snapshot['source_files'].items() if n.endswith('events.jsonl')) > journal.MAX_BYTES:
            raise ExportError('aggregate journal byte bound exceeded')
        output.mkdir(mode=0o700)
        source = output / 'source'
        source.mkdir(mode=0o700)
        fingerprints = archive.copied_files(object_dir / 'source', source, files, MAX_SOURCE_BYTES)
        if fingerprints != snapshot['source_files']:
            raise ExportError('copied collection differs from sealed source')
        config = _json(_bounded_read(source / 'config.json', 1048576))
        marker_raw = _bounded_read(source / 'collector.json', 65536)
        if (len(config['scopes']) != 1 or _json(marker_raw) != {
                'schema': 'nqc-miner-collector-v1', 'plan_sha256': snapshot['owner']['config_sha256']}):
            raise ExportError('invalid collector marker or scope')
        control = _binary_json(verifier, 'verify-journal', '--state', str(source))
        if control['owner'] != snapshot['owner'] or control['integrity_verified'] is not True:
            raise ExportError('control verification differs')
        if bool(control['invalidated_from']) != revoked:
            raise ExportError('snapshot revocation disagrees with control journal')
        if revoked:
            records = [_json(line)['record'] for line in (source / 'events.jsonl').read_bytes().splitlines()]
            if not records or any(r['kind'] != 'invalidated' or r['chain_id'] != config['scopes'][0]['chain_id']
                                  or r['from_block'] != config['scopes'][0]['from_block'] for r in records):
                raise ExportError('control does not revoke the entire collection')
            verification = {'status': 'quarantined', 'control': control}
        else:
            verification = _binary_json(verifier, 'verify-collector', '--config', str(source / 'config.json'),
                                        '--state', str(source))
            if (verification.get('integrity_verified') is not True or verification.get('incomplete_window') is not False
                    or verification.get('completed_windows') != len(windows)
                    or verification.get('plan_sha256') != snapshot['owner']['config_sha256']):
                raise ExportError('collection verification incomplete')
        prepared = output / 'journals'
        prepared.mkdir(mode=0o700)
        packages, manifests, count = [], [], 0
        for name in ['control', *windows]:
            result = journal.prepare_import(source if name == 'control' else source / name,
                                            prepared / name, verifier, database_id,
                                            maximum_records=max(1, journal.MAX_RECORDS - count))
            count += result['records']
            if count > journal.MAX_RECORDS:
                raise ExportError('aggregate record bound exceeded')
            manifests.append(result)
            request_raw = _bounded_read(prepared / name / 'request.json', MAX_REQUEST_BYTES)
            if _sha(request_raw) != result['request_sha256'] or result['verifier_sha256'] != verifier_hash:
                raise ExportError('prepared journal changed before collection binding')
            packages.append(_json(request_raw))
        request = {'schema': SCHEMA, 'database_id': database_id, 'archive_id': archive_id,
                   'receipt_hex': receipt_raw.hex(), 'snapshot_hex': snapshot_raw.hex(),
                   'receipt_fields_hex': archive.packed({k: v for k, v in receipt.items() if k != 'sha256'}).hex(),
                   'collector_hex': marker_raw.hex(), 'control': packages[0],
                   'windows': [{'index': i, 'journal': p} for i, p in enumerate(packages[1:])]}
        raw = journal.packed(request) + b'\n'
        if len(raw) > MAX_REQUEST_BYTES:
            raise ExportError('collection request byte bound exceeded')
        # Fail closed on noncooperating mutation while our archive lock was held.
        if archive.receipts(locked) != history or archive.read_object(locked, receipt['snapshot_sha256']) != snapshot:
            raise ExportError('archive changed during collection preparation')
        if _file_sha(verifier, archive.MAX_SEGMENT) != verifier_hash:
            raise ExportError('verifier changed during collection preparation')
        for name, fingerprint in fingerprints.items():
            if _file_sha(source / name, files[name]) != fingerprint['sha256']:
                raise ExportError('copied collection changed during preparation')
        _write_new(output / 'request.json', raw)
        _write_new(output / 'import.sql', transaction_sql(request))
        archive.new_json(output / 'verification.json', verification)
        _write_new(output / 'receipt.json', receipt_raw)
        _write_new(output / 'snapshot.json', snapshot_raw)
        manifest = {'schema': SCHEMA, 'complete': True, 'namespace': 'nqc_miner_v1', 'producer': 'nqc-miner',
                    'archive_id': archive_id, 'database_id': database_id, 'run_id': run_id,
                    'receipt_sha256': receipt['sha256'], 'receipt_sequence': receipt['sequence'],
                    'snapshot_sha256': receipt['snapshot_sha256'], 'status': snapshot['status'],
                    'windows': len(windows), 'records': count, 'data_class': 'historical',
                    'source_files': fingerprints, 'request_sha256': _sha(raw),
                    'sql_sha256': _file_sha(output / 'import.sql', 3 * MAX_REQUEST_BYTES),
                    'preparer_sha256': _file_sha(Path(__file__), 1048576),
                    'installer_sha256': _file_sha(Path(__file__).resolve().parents[1] / 'infra/postgres_collection.sql', 1048576),
                    'verifier_sha256': verifier_hash, 'verifier_build': manifests[0]['verifier_build'],
                    'database_applied': False, 'observer_bridge_enabled': False, 'delivery_enabled': False,
                    'authenticity_verified': False, 'live_chain_revalidated': False}
        for directory in sorted((p for p in output.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            archive.sync_dir(directory)
        archive.new_json(output / 'manifest.json', manifest)
        archive.sync_dir(output)
        return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['archive', 'output', 'verifier']:
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ['archive-id', 'database-id', 'run-id']:
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(prepare_collection(args.archive, args.output, args.verifier,
                                          args.archive_id, args.database_id, args.run_id), indent=2))
    except (ExportError, OSError, ValueError) as error:
        parser.exit(1, f'Miner collection preparation rejected: {error}\n')
