import unittest
from unittest.mock import patch
import zipfile

import verify_strategy_trials as v


class StrategyTrialTests(unittest.TestCase):
    def test_retained_offline_trials_reproduce_without_network_or_admission(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')):
            first = v.verify(v.HERE / 'inputs/strategy-trials.zip')
            self.assertEqual(first, v.verify(v.HERE / 'inputs/strategy-trials.zip'))
        self.assertEqual(first['historical_cases'], 1)
        self.assertEqual(first['new_trials'], 2)
        self.assertEqual(first['new_holdout_cases'], 0)
        self.assertEqual(first['upstream_requests'], 0)
        self.assertTrue(first['failed_first_attempt_retained'])
        self.assertIsNone(first['complete_profit_wei'])
        self.assertFalse(first['census_closed'])

    def test_missing_test_and_invented_metric_rejected(self):
        with zipfile.ZipFile(v.HERE / 'inputs/strategy-trials.zip') as z:
            raw = z.read('offline-002/normal.log')
        changes = [raw.replace(b'[PASS] testAaveWithSameBidCannotRepayAndRollsBack()', b'[FAIL] removed()'),
                   raw.replace(b'NQC_TRIAL_AAVE_SHORTFALL_BEFORE_GAS_WEI: 5101616615551362',
                               b'NQC_TRIAL_AAVE_SHORTFALL_BEFORE_GAS_WEI: 0'),
                   raw.replace(b'custom error 0x930bb771', b'custom error 0x00000000')]
        for changed in changes:
            with self.assertRaises(ValueError): v.metrics(changed)

    def test_changed_archive_rejected_before_execution(self):
        with patch.object(v.Path, 'read_bytes', return_value=b'altered'), self.assertRaisesRegex(ValueError, 'archive digest'):
            v.verify(v.HERE / 'inputs/strategy-trials.zip')


if __name__ == '__main__':
    unittest.main()
