"""Synthetic fixtures only. No fixture is evidence of a real opportunity."""
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from common import (HERE, need, canonical, qty, header, MORPHO, MARKET, BORROW, ORACLE,
                    IRM, MARKET_PARAMS, encode, Journal, pin)
from rpc_batch import Reader, decode, validate
import registry
from collect import run, update_registry, derive
from audit_capture import audit

POLICY = json.loads((HERE / 'policy.json').read_text())
A, B = '0x' + '1' * 40, '0x' + '2' * 40


def raw_header(n, stamp=1700000000):
    return {'number': hex(n), 'timestamp': hex(stamp), 'hash': '0x' + f'{n:064x}',
            'parentHash': '0x' + f'{n-1:064x}', 'stateRoot': '0x' + 'a' * 64, 'baseFeePerGas': hex(20008000)}


def event(n, address=A, index=0):
    return {'address': MORPHO, 'topics': [BORROW, MARKET, '0x' + '0' * 24 + address[2:], '0x' + '0' * 24 + address[2:]],
            'data': encode('0x', int(A, 16), 1000000, 1000000), 'removed': False,
            'blockNumber': hex(n), 'blockHash': raw_header(n)['hash'], 'transactionHash': '0x' + 'd' * 64,
            'transactionIndex': '0x0', 'logIndex': hex(index)}


def segment(state, start, end, logs):
    return registry.append(state, start, header(raw_header(start - 1)), header(raw_header(end)), logs,
                           [header(raw_header(n)) for n in sorted({qty(e['blockNumber']) for e in logs})], POLICY)


class FakeChain:
    def __init__(self):
        self.head = 1000000
        self.timestamp = int(time.time()) + 1
        self.original = json.loads((HERE.parent / 'robinhood-real-state-replay-20261016/evidence/provider-capture/08-prestate.json').read_text())['result']
        self.events = [event(800000, A), event(800001, B)]
        self.market = [400000000, 4000000, 300000000, 3000000, self.timestamp - 60, 0]

    def answer(self, request):
        method, params = request['method'], request['params']
        if method == 'eth_chainId': return hex(4663)
        if method == 'eth_getBlockByNumber':
            if params[0] == 'latest': self.head += 100
            return raw_header(self.head if params[0] == 'latest' else qty(params[0]), self.timestamp)
        if method == 'eth_getLogs':
            f = params[0]
            return [e for e in self.events if qty(f['fromBlock']) <= qty(e['blockNumber']) <= qty(f['toBlock'])]
        if method == 'eth_getCode': return self.original[params[0]]['code']
        if method == 'eth_call':
            tx = params[0]
            if tx['to'] == ORACLE: return encode('0x', 10**36)
            if tx['to'] == IRM: return encode('0x', 0)
            if tx['data'].startswith('0x5c60e39a'): return encode('0x', *self.market)
            if tx['data'].startswith('0x2c3c9157'): return encode('0x', *MARKET_PARAMS)
            if tx['data'].startswith('0x93c52062'): return encode('0x', 0, 1000000, 10**12)
        raise AssertionError('Unexpected synthetic request')

    def __call__(self, payload):
        batch = type(payload) is list
        values = payload if batch else [payload]
        replies = [{'jsonrpc': '2.0', 'id': q['id'], 'result': self.answer(q)} for q in values]
        return canonical(list(reversed(replies)) if batch else replies[0])


