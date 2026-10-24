import copy
import gzip
import json
import os
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import capture_aave_conditions as capture
import aave_runtime_identity as identity


def abi(values):
    return "0x" + "".join(f"{v:064x}" for v in values)


class FakeQuery:
    def __init__(self, source, mutate=None):
        self.source, self.mutate, self.sequence = source, mutate, 0

    def __call__(self, provider, method, arguments):
        self.sequence += 1
        request = {"jsonrpc": "2.0", "id": self.sequence, "method": method, "params": arguments}
        if method == "eth_chainId":
            value = "0x1"
        elif method == "eth_getBlockByNumber":
            original = self.source["identity"]
            h = original["block"] if arguments[0] == hex(original["block"]["number"]) else original["event_anchor"]
            value = {"number": hex(h["number"]), "timestamp": hex(h["timestamp"]), "hash": h["hash"], "parentHash": h["parent_hash"]}
        else:
            capture.validate_params(arguments)
            selector = arguments[0]["data"][:10]
            if selector == capture.SELECTORS["getReserveData"]:
                value = abi([1 << 56,1,1,1,1,0,1,0,1,0,0xdead,1,0,0,0])
            elif selector == capture.SELECTORS["getUserConfiguration"]:
                value = abi([2])
            elif selector == capture.SELECTORS["getUserAccountData"]:
                value = abi([10,9,0,8000,7500,999999999999999999])
            elif selector == capture.SELECTORS["getLiquidationGracePeriod"]:
                value = abi([0])
            else:
                value = abi([1])
        if self.mutate:
            value = self.mutate(self.sequence, provider, method, arguments, value)
        return {"request": request, "response": {"jsonrpc": "2.0", "id": self.sequence, "result": value}}


