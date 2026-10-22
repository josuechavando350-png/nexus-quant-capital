"""Exact offline causal dependency graph for Omega Census.

The graph answers which positions must be recomputed after a dependency changes.
It has no market acquisition, signing, broadcasting, spending or phase authority.
"""
from __future__ import annotations

import copy
import re
from collections import deque

from integrity import canonical, digest

SCHEMA = "nqc.omega.causal-graph.v1"
SCOPE = "CENSUS_OFFLINE_DEPENDENCY_GRAPH_ONLY"
HEX32 = re.compile(r"^[0-9a-f]{64}$")
HASH32 = re.compile(r"^0x[0-9a-f]{64}$")
NODE_KINDS = {
    "POSITION", "MARKET", "ORACLE", "INTEREST_MODEL", "LIQUIDITY_SOURCE", "ROUTE",
}
EDGE_RULES = {
    "POSITION_MARKET": ("POSITION", "MARKET"),
    "POSITION_ORACLE": ("POSITION", "ORACLE"),
    "POSITION_INTEREST": ("POSITION", "INTEREST_MODEL"),
    "POSITION_LIQUIDITY": ("POSITION", "LIQUIDITY_SOURCE"),
    "POSITION_ROUTE": ("POSITION", "ROUTE"),
    "MARKET_ORACLE": ("MARKET", "ORACLE"),
    "MARKET_INTEREST": ("MARKET", "INTEREST_MODEL"),
    "ROUTE_LIQUIDITY": ("ROUTE", "LIQUIDITY_SOURCE"),
}
POSITION_REQUIRED_EDGE_KINDS = {
    "POSITION_MARKET", "POSITION_ORACLE", "POSITION_INTEREST",
    "POSITION_LIQUIDITY", "POSITION_ROUTE",
}
AUTHORITY_KEYS = {
    "can_sign", "can_broadcast", "can_spend", "phase_advance_authorized",
    "census_closed",
}
TOP_KEYS = {
    "schema", "record_scope", "state_anchor", "nodes", "edges", "authorities",
    "graph_commitment_sha256",
}
NODE_KEYS = {"node_id", "kind", "evidence_sha256"}
EDGE_KEYS = {"from_node", "to_node", "kind", "evidence_sha256"}


def _hex32(value: object) -> bool:
    return isinstance(value, str) and HEX32.fullmatch(value) is not None


def _canonical_nodes(nodes: list[dict]) -> list[dict]:
    return sorted((copy.deepcopy(node) for node in nodes), key=lambda n: (n["kind"], n["node_id"]))


def _canonical_edges(edges: list[dict]) -> list[dict]:
    return sorted(
        (copy.deepcopy(edge) for edge in edges),
        key=lambda e: (e["from_node"], e["kind"], e["to_node"], e["evidence_sha256"]),
    )


