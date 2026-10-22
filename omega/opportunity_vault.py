"""Fail-closed offline Opportunity Dossier layer for Omega Evidence Vault.

This layer records evidence only. It cannot sign, broadcast, spend, close Census,
or turn a historical market outcome into NQC realized P&L.
"""
from __future__ import annotations

import copy
import os
import re
import tempfile
from pathlib import Path

from integrity import canonical, digest, read_regular, strict_json

SCHEMA = "nqc.omega.census-opportunity-dossier.v1"
SCOPE = "CENSUS_OFFLINE_EVIDENCE_ONLY"
HEX32 = re.compile(r"^[0-9a-f]{64}$")
HASH32 = re.compile(r"^0x[0-9a-f]{64}$")
ADDRESS = re.compile(r"^0x[0-9a-f]{40}$")
SIGNED_DECIMAL = re.compile(r"^(?:0|-?[1-9][0-9]*)$")
UNSIGNED_DECIMAL = re.compile(r"^(?:0|[1-9][0-9]*)$")
COST_KINDS = (
    "ProtocolFee", "CapitalFee", "SwapFee", "PriceImpact", "Gas",
    "PriorityFee", "BuilderPayment", "Financing", "Hedging", "Inventory",
    "ExpectedFailureRevert", "OpportunityCost", "Mev", "ChainSpecific",
)
TOP_KEYS = {
    "schema", "record_scope", "opportunity_id", "state_anchor", "protocol",
    "position", "decision", "economics", "competition", "scenarios", "outcome",
    "evidence", "blockers", "authorities", "dossier_commitment_sha256",
}
AUTHORITY_KEYS = {
    "can_sign", "can_broadcast", "can_spend", "phase_advance_authorized",
    "census_closed",
}


def _exact(value: object, keys: set[str], label: str, errors: list[str]) -> bool:
    if type(value) is not dict or set(value) != keys:
        errors.append(label + "_shape_invalid")
        return False
    return True


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _hex32(value: object) -> bool:
    return isinstance(value, str) and HEX32.fullmatch(value) is not None


def _address(value: object) -> bool:
    return isinstance(value, str) and ADDRESS.fullmatch(value) is not None


def _signed(value: object) -> bool:
    return isinstance(value, str) and SIGNED_DECIMAL.fullmatch(value) is not None


def _unsigned(value: object) -> bool:
    return isinstance(value, str) and UNSIGNED_DECIMAL.fullmatch(value) is not None


def identity_payload(record: dict) -> dict:
    return {
        "state_anchor": record["state_anchor"],
        "protocol": record["protocol"],
        "position": record["position"],
    }


