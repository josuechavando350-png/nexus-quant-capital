"""Mutation checks against the independently compiled, historical runtime sample."""
import copy
import importlib.util
import gzip
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import aave_runtime_identity as model


class RuntimeIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = model.read_json(model.EVIDENCE / "source.json.gz")
        cls.compiled = model.read_json(model.EVIDENCE / "local/compiler-output.json.gz")
        cls.flash_compiled = model.read_json(model.EVIDENCE / "local/flashloan-compiler-output.json.gz")
        cls.flash_input = model.read_json(model.EVIDENCE / "local/flashloan-compiler-input.json.gz")
        spec = importlib.util.spec_from_file_location("library_capture_test", model.EVIDENCE / "capture.py")
        cls.capture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.capture)
        cls.histories = cls.capture.replay()

    def check_audit(self, source, output, histories):
        return model.audit(source, output, histories, self.flash_compiled, self.flash_input)

    def test_six_compiled_contracts_at_three_blocks(self):
        result = self.check_audit(self.source, self.compiled, self.histories)
        self.assertEqual(len(result["contracts"]), 6)
        self.assertEqual({len(r["blocks"]) for r in result["contracts"]}, {3})
        self.assertFalse(result["original_source_text_authenticated"])
        self.assertFalse(result["executable_eligibility_verified"])
        self.assertTrue(all(r["metadata_bytes_compared"] for r in result["contracts"]))

    def test_each_contract_provider_and_block_mismatch_rejected(self):
        for i in range(3):
            for address in [model.POOL, *model.LIBRARIES.values()]:
                for provider in ("ethereum-primary", "ethereum-secondary"):
                    with self.subTest(block=i, address=address, provider=provider):
                        h = copy.deepcopy(self.histories)
                        original = h[i]["runtimes"][address][provider]
                        h[i]["runtimes"][address][provider] = "0x00" + original[4:]
                        with self.assertRaises(ValueError):
                            self.check_audit(self.source, self.compiled, h)

    def test_metadata_difference_is_not_ignored(self):
        h = copy.deepcopy(self.histories)
        for provider, raw in h[0]["runtimes"][model.POOL].items():
            h[0]["runtimes"][model.POOL][provider] = raw[:-2] + "ff"
        with self.assertRaisesRegex(ValueError, "runtime mismatch"):
            self.check_audit(self.source, self.compiled, h)

    def test_provider_and_block_coverage(self):
        for h in (self.histories[:2], copy.deepcopy(self.histories)):
            if len(h) == 3:
                del h[1]["runtimes"][model.POOL]["ethereum-secondary"]
            with self.assertRaises(ValueError):
                self.check_audit(self.source, self.compiled, h)
        h = [self.histories[0], self.histories[0], self.histories[2]]
        with self.assertRaisesRegex(ValueError, "block coverage"):
            self.check_audit(self.source, self.compiled, h)

    def test_compiler_checksum_precedes_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            compiler = Path(directory) / "fake-solc"
            compiler.write_bytes(b"wrong compiler")
            with patch.object(model.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "compiler checksum"):
                    model.compile_source(compiler, {})
                run.assert_not_called()

    def test_retained_source_index_and_rule_excerpts(self):
        result = model.verify_provenance(self.source)
        self.assertEqual(set(result), {"retrieval_sha256", "flashloan_retrieval_sha256", "rule_excerpts_sha256"})

    def test_explorer_decoded_as_data_and_requires_one_literal(self):
        html = gzip.decompress((model.EVIDENCE / "flashloan-etherscan.html.gz").read_bytes()).decode()
        self.assertEqual(model.flashloan_input(html), self.flash_input)
        for changed in (html + html, html.replace("var editor_contractJsonData", "var otherData"),
                        html.replace("v0.8.27+commit.40a35a09", "v0.8.28+commit.40a35a09")):
            with self.assertRaises(ValueError):
                model.flashloan_input(changed)

    def test_joint_compilation_cannot_stand_in_for_library(self):
        # The pool's Cancun compilation produces a different FlashLoanLogic.
        # This is the actual preflight failure, not an artificial byte mutation.
        candidate = {"contracts": {model.FLASH_PATH: {
            "FlashLoanLogic": self.compiled["contracts"][model.PREFIX + "protocol/libraries/logic/FlashLoanLogic.sol"]["FlashLoanLogic"]}}}
        with self.assertRaisesRegex(ValueError, "runtime mismatch: FlashLoanLogic"):
            model.audit(self.source, self.compiled, self.histories, candidate, self.flash_input)

    def test_source_identity_compiler_and_literal_inputs(self):
        for mutate in (
            lambda x: x.update(chainId="10"),
            lambda x: x.update(address="0x" + "11" * 20),
            lambda x: x["compilation"].update(compilerVersion="0.8.28"),
            lambda x: x["stdJsonInput"]["sources"][model.POOL_PATH].update(urls=["file:///tmp/foreign.sol"]),
            lambda x: x["stdJsonInput"]["settings"].update(viaIR=True),
        ):
            s = copy.deepcopy(self.source)
            mutate(s)
            with self.assertRaises(ValueError):
                model.compilation_input(s)

    def test_unknown_and_overlapping_links_rejected(self):
        base = copy.deepcopy(self.compiled["contracts"][model.POOL_PATH]["PoolInstance"]["evm"]["deployedBytecode"])
        path = next(iter(base["linkReferences"]))
        name = next(iter(base["linkReferences"][path]))
        for failure in ("unknown", "overlap", "bounds", "width"):
            code = copy.deepcopy(base)
            refs = code["linkReferences"][path][name]
            if failure == "unknown":
                code["linkReferences"]["foreign.sol"] = {"Foreign": refs}
            elif failure == "overlap":
                refs.append(copy.deepcopy(refs[0]))
            elif failure == "bounds":
                refs[0]["start"] = len(code["object"])
            else:
                refs[0]["length"] = 19
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                model.render_runtime(code, model.POOL, model.immutable_names(self.compiled))

    def test_immutable_name_and_shape_rejected(self):
        code = copy.deepcopy(self.compiled["contracts"][model.POOL_PATH]["PoolInstance"]["evm"]["deployedBytecode"])
        with self.assertRaisesRegex(ValueError, "unknown immutable"):
            model.render_runtime(code, model.POOL, {})
        identity = next(iter(code["immutableReferences"]))
        code["immutableReferences"][identity][0]["length"] = 20
        with self.assertRaises(ValueError):
            model.render_runtime(code, model.POOL, model.immutable_names(self.compiled))

    def test_library_guard_cannot_mask_arbitrary_prefix(self):
        code = {"object": "60" + "00" * 20 + "3014"}
        with self.assertRaisesRegex(ValueError, "self-address guard"):
            model.render_runtime(code, model.LIBRARIES["PoolLogic"], {}, True)

    def test_unresolved_bytes_and_compiler_errors(self):
        with self.assertRaises(ValueError):
            model.render_runtime({"object": "__$bad$__0"}, model.POOL, {})
        o = copy.deepcopy(self.compiled)
        o["errors"] = [{"severity": "error", "message": "failed"}]
        with self.assertRaisesRegex(ValueError, "compiler error"):
            self.check_audit(self.source, o, self.histories)

    def test_replay_rejects_wrong_chain_reorg_or_missing_runtime(self):
        original = self.capture.source(0)
        for failure in ("chain", "reorg", "empty", "disagreement"):
            history = copy.deepcopy(self.histories[0])
            if failure == "chain":
                history["records"][0]["response"]["result"] = "0x2"
            elif failure == "reorg":
                history["records"][-1]["response"]["result"]["hash"] = "0x" + "11" * 32
            elif failure == "empty":
                history["records"][4]["response"]["result"] = "0x"
            else:
                history["records"][17]["response"]["result"] = "0x6000"
            records = iter(history["records"])
            def query(provider, method, params):
                r = next(records)
                self.assertEqual((provider, method, params), (r["provider_id"], r["request"]["method"], r["request"]["params"]))
                return {"request": r["request"], "response": r["response"]}
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                self.capture.capture_one(original, query)


if __name__ == "__main__":
    unittest.main()
