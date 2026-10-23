"""Offline checks for the fixed, read-only proxy evidence probe."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("proxy_capture", ROOT / "capture.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
SOURCE = probe.MODULE / "evidence/aave-state-public-attempt-20261023/history-000/read-state.stdout"


def fake(fault=""):
    source = probe.load(SOURCE)
    headers = {h["number"]: h for h in (source["samples"][-1]["block"], source["event_anchor"], source["finalized_anchor"])}
    sequence = 0

    def call(provider, method, params):
        nonlocal sequence
        sequence += 1
        if method == "eth_chainId":
            value = "0x2" if fault == "chain" else "0x1"
        elif method == "eth_getBlockByNumber":
            h = source["finalized_anchor"] if params[0] == "finalized" else headers[int(params[0], 16)]
            value = {"number": hex(h["number"]), "timestamp": hex(h["timestamp"]), "hash": h["hash"], "parentHash": h["parent_hash"]}
            if fault == "hash" and params[0] != "finalized": value["hash"] = "0x" + "1" * 64
            if fault == "reorg" and sequence >= 21: value["hash"] = "0x" + "1" * 64
            if fault == "unfinalized" and params[0] == "finalized": value["number"] = "0x1"
        elif method == "eth_getStorageAt":
            if fault == "unavailable": raise RuntimeError("archive unavailable")
            value = "0x" + "0" * 63 + ("3" if fault == "disagreement" and provider == "ethereum-secondary" else "2")
            if fault == "zero": value = "0x" + "0" * 64
        elif method == "eth_getCode":
            value = "0x6001600055"
            if fault == "code-disagreement" and provider == "ethereum-secondary": value = "0x6002"
            if fault == "empty-code": value = "0x"
        else:
            raise AssertionError(method)
        return {"request": {"jsonrpc": "2.0", "id": sequence, "method": method, "params": params},
                "response": {"jsonrpc": "2.0", "id": sequence, "result": value}}
    return call


class ProbeTests(unittest.TestCase):
    def test_fixed_snapshot_quorum_and_raw_runtime_preserved(self):
        r = probe.capture_one(probe.load(SOURCE), fake())
        self.assertEqual(r["implementation"], "0x" + "0" * 39 + "2")
        self.assertEqual(len(r["records"]), 24)
        self.assertEqual(r["implementation_bytes"], 5)
        self.assertIsNone(r["protocol_version"])
        self.assertFalse(r["implementation_source_match_verified"])
        self.assertFalse(r["state_authentication_verified"])

    def test_chain_finality_header_and_post_quorum_reorg_rejected(self):
        for fault in ["chain", "unfinalized", "hash", "reorg"]:
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                probe.capture_one(probe.load(SOURCE), fake(fault))

    def test_storage_code_disagreement_missing_state_and_empty_code_rejected(self):
        for fault in ["disagreement", "code-disagreement", "zero", "unavailable", "empty-code"]:
            with self.subTest(fault=fault), self.assertRaises((ValueError, RuntimeError)):
                probe.capture_one(probe.load(SOURCE), fake(fault))

    def test_storage_address_is_exact_nonzero_word(self):
        for word in [None, "0x", "0x" + "0" * 64, "0x01" + "00" * 31, "0x" + "A" * 64]:
            with self.subTest(word=word), self.assertRaises(ValueError): probe.implementation(word)

    def test_code_bounds_and_hex(self):
        self.assertEqual(len(probe.code_bytes("0x" + "aa" * probe.MAX_CODE)), probe.MAX_CODE)
        for raw in [None, "0x", "0x0", "0xgg", "0x" + "aa" * (probe.MAX_CODE + 1)]:
            with self.subTest(raw=str(raw)[:20]), self.assertRaises(ValueError): probe.code_bytes(raw)

    def test_foreign_source_and_post_event_state_rejected(self):
        for path, value in [(('owner', 'data_class'), 'shadow'), (('plan', 'scope_id'), 'foreign'),
                            (('event_anchor', 'parent_hash'), '0x' + '1' * 64)]:
            r = probe.load(SOURCE);r[path[0]][path[1]] = value
            with self.assertRaises(ValueError): probe.capture_one(r, fake())

    def test_transport_rejects_unpinned_or_mutating_requests_before_network(self):
        anchor = {"blockHash": "0x" + "1" * 64, "requireCanonical": True}
        cases = [("eth_sendTransaction", []), ("eth_getStorageAt", [probe.POOL, "0x0", anchor]),
                 ("eth_getCode", [probe.POOL, "latest"]), ("eth_getCode", [probe.POOL, anchor, {}]),
                 ("eth_getCode", [probe.POOL, {**anchor, "requireCanonical": 1}])]
        with patch.object(probe.urllib.request, 'build_opener', side_effect=AssertionError('network reached')):
            for method, params in cases:
                with self.subTest(method=method, params=params), self.assertRaises(ValueError):
                    probe.Rpc()("ethereum-primary", method, params)


if __name__ == "__main__":
    unittest.main()
