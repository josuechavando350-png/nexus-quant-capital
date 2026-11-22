"""Reject fabricated discovery credit and unreplayed or unrepaired native witnesses."""
import copy
from pathlib import Path
import re
import tempfile
import unittest

from superhunter import product_python_fuzz_native as fuzz
from superhunter.product_reasoning import EvidenceError
from superhunter.safe_io import canonical, read_artifact, strict_json


class PythonFuzzNativeTests(unittest.TestCase):
    def setUp(self):
        self.payload = fuzz.inputs()
        self.evidence = strict_json(read_artifact(
            fuzz.ROOT, 'superhunter/product_supply/python-fuzz-native-sample.json'))

    def test_real_native_receipt_has_discovery_and_original_repaired_replays(self):
        report = fuzz.validate(self.evidence, self.payload)
        self.assertTrue(report['fresh_campaign']['counterexample_generated'])
        self.assertTrue(report['fresh_campaign']['repaired_replay_passed'])
        self.assertEqual(report['pinned_counterexample']['observed_remaining'], 252)
        self.assertEqual(report['repaired_campaign']['executed_units'], 512)

    def test_version_or_native_extension_substitution_is_rejected(self):
        for field, value in (('version', '0.0'), ('native_modules', {})):
            changed = copy.deepcopy(self.evidence)
            changed['discovery']['engine'][field] = value
            with self.assertRaisesRegex(EvidenceError, 'pinned native engine'):
                fuzz.validate(changed, self.payload)

    def test_zero_callbacks_cannot_receive_discovery_credit(self):
        self.evidence['discovery']['observations'] = []
        with self.assertRaisesRegex(EvidenceError, 'real bounded callback'):
            fuzz.validate(self.evidence, self.payload)

    def test_crash_without_invariant_failure_is_rejected(self):
        self.evidence['discovery']['returncode'] = -11
        with self.assertRaisesRegex(EvidenceError, 'owned invariant violation'):
            fuzz.validate(self.evidence, self.payload)

    def test_saved_corpus_must_equal_the_observed_failing_input(self):
        self.evidence['discovery']['counterexample_hex'] = '0102'
        with self.assertRaisesRegex(EvidenceError, 'failing corpus'):
            fuzz.validate(self.evidence, self.payload)

    def test_fabricated_accounting_result_is_recomputed_independently(self):
        self.evidence['discovery']['observations'][-1]['observed_remaining'] = 0
        with self.assertRaisesRegex(EvidenceError, 'independent witness'):
            fuzz.validate(self.evidence, self.payload)

    def test_counterexample_description_cannot_disagree_with_input(self):
        self.evidence['discovery']['violation']['amount'] = 255
        with self.assertRaisesRegex(EvidenceError, 'owned invariant violation'):
            fuzz.validate(self.evidence, self.payload)

    def test_repaired_implementation_must_reject_the_actual_witness(self):
        self.evidence['discovered_repaired']['observations'][-1]['observed_remaining'] = 252
        with self.assertRaisesRegex(EvidenceError, 'independent witness'):
            fuzz.validate(self.evidence, self.payload)

    def test_missing_clean_case_and_missing_replay_are_rejected(self):
        for missing in ('case', 'replay'):
            changed = copy.deepcopy(self.evidence)
            if missing == 'case':
                changed['clean']['observations'] = changed['clean']['observations'][1:]
            else:
                del changed['pinned_repaired']
            with self.assertRaises(EvidenceError):
                fuzz.validate(changed, self.payload)

    def test_shortened_repaired_campaign_cannot_claim_full_budget(self):
        self.evidence['repaired_campaign']['observations'].pop()
        with self.assertRaisesRegex(EvidenceError, 'execution and coverage statistics'):
            fuzz.validate(self.evidence, self.payload)

    def test_boolean_is_not_an_accounting_integer(self):
        self.evidence['clean']['observations'][0]['observed_remaining'] = False
        with self.assertRaisesRegex(EvidenceError, 'integer or rejection'):
            fuzz.validate(self.evidence, self.payload)

    def test_campaign_cannot_expand_into_arbitrary_inputs(self):
        self.evidence['discovery']['observations'][0]['input_hex'] = '00' * 4096
        with self.assertRaisesRegex(EvidenceError, 'bounded byte string'):
            fuzz.validate(self.evidence, self.payload)

    def test_normalization_excludes_process_identifiers_but_not_outcomes(self):
        before = fuzz.validate(self.evidence, self.payload)
        original = self.evidence['discovery']['stderr']
        changed = re.sub(r'==[0-9]+==', '==531==', original)
        self.assertNotEqual(original, changed)
        self.evidence['discovery']['stderr'] = changed
        after = fuzz.validate(self.evidence, self.payload)
        self.assertEqual(canonical(before), canonical(after))

    def test_unpinned_installed_code_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            package = work/'lib/atheris'
            package.mkdir(parents=True)
            (package/'unexpected.py').write_text('OWNED = 1\n')
            with self.assertRaisesRegex(EvidenceError, 'code membership'):
                fuzz.verify_installed(work, {'installed_members': {}})
            proof = {'installed_members': {'atheris/unexpected.py': {'bytes': 10, 'sha256': '0' * 64}}}
            with self.assertRaisesRegex(EvidenceError, 'source or notice'):
                fuzz.verify_installed(work, proof)


if __name__ == '__main__':
    unittest.main()
