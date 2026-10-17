"""Exactly three NEW, finite, unsigned local EVM variants; no relay or fork.

Reuses hash-locked 004 compiler artifacts and execution/trace collection unchanged.
The builder identity here is a LAB ASSIGNMENT, never a Titan/Quasar address.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'nqc-sponsored-bundle-gate-20261017'
sys.path.insert(0, str(BASE))
import local_node
import run_coordinated as rc
import reconcile_flows


def verify_base(artifacts_path=None, require_artifacts=True):
    lines = (BASE / 'MANIFEST.sha256').read_text().splitlines()
    for line in lines:
        sha, name = line.split('  ', 1)
        assert hashlib.sha256((BASE / name).read_bytes()).hexdigest() == sha, name
    if not require_artifacts:
        return None
    art = json.loads(Path(artifacts_path or BASE / 'build/artifacts.json').read_text())
    lock = json.loads((BASE / 'SOURCE_LOCK.json').read_text())
    for name, sha in lock['bytecode']['bytecode_sha256'].items():
        assert hashlib.sha256(bytes.fromhex(art[name]['bytecode'][2:])).hexdigest() == sha, name
    return art


def save(name, value):
    (HERE / 'evidence' / (name + '.json')).write_text(json.dumps(value, separators=(',', ':')) + '\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--anvil', required=True)
    parser.add_argument('--artifacts', help='Pinned 004 artifacts; may be rebuilt in a disposable baseline copy')
    args = parser.parse_args()
    art = verify_base(args.artifacts)
    local_node.HERE = HERE
    local_node.ref.HERE = HERE
    results = []
    with local_node.node(args.anvil, art, pool_override=True) as lab:
        lab.setup()
        save('setup', {'report': lab.setup_report, 'transactions': lab.setup_records})
        for name, aligned, advance in [
            ('V05_builder_funds_external_refund', False, 3*10**16),
            ('V06_builder_funds_own_refund', True, 3*10**16),
            ('V07_partial_topup', True, 10**13),
        ]:
            snapshot = lab.rpc('evm_snapshot')
            original_actors = dict(lab.actors)
            external = lab.actors['sponsor_and_topup_financier']
            builder = lab.actors['simulated_builder']
            lab.actors['external_refund_recipient'] = external
            lab.actors['sponsor_and_topup_financier'] = builder
            # Explicit synthetic external liquidity; not owner capital or public money.
            lab.rpc('anvil_setBalance', [builder, hex(100*rc.E)])
            lab.coinbase = lab.actors['proposer']
            lab.rpc('anvil_setCoinbase', [lab.coinbase])
            lab.records = []
            requests = rc.build_package(lab, advance=advance)
            # A builder financing itself needs no separate, internal fee transfer.
            # This five-transaction topology is actually executed, not gas-subtracted on paper.
            requests = [t for t in requests if t['label'] != 'separate_builder_fee']
            if not aligned:
                for t in requests:
                    if t['label'] == 'liquidate':
                        t['request']['data'] = rc.ref.calldata(
                            f'execute({rc.ref.PLAN},bytes,bytes)', lab.plan({'sponsor': external}))
            checkpoint = lab.rpc('evm_snapshot')
            trial = rc.execute_block(lab, requests, 10**9, name + '_planning', observe=False)
            op = lab.actors['nqc_sender_and_beneficiary']
            op_cost = sum(t['gas_cost_wei'] for t in trial['transactions'] if t['request']['from'] == op)
            assert lab.rpc('evm_revert', [checkpoint])
            if aligned and advance == 10**13:
                assert not trial['flags']['LIQUIDATION_COMPLETED']
                # Planned U=0 stays 0; no hypothetical return gets credited.
            else:
                assert trial['flags']['LIQUIDATION_COMPLETED']
                for t in requests:
                    if t['label'] == 'return_unused_advance':
                        t['request']['value'] = hex(advance-op_cost)
            result = rc.execute_block(lab, requests, 10**9, name)
            result.update(architecture='C1', fixture_cash_wei=0,
                          intended_requests=requests,
                          identity_scope='SYNTHETIC_LAB_ASSIGNMENT_ONLY',
                          builder_fixture_funding_wei=100*rc.E,
                          planning={'discarded_trial_receipts': True, 'operator_gas_cost_wei': op_cost},
                          aligned_refund=aligned)
            ledger = reconcile_flows.reconcile(result)
            if advance == 10**13:
                assert len(result['transactions']) == 1
                assert not result['flags']['EVM_LOCAL_PASS']
            else:
                assert result['flags']['EVM_LOCAL_PASS']
                assert len(result['transactions']) == 5
            save(name, result)
            item = {'scenario': name, 'included': len(result['transactions']),
                    'gas': sum(s['gas_used'] for s in ledger['steps']),
                    'builder_cash_delta_wei': ledger['balance_delta_by_address'][builder]['ETH'],
                    'NQC_WETH_delta': ledger['nqc']['liquidation_generated_WETH'],
                    'pending': len(result['accepted_not_included']),
                    'EVM_LOCAL_PASS': result['flags']['EVM_LOCAL_PASS']}
            print(json.dumps(item), flush=True)
            results.append(item)
            assert lab.rpc('evm_revert', [snapshot])
            lab.actors = original_actors
    save('new-evm-index', {'new_variants': 3, 'runs': results, 'node_stopped': True,
                         'unsigned_only': True, 'fork': None, 'chain_id': 31337,
                         'pool_override_is_not_builder_admission': True})


if __name__ == '__main__':
    main()
