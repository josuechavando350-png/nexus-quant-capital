"""Post-registration reporting only; no capture or selection changes."""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from statistics import median
import sys

from audit_transport import audit
from transport import canonical, MODES

folder = Path(sys.argv[1])
result = audit(folder)
def utc(ns):
    return datetime.fromtimestamp(ns/1e9, timezone.utc).isoformat()
def stats(values):
    return {'n':len(values),'min':min(values),'median':median(values),'max':max(values)} if values else None
rows = result['reads']
summary = {k:v for k,v in result.items() if k not in ('reads','started_utc_ns','ended_utc_ns')}
summary.update(started_utc=utc(result['started_utc_ns']), ended_utc=utc(result['ended_utc_ns']),
    modes={mode:{metric:stats([r[metric] for r in rows if r['mode']==mode]) for metric in
        ('input_ms','verified_ms','head_to_verified_ms','header_request_to_verified_ms')} for mode in MODES},
    triads=[],persistent_first_view=None,persistent_later_views=None)
for index in sorted({r['round'] for r in rows}):
    group = [r for r in rows if r['round']==index]
    state = group[0]['state']; coverage = state['coverage']
    shares,total = coverage['observed_borrow_shares'],coverage['total_borrow_shares']
    values = {r['mode']:{metric:r[metric] for metric in ('input_ms','verified_ms')} for r in group}
    ratios = None
    if len(group)==3:
        ratios = {mode:{metric:values[mode][metric]/values['persistent'][metric] for metric in ('input_ms','verified_ms')}
                  for mode in ('legacy','fresh')}
    summary['triads'].append({'round':index,'block':group[0]['block'],'order':[r['mode'] for r in group],
        'coverage':coverage,'coverage_percent':str(Decimal(shares)*100/Decimal(total)) if total else None,
        'positive_debt_accounts':state['positive_debt_accounts'],'candidates':state['screen_candidate_count'],
        'unhealthy':state['computed_unhealthy_count'], 'measurements':values, 'ratios_to_persistent':ratios})
persistent = [r for r in rows if r['mode']=='persistent']
if persistent:
    summary['persistent_first_view']={k:persistent[0][k] for k in ('input_ms','verified_ms','view_transport')}
    summary['persistent_later_views']={metric:stats([r[metric] for r in persistent[1:]]) for metric in ('input_ms','verified_ms')}
ledger = json.loads((folder/'requests.json').read_text()) if (folder/'requests.json').exists() else []
summary['transport_observations']={mode:{'requests':sum(r['mode']==mode for r in ledger),
    'socket_reused_true':sum(r['transport'].get('client_socket_reused') is True for r in ledger if r['mode']==mode),
    'socket_reused_false':sum(r['transport'].get('client_socket_reused') is False for r in ledger if r['mode']==mode),
    'socket_unobserved':sum(r['transport'].get('client_socket_reused') is None for r in ledger if r['mode']==mode)} for mode in MODES}
summary['input_below_assumed_1000ms']={mode:sum(r['input_ms']<=1000 for r in rows if r['mode']==mode) for mode in MODES}
summary['verified_below_assumed_1000ms']={mode:sum(r['verified_ms']<=1000 for r in rows if r['mode']==mode) for mode in MODES}
summary['errors']=sum('exception' in r for r in ledger)
(folder.parent/'summary.json').write_bytes(canonical(summary))
print(json.dumps(summary,indent=2))
