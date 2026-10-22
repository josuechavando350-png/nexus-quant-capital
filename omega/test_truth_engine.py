import copy
import unittest

from truth_engine import evaluate_batch, evaluate_triad, seal_triad, validate_triad


def h(ch):
    return ch * 64


def bh(ch):
    return "0x" + ch * 64


ANCHOR = {
    "chain_id": 1,
    "block_number": 26000000,
    "block_hash": bh("a"),
    "state_root": bh("b"),
}


def lanes(result="9"):
    return [
        {
            "lane": "EVENT_STORAGE_RECONSTRUCTION",
            "result_commitment_sha256": h(result),
            "source_commitment_sha256": h("1"),
            "producer_commitment_sha256": h("4"),
        },
        {
            "lane": "DIRECT_CONTRACT_READ",
            "result_commitment_sha256": h(result),
            "source_commitment_sha256": h("2"),
            "producer_commitment_sha256": h("5"),
        },
        {
            "lane": "EVM_REPLAY",
            "result_commitment_sha256": h(result),
            "source_commitment_sha256": h("3"),
            "producer_commitment_sha256": h("6"),
        },
    ]


def triad(subject="7", result="9"):
    return seal_triad(h(subject), ANCHOR, h("8"), lanes(result))


class TruthEngineTests(unittest.TestCase):
    def test_valid_triad_passes(self):
        value = triad()
        self.assertEqual(validate_triad(value), [])

    def test_exact_parity(self):
        result = evaluate_triad(triad())
        self.assertTrue(result["parity"])
        self.assertEqual(result["verdict"], "PARITY")
        self.assertEqual(result["agreed_result_commitment_sha256"], h("9"))
        self.assertFalse(result["certification_claimed"])

    def test_one_lane_mismatch_fails_closed(self):
        value = triad()
        value["lanes"][2]["result_commitment_sha256"] = h("0")
        # Reseal after deliberately producing a well-formed disagreement.
        value.pop("triad_commitment_sha256")
        from integrity import canonical, digest
        value["triad_commitment_sha256"] = digest(canonical(value))
        result = evaluate_triad(value)
        self.assertFalse(result["parity"])
        self.assertEqual(result["verdict"], "MISMATCH")
        self.assertIsNone(result["agreed_result_commitment_sha256"])
        self.assertEqual(len(result["mismatch_ledger"]), 3)

    def test_missing_lane_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "exactly_three_lanes_required"):
            seal_triad(h("7"), ANCHOR, h("8"), lanes()[:2])

    def test_duplicate_lane_is_blocked(self):
        items = lanes()
        items[2]["lane"] = items[1]["lane"]
        with self.assertRaises(ValueError) as ctx:
            seal_triad(h("7"), ANCHOR, h("8"), items)
        self.assertIn("duplicate_lane", str(ctx.exception))

    def test_unknown_lane_is_blocked(self):
        items = lanes()
        items[2]["lane"] = "MAGIC"
        with self.assertRaisesRegex(ValueError, "lane_name_invalid"):
            seal_triad(h("7"), ANCHOR, h("8"), items)

    def test_shared_source_breaks_independence(self):
        items = lanes()
        items[2]["source_commitment_sha256"] = items[1]["source_commitment_sha256"]
        with self.assertRaisesRegex(ValueError, "source_independence_not_proven"):
            seal_triad(h("7"), ANCHOR, h("8"), items)

    def test_shared_producer_breaks_independence(self):
        items = lanes()
        items[2]["producer_commitment_sha256"] = items[1]["producer_commitment_sha256"]
        with self.assertRaisesRegex(ValueError, "producer_independence_not_proven"):
            seal_triad(h("7"), ANCHOR, h("8"), items)

    def test_anchor_block_hash_is_required(self):
        anchor = dict(ANCHOR)
        anchor["block_hash"] = "bad"
        with self.assertRaisesRegex(ValueError, "block_hash_invalid"):
            seal_triad(h("7"), anchor, h("8"), lanes())

    def test_semantics_commitment_is_required(self):
        with self.assertRaisesRegex(ValueError, "semantics_commitment_invalid"):
            seal_triad(h("7"), ANCHOR, "", lanes())

    def test_tamper_breaks_commitment(self):
        value = triad()
        value["state_anchor"]["block_number"] += 1
        self.assertIn("triad_commitment_mismatch", validate_triad(value))

    def test_unsorted_lanes_are_rejected(self):
        value = triad()
        value["lanes"].reverse()
        self.assertIn("lanes_not_canonically_sorted", validate_triad(value))

    def test_all_authorities_are_false(self):
        value = triad()
        for key in value["authorities"]:
            changed = copy.deepcopy(value)
            changed["authorities"][key] = True
            self.assertIn("authority_forbidden", validate_triad(changed))

    def test_batch_requires_complete_coverage(self):
        with self.assertRaisesRegex(ValueError, "batch_coverage_mismatch"):
            evaluate_batch([triad("1")], [h("1"), h("2")])

    def test_batch_duplicate_subject_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "duplicate_subject_triad"):
            evaluate_batch([triad("1"), triad("1")], [h("1")])

    def test_batch_duplicate_expected_subject_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "duplicate_expected_subject"):
            evaluate_batch([triad("1")], [h("1"), h("1")])

    def test_batch_all_parity(self):
        result = evaluate_batch([triad("2"), triad("1")], [h("1"), h("2")])
        self.assertTrue(result["all_parity"])
        self.assertTrue(result["coverage_complete"])
        self.assertEqual([x["subject_id"] for x in result["subjects"]], [h("1"), h("2")])

    def test_batch_reports_failed_subjects(self):
        good = triad("1")
        bad = triad("2")
        bad["lanes"][0]["result_commitment_sha256"] = h("0")
        bad.pop("triad_commitment_sha256")
        from integrity import canonical, digest
        bad["triad_commitment_sha256"] = digest(canonical(bad))
        result = evaluate_batch([good, bad], [h("1"), h("2")])
        self.assertFalse(result["all_parity"])
        self.assertEqual(result["failed_subject_ids"], [h("2")])
        self.assertFalse(result["phase_advance_authorized"])

    def test_invalid_expected_subject_id_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "expected_subject_id_invalid"):
            evaluate_batch([triad("1")], ["bad"])

    def test_protocol_fork_truth_never_certified(self):
        result = evaluate_triad(triad())
        self.assertFalse(result["certification_claimed"])
        self.assertFalse(result["phase_advance_authorized"])


if __name__ == "__main__":
    unittest.main()