class RegistryTests(unittest.TestCase):
    def test_contiguous_append_persists_old_accounts(self):
        state = segment(registry.new(10), 10, 11, [event(10)])
        state = segment(state, 12, 13, [event(13, B)])
        self.assertEqual(registry.freeze(state, 13, POLICY)['addresses'], [A, B])

    def test_gap_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'REGISTRY_GAP'):
            segment(registry.new(10), 11, 12, [])

    def test_overlapping_retry_does_not_duplicate(self):
        state = segment(registry.new(10), 10, 11, [event(10)])
        with self.assertRaisesRegex(ValueError, 'REGISTRY_GAP'):
            segment(state, 10, 11, [event(10)])

    def test_unfinished_target_cannot_freeze(self):
        state = segment(registry.new(10), 10, 11, [event(10)])
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE'):
            registry.freeze(state, 12, POLICY)

    def test_invalidated_registry_cannot_resume_or_freeze(self):
        state = segment(registry.new(10), 10, 11, [event(10)])
        invalid = registry.invalidate(state, header(raw_header(12)))
        with self.assertRaises(ValueError): registry.freeze(invalid, 11, POLICY)
        with self.assertRaises(ValueError): segment(invalid, 12, 13, [])
        self.assertEqual(invalid['segments'], state['segments'])

    def test_checkpoint_reorg_invalidates_copy(self):
        state = segment(registry.new(10), 10, 11, [event(10)])
        def transport(q): return canonical({'jsonrpc': '2.0', 'id': q['id'], 'result': raw_header(11, 1700000010)})
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'run'; reader = Reader(folder, transport)
            with self.assertRaisesRegex(ValueError, 'REORG'):
                update_registry(reader, Journal(folder), POLICY, folder / 'registry.json', state, header(raw_header(12)))
            self.assertEqual(registry.load(folder / 'registry.json', POLICY)['status'], 'invalidated')
            self.assertEqual(state['status'], 'valid_prefix')

    def test_capacity_overflow_never_trims(self):
        state = segment(registry.new(10), 10, 11, [event(10), event(11, B)])
        policy = dict(POLICY, max_borrowers=1)
        with self.assertRaises(ValueError): registry.freeze(state, 11, policy)

    def test_wrong_market_removed_and_duplicate_events_rejected(self):
        for mutation in ['removed', 'market', 'duplicate']:
            logs = [event(10)]
            if mutation == 'removed': logs[0]['removed'] = True
            if mutation == 'market': logs[0]['topics'][1] = '0x' + '0' * 64
            if mutation == 'duplicate': logs.append(copy.deepcopy(logs[0]))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                segment(registry.new(10), 10, 11, logs)

    def test_event_header_hash_must_match(self):
        bad = event(10); bad['blockHash'] = raw_header(99)['hash']
        with self.assertRaisesRegex(ValueError, 'EVENT_HEADER_HASH'):
            segment(registry.new(10), 10, 11, [bad])

    def test_persistence_hash_detects_corruption(self):
        state = segment(registry.new(10), 10, 11, [event(10)])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'registry.json'; registry.save(path, state)
            self.assertEqual(registry.load(path, POLICY), state)
            value = json.loads(path.read_text()); value['state']['through_block'] += 1
            path.write_bytes(canonical(value))
            with self.assertRaisesRegex(ValueError, 'REGISTRY_HASH'): registry.load(path, POLICY)


class RpcTests(unittest.TestCase):
    def test_batch_out_of_order_id_matching(self):
        requests = [{'id': 1}, {'id': 2}]
        raw = canonical([{'jsonrpc': '2.0', 'id': 2, 'result': 'b'}, {'jsonrpc': '2.0', 'id': 1, 'result': 'a'}])
        self.assertEqual(decode(requests, raw), ['a', 'b'])

    def test_missing_duplicate_or_unknown_id_rejected(self):
        for ids in [[1], [1, 1], [1, 3]]:
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                decode([{'id': 1}, {'id': 2}], canonical([{'jsonrpc': '2.0', 'id': n, 'result': 0} for n in ids]))

    def test_partial_batch_error_stops_reader(self):
        def transport(q):
            return canonical([{'jsonrpc': '2.0', 'id': q[0]['id'], 'result': '0x1237'},
                              {'jsonrpc': '2.0', 'id': q[1]['id'], 'error': {'code': -32000, 'message': 'fixture error'}}])
        with tempfile.TemporaryDirectory() as tmp:
            r = Reader(Path(tmp) / 'run', transport)
            with self.assertRaises(ValueError): r.group([('eth_chainId', [])] * 2, 'error')
            self.assertTrue(r.stopped)
            with self.assertRaises(ValueError): r.call('eth_chainId', [], 'no-retry')
            self.assertEqual(r.count, 2)

    def test_each_batch_element_counts_against_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Reader(Path(tmp) / 'run', FakeChain(), max_requests=3)
            with self.assertRaises(ValueError): r.group([('eth_chainId', [])] * 4, 'too-many')
            self.assertEqual(r.count, 0)

    def test_send_trace_overrides_and_noncanonical_calls_rejected(self):
        for method, params in [('eth_sendRawTransaction', ['0x']), ('debug_traceCall', []),
                               ('eth_call', [{'to': MORPHO, 'data': '0x5c60e39a' + MARKET[2:]}, 'latest'])]:
            with self.subTest(method=method), self.assertRaises(ValueError): validate(method, params)

    def test_log_range_and_target_limits(self):
        f = {'address': MORPHO, 'topics': [BORROW, MARKET], 'fromBlock': '0x1', 'toBlock': hex(10000)}
        validate('eth_getLogs', [f])
        f['toBlock'] = hex(10001)
        with self.assertRaises(ValueError): validate('eth_getLogs', [f])


