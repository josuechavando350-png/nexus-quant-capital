#!/usr/bin/env python3
"""Post-registration reporting only; does not select accounts or issue RPC calls."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from support import canonical, registry
from audit_experiment import audit


def summary(folder):
    report = audit(folder)
    rows = [json.loads(x) for x in (folder/'journal.jsonl').read_text().splitlines()]
    policy = rows[0]['data']['policy']
    source = registry.load(folder/'source-registry.json', policy)
    prior_addresses = {e['borrower'] for s in source['segments'] for e in s['events']}
    result = {k: report[k] for k in ['status','registration','rpc_calls','http_requests','rpc_errors',
                                    'elapsed_seconds','backfill_merged','registry','http_latency_ms']}
    result.update(started_utc=datetime.fromtimestamp(rows[0]['recorded_wall_ns']/10**9, timezone.utc).isoformat(),
                  finished_utc=datetime.fromtimestamp(rows[-1]['recorded_wall_ns']/10**9, timezone.utc).isoformat(),
                  source_accounts=len(prior_addresses), source_events=sum(len(s['events']) for s in source['segments']),
                  cohort_accounts=len(report['cohort']['addresses']) if report['cohort'] else None,
                  newly_enrolled_accounts=sorted(set(report['cohort']['addresses'])-prior_addresses) if report['cohort'] else None,
                  rounds=[], route_simulations=0, realized_profit=None, realized_capture_rate=None, live_broadcasts=0,
                  provider_count=1, funded_capacity_wei=0)
    if report['registry']:
        r = report['registry']; result['indexed_blocks'] = r['through_block']-r['from_block']+1
    if report['backfill_merged']:
        older=registry.load(folder/'older-registry.json',policy)
        result['backfill_events']=sum(len(s['events']) for s in older['segments'])
        result['backfill_blocks']=older['through_block']-older['from_block']+1
    for pair in report['comparisons']:
        snap=next(s for s in report['snapshots'] if s['round']==pair['round'] and s['mode']=='creation')
        state=snap['state']; total=state['coverage']['total_borrow_shares']
        previous=sum(p['position'][1] for p in state['positions'] if p['borrower'] in prior_addresses)
        pct=lambda value: str(Decimal(value)*100/Decimal(total)) if total else None
        result['rounds'].append({'round':pair['round'],'block':pair['block']['number'],'block_hash':pair['block']['hash'],
            'order':pair['order'],'input_ms':pair['input_ms'],'exact_state_parity':pair['exact_state_parity'],
            'head_to_first_inputs_ms':pair['head_to_first_inputs_ms'],'head_to_second_inputs_ms':pair['head_to_second_inputs_ms'],
            'within_assumed_budget_first_mode':pair['within_assumed_budget_first_mode'],
            'coverage':state['coverage'],'coverage_pct':pct(state['coverage']['observed_borrow_shares']),
            'prior_cohort_coverage_pct_at_same_block':pct(previous),
            'new_accounts_debt_share_pct_at_same_block':pct(state['coverage']['observed_borrow_shares']-previous),
            'positive_debt_accounts':state['positive_debt_accounts'],'screen_candidate_count':state['screen_candidate_count'],
            'computed_unhealthy_count':state['computed_unhealthy_count'],
            'stored_market_debt_usdg':str(Decimal(state['market'][2])/10**6),
            'observed_accrued_debt_usdg':str(Decimal(sum(p['screen']['debt_usdg_raw'] for p in state['positions']))/10**6),
            'minimum_health_margin_bps_floor':min((p['screen']['health_margin_bps_floor'] for p in state['positions'] if p['screen']['debt_usdg_raw']>0),default=None),
            'unindexed_tail_blocks':pair['block']['number']-report['registry']['through_block']})
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();result=summary(args.folder);args.out.write_bytes(canonical(result));print(json.dumps(result,indent=2))
