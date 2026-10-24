import copy
import unittest
import capture_aave_payment as capture


class PaymentCaptureTests(unittest.TestCase):
    def query(self, *, wrong_chain=False, changed_implementation=False, reorg=False):
        self.calls = []
        plan = capture.prior.plans()[0]
        def run(provider, method, args):
            self.calls.append((provider, method, copy.deepcopy(args)))
            q = dict(jsonrpc='2.0', id=len(self.calls), method=method, params=args)
            if method == 'eth_chainId':
                value = '0x2' if wrong_chain else '0x1'
            elif method == 'eth_getBlockByNumber':
                h = plan['event_anchor'] if args[0] == 'finalized' else next(
                    h for h in [plan['block'], plan['event_anchor']] if hex(h['number']) == args[0])
                value = dict(number=hex(h['number']), hash=h['hash'], parentHash=h['parent_hash'], timestamp=hex(h['timestamp']))
                if reorg and len(self.calls) > 20:
                    value['hash'] = '0x' + 'ab' * 32
            elif method == 'eth_getCode':
                value = '0x60006000'
            else:
                address = capture.USDC if args[0] == capture.ATOKEN else (
                    capture.IMPLEMENTATION if args[1] == capture.IMPLEMENTATION_SLOT else '0x' + '11' * 20)
                if changed_implementation and args[1] == capture.IMPLEMENTATION_SLOT:
                    address = '0x' + '22' * 20
                value = '0x' + '00' * 12 + address[2:]
            return {'request': q, 'response': dict(jsonrpc='2.0', id=q['id'], result=value)}
        return run

    def test_closed_read_scope_refuses_transactions_wrong_slots_and_unpinned_reads(self):
        provider = next(iter(capture.PROVIDERS))
        pin = {'blockHash': capture.prior.plans()[0]['block']['hash'], 'requireCanonical': True}
        for method, args in [('eth_sendRawTransaction', ['0x00']),
                             ('eth_getStorageAt', [capture.USDC, '0x1', pin]),
                             ('eth_getCode', ['0x' + '22' * 20, pin]),
                             ('eth_getCode', [capture.USDC, 'latest']),
                             ('eth_getCode', [capture.USDC, {**pin, 'requireCanonical': False}])]:
            with self.assertRaises(ValueError):
                capture.validate(provider, method, args)

    def test_one_block_records_exactly_28_requests_and_two_provider_code_agreement(self):
        result = capture.capture_one(capture.prior.plans()[0], self.query())
        self.assertEqual(len(result['records']), 28)
        self.assertEqual(set(result['runtimes']), {capture.USDC, capture.IMPLEMENTATION})
        self.assertFalse(result['historical_state_authenticated'])
        self.assertFalse(result['transaction_prestate'])
        self.assertFalse(result['activation_allowed'])
        self.assertEqual(sum(m == 'eth_getCode' for _, m, _ in self.calls), 4)
        self.assertEqual(sum(m == 'eth_getStorageAt' for _, m, _ in self.calls), 6)

    def test_wrong_chain_implementation_and_changed_header_fail_closed(self):
        for options in [dict(wrong_chain=True), dict(changed_implementation=True), dict(reorg=True)]:
            with self.assertRaises(ValueError):
                capture.capture_one(capture.prior.plans()[0], self.query(**options))

    def test_rpc_limit_prevents_any_85th_request(self):
        rpc = capture.Rpc()
        rpc.sequence = capture.MAX_REQUESTS
        with self.assertRaisesRegex(ValueError, 'request budget'):
            rpc(next(iter(capture.PROVIDERS)), 'eth_chainId', [])


if __name__ == '__main__':
    unittest.main()
