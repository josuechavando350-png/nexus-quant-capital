//! Revision-11 collateral exhaustion and final fee cap on supplied balances.
//! The post-liquidator balance is an external input, not a simulated token transfer.
use crate::{aave_validation::LIQUIDATION_RUNTIME_SHA256, digest};
use alloy_primitives::U256;
use serde::{Deserialize, Serialize};

const RAY: U256 = U256::from_limbs([11515845246265065472, 54210108, 0, 0]);

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CollateralInput {
    pub liquidity_index_ray: String,
    pub borrower_scaled_collateral_balance: String,
    pub collateral_to_liquidator: String,
    pub protocol_fee_collateral: String,
    pub collateral_price: String,
    pub collateral_decimals: u8,
    pub total_collateral_base: String,
    /// Value returned by scaledBalanceOf after the liquidator's token operation.
    /// It is deliberately not inferred by subtracting the requested transfer.
    pub post_liquidator_scaled_balance: String,
}

#[derive(Debug, Serialize, PartialEq, Eq)]
pub struct CollateralAmounts {
    pub scaled_collateral_consumed: String,
    pub consumed_collateral_base: String,
    pub reserve_fully_consumed: bool,
    pub has_no_collateral_left: bool,
    pub clear_collateral_flag: bool,
    /// The contract still calls the token when a nonzero fee is capped to zero.
    pub fee_transfer_required: bool,
    pub final_protocol_fee_collateral: String,
    pub final_protocol_fee_scaled: String,
}

#[derive(Debug, Serialize)]
pub struct CollateralReport {
    pub schema: String,
    pub profile: String,
    pub input_sha256: String,
    pub reference_liquidation_runtime_sha256: String,
    pub calculation_passed: bool,
    pub amounts: Option<CollateralAmounts>,
    pub revert_data: Option<String>,
    pub post_liquidator_balance_supplied: bool,
    pub token_operations_executed: bool,
    pub input_state_authenticated: bool,
    pub executable_eligibility_verified: bool,
    pub activation_allowed: bool,
}

enum Revert {
    Empty,
    Arithmetic,
}
impl Revert {
    fn data(self) -> String {
        match self {
            Self::Empty => "0x".into(),
            Self::Arithmetic => format!("0x4e487b71{:064x}", 0x11),
        }
    }
}
type Calc<T> = Result<T, Revert>;
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
fn mul_div(a: U256, b: U256, divisor: U256, ceil: bool) -> Calc<U256> {
    let product = a.checked_mul(b).ok_or(Revert::Empty)?;
    let quotient = product.checked_div(divisor).ok_or(Revert::Empty)?;
    Ok(quotient + U256::from(ceil && product % divisor != U256::ZERO))
}

pub fn calculate(input: &CollateralInput) -> Result<CollateralReport, String> {
    let numbers = [
        &input.liquidity_index_ray,
        &input.borrower_scaled_collateral_balance,
        &input.collateral_to_liquidator,
        &input.protocol_fee_collateral,
        &input.collateral_price,
        &input.total_collateral_base,
        &input.post_liquidator_scaled_balance,
    ]
    .map(|value| integer(value));
    let mut parsed = [U256::ZERO; 7];
    for (out, value) in parsed.iter_mut().zip(numbers) {
        *out = value?;
    }
    let (amounts, revert_data) = match kernel(input.collateral_decimals, parsed) {
        Ok(value) => (Some(value), None),
        Err(reason) => (None, Some(reason.data())),
    };
    Ok(CollateralReport {
        schema: "nqc-miner-aave-collateral-v1".into(),
        profile: "ethereum-aave-pool-revision-11-collateral-kernel-v1".into(),
        input_sha256: digest(&serde_json::to_vec(input).map_err(|e| e.to_string())?),
        reference_liquidation_runtime_sha256: LIQUIDATION_RUNTIME_SHA256.into(),
        calculation_passed: amounts.is_some(),
        amounts,
        revert_data,
        post_liquidator_balance_supplied: true,
        token_operations_executed: false,
        input_state_authenticated: false,
        executable_eligibility_verified: false,
        activation_allowed: false,
    })
}

fn kernel(decimals: u8, values: [U256; 7]) -> Calc<CollateralAmounts> {
    let [index, scaled_balance, liquidator, fee, price, total_base, post_balance] = values;
    let unit = U256::from(10)
        .checked_pow(U256::from(decimals))
        .ok_or(Revert::Arithmetic)?;
    // Sum the two independent ceil divisions before capping. An overflow must
    // revert even if a saturating implementation would later cap the result.
    let consumed = mul_div(liquidator, RAY, index, true)?
        .checked_add(mul_div(fee, RAY, index, true)?)
        .ok_or(Revert::Arithmetic)?
        .min(scaled_balance);
    let fully_consumed = consumed == scaled_balance;
    let consumed_base = mul_div(consumed, index, RAY, false)?
        .checked_mul(price)
        .ok_or(Revert::Arithmetic)?
        / unit;
    let no_collateral = consumed_base == total_base;
    let mut fee_amount = fee;
    let mut fee_scaled = U256::ZERO;
    if fee != U256::ZERO {
        fee_scaled = mul_div(fee, RAY, index, true)?;
        if fee_scaled > post_balance {
            fee_scaled = post_balance;
            fee_amount = mul_div(post_balance, index, RAY, false)?;
        }
    }
    Ok(CollateralAmounts {
        scaled_collateral_consumed: consumed.to_string(),
        consumed_collateral_base: consumed_base.to_string(),
        reserve_fully_consumed: fully_consumed,
        has_no_collateral_left: no_collateral,
        clear_collateral_flag: fully_consumed || no_collateral,
        fee_transfer_required: fee != U256::ZERO,
        final_protocol_fee_collateral: fee_amount.to_string(),
        final_protocol_fee_scaled: fee_scaled.to_string(),
    })
}
