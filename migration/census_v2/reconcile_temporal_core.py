#!/usr/bin/env python3
"""Read actual D15B/D16 ledgers; retain uncertainty and deny positive capture."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

from verify_server_recovery import parse, require, sha

CORE_SHA = 'cc51fc5c9a3ea76daa59d42cc5eef6aed3909955d1bf5a68795ac3bf5b210ede'
TEMPORAL_SHA = '1acc37d37d82573dd3c27b02fe5de5bf40abd7081f42d22178cc27873f56efb4'
CAPACITY_SHA = '9dc03b2d2c480d689e5ecf1e4585d2af55a4271db6a3e5ef0851f821085fac63'
PRIOR_SHA = '170333170da1d68bfe49b3058847d123b96e09e6e74f4c5a9ad69ad74fefdbeb'
WETH = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'


def canon(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def read_core(path):
    require(sha(path.read_bytes()) == CORE_SHA, 'core transport digest')
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        require(len(names) == len(set(names)) == 71, 'core inventory')
        for n in names:
            require(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts, 'unsafe member')
        files = {n: z.read(n) for n in names}
    manifest = parse(files['recovery-manifest.json'])
    require({r['member'] for r in manifest['files']} == set(names) - {'recovery-manifest.json'}, 'manifest inventory')
    require(len(manifest['files']) == 70, 'manifest duplicates')
    for row in manifest['files']:
        raw = files[row['member']]
        require(len(raw) == row['bytes'] and sha(raw) == row['sha256'], 'manifest bytes')
    return files


def rows(files, name):
    return [parse(x) for x in files[name].splitlines()]


def keyed(items, field, count):
    result = {r[field]: r for r in items}
    require(len(result) == len(items) == count, 'duplicate/missing ' + field)
    return result


def bind(files, name, expected):
    require(sha(files[name]) == expected, 'historical hash binding: ' + name)


def commitment(doc, domain):
    stripped = dict(doc)
    value = stripped.pop('authority_commitment')
    require(value == '0x' + sha(domain.encode() + b'\0' + canon(stripped)), 'authority commitment')


def temporal(files):
    bind(files, 'rmc015-temporal-authority.json', TEMPORAL_SHA)
    doc = parse(files['rmc015-temporal-authority.json'])
    commitment(doc, 'NQC-RMC015-TEMPORAL-CONSERVATIVE-AUTHORITY-V1')
    links = {
        'trigger_authority_sha256': 'rmc015a-production-summary.json',
        'start_risk_authority_sha256': 'start-risk/start-risk-authority.json',
        'candidate_state_replay_sha256': 'candidate-state-transition-replay-summary.json',
        'candidate_envelope_sha256': 'interest-only-crossing-candidate-envelope-summary.json',
        'winner_replay_sha256': 'winner-replay/winner-replay-summary.json',
        'pool_trigger_sha256': 'pool-trigger-dual-provider-summary.json',
        'full_block_oracle_summary_sha256': 'full-block-oracle/drpc/provider-summary.json',
    }
    for key, name in links.items():
        bind(files, name, doc['inputs'][key])
    bind(files, 'rmc015-temporal-episodes.jsonl', doc['episode_ledger_sha256'])
    bind(files, 'rmc015-censored-candidates.jsonl', doc['censored_ledger_sha256'])
    episodes = rows(files, 'rmc015-temporal-episodes.jsonl')
    by_id = keyed(episodes, 'episode_id', 571)
    censored = keyed(rows(files, 'rmc015-censored-candidates.jsonl'), 'account', 29442)
    start = [r for r in episodes if r['classification'] == 'LEFT_CENSORED_LIQUIDATABLE_AT_WINDOW_START']
    observed = [r for r in episodes if r['classification'] == 'DEFINITE_LIQUIDATION_EVENT_OPPORTUNITY']
    require(len(start) == 432 and len(observed) == 139, 'episode classification counts')
    require(len({r['account'] for r in start}) == 432, 'duplicate starting account')
    definite = {r['account'] for r in episodes}
    require(len(definite) == 556 and not definite.intersection(censored), 'partition overlap/cardinality')
    require(len(definite | censored.keys()) == doc['candidate_account_count'] == 29998, 'partition conservation')
    pool = parse(files['pool-trigger-dual-provider-summary.json'])
    bind(files, 'liquidation-calls.jsonl', pool['liquidation_sha256'])
    require(files['liquidation-calls.jsonl'] == files['liquidations-tenderly.jsonl'], 'paired decoded events')
    events = rows(files, 'liquidation-calls.jsonl')
    for e in events:
        episode_id = f"liq:{e['block_number']}:{e['transaction_index']}:{e['log_index']}"
        row = by_id[episode_id]
        for key in ('transaction_hash', 'transaction_index', 'log_index', 'collateral_asset', 'debt_asset',
                    'debt_to_cover', 'liquidated_collateral_amount', 'liquidator', 'receive_atoken'):
            require(row[key] == e[key] and type(row[key]) is type(e[key]), 'episode/event field: ' + key)
        require(row['account'] == e['user'] and row['first_definite_block'] == e['block_number']
                and row['first_definite_block_hash'] == e['block_hash'], 'episode/event identity')
        require(doc['window']['start_block'] <= e['block_number'] <= doc['window']['end_block'], 'event outside window')
    for r in start:
        require(r['promotion_to_capacity'] is False and r['arrival_in_window'] is False, 'left censoring')
        require(r['first_definite_block'] == doc['window']['start_block'] and
                r['first_definite_block_hash'] == doc['window']['start_hash'], 'starting anchor')
    for r in censored.values():
        require(r['promotion_to_capacity'] is False and r['capacity_contribution'] == '0', 'censoring admission')
    account_episodes = defaultdict(list)
    for r in episodes:
        account_episodes[r['account']].append(r['episode_id'])
    classifications = []
    for account in sorted(definite | censored.keys()):
        reason = ('NO_DEFINITE_CROSSING_WITNESS' if account in censored
                  else 'NQC_FINANCING_FULL_COST_EXECUTION_AND_CAPTURE_UNPROVEN')
        classifications.append({'account': account, 'scope': 'D15B_HISTORICAL_WINDOW',
            'classification': 'INSUFFICIENT_EVIDENCE', 'reason': reason,
            'historical_episode_ids': sorted(account_episodes[account]),
            'decision_time_observation_proven': False, 'nqc_executable_value_usd_wad': '0'})
    return doc, events, classifications


def economics(files, events, prior_bytes):
    bind(files, 'rmc016-capacity-authority.json', CAPACITY_SHA)
    doc = parse(files['rmc016-capacity-authority.json'])
    commitment(doc, 'NQC-RMC016-CONSERVATIVE-REALIZABLE-CAPACITY-V1')
    for key, name in [('rmc015_temporal_authority_sha256', 'rmc015-temporal-authority.json'),
                      ('liquidation_price_authority_sha256', 'rmc016-liquidation-block-price-authority-summary.json'),
                      ('winner_replay_sha256', 'winner-replay/winner-replay-summary.json')]:
        bind(files, name, doc['inputs'][key])
    for key, name in [('event_economics_sha256', 'rmc016-observed-event-economics.jsonl'),
                      ('transaction_economics_sha256', 'rmc016-observed-transaction-economics.jsonl'),
                      ('daily_baseline_sha256', 'rmc016-observed-daily-market-baseline.jsonl')]:
        bind(files, name, doc[key])
    price_summary = parse(files['rmc016-liquidation-block-price-authority-summary.json'])
    bind(files, 'rmc016-liquidation-block-price-authority.jsonl', price_summary['ledger_sha256'])
    winner_summary = parse(files['winner-replay/winner-replay-summary.json'])
    bind(files, 'winner-replay/winner-replay-ledger.jsonl', winner_summary['ledger_sha256'])
    prices = keyed(rows(files, 'rmc016-liquidation-block-price-authority.jsonl'), 'block_number', 123)
    require(files['start-market-state/nodies.jsonl'] == files['start-market-state/tenderly.jsonl'], 'paired reserve bytes')
    market = keyed(rows(files, 'start-market-state/nodies.jsonl'), 'asset', 67)
    require({r['reserve_id'] for r in market.values()} == set(range(67)), 'reserve IDs')
    economic_events = keyed(rows(files, 'rmc016-observed-event-economics.jsonl'), 'episode_id', 139)
    winners = keyed(rows(files, 'winner-replay/winner-replay-ledger.jsonl'), 'transaction_hash', 127)
    txrows = keyed(rows(files, 'rmc016-observed-transaction-economics.jsonl'), 'transaction_hash', 127)
    require(sha(prior_bytes) == PRIOR_SHA, 'prior economic ledger pin')
    previous = keyed([parse(x) for x in prior_bytes.splitlines()], 'transaction_hash', 127)
    require(winners.keys() == txrows.keys() == previous.keys(), 'transaction universe')
    totals = defaultdict(lambda: [0, 0, 0])
    clipped_event_count = 0
    for e in events:
        key = f"liq:{e['block_number']}:{e['transaction_index']}:{e['log_index']}"
        row = economic_events[key]
        p = prices[e['block_number']]
        require(p['block_hash'] == e['block_hash'] and len(p['prices']) == 67, 'price anchor/vector')
        require(row['transaction_hash'] == e['transaction_hash'] and row['account'] == e['user']
                and row['timestamp'] == p['timestamp'], 'economic event identity/time')
        values = []
        for asset_field, amount_field, round_up in [('debt_asset', 'debt_to_cover', True),
                                                   ('collateral_asset', 'liquidated_collateral_amount', False)]:
            m = market[e[asset_field]]
            unit = 10 ** ((int(m['configuration']) >> 48) & 255)
            price = int(p['prices'][m['reserve_id']])
            q, rem = divmod(int(e[amount_field]) * price, unit)
            values.append((q + int(round_up and rem != 0)) * 10**10)
        debt, collateral = values
        require(int(row['debt_principal_usd_wad']) == debt and
                int(row['gross_collateral_oracle_value_usd_wad']) == collateral, 'event valuation')
        require(int(row['gross_oracle_edge_before_protocol_fee_route_gas_mev_usd_wad']) == max(0, collateral-debt), 'event edge')
        require(row['capacity_admission'] is False, 'economic event admitted')
        clipped_event_count += int(collateral < debt)
        t = totals[e['transaction_hash']]
        t[0] += debt; t[1] += collateral; t[2] += 1
    sum_debt = sum_edge = sum_gas = gas_wei_total = 0
    signs = Counter()
    days = defaultdict(lambda: [0, 0, 0, 0, 0])
    for tx, row in txrows.items():
        w, old = winners[tx], previous[tx]
        require(row['block_number'] == w['block_number'] == old['block_number'] and
                row['transaction_index'] == w['transaction_index'] == old['transaction_index'], 'winner anchor')
        gas_wei = int(w['gas_used']) * int(w['effective_gas_price_wei'])
        require(gas_wei == int(old['historical_gas']['whole_transaction_wei']) and
                row['gas_used'] == w['gas_used'] and row['effective_gas_price_wei'] == w['effective_gas_price_wei'], 'gas parity')
        price = int(prices[w['block_number']]['prices'][market[WETH]['reserve_id']])
        require(row['timestamp'] == prices[w['block_number']]['timestamp']
                and int(row['eth_price_base_units']) == price, 'transaction time/price')
        gas_usd = gas_wei * price // 10**8
        debt, collateral, count = totals[tx]
        edge = max(0, collateral-debt)
        for k, expected in [('event_count', count), ('debt_principal_usd_wad', debt),
                            ('gross_collateral_oracle_value_usd_wad', collateral),
                            ('gross_oracle_edge_usd_wad', edge), ('observed_winner_gas_cost_usd_wad', gas_usd),
                            ('gross_oracle_edge_minus_observed_winner_gas_usd_wad', edge-gas_usd)]:
            require(int(row[k]) == expected, 'transaction economics: ' + k)
        require(row['nqc_net_pnl_claimed'] is False and len(row['omitted_costs']) == 8, 'cost nonclaims')
        signs['positive' if edge > gas_usd else 'nonpositive'] += 1
        sum_debt += debt; sum_edge += edge; sum_gas += gas_usd; gas_wei_total += gas_wei
        day = (row['timestamp'] - 1788240215) // 86400
        require(0 <= day < 30, 'daily window')
        days[day] = [a+b for a,b in zip(days[day], [1, count, debt, edge, gas_usd])]
    daily = keyed(rows(files, 'rmc016-observed-daily-market-baseline.jsonl'), 'day_index', 30)
    require(set(daily) == set(range(30)), 'daily index set')
    fields = ['transaction_count', 'event_count', 'debt_principal_usd_wad',
              'gross_oracle_edge_usd_wad', 'observed_winner_gas_cost_usd_wad']
    for day, row in daily.items():
        require([int(row[k]) for k in fields] == days[day], 'daily reconciliation')
    for key, expected in [('observed_market_debt_principal_usd_wad', sum_debt),
                          ('observed_market_gross_oracle_edge_usd_wad', sum_edge),
                          ('observed_winner_gas_cost_usd_wad', sum_gas)]:
        require(int(doc[key]) == expected, 'aggregate total')
    return {'events': 139, 'transactions': 127, 'price_blocks': 123,
        'observed_debt_principal_usd_wad': str(sum_debt), 'observed_gross_oracle_edge_usd_wad': str(sum_edge),
        'observed_winner_gas_usd_wad': str(sum_gas), 'observed_winner_gas_wei': str(gas_wei_total),
        'gross_oracle_edge_minus_only_gas_usd_wad': str(sum_edge-sum_gas),
        'after_only_gas_sign_counts': dict(signs), 'legacy_negative_event_edges_clipped_to_zero': clipped_event_count,
        'all_127_match_prior_gas_ledger': True, 'double_counted_gas_transactions': 0,
        'daily_rows_reconciled': 30,
        'price_ledger_zero_base_fee_rows': sum(int(p['base_fee_per_gas']) == 0 for p in prices.values()),
        'price_ledger_base_fee_used_for_gas': False,
        'price_quote_state_scope': 'HISTORICAL_BLOCK_STATE_NOT_TRANSACTION_PRESTATE',
        'price_acquisition_received_at_available': False,
        'oracle_price_available_to_nqc_before_winner_proven': False,
        'reserve_decimals_historical_invariance_independently_proven': False,
        'complete_net_pnl_usd_wad': None, 'positive_nqc_value_admitted_usd_wad': '0'}


def verify(core, prior, output):
    files = read_core(core)
    temporal_doc, events, classifications = temporal(files)
    econ = economics(files, events, prior.read_bytes())
    output.mkdir(parents=True, exist_ok=False)
    ledger = b''.join(canon(r) for r in classifications)
    (output / 'temporal-candidate-classifications.jsonl').write_bytes(ledger)
    report = {'schema': 'nqc-temporal-economic-readback-v1', 'core_sha256': CORE_SHA,
        'temporal_authority_sha256': TEMPORAL_SHA, 'capacity_authority_sha256': CAPACITY_SHA,
        'window': temporal_doc['window'], 'candidate_accounts': len(classifications),
        'definite_accounts': 556, 'left_censored_initial_accounts': 432, 'censored_accounts': 29442,
        'classification_counts': {'INSUFFICIENT_EVIDENCE': len(classifications), 'EXECUTABLE': 0, 'NON_EXECUTABLE': 0},
        'classification_ledger_sha256': sha(ledger), 'classification_ledger_bytes': len(ledger),
        'original_envelope_replayed': False, 'upstream_risk_reconstruction_replayed': False,
        'decision_time_observations_proven': False, 'economics': econ,
        'scope': 'HASH_BOUND_HISTORICAL_LEDGER_PARTITION_AND_GROSS_ECONOMIC_ARITHMETIC',
        'independent_certification': False, 'census_closed': False,
        'verifier_sha256': sha(Path(__file__).read_bytes())}
    (output / 'report.json').write_bytes(canon(report))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('core', 'prior', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(verify(a.core, a.prior, a.output), sort_keys=True))
