"""Offline one-slot, existing-account trie cascade; NOT EVM execution.

The caller supplies a mutation, not a transaction. No RPC, secret, persistence,
account creation/deletion, gas, refunds, forks, or historical admission here.
"""
from pathlib import Path
import sys

import rlp

EXPERIMENTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(EXPERIMENTS / 'nqc-043-account-facts'))
sys.path.insert(0, str(EXPERIMENTS / 'nqc-044-write-witness'))
import account_facts as facts
import proof_trial as raw


def apply_slot(root, address, slot, value, proof, extra_storage_nodes=()):
    """Verify old account/slot, change storage, then replace the account leaf.

Only an already-present account is supported. Zero means delete the storage
leaf, not insert RLP(0). Fail closed on missing data. All DBs are disposable;
returned roots are raw candidate roots, not a block/state-transition verdict.
"""
    raw.v.require(type(value) is int and 0 <= value < 2**256, 'Invalid storage value')
    slot_hex = raw.v.slot(slot)
    checked = facts.verify_account_facts(root, address, [slot_hex], proof)
    raw.v.require(checked['account_existence'] == 'PRESENT', 'Account creation is unsupported')
    root_bytes, address_bytes = raw.v.data_hex(root, 32), raw.v.data_hex(address, 20)
    key = raw.v.k256(address_bytes)
    account_proof = [raw.v.data_hex(n) for n in proof['accountProof']]
    old_account = raw.mpt.trie_value(root_bytes, key, account_proof)
    fields = rlp.decode(old_account)
    storage_proof = [raw.v.data_hex(n) for n in proof['storageProof'][0]['proof']]
    storage = raw.trial(fields[2], raw.key_for_slot(slot), storage_proof,
                        'delete' if value == 0 else 'set',
                        None if value == 0 else rlp.encode(value), extra_storage_nodes)
    result = {
        'status': 'BLOCKED_STORAGE_NODE', 'missing_node_hash': storage['missing_node_hash'],
        'candidate_storage_root': None, 'candidate_state_root': None, 'candidate_account_rlp': None,
        'old_account_rlp': '0x' + old_account.hex(),
        'scope': 'one caller-specified slot mutation in an existing account; raw tries only',
        'raw_trie_cascade_completed': False, 'account_creation_or_deletion_supported': False,
        'historical_position_authenticated': False, 'nitro_replayed': False,
        'complete_parent_witness': False, 'commercial_admission': False,
    }
    if storage['status'] != 'RAW_TRIE_OPERATION_COMPLETED':
        return result
    # Preserve the original nonce, balance and codeHash bytes, replace only field 2.
    fields[2] = raw.v.data_hex(storage['new_root'], 32)
    account_bytes = rlp.encode(fields)
    state = raw.trial(root_bytes, key, account_proof, 'set', account_bytes)
    if state['status'] != 'RAW_TRIE_OPERATION_COMPLETED':
        result.update(status='BLOCKED_ACCOUNT_NODE', missing_node_hash=state['missing_node_hash'])
        return result
    result.update(status='RAW_TRIE_CASCADE_COMPLETED', raw_trie_cascade_completed=True,
                  candidate_storage_root=storage['new_root'], candidate_state_root=state['new_root'],
                  candidate_account_rlp='0x' + account_bytes.hex(), missing_node_hash=None)
    return result