class AaveConditionsTests(unittest.TestCase):
    def setUp(self):
        self.source = capture.sources()[0]

    def test_complete_capture_is_bounded_and_not_transaction_prestate(self):
        query = FakeQuery(self.source)
        report = capture.capture_one(self.source, query)
        self.assertEqual(query.sequence, 32)
        self.assertEqual(len([r for r in report["records"] if r["request"]["method"] == "eth_call"]), 14)
        self.assertEqual(report["inputs"]["selected_debt"], "1")
        self.assertFalse(report["transaction_prestate"])
        self.assertFalse(report["executable_eligibility_verified"])

    def test_chain_header_finality_and_final_recheck_fail_closed(self):
        for index in [1,2,3,4,12,13,14,29,30,31,32]:
            def mutate(i, provider, method, args, value):
                if i != index:
                    return value
                if method == "eth_chainId":
                    return "0x2"
                value = copy.deepcopy(value)
                if index == 2:
                    value["number"] = "0x1"
                else:
                    value["hash"] = "0x" + "11" * 32
                return value
            with self.subTest(index=index), self.assertRaises(ValueError):
                capture.capture_one(self.source, FakeQuery(self.source, mutate))

    def test_full_return_bytes_must_agree_including_unused_reserve_field(self):
        def mutate(i, provider, method, args, value):
            if i == 19:
                return value[:-1] + "1"
            return value
        with self.assertRaisesRegex(ValueError, "byte disagreement"):
            capture.capture_one(self.source, FakeQuery(self.source, mutate))

    def test_abi_canonical_width_zero_token_and_missing_return(self):
        good = [1 << 56,1,1,1,1,0,1,0,1,0,0xdead,1,0,0,0]
        for index, value in [(1,1 << 128),(6,1 << 40),(7,1 << 16),(8,1 << 160),(10,0)]:
            bad = good.copy(); bad[index] = value
            with self.assertRaises(ValueError):
                capture.reserve(abi(bad))
        for bad in ["0x", "0x0", abi(good[:-1]), abi(good + [0]), None]:
            with self.assertRaises(ValueError):
                capture.reserve(bad)

    def test_getter_mutation_rejected_before_network(self):
        good = capture.params("getReserveData", capture.probe.POOL, self.source["event"]["decoded"]["payload"]["debt_token"], self.source["identity"]["block"])
        changes = []
        x = copy.deepcopy(good); x[1] = "latest"; changes.append(x)
        x = copy.deepcopy(good); x.append({}); changes.append(x)
        x = copy.deepcopy(good); x[0]["data"] = "0xdeadbeef" + x[0]["data"][10:]; changes.append(x)
        x = copy.deepcopy(good); x[0]["value"] = "0x1"; changes.append(x)
        x = copy.deepcopy(good); x[1]["requireCanonical"] = False; changes.append(x)
        x = copy.deepcopy(good); x[0]["data"] = x[0]["data"][:10] + "1" + x[0]["data"][11:]; changes.append(x)
        with patch.object(capture.urllib.request, "build_opener") as network:
            for arguments in changes:
                with self.assertRaises(ValueError):
                    capture.Rpc()("ethereum-primary", "eth_call", arguments)
            with self.assertRaises(ValueError):
                capture.Rpc()("ethereum-primary", "eth_sendRawTransaction", ["0x"])
            network.assert_not_called()

    def test_compilation_preserves_original_sources_and_exact_fixture(self):
        directory = identity.MODULE / "evidence/aave-conditions-20261023/compiler"
        value = identity.read_json(directory / "input.json.gz")
        result = identity.read_json(directory / "output.json.gz")
        fixture = identity.read_json(identity.MODULE / "fixtures/aave_validation_harness.json")
        source = identity.read_json(identity.EVIDENCE / "source.json.gz")
        self.assertEqual({k: v for k, v in value["sources"].items() if k != "fixtures/AaveValidationHarness.sol"}, source["sources"])
        self.assertEqual(identity.sha(gzip.decompress((directory / "input.json.gz").read_bytes())), fixture["compiler_input_sha256"])
        self.assertEqual(identity.sha(gzip.decompress((directory / "output.json.gz").read_bytes())), fixture["compiler_output_sha256"])
        code = result["contracts"]["fixtures/AaveValidationHarness.sol"]["AaveValidationHarness"]["evm"]["deployedBytecode"]["object"]
        self.assertEqual("0x" + code, fixture["runtime_code"])
        self.assertFalse(fixture["activation_allowed"])

    def test_real_cli_rejects_unknown_fields_and_does_not_grant_execution(self):
        binary = os.environ["NQC_MINER_TEST_BINARY"]
        report = capture.capture_one(self.source, FakeQuery(self.source))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(json.dumps(report["inputs"]))
            run = subprocess.run([binary, "check-aave-conditions", "--input", str(path)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(run.stdout)
            self.assertTrue(result["initial_conditions_passed"])
            self.assertFalse(result["executable_eligibility_verified"])
            report["inputs"]["activation_allowed"] = True; path.write_text(json.dumps(report["inputs"]))
            rejected = subprocess.run([binary, "check-aave-conditions", "--input", str(path)], capture_output=True)
            self.assertNotEqual(rejected.returncode, 0)

    def test_retained_records_replay_and_tampering_is_not_hidden_by_new_hashes(self):
        directory = identity.MODULE / "evidence/aave-conditions-20261023/public"
        reports = capture.replay(directory)
        self.assertEqual(len(reports), 3)
        self.assertEqual(sum(len(r["records"]) for r in reports), 96)
        for failure in ("response_id", "request_anchor", "derived_debt", "transaction"):
            with tempfile.TemporaryDirectory() as temporary:
                copied = Path(temporary) / "capture"; shutil.copytree(directory, copied)
                path = copied / "conditions-000.json"; value = json.loads(path.read_bytes())
                if failure == "response_id":
                    value["records"][0]["response"]["id"] = True
                elif failure == "request_anchor":
                    value["records"][4]["request"]["params"][1]["blockHash"] = "0x" + "11" * 32
                elif failure == "derived_debt":
                    value["inputs"]["selected_debt"] = "0"
                else:
                    value["event_transaction"] = "0x" + "11" * 32
                path.write_bytes(identity.encoded(value))
                manifest = json.loads((copied / "manifest.json").read_bytes())
                manifest["observations"][0]["sha256"] = identity.sha(path.read_bytes())
                (copied / "manifest.json").write_bytes(identity.encoded(manifest))
                with self.subTest(failure=failure), self.assertRaises(ValueError):
                    capture.replay(copied)


if __name__ == "__main__":
    unittest.main()
