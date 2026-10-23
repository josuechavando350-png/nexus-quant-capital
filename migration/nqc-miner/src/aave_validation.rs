//! Offline model of the identified revision-11 validateLiquidationCall function.
//! Passing these initial conditions never certifies a complete liquidation.
use crate::{digest, valid_hex};
use alloy_primitives::{keccak256, U256};
use serde::{Deserialize, Serialize};

pub const PROFILE: &str = "ethereum-aave-pool-revision-11-validation-v1";
pub const LIQUIDATION_RUNTIME_SHA256: &str =
    "b11e141dc76358768078be0818b39d60b5b68385aed43552a617ad572e821914";
const MAX_U40: u64 = (1 << 40) - 1;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ValidationInput {
    pub borrower: String,
    pub liquidator: String,
    pub collateral_configuration: String,
    pub debt_configuration: String,
    pub collateral_grace_until: u64,
    pub debt_grace_until: u64,
    pub collateral_reserve_id: u16,
    pub user_configuration: String,
    pub health_factor_wad: String,
    pub selected_debt: String,
    pub timestamp: u64,
}

#[derive(Debug, Serialize, PartialEq, Eq)]
pub struct Condition {
    pub name: String,
    pub passed: bool,
}

#[derive(Debug, Serialize, PartialEq, Eq)]
pub struct ValidationReport {
    pub schema: String,
    pub profile: String,
    pub input_sha256: String,
    pub reference_liquidation_runtime_sha256: String,
    /// Only conditions reached before the first revert, in Solidity order.
    pub conditions: Vec<Condition>,
    pub initial_conditions_passed: bool,
    pub first_error: Option<String>,
    pub revert_selector: Option<String>,
    pub input_state_authenticated: bool,
    pub input_implementation_verified: bool,
    pub executable_eligibility_verified: bool,
    pub activation_allowed: bool,
}

fn integer(value: &str) -> Result<U256, String> {
    if value.is_empty()
        || value.len() > 78
        || !value.bytes().all(|b| b.is_ascii_digit())
        || (value.len() > 1 && value.starts_with('0'))
    {
        return Err("expected canonical decimal uint256".into());
    }
    U256::from_str_radix(value, 10).map_err(|_| "uint256 overflow".into())
}

pub fn validate(input: &ValidationInput) -> Result<ValidationReport, String> {
    if !valid_hex(&input.borrower, 20)
        || !valid_hex(&input.liquidator, 20)
        || input.timestamp > MAX_U40
        || input.collateral_grace_until > MAX_U40
        || input.debt_grace_until > MAX_U40
    {
        return Err("unsupported address or uint40 timestamp/grace".into());
    }
    let collateral = integer(&input.collateral_configuration)?;
    let debt = integer(&input.debt_configuration)?;
    let user = integer(&input.user_configuration)?;
    let health = integer(&input.health_factor_wad)?;
    let selected_debt = integer(&input.selected_debt)?;
    let mut report = ValidationReport {
        schema: "nqc-miner-aave-initial-conditions-v1".into(),
        profile: PROFILE.into(),
        input_sha256: digest(&serde_json::to_vec(input).map_err(|e| e.to_string())?),
        reference_liquidation_runtime_sha256: LIQUIDATION_RUNTIME_SHA256.into(),
        conditions: Vec::new(),
        initial_conditions_passed: false,
        first_error: None,
        revert_selector: None,
        input_state_authenticated: false,
        input_implementation_verified: false,
        executable_eligibility_verified: false,
        activation_allowed: false,
    };
    let checks = [
        (
            "different_liquidator",
            input.borrower != input.liquidator,
            "SelfLiquidation",
        ),
        (
            "both_reserves_active",
            collateral.bit(56) && debt.bit(56),
            "ReserveInactive",
        ),
        (
            "both_reserves_unpaused",
            !collateral.bit(60) && !debt.bit(60),
            "ReservePaused",
        ),
        (
            "both_grace_periods_expired",
            input.collateral_grace_until < input.timestamp
                && input.debt_grace_until < input.timestamp,
            "LiquidationGraceSentinelCheckFailed",
        ),
        (
            "health_below_one",
            health < U256::from(1_000_000_000_000_000_000u64),
            "HealthFactorNotBelowThreshold",
        ),
        (
            "collateral_reserve_id_in_bitmap",
            input.collateral_reserve_id < 128,
            "InvalidReserveIndex",
        ),
        (
            "borrower_enabled_collateral",
            input.collateral_reserve_id < 128
                && user.bit(usize::from(input.collateral_reserve_id) * 2 + 1),
            "CollateralCannotBeLiquidated",
        ),
        (
            "selected_asset_has_debt",
            !selected_debt.is_zero(),
            "SpecifiedCurrencyNotBorrowedByUser",
        ),
    ];
    for (name, passed, error) in checks {
        report.conditions.push(Condition {
            name: name.into(),
            passed,
        });
        if !passed {
            report.first_error = Some(error.into());
            report.revert_selector = Some(crate::historical::hex(
                &keccak256(format!("{error}()"))[..4],
            ));
            return Ok(report);
        }
    }
    report.initial_conditions_passed = true;
    Ok(report)
}
