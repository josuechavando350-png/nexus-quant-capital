"""NQC058: immutable Morpho results + public Aave evidence, offline only.

Reuses NQC055's exact-unit kernel/registry. No transport or executor.
Human source transcriptions remain source assertions, not consensus proofs.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import types

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
MANIFEST = json.loads((HERE / 'SOURCE_MANIFEST.json').read_bytes())


def verify_bytes(raw, pin):
    if (len(raw) != pin['bytes'] or hashlib.sha256(raw).hexdigest() != pin['sha256']
            or hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() != pin['git_blob_sha1']):
        raise ValueError('source integrity mismatch')
    return raw


# Load the exact original module, not an unverified current working-tree copy.
_pin = MANIFEST['files']['kernel']
_raw = verify_bytes(subprocess.check_output(['git', '-C', str(REPO), 'show',
                                           _pin['commit'] + ':' + _pin['path']]), _pin)
core = types.ModuleType('nqc055_core')
core.__file__ = str(REPO / _pin['path'])
sys.modules[core.__name__] = core
exec(compile(_raw, core.__file__, 'exec'), core.__dict__)

ETH = core.Asset(1, 'native:ETH', 18)
PUF = '0x34162fda07ca0ae1054d7c1252b8d1c48aba9a675fd3d09816393c29d8be50e4'
DENIED_REPORT_TX = '0x25784da3e88e979dbe4257cfe9cd3dd9b1c40a7f7d317be2132abf43f38f48ea'


class Evidence:
    def __init__(self):
        self.git = core.Sources(MANIFEST)
        self.inputs = core.parse((HERE / 'INPUT_MANIFEST.json').read_bytes())['files']

    def local(self, name):
        return core.parse(verify_bytes((HERE / name).read_bytes(), self.inputs[name]))

    def ref(self, name, pointer=''):
        value = self.local(name)
        for part in pointer.lstrip('/').split('/') if pointer else []:
            value = value[int(part)] if isinstance(value, list) else value[part]
        return {'file': name, 'pointer': pointer, **self.inputs[name]}

    def verify_all(self):
        for name in self.inputs:
            self.local(name)
        return {'git_pins': self.git.verify_all(), 'local_transcriptions_and_review': len(self.inputs)}


def decode_liquidation(record):
    core.require(record['chain_id'] == 1 and type(record['chain_id']) is int, 'Ethereum chain scope')
    core.require(record['to'] == '0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2', 'reported pool mismatch')
    core.require(record['method_id'] == '0x00a718a9', 'liquidation selector')
    words = record['calldata_words']
    core.require(len(words) == 5 and all(re.fullmatch('[0-9a-f]{64}', w) for w in words), 'ABI word length')
    core.require(all(w[:24] == '0' * 24 for w in words[:3]), 'address padding')
    core.require(int(words[4], 16) in (0, 1), 'ABI boolean')
    return {'collateral_address_requested': '0x' + words[0][24:],
            'debt_address_requested': '0x' + words[1][24:],
            'borrower_requested': '0x' + words[2][24:],
            'debt_to_cover_requested_raw': str(int(words[3], 16)),
            'receive_a_token_requested': bool(int(words[4], 16)),
            'requested_is_actual_transfer': False}


def failed_attempt(record, ref, *, exclude_external_compensation):
    """A scope bound for an included failed direct call, NOT its sender's total P&L."""
    decoded = decode_liquidation(record)
    core.require(type(exclude_external_compensation) is bool, 'explicit compensation scope required')
    core.integer(record['tx_index'])
    core.require(record['status'] == 'Fail' and record['value_wei'] == '0', 'failed direct-call scope')
    used = core.integer(record['gas_used'])
    core.require(0 < used <= core.integer(record['gas_limit']), 'gas range')
    price = core.units(record['effective_gas_price_gwei'], 9)
    base = core.units(record['base_fee_gwei'], 9)
    fee = core.units(record['fee_eth'], 18)
    burnt = core.units(record['burnt_eth'], 18)
    core.require(price >= base and used * price == fee and used * base == burnt, 'gas fee reconciliation')
    refs = (ref,)
    # Failed call produces no committed application revenue. Outside reimbursement
    # is excluded ONLY in the named scenario; unrestricted actor P&L stays unknown.
    sale = core.Interval(ETH, 0, 0 if exclude_external_compensation else None, refs)
    costs = []
    for category in sorted(core.REQUIRED_COSTS):
        known = fee if category == 'gas' else 0 if category == 'debt' else None
        covers = frozenset({'gas_base', 'gas_priority'}) if category == 'gas' else frozenset({category})
        costs.append(core.Cost(category, category, core.Interval(ETH, known or 0, known, refs), covers))
    result = core.bounds(sale, costs, hypothetical=True)
    result.update({'scope': 'Conditioned on explorer Fail being correct; only this included direct call; nonnegative extra costs. Not sender lifetime P&L or a rejection of Aave. ' + ('Outside compensation excluded in this scenario.' if exclude_external_compensation else 'Outside compensation unbounded; total net cannot be bounded above.'),
                   'classification': 'ECONOMICAMENTE_DESCARTADO' if result['net_upper_raw'] is not None else 'EVIDENCIA_INSUFICIENTE',
                   'external_compensation_excluded': exclude_external_compensation,
                   'unrestricted_actor_net_raw': None, 'source_grade': 'EXPLORER_ASSERTION_NOT_CANONICAL_PROOF'})
    flows = [
        {'payer': record['sender'], 'payee_role': 'base_fee_burn', 'amount_raw': str(burnt), 'asset': ETH.json(), 'economic_component': 'gas_base'},
        {'payer': record['sender'], 'payee_role': 'block_fee_recipient_unknown_address', 'amount_raw': str(fee - burnt), 'asset': ETH.json(), 'economic_component': 'gas_priority'}]
    return decoded, result, {'gas_cost_raw': str(fee), 'gas_used': used, 'effective_price_wei': str(price),
                           'flows': flows, 'add_flows_to_gas_again': False,
                           'sender_owner_is_NQC': None, 'financier_identity': None,
                           'builder_identity': None, 'proposer_identity': None,
                           'outside_reimbursement': None, 'personal_recourse': 'UNKNOWN'}


