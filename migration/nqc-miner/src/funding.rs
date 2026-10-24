//! Current Titan-only gas policy and offline review of supplied funding terms.
//!
//! An artifact locator or a consistent claim does not authenticate Titan, fund a
//! transaction, or authorize execution. No result from this module enables money.
use crate::controls::EvidenceHash;
use alloy_primitives::U256;
use serde::{Deserialize, Serialize};

pub const POLICY_ID: &str = "nqc-miner-titan-only-gas-v1";
pub const INPUT_SCHEMA: &str = "nqc-miner-gas-funding-input-v1";

/// Native gas-asset wei, never MXN or USD. Decimal strings avoid JSON rounding.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "String", into = "String")]
pub struct Wei(U256);
impl TryFrom<String> for Wei {
    type Error = &'static str;
    fn try_from(value: String) -> Result<Self, Self::Error> {
        if value.is_empty()
            || value.len() > 78
            || !value.bytes().all(|b| b.is_ascii_digit())
            || (value.len() > 1 && value.starts_with('0'))
        {
            return Err("wei must be a canonical uint256 decimal string");
        }
        U256::from_str_radix(&value, 10)
            .map(Self)
            .map_err(|_| "wei exceeds uint256")
    }
}
impl From<Wei> for String {
    fn from(value: Wei) -> Self {
        value.0.to_string()
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct FundingPolicy {
    pub id: &'static str,
    pub designated_gas_sponsor: &'static str,
    pub operator_gas_budget_wei: Wei,
    pub operator_prefunding_allowed: bool,
    pub operator_gas_fallback_allowed: bool,
    pub operator_principal_collateral_guarantees_allowed: bool,
    pub execution_specific_evidence_required: bool,
    pub spending_enabled: bool,
}
pub fn policy() -> FundingPolicy {
    FundingPolicy {
        id: POLICY_ID,
        designated_gas_sponsor: "titan",
        operator_gas_budget_wei: Wei(U256::ZERO),
        operator_prefunding_allowed: false,
        operator_gas_fallback_allowed: false,
        operator_principal_collateral_guarantees_allowed: false,
        execution_specific_evidence_required: true,
        spending_enabled: false,
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FundingParent {
    pub number: u64,
    pub hash: EvidenceHash,
}

/// One exact bundle targeting the next block, with caller-supplied cost bounds.
/// All zero-liability fields are required; absent/unknown never implies zero.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct GasPlan {
    pub chain_id: u64,
    pub bundle_digest: EvidenceHash,
    pub execution_code_sha256: EvidenceHash,
    pub parent_block: FundingParent,
    pub target_block: u64,
    pub gas_limit: u64,
    pub max_fee_per_gas_wei: Wei,
    pub additional_network_fee_cap_wei: Wei,
    pub operator_prefund_wei: Wei,
    pub operator_principal_required: bool,
    pub operator_collateral_required: bool,
    pub operator_guarantee_required: bool,
    pub operator_gas_fallback: bool,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ReviewContext {
    pub chain_id: u64,
    pub parent_block: FundingParent,
    pub now_unix_seconds: u64,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ClaimScope {
    ExactExecution,
    GeneralStatement,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ClaimBasis {
    ExternalObservation,
    Simulated,
    Shadow,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OutcomeCaps {
    pub included_success_wei: Option<Wei>,
    pub included_failure_wei: Option<Wei>,
    pub not_included_wei: Option<Wei>,
}

/// These are untrusted supplied terms. `evidence_artifact_sha256` is only a locator.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SponsorshipClaim {
    pub sponsor: String,
    pub scope: ClaimScope,
    pub basis: ClaimBasis,
    pub plan_sha256: EvidenceHash,
    pub evidence_artifact_sha256: EvidenceHash,
    pub observed_at: u64,
    pub expires_at: u64,
    pub revoked: bool,
    pub operator_recourse_allowed: bool,
    pub caps: OutcomeCaps,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FundingInput {
    pub schema: String,
    pub plan: GasPlan,
    pub context: ReviewContext,
    pub claim: Option<SponsorshipClaim>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct FundingReport {
    pub schema: &'static str,
    pub policy: FundingPolicy,
    pub input_sha256: EvidenceHash,
    pub plan_sha256: EvidenceHash,
    pub plan: GasPlan,
    pub context: ReviewContext,
    pub supplied_claim: Option<SponsorshipClaim>,
    pub maximum_network_cost_wei: Wei,
    pub declared_terms_consistent: bool,
    pub terms_blockers: Vec<&'static str>,
    pub operational_blockers: [&'static str; 3],
    pub input_state_authenticated: bool,
    pub sponsorship_authenticated: bool,
    pub execution_gas_coverage_verified: bool,
    pub activation_allowed: bool,
    pub spending_authorized: bool,
    pub network_used: bool,
}

fn hash_json(value: &impl Serialize) -> EvidenceHash {
    // Only fixed structs/scalars are serialized here; there are no unordered maps.
    EvidenceHash::sha256(&serde_json::to_vec(value).expect("fixed funding types serialize"))
}
pub fn plan_sha256(plan: &GasPlan) -> EvidenceHash {
    hash_json(&(POLICY_ID, plan))
}

pub fn assess(input: &FundingInput) -> Result<FundingReport, &'static str> {
    let p = &input.plan;
    let c = &input.context;
    if input.schema != INPUT_SCHEMA {
        return Err("unsupported funding input schema");
    }
    if p.chain_id == 0 || c.chain_id == 0 || c.now_unix_seconds == 0 {
        return Err("nonzero chain and review time required");
    }
    if p.parent_block.number.checked_add(1) != Some(p.target_block) {
        return Err("plan must target the block immediately after its pinned parent");
    }
    if p.gas_limit == 0 || p.max_fee_per_gas_wei.0 == U256::ZERO {
        return Err("nonzero gas limit and fee cap required");
    }
    let maximum = U256::from(p.gas_limit)
        .checked_mul(p.max_fee_per_gas_wei.0)
        .and_then(|v| v.checked_add(p.additional_network_fee_cap_wei.0))
        .ok_or("network cost exceeds uint256")?;
    let digest = plan_sha256(p);
    let mut blockers = Vec::new();
    if p.chain_id != c.chain_id {
        blockers.push("review_chain_mismatch");
    }
    if p.parent_block != c.parent_block {
        blockers.push("parent_changed_or_target_stale");
    }
    if p.operator_prefund_wei.0 != U256::ZERO {
        blockers.push("operator_prefunding_forbidden");
    }
    for (required, reason) in [
        (
            p.operator_principal_required,
            "operator_principal_forbidden",
        ),
        (
            p.operator_collateral_required,
            "operator_collateral_forbidden",
        ),
        (
            p.operator_guarantee_required,
            "operator_guarantee_forbidden",
        ),
    ] {
        if required {
            blockers.push(reason);
        }
    }
    if p.operator_gas_fallback {
        blockers.push("operator_gas_fallback_forbidden");
    }
    match &input.claim {
        None => blockers.push("execution_specific_titan_terms_missing"),
        Some(claim) => {
            if claim.sponsor != "titan" {
                blockers.push("designated_sponsor_mismatch");
            }
            if claim.scope != ClaimScope::ExactExecution {
                blockers.push("general_sponsorship_is_not_execution_coverage");
            }
            if claim.basis != ClaimBasis::ExternalObservation {
                blockers.push("paper_evidence_is_not_funding");
            }
            if claim.plan_sha256 != digest {
                blockers.push("claim_plan_mismatch");
            }
            if claim.revoked {
                blockers.push("sponsorship_claim_revoked");
            }
            if claim.observed_at == 0
                || claim.observed_at > c.now_unix_seconds
                || claim.observed_at >= claim.expires_at
                || c.now_unix_seconds >= claim.expires_at
            {
                blockers.push("sponsorship_claim_not_current");
            }
            if claim.operator_recourse_allowed {
                blockers.push("operator_recourse_forbidden");
            }
            for (cap, missing, short) in [
                (
                    claim.caps.included_success_wei,
                    "success_terms_unknown",
                    "success_cap_insufficient",
                ),
                (
                    claim.caps.included_failure_wei,
                    "failure_terms_unknown",
                    "failure_cap_insufficient",
                ),
            ] {
                match cap {
                    None => blockers.push(missing),
                    Some(cap) if cap.0 < maximum => blockers.push(short),
                    Some(_) => (),
                }
            }
            // No network gas is consumed by an unincluded bundle. An explicit
            // zero term is still required; omission is not a statement of terms.
            if claim.caps.not_included_wei.is_none() {
                blockers.push("not_included_terms_unknown");
            }
        }
    }
    Ok(FundingReport {
        schema: "nqc-miner-gas-funding-review-v1",
        policy: policy(),
        input_sha256: hash_json(&(POLICY_ID, input)),
        plan_sha256: digest,
        plan: p.clone(),
        context: c.clone(),
        supplied_claim: input.claim.clone(),
        maximum_network_cost_wei: Wei(maximum),
        declared_terms_consistent: blockers.is_empty(),
        terms_blockers: blockers,
        operational_blockers: [
            "sponsor_identity_and_terms_not_authenticated",
            "explicit_execution_authorization_not_verified",
            "operational_bridge_disabled",
        ],
        input_state_authenticated: false,
        sponsorship_authenticated: false,
        execution_gas_coverage_verified: false,
        activation_allowed: false,
        spending_authorized: false,
        network_used: false,
    })
}
