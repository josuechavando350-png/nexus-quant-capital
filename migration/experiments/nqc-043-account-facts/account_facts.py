"""Lossless account metadata on top of the unchanged NQC037 proof verifier.

Offline only. A verified proof is relative to its root, not consensus or replay.
No RPC client, no credentials, no modified acquisition plan or implicit zeroes.
"""
from pathlib import Path
import sys

PREVIOUS = Path(__file__).resolve().parent.parent / 'nqc-037-historical-state'
sys.path.insert(0, str(PREVIOUS / 'src'))
import verify as v
import storage_proof as mpt

FILTERED_ACCOUNT = '0xa4b0500000000000000000000000000000000001'


def verify_account_facts(root, address, slots, proof, code=None):
    """Return existence and account fields only after the original full check.

`slots` remains an exact requested set. Missing proof data raises; the only
absence result comes from a completed MPT non-inclusion verification.
`code=None` does not claim bytecode bytes have been supplied or authenticated.
"""
    v.require(isinstance(proof, dict), 'Proof must be an object')
    v.require(all(k in proof for k in ('address', 'nonce', 'balance', 'storageHash',
                                     'codeHash', 'accountProof', 'storageProof')),
              'Missing account proof field')
    checked = v.account_proof(root, address, slots, proof, code)
    # The original verifier checks the fields but discards its inclusion flag.
    # Recover that flag from the same verified path, never from nonce/balance=0.
    account = mpt.trie_value(v.data_hex(root, 32), v.k256(v.data_hex(address, 20)),
                             [v.data_hex(n) for n in proof['accountProof']])
    exists = account is not None
    result = dict(checked)
    result.update({
        'schema': 'nqc043-account-facts-v1',
        'address': '0x' + v.data_hex(address, 20).hex(),
        'supplied_state_root': '0x' + v.data_hex(root, 32).hex(),
        'account_existence': 'PRESENT' if exists else 'PROVEN_ABSENT',
        'nonce': str(v.quantity(proof['nonce'])),
        'balance_wei': str(v.quantity(proof['balance'])),
        'storage_root': '0x' + v.data_hex(proof['storageHash'], 32).hex(),
        'code_bytes_checked': code is not None,
        'complete_account_storage': False,
        'state_transition_executed': False,
    })
    return result


def verify_auxiliary_parent_account(proof):
    """Offline future intake for ONE account at the exact observed parent root.

This is not a ninth RPC request or authority to acquire one. The function cannot
take a replacement root/address and never promotes the observed root to finality.
It does not read/update the acquisition ledger or return an updated state root.
"""
    result = verify_account_facts(v.PARENT_ROOT, FILTERED_ACCOUNT, [], proof)
    result['requested_context'] = {
        'chain_id': v.CHAIN_ID, 'block_number': v.PARENT_NUMBER,
        'observed_block_hash': v.PARENT_HASH,
        'context_note': 'fixed acquisition target; chain identity and consensus not proved by this MPT',
    }
    return result
