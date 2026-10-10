from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile
from verify_native import verify, metrics, HERE


class NativeRealizationTests(unittest.TestCase):
    def test_real_replay_has_no_network_or_profit_admission(self):
        with patch("urllib.request.urlopen",side_effect=AssertionError("network forbidden")):
            r=verify(HERE/"inputs/native-realization.zip")
        self.assertEqual(r["operator_native_increase_wei"],"240390311727552")
        self.assertIsNone(r["complete_profit_wei"])
        self.assertFalse(r["native_wallet_authority_and_upfront_gas_proven"])
        for p in r["gas_profiles"]:
            self.assertGreater(int(p["remaining_for_other_costs_at_historical_base_fee_wei"]),0)
            self.assertLess(int(p["remaining_for_other_costs_at_1_gwei_wei"]),0)

    def test_wrong_calldata_cost_rejected(self):
        with zipfile.ZipFile(HERE/"inputs/native-realization.zip") as z:
            raw=z.read("offline-001/normal.log")
        changed=raw.replace(b"  NQC_NATIVE_INTRINSIC_4_16: 27060",b"  NQC_NATIVE_INTRINSIC_4_16: 0")
        self.assertNotEqual(raw,changed)
        with self.assertRaisesRegex(ValueError,"intrinsic component"):metrics(changed)


if __name__ == "__main__":unittest.main()
