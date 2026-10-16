"""Persist synthetic join/stop traces, never blockchain evidence."""
import json
from unittest.mock import patch
from test_history import HERE,fixture,execute,audit,canonical
with patch('requests.adapters.HTTPAdapter.send',side_effect=AssertionError('OFFLINE_ONLY')):
    chain,p,raw=fixture();path=HERE/'evidence/synthetic/complete';reader=execute(path,chain,p,raw)
    result=audit(path,p);(path/'audit.json').write_bytes(canonical(result))
    fault=next(r['payload']['id'] for r in reader.records if r['label']=='catchup-index-head')
    chain,p,raw=fixture();path=HERE/'evidence/synthetic/after-merge-stop';reader=execute(path,chain,p,raw,fail=fault)
    stopped=audit(path,p);(path/'audit.json').write_bytes(canonical(stopped))
    assert stopped['backfill_merged'] and stopped['cohort'] is None and stopped['registry']['added_history_blocks']==20
summary={'synthetic_only':True,'chain_rpc_calls':0,'complete_simulated_calls':result['rpc_calls'],
         'failure_simulated_call':fault,'minimum_simulated_start_gap_ms':result['minimum_start_gap_ms'],
         'after_merge_stop_preserves_history':True,'after_merge_stop_frozen_cohort':False}
(HERE/'evidence/synthetic-summary.json').write_bytes(canonical(summary));print(json.dumps(summary))
