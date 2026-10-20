"""Offline tests for bounded multi-market discovery, not liquidity or profit tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import bulk_shadow as b

M1='0x'+'11'*32
M2='0x'+'22'*32
M3='0x'+'33'*32
ADDR='0x'+'ab'*20


def pos(m=M1,addr=ADDR):
    return {'market':{'marketId':m},'user':{'address':addr}}


def gql(rows,*,count=None,total=None):
    return b.canonical({'data':{'marketPositions':{
        'items':rows,'pageInfo':{'count':len(rows) if count is None else count,'countTotal':total}}}})


def market(mid=M1,chain=1):
    return {'chain_id':chain,'market_id':mid,'loan_token':'0x'+'01'*20,
            'collateral_token':'0x'+'02'*20,'oracle_address':'0x'+'03'*20,
            'irm_address':'0x'+'04'*20,'lltv_wad':'860000000000000000'}


def rest(markets,cursor=None):
    return b.canonical({'data':markets,'cursor':cursor})


def legacy():
    return {'schema':'nqc055-radar-v1','evaluation':{'dossiers':142,
        'economically_rankable_alternatives':0,
        'status_counts':{'NO_PUEDE_EVALUARSE_CON_DATOS_ACTUALES':140,
                         'REQUIERE_EVIDENCIA_ESPECIFICA':2}},
        'shared_market_groups':61,'shared_asset_pair_groups':54}


class DocumentedQueryTests(unittest.TestCase):
    def test_query_matches_official_filter(self):
        q=b.query_request(0)
        self.assertIn('chainId_in: $chainIds',q['query'])
        self.assertIn('healthFactor_lte: $hfLte',q['query'])
        self.assertIn('marketListed: true',q['query'])
        self.assertIn('orderBy: HealthFactor',q['query'])
        self.assertEqual(q['variables'],{'chainIds':[1],'hfLte':1.02,'first':1000,'skip':0})
    def test_query_is_read_only(self):
        q=b.query_request(1000)
        self.assertNotIn('mutation',q['query'].lower())
        self.assertNotIn('sendRawTransaction',q['query'])
        self.assertNotIn('private_key',q['query'].lower())
    def test_query_rejects_bad_skip(self):
        for skip in (-1,1,999,0.0,'0',None,True):
            with self.subTest(skip=skip), self.assertRaises(b.EvidenceError):b.query_request(skip)
    def test_query_multiple_offset(self):
        self.assertEqual(b.query_request(5000)['variables']['skip'],5000)


class PositionPageTests(unittest.TestCase):
    def test_simple_page(self):
        p=b.parse_position_page(gql([pos()],total=1),0)
        self.assertEqual(p['count'],1)
        self.assertEqual(p['pairs'][0]['borrower'],ADDR)
        self.assertIsNone(p['pairs'][0]['profit'])
    def test_missing_pageinfo_fail(self):
        x=json.loads(gql([pos()]));del x['data']['marketPositions']['pageInfo']
        with self.assertRaises(b.EvidenceError):b.parse_position_page(b.canonical(x),0)
    def test_page_count_mismatch(self):
        with self.assertRaises(b.EvidenceError):b.parse_position_page(gql([pos()],count=2),0)
    def test_page_gql_error_fail(self):
        with self.assertRaises(b.EvidenceError):b.parse_position_page(b.canonical({'errors':[{'message':'blocked'}],'data':{}}),0)
    def test_page_more_than_1000(self):
        rows=[pos(addr='0x'+f'{i:040x}') for i in range(1001)]
        with self.assertRaises(b.EvidenceError):b.parse_position_page(gql(rows),0)
    def test_chain_unavailable_in_row_never_authentic(self):
        p=b.parse_position_page(gql([pos()]),0)['pairs'][0]
        self.assertIsNone(p['eligible_onchain'])
    def test_bad_market_rejected(self):
        with self.assertRaises(b.EvidenceError):b.parse_position_page(gql([pos('0x123')]),0)
    def test_bad_borrower_rejected(self):
        with self.assertRaises(b.EvidenceError):b.parse_position_page(gql([pos(addr='0x1')]),0)
    def test_duplicate_in_page_rejected(self):
        with self.assertRaises(b.EvidenceError):b.parse_position_page(gql([pos(),pos()]),0)
    def test_spoof_bad_counttotal(self):
        with self.assertRaises(b.EvidenceError):b.parse_position_page(gql([pos()],total=0),0)
    def test_float_count_rejected(self):
        with self.assertRaises(b.EvidenceError):b.parse_position_page(gql([pos()],count=1.0),0)
    def test_invalid_json_duplicate_keys_rejected(self):
        body=b'{"data":{"marketPositions":{"items":[],"pageInfo":{"count":0,"count":0}}}}'
        with self.assertRaises(b.EvidenceError):b.parse_position_page(body,0)
    def test_truncated_body_rejected(self):
        with self.assertRaises(b.EvidenceError):b.parse_position_page(b'x'*(b.MAX_BODY_BYTES+1),0)


class PaginationTests(unittest.TestCase):
    def many(self,n,start=0):
        return [pos(M1,'0x'+f'{i:040x}') for i in range(start,start+n)]
    def test_no_files_not_zero(self):
        p=b.aggregate_positions([])
        self.assertIsNone(p['indexed_candidates'])
        self.assertFalse(p['coverage_complete'])
    def test_one_short_page_terminal(self):
        p=b.aggregate_positions([(0,gql([pos(M1),pos(M2,'0x'+'cd'*20)],total=2))])
        self.assertEqual(p['indexed_candidates'],2)
        self.assertEqual(p['distinct_markets_with_candidates'],2)
        self.assertTrue(p['indexer_filtered_scan_reached_end'])
        self.assertFalse(p['coverage_complete'])
    def test_exact_1000_page_then_short(self):
        p=b.aggregate_positions([(0,gql(self.many(1000),total=1001)),
                                 (1000,gql(self.many(1,1000),total=1001))])
        self.assertEqual(p['raw_position_rows'],1001)
        self.assertEqual(p['indexed_candidates'],1001)
        self.assertTrue(p['indexer_filtered_scan_reached_end'])
    def test_pagecap_at_1000_not_completeness(self):
        p=b.aggregate_positions([(0,gql(self.many(1000),total=2000))])
        self.assertTrue(p['truncated_by_cap'])
        self.assertFalse(p['indexer_filtered_scan_reached_end'])
    def test_duplicate_across_pages_fails_complete(self):
        p=b.aggregate_positions([(0,gql(self.many(1000),total=1001)),
                                 (1000,gql(self.many(1),total=1001))])
        self.assertEqual(p['indexed_candidates'],1000)
        self.assertEqual(p['duplicate_pairs_across_pages'],1)
        self.assertFalse(p['pagination_consistent'])
        self.assertFalse(p['indexer_filtered_scan_reached_end'])
    def test_bad_offset_rejected(self):
        with self.assertRaises(b.EvidenceError):b.aggregate_positions([(1000,gql([pos()]))])
    def test_inconsistent_totals_fail_completeness(self):
        p=b.aggregate_positions([(0,gql(self.many(1000),total=1100)),
                                  (1000,gql(self.many(50,1000),total=1050))])
        self.assertFalse(p['pagination_consistent'])
    def test_extra_page_after_short_rejected(self):
        with self.assertRaises(b.EvidenceError):b.aggregate_positions([(0,gql([pos()])),(1,gql([]))])
    def test_no_progress_in_expected_total_rejected(self):
        with self.assertRaises(b.EvidenceError):b.aggregate_positions([(0,gql(self.many(1000),total=1500)),
                                                                        (1000,gql([],total=1500))])
    def test_max_pages_invalid(self):
        with self.assertRaises(b.EvidenceError):b.aggregate_positions([(0,gql([]))],max_pages=11)


class RestMarketsTests(unittest.TestCase):
    def test_no_rest_pages_not_zero(self):
        self.assertIsNone(b.aggregate_markets([])['market_count'])
    def test_rest_parser(self):
        p=b.parse_market_page(rest([market()],cursor='next'),'old')
        self.assertEqual(p['next_cursor'],'next')
        self.assertEqual(p['markets'][0]['market_id'],M1)
    def test_rest_chain_mismatch(self):
        with self.assertRaises(b.EvidenceError):b.parse_market_page(rest([market(chain=8453)]),None)
    def test_rest_missing_lltv(self):
        m=market();del m['lltv_wad']
        with self.assertRaises(b.EvidenceError):b.parse_market_page(rest([m]),None)
    def test_rest_bad_token(self):
        m=market();m['loan_token']='bad'
        with self.assertRaises(b.EvidenceError):b.parse_market_page(rest([m]),None)
    def test_rest_cursor_cycle(self):
        with self.assertRaises(b.EvidenceError):b.aggregate_markets([(None,rest([market()],cursor='a')),
            ('a',rest([market(M2)],cursor='a'))])
    def test_rest_duplicate_cross_page(self):
        with self.assertRaises(b.EvidenceError):b.aggregate_markets([(None,rest([market()],cursor='a')),
            ('a',rest([market()],cursor=None))])
    def test_rest_skip_partial(self):
        p=b.aggregate_markets([(None,rest([market()],cursor='next'))])
        self.assertEqual(p['market_count'],1)
        self.assertTrue(p['truncated_by_cap'])
        self.assertFalse(p['indexer_pagination_exhausted'])
    def test_rest_two_pages_full(self):
        p=b.aggregate_markets([(None,rest([market()],cursor='next')),
                               ('next',rest([market(M2)],cursor=None))])
        self.assertEqual(p['market_count'],2)
        self.assertTrue(p['indexer_pagination_exhausted'])
        self.assertFalse(p['canonical_universe_complete'])
    def test_rest_empty_with_cursor_rejected(self):
        with self.assertRaises(b.EvidenceError):b.parse_market_page(rest([],cursor='more'),None)


class EvidenceAndSafetyTests(unittest.TestCase):
    def test_legacy_references_not_live(self):
        p=b.reference_scope(legacy())
        self.assertEqual((p['historical_dossiers'],p['historical_distinct_markets'],p['historical_asset_pairs']), (142,61,54))
        self.assertEqual(p['not_evaluable'],140)
        self.assertIsNone(p['NQC_realized_profit'])
    def test_bad_legacy_rejected(self):
        x=legacy();x['evaluation']['dossiers']=149
        with self.assertRaises(b.EvidenceError):b.reference_scope(x)
    def test_import_NQC067_pinned_without_modification(self):
        mod=b.import_nqc067_pinned_parser()
        self.assertEqual(mod.API_URL,'https://api.morpho.org/graphql')
        self.assertEqual(mod.CHAIN_ID,1)
    def test_import_refuses_byte_modified_copy(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'shadow.py';f.write_bytes(b'print("patch")')
            with self.assertRaises(b.EvidenceError):b.import_nqc067_pinned_parser(f)
    def test_real_NQC067_deep_parser_reused(self):
        rich={'data':{
          'marketPositions':{'items':[]},'marketTransactions':{'items':[]}}}
        r=b.refine_with_pinned_nqc067(b.canonical(rich),[M1],
                 '2026-10-19T20:00:00Z',candidate_market_ids={M1})
        self.assertEqual(r['watchlisted_markets'],[M1])
        self.assertIsNone(r['actual_NQC_profit'])
        self.assertFalse(r['coverage_complete'])
    def test_deep_review_rejects_unseen_market(self):
        with self.assertRaises(b.EvidenceError):
            b.refine_with_pinned_nqc067(b'{}',[M2],
                '2026-10-19T20:00:00Z',candidate_market_ids={M1})
    def test_deep_review_max_three(self):
        with self.assertRaises(b.EvidenceError):
            b.refine_with_pinned_nqc067(b'{}',[M1,M2,M3,M1],
                '2026-10-19T20:00:00Z')

    def test_offline_no_records_unknown(self):
        p=b.offline_evaluate(None,None,None)
        self.assertIsNone(p['risk_candidate_count_from_input'])
        self.assertIsNone(p['economic_net_USD'])
        self.assertFalse(p['commercial_admission'])
    def test_offline_realized_remains_none(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);posdir=root/'positions';posdir.mkdir()
            (posdir/'positions_skip_000000.raw.json').write_bytes(gql([pos()]))
            ar=root/'old.json';ar.write_bytes(b.canonical(legacy()))
            p=b.offline_evaluate(posdir,None,ar)
            self.assertEqual(p['risk_screen']['indexed_candidates'],1)
            self.assertIsNone(p['NQC_actual_profit'])
            self.assertIsNone(p['authenticated_live_candidate_count'])
            self.assertEqual(p['legacy']['historical_dossiers'],142)
            self.assertIsNone(p['markets']['market_count'])
    def test_offline_market_position_conflict(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); posdir=root/'pos';posdir.mkdir();md=root/'markets';md.mkdir()
            (posdir/'positions_skip_000000.raw.json').write_bytes(gql([pos(M3)]))
            (md/'markets_000000.raw.json').write_bytes(rest([market()]))
            (md/'manifest.json').write_bytes(b.canonical({'ordered_pages':[
                {'file':'markets_000000.raw.json','input_cursor':None}]}))
            with self.assertRaises(b.EvidenceError):b.offline_evaluate(posdir,md,None)
    def test_offline_manifest_path_traversal(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);md=root/'markets';md.mkdir()
            (md/'manifest.json').write_bytes(b.canonical({'ordered_pages':[
                {'file':'../secrets.json','input_cursor':None}]}))
            with self.assertRaises(b.EvidenceError):b.offline_evaluate(None,md,None)
    def test_network_denied_without_approval(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(b,'api_fetch') as fetch:
                with self.assertRaises(b.EvidenceError):b.fetch_candidate_pages_bounded(Path(d)/'proof')
                fetch.assert_not_called()
    def test_network_only_one_request_on_success(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(b,'api_fetch',return_value=gql([pos()],total=1)) as fetch:
                z=b.fetch_candidate_pages_bounded(Path(d)/'proof',approval=True,max_pages=2)
                self.assertEqual(z['indexed_candidates'],1)
                self.assertEqual(fetch.call_count,1)
                self.assertFalse(z['commercial_admission'])
    def test_network_fail_halts_and_saves_sentinel(self):
        with tempfile.TemporaryDirectory() as d:
            proof=Path(d)/'proof'
            with patch.object(b,'api_fetch',side_effect=b.EvidenceError('HTTP 429, stop')) as fetch:
                with self.assertRaises(b.EvidenceError):b.fetch_candidate_pages_bounded(proof,approval=True)
                self.assertEqual(fetch.call_count,1)
            self.assertTrue((proof/'MANUAL_REVIEW_REQUIRED').exists())
            with patch.object(b,'api_fetch') as fetch:
                with self.assertRaises(b.EvidenceError):b.fetch_candidate_pages_bounded(proof,approval=True)
                fetch.assert_not_called()
    def test_network_full_page_then_second(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(b,'api_fetch',side_effect=[gql([pos(addr='0x'+f'{i:040x}') for i in range(1000)],total=1001),gql([pos(addr='0x'+'aa'*20)],total=1001)]) as fetch:
                z=b.fetch_candidate_pages_bounded(Path(d)/'proof',approval=True,max_pages=5)
                self.assertEqual(fetch.call_count,2)
                self.assertEqual(z['indexed_candidates'],1001)

    def test_network_market_directory_no_approval(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(b,'api_fetch') as fetch:
                with self.assertRaises(b.EvidenceError):b.fetch_market_directory_bounded(Path(d)/'x')
                fetch.assert_not_called()
    def test_network_market_directory_two_pages(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(b,'api_fetch',side_effect=[rest([market()],cursor='next'),rest([market(M2)],cursor=None)]) as fetch:
                result=b.fetch_market_directory_bounded(Path(d)/'x',approval=True,max_pages=3)
                self.assertEqual(fetch.call_count,2)
                self.assertEqual(result['market_count'],2)
                self.assertTrue(result['indexer_pagination_exhausted'])
                self.assertEqual(len(json.loads((Path(d)/'x'/'manifest.json').read_text())['ordered_pages']),2)
                urls=[args[0][0].full_url for args in fetch.call_args_list]
                self.assertTrue(all('chain_id=1' in url and 'limit=1000' in url for url in urls))
    def test_network_market_failure_sentinel_one_attempt(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'x'
            with patch.object(b,'api_fetch',side_effect=b.EvidenceError('denied')) as fetch:
                with self.assertRaises(b.EvidenceError):b.fetch_market_directory_bounded(out,approval=True)
                self.assertEqual(fetch.call_count,1)
            self.assertTrue((out/'MANUAL_REVIEW_REQUIRED').exists())
    def test_source_never_authenticates_offline_fixture(self):
        p=b.aggregate_positions([(0,gql([pos()]))])
        self.assertIn('NOT_AUTHENTICATED',p['source'])
        self.assertIsNone(p['NQC_realized_profit'])
    def test_cli_print_does_not_fetch(self):
        with patch.object(b,'api_fetch') as fetch:
            self.assertEqual(b.main(['--print-query']),0)
            fetch.assert_not_called()


if __name__=='__main__':unittest.main()