def validate_dossier(value: object) -> list[str]:
    errors: list[str] = []
    if type(value) is not dict:
        return ["dossier_not_object"]
    if set(value) != TOP_KEYS:
        errors.append("top_level_shape_invalid")
    if value.get("schema") != SCHEMA:
        errors.append("wrong_schema")
    if value.get("record_scope") != SCOPE:
        errors.append("wrong_scope")

    authorities = value.get("authorities")
    if _exact(authorities, AUTHORITY_KEYS, "authorities", errors):
        if any(authorities[key] is not False for key in AUTHORITY_KEYS):
            errors.append("authority_forbidden")

    anchor = value.get("state_anchor")
    anchor_keys = {"chain_id", "block_number", "block_hash", "state_root"}
    if _exact(anchor, anchor_keys, "state_anchor", errors):
        if type(anchor["chain_id"]) is not int or anchor["chain_id"] <= 0:
            errors.append("chain_id_invalid")
        if type(anchor["block_number"]) is not int or anchor["block_number"] <= 0:
            errors.append("block_number_invalid")
        if not isinstance(anchor["block_hash"], str) or not HASH32.fullmatch(anchor["block_hash"]):
            errors.append("block_hash_invalid")
        if not isinstance(anchor["state_root"], str) or not HASH32.fullmatch(anchor["state_root"]):
            errors.append("state_root_invalid")

    protocol = value.get("protocol")
    protocol_keys = {"protocol_id", "deployment", "market_id", "version_commitment"}
    if _exact(protocol, protocol_keys, "protocol", errors):
        if not _text(protocol["protocol_id"]):
            errors.append("protocol_id_invalid")
        if not _address(protocol["deployment"]):
            errors.append("deployment_invalid")
        if not _hex32(protocol["market_id"]):
            errors.append("market_id_invalid")
        if not _hex32(protocol["version_commitment"]):
            errors.append("protocol_version_invalid")

    position = value.get("position")
    position_keys = {"borrower", "collateral_asset", "debt_asset", "position_commitment"}
    if _exact(position, position_keys, "position", errors):
        for key in ("borrower", "collateral_asset", "debt_asset"):
            if not _address(position[key]):
                errors.append(key + "_invalid")
        if not _hex32(position["position_commitment"]):
            errors.append("position_commitment_invalid")

    if all(type(x) is dict for x in (anchor, protocol, position)):
        expected_id = digest(canonical(identity_payload(value)))
        if value.get("opportunity_id") != expected_id:
            errors.append("opportunity_id_mismatch")
    elif not _hex32(value.get("opportunity_id")):
        errors.append("opportunity_id_invalid")

    decision = value.get("decision")
    decision_keys = {
        "verdict", "reason_code", "decision_model_commitment", "truth_complete",
        "economics_complete", "competition_complete",
    }
    if _exact(decision, decision_keys, "decision", errors):
        if decision["verdict"] not in {"NO-GO", "OBSERVAR"}:
            errors.append("census_go_forbidden")
        if not _text(decision["reason_code"]):
            errors.append("reason_code_invalid")
        if not _hex32(decision["decision_model_commitment"]):
            errors.append("decision_model_commitment_invalid")
        for key in ("truth_complete", "economics_complete", "competition_complete"):
            if type(decision[key]) is not bool:
                errors.append(key + "_invalid")

    economics = value.get("economics")
    economics_keys = {
        "gross_value_usd_wad", "net_success_usd_wad", "expected_value_usd_wad",
        "costs", "complete", "model_commitment",
    }
    if _exact(economics, economics_keys, "economics", errors):
        if type(economics["complete"]) is not bool:
            errors.append("economics_complete_invalid")
        if not _hex32(economics["model_commitment"]):
            errors.append("economics_model_commitment_invalid")
        for key in ("gross_value_usd_wad", "net_success_usd_wad", "expected_value_usd_wad"):
            val = economics[key]
            if val is not None and not _signed(val):
                errors.append(key + "_invalid")
        costs = economics["costs"]
        if type(costs) is not dict or set(costs) != set(COST_KINDS):
            errors.append("cost_vector_incomplete")
        else:
            known_all = True
            for kind in COST_KINDS:
                item = costs[kind]
                if type(item) is not dict or set(item) != {"known", "usd_wad", "evidence_sha256"}:
                    errors.append("cost_component_shape_invalid")
                    known_all = False
                    continue
                if type(item["known"]) is not bool:
                    errors.append("cost_known_invalid")
                    known_all = False
                    continue
                if item["known"]:
                    if not _unsigned(item["usd_wad"]) or not _hex32(item["evidence_sha256"]):
                        errors.append("known_cost_missing_value_or_evidence")
                        known_all = False
                else:
                    known_all = False
                    if item["usd_wad"] is not None or item["evidence_sha256"] is not None:
                        errors.append("unknown_cost_must_be_null")
            if type(economics["complete"]) is bool and economics["complete"] != known_all:
                errors.append("economics_completeness_mismatch")
            if economics["complete"] and any(
                economics[key] is None for key in
                ("gross_value_usd_wad", "net_success_usd_wad", "expected_value_usd_wad")
            ):
                errors.append("complete_economics_missing_summary")

    competition = value.get("competition")
    competition_keys = {
        "winner_address", "oracle_update_block", "winner_block",
        "builder_payment_share_wad", "evidence_sha256", "complete",
    }
    if _exact(competition, competition_keys, "competition", errors):
        if type(competition["complete"]) is not bool:
            errors.append("competition_complete_invalid")
        winner = competition["winner_address"]
        oracle_block = competition["oracle_update_block"]
        winner_block = competition["winner_block"]
        share = competition["builder_payment_share_wad"]
        evidence_sha = competition["evidence_sha256"]
        values_present = (
            _address(winner)
            and type(oracle_block) is int and oracle_block > 0
            and type(winner_block) is int and winner_block >= oracle_block
            and _unsigned(share) and int(share) <= 10**18
            and _hex32(evidence_sha)
        )
        all_null = all(v is None for v in (winner, oracle_block, winner_block, share, evidence_sha))
        if competition["complete"] and not values_present:
            errors.append("complete_competition_missing_fields")
        if not competition["complete"] and not all_null:
            errors.append("incomplete_competition_must_be_null")

    scenarios = value.get("scenarios")
    if type(scenarios) is not list or not scenarios:
        errors.append("scenarios_invalid")
    else:
        names = set()
        for item in scenarios:
            if type(item) is not dict or set(item) != {
                "name", "commitment_sha256", "material_discrepancy"
            }:
                errors.append("scenario_shape_invalid")
                continue
            if not _text(item["name"]) or item["name"] in names:
                errors.append("scenario_name_invalid")
            names.add(item.get("name"))
            if not _hex32(item["commitment_sha256"]):
                errors.append("scenario_commitment_invalid")
            if type(item["material_discrepancy"]) is not bool:
                errors.append("scenario_discrepancy_invalid")

    outcome = value.get("outcome")
    outcome_keys = {"status", "transaction_hash", "nqc_execution", "realized_pnl_usd_wad"}
    if _exact(outcome, outcome_keys, "outcome", errors):
        if outcome["status"] not in {"UNOBSERVED", "HISTORICAL_MARKET_ONLY"}:
            errors.append("outcome_status_forbidden")
        if outcome["nqc_execution"] is not False:
            errors.append("nqc_execution_claim_forbidden")
        if outcome["realized_pnl_usd_wad"] is not None:
            errors.append("realized_pnl_claim_forbidden")
        tx = outcome["transaction_hash"]
        if outcome["status"] == "UNOBSERVED" and tx is not None:
            errors.append("unobserved_transaction_forbidden")
        if outcome["status"] == "HISTORICAL_MARKET_ONLY":
            if not isinstance(tx, str) or not HASH32.fullmatch(tx):
                errors.append("historical_transaction_hash_invalid")

    evidence = value.get("evidence")
    if type(evidence) is not list or not evidence:
        errors.append("evidence_invalid")
    else:
        seen = set()
        for item in evidence:
            if type(item) is not dict or set(item) != {"kind", "locator", "sha256"}:
                errors.append("evidence_shape_invalid")
                continue
            if not _text(item["kind"]) or not _text(item["locator"]) or not _hex32(item["sha256"]):
                errors.append("evidence_reference_invalid")
            key = (item.get("kind"), item.get("locator"), item.get("sha256"))
            if key in seen:
                errors.append("duplicate_evidence")
            seen.add(key)

    blockers = value.get("blockers")
    if type(blockers) is not list or not blockers or blockers != sorted(set(blockers)):
        errors.append("blockers_invalid")
    elif any(not _text(item) for item in blockers):
        errors.append("blocker_value_invalid")

    if type(decision) is dict and type(economics) is dict and type(competition) is dict:
        if decision.get("economics_complete") is not economics.get("complete"):
            errors.append("decision_economics_link_mismatch")
        if decision.get("competition_complete") is not competition.get("complete"):
            errors.append("decision_competition_link_mismatch")

    commitment = value.get("dossier_commitment_sha256")
    if _hex32(commitment):
        unsigned = {key: val for key, val in value.items() if key != "dossier_commitment_sha256"}
        if commitment != digest(canonical(unsigned)):
            errors.append("dossier_commitment_mismatch")
    else:
        errors.append("dossier_commitment_invalid")
    return sorted(set(errors))


