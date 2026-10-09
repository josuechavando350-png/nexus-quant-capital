import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from rpc_witness import HASHES, PREVIOUS, Witness, canonical, sha, upstream_params


class ReadOnlyWitnessTests(unittest.TestCase):
    def test_writes_latest_and_foreign_blocks_are_rejected(self):
        for method, params in [
            ("eth_sendRawTransaction", ["0x00"]),
            ("eth_sendTransaction", [{}]),
            ("eth_getBalance", ["0x" + "11" * 20, "latest"]),
            ("eth_getCode", ["0x" + "11" * 20, hex(PREVIOUS + 1)]),
            ("eth_getBlockByNumber", [hex(PREVIOUS), True]),
        ]:
            with self.subTest(method=method, params=params), self.assertRaises(ValueError):
                upstream_params(method, params)

    def test_state_reads_use_canonical_hash(self):
        p = ["0x" + "11" * 20, "0x0", hex(PREVIOUS)]
        out = upstream_params("eth_getStorageAt", p)
        self.assertEqual(out[-1], {"blockHash": HASHES[PREVIOUS], "requireCanonical": True})
        self.assertEqual(p[-1], hex(PREVIOUS))

    def fixture(self, root):
        request = canonical({"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []})
        response = canonical({"jsonrpc": "2.0", "id": 1, "result": "0x1"})
        row = {"sequence": 1, "client_method": "eth_chainId", "client_params": [],
               "request_utf8": request, "request_sha256": sha(request.encode()),
               "response_utf8": response, "response_sha256": sha(response.encode()), "http_status": 200}
        path = root / "source.jsonl"
        path.write_text(canonical(row) + "\n")
        return path, row

    def test_replay_is_network_free_and_missing_state_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, _ = self.fixture(root)
            with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
                witness = Witness(root / "out", replay=source)
                self.assertEqual(witness.call("eth_chainId", []), "0x1")
                with self.assertRaisesRegex(ValueError, "offline witness miss"):
                    witness.call("eth_getCode", ["0x" + "11" * 20, hex(PREVIOUS)])
            self.assertEqual(witness.count, 0)

    def test_corrupt_bytes_and_misbinding_fail_before_replay(self):
        for change in (lambda x: x.update(response_utf8="{}"),
                       lambda x: x.update(client_params=["different"]),
                       lambda x: x.update(http_status=429)):
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                source, row = self.fixture(root)
                change(row)
                source.write_text(canonical(row) + "\n")
                with self.assertRaises(ValueError):
                    Witness(root / "out", replay=source)

    def test_http_failure_halts_without_retry_and_is_retained(self):
        class FailedResponse:
            status = 429
            headers = {"Retry-After": "60"}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size): return b'{"error":"rate limit"}'
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "out"
            witness = Witness(root, interval=0)
            with patch("urllib.request.urlopen", return_value=FailedResponse()) as request:
                with self.assertRaises(ValueError): witness.call("eth_chainId", [])
                with self.assertRaises(RuntimeError): witness.call("eth_chainId", [])
                self.assertEqual(request.call_count, 1)
            row = json.loads((root / "upstream.jsonl").read_text())
            self.assertEqual(row["http_status"], 429)
            self.assertEqual(row["response_utf8"], '{"error":"rate limit"}')

    def test_zero_network_budget_stops_before_request(self):
        with tempfile.TemporaryDirectory() as d:
            witness = Witness(Path(d) / "out", max_requests=0)
            with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
                with self.assertRaises(RuntimeError): witness.call("eth_chainId", [])

    def test_retained_attempt_is_a_403_failure_not_a_fork_pass(self):
        path = Path(__file__).parent / "inputs/execution-attempt.zip"
        self.assertEqual(sha(path.read_bytes()), "3ff54ad55dd31138fc7ccd47e6cacd0fd81c0036f079874c856072d0ec06e9c6")
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read("attempt-manifest.json"))
            self.assertEqual(set(archive.namelist()), set(manifest["files"]) | {"attempt-manifest.json"})
            for name, pin in manifest["files"].items():
                raw = archive.read(name)
                self.assertEqual((len(raw), sha(raw)), (pin["bytes"], pin["sha256"]))
            report = json.loads(archive.read("capture-002/report.json"))
            self.assertEqual((report["status"], report["upstream_requests"], report["runs"]), ("FAILED", 1, []))
            row = json.loads(archive.read("capture-002/rpc/upstream.jsonl"))
            self.assertEqual((row["http_status"], row["response_utf8"]), (403, "error code: 1010\n"))
            self.assertEqual(sha(row["response_utf8"].encode()), row["response_sha256"])
            self.assertFalse(manifest["historical_fork_reproduced"])
            self.assertIn("8 passed; 0 failed; 0 skipped", archive.read("offline-unit-tests.log").decode())


if __name__ == "__main__":
    unittest.main()
