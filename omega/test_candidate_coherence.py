import copy
import unittest

from integrity import canonical, digest
from opportunity_vault import COST_KINDS, seal_dossier
from truth_engine import seal_triad
from causal_graph import seal_graph
from liquidation_order_book import seal_book
from oracle_semantics import seal_registry as seal_oracle_registry
from protocol_adapters import CAPABILITIES, seal_registry as seal_adapter_registry
from candidate_coherence import evaluate_candidate_coherence


def h(ch):
    return ch * 64


def bh(ch):
    return "0x" + ch * 64


def addr(ch):
    return "0x" + ch * 40


ANCHOR = {
    "chain_id": 1,
    "block_number": 26000000,
    "block_hash": bh("a"),
    "state_root": bh("b"),
}
POS = h("9")
MARKET = h("4")
ORACLE = h("3")
DEBT_ORACLE = h("8")
INTEREST = h("5")
LIQ = h("6")
ROUTE = h("7")
ADAPTER = h("1")
DEPLOYMENT = addr("3")
VERSION = h("5")


def dossier():
    costs = {
        kind: {"known": False, "usd_wad": None, "evidence_sha256": None}
        for kind in COST_KINDS
    }
    unsigned = {
        "schema": "nqc.omega.census-opportunity-dossier.v1",
        "record_scope": "CENSUS_OFFLINE_EVIDENCE_ONLY",
        "state_anchor": copy.deepcopy(ANCHOR),
        "protocol": {
            "protocol_id": "aave-v3",
            "deployment": DEPLOYMENT,
            "market_id": MARKET,
            "version_commitment": VERSION,
        },
        "position": {
            "borrower": addr("6"),
            "collateral_asset": addr("7"),
            "debt_asset": addr("8"),
            "position_commitment": POS,
        },
        "decision": {
            "verdict": "OBSERVAR",
            "reason_code": "FOUNDATION_ONLY",
            "decision_model_commitment": h("a"),
            "truth_complete": True,
            "economics_complete": False,
            "competition_complete": False,
        },
        "economics": {
            "gross_value_usd_wad": None,
            "net_success_usd_wad": None,
            "expected_value_usd_wad": None,
            "costs": costs,
            "complete": False,
            "model_commitment": h("b"),
        },
        "competition": {
            "winner_address": None,
            "oracle_update_block": None,
            "winner_block": None,
            "builder_payment_share_wad": None,
            "evidence_sha256": None,
            "complete": False,
        },
        "scenarios": [
            {"name": "baseline", "commitment_sha256": h("d"), "material_discrepancy": False}
        ],
        "outcome": {
            "status": "UNOBSERVED",
            "transaction_hash": None,
            "nqc_execution": False,
            "realized_pnl_usd_wad": None,
        },
        "evidence": [
            {"kind": "fixture", "locator": "h12-synthetic", "sha256": h("e")}
        ],
        "blockers": ["ECONOMICS_INCOMPLETE"],
        "authorities": {
            "can_sign": False,
            "can_broadcast": False,
            "can_spend": False,
            "phase_advance_authorized": False,
            "census_closed": False,
        },
    }
    return seal_dossier(unsigned)


def triad():
    lanes = [
        {
            "lane": "EVENT_STORAGE_RECONSTRUCTION",
            "result_commitment_sha256": h("c"),
            "source_commitment_sha256": h("1"),
            "producer_commitment_sha256": h("4"),
        },
        {
            "lane": "DIRECT_CONTRACT_READ",
            "result_commitment_sha256": h("c"),
            "source_commitment_sha256": h("2"),
            "producer_commitment_sha256": h("5"),
        },
        {
            "lane": "EVM_REPLAY",
            "result_commitment_sha256": h("c"),
            "source_commitment_sha256": h("3"),
            "producer_commitment_sha256": h("6"),
        },
    ]
    return seal_triad(POS, ANCHOR, h("f"), lanes)


def graph():
    nodes = [
        {"node_id": POS, "kind": "POSITION", "evidence_sha256": h("e")},
        {"node_id": MARKET, "kind": "MARKET", "evidence_sha256": h("e")},
        {"node_id": ORACLE, "kind": "ORACLE", "evidence_sha256": h("e")},
        {"node_id": INTEREST, "kind": "INTEREST_MODEL", "evidence_sha256": h("e")},
        {"node_id": LIQ, "kind": "LIQUIDITY_SOURCE", "evidence_sha256": h("e")},
        {"node_id": ROUTE, "kind": "ROUTE", "evidence_sha256": h("e")},
    ]
    edges = [
        {"from_node": POS, "to_node": MARKET, "kind": "POSITION_MARKET", "evidence_sha256": h("d")},
        {"from_node": POS, "to_node": ORACLE, "kind": "POSITION_ORACLE", "evidence_sha256": h("d")},
        {"from_node": POS, "to_node": INTEREST, "kind": "POSITION_INTEREST", "evidence_sha256": h("d")},
        {"from_node": POS, "to_node": LIQ, "kind": "POSITION_LIQUIDITY", "evidence_sha256": h("d")},
        {"from_node": POS, "to_node": ROUTE, "kind": "POSITION_ROUTE", "evidence_sha256": h("d")},
        {"from_node": MARKET, "to_node": ORACLE, "kind": "MARKET_ORACLE", "evidence_sha256": h("d")},
        {"from_node": MARKET, "to_node": INTEREST, "kind": "MARKET_INTEREST", "evidence_sha256": h("d")},
        {"from_node": ROUTE, "to_node": LIQ, "kind": "ROUTE_LIQUIDITY", "evidence_sha256": h("d")},
    ]
    return seal_graph(
        {"chain_id": 1, "block_number": ANCHOR["block_number"], "block_hash": ANCHOR["block_hash"]},
        nodes, edges
    )


