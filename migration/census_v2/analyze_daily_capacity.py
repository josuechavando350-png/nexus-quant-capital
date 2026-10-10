#!/usr/bin/env python3
"""Audit historical daily distribution against targets, without forecasting P&L."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess

import reconcile_temporal_core as c

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = '154137de8c998e39a2097473eac6cf92cda465fa'
START = 1788240215
DAYS = 30
UNIT = 10**18
TX_FILE = 'rmc016-observed-transaction-economics.jsonl'
DAY_FILE = 'rmc016-observed-daily-market-baseline.jsonl'


def pinned(path):
    raw = path.read_bytes()
    actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    expected = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse',
                                       BASE + ':' + str(path.relative_to(ROOT))], text=True).strip()
    c.require(actual == expected, 'daily analysis source drift: ' + str(path.relative_to(ROOT)))
    return raw


def fraction(numerator, denominator):
    c.require(type(denominator) is int and denominator > 0, 'invalid denominator')
    return {'numerator': str(numerator), 'denominator': denominator}


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def summarize(transactions, days):
    c.keyed(transactions, 'transaction_hash', 127)
    daily = c.keyed(days, 'day_index', DAYS)
    c.require(set(daily) == set(range(DAYS)), 'daily index population')
    actual = defaultdict(lambda: [0, 0, 0, 0])
    for tx in transactions:
        index = (tx['timestamp'] - START) // 86400
        c.require(0 <= index < DAYS and tx['nqc_net_pnl_claimed'] is False and
                  len(tx['omitted_costs']) == 8, 'transaction scope or economic authority')
        gross, gas = int(tx['gross_oracle_edge_usd_wad']), int(tx['observed_winner_gas_cost_usd_wad'])
        c.require(gross >= 0 and gas >= 0 and gross - gas ==
                  int(tx['gross_oracle_edge_minus_observed_winner_gas_usd_wad']), 'transaction reference arithmetic')
        actual[index] = [a+b for a,b in zip(actual[index], [1, tx['event_count'], gross, gas])]
    rows = []
    for index, day in sorted(daily.items()):
        fields = ['transaction_count', 'event_count', 'gross_oracle_edge_usd_wad', 'observed_winner_gas_cost_usd_wad']
        c.require([int(day[k]) for k in fields] == actual[index], 'daily transaction conservation')
        gross, gas = actual[index][2:]
        rows.append({**day, 'start_utc': iso(START + index * 86400),
                     'end_exclusive_utc': iso(START + (index + 1) * 86400),
                     'gross_less_only_observed_gas_usd_wad': str(gross - gas),
                     'complete_nqc_net_profit_usd_wad': None})
    values = sorted(int(r['gross_less_only_observed_gas_usd_wad']) for r in rows)
    gross_total = sum(int(r['gross_oracle_edge_usd_wad']) for r in rows)
    gas_total = sum(int(r['observed_winner_gas_cost_usd_wad']) for r in rows)
    ranked = sorted(transactions, key=lambda r: (-int(r['gross_oracle_edge_usd_wad']), r['transaction_hash']))
    bands = []
    for ceiling in [10, 25, 50, 100, 250, 500]:
        chosen = [t for t in transactions if 0 < int(t['gross_oracle_edge_minus_observed_winner_gas_usd_wad']) <= ceiling * UNIT]
        subtotal = sum(int(t['gross_oracle_edge_minus_observed_winner_gas_usd_wad']) for t in chosen)
        bands.append({'upper_reference_usd': ceiling, 'lower_reference_usd_exclusive': 0,
                      'transactions': len(chosen), 'subtotal_reference_usd_wad': str(subtotal),
                      'mean_daily_reference_usd_wad_fraction': fraction(subtotal, DAYS),
                      'subset_selection': 'RETROSPECTIVE_CUMULATIVE_BAND_NOT_A_TRADE_RULE',
                      'complete_profit_proven': False})
    targets = []
    for target in [1500, 3500]:
        monthly = target * DAYS
        targets.append({'target_net_usd_per_day': target, 'target_net_usd_per_30_days': monthly,
                        'reference_days_at_least_target': sum(v >= target * UNIT for v in values),
                        'reference_days_below_target': sum(v < target * UNIT for v in values),
                        'required_fraction_of_30_day_after_only_gas_reference': fraction(monthly * UNIT, gross_total - gas_total),
                        'fraction_is_capture_probability': False, 'target_minimum_proven': False})
    summary = {
        'transactions': 127, 'events': sum(d['event_count'] for d in days), 'days': DAYS,
        'gross_oracle_edge_usd_wad': str(gross_total), 'observed_winner_gas_usd_wad': str(gas_total),
        'reference_after_only_observed_gas_usd_wad': str(sum(values)),
        'mean_daily_reference_usd_wad_fraction': fraction(sum(values), DAYS),
        'median_daily_reference_usd_wad_fraction': fraction(values[14] + values[15], 2),
        'minimum_daily_reference_usd_wad': str(values[0]), 'maximum_daily_reference_usd_wad': str(values[-1]),
        'zero_transaction_days': sum(d['transaction_count'] == 0 for d in days),
        'reference_negative_days': sum(v < 0 for v in values),
        'observed_transactions_per_day_fraction': fraction(127, DAYS),
        'concentration_by_gross': [{'top_transactions': n,
            'gross_usd_wad': str(sum(int(t['gross_oracle_edge_usd_wad']) for t in ranked[:n])),
            'share_of_total_gross': fraction(sum(int(t['gross_oracle_edge_usd_wad']) for t in ranked[:n]), gross_total),
            'transaction_hashes': [t['transaction_hash'] for t in ranked[:n]]} for n in [1, 3, 5, 10, 20]],
        'small_reference_bands': bands, 'targets': targets,
        'hypothetical_captured_trades_required': [
            {'net_usd_per_captured_trade_assumption': net,
             'trades_for_1500_net_usd': (1500 + net - 1) // net,
             'trades_for_3500_net_usd': (3500 + net - 1) // net}
            for net in [20, 50, 100, 250]],
        'hypothetical_table_includes_all_costs_in_net_assumption': True,
        'hypothetical_table_is_forecast': False,
    }
    return rows, summary


def analyze(core):
    dependencies = {str(path.relative_to(ROOT)): c.sha(pinned(path)) for path in
                    [HERE / 'reconcile_temporal_core.py', HERE / 'verify_server_recovery.py']}
    files = c.read_core(core)
    temporal, events, _ = c.temporal(files)
    prior = pinned(HERE / 'evidence/economics/replay/winner-economic-ledger.jsonl')
    economic = c.economics(files, events, prior)
    # Compare the newly reexecuted economic section to its published readback.
    old = c.parse(pinned(HERE / 'evidence/server-recovery/core-readback.json'))
    c.require(old['economics'] == economic, 'published economic readback differs')
    rows, summary = summarize(c.rows(files, TX_FILE), c.rows(files, DAY_FILE))
    c.require(summary['gross_oracle_edge_usd_wad'] == economic['observed_gross_oracle_edge_usd_wad'] and
              summary['observed_winner_gas_usd_wad'] == economic['observed_winner_gas_usd_wad'], 'economic totals differ')
    ledger = b''.join(c.canon(r) for r in rows)
    report = {'schema': 'nqc-daily-capacity-target-audit-v1', 'source_commit': BASE,
        'consumer_sha256': c.sha(Path(__file__).read_bytes()), 'core_sha256': c.CORE_SHA,
        'dependencies_sha256': dependencies, 'source_files_sha256': {n: c.sha(files[n]) for n in
            [TX_FILE, DAY_FILE, 'rmc016-capacity-authority.json', 'rmc016-liquidation-block-price-authority.jsonl']},
        'daily_output_sha256': c.sha(ledger), 'window': temporal['window'],
        'window_start_utc': iso(START), 'window_end_utc': iso(START + DAYS * 86400),
        'bucket_definition': '30_CONSECUTIVE_24_HOUR_WINDOWS_FROM_SOURCE_ANCHOR_NOT_LOCAL_CALENDAR_DAYS',
        'scope': 'AAVE_V3_ETHEREUM_DECLARED_POOL_RETAINED_EXECUTED_WINNERS',
        'summary': summary, 'economic_readback': economic,
        'known_value_is_oracle_reference_not_monetizable_profit': True,
        'observed_reference_is_not_global_opportunity_upper_bound': True,
        'historical_winners_are_not_independent_nqc_captures': True,
        'complete_nqc_net_pnl_usd_wad': None, 'success_probability': None,
        'daily_minimum_income_proven': False, 'daily_average_income_proven': False,
        'new_independent_markets_validated': 0, 'new_rpc_requests': 0,
        'census_closed': False, 'independent_certification': False}
    return ledger, report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--core', type=Path, required=True); p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); ledger, report = analyze(a.core)
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out / 'daily.jsonl').write_bytes(ledger); (a.out / 'report.json').write_bytes(c.canon(report))
    print(c.canon(report['summary']).decode(), end='')
