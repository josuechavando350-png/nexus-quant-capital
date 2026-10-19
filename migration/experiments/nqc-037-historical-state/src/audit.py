"""Recompute the NQC037 evidence inventory without any network or state execution."""
import hashlib
import json
import re

from verify import (ROOT, PARENT_HASH, PARENT_NUMBER, TARGET_HASH, TARGET_NUMBER,
                    ANCHOR_HASH, ANCHOR_NUMBER, HISTORY_CODE, HISTORY_WINDOW,
                    ARBOS_FIELDS, arbos_slot, slot, k256, require, data_hex,
                    read_json, validate_header, closed_gates)
from intake import plan, save

NITRO_COMMIT = '3599acae1ad2fab4059fc46453c9cd3294126641'
GETH_COMMIT = 'f3a977ddf30b138da2fe673ac5cbff2bc6dd4c88'


def confirmation_event(logs, observation):
    require(not logs.get('isError'), 'Explorer returned an error')
    require(logs['structuredContent'].get('pagination') is None, 'Incomplete log pagination')
    signature = '0x' + k256(b'AssertionConfirmed(bytes32,bytes32,bytes32)').hex()
    items = [row for row in logs['structuredContent']['data']
             if row['address'].lower() == observation['to'].lower()
             and row['topics'][0] == signature]
    require(len(items) == 1, 'Missing or ambiguous confirmation event')
    event = items[0]
    require(not event.get('data_truncated'), 'Truncated event')
    topics = [t for t in event['topics'] if t is not None]
    require(len(topics) == 2 and topics[1] == observation['assertion_hash'], 'Wrong indexed assertion')
    body = data_hex(event['data'], 64)
    require('0x' + body[:32].hex() == observation['confirmed_block_hash_field'] == ANCHOR_HASH,
            'Wrong confirmation block hash')
    require('0x' + body[32:].hex() == observation['confirmed_send_root_field'], 'Wrong confirmed send root')
    require(event['block_number'] == observation['ethereum_block_number'], 'Wrong confirmation L1 height')
    return {'signature_topic': signature, 'log_index': event['index'],
            'assertion_hash': topics[1], 'block_hash': ANCHOR_HASH,
            'send_root': '0x' + body[32:].hex(),
            'raw_event_fields_match': True, 'receipt_inclusion_verified': False}


def source_checks():
    rows = read_json(ROOT / 'vendor/SOURCES.json')
    arbos_tree = {row['path']: row['sha'] for row in read_json(ROOT / 'evidence/nitro-arbos-tree.json')['tree']}
    params_tree = {row['name']: row['sha'] for row in read_json(ROOT / 'evidence/geth-params-tree.json')}
    for row in rows:
        require('local' in row and 'error' not in row, 'Missing upstream source')
        expected = NITRO_COMMIT if row['repository'] == 'OffchainLabs/nitro' else GETH_COMMIT
        require(row['commit'] == expected, 'Unexpected upstream commit')
        raw = (ROOT / 'vendor' / row['local']).read_bytes()
        require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'Source integrity mismatch')
        blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        require(blob == row['git_blob_sha'], 'Source Git blob mismatch')
        if row['path'].startswith('arbos/'):
            require(blob == arbos_tree[row['path'][6:]], 'Source differs from GitHub arbos tree')
        if row['path'] == 'params/protocol_params.go':
            require(blob == params_tree['protocol_params.go'], 'Source differs from GitHub params tree')
    tree = read_json(ROOT / 'evidence/nitro-tree.json')['tree']
    require(next(x['sha'] for x in tree if x['path'] == 'go-ethereum') == GETH_COMMIT, 'Geth submodule identity mismatch')
    protocol = (ROOT / 'vendor/go-ethereum__params__protocol_params.go').read_text()
    match = re.search(r'HistoryStorageCodeArbitrum = common.FromHex\("([0-9a-f]+)"\)', protocol)
    require(match is not None and bytes.fromhex(match[1]) == HISTORY_CODE, 'Runtime does not match pinned source')
    require('buffer size is 393168 blocks instead of 8191' in protocol, 'Unknown source window')
    require(k256(b'arbBlockNumber()')[:4] == bytes.fromhex('a3b1b31d'), 'ArbSys selector mismatch')
    return {'files_checked': len(rows), 'nitro_commit': NITRO_COMMIT,
            'go_ethereum_submodule_commit': GETH_COMMIT,
            'history_runtime_bytes': len(HISTORY_CODE),
            'history_runtime_keccak256': '0x' + k256(HISTORY_CODE).hex(),
            'historically_executed_binary_authenticated': False}


