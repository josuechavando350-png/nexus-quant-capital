"""Offline consolidation of pinned lab receipts, ledger and documentary boundaries.

No EVM execution, network client, financing API or provider admission model.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
STATES = {'MODEL_VALIDATED_ONLY', 'PUBLIC_DOCUMENTATION_SUPPORTED',
          'COMMERCIAL_TERMS_UNVERIFIED', 'SPECIFIC_PROVIDER_ACCEPTANCE_VERIFIED',
          'UNSUPPORTED_OR_ECONOMICALLY_REJECTED', 'INSUFFICIENT_EVIDENCE'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sources():
    manifest = json.loads((HERE / 'SOURCE_MANIFEST.json').read_text())
    out = {}
    for name, pin in manifest['files'].items():
        raw = subprocess.check_output(['git', '-C', str(REPO), 'show', pin['commit'] + ':' + pin['path']])
        require(len(raw) == pin['bytes'], name + ': length')
        require(hashlib.sha256(raw).hexdigest() == pin['sha256'], name + ': SHA256')
        require(hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
                == pin['git_blob_sha1'], name + ': Git blob')
        out[name] = raw
    return out


def integer(value):
    require(type(value) is int, 'integer base units required')
    return value


def consolidate(run, retained):
    """Cross-check existing flow extraction against original per-address balances.

    Does not re-execute EVM or independently re-decode every trace/ERC20 log.
    """
    require(run['chain_id'] == retained['chain_id'] == 31337, 'laboratory chain only')
    require(run['actors'] == retained['actors'], 'actor identity mismatch')
    actors = run['actors']; op = actors['nqc_sender_and_beneficiary']
    financier = actors['sponsor_and_topup_financier']; builder = actors['simulated_builder']
    proposer = actors['proposer']
    require(proposer not in {financier, builder, op}, 'do not merge proposer with builder')
    require(retained['flags']['BUILDER_REAL_ACCEPTED'] is None, 'lab is not provider acceptance')
    require(retained['sponsor']['real_failure_recourse_terms'] is None, 'unknown recourse changed')
    assets = {'ETH', 'WETH', 'COLLATERAL'}
    balances = run['initial']['balances']; final = run['final']['balances']
    require(set(balances) == set(final), 'balance address coverage')
    require(all(balances[op][asset] == 0 for asset in assets), 'operator initial assets')
    deltas = {a: {s: integer(final[a][s])-integer(balances[a][s]) for s in assets} for a in balances}
    require(deltas == retained['balance_delta_by_address'], 'retained asset deltas differ')
    flows = defaultdict(int); seen = set()
    for flow in retained['flows']:
        require(flow['chain_id'] == 31337 and flow['asset'] in assets, 'flow asset/chain')
        amount = integer(flow['amount_base_units']); require(amount >= 0, 'negative flow')
        key = (flow['evidence_ref'], flow['kind'], flow['asset'], flow['actor_from'], flow['actor_to'])
        require(key not in seen, 'duplicate flow'); seen.add(key)
        flows[(flow['actor_from'], flow['asset'])] -= amount
        flows[(flow['actor_to'], flow['asset'])] += amount
    for address, delta in deltas.items():
        for asset in assets:
            require(flows[(address, asset)] == delta[asset], 'flow/balance reconciliation')
    total_gas = 0; total_cost = 0; previous = balances
    for index, tx in enumerate(run['transactions']):
        receipt = tx['receipt']; request = tx['request']
        require(tx['before'] == previous, 'discontinuous snapshots'); previous = tx['after']
        require(int(receipt['transactionIndex'], 16) == index, 'receipt order')
        require(receipt['from'].lower() == request['from'].lower(), 'receipt sender')
        gas = int(receipt['gasUsed'], 16); price = int(receipt['effectiveGasPrice'], 16)
        require(gas * price == tx['gas_cost_wei'], 'actual gas cost mismatch')
        billed = sum(f['amount_base_units'] for f in retained['flows']
                     if f['tx_index'] == index and f['kind'] in {'gas_burn', 'priority_fee'})
        require(billed == gas * price, 'gas charged twice or omitted')
        total_gas += gas; total_cost += billed
    require(previous == final, 'final snapshot')
    s = retained['sponsor']
    margin = sum(integer(s[k]) for k in ('R_refund_wei', 'U_actually_returned_wei', 'V_other_receipts_wei'))
    margin -= sum(integer(s[k]) for k in ('A_disbursed_wei', 'F_funding_gas_wei',
                                         'P_separate_proposer_payment_wei', 'O_other_cash_costs_wei'))
    require(margin == s['cash_margin_wei'] == deltas[financier]['ETH'], 'financier cash formula')
    require(s['A_disbursed_wei'] - s['U_actually_returned_wei']
            == retained['nqc']['gas_paid_from_advance_wei'] + final[op]['ETH'], 'advance disposition')
    require(deltas[op]['WETH'] == retained['nqc']['liquidation_generated_WETH'], 'NQC token residue')
    full = not run['accepted_not_included'] and run['final']['position'][1] == 0
    status = 'MODEL_VALIDATED_ONLY' if full and margin > 0 else 'UNSUPPORTED_OR_ECONOMICALLY_REJECTED'
    role_map = {'owner_operator_LAB_ALIAS': op, 'executor': actors['nqc_executor'],
                'financier': financier, 'builder': builder, 'proposer': proposer,
                'protocol': actors['Morpho'], 'DEX_pool': actors['dex_pair'],
                'borrower': actors['borrower'], 'WETH_wrapper': actors['WETH']}
    return {'scenario': run['scenario'], 'state': status, 'scope': 'LAB_ONLY', 'chain_id': 31337,
            'identities': role_map, 'same_financier_builder_address_in_this_fixture': financier == builder,
            'actual_production_ownership': 'UNKNOWN', 'personal_recourse': 'UNKNOWN',
            'funding_asset': 'ETH', 'principal_asset': 'WETH',
            'asset_identities': {'ETH': 'native:31337', 'WETH': actors['WETH'], 'COLLATERAL': actors['ERC20']},
            'cash_terms_wei': {k: str(s[k]) for k in ('A_disbursed_wei', 'R_refund_wei',
                 'U_actually_returned_wei', 'V_other_receipts_wei', 'F_funding_gas_wei',
                 'P_separate_proposer_payment_wei', 'O_other_cash_costs_wei')},
            'financier_cash_delta_wei': str(margin), 'builder_cash_delta_wei': str(deltas[builder]['ETH']),
            'proposer_cash_delta_wei': str(deltas[proposer]['ETH']),
            'financier_and_builder_deltas_are_not_additive_if_same_address': True,
            'NQC_WETH_residue_raw': str(deltas[op]['WETH']), 'NQC_retained_advance_wei': str(final[op]['ETH']),
            'all_addresses_asset_deltas_raw': {a:{k:str(v) for k,v in sorted(d.items())} for a,d in sorted(deltas.items())},
            'gas_units': total_gas, 'gas_cost_wei': str(total_cost), 'complete_local_path': full,
            'external_costs': 'UNKNOWN', 'real_financing_secured': False,
            'evidence_sources': [run['scenario'], 'titan_ledger'],
            'source_pointer': '/scenarios/' + run['scenario'] + '/cashflows_and_all_asset_balances'}


def validate_matrix(matrix):
    require(matrix['decision'] == 'FINANCING_DOCUMENTATION_BOUNDARY_REACHED', 'documentary boundary')
    require(matrix['commercial_admission'] is False, 'commercial admission prohibited')
    require(matrix['real_financier_committed'] is False, 'no commitment evidence')
    for row in matrix['mechanisms']:
        require(row['state'] in STATES and row['commercial_state'] in STATES, 'unknown state')
        require(row['state'] != 'SPECIFIC_PROVIDER_ACCEPTANCE_VERIFIED'
                and row['commercial_state'] != 'SPECIFIC_PROVIDER_ACCEPTANCE_VERIFIED', 'no specific acceptance evidence')
        require(row['provider_acceptance_evidence'] is None, 'no authenticated acceptance artifact')
        require(row['personal_recourse'] == 'UNKNOWN', 'silence is not no-recourse assurance')
    return True


def run():
    raw = sources(); retained = json.loads(raw['titan_ledger'])['scenarios']
    cases = [consolidate(json.loads(raw[name]), value['cashflows_and_all_asset_balances'])
             for name, value in sorted(retained.items())]
    matrix = json.loads((HERE / 'FINANCING_MATRIX.json').read_text()); validate_matrix(matrix)
    return {'schema': 'nqc057-consolidation-v1', 'pinned_sources_verified': len(raw),
            'decision': matrix['decision'], 'real_financier_committed': False,
            'new_EVM_scenarios': 0, 'lab_cases_cross_checked': len(cases), 'cases': cases,
            'NQC018_and_NQC023': 'Pinned published audit summaries read; their CI exports were not re-downloaded or independently replayed here.',
            'scope': 'Cross-check published lab flow extraction against pinned snapshots and receipts; no historical mainnet authentication or full EVM verification.',
            'personal_recourse': 'UNKNOWN', 'commercial_admission': False}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2, sort_keys=True))
