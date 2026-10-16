"""Retain artificial full and interrupted runs; zero live RPC."""
import json
from pathlib import Path
from unittest.mock import patch
from test_recovery import HERE, fixture, execute
from audit_recovery import audit

out = HERE/'evidence/synthetic'
out.mkdir(parents=True,exist_ok=True)
with patch('requests.adapters.HTTPAdapter.send',side_effect=AssertionError('OFFLINE_ONLY')):
    chain,p,raw,older_raw=fixture()
    base=execute(out/'complete',chain,p,raw,older_raw)
    complete=audit(out/'complete',p)
    boundary=next(r['payload']['id'] for r in base.records if r['label']=='catchup-index-head')
    chain,p,raw,older_raw=fixture()
    execute(out/'stop-after-merge',chain,p,raw,older_raw,fail=boundary)
    stopped=audit(out/'stop-after-merge',p)
for name,result in [('complete',complete),('stop-after-merge',stopped)]:
    (out/(name+'-audit.json')).write_text(json.dumps(result,indent=2)+'\n')
(out/'receipt.json').write_text(json.dumps({'artificial':True,'chain_rpc_calls':0,
    'complete_rpc_positions':base.count,'stop_after_merge_before_catchup_rpc_position':boundary,
    'not_market_or_latency_evidence':True},indent=2)+'\n')
