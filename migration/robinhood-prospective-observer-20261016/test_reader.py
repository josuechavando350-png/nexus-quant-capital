import json
from pathlib import Path
import tempfile
import unittest
import read_rpc as rpc

PIN = {'blockHash': '0x' + 'ab' * 32, 'requireCanonical': True}


class ReaderTests(unittest.TestCase):
    def test_mutating_and_unbounded_methods_rejected(self):
        for name in ['eth_sendTransaction', 'eth_sendRawTransaction', 'eth_sign', 'eth_subscribe', 'debug_traceTransaction']:
            with self.assertRaises(rpc.Rejected): rpc.validate(name, [])

    def test_unpinned_calls_and_extra_overrides_rejected(self):
        tx = {'to': rpc.ORACLE, 'data': '0xa035b1fe'}
        for params in [[tx, 'latest'], [tx, PIN, {}], [tx, {**PIN, 'requireCanonical': False}]]:
            with self.assertRaises(rpc.Rejected): rpc.validate('eth_call', params)

    def test_borrow_scope_and_range_bound(self):
        item = {'address': rpc.MORPHO, 'topics': [rpc.BORROW, rpc.MARKET], 'fromBlock': '0x1', 'toBlock': '0x200'}
        rpc.validate('eth_getLogs', [item])
        with self.assertRaises(rpc.Rejected): rpc.validate('eth_getLogs', [{**item, 'toBlock': '0x201'}])
        with self.assertRaises(rpc.Rejected): rpc.validate('eth_getLogs', [{**item, 'topics': []}])

    def test_transport_error_stops_without_retry(self):
        count = []
        def transport(request):
            count.append(request)
            return rpc.canonical({'jsonrpc': '2.0', 'id': request['id'], 'error': {'code': -32005, 'message': 'limit'}})
        with tempfile.TemporaryDirectory() as temp:
            reader = rpc.Reader(Path(temp) / 'capture', transport)
            with self.assertRaises(rpc.RpcFailure): reader.call('eth_chainId', [], 'first')
            with self.assertRaises(rpc.Rejected): reader.call('eth_chainId', [], 'second')
            self.assertEqual(len(count), 1)
            self.assertTrue((reader.folder / 'requests.json').exists())

    def test_capture_before_analysis_and_finite_budget(self):
        transport = lambda request: rpc.canonical({'jsonrpc': '2.0', 'id': request['id'], 'result': '0x1237'})
        with tempfile.TemporaryDirectory() as temp:
            reader = rpc.Reader(Path(temp) / 'capture', transport, limit=1)
            self.assertEqual(rpc.qty(reader.call('eth_chainId', [], 'chain')), 4663)
            self.assertGreaterEqual(reader.records[0]['received_ns'], reader.records[0]['started_ns'])
            with self.assertRaises(rpc.Rejected): reader.call('eth_chainId', [], 'second')

    def test_stale_header_cannot_be_called_prospective(self):
        raw = {'number': '0x100', 'timestamp': '0x3e8', 'hash': '0x' + 'ab' * 32,
               'parentHash': '0x' + 'cd' * 32, 'stateRoot': '0x' + 'ef' * 32, 'baseFeePerGas': '0x1'}
        self.assertEqual(rpc.header(raw, 1030 * 10**9)['timestamp'], 1000)
        with self.assertRaisesRegex(rpc.Rejected, 'STALE'): rpc.header(raw, 1031 * 10**9)

    def test_rpc_id_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            reader = rpc.Reader(Path(temp) / 'capture', lambda _: rpc.canonical({'jsonrpc': '2.0', 'id': 99, 'result': '0x1'}))
            with self.assertRaisesRegex(rpc.Rejected, 'ENVELOPE'): reader.call('eth_chainId', [], 'chain')
            self.assertTrue(reader.stopped)

    def test_redirect_is_not_followed(self):
        with self.assertRaisesRegex(rpc.Rejected, 'REDIRECT'): rpc.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com')


if __name__ == '__main__': unittest.main()
