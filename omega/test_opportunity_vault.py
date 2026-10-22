from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from opportunity_vault import (
    COST_KINDS, query_dossiers, seal_dossier, store_dossier, validate_dossier,
)


def h(ch: str = "1") -> str:
    return ch * 64


def addr(ch: str = "1") -> str:
    return "0x" + ch * 40


def blockhash(ch: str = "1") -> str:
    return "0x" + ch * 64


def unsigned_fixture(*, protocol="aave-v3", block=26000000, verdict="OBSERVAR",
                     competition_complete=False, economics_complete=False):
    costs = {}
    for index, kind in enumerate(COST_KINDS):
        if economics_complete:
            costs[kind] = {"known": True, "usd_wad": str(index + 1), "evidence_sha256": h("a")}
        else:
            costs[kind] = {"known": False, "usd_wad": None, "evidence_sha256": None}
    competition = (
        {
            "winner_address": addr("b"),
            "oracle_update_block": block - 1,
            "winner_block": block,
            "builder_payment_share_wad": "500000000000000000",
            "evidence_sha256": h("c"),
            "complete": True,
        }
        if competition_complete
        else {
            "winner_address": None, "oracle_update_block": None, "winner_block": None,
            "builder_payment_share_wad": None, "evidence_sha256": None, "complete": False,
        }
    )
    return {
        "schema": "nqc.omega.census-opportunity-dossier.v1",
        "record_scope": "CENSUS_OFFLINE_EVIDENCE_ONLY",
        "state_anchor": {
            "chain_id": 1, "block_number": block,
            "block_hash": blockhash("1"), "state_root": blockhash("2"),
        },
        "protocol": {
            "protocol_id": protocol, "deployment": addr("3"),
            "market_id": h("4"), "version_commitment": h("5"),
        },
        "position": {
            "borrower": addr("6"), "collateral_asset": addr("7"),
            "debt_asset": addr("8"), "position_commitment": h("9"),
        },
        "decision": {
            "verdict": verdict, "reason_code": "INCOMPLETE_EVIDENCE",
            "decision_model_commitment": h("a"), "truth_complete": False,
            "economics_complete": economics_complete,
            "competition_complete": competition_complete,
        },
        "economics": {
            "gross_value_usd_wad": "1000" if economics_complete else None,
            "net_success_usd_wad": "900" if economics_complete else None,
            "expected_value_usd_wad": "100" if economics_complete else None,
            "costs": costs, "complete": economics_complete, "model_commitment": h("b"),
        },
        "competition": competition,
        "scenarios": [
            {"name": "baseline", "commitment_sha256": h("d"), "material_discrepancy": False}
        ],
        "outcome": {
            "status": "UNOBSERVED", "transaction_hash": None,
            "nqc_execution": False, "realized_pnl_usd_wad": None,
        },
        "evidence": [
            {"kind": "fixture", "locator": "synthetic-test-only", "sha256": h("e")}
        ],
        "blockers": ["COMPETITION_INCOMPLETE", "TRUTH_INCOMPLETE"],
        "authorities": {
            "can_sign": False, "can_broadcast": False, "can_spend": False,
            "phase_advance_authorized": False, "census_closed": False,
        },
    }


