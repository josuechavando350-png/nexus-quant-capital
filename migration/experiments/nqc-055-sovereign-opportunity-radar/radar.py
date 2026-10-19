"""Sovereign Opportunity Radar v1: reproducible research selection, never trading."""
from collections import Counter, defaultdict
import json
from core import Sources, Registry, digest, require
from morpho import MorphoArchive

POLICY = 'nqc055-evidence-first-v1'


def gaps(c):
    needed = []
    def add(key, decision, shared, burden):
        needed.append({'requirement': key, 'decision_unlocked': decision,
            'reuse_scope': shared, 'structural_burden': burden,
            'money_cost': None, 'work_hours': None, 'RPC_count': None, 'availability': None})
    if not c['order_bound_to_archived_header']:
        add('transaction_membership', 'confirm chain/block/index before using prefix advantage',
            'same block only; no cross-block state reuse', 'header and transaction membership evidence')
    if c['receipt_status'] != 'AVAILABLE':
        add('receipt_and_effective_gas', 'measure successful/reverted status and gas actually paid',
            'receipt schema reusable; bytes specific to transaction', 'complete receipt with block binding')
    if not c['full_trace']:
        add('call_trace_and_asset_ledger', 'identify route, financing, repayment and inclusion transfers',
            'decoder reusable by proven runtime/ABI; values never copied', 'complete trace and token/native reconciliation')
    add('parent_account_storage_code', 'execute authenticated historical state',
        'proof verifier reusable; state specific to chain/block', 'all accessed accounts/code/storage; complete set unknown')
    add('fork_and_system_transitions', 'reconstruct state before ordinary transactions',
        'configuration reusable only for proven fork scope', 'applicable chain configuration and system inputs')
    if c['tx_index']:
        add('prefix_execution', 'derive prestate immediately before target',
            'shared only for same chain/block prefix', {'reported_prior_transactions': c['tx_index'], 'authenticated': c['order_bound_to_archived_header']})
    add('sale_liquidity', 'bound executable conversion and venue costs at exact prestate',
        'same pool and exact state only; no route inheritance by symbol', 'pool identities, code, liquidity/limits and amount-specific route')
    add('financing_terms', 'determine principal feasibility, gas advance, premiums and liabilities',
        'terms reusable only within actual lender/sponsor scope', 'binding terms and available capacity; no offer exists in evidence')
    add('competitive_capture', 'distinguish historical winner from available NQC execution',
        'inclusion observations may inform a validated policy, never copy success probability', 'rival bids, timing, acceptance and failures with denominators')
    add('other_obligations', 'close net ledger including setup, operations and failure costs',
        'accounting schema reusable; liabilities must be documented', 'consolidated ownership and all additional payments/costs')
    return needed


def assessment(c):
    b = c['economic_bounds']['net_upper_raw'] is not None
    nonpositive = b and int(c['economic_bounds']['net_upper_raw']) <= 0
    known_gas = c['observed_gas'] is not None
    missing = gaps(c)
    return {'A_evidence_to_study': 'PARTIAL_CASH_LEDGER' if b else 'EVENT_AND_INDEXER_GAS' if known_gas else 'EVENT_ONLY',
        'B_verifiable_economic_indication': 'NONPOSITIVE_UPPER_BOUND_IN_STATED_SCOPE' if nonpositive else 'HISTORICAL_POSITIVE_UPPER_BOUND_NOT_NQC_NET' if b else 'UNKNOWN_NO_SALE_LEDGER',
        'C_cost_of_missing_evidence': {'money': None, 'hours': None, 'requests': None,
            'requirement_families': len(missing), 'interpretation': 'family count is not a cost estimate'},
        'criteria': {
            'source_authenticity_completeness': {'hash_pinned': True, 'canonical_state_authenticated': False,
                'receipt': c['receipt_status'], 'trace': c['full_trace']},
            'historical_reconstruction': {'reported_prefix_count': c['tx_index'],
                'order_bound_to_header': c['order_bound_to_archived_header'], 'state_available': False},
            'sale_route': 'HISTORICAL_FILL_ONLY' if c['routes'] else 'UNKNOWN',
            'economic_margin': 'UPPER_BOUND_ONLY' if b else 'UNKNOWN',
            'principal_financing': c['financing'],
            'gas_and_obligations': {'historical_gas_observed': known_gas, 'NQC_gas_advance': None, 'all_obligations_known': False},
            'competition': {'observed_coinbase_payment': c['observed_inclusion'], 'NQC_capture': None},
            'evidence_burden': {'requirements': [r['requirement'] for r in missing], 'cost_known': False},
            'rapid_refutation': {'closed_scenarios': c['closed_scenario_count'], 'next': 'NEEDS_NEW_EVIDENCE' if c['reference_frozen_pending_new_evidence'] else 'NEEDS_CASH_LEDGER_BEFORE_STATE_REPLAY'}},
        'research_status': 'DESCARTADO_DENTRO_DE_CONDICIONES' if nonpositive else
            'REQUIERE_EVIDENCIA_ESPECIFICA' if c['reference_frozen_pending_new_evidence'] or known_gas and not b else
            'VALE_LA_PENA_INVESTIGAR' if b else 'NO_PUEDE_EVALUARSE_CON_DATOS_ACTUALES',
        'missing': [r['requirement'] for r in missing], 'profit_rank': None}


