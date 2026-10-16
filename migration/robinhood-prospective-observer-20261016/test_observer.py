import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import read_rpc as rpc
import model
import observer
import audit

POLICY = observer.read(observer.HERE / 'policy.json')
BORROWER = '0x' + '12' * 20


def block_raw(number, timestamp):
    return {'number': hex(number), 'timestamp': hex(timestamp), 'hash': '0x' + f'{number:064x}',
            'parentHash': '0x' + f'{number-1:064x}', 'stateRoot': '0x' + f'{number+100000:064x}', 'baseFeePerGas': '0x1'}


def borrow_event(number):
    return {'address': rpc.MORPHO, 'topics': [rpc.BORROW, rpc.MARKET,
            '0x' + '00' * 12 + BORROWER[2:], '0x' + '00' * 12 + BORROWER[2:]],
            'data': model.encode('0x', 1, 100000000, 10**14), 'removed': False,
            'blockNumber': hex(number), 'blockHash': '0x' + f'{number:064x}',
            'transactionHash': '0x' + 'cd' * 32, 'transactionIndex': '0x1', 'logIndex': '0x0'}


class FakeChain:
    """Explicitly synthetic test transport; no network or profit evidence."""
    def __init__(self, empty=False, healthy=False, jump=1):
        self.height = 9999; self.anchor = None; self.headers = {}
        self.empty, self.healthy, self.jump = empty, healthy, jump
        self.original = observer.read(observer.OLD / 'evidence/provider-capture/08-prestate.json')['result']

    def __call__(self, request):
        method, params = request['method'], request['params']
        if method == 'eth_chainId': result = hex(4663)
        elif method == 'eth_getBlockByNumber':
            if params[0] == 'latest':
                self.height += self.jump if self.anchor else 1
                self.anchor = self.anchor or self.height
                self.headers[self.height] = block_raw(self.height, int(time.time()))
                number = self.height
            else: number = int(params[0], 16)
            if number not in self.headers: self.headers[number] = block_raw(number, int(time.time()))
            result = self.headers[number]
        elif method == 'eth_getLogs':
            f = params[0]; number = self.anchor - 1
            result = [] if self.empty or not int(f['fromBlock'], 16) <= number <= int(f['toBlock'], 16) else [borrow_event(number)]
        elif method == 'eth_getCode': result = '0x' if params[0] in rpc.FIXTURES else self.original[params[0]]['code']
        elif method == 'eth_call':
            selector = params[0]['data'][:10]
            if selector == '0x2c3c9157': values = model.MARKET_PARAMS
            elif selector == '0x5c60e39a': values = [10**9, 10**15, 100000000, 10**14, int(time.time())-1, 0]
            elif selector == '0xa035b1fe': values = [2 * 10**26 if self.healthy else 15 * 10**25]
            elif selector == '0x8c00bf6b': values = [0]
            elif selector == '0x93c52062': values = [0, 10**14, 10**18]
            else: raise AssertionError(selector)
            result = model.encode('0x', *values)
        elif method == 'debug_traceCall':
            result = {'gasUsed': '0x64', 'output': model.encode('0x', 10000000),
                      'beforeEVMTransfers': [{'purpose': 'feePayment', 'from': rpc.ACCOUNT, 'to': None, 'value': '0x64'}],
                      'afterEVMTransfers': [{'purpose': 'gasRefund', 'from': None, 'to': rpc.ACCOUNT, 'value': '0x0'},
                                            {'purpose': 'feeCollection', 'from': None, 'to': '0x' + 'ab'*20, 'value': '0x64'}]}
        else: raise AssertionError(method)
        return rpc.canonical({'jsonrpc': '2.0', 'id': request['id'], 'result': result})


def exercise(folder, **kwargs):
    reader = rpc.Reader(folder, FakeChain(**kwargs))
    journal = observer.Journal(folder)
    with patch('observer.time.sleep'):
        status = observer.run(reader, journal, POLICY, '1' * 40)
    journal.append('stop', {'status': status, 'reason': None, 'requests': reader.count,
                           'broadcasts': 0, 'realized_revenue': False})
    return reader, journal


