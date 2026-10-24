use alloy_primitives::U256;
use nqc_miner::controls::EvidenceHash;
use nqc_miner::funding::*;
use proptest::prelude::*;

fn wei(v: impl ToString) -> Wei {
    Wei::try_from(v.to_string()).unwrap()
}
fn hash(n: u8) -> EvidenceHash {
    EvidenceHash::new([n; 32]).unwrap()
}
fn parent(number: u64, hash: EvidenceHash) -> FundingParent {
    FundingParent { number, hash }
}
fn fixture() -> FundingInput {
    let p = GasPlan {
        chain_id: 1,
        bundle_digest: hash(1),
        execution_code_sha256: hash(2),
        parent_block: parent(100, hash(3)),
        target_block: 101,
        gas_limit: 300_000,
        max_fee_per_gas_wei: wei(30_000_000_000u64),
        additional_network_fee_cap_wei: wei(15),
        operator_prefund_wei: wei(0),
        operator_principal_required: false,
        operator_collateral_required: false,
        operator_guarantee_required: false,
        operator_gas_fallback: false,
    };
    let claim = SponsorshipClaim {
        sponsor: "titan".into(),
        scope: ClaimScope::ExactExecution,
        basis: ClaimBasis::ExternalObservation,
        plan_sha256: plan_sha256(&p),
        evidence_artifact_sha256: hash(4),
        observed_at: 900,
        expires_at: 1100,
        revoked: false,
        operator_recourse_allowed: false,
        caps: OutcomeCaps {
            included_success_wei: Some(wei(9_000_000_000_000_015u64)),
            included_failure_wei: Some(wei(9_000_000_000_000_015u64)),
            not_included_wei: Some(wei(0)),
        },
    };
    FundingInput {
        schema: INPUT_SCHEMA.into(),
        context: ReviewContext {
            chain_id: 1,
            parent_block: p.parent_block,
            now_unix_seconds: 1000,
        },
        plan: p,
        claim: Some(claim),
    }
}
fn rejected(input: &FundingInput, reason: &str) {
    let r = assess(input).unwrap();
    assert!(!r.declared_terms_consistent);
    assert!(r.terms_blockers.contains(&reason), "{:?}", r.terms_blockers);
    assert!(!r.execution_gas_coverage_verified);
    assert!(!r.activation_allowed);
}

#[test]
fn current_policy_has_no_operator_allowance_and_consistent_claim_never_enables_money() {
    let p = policy();
    assert_eq!(p.designated_gas_sponsor, "titan");
    assert_eq!(p.operator_gas_budget_wei, wei(0));
    assert!(!p.operator_prefunding_allowed);
    assert!(!p.operator_gas_fallback_allowed);
    assert!(!p.operator_principal_collateral_guarantees_allowed);
    assert!(!p.spending_enabled);
    let i = fixture();
    let r = assess(&i).unwrap();
    assert!(r.declared_terms_consistent);
    assert_eq!(r.maximum_network_cost_wei, wei(9_000_000_000_000_015u64));
    assert_eq!(r.plan, i.plan);
    assert_eq!(r.supplied_claim, i.claim);
    assert_eq!(r.operational_blockers.len(), 3);
    assert!(!r.sponsorship_authenticated);
    assert!(!r.input_state_authenticated);
    assert!(!r.execution_gas_coverage_verified);
    assert!(!r.activation_allowed);
    assert!(!r.spending_authorized);
    assert!(!r.network_used);
}

#[test]
fn missing_terms_are_unknown_and_general_statement_cannot_cover_an_execution() {
    let mut i = fixture();
    i.claim = None;
    rejected(&i, "execution_specific_titan_terms_missing");
    i = fixture();
    i.claim.as_mut().unwrap().scope = ClaimScope::GeneralStatement;
    rejected(&i, "general_sponsorship_is_not_execution_coverage");
    i.claim.as_mut().unwrap().sponsor = "other".into();
    rejected(&i, "designated_sponsor_mismatch");
}

#[test]
fn simulated_and_shadow_claims_never_count_as_external_funding() {
    for basis in [ClaimBasis::Simulated, ClaimBasis::Shadow] {
        let mut i = fixture();
        i.claim.as_mut().unwrap().basis = basis;
        rejected(&i, "paper_evidence_is_not_funding");
    }
}

#[test]
fn all_operator_exposures_are_rejected_even_with_rebound_titan_terms() {
    let paths = [
        ("operator_prefund_wei", "operator_prefunding_forbidden"),
        (
            "operator_principal_required",
            "operator_principal_forbidden",
        ),
        (
            "operator_collateral_required",
            "operator_collateral_forbidden",
        ),
        (
            "operator_guarantee_required",
            "operator_guarantee_forbidden",
        ),
    ];
    for (key, reason) in paths {
        let mut json = serde_json::to_value(fixture()).unwrap();
        json["plan"][key] = if key == "operator_prefund_wei" {
            "1".into()
        } else {
            true.into()
        };
        let mut i: FundingInput = serde_json::from_value(json).unwrap();
        i.claim.as_mut().unwrap().plan_sha256 = plan_sha256(&i.plan);
        rejected(&i, reason);
    }
    let mut i = fixture();
    i.plan.operator_gas_fallback = true;
    i.claim.as_mut().unwrap().plan_sha256 = plan_sha256(&i.plan);
    rejected(&i, "operator_gas_fallback_forbidden");
    i = fixture();
    i.claim.as_mut().unwrap().operator_recourse_allowed = true;
    rejected(&i, "operator_recourse_forbidden");
}

