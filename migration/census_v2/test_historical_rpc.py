import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError
import io

from recover_historical_rpc import Recorder, decode_response, PROVIDERS, sha


class HistoricalRpcTests(unittest.TestCase):
    def test_rpc_envelope_rejects_duplicate_keys_wrong_identity_and_errors(self):
        for raw in [b'{"jsonrpc":"2.0","id":1,"id":1,"result":[]}',
                    b'{"jsonrpc":"2.0","id":true,"result":[]}',
                    b'{"jsonrpc":"2.0","id":2,"result":[]}',
                    b'{"jsonrpc":"2.0","id":1,"error":{"code":-1}}']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                decode_response(raw, 1)
        self.assertEqual(decode_response(b'{"jsonrpc":"2.0","id":1,"result":[]}', 1), [])

    def test_forbidden_methods_and_floating_blocks_never_reach_network(self):
        provider = next(p for p in PROVIDERS if p[0] == "drpc")
        def forbidden(*a, **k):
            self.fail("network reached")
        with tempfile.TemporaryDirectory() as temp:
            recorder = Recorder(provider, Path(temp)/"rpc", opener=forbidden)
            for method, params in [("eth_sendRawTransaction", ["0x"]),
                                   ("eth_getBlockByNumber", ["latest", False])]:
                with self.assertRaises(ValueError):
                    recorder(provider[2], method, params)
            self.assertEqual(list((Path(temp)/"rpc").iterdir()), [])

    def test_rate_limit_is_recorded_with_raw_bytes_and_no_retry(self):
        provider = next(p for p in PROVIDERS if p[0] == "drpc")
        calls = []
        body = b'{"error":"rate limited"}'
        def limited(request, **kwargs):
            calls.append(request)
            raise HTTPError(request.full_url, 429, "Too Many Requests", {"Retry-After": "30"}, io.BytesIO(body))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"rpc"
            recorder = Recorder(provider, path, opener=limited)
            with self.assertRaises(HTTPError):
                recorder(provider[2], "eth_chainId", [])
            entry = json.loads((path/"decision-time-ledger.jsonl").read_bytes())
            self.assertEqual(len(calls), 1)
            self.assertEqual(entry["http_status"], 429)
            self.assertEqual(entry["response_sha256"], sha(body))
            self.assertEqual((path/"000001.response.json").read_bytes(), body)
            self.assertFalse(entry["original_decision_time_observation_proven"])
            with self.assertRaises(FileExistsError):
                Recorder(provider, path)

    def test_resume_preserves_receipt_times_rejects_tamper_and_request_drift(self):
        provider = next(p for p in PROVIDERS if p[0] == "drpc")
        body = b'{"jsonrpc":"2.0","id":1,"result":"0x1"}'
        class Response(io.BytesIO):
            status = 200
            headers = {}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = Recorder(provider, root/"first/rpc", opener=lambda *a, **kw: Response(body))
            self.assertEqual(first(provider[2], "eth_chainId", []), "0x1")
            def no_network(*a, **kw):
                self.fail("completed checkpoint repeated network request")
            second = Recorder(provider, root/"second/rpc", opener=no_network, resume=root/"first")
            self.assertEqual(second(provider[2], "eth_chainId", []), "0x1")
            self.assertEqual((root/"first/rpc/decision-time-ledger.jsonl").read_bytes(),
                             (root/"second/rpc/decision-time-ledger.jsonl").read_bytes())
            third = Recorder(provider, root/"third/rpc", opener=no_network, resume=root/"first")
            with self.assertRaisesRegex(ValueError, "order"):
                third(provider[2], "eth_getTransactionReceipt", ["0x123"])
            (root/"first/rpc/000001.response.json").write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "corrupted"):
                Recorder(provider, root/"fourth/rpc", resume=root/"first")


if __name__ == "__main__":
    unittest.main()
