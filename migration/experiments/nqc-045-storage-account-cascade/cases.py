"""Invented accounts/values only; reuse NQC043 independent fixture builder."""
import copy
import rlp

import cascade as c
from fixtures import fixture, address

TARGET, NEIGHBOR = address(1), address(2)


def records():
    return {TARGET: {'nonce': 7, 'balance': 2**200 + 31, 'code': b'\x60\x00',
                     'storage': {9: 77, 13: 88}},
            NEIGHBOR: {'nonce': 5, 'balance': 123, 'storage': {21: 456}}}


def demonstration():
    data = records()
    root, proof = fixture(data, TARGET, [9])
    blocked = c.apply_slot(root, TARGET, 9, 0, proof)
    c.raw.v.require(blocked['status'] == 'BLOCKED_STORAGE_NODE', 'Fixture must require sibling')
    missing = c.raw.v.data_hex(blocked['missing_node_hash'], 32)
    _, db = c.raw.build({c.raw.key_for_slot(k): rlp.encode(v) for k, v in data[TARGET]['storage'].items()})
    extra = db[missing]  # Synthetic generator only; no external retrieval.
    completed = c.apply_slot(root, TARGET, 9, 0, proof, [(missing, extra)])
    after = copy.deepcopy(data)
    del after[TARGET]['storage'][9]
    expected_root, expected_proof = fixture(after, TARGET, [9, 13])
    checked_after = c.facts.verify_account_facts(expected_root, TARGET,
                                                [c.raw.v.slot(9), c.raw.v.slot(13)], expected_proof)
    c.raw.v.require(completed['candidate_state_root'] == expected_root, 'Full state-root mismatch')
    c.raw.v.require(completed['candidate_storage_root'] == checked_after['storage_root'], 'Storage-root mismatch')
    # Verify the full reference proof against the independently computed partial candidate.
    c.facts.verify_account_facts(completed['candidate_state_root'], TARGET,
                                 [c.raw.v.slot(9), c.raw.v.slot(13)], expected_proof)
    return {'evidence_class': 'SYNTHETIC only; not historical chain state',
            'input_state_root': root, 'input_proof': proof,
            'mutation': {'address': TARGET, 'slot': 9, 'new_value': 0},
            'blocked_without_sibling': blocked,
            'extra_node_hash': '0x' + missing.hex(), 'extra_node_bytes': '0x' + extra.hex(),
            'completed_with_sibling': completed,
            'full_reference_state_root': expected_root, 'full_reference_proof': expected_proof,
            'post_proof_checked': checked_after,
            'stale_account_leaf_would_keep_old_state_root': root,
            'rpc_requests_sent': 0, 'historical_proofs_acquired': 0, 'commercial_admission': False}
