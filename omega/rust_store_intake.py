"""H19 artifact-only Python/Rust transport with an external inventory commitment.

The Rust store root excludes orphan artifacts. A complete snapshot commitment
and caller-held journal head are therefore required; the root alone is not a
replica identity. Revocation remains batch-local, not canonical reorg authority.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from evidence_store import (HEX, MAX_OBJECTS, audit_store, create, export_store,
                            read_batch, restore_store, revoke, safe_path)
from historical_intake import ROOT, need, same
from integrity import canonical, digest, read_regular, strict_json
from temporal_intake import query_temporal_report, store_temporal_report

SCHEMA = 'nqc.omega.rust-artifact-transport.v1'
MAX_TRANSPORT = 64 * 1024 * 1024
BRIDGE_SOURCE = 'omega/rust_store_bridge.rs'
BRIDGE_SOURCE_SHA256 = '6befee0d4e6d3ab1a2e778a1654ceb6682514fb83447134e10cc57afd375de39'
EXAMPLE = 'nqc-census/crates/nqc-census-store/examples/nqc_omega_bridge.rs'
REJECTION_CASES = ['corrupt_frame', 'corrupt_export', 'existing_import', 'existing_export',
                   'empty_import', 'malformed_name', 'digest_mismatch', 'symlink_input',
                   'missing_snapshot']


def read_bridge_source(root=ROOT):
    raw = read_regular(Path(root)/BRIDGE_SOURCE)
    need(digest(raw) == BRIDGE_SOURCE_SHA256, 'bridge_source_pin_mismatch')
    return raw


def new_directory(path, root=ROOT):
    path = Path(path).absolute()
    need(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink_transport_path')
    need('..' not in path.parts and not path.is_relative_to(Path(root).resolve()), 'unsafe_transport_path')
    path.mkdir(exist_ok=False)
    return path


def snapshot_objects(snapshot, expected_head):
    need(type(expected_head) is str and HEX.fullmatch(expected_head), 'external_head_required')
    with tempfile.TemporaryDirectory(prefix='omega-transport-validate-') as tmp:
        db = Path(tmp)/'snapshot.sqlite'
        restore_store(db, snapshot)
        audit_store(db, expected_head)
    objects = {o['sha256']: bytes.fromhex(o['hex']) for o in snapshot['objects']}
    raw = canonical(snapshot)
    objects[digest(raw)] = raw
    need(0 < len(objects) <= MAX_OBJECTS + 1 and sum(map(len, objects.values())) <= MAX_TRANSPORT,
         'transport_bounds')
    return objects


def inventory(objects):
    return {sha: len(raw) for sha, raw in sorted(objects.items())}


def read_transport(path):
    path = Path(path)
    need(not any(p.is_symlink() for p in (path, *path.absolute().parents)), 'symlink_transport_path')
    files = list(path.iterdir())
    need(0 < len(files) <= MAX_OBJECTS + 1, 'transport_inventory_bounds')
    objects = {}
    total = 0
    for file in files:
        need(HEX.fullmatch(file.name), 'transport_object_name')
        raw = read_regular(file, MAX_TRANSPORT)
        total += len(raw)
        need(raw and total <= MAX_TRANSPORT and digest(raw) == file.name, 'transport_object_digest_or_bounds')
        objects[file.name] = raw
    return objects


def write_transport(path, objects):
    path = new_directory(path)
    for sha, raw in objects.items():
        need(type(sha) is str and HEX.fullmatch(sha) and type(raw) is bytes and digest(raw) == sha,
             'invalid_transport_object')
        with (path/sha).open('xb') as f: f.write(raw)
    need(read_transport(path) == objects, 'transport_write_mismatch')


def restore_transport(path, destination, *, snapshot_id, expected_inventory, expected_head):
    need(type(snapshot_id) is str and HEX.fullmatch(snapshot_id), 'external_snapshot_required')
    objects = read_transport(path)
    same(inventory(objects), expected_inventory, 'external_inventory_mismatch')
    need(snapshot_id in objects, 'snapshot_missing')
    snapshot = strict_json(objects[snapshot_id])
    need(objects == snapshot_objects(snapshot, expected_head), 'snapshot_inventory_mismatch')
    safe_path(destination)
    need(not Path(destination).resolve().is_relative_to(ROOT.resolve()), 'restore_inside_source')
    return restore_store(destination, snapshot)


def parse_verifier(raw, expected_inventory):
    lines = raw.decode('ascii').splitlines()
    keys = {'RMC_004_OFFLINE_VERIFY', 'format_version', 'config_id', 'chunks', 'artifacts',
            'logical_bytes', 'stored_bytes', 'orphan_chunks', 'orphan_artifacts',
            'abandoned_registrations', 'staging_files', 'streams', 'ranges_certified',
            'tips_matched', 'evidence_root'}
    need(all(line.count('=') == 1 for line in lines), 'verifier_line_shape')
    pairs = [line.split('=') for line in lines]
    data = dict(pairs)
    need(len(pairs) == len(data) and set(data) == keys, 'verifier_inventory')
    need(data.pop('RMC_004_OFFLINE_VERIFY') == 'PASS', 'verifier_not_pass')
    for key in ('config_id', 'evidence_root'):
        need(HEX.fullmatch(data[key]), 'verifier_digest')
    for key in keys - {'RMC_004_OFFLINE_VERIFY', 'config_id', 'evidence_root'}:
        need(re.fullmatch(r'0|[1-9][0-9]*', data[key]), 'verifier_noninteger')
        data[key] = int(data[key])
    need(data['artifacts'] == data['orphan_artifacts'] == len(expected_inventory)
         and data['logical_bytes'] == sum(expected_inventory.values()), 'verifier_inventory_mismatch')
    need(all(data[k] == 0 for k in ('streams','ranges_certified','tips_matched','orphan_chunks',
                                   'staging_files','abandoned_registrations')), 'unexpected_range_authority')
    need(data['format_version'] == 1 and data['chunks'] > 0 and data['stored_bytes'] > 0,
         'empty_or_unknown_rust_store')
    return data


def call(argv, *, expected=0):
    env = {k:v for k,v in os.environ.items() if k not in {'GH_TOKEN','GITHUB_TOKEN'}}
    result = subprocess.run([str(x) for x in argv], env=env, capture_output=True, timeout=120)
    print('OMEGA_RUST_COMMAND ' + json.dumps({'argv':[str(x) for x in argv],
        'exit_code':result.returncode,'expected_exit':expected,
        'stdout_sha256':digest(result.stdout),'stderr_sha256':digest(result.stderr)},sort_keys=True),flush=True)
    need(result.returncode == expected, 'bridge_command_failed:' + result.stderr.decode(errors='replace')[:1000])
    return result.stdout


def fixture(path, root=ROOT):
    create(path)
    result = store_temporal_report(path, root=root)
    # Revoke an upstream batch while retaining the separate active temporal batch.
    # This explicitly preserves existing batch-local semantics across languages.
    revoke(path, result['state_batch'], 'CONTROLLED_TRANSPORT_REVOCATION_TEST',
           canonical({'test_only': True, 'batch': result['state_batch']}))
    query_temporal_report(path, result['temporal_batch'], root)
    return result


def verify_report(report, root=ROOT):
    need(type(report) is dict and report.get('report_commitment_sha256') == digest(canonical({
        k:v for k,v in report.items() if k != 'report_commitment_sha256'})), 'transport_report_digest')
    network = report.get('network', {})
    need(network.get('interfaces') == ['lo'] and network.get('routable_network') is False,
         'transport_network')
    need(all(type(network.get(k)) is str and re.fullmatch(r'net:\[[0-9]+\]', network[k])
             for k in ('network_namespace','parent_network_namespace'))
         and network['network_namespace'] != network['parent_network_namespace'], 'transport_namespace')
    with tempfile.TemporaryDirectory(prefix='omega-transport-report-') as tmp:
        db = Path(tmp)/'fixture.sqlite'
        result = fixture(db, root)
        head = audit_store(db)['journal_head']
        snapshot = export_store(db)
        expected = inventory(snapshot_objects(snapshot, head))
    verifier = report['rust_verifier']
    encoded = ('RMC_004_OFFLINE_VERIFY=PASS\n' + ''.join(f'{k}={v}\n' for k,v in verifier.items())).encode()
    same(parse_verifier(encoded, expected), verifier, 'transport_verifier')
    expected_report = {'schema': SCHEMA, 'status': 'RUST_ARTIFACT_TRANSPORT_PASS',
        'snapshot_sha256': digest(canonical(snapshot)), 'journal_head': head,
        'inventory': expected, 'inventory_sha256': digest(canonical(expected)),
        'temporal_report_commitment': result['report']['report_commitment_sha256'],
        'bridge_source_sha256': digest(read_bridge_source(root)),
        'rust_verifier': verifier, 'network': network,
        'rejection_cases': REJECTION_CASES,
        'byte_identical_restore': True, 'corruption_rejected': True,
        'missing_object_rejected': True, 'revoked_bytes_preserved': True,
        'revoked_batch_query_rejected': True, 'revocation_scope': 'BATCH_LOCAL',
        'remote_replication_tested': False, 'real_chain_reorg_tested': False,
        'certified_components': 0, 'census_closed': False}
    expected_report['report_commitment_sha256'] = digest(canonical(expected_report))
    same(report, expected_report, 'transport_report_differs_from_sources')
    return report


def exercise(output, bridge, verifier, network, root=ROOT):
    need(network.get('interfaces') == ['lo'] and network.get('routable_network') is False
         and network.get('network_namespace') != network.get('parent_network_namespace'), 'network_not_isolated')
    output = new_directory(output, root)
    print('OMEGA_RUST_STORE_BEGIN', flush=True)
    original = output/'original.sqlite'
    batch = fixture(original, root)
    head = audit_store(original)['journal_head']
    snapshot = export_store(original)
    objects = snapshot_objects(snapshot, head)
    expected = inventory(objects)
    snapshot_id = digest(canonical(snapshot))
    write_transport(output/'input', objects)
    call([bridge, 'import', output/'input', output/'rust-store'])
    raw_verify = call([verifier, '--store', output/'rust-store'])
    checked = parse_verifier(raw_verify, expected)
    (output/'rust-verifier.log').write_bytes(raw_verify)
    # A separate process reopens the real Rust store and exports its whole inventory.
    call([bridge, 'export', output/'rust-store', output/'restored-objects'])
    recovered = output/'restored.sqlite'
    restore_transport(output/'restored-objects', recovered, snapshot_id=snapshot_id,
                      expected_inventory=expected, expected_head=head)
    same(export_store(recovered), snapshot, 'recovered_snapshot_mismatch')
    same(query_temporal_report(recovered, batch['temporal_batch'], root), batch['report'], 'recovered_report_mismatch')
    try: read_batch(recovered, batch['state_batch'])
    except ValueError as e: need(str(e) == 'batch_inactive_or_missing', 'wrong_revocation_failure')
    else: raise ValueError('revocation_lost')
    need(read_batch(recovered, batch['state_batch'], include_revoked=True) ==
         read_batch(original, batch['state_batch'], include_revoked=True), 'revoked_bytes_lost')
    # Physical corruption: a frame byte must fail the unchanged standalone verifier.
    corrupt = output/'corrupt-store'
    shutil.copytree(output/'rust-store', corrupt)
    chunk = next((corrupt/'objects/chunks').glob('*/*'))
    raw = bytearray(chunk.read_bytes()); raw[-1] ^= 1
    mode = chunk.stat().st_mode & 0o777
    chunk.chmod(0o600); chunk.write_bytes(raw); chunk.chmod(mode)
    call([verifier, '--store', corrupt], expected=1)
    call([bridge, 'export', corrupt, output/'rejected-corrupt-export'], expected=1)
    call([bridge, 'import', output/'input', output/'rust-store'], expected=1)
    call([bridge, 'export', output/'rust-store', output/'restored-objects'], expected=1)
    for label in ('empty_import','malformed_name','digest_mismatch','symlink_input'):
        bad = output/label; bad.mkdir()
        if label == 'malformed_name': (bad/'not-a-sha').write_bytes(b'bad')
        if label == 'digest_mismatch': (bad/('f'*64)).write_bytes(b'wrong digest')
        if label == 'symlink_input': (bad/snapshot_id).symlink_to(output/'input'/snapshot_id)
        call([bridge, 'import', bad, output/(label+'-store')], expected=1)
        need(not (output/(label+'-store')).exists(), 'rejected_import_created_store')
    # All transport objects are orphans. Removing the sole manifest may leave a
    # perfectly valid Rust store/root: the external inventory must still reject it.
    missing = output/'missing-object'
    write_transport(missing, {sha: b for sha,b in objects.items() if sha != snapshot_id})
    try:
        restore_transport(missing, output/'must-not-restore.sqlite', snapshot_id=snapshot_id,
                          expected_inventory=expected, expected_head=head)
    except ValueError as e:
        need(str(e) == 'external_inventory_mismatch', 'wrong_missing_failure')
        print('OMEGA_RUST_MISSING_SNAPSHOT_REJECTED', flush=True)
    else: raise ValueError('missing_object_accepted')
    report = {'schema': SCHEMA, 'status': 'RUST_ARTIFACT_TRANSPORT_PASS',
        'snapshot_sha256': snapshot_id, 'journal_head': head,
        'inventory': expected, 'inventory_sha256': digest(canonical(expected)),
        'temporal_report_commitment': batch['report']['report_commitment_sha256'],
        'bridge_source_sha256': digest(read_bridge_source(root)),
        'rust_verifier': checked, 'network': network,
        'rejection_cases': REJECTION_CASES,
        'byte_identical_restore': True, 'corruption_rejected': True,
        'missing_object_rejected': True, 'revoked_bytes_preserved': True,
        'revoked_batch_query_rejected': True, 'revocation_scope': 'BATCH_LOCAL',
        'remote_replication_tested': False, 'real_chain_reorg_tested': False,
        'certified_components': 0, 'census_closed': False}
    report['report_commitment_sha256'] = digest(canonical(report))
    (output/'report.json').write_bytes(canonical(report))
    print('OMEGA_RUST_STORE_REPORT ' + canonical(report).decode().strip(), flush=True)
    return report
