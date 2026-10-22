"""Cross-artifact coherence gate for one Omega Census candidate.

This gate validates that already-sealed offline artifacts describe the same
candidate and state. It never authorizes GO, signing, broadcasting, spending,
Census closeout, certification, or phase advancement.
"""
from __future__ import annotations

import copy

from integrity import canonical, digest
from opportunity_vault import validate_dossier
from truth_engine import evaluate_triad, validate_triad
from causal_graph import CausalGraph, validate_graph
from liquidation_order_book import LiquidationOrderBook, validate_book
from oracle_semantics import OracleSemanticsRegistry, validate_registry as validate_oracle_registry
from protocol_adapters import (
    CAPABILITIES,
    ProtocolAdapterRegistry,
    validate_registry as validate_adapter_registry,
)

SCHEMA = "nqc.omega.candidate-coherence.v1"
PROTOCOL_FAMILY = {
    "aave-v3": "AAVE_V3",
    "morpho-blue": "MORPHO_BLUE",
    "morpho-midnight": "MORPHO_MIDNIGHT",
    "dutch-auction": "DUTCH_AUCTION",
}


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def _anchor3(anchor: dict) -> dict:
    return {
        "chain_id": anchor["chain_id"],
        "block_number": anchor["block_number"],
        "block_hash": anchor["block_hash"],
    }


def _direct_by_kind(graph: CausalGraph, position_id: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for item in graph.direct_dependencies(position_id):
        out.setdefault(item["edge_kind"], []).append(item["node_id"])
    return {key: sorted(value) for key, value in sorted(out.items())}


def evaluate_candidate_coherence(
    dossier: dict,
    triad: dict,
    graph_payload: dict,
    order_book_payload: dict,
    oracle_registry_payload: dict,
    adapter_registry_payload: dict,
) -> dict:
    """Validate a single candidate across six independently sealed artifacts."""
    errors = validate_dossier(dossier)
    _require(not errors, "invalid_dossier:" + ",".join(errors))
    errors = validate_triad(triad)
    _require(not errors, "invalid_triad:" + ",".join(errors))
    errors = validate_graph(graph_payload)
    _require(not errors, "invalid_graph:" + ",".join(errors))
    errors = validate_book(order_book_payload)
    _require(not errors, "invalid_order_book:" + ",".join(errors))
    errors = validate_oracle_registry(oracle_registry_payload)
    _require(not errors, "invalid_oracle_registry:" + ",".join(errors))
    errors = validate_adapter_registry(adapter_registry_payload)
    _require(not errors, "invalid_adapter_registry:" + ",".join(errors))

    truth = evaluate_triad(triad)
    _require(truth["parity"] is True, "truth_parity_required")
    _require(dossier["decision"]["truth_complete"] is True, "dossier_truth_must_be_complete")

    full_anchor = dossier["state_anchor"]
    _require(triad["state_anchor"] == full_anchor, "truth_anchor_mismatch")
    expected_anchor3 = _anchor3(full_anchor)
    _require(graph_payload["state_anchor"] == expected_anchor3, "graph_anchor_mismatch")
    _require(order_book_payload["state_anchor"] == expected_anchor3, "order_book_anchor_mismatch")
    _require(oracle_registry_payload["state_anchor"] == expected_anchor3, "oracle_anchor_mismatch")

    position_id = dossier["position"]["position_commitment"]
    market_id = dossier["protocol"]["market_id"]
    _require(triad["subject_id"] == position_id, "truth_subject_mismatch")

    graph = CausalGraph(graph_payload)
    deps = _direct_by_kind(graph, position_id)
    _require(deps.get("POSITION_MARKET") == [market_id], "graph_market_binding_mismatch")
    graph_oracles = deps.get("POSITION_ORACLE")
    _require(isinstance(graph_oracles, list) and len(graph_oracles) == 1,
             "graph_oracle_binding_not_unique")
    graph_oracle = graph_oracles[0]

    matching_entries = [
        entry for entry in order_book_payload["entries"]
        if entry["position_id"] == position_id
    ]
    _require(len(matching_entries) == 1, "order_book_position_binding_missing")
    order_entry = matching_entries[0]
    _require(order_entry["oracle_id"] == graph_oracle, "graph_order_book_oracle_mismatch")

    oracle_registry = OracleSemanticsRegistry(oracle_registry_payload)
    market = next(
        (item for item in oracle_registry_payload["markets"] if item["market_id"] == market_id),
        None,
    )
    _require(market is not None, "oracle_market_binding_missing")
    market_oracles = {market["collateral_oracle_id"], market["debt_oracle_id"]}
    _require(graph_oracle in market_oracles, "order_book_oracle_not_in_market")
    oracle_semantics = oracle_registry.oracle_semantics(graph_oracle)

    protocol_id = dossier["protocol"]["protocol_id"]
    family = PROTOCOL_FAMILY.get(protocol_id)
    _require(family is not None, "unsupported_protocol_id")

    adapter_registry = ProtocolAdapterRegistry(adapter_registry_payload)
    adapters = [
        item for item in adapter_registry_payload["adapters"]
        if (
            item["protocol_family"] == family
            and item["chain_id"] == full_anchor["chain_id"]
            and item["deployment"] == dossier["protocol"]["deployment"]
            and item["version_commitment_sha256"]
            == dossier["protocol"]["version_commitment"]
        )
    ]
    _require(len(adapters) == 1, "adapter_binding_not_unique")
    adapter = adapters[0]
    conformance = adapter_registry.require_capabilities(
        adapter["adapter_id"], list(CAPABILITIES)
    )
    _require(conformance["conformant"] is True, "adapter_capabilities_incomplete")

    result = {
        "schema": SCHEMA,
        "status": "FOUNDATION_COHERENT",
        "opportunity_id": dossier["opportunity_id"],
        "position_id": position_id,
        "market_id": market_id,
        "oracle_id": graph_oracle,
        "adapter_id": adapter["adapter_id"],
        "state_anchor": copy.deepcopy(full_anchor),
        "oracle_semantics": oracle_semantics["semantic_class"],
        "artifact_commitments": {
            "dossier": dossier["dossier_commitment_sha256"],
            "truth_triad": triad["triad_commitment_sha256"],
            "causal_graph": graph.commitment,
            "liquidation_order_book": LiquidationOrderBook(order_book_payload).commitment,
            "oracle_registry": oracle_registry.commitment,
            "adapter_registry": adapter_registry.commitment,
        },
        "certification_claimed": False,
        "go_authorized": False,
        "signing_authorized": False,
        "broadcast_authorized": False,
        "spending_authorized": False,
        "phase_advance_authorized": False,
        "census_closed": False,
    }
    result["coherence_commitment_sha256"] = digest(canonical(result))
    return result
