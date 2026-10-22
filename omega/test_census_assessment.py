import copy
import unittest
from pathlib import Path

from census_assessment import load_strict, verify_assessment

HERE = Path(__file__).resolve().parent


class CensusAssessmentTests(unittest.TestCase):
    def setUp(self):
        self.value = load_strict(HERE / "census_assessment.json")

    def test_baseline_passes(self):
        self.assertEqual(verify_assessment(self.value), [])

    def test_never_accepts_certification(self):
        for key, val in (("census_closed", True), ("certified_components", 1)):
            value = copy.deepcopy(self.value)
            value[key] = val
            self.assertIn("unsupported_certification_claim", verify_assessment(value))

    def test_each_component_certification_is_forbidden(self):
        for index in range(9):
            value = copy.deepcopy(self.value)
            value["components"][index]["component_certified"] = True
            self.assertIn("component_certification_forbidden", verify_assessment(value))

    def test_all_component_ids_are_exact(self):
        for index in range(9):
            value = copy.deepcopy(self.value)
            value["components"][index]["id"] = 999
            self.assertIn("component_ids_invalid", verify_assessment(value))

    def test_partial_requires_evidence(self):
        for index, item in enumerate(self.value["components"]):
            if item["status"] == "not_evidenced":
                continue
            value = copy.deepcopy(self.value)
            value["components"][index]["evidence"] = []
            self.assertIn("partial_without_evidence", verify_assessment(value))

    def test_blob_hashes_are_strict(self):
        value = copy.deepcopy(self.value)
        value["components"][0]["evidence"][0]["git_blob"] = "0" * 39
        self.assertIn("evidence_blob_invalid", verify_assessment(value))

    def test_paths_cannot_escape(self):
        value = copy.deepcopy(self.value)
        value["components"][0]["evidence"][0]["path"] = "nqc-census/../secret"
        self.assertIn("evidence_path_invalid", verify_assessment(value))

    def test_summary_cannot_be_inflated(self):
        value = copy.deepcopy(self.value)
        value["summary"]["foundational_partial"] = 9
        self.assertIn("summary_mismatch", verify_assessment(value))

    def test_unknown_status_is_rejected(self):
        value = copy.deepcopy(self.value)
        value["components"][0]["status"] = "certified"
        errors = verify_assessment(value)
        self.assertIn("status_invalid", errors)
        self.assertIn("summary_mismatch", errors)

    def test_duplicate_json_key_rejected(self):
        path = HERE / "duplicate.json"
        try:
            path.write_text('{"a":1,"a":2}')
            with self.assertRaisesRegex(ValueError, "duplicate_json_key"):
                load_strict(path)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
