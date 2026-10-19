"""Only installed adapter: archived Ethereum Morpho liquidation observations."""
from collections import defaultdict
from core import Asset, Cost, Interval, bounds, canonical, integer, require

TX_B = '0x46300e9614c547118ecdd524bc7218208088cc4ae9e5bd534e62055d38f9925b'
MORPHO = '0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb'
WETH = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'
ETH = Asset(1, 'native:ETH', 18)


def asset(raw):
    return Asset(1, raw['address'].lower(), raw['decimals']).json()


def normalize_event(row, explicit_query_chain=None):
    chain = row.get('chain', {}).get('id', explicit_query_chain)
    require(type(chain) is int and chain == 1 and row['type'] == 'Liquidation', 'Morpho source chain/type')
    return {'chain_id': chain, 'tx_hash': row['txHash'].lower(),
        'block': integer(row['blockNumber']), 'tx_index': integer(row['txIndex']),
        'log_index': integer(row['logIndex']), 'timestamp': integer(row['timestamp']),
        'market_id': row['market']['marketId'].lower(), 'lltv_raw': str(integer(row['market']['lltv'])),
        'loan': asset(row['market']['loanAsset']), 'collateral': asset(row['market']['collateralAsset']),
        'repaid_raw': str(integer(row['data']['repaidAssets'])),
        'seized_raw': str(integer(row['data']['seizedAssets'])),
        'bad_debt_raw': str(integer(row['data']['badDebtAssets'])),
        'liquidator': row['data']['liquidator'].lower(), 'borrower': None}


def b_ledger(s, *, finance_fee=None, free_gas=False):
    """ETH-equivalent obligation ONLY for B's archived wrapping route.

    This is an explicit case-specific 1:1 WETH settlement conversion, not a
    general token-price conversion. No token names are used as exchange rates.
    """
    p = s.json('economics')['case_b']
    require(p['chain_id'] == 1 and p['tx_hash'] == TX_B and p['loan_asset'] == WETH, 'B ledger identity')
    ref = s.ref('economics', '/case_b')
    route_ref = s.ref('audit', '/economics/inherited_reconciled_ledger')
    sale = Interval(ETH, p['sale_output_eth_wei'], p['sale_output_eth_wei'], (ref,))
    exact = {'debt': p['repaid_debt_weth_wei'], 'gas': 0 if free_gas else p['gas_cost_wei'],
             'inclusion': p['coinbase_transfer_wei']}
    costs = []
    for category in ('debt', 'gas', 'inclusion', 'financing', 'failures', 'operations', 'other'):
        value = finance_fee if category == 'financing' else exact.get(category)
        provenance = ({'hypothesis': 'all gas removed, not executable'},) if category == 'gas' and free_gas else (
            ({'hypothesis': 'full debt financing fee, not a lender offer'},) if category == 'financing' and finance_fee is not None else (ref, route_ref))
        amount = Interval(ETH, 0 if value is None else value, value, provenance)
        covers = frozenset({'gas_base', 'gas_priority'}) if category == 'gas' else frozenset({category})
        costs.append(Cost(category, category, amount, covers))
    return sale, costs