def book():
    return seal_book(
        {"chain_id": 1, "block_number": ANCHOR["block_number"], "block_hash": ANCHOR["block_hash"]},
        [{
            "position_id": POS,
            "oracle_id": ORACLE,
            "direction": "AT_OR_BELOW",
            "threshold_numerator": "100",
            "threshold_denominator": "1",
            "source_commitment_sha256": h("d"),
        }]
    )


def oracle_registry():
    return seal_oracle_registry(
        {"chain_id": 1, "block_number": ANCHOR["block_number"], "block_hash": ANCHOR["block_hash"]},
        [
            {
                "oracle_id": ORACLE,
                "semantic_class": "MARKET_PRICE",
                "base_asset_id": h("a"),
                "quote_asset_id": h("b"),
                "source_commitment_sha256": h("d"),
            },
            {
                "oracle_id": DEBT_ORACLE,
                "semantic_class": "EXCHANGE_RATE",
                "base_asset_id": h("c"),
                "quote_asset_id": h("d"),
                "source_commitment_sha256": h("e"),
            },
        ],
        [{
            "market_id": MARKET,
            "collateral_oracle_id": ORACLE,
            "debt_oracle_id": DEBT_ORACLE,
            "source_commitment_sha256": h("f"),
        }],
    )


def adapter_registry(missing=None, family="AAVE_V3", deployment=DEPLOYMENT, version=VERSION):
    missing = set(missing or ())
    capabilities = {
        name: {
            "supported": name not in missing,
            "evidence_sha256": None if name in missing else h("e"),
        }
        for name in CAPABILITIES
    }
    return seal_adapter_registry([{
        "adapter_id": ADAPTER,
        "protocol_family": family,
        "chain_id": 1,
        "deployment": deployment,
        "version_commitment_sha256": version,
        "implementation_git_blob": "b" * 40,
        "capabilities": capabilities,
        "source_commitment_sha256": h("c"),
    }])


def bundle(**overrides):
    data = {
        "dossier": dossier(),
        "triad": triad(),
        "graph_payload": graph(),
        "order_book_payload": book(),
        "oracle_registry_payload": oracle_registry(),
        "adapter_registry_payload": adapter_registry(),
    }
    data.update(overrides)
    return data


def reseal(value, commitment_key):
    value.pop(commitment_key, None)
    value[commitment_key] = digest(canonical(value))
    return value