def seal_dossier(unsigned: dict) -> dict:
    """Seal a fully specified Census dossier; validation remains authoritative."""
    record = copy.deepcopy(unsigned)
    record.pop("opportunity_id", None)
    record.pop("dossier_commitment_sha256", None)
    if not all(key in record for key in ("state_anchor", "protocol", "position")):
        raise ValueError("identity_fields_missing")
    record["opportunity_id"] = digest(canonical(identity_payload(record)))
    record["dossier_commitment_sha256"] = digest(canonical(record))
    errors = validate_dossier(record)
    if errors:
        raise ValueError("invalid_dossier:" + ",".join(errors))
    return record


def store_dossier(directory: Path, dossier: dict) -> Path:
    errors = validate_dossier(dossier)
    if errors:
        raise ValueError("invalid_dossier:" + ",".join(errors))
    directory = Path(directory).absolute()
    if any(part.is_symlink() for part in (directory, *directory.parents)):
        raise ValueError("symlink_vault_directory")
    directory.mkdir(parents=True, exist_ok=True)
    filename = dossier["opportunity_id"] + "-" + dossier["dossier_commitment_sha256"] + ".json"
    final = directory / filename
    raw = canonical(dossier)
    if final.exists() or final.is_symlink():
        if read_regular(final, limit=2_097_152) != raw:
            raise ValueError("existing_dossier_mismatch")
        return final
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".omega-dossier-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, final)
        except FileExistsError:
            if read_regular(final, limit=2_097_152) != raw:
                raise ValueError("existing_dossier_mismatch") from None
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return final