class OpportunityVaultTests(unittest.TestCase):
    def test_valid_incomplete_dossier_passes(self):
        record = seal_dossier(unsigned_fixture())
        self.assertEqual(validate_dossier(record), [])

    def test_go_is_forbidden_in_census(self):
        raw = unsigned_fixture(verdict="GO")
        with self.assertRaisesRegex(ValueError, "census_go_forbidden"):
            seal_dossier(raw)

    def test_every_authority_is_forbidden(self):
        for key in unsigned_fixture()["authorities"]:
            raw = unsigned_fixture()
            raw["authorities"][key] = True
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "authority_forbidden"):
                seal_dossier(raw)

    def test_opportunity_identity_is_bound_to_position_and_block(self):
        record = seal_dossier(unsigned_fixture())
        changed = copy.deepcopy(record)
        changed["state_anchor"]["block_number"] += 1
        errors = validate_dossier(changed)
        self.assertIn("opportunity_id_mismatch", errors)
        self.assertIn("dossier_commitment_mismatch", errors)

    def test_cost_vector_requires_all_fourteen_categories(self):
        raw = unsigned_fixture()
        raw["economics"]["costs"].pop(COST_KINDS[0])
        with self.assertRaisesRegex(ValueError, "cost_vector_incomplete"):
            seal_dossier(raw)

    def test_complete_economics_requires_values_and_evidence(self):
        raw = unsigned_fixture(economics_complete=True)
        raw["economics"]["costs"]["Gas"]["evidence_sha256"] = None
        with self.assertRaisesRegex(ValueError, "known_cost_missing_value_or_evidence"):
            seal_dossier(raw)

    def test_incomplete_costs_must_be_explicit_nulls(self):
        raw = unsigned_fixture()
        raw["economics"]["costs"]["Gas"]["usd_wad"] = "0"
        with self.assertRaisesRegex(ValueError, "unknown_cost_must_be_null"):
            seal_dossier(raw)

    def test_competition_completeness_is_all_or_none(self):
        raw = unsigned_fixture()
        raw["competition"]["winner_block"] = 26000000
        with self.assertRaisesRegex(ValueError, "incomplete_competition_must_be_null"):
            seal_dossier(raw)

    def test_historical_market_outcome_never_becomes_nqc_pnl(self):
        raw = unsigned_fixture()
        raw["outcome"] = {
            "status": "HISTORICAL_MARKET_ONLY", "transaction_hash": blockhash("f"),
            "nqc_execution": False, "realized_pnl_usd_wad": None,
        }
        record = seal_dossier(raw)
        self.assertEqual(validate_dossier(record), [])
        changed = copy.deepcopy(record)
        changed["outcome"]["realized_pnl_usd_wad"] = "1"
        self.assertIn("realized_pnl_claim_forbidden", validate_dossier(changed))

    def test_nqc_execution_claim_is_forbidden(self):
        raw = unsigned_fixture()
        raw["outcome"]["nqc_execution"] = True
        with self.assertRaisesRegex(ValueError, "nqc_execution_claim_forbidden"):
            seal_dossier(raw)

    def test_store_is_content_addressed_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            record = seal_dossier(unsigned_fixture())
            left = store_dossier(Path(temp), record)
            right = store_dossier(Path(temp), record)
            self.assertEqual(left, right)
            self.assertIn(record["opportunity_id"], left.name)
            self.assertIn(record["dossier_commitment_sha256"], left.name)

    def test_tampered_existing_record_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            record = seal_dossier(unsigned_fixture())
            path = store_dossier(Path(temp), record)
            path.write_text("tampered")
            with self.assertRaisesRegex(ValueError, "existing_dossier_mismatch"):
                store_dossier(Path(temp), record)
            self.assertEqual(path.read_text(), "tampered")

    def test_query_filters_valid_records(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            a = seal_dossier(unsigned_fixture(protocol="aave-v3", block=100))
            b = seal_dossier(unsigned_fixture(protocol="morpho-blue", block=200, verdict="NO-GO"))
            store_dossier(root, a)
            store_dossier(root, b)
            self.assertEqual(len(query_dossiers(root)), 2)
            self.assertEqual(query_dossiers(root, protocol_id="morpho-blue")[0]["block_number"], 200)
            self.assertEqual(query_dossiers(root, verdict="NO-GO")[0]["protocol_id"], "morpho-blue")
            self.assertEqual(query_dossiers(root, min_block=150, max_block=250)[0]["block_number"], 200)

    def test_query_fails_closed_on_unreviewed_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store_dossier(root, seal_dossier(unsigned_fixture()))
            (root / "notes.txt").write_text("not a dossier")
            with self.assertRaisesRegex(ValueError, "unreviewed_vault_entry"):
                query_dossiers(root)

    def test_symlink_vault_directory_is_forbidden(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            actual = root / "actual"
            actual.mkdir()
            link = root / "link"
            link.symlink_to(actual, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink_vault_directory"):
                store_dossier(link, seal_dossier(unsigned_fixture()))

    def test_unknown_top_level_field_fails(self):
        record = seal_dossier(unsigned_fixture())
        record["surprise"] = True
        self.assertIn("top_level_shape_invalid", validate_dossier(record))

    def test_blockers_are_sorted_unique(self):
        raw = unsigned_fixture()
        raw["blockers"] = ["B", "A", "A"]
        with self.assertRaisesRegex(ValueError, "blockers_invalid"):
            seal_dossier(raw)

    def test_decision_links_economic_and_competition_completeness(self):
        raw = unsigned_fixture()
        raw["decision"]["economics_complete"] = True
        with self.assertRaisesRegex(ValueError, "decision_economics_link_mismatch"):
            seal_dossier(raw)

    def test_complete_competition_rejects_reverse_block_order(self):
        raw = unsigned_fixture(competition_complete=True)
        raw["competition"]["oracle_update_block"] = raw["competition"]["winner_block"] + 1
        with self.assertRaisesRegex(ValueError, "complete_competition_missing_fields"):
            seal_dossier(raw)


if __name__ == "__main__":
    unittest.main()