class CandidateCoherenceTests(unittest.TestCase):
    def test_valid_bundle_is_foundation_coherent(self):
        result = evaluate_candidate_coherence(**bundle())
        self.assertEqual(result["status"], "FOUNDATION_COHERENT")
        self.assertFalse(result["certification_claimed"])

    def test_no_execution_authority_is_emitted(self):
        result = evaluate_candidate_coherence(**bundle())
        for key in (
            "go_authorized", "signing_authorized", "broadcast_authorized",
            "spending_authorized", "phase_advance_authorized", "census_closed",
        ):
            self.assertIs(result[key], False)

    def test_truth_mismatch_is_blocked(self):
        t = triad()
        t["lanes"][2]["result_commitment_sha256"] = h("0")
        reseal(t, "triad_commitment_sha256")
        with self.assertRaisesRegex(ValueError, "truth_parity_required"):
            evaluate_candidate_coherence(**bundle(triad=t))

    def test_dossier_truth_flag_is_required(self):
        d = dossier()
        d["decision"]["truth_complete"] = False
        reseal(d, "dossier_commitment_sha256")
        with self.assertRaisesRegex(ValueError, "dossier_truth_must_be_complete"):
            evaluate_candidate_coherence(**bundle(dossier=d))

    def test_truth_anchor_mismatch_is_blocked(self):
        t = triad()
        t["state_anchor"]["state_root"] = bh("c")
        reseal(t, "triad_commitment_sha256")
        with self.assertRaisesRegex(ValueError, "truth_anchor_mismatch"):
            evaluate_candidate_coherence(**bundle(triad=t))

    def test_graph_anchor_mismatch_is_blocked(self):
        g = graph()
        g["state_anchor"]["block_number"] += 1
        reseal(g, "graph_commitment_sha256")
        with self.assertRaisesRegex(ValueError, "graph_anchor_mismatch"):
            evaluate_candidate_coherence(**bundle(graph_payload=g))

    def test_order_book_anchor_mismatch_is_blocked(self):
        b = book()
        b["state_anchor"]["block_number"] += 1
        reseal(b, "book_commitment_sha256")
        with self.assertRaisesRegex(ValueError, "order_book_anchor_mismatch"):
            evaluate_candidate_coherence(**bundle(order_book_payload=b))

    def test_oracle_anchor_mismatch_is_blocked(self):
        o = oracle_registry()
        o["state_anchor"]["block_number"] += 1
        reseal(o, "registry_commitment_sha256")
        with self.assertRaisesRegex(ValueError, "oracle_anchor_mismatch"):
            evaluate_candidate_coherence(**bundle(oracle_registry_payload=o))

    def test_truth_subject_must_equal_position(self):
        t = triad()
        t["subject_id"] = h("2")
        reseal(t, "triad_commitment_sha256")
        with self.assertRaisesRegex(ValueError, "truth_subject_mismatch"):
            evaluate_candidate_coherence(**bundle(triad=t))

    def test_graph_market_binding_is_exact(self):
        g = graph()
        for edge in g["edges"]:
            if edge["kind"] == "POSITION_MARKET":
                edge["to_node"] = h("2")
                break
        reseal(g, "graph_commitment_sha256")
        with self.assertRaises(ValueError):
            evaluate_candidate_coherence(**bundle(graph_payload=g))

    def test_graph_and_order_book_oracle_must_match(self):
        b = book()
        b["entries"][0]["oracle_id"] = DEBT_ORACLE
        reseal(b, "book_commitment_sha256")
        with self.assertRaisesRegex(ValueError, "graph_order_book_oracle_mismatch"):
            evaluate_candidate_coherence(**bundle(order_book_payload=b))

    def test_order_book_must_contain_position(self):
        b = book()
        b["entries"][0]["position_id"] = h("2")
        reseal(b, "book_commitment_sha256")
        with self.assertRaisesRegex(ValueError, "order_book_position_binding_missing"):
            evaluate_candidate_coherence(**bundle(order_book_payload=b))

    def test_oracle_registry_must_contain_market(self):
        o = oracle_registry()
        o["markets"][0]["market_id"] = h("2")
        reseal(o, "registry_commitment_sha256")
        with self.assertRaisesRegex(ValueError, "oracle_market_binding_missing"):
            evaluate_candidate_coherence(**bundle(oracle_registry_payload=o))

    def test_order_book_oracle_must_belong_to_market(self):
        alt = h("2")
        g = graph()
        for node in g["nodes"]:
            if node["node_id"] == ORACLE:
                node["node_id"] = alt
        for edge in g["edges"]:
            if edge["to_node"] == ORACLE:
                edge["to_node"] = alt
        reseal(g, "graph_commitment_sha256")
        b = book()
        b["entries"][0]["oracle_id"] = alt
        reseal(b, "book_commitment_sha256")
        with self.assertRaisesRegex(ValueError, "order_book_oracle_not_in_market"):
            evaluate_candidate_coherence(**bundle(graph_payload=g, order_book_payload=b))

    def test_adapter_deployment_must_match(self):
        a = adapter_registry(deployment=addr("4"))
        with self.assertRaisesRegex(ValueError, "adapter_binding_not_unique"):
            evaluate_candidate_coherence(**bundle(adapter_registry_payload=a))

    def test_adapter_version_must_match(self):
        a = adapter_registry(version=h("6"))
        with self.assertRaisesRegex(ValueError, "adapter_binding_not_unique"):
            evaluate_candidate_coherence(**bundle(adapter_registry_payload=a))

    def test_adapter_family_must_match_protocol(self):
        a = adapter_registry(family="MORPHO_BLUE")
        with self.assertRaisesRegex(ValueError, "adapter_binding_not_unique"):
            evaluate_candidate_coherence(**bundle(adapter_registry_payload=a))

    def test_adapter_requires_all_declared_capabilities(self):
        a = adapter_registry(missing={"liquidation_math"})
        with self.assertRaisesRegex(ValueError, "adapter_capabilities_incomplete"):
            evaluate_candidate_coherence(**bundle(adapter_registry_payload=a))

    def test_unsupported_protocol_id_is_blocked(self):
        d = dossier()
        d["protocol"]["protocol_id"] = "unknown"
        from opportunity_vault import identity_payload
        d["opportunity_id"] = digest(canonical(identity_payload(d)))
        reseal(d, "dossier_commitment_sha256")
        with self.assertRaisesRegex(ValueError, "unsupported_protocol_id"):
            evaluate_candidate_coherence(**bundle(dossier=d))

    def test_tampered_input_fails_before_cross_artifact_checks(self):
        d = dossier()
        d["position"]["borrower"] = addr("2")
        with self.assertRaisesRegex(ValueError, "invalid_dossier"):
            evaluate_candidate_coherence(**bundle(dossier=d))

    def test_commitment_is_deterministic(self):
        left = evaluate_candidate_coherence(**bundle())
        right = evaluate_candidate_coherence(**bundle())
        self.assertEqual(left["coherence_commitment_sha256"], right["coherence_commitment_sha256"])


if __name__ == "__main__":
    unittest.main()
