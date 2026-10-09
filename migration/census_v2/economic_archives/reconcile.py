#!/usr/bin/env python3
"""Reconcile recovered economic archives and full decoded receipts offline."""
from collections import Counter
import argparse
import gzip
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
ROOT = V2.parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT / 'ci/nqc-census'), str(V2), str(V2 / 'additional_evidence')]
from replay_historical_regressions import blob, metadata_identity
from verify_winner_recovery import PINS, archive, canonical, need, parse, sha, transport
from rmc016_weth_cashflow_audit import audit as cashflow_audit
from rmc016_historical_aave_flash_premium import verified_candidates
from rmc016_aave_event_legs import authentic_source, bind_logs, POOL, TOPIC
from rmc016_resume_verified_receipts import authenticated_drpc_checkpoint
from rmc016_tenderly_receipt_crosscheck import reconcile as receipt_reconcile
from reconcile_additional import origin_check, join_v2_ledger
from reconcile_winner_economics import semantic_receipt, flash_event, token_flows, abi_binding

BASE = '387ac1decb49ca1d3118c028d889cabd5f115ce0'


def pinned_source(path):
    raw = (ROOT / path).read_bytes()
    expected = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', BASE + ':' + path],
                                       text=True).strip()
    need(blob(raw) == expected, 'existing source drift: ' + path)
    return raw


def authenticated_inputs():
    original = parse(pinned_source('migration/census_v2/evidence/economics/additional-acquisition.json'))
    need(original['source_repository'] == 'josuechavando350-png/nexus-engine'
         and len(original['artifacts']) == 13, 'original economic inventory drift')
    contents, sources = {}, []
    for row in original['artifacts']:
        pin = row['artifact_metadata']
        aid = pin['id']
        path = HERE / 'inputs' / (str(aid) + '.zip')
        raw = path.read_bytes()
        need(sha(raw) == pin['digest'][7:] and len(raw) == pin['size_in_bytes'],
             'original economic archive hash/size mismatch')
        meta = parse((HERE / 'inputs' / (str(aid) + '.metadata.json')).read_bytes())
        identity = metadata_identity(*(canonical(meta[k]) for k in ('run', 'artifact', 'commit')),
                                     {'run_id': row['run_id'], 'artifact_id': aid,
                                      'head_sha': pin['workflow_run']['head_sha'],
                                      'artifact_digest': pin['digest']})
        need(meta['artifact']['size_in_bytes'] == len(raw) and meta['artifact']['name'] == pin['name'],
             'fresh artifact size/name mismatch')
        contents[aid] = archive(path)
        sources.append({**identity, 'bytes': len(raw), 'original_event': meta['run']['event'],
                        'metadata_sha256': sha(canonical(meta)),
                        'members': {n: {'sha256': sha(b), 'bytes': len(b)}
                                    for n, b in sorted(contents[aid].items())}})
    # The already-recovered event, receipt and price archives retain their own
    # historical provenance. In particular, the dRPC parent run remains failed.
    for pin in (PINS[0], PINS[1], PINS[4]):
        path = HERE / 'inputs' / (str(pin[1]) + '.zip')
        meta = parse(pinned_source('migration/census_v2/evidence/winner-api/' + str(pin[0]) + '.json'))
        sources.append(transport(pin, meta, path.read_bytes()))
        contents[pin[1]] = archive(path)
    return contents, sources


def committed_json(raw):
    doc = parse(raw)
    if 'report_sha256' in doc:
        unsigned = {k: v for k, v in doc.items() if k != 'report_sha256'}
        need(doc['report_sha256'] == sha(canonical(unsigned)), 'inner report commitment mismatch')
    return doc


