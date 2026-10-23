"""Offline fail-closed consistency audit for Omega's architecture plan.

This checks plan integrity only: NOT protocol truth, market coverage,
reconstruction parity, simulated economics, or authorization to trade.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from integrity import read_regular, strict_json

HERE = Path(__file__).resolve().parent
PHASES = ("Census", "Shadow", "Canary", "Escala")
EXPECTED_COUNTS = {"Census": 9, "Shadow": 9, "Canary": 4, "Escala": 14}
CENSUS_IDS = {1, 6, 7, 8, 10, 24, 25, 29, 32}
EXPECTED_SOURCE_SHA256 = "5c1739799ab5099bc95f7347aeed8bcc2e3b098e64c3688584331004f15edf0f"
EXPECTED_LAYERS = {
    **{n: "L0" for n in range(1, 6)},
    **{n: "L1" for n in range(6, 11)},
    **{n: "L2" for n in range(11, 17)},
    **{n: "L3" for n in range(17, 21)},
    **{n: "L4" for n in range(21, 24)},
    **{n: "L5" for n in range(24, 29)},
    **{n: "L6" for n in range(29, 32)},
    **{n: "L7" for n in range(32, 37)},
}
EXPECTED_PHASE_BY_ID = dict(zip(range(1, 37), (
    "Census", "Escala", "Escala", "Escala", "Canary",
    "Census", "Census", "Census", "Shadow", "Census",
    "Shadow", "Shadow", "Shadow", "Canary", "Escala", "Shadow",
    "Shadow", "Shadow", "Escala", "Escala", "Shadow", "Escala", "Canary",
    "Census", "Census", "Canary", "Escala", "Escala",
    "Census", "Shadow", "Escala", "Census", "Escala", "Escala", "Escala", "Escala",
)))
REQUIRED_ACCEPTANCE = {
    "Census": {"historical_truth_parity", "all_scoped_positions_reconciled", "bonuses_winners_blocks_builder_tips_measured"},
    "Shadow": {"reorganization_replay", "material_simulation_disagreements_resolved", "latency_percentiles_measured", "competitive_temporal_replay", "complete_net_costs"},
    "Canary": {"executor_invariants_and_formal_verification", "kill_switch_and_loss_budget", "real_capture_with_bounded_gas"},
    "Escala": {"verified_real_canary_capture", "out_of_sample_net_margin_improvement"},
}


def verify_plan(plan: object) -> list[str]:
    """Return sorted deterministic errors. Empty result = structurally valid only."""
    problems = []
    if not isinstance(plan, dict):
        return ["plan_not_object"]
    if plan.get("schema") != "nqc.omega.architecture.v1":
        problems.append("wrong_schema")
    source = plan.get("source")
    if not isinstance(source, dict) or source.get("pdf_sha256") != EXPECTED_SOURCE_SHA256:
        problems.append("source_pdf_sha256_missing")
    if plan.get("phase_order") != list(PHASES):
        problems.append("phase_order_wrong")
    safety = plan.get("safety")
    if not isinstance(safety, dict) or any(safety.get(k) is not False for k in (
        "observer_can_sign", "observer_can_broadcast", "observer_can_spend",
        "live_operation_authorized", "legacy_workflows_enabled",
    )):
        problems.append("safety_boundary_broken")
    # User directive 2026-10-23 supersedes the PDF's proprietary gas allowance.
    # A funding policy names the payer; it is not execution-specific coverage.
    expected_gas = {"schema": "nqc.omega.titan-gas-policy.v1", "payer": "TITAN",
        "operator_gas_cap_mxn": 0, "operator_prefund_allowed": False,
        "operator_principal_allowed": False, "operator_collateral_allowed": False,
        "operator_guarantees_allowed": False, "own_gas_fallback_allowed": False,
        "per_execution_coverage_required": True, "execution_coverage_proven": False,
        "funded_wallets_in_census_or_shadow_allowed": False,
        "basis": "USER_DIRECTIVE_2026-10-23", "supersedes": "CANARY_2000_MXN_ALLOWANCE"}
    policy = plan.get("gas_funding_policy")
    if (type(policy) is not dict or set(policy) != set(expected_gas)
            or any(type(policy[k]) is not type(v) or policy[k] != v
                   for k, v in expected_gas.items())):
        problems.append("gas_funding_policy_changed")
    if "canary_gas_budget_mxn" in plan:
        problems.append("obsolete_operator_gas_budget")
    acceptance = plan.get("acceptance")
    if not isinstance(acceptance, dict) or any(
        not isinstance(acceptance.get(p), list)
        or any(type(gate) is not str for gate in acceptance[p])
        or set(acceptance[p]) != REQUIRED_ACCEPTANCE[p]
        or len(acceptance[p]) != len(REQUIRED_ACCEPTANCE[p])
        for p in PHASES
    ):
        problems.append("phase_gates_missing_or_changed")
    components = plan.get("components")
    if not isinstance(components, list):
        return sorted(problems + ["components_not_list"])
    if len(components) != 36:
        problems.append("expected_36_components")
    if any(not isinstance(c, dict) for c in components):
        return sorted(problems + ["component_not_object"])
    identifiers = [c.get("id") for c in components]
    if len(identifiers) != 36 or any(type(i) is not int for i in identifiers) or sorted(identifiers) != list(range(1, 37)):
        return sorted(set(problems + ["component_ids_invalid"]))
    if any(type(c.get("phase")) is not str or type(c.get("layer")) is not str for c in components):
        return sorted(set(problems + ["component_phase_or_layer_type_invalid"]))
    counts = Counter(c.get("phase") for c in components)
    if dict(counts) != EXPECTED_COUNTS:
        problems.append("wrong_phase_counts")
    layers = {c.get("layer") for c in components}
    if layers != {f"L{i}" for i in range(8)}:
        problems.append("layer_coverage_invalid")
    if {c.get("id") for c in components if c.get("phase") == "Census"} != CENSUS_IDS:
        problems.append("census_components_changed")
    if any(c.get("layer") != EXPECTED_LAYERS.get(c.get("id")) for c in components):
        problems.append("component_layer_mismatch")
    if any(c.get("phase") != EXPECTED_PHASE_BY_ID.get(c.get("id")) for c in components):
        problems.append("component_phase_mismatch")
    if any(c.get("omega_verification") != "not_assessed" for c in components):
        problems.append("unsupported_verification_claim")
    if any(not isinstance(c.get("name"), str) or not c["name"].strip() for c in components):
        problems.append("missing_component_name")
    return sorted(set(problems))


def main() -> int:
    try:
        plan = strict_json(read_regular(HERE / "architecture_v3.json"))
    except (OSError, ValueError, RecursionError) as exc:
        print(f"BLOCK: plan unavailable or malformed: {exc}")
        return 2
    errors = verify_plan(plan)
    if errors:
        print("BLOCK: " + ", ".join(errors))
        return 1
    print("STRUCTURAL PASS: 36 components; 8 layers; Census/Shadow/Canary/Escala = 9/9/4/14.")
    print("NOT CERTIFIED: no chain truth, economic edge, funds, or deployment validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
