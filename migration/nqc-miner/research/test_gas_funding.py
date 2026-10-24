"""Actual CLI checks with artificial terms; never evidence of Titan commitment."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


MODULE = Path(__file__).resolve().parents[1]


class GasFundingTests(unittest.TestCase):
    def input(self):
        return json.loads((MODULE / "fixtures/gas_funding.synthetic.json").read_text())

    def command(self, data):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            path.write_text(json.dumps(data))
            return subprocess.run(
                [os.environ["NQC_MINER_TEST_BINARY"], "assess-gas-funding", "--input", str(path)],
                capture_output=True, text=True, check=False)

    def report(self, data):
        result = self.command(data)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def claimed(self):
        data = self.input()
        report = self.report(data)
        # Artificial external-labelled metadata exercises the structural path only.
        data["claim"] = dict(
            sponsor="titan", scope="exact_execution", basis="external_observation",
            plan_sha256=report["plan_sha256"], evidence_artifact_sha256="44" * 32,
            observed_at=900, expires_at=1100, revoked=False, operator_recourse_allowed=False,
            caps=dict(included_success_wei=report["maximum_network_cost_wei"],
                      included_failure_wei=report["maximum_network_cost_wei"], not_included_wei="0"))
        return data

    def test_about_reports_current_titan_only_policy_with_no_operational_funding(self):
        result = subprocess.run([os.environ["NQC_MINER_TEST_BINARY"], "about"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        about = json.loads(result.stdout)
        p = about["funding_policy"]
        self.assertEqual(p["id"], "nqc-miner-titan-only-gas-v1")
        self.assertEqual(p["designated_gas_sponsor"], "titan")
        self.assertEqual(p["operator_gas_budget_wei"], "0")
        self.assertFalse(p["operator_prefunding_allowed"])
        self.assertFalse(p["operator_gas_fallback_allowed"])
        self.assertFalse(p["operator_principal_collateral_guarantees_allowed"])
        self.assertFalse(p["spending_enabled"])
        self.assertFalse(about["signing_enabled"])
        self.assertFalse(about["observer_bridge_enabled"])
        self.assertEqual(about["gas_budget_mxn_centavos"], 0)

    def test_missing_claim_stays_unknown_and_large_wei_cost_is_exact(self):
        data = self.input()
        report = self.report(data)
        expected = data["plan"]["gas_limit"] * int(data["plan"]["max_fee_per_gas_wei"]) + int(data["plan"]["additional_network_fee_cap_wei"])
        self.assertGreater(expected, 2**53)
        self.assertEqual(report["maximum_network_cost_wei"], str(expected))
        self.assertIsNone(report["supplied_claim"])
        self.assertFalse(report["declared_terms_consistent"])
        self.assertEqual(report["terms_blockers"], ["execution_specific_titan_terms_missing"])

    def test_matching_supplied_terms_never_become_authenticated_or_authorized(self):
        data = self.claimed()
        report = self.report(data)
        self.assertTrue(report["declared_terms_consistent"])
        self.assertEqual(report["supplied_claim"], data["claim"])
        self.assertEqual(len(report["operational_blockers"]), 3)
        for flag in ["input_state_authenticated", "sponsorship_authenticated", "execution_gas_coverage_verified",
                     "activation_allowed", "spending_authorized", "network_used"]:
            self.assertFalse(report[flag])
        self.assertEqual(report, self.report(data))

    def test_plan_and_review_mutations_reject_previously_consistent_terms(self):
        data = self.claimed()
        cases = [
            ("plan", "operator_prefund_wei", "1", "operator_prefunding_forbidden"),
            ("plan", "operator_gas_fallback", True, "operator_gas_fallback_forbidden"),
            ("plan", "bundle_digest", "55" * 32, "claim_plan_mismatch"),
            ("context", "now_unix_seconds", 1100, "sponsorship_claim_not_current"),
            ("claim", "scope", "general_statement", "general_sponsorship_is_not_execution_coverage"),
            ("claim", "revoked", True, "sponsorship_claim_revoked"),
        ]
        before = self.report(data)
        for parent, key, value, reason in cases:
            candidate = copy.deepcopy(data)
            candidate[parent][key] = value
            result = self.report(candidate)
            self.assertIn(reason, result["terms_blockers"])
            self.assertNotEqual(before["input_sha256"], result["input_sha256"])
            self.assertFalse(result["execution_gas_coverage_verified"])
        candidate = copy.deepcopy(data)
        candidate["context"]["parent_block"]["hash"] = "66" * 32
        self.assertIn("parent_changed_or_target_stale", self.report(candidate)["terms_blockers"])

    def test_no_success_only_coverage_and_unknown_is_not_zero(self):
        data = self.claimed()
        for field, reason in [("included_failure_wei", "failure_terms_unknown"),
                              ("included_success_wei", "success_terms_unknown"),
                              ("not_included_wei", "not_included_terms_unknown")]:
            candidate = copy.deepcopy(data)
            candidate["claim"]["caps"][field] = None
            self.assertIn(reason, self.report(candidate)["terms_blockers"])
            del candidate["claim"]["caps"][field]
            self.assertIn(reason, self.report(candidate)["terms_blockers"])
        data["claim"]["caps"]["included_failure_wei"] = "0"
        self.assertIn("failure_cap_insufficient", self.report(data)["terms_blockers"])

    def test_legacy_budget_and_supplied_authorization_flags_are_not_accepted(self):
        data = self.claimed()
        for parent in [None, "plan", "context", "claim"]:
            candidate = copy.deepcopy(data)
            target = candidate if parent is None else candidate[parent]
            target["spending_authorized"] = True
            self.assertNotEqual(self.command(candidate).returncode, 0)
        data["plan"]["gas_budget_mxn_centavos"] = 200_000
        self.assertNotEqual(self.command(data).returncode, 0)
        for value in [1, True, "01", "-1", "1e9", str(2**256)]:
            candidate = self.input()
            candidate["plan"]["max_fee_per_gas_wei"] = value
            self.assertNotEqual(self.command(candidate).returncode, 0)


if __name__ == "__main__":
    unittest.main()
