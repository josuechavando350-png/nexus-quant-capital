import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import batch


def row(n, market=None):
    return {'market': {'marketId': '0x' + f'{n % 37 if market is None else market:064x}'},
            'user': {'address': '0x' + f'{n+1:040x}'}}


def page(items, total=None, count=None):
    return json.dumps({'data': {'marketPositions': {'items': items, 'pageInfo': {
        'count': len(items) if count is None else count, 'countTotal': total}}}}).encode()


def source(pages):
    it = iter(pages)
    def fetch(skip, first):
        try:
            return next(it)
        except StopIteration as exc:
            raise batch.BatchError('fixture ended') from exc
    return fetch


class BatchTests(unittest.TestCase):
    def test_global_query(self):
        p = json.loads(batch.request_body())
        self.assertEqual(p['variables']['chainIds'], [1])
        self.assertEqual(p['variables']['first'], 1000)
        self.assertIn('marketListed: true', p['query'])
        self.assertNotIn('marketUniqueKey_in', p['query'])
        self.assertNotIn('mutation', p['query'])

    def test_ten_thousand_across_37_markets(self):
        offsets = []
        def fetch(skip, first):
            offsets.append(skip)
            return page([row(n) for n in range(skip, skip+first)], 10000)
        r = batch.collect(fetch)
        self.assertEqual(r['unique_pairs'], 10000)
        self.assertEqual(r['markets_with_returned_candidates'], 37)
        self.assertEqual(offsets, list(range(0, 10000, 1000)))
        self.assertTrue(r['enumeration_without_detected_anomaly'])
        self.assertFalse(r['point_in_time_complete'])
        self.assertEqual(r['evidence_kind'], 'OFFLINE_TEST')

    def test_more_than_three_markets(self):
        r = batch.collect(source([page([row(n) for n in range(12)], 12)]))
        self.assertEqual(r['markets_with_returned_candidates'], 12)

    def test_non_multiple_last_page(self):
        r = batch.collect(source([page([row(0), row(1)], 3), page([row(2)], 3)]), first=2)
        self.assertEqual(r['unique_pairs'], 3)
        self.assertTrue(r['reported_pagination_exhausted'])

    def test_stable_total_not_canonical(self):
        r = batch.collect(source([page([row(0)], 1)]))
        self.assertTrue(r['reported_pagination_exhausted'])
        self.assertFalse(r['point_in_time_complete'])
        self.assertIsNone(r['total_markets_on_ethereum'])

    def test_empty_success_not_error(self):
        r = batch.collect(source([page([], 0)]))
        self.assertEqual(r['stop_reason'], 'REPORTED_TOTAL_REACHED')
        self.assertTrue(r['enumeration_without_detected_anomaly'])

    def test_empty_but_nonzero_total(self):
        r = batch.collect(source([page([], 15)]))
        self.assertEqual(r['stop_reason'], 'SHORT_PAGE_BEFORE_REPORTED_TOTAL')
        self.assertFalse(r['reported_pagination_exhausted'])

    def test_unknown_total_short_page(self):
        r = batch.collect(source([page([row(0)])]), first=2)
        self.assertEqual(r['stop_reason'], 'PARTIAL_PAGE_WITHOUT_TOTAL')
        self.assertFalse(r['point_in_time_complete'])

    def test_page_cap_incomplete(self):
        r = batch.collect(source([page([row(0), row(1)], 4)]), first=2, max_pages=1)
        self.assertEqual(r['stop_reason'], 'PAGE_CAP')
        self.assertFalse(r['reported_pagination_exhausted'])

    def test_duplicates_do_not_inflate(self):
        r = batch.collect(source([page([row(0), row(1)], 4), page([row(1), row(2)], 4)]), first=2)
        self.assertEqual(r['unique_pairs'], 3)
        self.assertEqual(r['duplicate_pairs'], 1)
        self.assertFalse(r['enumeration_without_detected_anomaly'])

    def test_malformed_row_visible(self):
        r = batch.collect(source([page([row(0), {'bad': 'row'}], 2)]))
        self.assertEqual(r['malformed_rows'], 1)
        self.assertEqual(r['unique_pairs'], 1)
        self.assertFalse(r['enumeration_without_detected_anomaly'])

    def test_changing_total_visible(self):
        r = batch.collect(source([page([row(0), row(1)], 3), page([row(2), row(3)], 4)]), first=2)
        self.assertTrue(r['source_total_changed'])
        self.assertFalse(r['enumeration_without_detected_anomaly'])

    def test_repeated_page_stops(self):
        p = page([row(0), row(1)], 10)
        r = batch.collect(source([p, p]), first=2)
        self.assertEqual(r['pages_attempted'], 2)
        self.assertEqual(r['pages_validated'], 1)
        self.assertIn('repeated page', r['error'])

    def test_oversized_page_rejected(self):
        r = batch.collect(source([page([row(0), row(1)], 2)]), first=1)
        self.assertEqual(r['pages_validated'], 0)
        self.assertIn('page size', r['error'])

    def test_bad_count(self):
        r = batch.collect(source([page([row(0)], 1, count=0)]))
        self.assertIn('count does not match', r['error'])

    def test_count_total_smaller_than_rows(self):
        r = batch.collect(source([page([row(0), row(1)], 1)]))
        self.assertEqual(r['stop_reason'], 'COUNT_TOTAL_INCONSISTENT')
        self.assertFalse(r['enumeration_without_detected_anomaly'])

    def test_graphql_error_not_empty_success(self):
        r = batch.collect(source([b'{"errors":[{"message":"failed"}]}']))
        self.assertEqual(r['stop_reason'], 'READ_OR_SCHEMA_FAILURE')
        self.assertFalse(r['reported_pagination_exhausted'])

    def test_null_data_is_reported(self):
        r = batch.collect(source([b'{"data":null}']))
        self.assertIn('data object', r['error'])

    def test_duplicate_json_keys_rejected(self):
        r = batch.collect(source([b'{"data":{},"data":{}}']))
        self.assertIn('duplicate JSON', r['error'])

    def test_byte_cap(self):
        r = batch.collect(source([b'x' * (batch.MAX_BODY+1)]))
        self.assertIn('byte cap', r['error'])

    def test_invalid_types_and_caps(self):
        for first in (0, 1001, True, '10', 1.5):
            with self.subTest(first=first), self.assertRaises(batch.BatchError):
                batch.collect(None, first=first)
        for maximum in (0, 11, True, 1.5):
            with self.subTest(maximum=maximum), self.assertRaises(batch.BatchError):
                batch.collect(None, max_pages=maximum)

    def test_network_failure_stops_once(self):
        calls = []
        def fail(skip, first):
            calls.append(skip)
            raise OSError('DNS failed')
        r = batch.collect(fail)
        self.assertEqual(calls, [0])
        self.assertEqual(r['pages_validated'], 0)
        self.assertFalse(r['enumeration_without_detected_anomaly'])

    def test_failure_after_first_page_keeps_partial(self):
        r = batch.collect(source([page([row(0)], 2)]), first=1)
        self.assertEqual(r['unique_pairs'], 1)
        self.assertEqual(r['stop_reason'], 'READ_OR_SCHEMA_FAILURE')

    def test_never_manufactures_profit(self):
        r = batch.collect(source([page([row(0)], 1)]))
        self.assertFalse(r['commercial_admission'])
        self.assertFalse(r['canary_enabled'])
        self.assertEqual(r['rpc_requests'], 0)
        self.assertIsNone(r['nqc_realized_profit'])
        self.assertIsNone(r['candidates'][0]['onchain_eligible'])
        self.assertIsNone(r['candidates'][0]['net_profit'])

    def test_hold_prevents_network(self):
        with tempfile.TemporaryDirectory() as directory:
            hold = Path(directory)/'hold.json'
            hold.write_text('{}')
            with patch.object(batch, 'HOLD', hold), patch('urllib.request.build_opener') as opener:
                with self.assertRaises(batch.BatchError):
                    batch.live_fetcher(Path(directory)/'out')
                opener.assert_not_called()

    def test_no_redirect(self):
        with self.assertRaises(batch.BatchError):
            batch.NoRedirect().redirect_request(None, None, 302, None, None, 'https://other')

    def test_plan_mode_is_offline(self):
        with patch('urllib.request.build_opener') as opener, patch('sys.stdout', io.StringIO()):
            self.assertEqual(batch.main(['--plan']), 0)
            opener.assert_not_called()

    def test_identity_normalizes_case_without_symbol_inference(self):
        r = row(14)
        r['market']['marketId'] = '0x' + 'A'*64
        r['user']['address'] = '0x' + 'B'*40
        self.assertEqual(batch.identity(r), ('0x'+'a'*64, '0x'+'b'*40))


if __name__ == '__main__':
    unittest.main()
