"""Post-registration descriptive reporting only, no network or selection."""
from datetime import datetime,timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from statistics import median
import sys

HERE=Path(__file__).resolve().parent
PROTOCOL=HERE.parent/'robinhood-paced-acquisition-20261016T1024'
sys.path.insert(0,str(PROTOCOL))
from audit_paced import audit
from paced_acquisition import canonical,registry

folder=Path(sys.argv[1]);result=audit(folder)
observations=result['observations']
journal=[json.loads(x) for x in (folder/'journal.jsonl').read_text().splitlines()]
rows=json.loads((folder/'requests.json').read_text()) if (folder/'requests.json').exists() else []
def stats(values):return {'n':len(values),'min':min(values),'median':median(values),'max':max(values)} if values else None
def utc(ns):return datetime.fromtimestamp(ns/1e9,timezone.utc).isoformat()
summary={k:v for k,v in result.items() if k not in ('observations','started_utc_ns','ended_utc_ns')}
summary.update(started_utc=utc(result['started_utc_ns']),ended_utc=utc(result['ended_utc_ns']),
    observations=[],completed_observations=len(observations),planned_observations=journal[0]['data']['policy']['rounds'],
    unique_blocks=len({r['block']['hash'] for r in observations}),repeated_heads=sum(r['repeated_head'] for r in observations),
    errors=sum('exception' in r for r in rows))
rotation=next((r for r in journal if r['kind']=='measurement_session_started'),None)
summary['preparation_seconds']=(rotation['recorded_ns']-journal[0]['data']['run_started_ns'])/1e9 if rotation else None
summary['preparation_rpc_calls']=rotation['data']['rpc_calls_before'] if rotation else None
source=json.loads((folder/'source-registry.json').read_text())['state']
prior_addresses={e['borrower'] for segment in source['segments'] for e in segment['events']}
summary['new_accounts']=sorted(set(result['cohort']['addresses'])-prior_addresses) if result['cohort'] else None
metrics=('header_ms','view_input_ms','request_to_inputs_ms','request_to_verified_ms',
         'header_admission_wait_ms','admission_to_inputs_ms','admission_to_verified_ms',
         'received_head_to_verified_ms','header_timestamp_age_at_final_response_ms','unindexed_tail_blocks')
summary['cold']={metric:observations[0][metric] for metric in metrics} if observations else None
summary['later']={metric:stats([r[metric] for r in observations[1:]]) for metric in metrics}
summary['within_assumed_1000ms']={'cold':observations[0]['within_assumed_1000ms'] if observations else None,
                                'later':sum(r['within_assumed_1000ms'] for r in observations[1:])}
prefix=json.loads((folder/'registry.json').read_text())['state']
prefix_accounts={e['borrower'] for segment in prefix['segments'] for e in segment['events']}
summary['validated_prefix_accounts']=len(prefix_accounts)
summary['new_prefix_accounts']=sorted(prefix_accounts-prior_addresses)
summary['measurement_started']=rotation is not None
summary['http_errors']=[{'label':r['label'],'status':r['transport'].get('status'),
                        'response_file':r.get('response_file'),'response_sha256':r.get('response_sha256')}
                       for r in rows if 'exception' in r]
for r in observations:
    s=r['state'];c=s['coverage'];total=c['total_borrow_shares']
    prior=sum(p['position'][1] for p in s['positions'] if p['borrower'] in prior_addresses)
    summary['observations'].append({**{k:r[k] for k in ('round','block','planned_start','repeated_head',*metrics)},
        'coverage':c,'coverage_percent':str(Decimal(c['observed_borrow_shares'])*100/Decimal(total)) if total else None,
        'prior_cohort_coverage_percent_same_block':str(Decimal(prior)*100/Decimal(total)) if total else None,
        'new_accounts_coverage_percentage_points':str(Decimal(c['observed_borrow_shares']-prior)*100/Decimal(total)) if total else None,
        'positive_debt_accounts':s['positive_debt_accounts'],'candidates':s['screen_candidate_count'],
        'unhealthy':s['computed_unhealthy_count'],
        'actual_socket_reused':{part:r[part+'_transport'].get('client_socket_reused') for part in ('head','view','canonical')},
        'client_socket_tags':{part:r[part+'_transport'].get('client_socket_tag') for part in ('head','view','canonical')}})
summary['measurement_transport']={'requests':len(rows)-rotation['data']['rpc_calls_before'] if rotation else 0,
    'observed_reused':sum(row['transport'].get('client_socket_reused') is True for row in rows[rotation['data']['rpc_calls_before']:]) if rotation else 0,
    'observed_new':sum(row['transport'].get('client_socket_reused') is False for row in rows[rotation['data']['rpc_calls_before']:]) if rotation else 0}
intervals=result['acquisition_admission_intervals_ms']
summary['cadence_intervals_ms']=stats(intervals)
summary['cadence_intervals_all_ms']=intervals
summary['observed_acquisition_rate_per_second']=1000*len(intervals)/sum(intervals) if intervals else None
summary['later_admission_intervals_ms']=stats(intervals[1:])
summary['later_observed_rate_per_second']=1000*len(intervals[1:])/sum(intervals[1:]) if len(intervals)>1 else None
heads=[r for r in rows if r['label'].startswith('r') and r['label'].endswith('-head')]
dispatch_intervals=[(b['started_ns']-a['started_ns'])/1e6 for a,b in zip(heads,heads[1:])]
summary['header_dispatch_intervals_all_ms']=dispatch_intervals
summary['later_header_dispatch_intervals_ms']=stats(dispatch_intervals[1:])
summary['later_mean_admission_interval_ms']=sum(intervals[1:])/len(intervals[1:]) if len(intervals)>1 else None
summary['rpc_start_gaps_ms']=stats([(b['started_ns']-a['started_ns'])/1e6 for a,b in zip(rows,rows[1:])])
summary['all_method_admission_wait_ms']=stats([(r['started_ns']-r['admission_requested_ns'])/1e6 for r in rows])
summary['all_methods_below_minimum_gap']=sum(b['started_ns']-a['started_ns'] < 350_000_000 for a,b in zip(rows,rows[1:]))
summary['measurement_seconds_including_admission']=(observations[-1]['verified_ns']-observations[0]['header_admission_requested_ns'])/1e9 if observations else None
summary['registry_file_sha256']=hashlib.sha256((folder/'registry.json').read_bytes()).hexdigest()
summary['first_connection_ms']=(rows[0]['received_ns']-rows[0]['started_ns'])/1e6 if rows and 'received_ns' in rows[0] else None
summary['terminal']=journal[-1]['data']
(HERE/'evidence/summary.json').write_bytes(canonical(summary))
print(json.dumps(summary,indent=2))