class CoverageTests(unittest.TestCase):
    def calculate(self, positions, total=3000000):
        block = header(raw_header(100))
        market = [400000000, 4000000, 300000000, total, block['timestamp'], 0]
        raw = [encode('0x', *market), encode('0x', 10**36)] + [encode('0x', *p) for p in positions]
        return derive(block, [A, B][:len(positions)], raw, encode('0x', 0), POLICY)

    def test_partial_share_coverage_explicit(self):
        state = self.calculate([[0, 1000000, 10**12]])
        self.assertEqual(state['coverage']['debt_share_coverage_bps_floor'], 3333)
        self.assertEqual(state['coverage']['missing_borrow_shares'], 2000000)
        self.assertIsNone(state['profitable_opportunities'])

    def test_full_current_debt_coverage_is_not_full_history(self):
        state = self.calculate([[0, 3000000, 10**12]])
        self.assertTrue(state['coverage']['all_positive_debt_shares_accounted_at_this_block'])
        self.assertFalse(state['coverage']['historical_event_coverage_complete'])

    def test_empty_cohort_with_debt_is_zero_coverage(self):
        state = self.calculate([])
        self.assertEqual(state['coverage']['debt_share_coverage_bps_floor'], 0)
        self.assertIsNone(state['realized_profit'])

    def test_zero_debt_has_no_percentage(self):
        state = self.calculate([], total=0)
        self.assertIsNone(state['coverage']['debt_share_coverage_bps_floor'])

    def test_sum_over_total_rejected(self):
        with self.assertRaisesRegex(ValueError, 'COHORT_DEBT_SHARES'):
            self.calculate([[0, 2000000, 1], [0, 2000000, 1]])

    def test_unhealthy_is_not_profitability(self):
        state = self.calculate([[0, 1000000, 1]])
        self.assertEqual(state['computed_unhealthy_count'], 1)
        self.assertIsNone(state['profitable_opportunities'])


class EndToEndTests(unittest.TestCase):
    def test_resumption_keeps_prior_accounts_and_raw_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeChain()
            first = Path(tmp) / 'first'; r1 = Reader(first, fake)
            with patch('builtins.print'):
                run(r1, Journal(first), POLICY, '1' * 40, first / 'registry.json')
            before = (first / 'registry.json').read_bytes()
            state = registry.load(first / 'registry.json', POLICY)
            second = Path(tmp) / 'second'; r2 = Reader(second, fake)
            with patch('builtins.print'):
                run(r2, Journal(second), POLICY, '1' * 40, second / 'registry.json', state)
            result = audit(second)
            self.assertEqual(result['cohort']['addresses'], [A, B])
            self.assertGreater(result['registry']['through_block'], state['through_block'])
            self.assertEqual((first / 'registry.json').read_bytes(), before)

    def test_synthetic_run_reconstructs_raw_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'run'; reader = Reader(folder, FakeChain())
            with patch('builtins.print'):
                run(reader, Journal(folder), POLICY, '1' * 40, folder / 'registry.json')
            result = audit(folder)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(result['cohort']['addresses'], [A, B])
            self.assertEqual(result['snapshots'][0]['state']['coverage']['debt_share_coverage_bps_floor'], 6666)
            self.assertEqual(len(result['snapshots']), 4)
            self.assertTrue(result['comparisons'][0]['exact_state_parity'])
            raw = folder / reader.records[0]['response_file']; raw.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'RAW_RESPONSE_HASH'): audit(folder)

    def test_empty_synthetic_cohort_does_not_become_no_profit(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = FakeChain(); fake.events = []
            folder = Path(tmp) / 'run'; reader = Reader(folder, fake)
            with patch('builtins.print'):
                run(reader, Journal(folder), POLICY, '1' * 40, folder / 'registry.json')
            result = audit(folder)
            self.assertEqual(result['cohort']['addresses'], [])
            self.assertIsNone(result['realized_capture_rate'])


if __name__ == '__main__':
    unittest.main()