def unknown_bounds():
    return {'net_lower_raw': None, 'net_upper_raw': None, 'asset': None,
            'reason': 'No actual sale or complete participant liabilities', 'commercial_admission': False}


class MorphoPublished:
    """Projection of the pinned radar; no new census or repeated old simulation."""
    def candidates(self, evidence):
        source = evidence.git.json('radar055')
        status = evidence.git.json('status056')
        core.require(status['classification'] == 'EVIDENCIA_INSUFICIENTE' and not status['new_onchain_authentication'], '056 boundary changed')
        rows = []
        for i, old in enumerate(source['candidates']):
            keys = ['id', 'chain_id', 'protocol', 'family', 'tx_hash', 'block', 'tx_index',
                    'contracts', 'events', 'economic_bounds', 'financing', 'competition',
                    'observed_sale', 'observed_gas', 'observed_inclusion', 'receipt_status',
                    'order_bound_to_archived_header', 'historical_state_authenticated']
            c = {k: copy.deepcopy(old[k]) for k in keys}
            c.update({'classification': 'EVIDENCIA_INSUFICIENTE', 'evidence_grade': old['assessment']['A_evidence_to_study'],
                      'source_refs': [evidence.git.ref('radar055', f'/candidates/{i}')],
                      'missing': old['assessment']['missing'], 'commercial_admission': False,
                      'NQC_capture_demonstrated': False, 'currently_executable': False,
                      'net_profit_captured_by_NQC': None, 'economic_rank': None,
                      'research_state': 'SUSPENDED_EXISTING_INFORMATION_BOUNDARY',
                      'closed_scenarios': old['closed_scenario_count']})
            if old['tx_hash'] == PUF:
                c['source_refs'].append(evidence.git.ref('status056'))
                c['research_state'] = 'SUSPENDED_NQC056_NO_RETRY'
            rows.append(c)
        return rows


