"""SUPERHUNTER phase 1: offline, fail-closed DIABLO <-> NQC data bridge.

This validates attestations and artifact bindings. It does NOT run a fork,
prove exploitability, consult live program scopes, or calculate severity itself.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from pathlib import Path
from typing import Any

FAMILIES = {"vault", "amm", "oracle", "lending", "flashloan", "staking"}
SEVERITIES = ("none", "low", "medium", "high", "critical")
SHA40 = re.compile(r"[a-fA-F0-9]{40}\Z")
SHA64 = re.compile(r"(?:0x)?[a-fA-F0-9]{64}\Z")
ADDRESS = re.compile(r"0x[a-fA-F0-9]{40}\Z")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
TEST_REF = re.compile(r"[^\s:]+\.t\.sol::test_[A-Za-z0-9_]+\Z")
SLUG = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*\Z")
MAX_ARTIFACT_BYTES = 2_000_000


class ContractError(ValueError):
    """A required field or proof is missing or invalid."""


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ContractError(reason)


def fields(obj: Any, required: set[str], *, name: str) -> dict:
    require(type(obj) is dict, f"{name}: expected object")
    require(set(obj) == required,
            f"{name}: fields mismatch (missing={sorted(required - set(obj))}, extra={sorted(set(obj) - required)})")
    return obj


def string(value: Any, name: str, pattern: re.Pattern | None = None) -> str:
    require(type(value) is str and bool(value.strip()), f"{name}: expected nonempty string")
    if pattern is not None:
        require(pattern.fullmatch(value) is not None, f"{name}: invalid format")
    return value


def number(value: Any, name: str, *, minimum: float | None = None) -> float:
    require(type(value) in (float, int) and math.isfinite(value), f"{name}: finite number required")
    if minimum is not None:
        require(value >= minimum, f"{name}: must be >= {minimum}")
    return float(value)


def integer(value: Any, name: str) -> int:
    require(type(value) is int and value >= 0, f"{name}: nonnegative integer required")
    return value


def addresses(value: Any, name: str) -> list[str]:
    require(type(value) is list and bool(value), f"{name}: nonempty array required")
    require(all(type(v) is str and ADDRESS.fullmatch(v) for v in value), f"{name}: invalid address")
    require(len({v.lower() for v in value}) == len(value), f"{name}: duplicate address")
    return value


def uuid_text(value: Any, name: str) -> str:
    string(value, name)
    try:
        require(str(uuid.UUID(value)) == value.lower(), f"{name}: canonical UUID required")
    except (ValueError, AttributeError) as exc:
        raise ContractError(f"{name}: invalid UUID") from exc
    return value


def sha256_text(value: Any, name: str) -> str:
    string(value, name, SHA64)
    return value.removeprefix("0x").lower()


def candidate(data: Any) -> dict:
    data = fields(data, {"id", "scope_id", "target", "family", "invariant_broken", "poc_path",
                         "affected_contracts", "prelim_severity", "forge_evidence_sha"}, name="Candidate")
    uuid_text(data["id"], "Candidate.id")
    require(string(data["scope_id"], "Candidate.scope_id").startswith("immunefi-") or
            string(data["scope_id"], "Candidate.scope_id").startswith("bounty-"),
            "Candidate.scope_id: needs program identifier")
    target = fields(data["target"], {"repo", "commit", "fork_block"}, name="Candidate.target")
    string(target["repo"], "Candidate.target.repo", REPO)
    string(target["commit"], "Candidate.target.commit", SHA40)
    require(target["fork_block"] is None or
            (type(target["fork_block"]) is int and target["fork_block"] >= 0),
            "Candidate.target.fork_block: invalid")
    require(data["family"] in FAMILIES, "Candidate.family: unsupported")
    string(data["invariant_broken"], "Candidate.invariant_broken")
    string(data["poc_path"], "Candidate.poc_path", TEST_REF)
    addresses(data["affected_contracts"], "Candidate.affected_contracts")
    require(data["prelim_severity"] == "unverified", "Candidate.prelim_severity: must be unverified")
    sha256_text(data["forge_evidence_sha"], "Candidate.forge_evidence_sha")
    return data


def reconstruction(data: Any) -> dict:
    data = fields(data, {"candidate_id", "state_anchor", "protocol_model", "funds_at_risk",
                         "attacker_cost", "net_profit_usd", "reproducible", "economic_severity",
                         "confidence", "notes"}, name="Reconstruction")
    uuid_text(data["candidate_id"], "Reconstruction.candidate_id")
    anchor = fields(data["state_anchor"], {"block", "block_hash"}, name="Reconstruction.state_anchor")
    integer(anchor["block"], "Reconstruction.state_anchor.block")
    sha256_text(anchor["block_hash"], "Reconstruction.state_anchor.block_hash")
    string(data["protocol_model"], "Reconstruction.protocol_model", SLUG)
    funds = fields(data["funds_at_risk"], {"token", "amount_wei", "usd"}, name="Reconstruction.funds_at_risk")
    string(funds["token"], "Reconstruction.funds_at_risk.token", ADDRESS)
    require(type(funds["amount_wei"]) is str and funds["amount_wei"].isdigit(),
            "Reconstruction.funds_at_risk.amount_wei: decimal string required")
    number(funds["usd"], "Reconstruction.funds_at_risk.usd", minimum=0)
    cost = fields(data["attacker_cost"], {"usd"}, name="Reconstruction.attacker_cost")
    number(cost["usd"], "Reconstruction.attacker_cost.usd", minimum=0)
    number(data["net_profit_usd"], "Reconstruction.net_profit_usd")
    require(type(data["reproducible"]) is bool, "Reconstruction.reproducible: boolean required")
    require(data["economic_severity"] in SEVERITIES, "Reconstruction.economic_severity: invalid")
    conf = number(data["confidence"], "Reconstruction.confidence", minimum=0)
    require(conf <= 1, "Reconstruction.confidence: must be <=1")
    require(type(data["notes"]) is str, "Reconstruction.notes: string required")
    return data


def _load_artifact(root: Path, relative: Any) -> bytes:
    rel = Path(string(relative, "artifact path"))
    require(not rel.is_absolute() and ".." not in rel.parts, "artifact: absolute/traversal path rejected")
    root = root.resolve()
    dest = (root / rel).resolve()
    require(dest.is_relative_to(root) and dest.is_file(), "artifact: file not found inside evidence root")
    require(dest.stat().st_size <= MAX_ARTIFACT_BYTES, "artifact: file too large")
    return dest.read_bytes()


def _same_addresses(left: list[str], right: list[str]) -> bool:
    return {x.lower() for x in left} == {x.lower() for x in right}


def evaluate(c: Any, r: Any, admission: Any, *, evidence_root: Path, report_path: str) -> dict:
    """Return REJECTED or a flattened Finding, never execute untrusted code."""
    c, r = candidate(c), reconstruction(r)
    require(type(admission) is dict, "admission: object required")
    a = fields(admission, {"scope", "forge", "nqc", "duplicate", "severity"}, name="Admission")
    errors: list[str] = []
    require(c["id"].lower() == r["candidate_id"].lower(), "candidate_id mismatch")

    def gate(name: str, fn) -> None:
        try:
            fn()
        except (ContractError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"{name}: {exc}")

    def scope_gate() -> None:
        s = fields(a["scope"], {"scope_id", "repo", "commit", "allowed_contracts", "excluded_contracts",
                                "policy_sha256", "source_url", "reviewed_by", "approved"}, name="scope")
        require(s["scope_id"] == c["scope_id"], "scope_id mismatch")
        require(s["repo"] == c["target"]["repo"] and s["commit"].lower() == c["target"]["commit"].lower(),
                "target repo/commit mismatch")
        addresses(s["allowed_contracts"], "scope.allowed_contracts")
        require(type(s["excluded_contracts"]) is list and
                all(type(x) is str and ADDRESS.fullmatch(x) for x in s["excluded_contracts"]),
                "scope.excluded_contracts invalid")
        sha256_text(s["policy_sha256"], "scope.policy_sha256")
        require(string(s["source_url"], "scope.source_url").startswith("https://"), "scope.source_url invalid")
        string(s["reviewed_by"], "scope.reviewed_by")
        require(s["approved"] is True, "scope not approved")
        require(set(x.lower() for x in c["affected_contracts"]).issubset(
                set(x.lower() for x in s["allowed_contracts"])), "affected contract outside scope")
        require(not set(x.lower() for x in c["affected_contracts"]).intersection(
                set(x.lower() for x in s["excluded_contracts"])), "excluded contract")

    def forge_gate() -> None:
        f = fields(a["forge"], {"candidate_id", "repo", "commit", "fork_block", "poc_path",
                                "affected_contracts", "output_file", "exit_code", "test_pass",
                                "target_bound"}, name="forge")
        require(f["candidate_id"].lower() == c["id"].lower(), "candidate_id mismatch")
        require(f["repo"] == c["target"]["repo"] and f["commit"].lower() == c["target"]["commit"].lower(),
                "target mismatch")
        require(f["fork_block"] == c["target"]["fork_block"] and f["poc_path"] == c["poc_path"],
                "PoC/fork mismatch")
        require(_same_addresses(addresses(f["affected_contracts"], "forge.affected_contracts"),
                                c["affected_contracts"]), "contract mismatch")
        require(type(f["exit_code"]) is int and f["exit_code"] == 0 and
                f["test_pass"] is True and f["target_bound"] is True, "forge did not attest PASS and target binding")
        output = _load_artifact(evidence_root, f["output_file"])
        require(hashlib.sha256(output).hexdigest() == sha256_text(c["forge_evidence_sha"], "candidate hash"),
                "forge output SHA256 mismatch")
        test_name = c["poc_path"].split("::")[-1]
        require(re.search(r"\[PASS\]\s+" + re.escape(test_name) + r"\s*\(",
                          output.decode("utf-8")) is not None, "named test absent from Forge PASS output")

    def nqc_gate() -> None:
        n = fields(a["nqc"], {"candidate_id", "state_anchor", "protocol_model", "evidence_file",
                               "evidence_sha256", "producer", "run_ok"}, name="nqc")
        require(n["candidate_id"].lower() == c["id"].lower(), "candidate_id mismatch")
        require(n["state_anchor"] == r["state_anchor"] and n["protocol_model"] == r["protocol_model"],
                "state/model mismatch")
        require(c["target"]["fork_block"] is not None and
                r["state_anchor"]["block"] == c["target"]["fork_block"], "fork block/anchor mismatch")
        require(n["producer"] == "NQC" and n["run_ok"] is True and
                r["reproducible"] is True and r["confidence"] >= 0.95, "reconstruction not sufficiently verified")
        require(r["economic_severity"] != "none" and r["funds_at_risk"]["usd"] > 0 and
                int(r["funds_at_risk"]["amount_wei"]) > 0,
                "no proven economic impact")
        raw = _load_artifact(evidence_root, n["evidence_file"])
        require(hashlib.sha256(raw).hexdigest() == sha256_text(n["evidence_sha256"], "nqc evidence hash"),
                "NQC evidence SHA256 mismatch")
        statement = json.loads(raw)
        require(type(statement) is dict and statement.get("candidate_id") == r["candidate_id"] and
                statement.get("state_anchor") == r["state_anchor"] and
                statement.get("protocol_model") == r["protocol_model"] and
                statement.get("funds_at_risk") == r["funds_at_risk"] and
                statement.get("attacker_cost") == r["attacker_cost"] and
                statement.get("net_profit_usd") == r["net_profit_usd"] and
                statement.get("reproducible") is True, "NQC evidence does not bind economics to candidate")

    def duplicate_gate() -> None:
        d = fields(a["duplicate"], {"result", "checked_sources", "reviewed_by"}, name="duplicate")
        require(d["result"] == "none", "possible duplicate or duplicate check missing")
        require(type(d["checked_sources"]) is list and len(d["checked_sources"]) > 0 and
                all(type(v) is str and v.strip() for v in d["checked_sources"]), "duplicate sources missing")
        string(d["reviewed_by"], "duplicate.reviewed_by")

    def severity_gate() -> None:
        s = fields(a["severity"], {"program_cap", "impact_review", "reviewed_by"}, name="severity")
        require(s["program_cap"] in SEVERITIES and s["impact_review"] in SEVERITIES,
                "invalid severity cap/review")
        string(s["reviewed_by"], "severity.reviewed_by")
        require(s["program_cap"] != "none" and s["impact_review"] != "none", "no reportable severity")

    for name, fn in (("scope", scope_gate), ("forge", forge_gate), ("nqc", nqc_gate),
                     ("duplicate", duplicate_gate), ("severity", severity_gate)):
        gate(name, fn)
    if errors:
        return {"status": "REJECTED", "candidate_id": c["id"], "reasons": errors}
    caps = a["severity"]
    # prelim_severity=unverified is a STATUS, not an ordinal severity; do not min() it.
    final_severity = min((r["economic_severity"], caps["program_cap"], caps["impact_review"]),
                         key=SEVERITIES.index)
    require(final_severity != "none", "severity after calibration not reportable")
    return {"status": "REPORT_READY", "finding": {
        **c, **r, "scope_pass": True, "dup_check": "none", "forge_pass": True,
        "final_severity": final_severity, "report_md": report_path,
    }}


def render_report(finding: dict) -> str:
    """Minimal report draft; never assert live exploit or paid bounty."""
    target = finding["target"]
    anchor = finding["state_anchor"]
    return (f"# SUPERHUNTER — {finding['invariant_broken']}\n\n"
            f"Status: evidence-gated draft; human review required before disclosure.\n\n"
            f"- Candidate: `{finding['id']}`\n"
            f"- Program: `{finding['scope_id']}`\n"
            f"- Repo: `{target['repo']}` at `{target['commit']}`\n"
            f"- Fork: `{target['fork_block']}`; anchor `{anchor['block_hash']}`\n"
            f"- Family: `{finding['family']}`\n"
            f"- PoC: `{finding['poc_path']}`\n"
            f"- Forge output SHA256: `{finding['forge_evidence_sha']}`\n"
            f"- NQC model: `{finding['protocol_model']}`\n"
            f"- Funds at risk (modeled): USD {finding['funds_at_risk']['usd']}\n"
            f"- Attacker cost (modeled): USD {finding['attacker_cost']['usd']}\n"
            f"- Net profit (modeled): USD {finding['net_profit_usd']}\n"
            f"- Calibrated severity: **{finding['final_severity']}**\n"
            f"- Reconstruction confidence (claimed): {finding['confidence']}\n\n"
            f"## Notes\n\n{finding['notes']}\n\n"
            f"This is an offline review draft, NOT independent proof of exploitability.\n")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
