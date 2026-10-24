"""Offline evidence tampering, admission limits and build-copy boundaries."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from integrity import canonical, digest, strict_json
import morpho_experiment as m


class MorphoCaptureTests(unittest.TestCase):
    def setUp(self):
        self.raw = (m.HERE / "evidence/h25-morpho-partial.json").read_bytes()
        self.data = strict_json(self.raw)

    def mutate(self, provider, label, field, function):
        entry = self.data["entries"][provider+"-"+label]
        value = strict_json(entry[field].encode())
        function(value)
        entry[field] = canonical(value).decode()
        if field != "metadata":
            metadata = strict_json(entry["metadata"].encode())
            metadata[field+"_sha256"] = digest(entry[field].encode())
            entry["metadata"] = canonical(metadata).decode()

    def reject(self, reason):
        with self.assertRaisesRegex(ValueError, reason):
            m._validate_capture(self.data)

    def test_retained_capture_stays_no_go(self):
        report = m.verify_partial_capture()
        self.assertEqual(report["decision"], "NO-GO")
        self.assertEqual(report["completed_rpc_captures"], 15)
        self.assertEqual(report["gas_provider"], "Titan")
        self.assertEqual(report["operator_gas_budget_wei"], "0")
        for key in ("historical_fork_executed", "receipt_replay_verified", "aave_implementation_pinned",
                    "receipt_trie_proof_verified", "own_gas_fallback", "titan_execution_coverage_proven",
                    "all_in_profit_proven", "signing_authorized", "broadcast_authorized", "spending_authorized",
                    "phase_advance_authorized"):
            self.assertIs(report[key], False, key)
        commitment = report.pop("report_commitment_sha256")
        self.assertEqual(commitment, digest(canonical(report)))

    def test_public_pin_rejects_resealed_capture(self):
        self.mutate("blastapi", "chain", "response", lambda d: d.update(result="0x2"))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"capture.json"
            path.write_bytes(canonical(self.data))
            with self.assertRaisesRegex(ValueError, "capture_pin_mismatch"):
                m.verify_partial_capture(path)

    def test_duplicate_json_key_rejected(self):
        self.data["entries"]["blastapi-chain"]["metadata"] = '{"url":"x","url":"y"}'
        self.reject("duplicate_json_key")

    def test_fabricated_completion_rejected(self):
        self.data["acquisition_status"] = "COMPLETE"
        self.reject("capture_scope")

    def test_missing_completed_entry_rejected(self):
        del self.data["entries"]["blastapi-receipt"]
        self.reject("completed_inventory")

    def test_incomplete_request_cannot_be_promoted(self):
        self.data["entries"]["mevblocker-weth-code"] = copy.deepcopy(self.data["entries"]["blastapi-weth-code"])
        self.reject("completed_inventory")

    def test_unexpected_authority_field_rejected(self):
        self.data["titan_execution_coverage_proven"] = True
        self.reject("capture_fields")

    def test_request_anchor_cannot_be_resealed(self):
        self.mutate("blastapi", "pool-code", "request", lambda d: d.update(params=[m.POOL, "latest"]))
        self.reject("request_identity")

    def test_wrong_provider_rejected(self):
        self.mutate("blastapi", "chain", "metadata", lambda d: d.update(url=m.PROVIDERS["mevblocker"]))
        self.reject("provider_identity")

    def test_transport_failure_rejected(self):
        self.mutate("blastapi", "chain", "metadata", lambda d: d.update(returncode=True))
        self.reject("transport_failed")

    def test_transport_digest_rejected(self):
        self.mutate("blastapi", "chain", "metadata", lambda d: d.update(response_sha256="0"*64))
        self.reject("transport_digest")

    def test_wrong_jsonrpc_id_rejected(self):
        self.mutate("blastapi", "chain", "response", lambda d: d.update(id=True))
        self.reject("response_identity")

    def test_provider_disagreement_rejected(self):
        self.mutate("blastapi", "chain", "response", lambda d: d.update(result="0x2"))
        self.reject("provider_disagreement")

    def test_both_providers_wrong_block_rejected(self):
        for p in m.PROVIDERS:
            self.mutate(p, "winner", "response", lambda d: d["result"].update(timestamp="0x1"))
        self.reject("winner_anchor")

    def test_both_providers_wrong_order_rejected(self):
        for p in m.PROVIDERS:
            self.mutate(p, "winner", "response", lambda d: d["result"]["transactions"].reverse())
        self.reject("transaction_order")

    def test_both_providers_wrong_receipt_amount_rejected(self):
        def alter(d):
            leg = next(x for x in d["result"]["logs"] if x["topics"][0] == m.LIQUIDATION_TOPIC)
            leg["data"] = "0x"+"0"*64+leg["data"][66:]
        for p in m.PROVIDERS:
            self.mutate(p, "receipt", "response", alter)
        self.reject("liquidation_amounts")

    def test_removed_logs_rejected(self):
        for p in m.PROVIDERS:
            self.mutate(p, "receipt", "response", lambda d: d["result"]["logs"][0].update(removed=True))
        self.reject("log_anchor")

    def test_both_providers_wrong_code_rejected(self):
        for p in m.PROVIDERS:
            self.mutate(p, "pool-code", "response", lambda d: d.update(result="0x00"))
        self.reject("runtime_digest")

    def test_pending_request_tampering_rejected(self):
        self.data["incomplete_requests"]["mevblocker-weth-code-request.json"] = canonical(m.expected_request("chain")).decode()
        self.reject("incomplete_request")

    def test_timestamp_requires_timezone(self):
        self.mutate("blastapi", "chain", "metadata", lambda d: d.update(retrieved_at="2026-10-24T01:00:00"))
        self.reject("capture_time")


class MorphoPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_offline_copy_exact_and_fork_not_runnable(self):
        dest = self.root/"build"
        manifest = m.prepare_offline(dest)
        for source, target in m.SOURCE_LAYOUT.items():
            self.assertEqual((m.HERE/source).read_bytes(), (dest/target).read_bytes())
            self.assertEqual(manifest["files_sha256"][target], digest((dest/target).read_bytes()))
        self.assertFalse(manifest["network_used"])
        self.assertFalse(manifest["executed"])
        self.assertEqual(list((dest/"test").iterdir()), [dest/"test/morpho_liquidation_test.sol"])
        self.assertIn("abstract contract OmegaMorphoHistoricalHarness", (dest/"src/morpho_liquidation_fork.sol").read_text())

    def test_existing_destination_not_overwritten(self):
        dest = self.root/"build"
        dest.mkdir()
        keep = dest/"keep.txt"
        keep.write_text("preserve")
        with self.assertRaisesRegex(ValueError, "destination_exists"):
            m.prepare_offline(dest)
        self.assertEqual(keep.read_text(), "preserve")

    def test_repository_destination_rejected(self):
        with self.assertRaisesRegex(ValueError, "destination_overlaps_repository"):
            m.prepare_offline(m.HERE/"build")

    def test_symlink_parent_rejected(self):
        (self.root/"alias").symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "destination_symlink"):
            m.prepare_offline(self.root/"alias/build")

    def test_parent_segments_cannot_enter_repository(self):
        path = m.HERE.parent.parent/"nqc-radar-morpho/../nqc-radar-morpho/omega/build"
        with self.assertRaisesRegex(ValueError, "destination_overlaps_repository"):
            m.prepare_offline(path)

    def test_capture_symlink_rejected(self):
        p = self.root/"capture.json"
        p.symlink_to(m.HERE/"evidence/h25-morpho-partial.json")
        with self.assertRaisesRegex(ValueError, "symlink_input"):
            m.verify_partial_capture(p)


if __name__ == "__main__":
    unittest.main()