class AavePublic:
    def candidates(self, evidence):
        raw = evidence.local('inputs/aave_failed.json')
        ref = evidence.ref('inputs/aave_failed.json')
        decoded, result, book = failed_attempt(raw, ref, exclude_external_compensation=True)
        failed = self.base(raw['tx_hash'], raw['block'], raw['tx_index'], ref)
        failed.update({'evidence_grade': 'EXPLORER_FAILED_CALL_AND_FEE', 'classification': result['classification'],
                       'call_requested': decoded, 'economic_bounds': result, 'participant_book': book,
                       'contracts': {'reported_pool': raw['to'], 'runtime_verified': False},
                       'receipt_status': 'FAIL_REPORTED_BY_EXPLORER_NO_RAW_RECEIPT',
                       'research_state': 'CLOSED_FAILED_ATTEMPT_SCOPE', 'closed_scenarios': 1,
                       'actual_debt_repaid_raw_in_failed_call': '0', 'actual_collateral_received_raw_in_failed_call': '0',
                       'sale_output_raw_in_failed_call': '0', 'amount_scope': 'Committed call effects if reported failure is correct',
                       'missing': ['canonical_receipt_transaction_binding', 'outside_compensation_and_liabilities']})
        report = evidence.local('inputs/aave_report.json')
        core.require(type(report['chain_id']) is int and report['chain_id'] == 1, 'Aave report chain')
        rows = [failed]
        for i, item in enumerate(report['rows']):
            for field in ('seized_reference_usd_rounded', 'repaid_reference_usd_rounded'):
                core.integer(item[field])
            c = self.base(item['tx_hash'], item['block'], None, evidence.ref('inputs/aave_report.json', f'/rows/{i}'))
            c.update({'evidence_grade': 'PRIMARY_REPORT_NO_RECEIPT', 'classification': 'EVIDENCIA_INSUFICIENTE',
                      'research_state': 'REQUIRES_COMPLETE_HISTORICAL_PACKET', 'closed_scenarios': 0,
                      'reported_reference_valuations': {k: item[k] for k in ('seized_reference_usd_rounded', 'repaid_reference_usd_rounded')},
                      'valuation_is_sale': False, 'collateral': {'symbol_reported': 'AAVE', 'address': None, 'decimals': None, 'amount_raw': None},
                      'debt': {'symbol_reported': 'USDC', 'address': None, 'decimals': None, 'amount_raw': None},
                      'borrower': None, 'contracts': None, 'receipt_status': 'NO_RECEIPT_ACQUIRED',
                      'economic_bounds': unknown_bounds(), 'participant_book': None,
                      'reported_liquidation_is_successful_NQC_capture': False,
                      'source_inferred_inventory_sale': item['block'] == 24394116,
                      'inventory_sale_verified': False,
                      'known_direct_page_access_blocked': item['tx_hash'] == DENIED_REPORT_TX,
                      'missing': ['canonical_identity_and_order', 'actual_debt_collateral_units_and_contracts',
                                  'receipt_gas_and_trace', 'sale_route_liquidity_and_proceeds',
                                  'protocol_fee_SVR_inclusion_allocation', 'flash_amount_fee_repayment',
                                  'gas_funding_and_no_recourse', 'outside_obligations', 'competitive_capture']})
            rows.append(c)
        return rows

    def base(self, tx, block, index, ref):
        return {'id': f'eip155:1/aave-v3/{tx}', 'chain_id': 1, 'protocol': 'aave-v3',
                'family': 'lending_liquidation', 'tx_hash': tx, 'block': core.integer(block), 'tx_index': index,
                'order_bound_to_archived_header': False, 'historical_state_authenticated': False,
                'source_refs': [ref], 'commercial_admission': False, 'NQC_capture_demonstrated': False,
                'net_profit_captured_by_NQC': None, 'currently_executable': False, 'economic_rank': None,
                'financing': {'principal_mechanism': 'Documentary Aave flashLoanSimple or flashLoan mode 0, subject to amount, fee, liquidity and repay; not observed here',
                              'own_principal_authorized': False, 'available_amount_raw': None, 'premium_raw': None,
                              'gas_sponsor_available': None, 'provider_acceptance': False, 'personal_recourse': 'UNKNOWN'},
                'competition': {'rival_bids': None, 'capture_probability': None, 'acceptance_of_NQC_bid': None}}