class MorphoArchive:
    family = 'lending_liquidation'

    def evaluate(self, s, candidates):
        b = next(c for c in candidates if c['tx_hash'] == TX_B)
        sale, costs = b_ledger(s)
        b['economic_bounds'] = bounds(sale, costs, embedded=frozenset({'venue_fee', 'price_impact'}))
        b['economic_bounds']['scope'] = 'Inherited historical ETH-equivalent ledger; WETH principal converted 1:1 only for observed B wrapping/repayment route; nonnegative additional liabilities and no unevidenced extra income.'
        debt = s.json('economics')['case_b']['repaid_debt_weth_wei']
        sale, costs = b_ledger(s, finance_fee=(debt + 9999) // 10000, free_gas=True)
        rejected = bounds(sale, costs, embedded=frozenset({'venue_fee', 'price_impact'}), hypothetical=True)
        rejected.update({'id': b['id']+'/full-debt-fee-at-least-1bp', 'candidate_id': b['id'],
            'scope': 'Same historical sale and complete coinbase transfer; full debt financing >=1bp; zero gas is optimistic upper bound; other costs nonnegative.',
            'fee_bps_lower': '1', 'financing_offer_exists': False,
            'reference': s.ref('audit', '/economics/scenarios/2'), 'all_Morpho_discarded': False})
        require(rejected['net_upper_raw'] == str(s.json('audit')['economics']['scenarios'][2]['upper_bound_even_if_gas_zero_wei']), 'NQC054 rejection parity')
        b['closed_scenario_count'] = 1
        for c in candidates:
            if c is not b:
                c['economic_bounds'] = {'net_lower_raw': None, 'net_upper_raw': None,
                    'reason': 'No sale ledger or common-unit valuation; amounts are not profit', 'commercial_admission': False}
        return [rejected]

    def candidates(self, s):
        audit = s.json('audit'); econ = s.json('economics')['case_b']
        require(audit['prestate']['chain_id'] == 1 and audit['prestate']['target_tx'] == TX_B, 'B state scope')
        coverage = {r['tx_hash']: r for r in audit['candidates']['monthly_transactions']}
        events, event_refs, duplicate_count, metadata = {}, defaultdict(list), 0, {}
        def ingest(row, ref, query_chain=None):
            nonlocal duplicate_count
            e = normalize_event(row, query_chain)
            key = (e['chain_id'], e['tx_hash'], e['log_index'])
            for token in (e['loan'], e['collateral']):
                k = (token['chain_id'], token['address'])
                require(k not in metadata or metadata[k] == token['decimals'], 'conflicting asset decimals')
                metadata[k] = token['decimals']
            if key in events:
                require(events[key] == e, 'conflicting duplicate event')
                duplicate_count += 1
            else:
                events[key] = e
            event_refs[key].append(ref)
        for name in ('page0', 'page1'):
            for i, row in enumerate(s.json(name)['response']['data']['marketTransactions']['items']):
                ingest(row, s.ref(name, f'/response/data/marketTransactions/items/{i}'))
        selected = s.json('selected')
        require('chainId_in: [1]' in selected['request']['query'], 'unbound selected chain')
        for i, row in enumerate(selected['response']['data']['marketTransactions']['items']):
            ingest(row, s.ref('selected', f'/response/data/marketTransactions/items/{i}'), 1)
        require(len(events) == 143 and duplicate_count == 2, 'archived event membership')
        grouped = defaultdict(list)
        for key in sorted(events):
            grouped[key[1]].append({**events[key], 'refs': sorted(event_refs[key], key=canonical)})
        require(set(grouped) == set(coverage), 'NQC054 candidate membership conflict')
        rows = []
        for tx, items in sorted(grouped.items()):
            require(len({(e['block'], e['tx_index']) for e in items}) == 1, 'transaction block/index conflict')
            c = self.base(tx, items[0]['block'], items[0]['tx_index'], items,
                          coverage[tx]['receipt_status'], 'B' if tx == TX_B else 'monthly')
            c['refs'] = [s.ref('audit', '/candidates/monthly_transactions')] + [r for e in items for r in e['refs']]
            require(c['block'] == coverage[tx]['block'] and c['tx_index'] == coverage[tx]['tx_index'], 'NQC054 identity conflict')
            if tx == TX_B:
                c.update({'observed_sale': {'amount_raw': str(econ['sale_output_eth_wei']), 'asset': ETH.json()},
                    'observed_gas': {'amount_raw': str(econ['gas_cost_wei']), 'asset': ETH.json()},
                    'observed_inclusion': {'amount_raw': str(econ['coinbase_transfer_wei']), 'asset': ETH.json()},
                    'routes': [{'kind': 'historical_fill', 'pool': econ['pool'], 'liquidity': econ['liquidity'],
                        'mechanism': 'Morpho collateral-first callback then Fluid sale and WETH repayment',
                        'counterfactual_available': None}], 'borrower': econ['borrower'],
                    'contracts': {'morpho': MORPHO, **audit['prestate']['contracts'],
                        'pool': econ['pool'], 'liquidity': econ['liquidity'], 'executor': econ['external_executor']},
                    'order_bound_to_archived_header': True, 'full_trace': True,
                    'financing': {'principal_advance_necessary_for_observed_callback': False,
                        'own_principal_authorized': False, 'gas_sponsor_available': None, 'premium': None,
                        'NQC_funding_demonstrated': False},
                    'reference_frozen_pending_new_evidence': True})
                c['refs'] += [s.ref('economics', '/case_b'), s.ref('audit', '/prestate'),
                    s.ref('B_receipt'), s.ref('B_trace'), s.ref('B_route')]
            rows.append(c)
        a = s.json('A'); ap = s.json('A_params'); inherited = audit['candidates']['older_case_A']
        require(a['chain_id'] == 1 and a['transaction_hash'] == inherited['tx_hash'] == ap['transaction_hash'], 'A identity')
        event = {'chain_id': 1, 'tx_hash': a['transaction_hash'], 'block': a['block_number'],
            'tx_index': inherited['tx_index'], 'log_index': None, 'market_id': ap['market_id'],
            'loan': Asset(1, a['loan_token'].lower(), a['loan_decimals']).json(),
            'collateral': Asset(1, a['collateral_token'].lower(), a['collateral_decimals']).json(),
            'repaid_raw': str(integer(a['repaid_loan_raw'])), 'seized_raw': str(integer(a['seized_collateral_raw'])),
            'bad_debt_raw': None, 'borrower': a['borrower_address'].lower(),
            'refs': [s.ref('A'), s.ref('A_params')]}
        c = self.base(a['transaction_hash'], a['block_number'], inherited['tx_index'], [event], 'OBSERVED_NULL', 'A')
        c.update({'refs': [s.ref('A'), s.ref('A_params'), s.ref('audit', '/candidates/older_case_A')],
            'observed_gas': {'amount_raw': a['actual_fee_wei'], 'asset': ETH.json(), 'quality': 'indexer_only'},
            'borrower': a['borrower_address'].lower(), 'original_callback_empty': True})
        rows.append(c)
        self.dedup = {'monthly_unique_events': len(events), 'monthly_unique_transactions': len(grouped),
                      'original_observation_rows_processed': len(events) + duplicate_count,
                      'duplicate_events_merged': duplicate_count, 'older_dossiers_added': 1}
        return rows

    def base(self, tx, block, index, events, receipt, label):
        return {'id': f'eip155:1/morpho-blue/{tx}', 'chain_id': 1, 'protocol': 'morpho-blue',
            'family': self.family, 'label': label, 'tx_hash': tx, 'block': block, 'tx_index': index,
            'mechanism': 'liquidation collateral realization minus debt and all obligations',
            'debt_native_comparability': all(e['loan']['address'] == WETH for e in events),
            'reuse_groups': sorted(set(['market:1:morpho-blue:'+e['market_id'] for e in events]+
                ['pair:1:'+e['loan']['address']+':'+e['collateral']['address'] for e in events])),
            'closed_scenario_count': 0,
            'contracts': {'morpho': MORPHO}, 'borrower': None, 'events': events,
            'receipt_status': receipt, 'full_trace': False, 'historical_state_authenticated': False,
            'order_bound_to_archived_header': False, 'observed_sale': None, 'observed_gas': None,
            'observed_inclusion': None, 'routes': [], 'collateral_value': None, 'debt_value_usd': None,
            'funding_advance_is_income': False, 'net_profit': None, 'economic_rank': None,
            'financing': {'own_principal_authorized': False, 'principal_funding_available': None,
                'gas_sponsor_available': None, 'premium': None, 'NQC_funding_demonstrated': False},
            'competition': {'rival_bids': None, 'acceptance_of_NQC_bid': None, 'capture_probability': None},
            'currently_executable': False, 'NQC_capture_demonstrated': False,
            'reference_frozen_pending_new_evidence': False, 'commercial_admission': False}
