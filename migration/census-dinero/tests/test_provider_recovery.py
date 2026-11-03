"""Regresiones de los fallos retenidos de rango, cuota y prefijos incompletos."""

import json
import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from census_dinero import sonda
from census_dinero.rpc import LogQueryInterrupted, Rpc, RpcError
from test_census import make_collector, no_sleep
from test_tramos import error
import fakechain as fc


class TestProbeRecovery(unittest.TestCase):
    def probe(self, behavior, end=20_000):
        seen, pauses = [], []

        def transport(url, payload, timeout):
            if payload['method'] == 'eth_blockNumber':
                return {'result': hex(end)}
            self.assertEqual(payload['method'], 'eth_getLogs')
            f = payload['params'][0]
            span = int(f['toBlock'], 16) - int(f['fromBlock'], 16) + 1
            seen.append(span)
            return behavior(payload, span, len(seen))

        rpc = Rpc(['https://fake'], transport=transport, sleep=pauses.append, rps=0)
        result = sonda.probe_provider(rpc, rpc.urls[0], {
            'end': end, 'log_topics': [None], 'log_address': fc.POOLX, 'max_span': end + 1})
        sonda.apply(rpc, [result], list(rpc.urls))
        return rpc, result, seen, pauses

    def test_flare_thirty_block_limit_is_usable(self):
        rpc, r, seen, _ = self.probe(lambda p, n, k: {'result': []} if n <= 30 else
                                     error(p, 'requested too many blocks, maximum is set to 30'))
        self.assertEqual(r['getlogs_max'], 30)
        self.assertEqual(r['getlogs_status'], 'supported')
        self.assertFalse(rpc.dead_for_all('eth_getLogs'))
        self.assertEqual(rpc.get_logs(fc.POOLX, [None], 1, 65), [])
        self.assertEqual(seen[-3:], [30, 30, 5])

    def test_http_413_does_not_discard_a_small_range_provider(self):
        def behavior(p, n, k):
            if n > 100:
                raise RpcError('HTTP 413 en fake', code=413)
            return {'result': []}
        rpc, r, _, _ = self.probe(behavior)
        self.assertEqual(r['getlogs_max'], 100)
        self.assertFalse(rpc.dead_for_all('eth_getLogs'))

    def test_not_supported_range_is_not_an_unsupported_method(self):
        rpc, r, _, _ = self.probe(lambda p, n, k: {'result': []} if n <= 10 else
                                 error(p, 'ranges over 10 blocks are not supported'))
        self.assertEqual(r['getlogs_max'], 10)
        self.assertFalse(rpc.dead_for_all('eth_getLogs'))

    def test_transient_first_failure_retries_same_range_once(self):
        rpc, r, seen, pauses = self.probe(lambda p, n, k: error(p, 'rate limited') if k == 1 else
                                         {'result': []})
        self.assertEqual(seen, [1, 1])
        self.assertEqual(pauses, [2])
        self.assertEqual(r['getlogs_status'], 'supported')
        self.assertEqual(rpc.log_limit['https://fake'], 1)

    def test_persistent_rate_limit_remains_unverified(self):
        rpc, r, seen, pauses = self.probe(lambda p, n, k: error(p, 'HTTP 429'))
        self.assertEqual((seen, pauses), ([1, 1], [2]))
        self.assertEqual(r['getlogs_status'], 'unverified')
        self.assertFalse(rpc.dead_for_all('eth_getLogs'))

    def test_pruned_history_does_not_establish_method_absence(self):
        rpc, r, seen, _ = self.probe(lambda p, n, k: error(p, 'requested height has been pruned'))
        self.assertEqual(seen, [1])
        self.assertEqual(r['getlogs_status'], 'unverified')
        self.assertFalse(rpc.dead_for_all('eth_getLogs'))

    def test_explicit_method_absence_still_disables_method(self):
        rpc, r, seen, _ = self.probe(lambda p, n, k: error(p, 'Method not found', -32601))
        self.assertEqual(seen, [1])
        self.assertEqual(r['getlogs_status'], 'unavailable')
        self.assertTrue(rpc.dead_for_all('eth_getLogs'))

    def test_null_logs_do_not_count_as_a_successful_probe(self):
        rpc, r, _, _ = self.probe(lambda p, n, k: {'result': None})
        self.assertEqual(r['getlogs_max'], 0)
        self.assertEqual(r['getlogs_status'], 'unverified')
        self.assertFalse(rpc.dead_for_all('eth_getLogs'))

    def test_reported_limit_is_the_actual_span_for_a_young_chain(self):
        _, r, seen, _ = self.probe(lambda p, n, k: {'result': []}, end=4)
        self.assertEqual(r['getlogs_max'], 5)
        self.assertEqual(seen, [1, 5])


class TestRetainedLogPrefix(unittest.TestCase):
    def broken_rpc(self, fail_at):
        chain = fc.FakeChain()
        def transport(url, payload, timeout):
            if payload['method'] == 'eth_getLogs':
                start = int(payload['params'][0]['fromBlock'], 16)
                if start >= fail_at:
                    return error(payload, 'invalid block range')
            return chain(url, payload, timeout)
        return Rpc(['https://fake'], transport=transport, sleep=no_sleep, rps=0,
                   log_chunk=5, max_log_chunk=5)

    def test_partial_logs_survive_a_later_failure(self):
        rpc = self.broken_rpc(19994)
        with self.assertRaises(LogQueryInterrupted) as cm:
            rpc.get_logs(None, [None], 19989, 20003)
        self.assertEqual(cm.exception.next_block, 19994)
        self.assertTrue(cm.exception.logs)
        self.assertTrue(all(int(x['blockNumber'], 16) < 19994 for x in cm.exception.logs))
        self.assertIsInstance(cm.exception, RpcError)

    def test_collector_saves_prefix_and_never_certifies_full_window(self):
        col, _ = make_collector()
        col.rpc = self.broken_rpc(19994)
        records = col.fetch_liquidations(19989, 20003)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['block'], 19990)
        self.assertEqual(col.events_cover, 19993)
        self.assertTrue(col.fatal)
        with tempfile.TemporaryDirectory() as tmp:
            meta = col.write(tmp, records, {}, {'start_block': 19989, 'end_block': 20003}, time.time())
            self.assertFalse(meta['events_complete'])
            self.assertEqual(meta['events'], 1)
            self.assertEqual(len(meta['log_interruptions']), 2)
            with open(os.path.join(tmp, 'liquidaciones.jsonl')) as fh:
                self.assertEqual(json.loads(fh.readline())['block'], 19990)

    def test_failure_in_first_chunk_has_no_false_coverage(self):
        col, _ = make_collector()
        col.rpc = self.broken_rpc(19989)
        self.assertEqual(col.fetch_liquidations(19989, 20003), [])
        self.assertEqual(col.events_cover, 19988)
        self.assertTrue(col.fatal)


if __name__ == '__main__':
    unittest.main()