def compare(evidence=None, adapters=None):
    evidence = evidence or Evidence()
    verified = evidence.verify_all()
    registry = core.Registry()
    for adapter in adapters if adapters is not None else [MorphoPublished(), AavePublic()]:
        for c in adapter.candidates(evidence):
            registry.add(c)
    candidates = registry.ordered()
    report_group = sorted(c['id'] for c in candidates if c['protocol'] == 'aave-v3'
                          and c['evidence_grade'] == 'PRIMARY_REPORT_NO_RECEIPT')
    # No cross-protocol profitability score. Exclude a known denied URL as an
    # operational acquisition target. Lexical choice only represents an equal group.
    eligible = [i for i in report_group if not i.endswith(DENIED_REPORT_TX)]
    groups = []
    for protocol in sorted({c['protocol'] for c in candidates}):
        rows = [c for c in candidates if c['protocol'] == protocol]
        groups.append({'protocol': protocol, 'chain_id': 1, 'dossiers': len(rows),
                       'net_positive_demonstrated': 0, 'economic_rank': None,
                       'scenarios_rejected': sum(c['closed_scenarios'] for c in rows),
                       'new_public_observations': len(rows) if protocol == 'aave-v3' else 0,
                       'financier_committed': False, 'GO_for_financial_execution': False,
                       'profitability': 'UNKNOWN'})
    inherited = evidence.git.json('radar055')['discarded_scenarios']
    finance = evidence.git.json('status057')
    core.require(not finance['real_financier_committed'] and finance['personal_recourse'] == 'UNKNOWN', 'funding baseline changed')
    for c in candidates:
        c['decision_hash'] = core.digest(c)
    output = {'schema': 'nqc058-multi-mine-v1', 'sources_verified': verified, 'candidates': candidates,
              'mine_matrix': groups, 'duplicate_dossiers_merged': registry.duplicates,
              'inherited_discarded_scenarios': inherited,
              'economic_result': 'OPORTUNIDAD_RENTABLE_NO_DEMOSTRADA',
              'distinct_protocol_mines': len(groups), 'distinct_strategy_families': len({c['family'] for c in candidates}),
              'live_protocol_coverage': 0, 'NQC_net_profit_demonstrated': None,
              'decision': {'financial_execution': 'NO-GO', 'profitability': 'UNKNOWN', 'bounded_offline_evidence_review': 'GO'},
              'next_information_probe': {'kind': 'CONDITIONAL_PACKET_NOT_PROFIT_WINNER',
                                         'equal_evidence_group': report_group,
                                         'representative_id': eligible[0] if eligible else None,
                                         'tie_break': 'canonical ID only; no economic or cost advantage claimed',
                                         'known_denied_targets_not_retried': [DENIED_REPORT_TX],
                                         'public_packet_source_available': None, 'new_restricted_acquisition_authorized': False,
                                         'value': 'One complete ledger may reveal nonpositive net upper bound before costly replay; benefit and acquisition cost unknown'},
              'monthly': {'targets_USD': [5000, 15000, 45000], 'forecast': None, 'capturable_frequency': None,
                          'coverage_complete': False, 'NQC_net_per_capture': None},
              'security': {'commercial_admission': False, 'new_RPC_requests': 0, 'Triport_known_lifetime_used': 0,
                           'Triport_lifetime_budget': 8, 'credential_channel_demonstrated': False,
                           'unique_operational_ledger_demonstrated': False, 'canary_enabled': False,
                           'own_principal_authorized': False, 'wallet_funds_Census_Shadow': 0,
                           'gas_budget_available_now': False, 'future_gas_cap_MXN': 2000,
                           'future_topup_cap_MXN': 500, 'future_review_without_capture_MXN': 1000}}
    output['result_sha256'] = core.digest(output)
    return output


if __name__ == '__main__':
    print(json.dumps(compare(), indent=2, sort_keys=True))
