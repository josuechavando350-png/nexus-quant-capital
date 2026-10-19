"""Offline transport controls; no fixture is historical chain evidence."""
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import triport_intake as t

KEY = 'synthetic_test_key_not_a_real_credential'


class TransportTests(unittest.TestCase):
    def response(self, data):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = data
        return response

    def test_fixed_blocks_and_header_bindings(self):
        wire = t.wire_plan()
        self.assertEqual(len(wire), 8)
        self.assertEqual(wire[1]['request']['params'], [t.v.PARENT_HASH, False])
        self.assertEqual(wire[5]['request']['params'], [t.v.ANCHOR_HASH, False])
        for i in [2, 3, 4, 6, 7]:
            expected = t.v.PARENT_NUMBER if i < 5 else t.v.ANCHOR_NUMBER
            self.assertEqual(wire[i]['request']['params'][-1], hex(expected))
        self.assertIsInstance(t.intake.plan()[2]['request']['params'][-1], dict)
        self.assertFalse(t.specification()['gates']['commercial_admission'])

    def test_auth_header_and_exact_wire_request(self):
        transport = t.TriportTransport(KEY)
        transport.opener = Mock()
        transport.opener.open.return_value = self.response(b'{"jsonrpc":"2.0","id":3,"result":{}}')
        transport(t.intake.plan()[2])
        req = transport.opener.open.call_args.args[0]
        self.assertEqual(req.full_url, t.ENDPOINT)
        self.assertEqual(req.get_header('X-token'), KEY)
        self.assertEqual(json.loads(req.data), t.wire_plan()[2]['request'])

    def test_unapproved_target_rejected_before_network(self):
        transport = t.TriportTransport(KEY)
        transport.opener = Mock()
        altered = copy.deepcopy(t.intake.plan()[2])
        altered['request']['params'][-1] = 'latest'
        with self.assertRaises(t.v.ValidationError):
            transport(altered)
        transport.opener.open.assert_not_called()

    def test_http_failure_one_attempt_and_no_secret_persistence(self):
        for status in [401, 403, 429]:
            opener = Mock()
            opener.open.side_effect = urllib.error.HTTPError(t.ENDPOINT, status, KEY, {}, io.BytesIO(KEY.encode()))
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                out = Path(directory) / 'result'
                with patch.object(t.urllib.request, 'build_opener', return_value=opener):
                    report = t.collect(KEY, out)
                self.assertEqual(opener.open.call_count, 1)
                self.assertEqual(report['responses_verified'], 0)
                self.assertIn('HTTP ' + str(status), report['reason'])
                self.assertNotIn(KEY, ''.join(p.read_text() for p in out.iterdir()))
                self.assertTrue((out / 'WIRE_REQUESTS.json').exists())

    def test_wrong_chain_and_tampered_parent_stop_before_proof(self):
        header = t.v.read_json(t.v.ROOT / 'inputs/parent-header.json')['result']
        header['stateRoot'] = '0x' + '12' * 32
        scenarios = [
            ([{'jsonrpc': '2.0', 'id': 1, 'result': '0x1'}], 0),
            ([{'jsonrpc': '2.0', 'id': 1, 'result': '0x1237'},
              {'jsonrpc': '2.0', 'id': 2, 'result': header}], 1),
        ]
        for envelopes, verified in scenarios:
            opener = Mock()
            opener.open.side_effect = [self.response(json.dumps(x).encode()) for x in envelopes]
            with self.subTest(verified=verified), tempfile.TemporaryDirectory() as directory:
                with patch.object(t.urllib.request, 'build_opener', return_value=opener):
                    report = t.collect(KEY, Path(directory) / 'result')
                self.assertEqual(report['responses_verified'], verified)
                self.assertEqual(opener.open.call_count, len(envelopes))
                self.assertEqual(report['status'], 'BLOCKED_OR_REJECTED')

    def test_bad_envelopes_and_oversize_rejected(self):
        samples = [b'{"jsonrpc":"2.0","id":1,"id":1,"result":"0x1237"}',
                   b'{"jsonrpc":"2.0","id":2,"result":"0x1237"}',
                   b'{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"secret"}}',
                   b'x' * 257]
        for data in samples:
            transport = t.TriportTransport(KEY)
            transport.opener = Mock()
            transport.opener.open.return_value = self.response(data)
            with self.subTest(data=data[:30]), patch.object(t, 'MAX_RESPONSE', 256), self.assertRaises(ValueError):
                transport(t.intake.plan()[0])

    def test_no_redirect_and_no_invalid_key(self):
        with self.assertRaises(t.v.ValidationError):
            t.intake.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example')
        for key in ['', KEY + '\n', KEY + '\rInjected: value']:
            with self.subTest(key=bool(key)), self.assertRaises(t.v.ValidationError):
                t.TriportTransport(key)


if __name__ == '__main__':
    unittest.main()
