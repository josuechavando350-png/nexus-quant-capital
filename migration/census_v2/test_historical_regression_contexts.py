"""Reject cross-context provenance drift before running historical tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import replay_historical_regressions as m


class HistoricalContextGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = m.original_files()
        cls.nine = (m.EVIDENCE / "universe-nine.json").read_bytes()
        cls.seven = (m.EVIDENCE / "universe-seven.json").read_bytes()
        cls.current = cls.original[m.CATALOG]
        cls.meta = [json.loads((m.EVIDENCE / ("debt-" + n + ".json")).read_bytes())
                    for n in ("run", "artifact", "commit")]
        cls.pin = {"run_id": 37832286518, "head_sha": "5b79e7be1c185cbb4924d592991b9c990fc0465a",
                   "artifact_id": 11573678487,
                   "artifact_digest": "sha256:" + m.ARCHIVES["original-five-stage-authority.zip"]}

    def test_current_rows_preserve_both_historical_contexts(self):
        for raw, pin, count in ((self.seven, m.SEVEN, 7), (self.nine, m.NINE, 9)):
            report = m.catalog_compatibility(raw, pin, self.current, count)
            self.assertEqual(len(report["unchanged_historical_resolved_rows"]), count)
            self.assertFalse(report["current_capital_admission_changed"])
        self.assertNotEqual(m.blob(self.current), m.NINE)

    def test_wrong_historical_version_rejected(self):
        with self.assertRaisesRegex(ValueError, "blob changed"):
            m.catalog_compatibility(self.nine, m.SEVEN, self.current, 7)

    def test_boolean_to_integer_family_drift_rejected(self):
        doc = json.loads(self.current)
        family = next(r for r in doc["families"] if r["id"] == "COLLATERALIZED_BORROWING")
        family["terminally_resolved"] = 1
        with self.assertRaisesRegex(ValueError, "binding changed"):
            m.catalog_compatibility(self.nine, m.NINE, m.canonical(doc), 9)

    def test_same_tree_wrong_commit_is_rejected(self):
        values = copy.deepcopy(self.meta)
        values[2]["sha"] = "f" * 40
        with self.assertRaisesRegex(ValueError, "commit/tree"):
            m.metadata_identity(*map(m.canonical, values), self.pin)

    def test_run_tree_or_artifact_drift_rejected(self):
        for index, field, value in ((0, "conclusion", "failure"), (1, "digest", "sha256:" + "a" * 64)):
            with self.subTest(field=field):
                values = copy.deepcopy(self.meta)
                values[index][field] = value
                with self.assertRaises(ValueError):
                    m.metadata_identity(*map(m.canonical, values), self.pin)
        values = copy.deepcopy(self.meta)
        values[2]["tree"]["sha"] = "f" * 40
        with self.assertRaisesRegex(ValueError, "commit/tree"):
            m.metadata_identity(*map(m.canonical, values), self.pin)

    def test_fresh_copy_preserves_every_other_byte_and_refuses_reuse(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "replay"
            m.create_copy(root, self.original, self.seven)
            for path, raw in self.original.items():
                self.assertEqual((root / path).read_bytes(), self.seven if path == m.CATALOG else raw)
            with self.assertRaises(FileExistsError):
                m.create_copy(root, self.original, self.nine)
        self.assertEqual(m.original_files(), self.original)


if __name__ == "__main__":
    unittest.main()
