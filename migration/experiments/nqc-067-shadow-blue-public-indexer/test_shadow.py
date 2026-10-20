import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import urllib.error

import shadow

MARKET='0x698fe98247a40c5771537b5786b2f3f9d78eb487b4ce4d75533cd0e94d88a115'
BORROWER='0x'+'12'*20
LIQUIDATOR='0x'+'56'*20
TX='0x'+'ab'*32
NOW=dt.datetime(2026,10,19,20,0,tzinfo=dt.timezone.utc)

def position(*, usd='100',coll='100',debt='100',addr=BORROWER):
    return {
        'market':{'marketId':MARKET,'lltv':'860000000000000000',
                  'loanAsset':{'address':'0x'+'34'*20,'decimals':6},
                  'collateralAsset':{'address':'0x'+'23'*20,'decimals':18}},
        'user':{'address':addr},
        'state':{'borrowAssets':debt,'collateral':coll,
                 'borrowAssetsUsd':usd,'collateralUsd':coll}
    }

def event(*,index=1,tx=TX):
    return {'blockNumber':24550000,'txHash':tx,'timestamp':1792440000,
        'logIndex':index,'type':'Liquidation', 'market':{'marketId':MARKET},
        'user':{'address':BORROWER},
        'data':{'seizedAssets':'1000','repaidAssets':'200','badDebtAssets':'0','liquidator':LIQUIDATOR}}

def wrapper(positions=None,events=None):
    return {'data':{
        'marketPositions':{'items':positions if positions is not None else [position()]},
        'marketTransactions':{'items':events if events is not None else [event()]}
    }}