#[test]
fn every_plan_field_is_bound_to_claim_and_report_identity() {
    let i = fixture();
    let base = serde_json::to_value(&i).unwrap();
    let original = assess(&i).unwrap();
    for (key, value) in [
        ("chain_id", serde_json::json!(42161)),
        ("bundle_digest", serde_json::json!(hash(11))),
        ("execution_code_sha256", serde_json::json!(hash(12))),
        ("gas_limit", serde_json::json!(299999)),
        ("max_fee_per_gas_wei", serde_json::json!("30000000001")),
        ("additional_network_fee_cap_wei", serde_json::json!("16")),
        ("operator_prefund_wei", serde_json::json!("1")),
        ("operator_principal_required", serde_json::json!(true)),
        ("operator_collateral_required", serde_json::json!(true)),
        ("operator_guarantee_required", serde_json::json!(true)),
        ("operator_gas_fallback", serde_json::json!(true)),
    ] {
        let mut changed = base.clone();
        changed["plan"][key] = value;
        let changed: FundingInput = serde_json::from_value(changed).unwrap();
        rejected(&changed, "claim_plan_mismatch");
        assert_ne!(
            assess(&changed).unwrap().input_sha256,
            original.input_sha256
        );
    }
    let mut changed = i.clone();
    changed.plan.parent_block = parent(101, hash(20));
    changed.plan.target_block = 102;
    rejected(&changed, "claim_plan_mismatch");
}

#[test]
fn context_chain_reorg_and_stale_target_are_rechecked_without_changing_plan() {
    let mut i = fixture();
    i.context.chain_id = 42161;
    rejected(&i, "review_chain_mismatch");
    for parent in [parent(100, hash(9)), parent(101, hash(3))] {
        i = fixture();
        i.context.parent_block = parent;
        rejected(&i, "parent_changed_or_target_stale");
    }
}

#[test]
fn claim_times_and_revocation_fail_closed_including_expiry_boundary() {
    for (observed, expires, now) in [
        (0, 1100, 1000),
        (1001, 1100, 1000),
        (900, 900, 1000),
        (900, 1000, 1000),
        (900, 999, 1000),
    ] {
        let mut i = fixture();
        i.context.now_unix_seconds = now;
        let c = i.claim.as_mut().unwrap();
        c.observed_at = observed;
        c.expires_at = expires;
        rejected(&i, "sponsorship_claim_not_current");
    }
    let mut i = fixture();
    i.context.now_unix_seconds = 900;
    assert!(assess(&i).unwrap().declared_terms_consistent);
    i.claim.as_mut().unwrap().revoked = true;
    rejected(&i, "sponsorship_claim_revoked");
}

#[test]
fn failure_coverage_cannot_be_inferred_from_success_or_omitted_as_zero() {
    for key in [
        "included_success_wei",
        "included_failure_wei",
        "not_included_wei",
    ] {
        let mut data = serde_json::to_value(fixture()).unwrap();
        data["claim"]["caps"][key] = serde_json::Value::Null;
        let i: FundingInput = serde_json::from_value(data).unwrap();
        assert!(!assess(&i).unwrap().declared_terms_consistent);
    }
    let mut i = fixture();
    i.claim.as_mut().unwrap().caps.included_success_wei = Some(wei(9_000_000_000_000_014u64));
    rejected(&i, "success_cap_insufficient");
    i = fixture();
    i.claim.as_mut().unwrap().caps.included_failure_wei = Some(wei(0));
    rejected(&i, "failure_cap_insufficient");
}

#[test]
fn malformed_decimal_and_non_string_wei_are_rejected_without_rounding() {
    for value in [
        "", "00", "01", "-1", "+1", "1.0", "1e3", " 1", "0x1", "１２", "NaN",
    ] {
        assert!(Wei::try_from(value.to_owned()).is_err());
    }
    for value in [
        serde_json::json!(1),
        serde_json::json!(true),
        serde_json::Value::Null,
    ] {
        assert!(serde_json::from_value::<Wei>(value).is_err());
    }
    assert_eq!(String::from(wei(U256::MAX)), U256::MAX.to_string());
    assert!(Wei::try_from(format!("{}0", U256::MAX)).is_err());
    let above = "115792089237316195423570985008687907853269984665640564039457584007913129639936";
    assert!(Wei::try_from(above.to_owned()).is_err());
}

