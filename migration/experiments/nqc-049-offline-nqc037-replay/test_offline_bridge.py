"""NQC049 stdlib unit tests: synthetic receipts and injected NO-NETWORK validator."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parent))
import offline_bridge as bridge


class OfflineBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.plan = [{"purpose": p, "request": {"jsonrpc": "2.0", "id": i}} for i, p in enumerate(
            ["chain", "parent", "priority_proof", "priority_code", "arbos_proof", "anchor", "history_proof", "history_code"], 1)]
        self.journal = dict(schema=bridge.SCHEMA, mode="DRY_RUN", scope=bridge.SCOPE,
                            plan_sha256=bridge.PLAN_DIGEST, spec_sha256=bridge.SPEC_DIGEST,
                            max_requests=8, commercial_admission=False, entries=[])
        self.called = []

    def validate(self, op, r, state):
        self.called.append(op["request"]["id"])
        if r["result"] != "SAFE_TEST_" + str(op["request"]["id"]):
            raise ValueError("synthetic validator refused")
        state[op["purpose"]] = r["result"]

    def add(self, *, result="SAFE_TEST_1", status="RECEIVED", pad=0, raw=None, bad_chunk=None):
        index = len(self.journal["entries"]) + 1
        if raw is None:
            obj = {"jsonrpc": "2.0", "id": index, "result": result, "padding": "X" * pad}
            raw = bridge.canonical_json(obj)
        parts = []
        for i, start in enumerate(range(0, len(raw), bridge.CHUNK_BYTES)):
            data = raw[start:start + bridge.CHUNK_BYTES]
            encoded = base64.b64encode(data)
            place = self.base / "receipts" / f"{index:02d}"
            place.mkdir(parents=True, exist_ok=True)
            (place / f"part-{i:03d}.b64").write_bytes(encoded)
            parts.append({"bytes": len(data), "b64_sha256": bridge.digest(encoded)})
        row = dict(id=index, purpose=self.plan[index-1]["purpose"], status=status,
                   receipt=dict(byte_length=len(raw), sha256=bridge.digest(raw), parts=parts))
        self.journal["entries"].append(row)
        return row

    def test_01_received_revalidates_but_does_not_clear(self):
        self.add()
        result = bridge.replay_snapshot(self.base, self.journal, self.plan, self.validate)
        self.assertEqual(result["status"], "BLOCKED_RECEIVED_REVIEW_REQUIRED")
        self.assertEqual(self.called, [1])
        self.assertFalse(result["commercial_admission"])

    def test_02_verified_prefix_may_be_inspected_not_dispatched(self):
        self.add(status="VERIFIED")
        result = bridge.replay_snapshot(self.base, self.journal, self.plan, self.validate)
        self.assertEqual(result["status"], "OFFLINE_VERIFIED_PREFIX_ONLY_NO_DISPATCH")
        self.assertEqual(result["responses_validated"], 1)

    def test_03_large_three_chunk_integrity(self):
        row = self.add(pad=700000)
        self.assertGreater(row["receipt"]["byte_length"], 650000)
        self.assertEqual(len(row["receipt"]["parts"]), 3)
        self.assertEqual(bridge.replay_snapshot(self.base, self.journal, self.plan, self.validate)["responses_validated"], 1)

    def test_04_bad_chunk_blocks(self):
        self.add()
        (self.base / "receipts/01/part-000.b64").write_text("tampered")
        with self.assertRaisesRegex(bridge.Blocked, "CHUNK_SHA_MISMATCH"):
            bridge.replay_snapshot(self.base, self.journal, self.plan, self.validate)
        self.assertEqual(self.called, [])

    def test_05_response_json_duplicate_keys_refused(self):
        raw = b'{"jsonrpc":"2.0","id":1,"result":"SAFE_TEST_1","result":"SAFE_TEST_1"}'
        self.add(raw=raw)
        with self.assertRaisesRegex(bridge.Blocked, "DUPLICATE_JSON_KEY"):
            bridge.replay_snapshot(self.base, self.journal, self.plan, self.validate)

    def test_06_rpc_envelope_wrong_id_refused(self):
        raw = b'{"jsonrpc":"2.0","id":2,"result":"SAFE_TEST_1"}'
        self.add(raw=raw)
        with self.assertRaisesRegex(bridge.Blocked, "RPC_ENVELOPE_INVALID"):
            bridge.replay_snapshot(self.base, self.journal, self.plan, self.validate)

    def test_07_errors_refused(self):
        raw = b'{"jsonrpc":"2.0","id":1,"error":{"code":429}}'
        self.add(raw=raw)
        with self.assertRaisesRegex(bridge.Blocked, "RPC_ENVELOPE_INVALID"):
            bridge.replay_snapshot(self.base, self.journal, self.plan, self.validate)

    def test_08_pending_reservation_never_validates_or_dispatches(self):
        self.journal["entries"] = [dict(id=1,purpose="chain",status="RESERVED")]
        self.assertEqual(bridge.replay_snapshot(self.base, self.journal, self.plan, self.validate)["status"], "BLOCKED_PENDING_RESERVATION")
        self.assertEqual(self.called, [])

    def test_09_rejected_stays_rejected(self):
        self.journal["entries"] = [dict(id=1,purpose="chain",status="REJECTED")]
        self.assertEqual(bridge.replay_snapshot(self.base, self.journal, self.plan, self.validate)["status"], "BLOCKED_REJECTED_STEP")

    def test_10_no_false_chain_acceptance_for_synthetic_result(self):
        self.add(result="SIM_ACCEPTED_1")
        result = bridge.replay_snapshot(self.base, self.journal, self.plan, self.validate)
        self.assertEqual(result["status"], "BLOCKED_NQC037_VALIDATION")
        self.assertEqual(result["responses_validated"], 0)

    def test_11_extra_journal_field_refused(self):
        self.journal["commercial_admission"] = True
        with self.assertRaisesRegex(bridge.Blocked, "JOURNAL_BINDING"):
            bridge.replay_snapshot(self.base, self.journal, self.plan, self.validate)

    def test_12_no_ninth_entry(self):
        self.journal["entries"] = [dict(id=i,purpose="x",status="VERIFIED") for i in range(1,10)]
        with self.assertRaisesRegex(bridge.Blocked, "JOURNAL_BUDGET"):
            bridge.replay_snapshot(self.base, self.journal, self.plan, self.validate)

    def test_13_nonterminal_prefix_refused(self):
        self.journal["entries"] = [dict(id=1,purpose="chain",status="RESERVED"),dict(id=2,purpose="parent",status="RESERVED")]
        with self.assertRaisesRegex(bridge.Blocked, "JOURNAL_PREFIX"):
            bridge.replay_snapshot(self.base, self.journal, self.plan, self.validate)

    def test_14_nonfinal_short_chunk_refused(self):
        row = self.add(pad=350000)
        row["receipt"]["parts"][0]["bytes"] -= 1
        with self.assertRaisesRegex(bridge.Blocked, "RECEIPT_NONFINAL_PART"):
            bridge.replay_snapshot(self.base, self.journal, self.plan, self.validate)

    def test_15_missing_part_refused(self):
        self.add()
        (self.base / "receipts/01/part-000.b64").unlink()
        with self.assertRaisesRegex(bridge.Blocked, "MISSING_OR_UNSAFE_FILE"):
            bridge.replay_snapshot(self.base, self.journal, self.plan, self.validate)

    def test_16_symlink_refused(self):
        self.add()
        part = self.base / "receipts/01/part-000.b64"
        moved = part.with_suffix(".bak")
        part.rename(moved)
        part.symlink_to(moved)
        with self.assertRaisesRegex(bridge.Blocked, "MISSING_OR_UNSAFE_FILE"):
            bridge.replay_snapshot(self.base, self.journal, self.plan, self.validate)

    def test_17_nan_json_refused(self):
        self.add(raw=b'{"jsonrpc":"2.0","id":1,"result":NaN}')
        with self.assertRaisesRegex(bridge.Blocked, "NON_JSON_CONSTANT"):
            bridge.replay_snapshot(self.base, self.journal, self.plan, self.validate)

    def test_18_actual_source_guard_missing_files_blocks(self):
        self.assertEqual(bridge.audit_repository(self.base)["status"], "BLOCKED_PIN_OR_INPUT")

    def test_19_source_pin_mutation_block(self):
        f = self.base / "nqc-037-historical-state/src/intake.py"
        f.parent.mkdir(parents=True)
        f.write_text("# unexpected change")
        with self.assertRaisesRegex(bridge.Blocked, "PINNED_SOURCE_MISMATCH"):
            bridge.source_bindings(self.base)

    def test_20_git_blob_hash_known_vector(self):
        self.assertEqual(bridge.git_blob_sha(b"hello\n"), "ce013625030ba8dba906f756967f9e9ca394464a")

    def test_21_wrong_sha256_complete_response_refused(self):
        self.add()
        self.journal["entries"][0]["receipt"]["sha256"] = "a" * 64
        with self.assertRaisesRegex(bridge.Blocked, "RECEIPT_SHA_MISMATCH"):
            bridge.replay_snapshot(self.base, self.journal, self.plan, self.validate)

    def test_22_boolean_id_is_not_integer(self):
        self.add(raw=b'{"jsonrpc":"2.0","id":true,"result":"SAFE_TEST_1"}')
        with self.assertRaisesRegex(bridge.Blocked, "RPC_ENVELOPE_INVALID"):
            bridge.replay_snapshot(self.base, self.journal, self.plan, self.validate)


if __name__ == "__main__":
    unittest.main(verbosity=2)
