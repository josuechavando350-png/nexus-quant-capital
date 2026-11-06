"""Content-addressed causal proof graph for *local, fixed* DIABLO/NQC regressions.

Not a signature, vulnerability proof, consensus certificate, or authenticating
attestation. Graph is regenerated from independently checked run artifacts.
"""
from __future__ import annotations

import hashlib
from typing import Any

from .safe_io import canonical

GRAPH_DOMAIN = b"SUPERHUNTER-CLOSED-LOCAL-CAUSAL-GRAPH-V1\x00"


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _node(identifier: str, kind: str, deps: list[str], witness: Any) -> dict:
    body = {"id": identifier, "kind": kind, "depends_on": deps,
            "witness_sha256": digest(witness)}
    return {**body, "node_sha256": hashlib.sha256(GRAPH_DOMAIN + canonical(body)).hexdigest()}


def _assert_run_links(cases: list[dict], entries: list[dict], summary: dict) -> None:
    """Proof goes beyond hash continuity: check which event proves which input/output."""
    if len(cases) != 5 or len(entries) != 18:
        raise ValueError("local causal graph requires five cases and 18 audit events")
    if entries[0].get("event") != "lab.start" or entries[0].get("data") != {
        "run_id": summary["run_id"], "fixture_only": True
    }:
        raise ValueError("run start is not bound to summary")
    for index, case in enumerate(cases):
        name = case["case"]
        allowed, start, finish = entries[1 + index*3:4 + index*3]
        if allowed.get("event") != "scope.check" or allowed.get("data") != {
            "target": name + ".lab.invalid", "kind": "fixture", "decision": "ALLOW",
            "reason": "in scope (*.lab.invalid)", "matched_rule": "*.lab.invalid",
        }:
            raise ValueError("scope admission does not bind to NQC case " + name)
        if start.get("event") != "lab.nqc.start" or start.get("data") != {
            "case": name, "input_sha256": digest(case["inputs"])
        }:
            raise ValueError("NQC input digest not bound to DIABLO audit " + name)
        if finish.get("event") != "lab.nqc.finish" or finish.get("data") != {
            "case": name, "output_commitment": case["nqc"]["commitment"]
        }:
            raise ValueError("NQC result commitment not bound to DIABLO audit " + name)
        if case.get("match") is not True:
            raise ValueError("independent comparison was not successful")
    if entries[16].get("event") != "scope.check" or entries[16].get("data") != {
        "target": "blocked.lab.invalid", "kind": "fixture", "decision": "DENY",
        "reason": "explicitly out of scope (blocked.lab.invalid)",
        "matched_rule": "blocked.lab.invalid",
    }:
        raise ValueError("out-of-scope negative witness missing")
    if entries[17].get("event") != "lab.completed" or entries[17].get("data") != {
        "run_id": summary["run_id"], "cases": 5, "vulnerability_confirmed": False
    }:
        raise ValueError("completion event mismatch")


def build_graph(cases: list[dict], entries: list[dict], provenance: list[dict], summary: dict) -> dict:
    """Generate a DAG only after checking all DIABLO/NQC causal event bindings."""
    _assert_run_links(cases, entries, summary)
    if not isinstance(provenance, list) or len(provenance) != 5:
        raise ValueError("all five pinned sources required")
    diablo = [p for p in provenance if p.get("repository", "").endswith("/DIABLO")]
    nqc = [p for p in provenance if p.get("repository", "").endswith("/nexus-quant-capital")]
    if len(diablo) != 4 or len(nqc) != 1:
        raise ValueError("DIABLO/NQC provenance separation invalid")
    nodes = [_node("source:diablo", "pinned-code", [], diablo),
             _node("source:nqc", "pinned-code", [], nqc)]
    previous = set(node["id"] for node in nodes)

    for i, case in enumerate(cases):
        name = case["case"]
        for suffix, kind, deps, witness in (
            ("scope", "scope-decision", ["source:diablo"], entries[i*3+1]["data"]),
            ("input", "fixed-input", [f"{name}:scope"], case["inputs"]),
            ("nqc", "native-result", [f"{name}:input", "source:nqc"], case["nqc"]),
            ("reference", "independent-reference", [f"{name}:nqc"], case["independent"]),
        ):
            identifier = f"{name}:{suffix}"
            if identifier in previous or any(parent not in previous for parent in deps):
                raise ValueError("graph is not unique and topologically closed")
            nodes.append(_node(identifier, kind, deps, witness))
            previous.add(identifier)

    comparison_nodes = [f"{c['case']}:reference" for c in cases]
    nodes.append(_node("diablo:audit", "hash-chain", comparison_nodes + ["source:diablo"], entries))
    nodes.append(_node("run:decision", "local-verdict", ["diablo:audit"], summary))
    raw = b"".join(bytes.fromhex(node["node_sha256"]) for node in nodes)
    return {"schema_version": 1, "domain": "local-fixed-regression-not-vulnerability",
            "run_id": summary["run_id"], "nodes": nodes,
            "root_sha256": hashlib.sha256(GRAPH_DOMAIN + raw).hexdigest(),
            "production_finding": False, "independently_authenticated": False}


def verify_graph(graph: Any, *, cases: list[dict], entries: list[dict],
                 provenance: list[dict], summary: dict) -> None:
    """Recompute every node and dependency from supplied, otherwise verified artifacts."""
    expected = build_graph(cases, entries, provenance, summary)
    if type(graph) is not dict or canonical(graph) != canonical(expected):
        raise ValueError("causal graph mismatch: changed node, dependency, run, or root")