#[test]
fn cost_arithmetic_detects_multiplication_and_addition_overflow() {
    let mut i = fixture();
    i.plan.max_fee_per_gas_wei = wei(U256::MAX);
    assert_eq!(assess(&i).unwrap_err(), "network cost exceeds uint256");
    i.plan.gas_limit = 1;
    i.plan.additional_network_fee_cap_wei = wei(1);
    assert_eq!(assess(&i).unwrap_err(), "network cost exceeds uint256");
    i.plan.additional_network_fee_cap_wei = wei(0);
    i.claim = None;
    assert_eq!(assess(&i).unwrap().maximum_network_cost_wei, wei(U256::MAX));
}

#[test]
fn invalid_schema_zero_chain_time_gas_and_target_are_errors() {
    let base = serde_json::to_value(fixture()).unwrap();
    for pointer in [
        "/plan/chain_id",
        "/context/chain_id",
        "/context/now_unix_seconds",
        "/plan/gas_limit",
    ] {
        let mut data = base.clone();
        *data.pointer_mut(pointer).unwrap() = 0.into();
        assert!(assess(&serde_json::from_value(data).unwrap()).is_err());
    }
    let mut i = fixture();
    i.schema = "legacy-own-gas-v1".into();
    assert!(assess(&i).is_err());
    i = fixture();
    i.plan.max_fee_per_gas_wei = wei(0);
    assert!(assess(&i).is_err());
    for block in [100, 102, u64::MAX] {
        i = fixture();
        i.plan.target_block = block;
        assert!(assess(&i).is_err());
    }
    i.plan.parent_block = parent(u64::MAX, hash(3));
    assert!(assess(&i).is_err());
}

#[test]
fn missing_operator_zero_fields_and_unknown_authority_flags_are_not_defaults() {
    let base = serde_json::to_value(fixture()).unwrap();
    for key in [
        "operator_prefund_wei",
        "operator_principal_required",
        "operator_collateral_required",
        "operator_guarantee_required",
        "operator_gas_fallback",
        "additional_network_fee_cap_wei",
    ] {
        let mut data = base.clone();
        data["plan"].as_object_mut().unwrap().remove(key);
        assert!(serde_json::from_value::<FundingInput>(data).is_err());
    }
    for pointer in [
        "",
        "/plan",
        "/context",
        "/plan/parent_block",
        "/context/parent_block",
        "/claim",
        "/claim/caps",
    ] {
        let mut data = base.clone();
        data.pointer_mut(pointer)
            .unwrap()
            .as_object_mut()
            .unwrap()
            .insert("spending_authorized".into(), true.into());
        assert!(serde_json::from_value::<FundingInput>(data).is_err());
    }
}

#[test]
fn report_is_reproducible_and_time_revocation_and_artifact_change_its_digest() {
    let i = fixture();
    let r = assess(&i).unwrap();
    assert_eq!(r, assess(&i).unwrap());
    let mut changed = i.clone();
    changed.context.now_unix_seconds += 1;
    assert_ne!(assess(&changed).unwrap().input_sha256, r.input_sha256);
    changed = i.clone();
    changed.claim.as_mut().unwrap().revoked = true;
    assert_ne!(assess(&changed).unwrap().input_sha256, r.input_sha256);
    changed = i.clone();
    changed.claim.as_mut().unwrap().evidence_artifact_sha256 = hash(50);
    assert_ne!(assess(&changed).unwrap().input_sha256, r.input_sha256);
    assert_eq!(assess(&changed).unwrap().plan_sha256, r.plan_sha256);
}

proptest! {
    #[test]
    fn cost_is_exact_and_matching_terms_never_authenticate_sponsor(gas in 1u64..u64::MAX, fee in 1u64..u64::MAX, extra in any::<u64>()) {
        let mut i = fixture();
        i.plan.gas_limit = gas;
        i.plan.max_fee_per_gas_wei = wei(fee);
        i.plan.additional_network_fee_cap_wei = wei(extra);
        let expected = U256::from(gas) * U256::from(fee) + U256::from(extra);
        let c = i.claim.as_mut().unwrap();
        c.plan_sha256 = plan_sha256(&i.plan);
        c.caps.included_success_wei = Some(wei(expected));
        c.caps.included_failure_wei = Some(wei(expected));
        let r = assess(&i).unwrap();
        prop_assert!(r.declared_terms_consistent);
        prop_assert_eq!(r.maximum_network_cost_wei, wei(expected));
        prop_assert!(!r.spending_authorized);
        prop_assert!(!r.execution_gas_coverage_verified);
    }
    #[test]
    fn any_nonzero_operator_prefunding_is_forbidden(amount in 1u64..u64::MAX) {
        let mut i = fixture(); i.plan.operator_prefund_wei = wei(amount);
        i.claim.as_mut().unwrap().plan_sha256 = plan_sha256(&i.plan);
        let r = assess(&i).unwrap();
        prop_assert!(r.terms_blockers.contains(&"operator_prefunding_forbidden"));
        prop_assert!(!r.declared_terms_consistent);
    }
}
