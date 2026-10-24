//! Offline revision-11 amount kernel, after initial validation and index updates.
//! Inputs are supplied, not authenticated. No token operations or execution claim.
use crate::{aave_validation::LIQUIDATION_RUNTIME_SHA256, digest};
use alloy_primitives::{keccak256, U256};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AmountInput {
    pub collateral_balance: String,
    pub reserve_debt: String,
    pub total_debt_base: String,
    pub health_factor_wad: String,
    pub collateral_price: String,
    pub debt_price: String,
    pub collateral_decimals: u8,
    pub debt_decimals: u8,
    /// Already selected from reserve/eMode configuration by the caller.
    pub liquidation_bonus_bps: u16,
    pub liquidation_protocol_fee_bps: u16,
    pub debt_to_cover: String,
}

#[derive(Debug, Serialize, PartialEq, Eq)]
pub struct Amounts {
    pub max_liquidatable_debt: String,
    pub debt_to_liquidate: String,
    /// Before token-index transfer rounding and any treasury fee cap.
    pub collateral_to_liquidator: String,
    pub protocol_fee_collateral: String,
    pub reserve_debt_base: String,
    pub reserve_collateral_base: String,
}

#[derive(Debug, Serialize)]
pub struct AmountReport {
    pub schema: String,
    pub profile: String,
    pub input_sha256: String,
    pub reference_liquidation_runtime_sha256: String,
    pub amount_calculation_passed: bool,
    pub amounts: Option<Amounts>,
    pub revert_data: Option<String>,
    pub initial_conditions_checked: bool,
    pub input_state_authenticated: bool,
    pub executable_eligibility_verified: bool,
    pub activation_allowed: bool,
}

