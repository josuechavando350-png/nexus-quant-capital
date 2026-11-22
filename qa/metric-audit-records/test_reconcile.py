"""Document interpretation regressions on a short, invented auditor note."""
import unittest

from reconcile import sherlock


class DispositionTest(unittest.TestCase):
    note = """
Issues Found
High    Medium
1       1

Issues Not Fixed and Not Acknowledged
High    Medium
0       0

Issue H-1: Example A
This issue has been acknowledged by the team but won't be fixed at this time.
Issue M-1: Example B
No disposition recorded here.
"""

    def test_summary_zero_preserves_acknowledgment_and_uncertainty(self):
        disposition = sherlock(self.note)["disposition_wording"]
        self.assertEqual(disposition, {"acknowledged_no_fix_at_report_time": 1, "unclassified_wording": 1})

    def test_summary_disagreement_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "summary and detailed headings disagree"):
            sherlock(self.note.replace("1       1", "1       2"))

    def test_conflicting_dispositions_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Conflicting disposition"):
            sherlock(self.note.replace("Issue M-1:", "Fix confirmed.\nIssue M-1:"))

    def test_duplicate_heading_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            sherlock(self.note.replace("Issue M-1:", "Issue H-1:"))


if __name__ == "__main__":
    unittest.main()
