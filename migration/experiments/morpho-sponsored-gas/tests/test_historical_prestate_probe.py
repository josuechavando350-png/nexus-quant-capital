"""Pinned parent-block candidate, never a claim of NQC capture."""
import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from historical_prestate_probe import (  # noqa: E402
    build_calls, calldata, check_fixture, market_id, parse_response, run_probe,
)

FIXTURE = ROOT / "observations/ethereum_morpho_2026-06-26_market_params.json"
RECORD = json.loads(FIXTURE.read_text())
EXPECTED_MARKET_ID = "0x582fdc4176da0ab5c65e086603ab9ecd9188e889e16efef6e35854cf14e15065"


def abi_return(*ns):
    return "0x" + "".join(int(v).to_bytes(32, "big").hex() for v in ns)


def response_set(r=RECORD):
    a = [int(r[k], 16) for k in ("loan_token", "collateral_token", "oracle", "irm")]
    a.append(int(r["lltv"]))
    return [
        {"jsonrpc": "2.0", "id": 1, "result": abi_return(*a)},
        {"jsonrpc": "2.0", "id": 2, "result": abi_return(200000000, 200000000, 150000000, 150000000000000, 1700000000, 0)},
        {"jsonrpc": "2.0", "id": 3, "result": abi_return(0, 120000000000000, 141266903937864768497)},
    ]


class PinnedParentBlockTests(unittest.TestCase):
    def test_morpho_market_id_matches_abi_keccak(self):
        self.assertEqual(market_id(RECORD), EXPECTED_MARKET_ID)
        self.assertNotEqual("0x" + hashlib.sha3_256(bytes.fromhex(EXPECTED_MARKET_ID[2:])).hexdigest(),
                            EXPECTED_MARKET_ID)

    def test_fixture_fields_are_pinned(self):
        check_fixture(RECORD)
        self.assertEqual(RECORD["callback_data"], "0x")
        self.assertEqual(RECORD["transaction_index"], 226)

    def test_only_three_read_only_eth_call_requests(self):
        calls = build_calls(RECORD)
        self.assertEqual(len(calls), 3)
        for idx, item in enumerate(calls, 1):
            self.assertEqual(item["method"], "eth_call")
            self.assertEqual(item["id"], idx)
            self.assertEqual(item["params"][0]["to"].lower(), RECORD["morpho_contract"].lower())
            self.assertEqual(item["params"][1], {
                "blockHash": RECORD["parent_block_hash"], "requireCanonical": True
            })
            self.assertNotIn("from", item["params"][0])
            self.assertNotIn("value", item["params"][0])

    def test_expected_abi_call_data_shapes(self):
        calls = build_calls(RECORD)
        self.assertEqual([len(x["params"][0]["data"]) for x in calls], [74, 74, 138])
        self.assertEqual(calls[0]["params"][0]["data"],
                         calldata("idToMarketParams(bytes32)", int(EXPECTED_MARKET_ID, 16)))
        self.assertEqual(calls[2]["params"][0]["data"],
                         calldata("position(bytes32,address)", int(EXPECTED_MARKET_ID, 16),
                                  int(RECORD["borrower"], 16)))

    def test_no_rpc_blocks_explicitly(self):
        code, report = run_probe(FIXTURE, None)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "BLOCKED_NO_ARCHIVE_RPC")
        self.assertFalse(report["certified"])

    def test_archive_responses_cannot_certify_nqc(self):
        report = parse_response(RECORD, response_set())
        self.assertEqual(report["status"], "PARENT_STATE_ONLY_NOT_PRETRANSACTION")
        self.assertFalse(report["certified"])
        self.assertFalse(report["live_executable"])
        self.assertIn("NOT_EXACT_PRETX_STATE_226_PRIOR_TXS_UNREPLAYED", report["blockers"])
        self.assertNotIn("profit", report)

    def test_mutated_market_id_fails(self):
        bad = dict(RECORD, market_id="0x"+"0"*64)
        with self.assertRaises(ValueError):
            check_fixture(bad)

    def test_mutated_oracle_fails(self):
        bad = dict(RECORD, oracle="0x"+"1"*40)
        with self.assertRaises(ValueError):
            check_fixture(bad)

    def test_mutated_parent_hash_fails(self):
        bad = dict(RECORD, parent_block_hash="0x"+"2"*64)
        with self.assertRaises(ValueError):
            check_fixture(bad)

    def test_mutated_scope_fails(self):
        bad = dict(RECORD, scope="PROFIT_CERTIFIED")
        with self.assertRaises(ValueError):
            check_fixture(bad)

    def test_bad_lltv_type_fails(self):
        for v in (True, -1, "1e18", "-1", 2**256):
            with self.subTest(v=v):
                with self.assertRaises(ValueError):
                    check_fixture(dict(RECORD, lltv=v))

    def test_response_id_must_match(self):
        fake = response_set()
        fake[1]["id"] = 66
        with self.assertRaises(ValueError):
            parse_response(RECORD, fake)

    def test_rpc_error_rejected(self):
        fake = response_set()
        fake[0].pop("result")
        fake[0]["error"] = {"code": -32000, "message": "archive state unavailable"}
        with self.assertRaises(ValueError):
            parse_response(RECORD, fake)

    def test_wrong_market_rejected(self):
        fake = response_set()
        fake[0]["result"] = abi_return(1,2,3,4,5)
        with self.assertRaises(ValueError):
            parse_response(RECORD, fake)

    def test_missing_borrower_rejected(self):
        fake = response_set()
        fake[2]["result"] = abi_return(0,0,0)
        with self.assertRaises(ValueError):
            parse_response(RECORD, fake)

    def test_malformed_data_rejected(self):
        fake = response_set()
        fake[2]["result"] = "0x01"
        with self.assertRaises(ValueError):
            parse_response(RECORD, fake)

    def test_self_consistent_market_substitution_rejected(self):
        bad = dict(RECORD, oracle="0x"+"1"*40)
        bad["market_id"] = market_id(bad)
        with self.assertRaises(ValueError): check_fixture(bad)

    def test_boolean_response_id_rejected(self):
        fake = response_set(); fake[0]["id"] = True
        with self.assertRaises(ValueError): parse_response(RECORD, fake)

    def test_uint128_overflow_in_state_rejected(self):
        fake = response_set(); fake[2]["result"] = abi_return(0,2**128,1)
        with self.assertRaises(ValueError): parse_response(RECORD, fake)

    def test_borrower_shares_must_fit_total(self):
        fake = response_set(); fake[2]["result"] = abi_return(0,150000000000001,1)
        with self.assertRaises(ValueError): parse_response(RECORD, fake)


if __name__ == "__main__":
    unittest.main()