def audit():
    target = read_json(ROOT / 'inputs/target-header.json')['result']
    parent = read_json(ROOT / 'inputs/parent-header.json')['result']
    validate_header(target, TARGET_HASH, TARGET_NUMBER)
    validate_header(parent, PARENT_HASH, PARENT_NUMBER)
    require(target['parentHash'] == PARENT_HASH, 'Captured parent link mismatch')
    observation = read_json(ROOT / 'inputs/l1-observations.json')['confirmation']
    event = confirmation_event(read_json(ROOT / 'evidence/blockscout-confirmation-logs.json'), observation)
    block = read_json(ROOT / 'evidence/blockscout-confirmed-block.json')['structuredContent']['data']['block_details']
    require(block['height'] == ANCHOR_NUMBER and block['hash'] == ANCHOR_HASH, 'Anchor observation mismatch')
    require(block['arbitrum']['send_root'] == event['send_root'], 'Observed send root mismatch')
    tx = read_json(ROOT / 'evidence/blockscout-confirmation-tx.json')['structuredContent']['data']
    require(tx['to'].lower() == observation['to'].lower() and tx['status'] == 'ok'
            and tx['block_number'] == observation['ethereum_block_number'], 'Confirmation transaction observation mismatch')
    attempts = [read_json(ROOT / f'evidence/{name}-chain.json') for name in ['publicnode', 'blockreq']]
    require(all(row['http_status'] == 403 and row['request']['method'] == 'eth_chainId'
                and row['retries'] == 0 for row in attempts), 'Unexpected endpoint attempt outcome')
    previous = read_json(ROOT / 'inputs/augmented-prestate.json')['result']
    arbos_snapshot = previous['0xa4b05fffffffffffffffffffffffffffffffffff']
    history_snapshot = previous['0x0000f90827f1c53a10cb7a02335b175320002935']
    require(data_hex(history_snapshot['code']) == HISTORY_CODE, 'Diagnostic history runtime differs from source')
    missing = [name for name, offset in ARBOS_FIELDS.items() if arbos_slot(offset) not in arbos_snapshot.get('storage', {})]
    source = source_checks()
    report = {'status': 'NEW_ANCHOR_OBSERVATIONS_AND_VERIFIED_INTAKE_READY_STATE_ACCESS_BLOCKED',
              'source_checks': source, 'confirmation_event': event,
              'confirmation_calldata_truncated': bool(tx.get('raw_input_truncated')),
              'confirmation_calldata_fully_decoded': False,
              'assertion_hash_recomputed_from_calldata': False,
              'observed_confirmed_l2_block_number': ANCHOR_NUMBER,
              'target_to_observed_anchor_blocks': ANCHOR_NUMBER - TARGET_NUMBER,
              'parent_to_observed_anchor_blocks': ANCHOR_NUMBER - PARENT_NUMBER,
              'history_route': {'status': 'SOURCE_DERIVED_NOT_ACQUIRED',
                               'arbitrum_window': HISTORY_WINDOW, 'ethereum_window_not_applicable': 8191,
                               'target_slot': slot(TARGET_NUMBER % HISTORY_WINDOW),
                               'parent_slot': slot(PARENT_NUMBER % HISTORY_WINDOW),
                               'in_window': ANCHOR_NUMBER - PARENT_NUMBER <= HISTORY_WINDOW,
                               'proofs_received': 0, 'full_anchor_header_received': False},
              'arbos_root_slots': {name: arbos_slot(n) for name, n in ARBOS_FIELDS.items()},
              'new_rpc_attempts': [{'endpoint': row['endpoint'], 'http_status': row['http_status'],
                                    'requests': 1, 'historical_methods_reached': False} for row in attempts],
              'minimal_acquisition_plan_requests': len(plan()),
              'planned_parent_priority_slots': 11, 'planned_parent_arbos_slots': 5,
              'planned_anchor_history_slots': 2,
              'parent_state_proofs_received': 0, 'parent_slots_authenticated': 0,
              'diagnostic_snapshot_accounts': len(previous),
              'diagnostic_snapshot_storage_slots': sum(len(v.get('storage', {})) for v in previous.values()),
              'diagnostic_snapshot_is_complete_system_witness': False,
              'arbos_account_in_diagnostic_snapshot': '0xa4b05fffffffffffffffffffffffffffffffffff' in previous,
              'history_account_in_diagnostic_snapshot': '0x0000f90827f1c53a10cb7a02335b175320002935' in previous,
              'diagnostic_arbos_storage_slots': len(arbos_snapshot.get('storage', {})),
              'diagnostic_arbos_context_fields_missing': missing,
              'diagnostic_history_storage_slots': len(history_snapshot.get('storage', {})),
              'diagnostic_history_code_matches_pinned_runtime': True,
              'diagnostic_snapshot_merkle_proofs_present': False,
              'gates': closed_gates()}
    save(ROOT / 'evidence/REQUESTS.json', plan())
    save(ROOT / 'evidence/RESULTS.json', report)
    return report


if __name__ == '__main__':
    result = audit()
    print(json.dumps({'status': result['status'], 'parent_proofs_received': 0,
                      'commercial_admission': False}, indent=2))