class SafeShadowTests(unittest.TestCase):
    def test_pinned_query_no_private_endpoints(self):
        q=shadow.build_query([MARKET])
        self.assertIn('marketPositions(first: 25',q)
        self.assertIn('marketTransactions(first: 20',q)
        self.assertIn('type_in: [Liquidation]',q)
        self.assertNotIn('sendRawTransaction',q)
        self.assertNotIn('mutation',q)
    def test_market_whitelist_rejects_invalid(self):
        for x in ([],['foo'], [MARKET]*4):
            if x == [MARKET]*4: continue  # repeated markets dedupe, not 4 distinct markets
            with self.assertRaises(shadow.ShadowBoundaryError):
                shadow.check_markets(x)
        self.assertEqual(shadow.check_markets([MARKET.upper().replace('0X','0x'),MARKET]),[MARKET])
    def test_market_max_three_unique(self):
        with self.assertRaises(shadow.ShadowBoundaryError):
            shadow.check_markets([MARKET]+['0x'+f'{i:064x}' for i in (1,2,3)])
    def test_indexer_health_heuristic_only(self):
        r=shadow.normalize(wrapper(),[MARKET],'2026-10-19T20:00:00Z','0'*64)
        self.assertEqual(r['positions'][0]['indexed_estimated_health_factor'],'0.860000')
        self.assertIn('NOT_CANONICAL',r['positions'][0]['screen_status'])
        self.assertIsNone(r['positions'][0]['can_liquidate_onchain'])
        self.assertIsNone(r['positions'][0]['profitability'])
    def test_absent_usd_cannot_estimate(self):
        p=position()
        p['state']['collateralUsd']=None
        r=shadow.normalize(wrapper([p]),[MARKET],'2026-10-19T20:00:00Z','0'*64)
        self.assertIsNone(r['positions'][0]['indexed_estimated_health_factor'])
    def test_debt_zero_not_an_at_risk_loan(self):
        p=position(debt='0')
        r=shadow.normalize(wrapper([p]),[MARKET],'2026-10-19T20:00:00Z','0'*64)
        self.assertEqual(r['positions'][0]['screen_status'],'INDEXER_AMOUNTS_ONLY')
    def test_other_market_rejected(self):
        p=position();p['market']['marketId']='0x'+'01'*32
        with self.assertRaises(shadow.ShadowBoundaryError):
            shadow.normalize(wrapper([p]),[MARKET],'2026-10-19T20:00:00Z','0'*64)
    def test_event_identity_and_no_profit(self):
        r=shadow.normalize(wrapper(),[MARKET],'2026-10-19T20:00:00Z','0'*64)
        e=r['events'][0]
        self.assertTrue(e['event_id'].startswith('1:'+MARKET+':'))
        self.assertIsNone(e['net_NQC_profit'])
        self.assertFalse(e['canonical_proof'])
        self.assertFalse(r['commercial_admission'])
    def test_duplicate_event_fails(self):
        with self.assertRaises(shadow.ShadowBoundaryError):
            shadow.normalize(wrapper(events=[event(),event()]),[MARKET],'2026-10-19T20:00:00Z','0'*64)
    def test_bad_non_integer_amount_fails(self):
        p=position(debt='1e9')
        with self.assertRaises(shadow.ShadowBoundaryError):
            shadow.normalize(wrapper([p]),[MARKET],'2026-10-19T20:00:00Z','0'*64)
    def test_gql_errors_rejected(self):
        r=wrapper();r['errors']=[{'message':'rate limited'}]
        with self.assertRaises(shadow.ShadowBoundaryError):
            shadow.normalize(r,[MARKET],'2026-10-19T20:00:00Z','0'*64)
    def test_partial_results_rejected(self):
        r={'data':{'marketPositions':{'items':[]}}}
        with self.assertRaises(shadow.ShadowBoundaryError):
            shadow.normalize(r,[MARKET],'2026-10-19T20:00:00Z','0'*64)
    def test_baseline_not_fake_activity(self):
        baseline=shadow.normalize(wrapper(),[MARKET],'2026-10-19T20:00:00Z','0'*64)
        d=shadow.first_seen_deltas(None,baseline)
        self.assertEqual(d['snapshot_kind'],'BASELINE_ONLY')
        self.assertEqual(d['new_indexer_event_ids'],[])
    def test_second_snapshot_sees_new_event_not_capturable(self):
        p=shadow.normalize(wrapper(),[MARKET],'2026-10-19T20:00:00Z','0'*64)
        e2=event(index=2,tx='0x'+'cd'*32)
        q=shadow.normalize(wrapper(events=[event(),e2]),[MARKET],'2026-10-19T20:01:00Z','1'*64)
        d=shadow.first_seen_deltas(p,q)
        self.assertEqual(len(d['new_indexer_event_ids']),1)
        self.assertFalse(d['can_infer_ex_ante_capture'])
    def test_different_market_comparison_forbidden(self):
        p=shadow.normalize(wrapper(),[MARKET],'2026-10-19T20:00:00Z','0'*64)
        q=dict(p,watchlisted_markets=['0x'+'01'*32])
        with self.assertRaises(shadow.ShadowBoundaryError):
            shadow.first_seen_deltas(p,q)
    def test_raw_bytes_and_normalized_snapshot_are_distinct(self):
        raw=json.dumps(wrapper(),indent=4).encode('utf-8')
        with tempfile.TemporaryDirectory() as d:
            a=shadow.ingest_body(raw,[MARKET],Path(d),NOW)
            b=shadow.ingest_body(raw,[MARKET],Path(d),NOW+dt.timedelta(hours=1))
            self.assertEqual(a['raw_body_sha256'],shadow.sha256(raw))
            self.assertEqual(b['delta_from_previous']['snapshot_kind'],'AFTER_BASELINE')
            self.assertEqual(len(list(Path(d).glob('*.raw.json'))),2)
            self.assertEqual(len(list(Path(d).glob('observation_*.json'))),4)
    def test_file_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a';shadow.save_new(p,b'hello')
            with self.assertRaises(FileExistsError):
                shadow.save_new(p,b'world')
            self.assertEqual(p.read_bytes(),b'hello')
    def test_no_network_by_default(self):
        with patch('shadow.fetch_public_once') as f, tempfile.TemporaryDirectory() as d:
            with patch('sys.stdout'):
                rc=shadow.run_cli(['--market-id',MARKET,'--print-query','--out',d])
            self.assertEqual(rc,0)
            f.assert_not_called()
    def test_no_public_fetch_without_explicit_approval(self):
        with patch('shadow.fetch_public_once') as f, tempfile.TemporaryDirectory() as d:
            with patch('sys.stderr'):
                rc=shadow.run_cli(['--market-id',MARKET,'--fetch-public-once','--out',d])
            self.assertEqual(rc,2)
            f.assert_not_called()
    def test_provider_403_stops_no_retry(self):
        with patch('shadow.urllib.request.urlopen',side_effect=urllib.error.HTTPError(shadow.API_URL,403,'forbidden',{},None)) as f:
            with self.assertRaises(shadow.ShadowBoundaryError):
                shadow.fetch_public_once(shadow.build_query([MARKET]))
            self.assertEqual(f.call_count,1)
    def test_provider_429_stops_no_retry(self):
        with patch('shadow.urllib.request.urlopen',side_effect=urllib.error.HTTPError(shadow.API_URL,429,'rate',{},None)) as f:
            with self.assertRaises(shadow.ShadowBoundaryError):
                shadow.fetch_public_once(shadow.build_query([MARKET]))
            self.assertEqual(f.call_count,1)
    def test_size_cap(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(shadow.ShadowBoundaryError):
                shadow.ingest_body(b'x'*(shadow.MAX_BYTES+1),[MARKET],Path(d),NOW)
    def test_snapshot_page_not_complete(self):
        r=shadow.normalize(wrapper(),[MARKET],'2026-10-19T20:00:00Z','0'*64)
        self.assertFalse(r['coverage_complete'])
        self.assertIsNone(r['actual_NQC_profit'])
    def test_no_extra_obligations_inferred(self):
        e=shadow.assess_indexed_liquidation(event(),{MARKET})
        self.assertIsNone(e['event_was_ex_ante_capturable'])
        self.assertIsNone(e['net_NQC_profit'])

if __name__=='__main__':
    unittest.main()

class AdditionalBoundaries(unittest.TestCase):
    def test_binary_float_rejected(self):
        with self.assertRaises(shadow.ShadowBoundaryError):
            shadow.decimal_str(0.86,'indexedPrice')
    def test_decimal_is_exact(self):
        from decimal import Decimal
        self.assertEqual(shadow.decimal_str(Decimal('1.123456789012345678'),'usd'),Decimal('1.123456789012345678'))
    def test_ingest_json_numeric_decimal_precision(self):
        raw=b'{"data":{"marketPositions":{"items":[]},"marketTransactions":{"items":[]}}}'
        with tempfile.TemporaryDirectory() as d:
            snap=shadow.ingest_body(raw,[MARKET],Path(d),NOW)
            self.assertEqual(snap['observed_liquidation_events_count'],0)
            self.assertFalse(snap['coverage_complete'])
    def test_network_failure_creates_permanent_review_marker(self):
        with tempfile.TemporaryDirectory() as d:
            with patch('shadow.fetch_public_once',side_effect=shadow.ShadowBoundaryError('HTTP 429')) as f, patch('sys.stderr'):
                out=shadow.run_cli(['--market-id',MARKET,'--fetch-public-once','--explicit-read-approval','--out',d])
            self.assertEqual(out,2)
            self.assertTrue((Path(d)/'MANUAL_REVIEW_REQUIRED').exists())
            with patch('shadow.fetch_public_once') as second, patch('sys.stderr'):
                out=shadow.run_cli(['--market-id',MARKET,'--fetch-public-once','--explicit-read-approval','--out',d])
            self.assertEqual(out,2)
            second.assert_not_called()