#[derive(Debug, Clone, Copy)]
enum Revert {
    Arithmetic,
    DivisionByZero,
    Empty,
    Dust,
}
impl Revert {
    fn data(self) -> String {
        match self {
            Self::Arithmetic => format!("0x4e487b71{:064x}", 0x11),
            Self::DivisionByZero => format!("0x4e487b71{:064x}", 0x12),
            Self::Empty => "0x".into(),
            Self::Dust => crate::historical::hex(&keccak256("MustNotLeaveDust()")[..4]),
        }
    }
}
type Calc<T> = Result<T, Revert>;
fn mul(a: U256, b: U256) -> Calc<U256> {
    a.checked_mul(b).ok_or(Revert::Arithmetic)
}
fn add(a: U256, b: U256) -> Calc<U256> {
    a.checked_add(b).ok_or(Revert::Arithmetic)
}
fn sub(a: U256, b: U256) -> Calc<U256> {
    a.checked_sub(b).ok_or(Revert::Arithmetic)
}
fn div(a: U256, b: U256) -> Calc<U256> {
    a.checked_div(b).ok_or(Revert::DivisionByZero)
}
// Aave's assembly helpers revert with empty bytes, unlike checked Solidity math.
fn mul_div(a: U256, b: U256, c: U256, ceil: bool) -> Calc<U256> {
    let product = a.checked_mul(b).ok_or(Revert::Empty)?;
    let quotient = product.checked_div(c).ok_or(Revert::Empty)?;
    Ok(quotient + U256::from(ceil && product % c != U256::ZERO))
}
fn percent_half_up(a: U256) -> Calc<U256> {
    a.checked_mul(U256::from(5000))
        .and_then(|p| p.checked_add(U256::from(5000)))
        .map(|p| p / U256::from(10000))
        .ok_or(Revert::Empty)
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

pub fn calculate(input: &AmountInput) -> Result<AmountReport, String> {
    // Parse all inputs before evaluating a contract result. Malformed JSON is
    // never represented as a Solidity rejection or a successful zero amount.
    let numbers = [
        &input.collateral_balance,
        &input.reserve_debt,
        &input.total_debt_base,
        &input.health_factor_wad,
        &input.collateral_price,
        &input.debt_price,
        &input.debt_to_cover,
    ]
    .map(|v| integer(v));
    let mut parsed = [U256::ZERO; 7];
    for (out, value) in parsed.iter_mut().zip(numbers) {
        *out = value?;
    }
    let result = kernel(input, parsed);
    let (amounts, revert_data) = match result {
        Ok(value) => (Some(value), None),
        Err(reason) => (None, Some(reason.data())),
    };
    Ok(AmountReport {
        schema: "nqc-miner-aave-amounts-v1".into(),
        profile: "ethereum-aave-pool-revision-11-amount-kernel-v1".into(),
        input_sha256: digest(&serde_json::to_vec(input).map_err(|e| e.to_string())?),
        reference_liquidation_runtime_sha256: LIQUIDATION_RUNTIME_SHA256.into(),
        amount_calculation_passed: amounts.is_some(),
        amounts,
        revert_data,
        initial_conditions_checked: false,
        input_state_authenticated: false,
        executable_eligibility_verified: false,
        activation_allowed: false,
    })
}

fn kernel(input: &AmountInput, numbers: [U256; 7]) -> Calc<Amounts> {
    let [balance, debt, total_debt, health, collateral_price, debt_price, requested] = numbers;
    let unit = |decimals: u8| {
        U256::from(10)
            .checked_pow(U256::from(decimals))
            .ok_or(Revert::Arithmetic)
    };
    let collateral_unit = unit(input.collateral_decimals)?;
    let debt_unit = unit(input.debt_decimals)?;
    let bonus = U256::from(input.liquidation_bonus_bps);
    let fee_bps = U256::from(input.liquidation_protocol_fee_bps);
    let bps = U256::from(10000);
    let debt_base = mul_div(debt, debt_price, debt_unit, true)?;
    let collateral_base = div(mul(balance, collateral_price)?, collateral_unit)?;
    let threshold = U256::from(200_000_000_000u64);
    let mut max_debt = debt;
    if collateral_base >= threshold
        && debt_base >= threshold
        && health > U256::from(950_000_000_000_000_000u64)
    {
        let default_debt_base = percent_half_up(total_debt)?;
        if debt_base > default_debt_base {
            max_debt = div(mul(default_debt_base, debt_unit)?, debt_price)?;
        }
    }
    let mut actual_debt = requested.min(max_debt);
    let base_collateral = div(
        mul(mul(debt_price, actual_debt)?, collateral_unit)?,
        mul(collateral_price, debt_unit)?,
    )?;
    let max_collateral = mul_div(base_collateral, bonus, bps, false)?;
    let mut collateral;
    if max_collateral > balance {
        collateral = balance;
        actual_debt = mul_div(
            div(
                mul(mul(collateral_price, collateral)?, debt_unit)?,
                mul(debt_price, collateral_unit)?,
            )?,
            bps,
            bonus,
            true,
        )?;
    } else {
        collateral = max_collateral;
    }
    let mut fee = U256::ZERO;
    if fee_bps != U256::ZERO {
        let bonus_collateral = sub(collateral, mul_div(collateral, bps, bonus, false)?)?;
        fee = mul_div(bonus_collateral, fee_bps, bps, true)?;
        collateral = sub(collateral, fee)?;
    }
    if actual_debt < debt && add(collateral, fee)? < balance {
        let debt_left = mul_div(sub(debt, actual_debt)?, debt_price, debt_unit, true)?;
        let collateral_left = div(
            mul(sub(sub(balance, collateral)?, fee)?, collateral_price)?,
            collateral_unit,
        )?;
        if debt_left < threshold / U256::from(2) || collateral_left < threshold / U256::from(2) {
            return Err(Revert::Dust);
        }
    }
    Ok(Amounts {
        max_liquidatable_debt: max_debt.to_string(),
        debt_to_liquidate: actual_debt.to_string(),
        collateral_to_liquidator: collateral.to_string(),
        protocol_fee_collateral: fee.to_string(),
        reserve_debt_base: debt_base.to_string(),
        reserve_collateral_base: collateral_base.to_string(),
    })
}