def _has_cycle(node_ids: set[str], edges: list[dict]) -> bool:
    forward = {node: [] for node in node_ids}
    indegree = {node: 0 for node in node_ids}
    for edge in edges:
        forward[edge["from_node"]].append(edge["to_node"])
        indegree[edge["to_node"]] += 1
    queue = deque(sorted(node for node, degree in indegree.items() if degree == 0))
    visited = 0
    while queue:
        node = queue.popleft()
        visited += 1
        for nxt in sorted(forward[node]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    return visited != len(node_ids)


def validate_graph(value: object) -> list[str]:
    errors: list[str] = []
    if type(value) is not dict:
        return ["graph_not_object"]
    if set(value) != TOP_KEYS:
        errors.append("top_level_shape_invalid")
    if value.get("schema") != SCHEMA:
        errors.append("wrong_schema")
    if value.get("record_scope") != SCOPE:
        errors.append("wrong_scope")

    authorities = value.get("authorities")
    if type(authorities) is not dict or set(authorities) != AUTHORITY_KEYS:
        errors.append("authorities_shape_invalid")
    elif any(authorities[key] is not False for key in AUTHORITY_KEYS):
        errors.append("authority_forbidden")

    anchor = value.get("state_anchor")
    if type(anchor) is not dict or set(anchor) != {"chain_id", "block_number", "block_hash"}:
        errors.append("anchor_shape_invalid")
    else:
        if type(anchor["chain_id"]) is not int or anchor["chain_id"] <= 0:
            errors.append("chain_id_invalid")
        if type(anchor["block_number"]) is not int or anchor["block_number"] <= 0:
            errors.append("block_number_invalid")
        if not isinstance(anchor["block_hash"], str) or HASH32.fullmatch(anchor["block_hash"]) is None:
            errors.append("block_hash_invalid")

    nodes = value.get("nodes")
    node_by_id: dict[str, dict] = {}
    if type(nodes) is not list or not nodes:
        errors.append("nodes_invalid")
    else:
        for node in nodes:
            if type(node) is not dict or set(node) != NODE_KEYS:
                errors.append("node_shape_invalid")
                continue
            node_id = node["node_id"]
            if not _hex32(node_id):
                errors.append("node_id_invalid")
            elif node_id in node_by_id:
                errors.append("duplicate_node")
            else:
                node_by_id[node_id] = node
            if node["kind"] not in NODE_KINDS:
                errors.append("node_kind_invalid")
            if not _hex32(node["evidence_sha256"]):
                errors.append("node_evidence_invalid")
        if all(type(node) is dict and set(node) == NODE_KEYS for node in nodes):
            if nodes != _canonical_nodes(nodes):
                errors.append("nodes_not_canonically_sorted")

    edges = value.get("edges")
    valid_edges: list[dict] = []
    seen_edges = set()
    if type(edges) is not list:
        errors.append("edges_not_list")
    else:
        for edge in edges:
            if type(edge) is not dict or set(edge) != EDGE_KEYS:
                errors.append("edge_shape_invalid")
                continue
            source = edge["from_node"]
            target = edge["to_node"]
            kind = edge["kind"]
            if not _hex32(source) or not _hex32(target):
                errors.append("edge_node_id_invalid")
                continue
            if source == target:
                errors.append("self_edge_forbidden")
            if source not in node_by_id or target not in node_by_id:
                errors.append("dangling_edge")
                continue
            if kind not in EDGE_RULES:
                errors.append("edge_kind_invalid")
            else:
                expected_source, expected_target = EDGE_RULES[kind]
                if (node_by_id[source]["kind"], node_by_id[target]["kind"]) != (
                    expected_source, expected_target
                ):
                    errors.append("edge_type_mismatch")
            if not _hex32(edge["evidence_sha256"]):
                errors.append("edge_evidence_invalid")
            identity = (source, target, kind)
            if identity in seen_edges:
                errors.append("duplicate_edge")
            seen_edges.add(identity)
            valid_edges.append(edge)
        if all(type(edge) is dict and set(edge) == EDGE_KEYS for edge in edges):
            if edges != _canonical_edges(edges):
                errors.append("edges_not_canonically_sorted")

    if node_by_id and valid_edges:
        positions = {node_id for node_id, node in node_by_id.items() if node["kind"] == "POSITION"}
        outgoing = {position: set() for position in positions}
        for edge in valid_edges:
            if edge["from_node"] in positions:
                outgoing[edge["from_node"]].add(edge["kind"])
        for position, kinds in outgoing.items():
            if not POSITION_REQUIRED_EDGE_KINDS.issubset(kinds):
                errors.append("position_dependency_coverage_incomplete")
                break
        safe_edges = [
            edge for edge in valid_edges
            if edge["from_node"] in node_by_id and edge["to_node"] in node_by_id
        ]
        if _has_cycle(set(node_by_id), safe_edges):
            errors.append("causal_cycle_forbidden")

    commitment = value.get("graph_commitment_sha256")
    if _hex32(commitment):
        unsigned = {key: val for key, val in value.items() if key != "graph_commitment_sha256"}
        if commitment != digest(canonical(unsigned)):
            errors.append("graph_commitment_mismatch")
    else:
        errors.append("graph_commitment_invalid")
    return sorted(set(errors))


def seal_graph(state_anchor: dict, nodes: list[dict], edges: list[dict]) -> dict:
    graph = {
        "schema": SCHEMA,
        "record_scope": SCOPE,
        "state_anchor": copy.deepcopy(state_anchor),
        "nodes": _canonical_nodes(nodes),
        "edges": _canonical_edges(edges),
        "authorities": {
            "can_sign": False,
            "can_broadcast": False,
            "can_spend": False,
            "phase_advance_authorized": False,
            "census_closed": False,
        },
    }
    graph["graph_commitment_sha256"] = digest(canonical(graph))
    errors = validate_graph(graph)
    if errors:
        raise ValueError("invalid_graph:" + ",".join(errors))
    return graph


class CausalGraph:
    def __init__(self, graph: dict):
        errors = validate_graph(graph)
        if errors:
            raise ValueError("invalid_graph:" + ",".join(errors))
        self._graph = copy.deepcopy(graph)
        self._kind = {node["node_id"]: node["kind"] for node in graph["nodes"]}
        self._reverse: dict[str, list[str]] = {node_id: [] for node_id in self._kind}
        for edge in graph["edges"]:
            self._reverse[edge["to_node"]].append(edge["from_node"])
        for values in self._reverse.values():
            values.sort()

    @property
    def commitment(self) -> str:
        return self._graph["graph_commitment_sha256"]

    def affected_positions(self, changed_node_ids: list[str]) -> list[str]:
        """Reverse-traverse dependencies and return only affected POSITION nodes."""
        if type(changed_node_ids) is not list or not changed_node_ids:
            raise ValueError("changed_nodes_invalid")
        unknown = [node for node in changed_node_ids if node not in self._kind]
        if unknown:
            raise ValueError("unknown_changed_node:" + ",".join(sorted(unknown)))
        queue = deque(sorted(set(changed_node_ids)))
        seen = set(queue)
        positions = set()
        while queue:
            node = queue.popleft()
            if self._kind[node] == "POSITION":
                positions.add(node)
            for parent in self._reverse[node]:
                if parent not in seen:
                    seen.add(parent)
                    queue.append(parent)
        return sorted(positions)

    def direct_dependencies(self, position_id: str) -> list[dict]:
        if self._kind.get(position_id) != "POSITION":
            raise ValueError("position_id_invalid")
        dependencies = []
        for edge in self._graph["edges"]:
            if edge["from_node"] == position_id:
                dependencies.append({
                    "edge_kind": edge["kind"],
                    "node_id": edge["to_node"],
                    "node_kind": self._kind[edge["to_node"]],
                })
        return sorted(dependencies, key=lambda item: (item["edge_kind"], item["node_id"]))