def query_dossiers(directory: Path, *, verdict: str | None = None,
                   protocol_id: str | None = None,
                   min_block: int | None = None, max_block: int | None = None) -> list[dict]:
    """Fail the whole query if any record in the vault is invalid."""
    directory = Path(directory).absolute()
    if any(part.is_symlink() for part in (directory, *directory.parents)):
        raise ValueError("symlink_vault_directory")
    if not directory.is_dir():
        raise ValueError("vault_directory_missing")
    results = []
    for path in sorted(directory.iterdir()):
        if path.is_symlink() or not path.is_file() or path.suffix != ".json":
            raise ValueError("unreviewed_vault_entry:" + path.name)
        dossier = strict_json(read_regular(path, limit=2_097_152))
        errors = validate_dossier(dossier)
        if errors:
            raise ValueError("invalid_stored_dossier:" + path.name + ":" + ",".join(errors))
        expected_name = dossier["opportunity_id"] + "-" + dossier["dossier_commitment_sha256"] + ".json"
        if path.name != expected_name:
            raise ValueError("dossier_filename_mismatch:" + path.name)
        block = dossier["state_anchor"]["block_number"]
        if verdict is not None and dossier["decision"]["verdict"] != verdict:
            continue
        if protocol_id is not None and dossier["protocol"]["protocol_id"] != protocol_id:
            continue
        if min_block is not None and block < min_block:
            continue
        if max_block is not None and block > max_block:
            continue
        results.append({
            "opportunity_id": dossier["opportunity_id"],
            "dossier_commitment_sha256": dossier["dossier_commitment_sha256"],
            "block_number": block,
            "protocol_id": dossier["protocol"]["protocol_id"],
            "verdict": dossier["decision"]["verdict"],
            "outcome_status": dossier["outcome"]["status"],
        })
    return results