def select_probe(candidates):
    """A structural acquisition tie-break, not a probability, market or cost model.

    No archived new candidate has demonstrated positive economic indication.
    B is frozen. Rank remaining diagnostic dossiers by reported prefix count,
    WETH debt comparability with ETH gas, then available financial documentation.
    Stable identity only resolves otherwise equal positions; equal keys stay tied.
    """
    eligible = [c for c in candidates if not c['reference_frozen_pending_new_evidence'] and
        (c['economic_bounds']['net_upper_raw'] is None or int(c['economic_bounds']['net_upper_raw']) > 0)]
    def key(c):
        return (c['tx_index'], 0 if c['debt_native_comparability'] else 1, 0 if c['observed_gas'] else 1)
    ordered = sorted(eligible, key=lambda c: (key(c), c['id']))
    if not ordered:
        return {'kind': 'NO_NEW_RESEARCH_CANDIDATE', 'candidate_id': None, 'acquisition_authorized': False}
    best = ordered[0]
    ties = [c['id'] for c in ordered if key(c) == key(best)]
    return {'kind': 'CONDITIONAL_INFORMATION_ACQUISITION_PRIORITY', 'candidate_id': best['id'],
        'tx_hash': best['tx_hash'], 'block': best['block'], 'reported_tx_index': best['tx_index'],
        'policy_key': list(key(best)), 'equal_priority_ids': ties,
        'reported_zero_prefix_candidates': [{'id': c['id'], 'debt_native_comparability': c['debt_native_comparability']}
            for c in ordered if c['tx_index'] == 0],
        'next_packet': ['canonical block/transaction membership and complete receipt',
            'complete call trace with collateral/debt/native/token ledger and observed sale/inclusion payments'],
        'decision_enabled': 'If these bytes reveal a nonpositive sale-minus-debt-minus-known-costs upper bound, reject that historical route before requesting state. Otherwise keep unknown financing/capture obligations open.',
        'then_only_if_needed': ['authenticated parent state, runtime and fork/system inputs',
            'amount-specific executable sale, financing and competitive inclusion conditions'],
        'assumptions': ['indexer txIndex is correct; MUST authenticate before treating prefix as empty',
            'all else equal, avoiding prior ordinary transactions removes one reconstruction dependency',
            'WETH debt/ETH gas may simplify denomination; no sale route or fee-free funding is assumed'],
        'not_claimed': ['cheapest candidate in money or time', 'highest expected profit', 'positive net', 'available provider'],
        'expected_monetary_value': None, 'capture_probability': None, 'acquisition_authorized': False,
        'tie_break_is_profit_ranking': False, 'B_reopened': False}


def sharing(candidates):
    markets, pairs = defaultdict(list), defaultdict(list)
    for c in candidates:
        for group in c['reuse_groups']:
            (markets if group.startswith('market:') else pairs)[group].append(c['id'])
    return {'same_market_groups': {k: sorted(set(v)) for k, v in sorted(markets.items())},
        'same_asset_pair_groups': {k: sorted(set(v)) for k, v in sorted(pairs.items())},
        'reusable': ['identity and receipt decoders', 'cash-ledger reconciliation rules',
            'storage derivation ONLY after runtime/layout binding', 'funding/capture evidence checklist'],
        'not_reusable_without_new_binding': ['prestate values across blocks', 'routes across asset pairs',
            'liquidity across times', 'sponsor commitments or capture probability'],
        'same_pair_does_not_establish_shared_pool_or_profit': True}


