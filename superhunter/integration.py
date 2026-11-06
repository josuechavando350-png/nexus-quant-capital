"""Offline adapters for DIABLO's native Finding and NQC evidence responses.

Only transports existing evidence. Never imports executable project code,
launches Forge, opens an RPC connection, or confirms an exploit.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
import hashlib
from pathlib import Path
from typing import Any
import uuid

from .bridge import (ContractError, SHA40, SHA64, REPO, candidate, evaluate,
                     fields, integer, reconstruction, require, string)
from .safe_io import canonical

DIABLO_SCHEMA_SOURCE = {
    "repo": "josuechavando350-png/DIABLO",
    "commit": "0c27792fba1af1f925bfff03fbcc6fd82a3791b0",
    "path": "nexus-offensive/core/models.py",
    "git_blob": "bd832c728e71dc18bb4e9fa76bca7b36bf714a8b",
}
CONTEXT_KEYS = {"scope_id", "repo", "commit", "chain", "chain_id", "fork_block",
                "block_hash", "family", "poc_path"}


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def context_record(value: Any) -> dict:
    value = fields(value, CONTEXT_KEYS, name="context")
    string(value["scope_id"], "context.scope_id")
    string(value["repo"], "context.repo", REPO)
    string(value["commit"], "context.commit", SHA40)
    string(value["chain"], "context.chain")
    require(integer(value["chain_id"], "context.chain_id") > 0, "chain_id must be positive")
    if value["fork_block"] is None:
        require(value["block_hash"] is None, "unanchored context must not claim a block hash")
    else:
        integer(value["fork_block"], "context.fork_block")
        string(value["block_hash"], "context.block_hash", SHA64)
        require(value["block_hash"].startswith("0x") and int(value["block_hash"], 16) > 0,
                "block_hash must be a nonzero 0x-prefixed hash")
    return deepcopy(value)


def export_diablo(native_finding: Any, context: Any, forge_output: bytes) -> dict:
    """Accept a DIABLO Finding dataclass or its JSON representation.

    Legacy DIABLO HIGH/CRITICAL and the word 'fork' in its description confer
    no authority. The candidate is unverified and scope still needs review.
    """
    if is_dataclass(native_finding) and not isinstance(native_finding, type):
        native_finding = asdict(native_finding)
    require(type(native_finding) is dict, "DIABLO Finding must be an object")
    required = {"id", "title", "severity", "target", "description", "invariant", "poc_ref", "created_at"}
    n = fields(native_finding, required, name="DIABLO Finding")
    t = fields(n["target"], {"value", "kind", "chain", "label"}, name="DIABLO target")
    ctx = context_record(context)
    require(t["kind"] == "contract" and t["chain"] == ctx["chain"], "DIABLO target kind/chain mismatch")
    string(n["id"], "DIABLO native id")
    string(n["invariant"], "DIABLO invariant")
    string(n["poc_ref"], "DIABLO poc_ref")
    string(ctx["poc_path"], "context.poc_path")
    require(n["poc_ref"] in (ctx["poc_path"], ctx["poc_path"].split("::")[0]),
            "DIABLO PoC reference does not match explicit context")
    require(type(forge_output) is bytes and 0 < len(forge_output) <= 2_000_000,
            "Forge artifact must be nonempty bounded bytes")
    # Never infer target binding or successful execution from the text log.
    output_sha = hashlib.sha256(forge_output).hexdigest()
    identity = {"native_id": n["id"], "context": ctx, "target": t["value"],
                "invariant": n["invariant"], "forge_sha256": output_sha}
    c = candidate({
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "superhunter:" + digest(identity))),
        "scope_id": ctx["scope_id"],
        "target": {"repo": ctx["repo"], "commit": ctx["commit"], "fork_block": ctx["fork_block"]},
        "family": ctx["family"], "invariant_broken": n["invariant"],
        "poc_path": ctx["poc_path"], "affected_contracts": [t["value"]],
        "prelim_severity": "unverified", "forge_evidence_sha": output_sha,
    })
    request = {
        "schema_version": 1, "candidate": c, "candidate_sha256": digest(c), "context": ctx,
        "source": {"format": "diablo-finding-v1", "native_id": n["id"],
                   "native_sha256": digest(n), "schema_source": DIABLO_SCHEMA_SOURCE},
    }
    request["request_sha256"] = digest(request)
    return request


def validate_request(value: Any) -> dict:
    request = fields(value, {"schema_version", "candidate", "candidate_sha256", "context",
                             "source", "request_sha256"}, name="request")
    require(type(request["schema_version"]) is int and request["schema_version"] == 1,
            "unsupported request schema")
    body = {k: v for k, v in request.items() if k != "request_sha256"}
    require(digest(body) == request["request_sha256"], "request digest mismatch")
    c = candidate(request["candidate"])
    ctx = context_record(request["context"])
    require(digest(c) == request["candidate_sha256"], "candidate digest mismatch")
    for key in ("repo", "commit", "fork_block"):
        require(c["target"][key] == ctx[key], "candidate/context mismatch")
    for key in ("scope_id", "family", "poc_path"):
        require(c[key] == ctx[key], "candidate/context mismatch")
    source = fields(request["source"], {"format", "native_id", "native_sha256", "schema_source"}, name="source")
    require(source["format"] == "diablo-finding-v1" and source["schema_source"] == DIABLO_SCHEMA_SOURCE,
            "unsupported DIABLO source schema")
    string(source["native_id"], "native id")
    string(source["native_sha256"], "native digest", SHA64)
    return request


def import_nqc(request: Any, response: Any, admission: Any, *, evidence_root: Path,
               report_path: str) -> dict:
    """Bind an existing NQC response to the exported request; no execution.

    A legacy PFT closeout is policy/history, NOT a Reconstruction. Its admission
    is explicitly blocked even when every tracked gate says PASS.
    """
    q = validate_request(request)
    require(type(response) is dict, "NQC response must be an object")
    c = q["candidate"]
    if response.get("closeout") == "PROTOCOL_FORK_TRUTH":
        decision = {
            "status": "INCOMPLETE", "candidate_id": c["id"], "execution_verified": False,
            "reasons": ["NQC Protocol/Fork closeout is policy/history, not candidate reconstruction.",
                        "No target-bound economic impact or independent execution is supplied."],
            "nqc_status": response.get("status"),
        }
    else:
        r = fields(response, {"schema_version", "request_sha256", "chain_id", "reconstruction"}, name="NQC response")
        require(type(r["schema_version"]) is int and r["schema_version"] == 1,
                "unsupported NQC response schema")
        require(r["request_sha256"] == q["request_sha256"], "NQC response/request mismatch")
        require(type(r["chain_id"]) is int and r["chain_id"] == q["context"]["chain_id"],
                "NQC chain_id mismatch")
        rec = reconstruction(r["reconstruction"])
        ctx = q["context"]
        require(ctx["fork_block"] is not None, "unanchored case requires a separate local-state schema")
        require(rec["state_anchor"] == {"block": ctx["fork_block"], "block_hash": ctx["block_hash"]},
                "NQC state anchor mismatch")
        decision = evaluate(c, rec, admission, evidence_root=evidence_root, report_path=report_path)
    decision["candidate_id"] = c["id"]
    decision["request_sha256"] = q["request_sha256"]
    # A machine-readable return path to DIABLO, without writing to its repo.
    decision["diablo_feedback"] = {
        "native_id": q["source"]["native_id"], "candidate_id": c["id"],
        "status": decision["status"], "confirmed": False,
        "next_action": "human_review" if decision["status"] == "REVIEW_REQUIRED" else "supply_missing_evidence",
    }
    return decision
