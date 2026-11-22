"""Reject false classifications and unbound sources; native replay is recorded separately."""
import copy
from pathlib import Path
import tempfile
import unittest

from superhunter import product_iam_native as iam
from superhunter.product_reasoning import EvidenceError
from superhunter.safe_io import read_artifact, strict_json


class IAMNativeTests(unittest.TestCase):
    def setUp(self):
        self.native = strict_json(read_artifact(iam.ROOT, 'superhunter/product_supply/iam-native-sample.json'))
        self.payload = iam.inputs()

    def test_native_sample_preserves_permissions_and_unknown_actions(self):
        rows = iam.validate(self.native, self.payload)
        self.assertEqual(rows['permissions']['review_state'], 'permissions_management_present')
        self.assertEqual(rows['wildcard']['review_state'], 'permissions_management_present')
        self.assertEqual(rows['unknown']['review_state'], 'unknown_action')
        self.assertEqual(rows['denied']['access_levels']['Permissions management'], [])

    def test_erasing_a_permission_cannot_turn_positive_into_clean(self):
        self.native['cases']['permissions']['access_levels']['Permissions management'] = []
        with self.assertRaisesRegex(EvidenceError, 'owned policy witness'):
            iam.validate(self.native, self.payload)

    def test_unknown_action_cannot_be_silently_classified_as_known(self):
        self.native['cases']['unknown']['unknown_actions'] = []
        with self.assertRaisesRegex(EvidenceError, 'owned policy witness'):
            iam.validate(self.native, self.payload)

    def test_deny_only_control_cannot_publish_an_allow(self):
        self.native['cases']['denied']['expanded']['Statement'][0]['Effect'] = 'Allow'
        with self.assertRaisesRegex(EvidenceError, 'owned policy witness'):
            iam.validate(self.native, self.payload)

    def test_missing_control_and_wrong_version_fail(self):
        for mutate in (lambda row: row['cases'].pop('readonly'), lambda row: row.update(version='0.0')):
            changed = copy.deepcopy(self.native)
            mutate(changed)
            with self.assertRaisesRegex(EvidenceError, 'control membership'):
                iam.validate(changed, self.payload)

    def test_extra_python_module_and_replaced_source_fail_before_data_use(self):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp)
            package = work/'lib/policy_sentry'
            package.mkdir(parents=True)
            path = package/'unexpected.py'
            path.write_text('OWNED = 1\n')
            with self.assertRaisesRegex(EvidenceError, 'membership'):
                iam.verify_installed(work, {'python_git_blobs': {}})
            with self.assertRaisesRegex(EvidenceError, 'Git blob'):
                iam.verify_installed(work, {'python_git_blobs': {'policy_sentry/unexpected.py': '0'*40}})


if __name__ == '__main__':
    unittest.main()