class ProtocolTests(unittest.TestCase):
    def test_exact_healthy_boundary_and_one_unit_debt(self):
        market = [100, 100000000, 100, 100000000, 1000, 0]
        p = [0, 100000000, 160]
        self.assertFalse(model.screen(p, market, 0, 10**36, 1000, POLICY)['computed_unhealthy'])
        self.assertTrue(model.screen([0, 100000000, 159], market, 0, 10**36, 1000, POLICY)['computed_unhealthy'])

    def test_virtual_share_rounding_and_no_debt(self):
        market = [1000, 1000, 100, 100000001, 1000, 0]
        s = model.screen([0, 1, 100], market, 0, 10**36, 1000, POLICY)
        self.assertEqual(s['debt_usdg_raw'], 1)
        self.assertFalse(model.screen([0, 0, 0], market, 0, 10**36, 1000, POLICY)['screen_candidate'])

    def test_future_accrual_origin_and_overflow_rejected(self):
        with self.assertRaises(rpc.Rejected): model.accrue([100, 1, 1, 1, 1001, 0], 1, 1000)
        with self.assertRaises(rpc.Rejected): model.screen([0, 1, 2**127], [100, 1, 1, 1, 1000, 0], 0, 2**255, 1000, POLICY)

    def test_historical_morpho_debt_and_liquidation_rounding(self):
        trace = observer.read(observer.OLD / 'evidence/provider-capture/07-call-trace.json')['result']
        frames = list(observer.flatten(trace))
        irm = next(f for f in frames if f.get('to', '').lower() == rpc.IRM)
        all_values = model.words('0x' + irm['input'][10:], 11)
        self.assertEqual(all_values[:5], model.MARKET_PARAMS)
        market = all_values[5:]
        rate = model.words(irm['output'], 1)[0]
        oracle = next(f for f in frames if f.get('to', '').lower() == rpc.ORACLE and f.get('input') == '0xa035b1fe')
        price = model.words(oracle['output'], 1)[0]
        s = model.screen([0, 190045154242350, 132629526487103808], market, rate, price, 1789786800, POLICY)
        self.assertTrue(s['computed_unhealthy'])
        assets, shares = model.accrue(market, rate, 1789786800)
        incentive = min(115 * model.WAD // 100, model.WAD**2 // (model.WAD - 3 * model.WAD // 10 * (model.WAD-model.MARKET_PARAMS[4]) // model.WAD))
        repaid_shares = model.up(model.up(model.up(93436250743843184 * price, model.SCALE) * model.WAD, incentive) * (shares+10**6), assets+1)
        self.assertEqual(model.up(repaid_shares*(assets+1), shares+10**6), 194034131)

    def test_size_is_bounded_by_debt_and_policy(self):
        s = model.screen([0, 10**14, 10**18], [10**9, 10**15, 100000000, 10**14, 1000, 0], 0, 15*10**25, 1000, POLICY)
        sizing = model.size(s, 15*10**25, POLICY)
        self.assertLessEqual(sizing['seize_raw'], 10**18 // 4)
        self.assertLessEqual(sizing['predicted_repaid_shares'], s['debt_shares'])
        self.assertLessEqual(sizing['predicted_repay_usdg_raw'], sizing['max_repay_usdg_raw'])

    def test_cohort_rejects_future_removed_and_duplicate_events(self):
        anchor = rpc.header(block_raw(10000, 1000))
        for logs in [[borrow_event(10001)], [{**borrow_event(9999), 'removed': True}], [borrow_event(9999)]*2]:
            with self.assertRaises(rpc.Rejected): observer.enrollment(logs, 9000, anchor, POLICY)

    def test_cohort_selection_does_not_read_health(self):
        cohort = observer.enrollment([borrow_event(9999)], 9000, rpc.header(block_raw(10000, 1000)), POLICY)
        self.assertEqual(cohort['addresses'], [BORROWER])
        self.assertFalse(cohort['selection_uses_health_or_liquidation_outcome'])

    def test_economics_does_not_turn_simulation_into_capture(self):
        result = observer.economic_hypothesis(32060665, POLICY)
        self.assertFalse(result['capture_rate_measured'])
        self.assertFalse(result['realized_revenue'])
        self.assertEqual(result['capture_probability_assumed'], '0.05')


class EndToEndTests(unittest.TestCase):
    def test_synthetic_candidate_and_exact_payload_survival(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'run'; reader, _ = exercise(folder)
            report = audit.audit(folder)
            self.assertEqual(report['borrower_state_observations'], 3)
            self.assertEqual(report['successful_route_simulations'], 6)
            self.assertEqual(report['outcomes'][0]['status'], 'EXACT_PAYLOAD_RECHECK')
            self.assertEqual(report['outcomes'][-1]['status'], 'RIGHT_CENSORED_RUN_ENDED')
            self.assertFalse(report['production_authorization'])
            self.assertLessEqual(reader.count, 90)

    def test_empty_cohort_is_not_three_no_opportunity_periods(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'run'; exercise(folder, empty=True)
            report = audit.audit(folder)
            self.assertEqual(report['empty_cohort_rounds'], 3)
            self.assertEqual(report['nonempty_cohort_rounds_without_signal'], 0)
            self.assertFalse(report['complete_with_nonempty_cohort'])
            self.assertIsNone(report['realized_capture_rate'])

    def test_healthy_cohort_records_all_rejections(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'run'; exercise(folder, healthy=True)
            report = audit.audit(folder)
            self.assertEqual(report['nonempty_cohort_rounds_without_signal'], 3)
            self.assertEqual(report['screen_candidate_observations'], 0)

    def test_skipped_blocks_do_not_become_success_or_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'run'; exercise(folder, jump=10)
            report = audit.audit(folder)
            outcome = report['outcomes'][0]
            self.assertEqual(outcome['status'], 'DEADLINE_PASSED_BEFORE_NEXT_OBSERVED_HEAD')
            self.assertIsNone(outcome['survival_at_intermediate_blocks'])
            self.assertEqual(outcome['unobserved_intermediate_blocks'], 9)

    def test_journal_mutation_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'run'; exercise(folder, empty=True)
            path = folder / 'journal.jsonl'
            path.write_text(path.read_text().replace('"broadcasts":0', '"broadcasts":1'))
            with self.assertRaisesRegex(rpc.Rejected, 'HASH_CHAIN'): audit.audit(folder)

    def test_response_mutation_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'run'; reader, _ = exercise(folder, empty=True)
            path = folder / reader.records[0]['response_file']
            path.write_bytes(path.read_bytes() + b' ')
            with self.assertRaisesRegex(rpc.Rejected, 'DIGEST'): audit.audit(folder)


if __name__ == '__main__': unittest.main()