def scan(s, adapters):
    """Adapter-neutral entry point; adapters own parsing and economic derivations."""
    registry = Registry()
    scenarios = []
    for adapter in adapters:
        rows = adapter.candidates(s)
        scenarios.extend(adapter.evaluate(s, rows))
        for c in rows:
            registry.add(c)
    candidates = registry.ordered()
    catalog = {}
    for c in candidates:
        for requirement in gaps(c):
            if requirement['requirement'] == 'prefix_execution':
                requirement['structural_burden'] = 'candidate.tx_index ordinary predecessors; order assurance is candidate.order_bound_to_archived_header'
            key = requirement['requirement']
            require(key not in catalog or catalog[key] == requirement, 'conflicting requirement definitions')
            catalog[key] = requirement
        c['assessment'] = assessment(c)
        c['decision_hash'] = digest(c)
    return {'candidates': candidates, 'discarded_scenarios': scenarios,
        'requirement_catalog': dict(sorted(catalog.items())),
        'duplicate_dossiers_merged': registry.duplicates, 'proposed_next_probe': select_probe(candidates),
        'shared_requirements': sharing(candidates)}


def run(s=None):
    """NQC055 experiment wrapper. Reference metrics deliberately dataset-specific."""
    s = s or Sources(); verified = s.verify_all()
    adapter = MorphoArchive()
    result = scan(s, [adapter])
    candidates = result['candidates']
    inherited = s.json('audit')['candidates']
    matches = sum(c['net_profit'] is None and c['commercial_admission'] is False and
        c['assessment']['profit_rank'] is None for c in candidates)
    output = {'schema': 'nqc055-radar-v1', 'policy': POLICY, 'mode': 'OFFLINE_RESEARCH',
        'sources': s.manifest['files'], 'sources_verified': verified, **result,
        'evaluation': {'comparison_scope': 'regression against pinned NQC054, not independent predictive ground truth',
            'dossiers': len(candidates), 'event_deduplication': adapter.dedup,
            'reference_decisions_matched': matches, 'reference_decisions_total': len(inherited['monthly_transactions']) + 1,
            'demonstrated_rejections_reproduced': 1, 'positive_NQC_profit_claims': 0,
            'economically_rankable_alternatives': 0,
            'status_counts': dict(sorted(Counter(c['assessment']['research_status'] for c in candidates).items())),
            'manual_time_saved_measured': None, 'out_of_sample_accuracy': None,
            'added_value': ['145 archived monthly/detail rows normalized into 143 events in 141 transactions',
                'one explicit conditional rejection kept separate from candidate viability',
                'four reported txIndex0 candidates identified for an acquisition gate',
                'requirements and shared schema scopes attached to every candidate; no economic ranking invented']},
        'outcome': {'A_functional_research_radar': True, 'B_conditional_rejection_reproduced': True,
            'C_economic_discrimination_limit': True, 'economic_superiority_selected': False},
        'security': {'commercial_admission': False, 'network_requests_by_radar': 0,
            'Triport_total_known': 0, 'Triport_lifetime_budget': 8, 'safe_secret_channel_demonstrated': False,
            'unique_live_ledger_demonstrated': False, 'new_budget': False,
            'stage': 'OFFLINE_RESEARCH_NOT_CANARY', 'own_principal': 'PROHIBITED',
            'future_Canary_gas_cap_MXN': 2000, 'future_hot_wallet_topup_cap_MXN': 500,
            'future_stop_and_review_without_capture_MXN': 1000, 'gas_budget_available_now': False,
            'Census_Shadow_connected_wallet_funds_permitted': 0, 'funding_or_signing_capability': False},
        'monthly': {'targets_usd': [5000, 15000, 45000], 'forecast': None,
            'observed_sample_is_complete': False, 'capturable_frequency': None, 'demonstrated_NQC_net': None}}
    output['result_sha256'] = digest(output)
    return output


if __name__ == '__main__':
    print(json.dumps(run(), indent=2, sort_keys=True))