def premium_recalculation(candidates, report):
    operators = report['two_rpc_operators']
    need([r['provider_id'] for r in operators] == ['drpc', 'blast']
         and [r['operator'] for r in operators] == ['dRPC', 'BlastAPI']
         and operators[0]['rows'] == operators[1]['rows'], 'retained premium operator observations differ')
    need(len(candidates) == len(operators[0]['rows']) == len(report['network_observed_history']) == 3,
         'premium population drift')
    for candidate, observation, recorded in zip(candidates, operators[0]['rows'], report['network_observed_history']):
        bps = observation['premium_bps']
        need(type(bps) is int and 0 <= bps <= 10000
             and observation['block'] == candidate['historical_previous_block_number']
             and observation['hash'] == candidate['previous_block_hash'], 'premium anchor/value mismatch')
        fee = (int(candidate['original_debt_weth_wei']) * bps + 5000) // 10000
        after = int(candidate['original_after_competitor_gas_wei']) - fee
        dollars = (1 if after >= 0 else -1) * (abs(after) * int(candidate['previous_block_weth_usd_base_1e8']) // 10**8)
        need(all(recorded.get(k) == v for k, v in candidate.items())
             and recorded['historical_pool_premium_wei_percentmul_half_up'] == str(fee)
             and recorded['historical_after_winner_gas_and_pool_premium_wei'] == str(after)
             and recorded['historical_remaining_usd_wad_preblock_reference'] == str(dollars)
             and recorded['aave_flashloan_simple_premium_bps_preblock'] == bps,
             'historical premium arithmetic or source mismatch')
        need(recorded['historical_pool_liquidity_cap_verified'] is False
             and recorded['historical_pool_fee_is_availability_quote'] is False
             and recorded['nexus_net_profit_proven'] is False,
             'historical premium cannot prove available capital or profit')
    need(report['real_market_census_closed'] is False
         and report['same_block_flash_principal_liquidity_verified'] is False,
         'historical premium scope promotion')
    return {'candidates': 3, 'arithmetic_mismatches': 0,
            'retained_operator_records': 2, 'new_rpc_observations': 0,
            'underlying_node_independence_proven': False,
            'availability_or_complete_cost_quote': False}


def complete_receipt_logs(contents):
    pinned_source('migration/census_v2/additional_evidence/origins.json')
    origin_check()
    raw = gzip.decompress((V2 / 'additional_evidence/recovered-rmc016/tenderly-receipts-20261009.jsonl.gz').read_bytes())
    exchanges = [parse(line) for line in raw.splitlines()]
    events = HERE / 'inputs/11524139188.zip'
    checkpoint = HERE / 'inputs/11524199698.zip'
    parity = receipt_reconcile(events, checkpoint, exchanges)
    norm, _, _ = authenticated_drpc_checkpoint(checkpoint, events)
    ledger = pinned_source('migration/census_v2/evidence/economics/replay/winner-economic-ledger.jsonl')
    joined = join_v2_ledger(exchanges, ledger)
    prior = {r['transaction_hash']: r for r in (parse(line) for line in ledger.splitlines())}
    semantics, flashes, liquidation_logs, counts = {}, [], [], Counter()
    matched_witnesses, matched_transactions, new_transactions = 0, set(), []
    for exchange in exchanges:
        if exchange['method'] != 'eth_getTransactionReceipt':
            continue
        tx = exchange['params'][0]
        sem = semantic_receipt(exchange['result'], norm[tx])
        semantics[tx] = sem
        commitment = sha(canonical(sem))
        witnesses = prior[tx]['raw_receipt_witnesses']
        if witnesses:
            for witness in witnesses:
                need(witness['semantic_receipt_sha256'] == commitment, 'full receipt/log historical mismatch')
                matched_witnesses += 1
            matched_transactions.add(tx)
        else:
            new_transactions.append(tx)
        for log in sem['logs']:
            flash = flash_event(log)
            if flash is not None:
                flashes.append(flash)
            if log['address'] == POOL and log['topics'] and log['topics'][0] == TOPIC:
                liquidation_logs.append(log)
        _, transfers, ambiguous = token_flows(sem['logs'])
        counts['receipt_logs'] += len(sem['logs'])
        counts['erc20_shaped_transfers'] += transfers
        counts['ambiguous_transfers'] += ambiguous
    source, _ = authentic_source(events)
    legs = bind_logs(source, b''.join(canonical(log) for log in liquidation_logs))
    need(b''.join(canonical(r) for r in legs) == contents[11525823668]['decoded-liquidation-legs.jsonl'],
         'full 139 decoded liquidation legs differ from original archive')
    original_flashes = [parse(line) for line in pinned_source(
        'migration/census_v2/evidence/economics/replay/observed-flash-events.jsonl').splitlines()]
    flash_lookup = {(x['transaction_hash'], x['log_index']): x for x in flashes}
    for old in original_flashes:
        current = flash_lookup.get((old['transaction_hash'], old['log_index']))
        need(current is not None and all(old.get(k) == v for k, v in current.items()),
             'original flash event changed')
    old_flash_ids = {(x['transaction_hash'], x['log_index']) for x in original_flashes}
    new_flashes = [r for r in flashes if (r['transaction_hash'], r['log_index']) not in old_flash_ids]
    return {'receipt_parity': parity, 'ledger_join': joined,
            'complete_decoded_receipts': len(semantics),
            'previous_full_receipt_transactions_matched': len(matched_transactions),
            'previous_operator_witnesses_matched': matched_witnesses,
            'new_full_receipt_transactions': new_transactions,
            'all_139_liquidation_legs_byte_identical': True,
            'recognized_flash_events': len(flashes),
            'recognized_flash_transactions': len({r['transaction_hash'] for r in flashes}),
            'original_flash_events_preserved': len(original_flashes),
            'additional_flash_events': new_flashes,
            'flash_protocol_counts': dict(Counter(x['protocol'] for x in flashes)),
            'transfer_and_log_counts': dict(counts),
            'per_request_receive_timestamps_preserved': False,
            'original_http_bytes_preserved': False,
            'balances_or_complete_financing_proven': False}, flashes


def reconcile():
    contents, sources = authenticated_inputs()
    abi_binding()
    docs = {}
    for aid, files in contents.items():
        for name, raw in files.items():
            if name.endswith('.json'):
                docs[(aid, name)] = committed_json(raw)
    replay = cashflow_audit(*(HERE / 'inputs' / (str(aid) + '.zip')
                             for aid in (11524139188, 11524199698, 11525823668, 11527902751)))
    for aid in (11529867393, 11530691544):
        need(canonical(replay) == contents[aid]['historical-weth-cashflow.json'],
             'nine-winner cashflow replay is not byte-identical')
    need(contents[11530103644]['rank2-preblock-weth-price.json'] ==
         contents[11530582289]['rank2-preblock-weth-price.json'], 'push/PR rank2 payload differs')
    candidates = verified_candidates(replay, docs[(11530582289, 'rank2-preblock-weth-price.json')],
                                     docs[(11527902751, 'top-two-weth-prices.json')])
    premium = premium_recalculation(candidates, docs[(11530638026, 'observed-aave-flash-premium.json')])
    receipts, flashes = complete_receipt_logs(contents)
    policy = pinned_source('migration/census_v2/capital-policy.json')
    need(parse(policy)['currency'] == 'MXN' and parse(policy)['operator_gas_budget_centavos'] == 200000,
         'active peso policy drift')
    report = {'schema': 'nqc-recovered-economic-archives-v1',
              'status': 'HISTORICAL_ECONOMIC_INPUTS_RECONCILED_NOT_EXECUTION_ADMISSION',
              'producer_repository': 'josuechavando350-png/nexus-quant-capital',
              'producer_repository_id': 1411047452, 'source_base_commit': BASE,
              'consumer_sha256': sha(Path(__file__).read_bytes()), 'sources': sources,
              'recovered_previously_missing_archives': 13,
              'identical_push_pr_payloads_counted_as_new_observations': False,
              'cashflow_replay_byte_identical': True, 'weth_competitor_cases': 9,
              'conditional_positive_after_hypothetical_5bps': 8,
              'conditional_margin_is_nqc_profit': False,
              'premium_recalculation': premium, 'full_receipt_log_reconciliation': receipts,
              'historical_zero_own_gas_policy_applied_to_nqc': False,
              'active_capital_policy_sha256': sha(policy), 'active_gas_budget_currency': 'MXN',
              'active_gas_budget_minor_units': 200000, 'gas_spent_by_replay_wei': '0',
              'economic_classifications_changed': False, 'positive_nqc_value_admitted': False,
              'original_decision_time_information_proven': False,
              'original_30_day_log_or_oracle_coverage_completed': False,
              'native_internal_costs_and_offchain_liabilities_complete': False,
              'new_rpc_requests': 0, 'independent_certification_issued': False,
              'real_market_census_closed': False}
    return report, flashes


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    out = parser.parse_args().out
    need(not out.exists(), 'append-only output directory required')
    report, flashes = reconcile()
    out.mkdir(parents=True)
    (out / 'report.json').write_bytes(canonical(report))
    (out / 'tenderly-flash-observations.jsonl').write_bytes(b''.join(canonical(r) for r in flashes))
    print(report['status'])
    print(json.dumps(report['full_receipt_log_reconciliation']['transfer_and_log_counts'], sort_keys=True))
