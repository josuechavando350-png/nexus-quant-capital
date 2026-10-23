"""Join retained predecessor-state witnesses to historical competitor cashflows.

Prices and Pool fee parameters are block-end observations. A fee calculated on
historical debt is conditional, not a paid fee. Hindsight-selected winners never
become a prospective signal, an executable order, or a complete net-profit row.
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import re
import tempfile

from cashflow_intake import PRICE_NAMES, build_cashflow, store_cashflow
from evidence_store import admit, read_batch, safe_path
from historical_intake import (API, AUTHORITIES, EVIDENCE, PINS, ROOT, SOURCE,
    SOURCE_ID, build_ledger, fields, need, same, unpack, utc)
from historical_pipeline import LEDGER_NAME, SOURCE_NAMES
from integrity import canonical, digest, read_regular, strict_json
from liquidator_intake import CAPTURE_NAMES, build_liquidator_report

SCHEMA = 'nqc.omega.historical-predecessor-state.v1'
PIN_SHA256 = '5e9c18944805c8c4eab1b92200b16336b8d44155f633dbc07cf4188ed8d0405c'
SOURCE_KEYS = ('rank2-price', 'aave-premium', 'top3-health')
STATE_NAMES = {'historical-state-pin.json'} | {
    key + suffix for key in SOURCE_KEYS for suffix in ('-original.zip', '-metadata.json')}
REPORT_NAME = 'historical-state-report.json'
WETH = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'
POOL = '0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2'
HASH = re.compile(r'0x[0-9a-f]{64}\Z')
ADDRESS = re.compile(r'0x[0-9a-f]{40}\Z')
WAD = 10**18


def uint(value):
    need(type(value) is str and re.fullmatch(r'0|[1-9][0-9]*', value)
         and int(value) < 2**256, 'noncanonical_uint256')
    return int(value)


def signed_reference(amount, price):
    """USD-WAD at a USD-1e8 reference, truncating toward zero."""
    need(type(amount) is int, 'noninteger_amount')
    p = uint(price)
    need(p > 0, 'zero_reference_price')
    return str((abs(amount) * p // 10**8) * (-1 if amount < 0 else 1))


def percent_mul(amount, bps):
    need(type(amount) is int and 0 <= amount < 2**256
         and type(bps) is int and 0 <= bps <= 10000, 'invalid_fee_input')
    need(bps == 0 or amount <= (2**256 - 1 - 5000) // bps,
         'percent_mul_overflow')
    return (amount * bps + 5000) // 10000 if bps else 0


def load_state_sources(directory=EVIDENCE):
    directory = Path(directory)
    raw = read_regular(directory / 'historical-state-pin.json')
    need(digest(raw) == PIN_SHA256, 'state_pin_changed')
    pin = strict_json(raw)
    need(canonical(pin) == raw and set(pin['sources']) == set(SOURCE_KEYS),
         'state_pin_inventory')
    reports, provenance = {}, {}
    for name in SOURCE_KEYS:
        p = pin['sources'][name]
        raw_meta = read_regular(directory / (name + '-metadata.json'))
        need(digest(raw_meta) == p['metadata_sha256'], 'state_metadata_pin_changed')
        meta = strict_json(raw_meta)
        run, commit, art = (meta[k] for k in ('run', 'commit', 'artifact'))
        fields(run, {'id': p['run_id'], 'head_sha': p['commit'], 'head_branch': p['branch'],
            'status': 'completed', 'conclusion': 'success', 'run_attempt': 1,
            'path': p['workflow'], 'workflow_id': p['workflow_id'],
            'url': API + f"/actions/runs/{p['run_id']}"}, 'state_run')
        for key in ('repository', 'head_repository'):
            fields(run[key], {'id': SOURCE_ID, 'full_name': SOURCE, 'private': False}, 'state_repo')
        fields(run['head_commit'], {'id': p['commit'], 'tree_id': p['tree']}, 'state_head')
        fields(commit, {'sha': p['commit'], 'url': API + '/git/commits/' + p['commit']}, 'state_commit')
        fields(commit['tree'], {'sha': p['tree']}, 'state_tree')
        fields(art, {'id': p['artifact_id'], 'name': p['artifact_name'],
            'expired': False, 'size_in_bytes': p['archive_bytes'],
            'digest': 'sha256:' + p['archive_sha256'],
            'url': API + f"/actions/artifacts/{p['artifact_id']}"}, 'state_artifact')
        fields(art['workflow_run'], {'id': p['run_id'], 'head_sha': p['commit'],
            'head_branch': p['branch'], 'repository_id': SOURCE_ID,
            'head_repository_id': SOURCE_ID}, 'state_artifact_run')
        need(utc(run['created_at']) <= utc(run['run_started_at']) <= utc(art['created_at'])
             <= utc(run['updated_at']) <= utc(meta['retrieved_at']) < utc(art['expires_at']),
             'state_capture_order')
        archive = read_regular(directory / (name + '-original.zip'), 128 * 1024)
        need(len(archive) == p['archive_bytes'] and digest(archive) == p['archive_sha256'],
             'state_archive_pin_changed')
        members = unpack(archive, p['members'])
        lines = members['archive.sha256'].decode('ascii').splitlines()
        expected = {digest(b) + '  ' + n for n, b in members.items() if n != 'archive.sha256'}
        need(len(lines) == len(expected) and set(lines) == expected, 'state_inner_manifest')
        doc = strict_json(members[p['report_member']])
        need(doc['report_sha256'] == digest(canonical({k: v for k, v in doc.items()
             if k != 'report_sha256'})), 'state_source_report_commitment')
        reports[name] = doc
        provenance[name] = {'repository': SOURCE, 'run_id': p['run_id'],
            'producer_commit': p['commit'], 'producer_tree': p['tree'],
            'artifact_id': p['artifact_id'], 'archive_sha256': p['archive_sha256'],
            'metadata_sha256': p['metadata_sha256'], 'source_report_sha256': doc['report_sha256'],
            'retrieved_at': meta['retrieved_at'],
            'trust_basis': 'REVIEWED_RETAINED_GITHUB_CAPTURE_NOT_FRESH_CHAIN_OBSERVATION'}
    return reports, provenance


def operator_rows(providers):
    need(type(providers) is list and len(providers) == 2, 'two_operators_required')
    fields(providers[0], {'provider_id': 'drpc', 'operator': 'dRPC'}, 'operator')
    fields(providers[1], {'provider_id': 'blast', 'operator': 'BlastAPI'}, 'operator')
    same(providers[0]['rows'], providers[1]['rows'], 'operator_disagreement')
    need(len(providers[0]['rows']) == 3, 'operator_scope')
    return providers[0]['rows']


def validate_join(cashflow, ledger, identities, sources):
    """Check cross-source identity, chronology, arithmetic and observation scope."""
    r2, fee, health = (sources[k] for k in SOURCE_KEYS)
    fields(r2, {'status': 'RMC016_RANK2_WETH_DUAL_OPERATOR_PREBLOCK_ORACLE_PASS',
        'selected_rank': 2, 'historical_weth_weth_winner_count': 9,
        'source_selection_retrospective': True, 'nexus_net_profit_proven': False,
        'nexus_gas_or_flash_provider_authorized': False, 'real_market_census_closed': False}, 'rank2')
    same(r2['source_hashes'], {a + '_zip_sha256': PINS[b]['sha256'] for a, b in
         [('event', 'events'), ('receipt', 'receipts'), ('legs', 'legs')]}, 'rank2_sources')
    fields(fee, {'status': 'RMC016_AAVE_PREBLOCK_ACTUAL_FLASH_PREMIUM_3_WETH_WINNERS_PASS',
        'operator_count': 2, 'historical_competitor_winners': 3,
        'same_block_flash_principal_liquidity_verified': False,
        'native_gas_sponsor_authorized': False, 'nexus_flash_principal_provider_authorized': False,
        'actual_historical_nexus_calldata_replayed': False, 'nexus_capture_calibrated': False,
        'nexus_realized_net_pnl_proven': False, 'real_market_census_closed': False}, 'fee')
    from cashflow_intake import PRICE_SHA256
    fields(fee['source_sha256'], {'rank1_rank3_oracle': PRICE_SHA256,
        'rank2_oracle': 'ece575718b4834293ffb0a6e42f4329f41b39fef4b1befcad96eac507df1a92f',
        '9_winner_audit': '79cd8ee2056df668d31169444271bafb8f8ff3552e993000cf4e7df63ad28cb3'}, 'fee_sources')
    fields(health, {'status': 'RMC016_TOP3_HISTORICAL_WETH_PREBLOCK_HEALTH_TRUTH_ONLY',
        'observed_historical_top_three_count': 3, 'independent_two_provider_parity': True,
        'source_selection_uses_future_winner_knowledge': True,
        'evidence_of_ex_ante_discovery_or_strategy_capture': False,
        'replayed_real_liquidation_in_preblock': False,
        'flash_principal_and_gas_externally_financed': False,
        'complete_costs_or_realized_nexus_profit_certified': False,
        'real_market_census_closed': False}, 'health')
    fields(health, {'source_event_archive_sha256': PINS['events']['sha256'],
        'source_receipts_archive_sha256': PINS['receipts']['sha256'],
        'source_integer_legs_archive_sha256': PINS['legs']['sha256']}, 'health_sources')
    frows, hrows = operator_rows(fee['two_rpc_operators']), operator_rows(health['provider_records'])
    need(len(fee['network_observed_history']) == len(health['three_source_rows']) == 3, 'source_row_count')
    receipts = {r['transaction_hash']: r for r in ledger['records']}
    joined = []
    for index, row in enumerate(cashflow['records'][:3]):
        rank, tx = index + 1, row['transaction_hash']
        h, public, f, calculated = (hrows[index], health['three_source_rows'][index],
            frows[index], fee['network_observed_history'][index])
        base = receipts[tx]
        legs = [leg for leg in base['liquidation_legs']
                if leg['collateral_asset'] == leg['debt_asset'] == WETH]
        need(len(legs) == 1, 'weth_leg_ambiguity')
        leg = legs[0]
        raw_events = [e for e in identities['events'] if e['transaction_hash'] == tx
                      and e['log_index'] == leg['log_index']]
        need(len(raw_events) == 1, 'identity_event_ambiguity')
        fields(h, {'rank': rank, 'winner_transaction_hash': tx,
            'winner_block_number': row['block_number'], 'winner_block_hash': row['block_hash'],
            'receipt_evidence_sha256': base['receipt']['receipt_evidence_sha256'],
            'source_borrower_identity_sha256': leg['borrower_identity_sha256'],
            'borrower': raw_events[0]['borrower_address']}, 'health_receipt_identity')
        need(ADDRESS.fullmatch(h['borrower']) and digest(('0x' + h['borrower'][2:].rjust(64, '0')).encode())
             == leg['borrower_identity_sha256'], 'borrower_fingerprint')
        earlier = h['predecessor_block']
        need(type(earlier['number']) is int and earlier['number'] == row['block_number'] - 1,
             'predecessor_number')
        for key in ('hash', 'parent_hash', 'state_root'):
            need(type(earlier[key]) is str and HASH.fullmatch(earlier[key]), 'predecessor_hash')
        if rank == 2:
            price = r2['row']['historical_preblock_oracle']
            end = r2['row']['historical_winner_block_end_oracle']
            fields(r2['row'], {'transaction_hash': tx, 'block_number': row['block_number'],
                'block_hash': row['block_hash'], 'historical_rank_after_competitor_gas': 2,
                'historical_weth_debt_wei': row['weth_debt_wei'],
                'historical_weth_collateral_wei': row['weth_collateral_wei'],
                'historical_winner_full_tx_gas_wei': row['full_transaction_gas_wei'],
                'historical_after_winner_gas_wei': row['gross_delta_minus_full_transaction_gas_wei'],
                'two_independent_operator_price_consensus': True,
                'previous_block_price_is_not_exact_pretransaction_price': True}, 'rank2_join')
        else:
            price, end = (row['preblock_price_reference'][k] for k in ('preblock', 'block_end'))
        fields(price, {'block': earlier['number'], 'hash': earlier['hash']}, 'price_anchor')
        fields(end, {'block': row['block_number'], 'hash': row['block_hash']}, 'price_end')
        need(uint(price['oracle_usd_base_1e8']) > 0 and uint(end['oracle_usd_base_1e8']) > 0, 'price_zero')
        fields(f, {'block': earlier['number'], 'hash': earlier['hash']}, 'fee_anchor')
        bps = f['premium_bps']
        amount = percent_mul(uint(row['weth_debt_wei']), bps)
        remaining = int(row['gross_delta_minus_full_transaction_gas_wei']) - amount
        fields(calculated, {'rank': rank, 'transaction_hash': tx, 'block_number': row['block_number'],
            'block_hash': row['block_hash'], 'aave_pool': POOL,
            'historical_previous_block_number': earlier['number'], 'previous_block_hash': earlier['hash'],
            'original_debt_weth_wei': row['weth_debt_wei'],
            'original_after_competitor_gas_wei': row['gross_delta_minus_full_transaction_gas_wei'],
            'previous_block_weth_usd_base_1e8': price['oracle_usd_base_1e8'],
            'aave_flashloan_simple_premium_bps_preblock': bps,
            'historical_pool_premium_wei_percentmul_half_up': str(amount),
            'historical_after_winner_gas_and_pool_premium_wei': str(remaining),
            'historical_remaining_usd_wad_preblock_reference': signed_reference(remaining, price['oracle_usd_base_1e8']),
            'historical_pool_fee_is_availability_quote': False,
            'historical_pool_liquidity_cap_verified': False, 'nexus_capture_proven': False,
            'nexus_external_gas_funding_proven': False, 'nexus_net_profit_proven': False}, 'fee_calculation')
        account = h['account_data']
        for key in ('total_collateral_base', 'total_debt_base', 'available_borrows_base', 'health_factor_wad'):
            uint(account[key])
        need(uint(account['total_debt_base']) > 0, 'no_observed_debt')
        for key in ('current_liquidation_threshold_bps', 'ltv_bps'):
            need(type(account[key]) is int and 0 <= account[key] <= 10000, 'account_bps')
        below = uint(account['health_factor_wad']) < WAD
        fields(h, {'health_factor_below_one_at_predecessor': below}, 'health_threshold')
        fields(public, {'rank': rank, 'historical_competitor_tx': tx,
            'previous_block_number': earlier['number'], 'previous_block_hash': earlier['hash'],
            'previous_block_state_root': earlier['state_root'],
            'source_borrower_identity_sha256': leg['borrower_identity_sha256'],
            'total_debt_base': account['total_debt_base'], 'health_factor_wad': account['health_factor_wad'],
            'below_one_at_previous_block': below, 'can_only_attempt_preblock_fork_if_below_one': below}, 'health_public')
        joined.append({'transaction_hash': tx, 'predecessor_block': earlier,
            'borrower_address': h['borrower'], 'account_data': account,
            'below_one_at_predecessor': below, 'price_reference': price,
            'observed_pool_premium_bps': bps, 'conditional_flash_fee_wei': str(amount),
            'conditional_remaining_wei': str(remaining),
            'conditional_remaining_usd_wad': signed_reference(remaining, price['oracle_usd_base_1e8'])})
    count = sum(r['below_one_at_predecessor'] for r in joined)
    fields(health, {'observed_predecessor_below_one_count': count,
                   'observed_predecessor_not_below_one_count': 3 - count}, 'health_counts')
    return joined


def build_state_report(directory=EVIDENCE, root=ROOT):
    cashflow, ledger, identities = (build_cashflow(directory, root),
        build_ledger(directory, root), build_liquidator_report(directory, root))
    sources, provenance = load_state_sources(directory)
    joined = validate_join(cashflow, ledger, identities, sources)
    observed = {r['transaction_hash']: r for r in joined}
    rows = []
    for cash in cashflow['records']:
        witness = observed.get(cash['transaction_hash'])
        row = copy.deepcopy(cash)
        row.pop('record_commitment_sha256')
        row['predecessor_state'] = witness
        # Preserve the H16 row and its original price sample intact; enrichment
        # is a separate witness, not a rewrite of a source report's two prices.
        row['predecessor_threshold_status'] = ('UNKNOWN' if witness is None else
            'BELOW_ONE' if witness['below_one_at_predecessor'] else 'NOT_BELOW_ONE')
        row['source_selected_with_hindsight'] = True
        row['prospective_signal_proven'] = False
        row['executable_candidate'] = False
        row['observed_paid_flash_fee_wei'] = None
        row['complete_receipt_parity_for_corpus'] = False
        row['two_operator_receipt_commitment_matched_for_this_transaction'] = witness is not None
        row['decision_blockers'] = ['HINDSIGHT_SELECTED_WINNER', 'EXACT_TRANSACTION_PRESTATE_MISSING',
            'FULL_COSTS_MISSING', 'EXTERNAL_GAS_AND_PRINCIPAL_UNPROVEN']
        row['decision_blockers'].append('PREDECESSOR_STATE_UNOBSERVED' if witness is None else
            'PREDECESSOR_THRESHOLD_NOT_MET' if not witness['below_one_at_predecessor'] else
            'THRESHOLD_ALONE_DOES_NOT_PROVE_EXECUTABILITY')
        row['record_commitment_sha256'] = digest(canonical(row))
        rows.append(row)
    report = {'schema': SCHEMA, 'status': 'RETAINED_HISTORICAL_PREDECESSOR_DIAGNOSTIC',
        'cashflow_report_commitment': cashflow['report_commitment_sha256'],
        'source_provenance': provenance, 'records': rows,
        'summary': {'cashflow_transactions': 9, 'historical_corpus_transactions': 127,
            'predecessor_price_count': 3, 'predecessor_health_count': 3,
            'predecessor_pool_premium_count': 3, 'selected_receipt_parity_count': 3,
            'predecessor_below_one_count': sum(x['below_one_at_predecessor'] for x in joined),
            'predecessor_not_below_one_count': sum(not x['below_one_at_predecessor'] for x in joined),
            'predecessor_health_unknown_count': 6, 'complete_cost_count': 0,
            'prospectively_discovered_count': 0, 'executable_candidate_count': 0},
        'observed_pool_parameter_is_paid_fee': False, 'predecessor_is_transaction_prestate': False,
        'oracle_cause_observed': False, 'oracle_update_delay_blocks': None,
        'new_chain_acquisition_performed': False, 'complete_corpus_receipt_parity': False,
        'nqc_realized_profit_wei': None, 'authorities': dict(AUTHORITIES)}
    report['report_commitment_sha256'] = digest(canonical(report))
    return report


def verify_state_report(report, directory=EVIDENCE, root=ROOT):
    expected = build_state_report(directory, root)
    same(report, expected, 'state_report_differs_from_sources')
    return expected


def store_state_report(store, directory=EVIDENCE, root=ROOT):
    base = store_cashflow(store, directory, root)
    objects = read_batch(store, base['cashflow_batch'])
    objects.update({n: read_regular(Path(directory) / n) for n in STATE_NAMES})
    with tempfile.TemporaryDirectory(prefix='omega-state-') as tmp:
        for n, b in objects.items(): (Path(tmp) / n).write_bytes(b)
        report = build_state_report(Path(tmp), root)
    objects[REPORT_NAME] = canonical(report)
    return {'cashflow_batch': base['cashflow_batch'], 'state_batch': admit(store, objects), 'report': report}


def query_state_report(store, batch, root=ROOT):
    objects = read_batch(store, batch)
    expected = SOURCE_NAMES | CAPTURE_NAMES | PRICE_NAMES | STATE_NAMES | {
        LEDGER_NAME, 'liquidator-report.json', 'cashflow-report.json', REPORT_NAME}
    need(set(objects) == expected, 'state_batch_inventory')
    with tempfile.TemporaryDirectory(prefix='omega-state-query-') as tmp:
        directory = Path(tmp)
        for n, b in objects.items(): (directory / n).write_bytes(b)
        from historical_intake import verify_ledger
        from cashflow_intake import verify_cashflow
        verify_ledger(strict_json(objects[LEDGER_NAME]), directory, root)
        same(strict_json(objects['liquidator-report.json']), build_liquidator_report(directory, root),
             'state_identity_differs_from_sources')
        verify_cashflow(strict_json(objects['cashflow-report.json']), directory, root)
        return verify_state_report(strict_json(objects[REPORT_NAME]), directory, root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=EVIDENCE)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    safe_path(args.out)
    need(not args.out.resolve().is_relative_to(ROOT), 'output_inside_source')
    report = build_state_report(args.evidence)
    with args.out.open('xb') as stream: stream.write(canonical(report))
    print(report['status'], report['summary'])


if __name__ == '__main__': main()
