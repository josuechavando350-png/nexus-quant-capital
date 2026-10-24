//! Revision-11 cache/updateState and scaled-to-underlying balances.
//! The supplied cache/token values are not authenticated chain state.
use crate::{aave_validation::LIQUIDATION_RUNTIME_SHA256, digest};
use alloy_primitives::{keccak256, U256};
use serde::{Deserialize, Serialize};

const RAY: U256 = U256::from_limbs([11515845246265065472, 54210108, 0, 0]);
const YEAR: u64 = 31_536_000;
const MAX_U40: u64 = (1 << 40) - 1;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ReserveInput {
    pub liquidity_index_ray: String,
    pub variable_borrow_index_ray: String,
    pub liquidity_rate_ray: String,
    pub variable_borrow_rate_ray: String,
    pub accrued_to_treasury_scaled: String,
    pub last_update_timestamp: u64,
    pub reserve_factor_bps: u16,
    pub total_scaled_variable_debt: String,
    pub user_scaled_collateral: String,
    pub user_scaled_variable_debt: String,
    pub timestamp: u64,
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct ProjectedReserve {
    pub liquidity_index_ray: String,
    pub variable_borrow_index_ray: String,
    pub accrued_to_treasury_scaled: String,
    pub last_update_timestamp: u64,
    pub user_collateral_balance: String,
    pub user_variable_debt_balance: String,
}

#[derive(Debug, Serialize)]
pub struct ReserveReport {
    pub schema: String,
    pub profile: String,
    pub input_sha256: String,
    pub reference_liquidation_runtime_sha256: String,
    pub projection_passed: bool,
    pub projected: Option<ProjectedReserve>,
    pub revert_data: Option<String>,
    pub input_state_authenticated: bool,
    pub token_implementation_verified: bool,
    pub executable_eligibility_verified: bool,
    pub activation_allowed: bool,
}

#[derive(Debug)]
enum Revert {
    Arithmetic,
    Empty,
    Downcast(U256),
}
type Calc<T> = Result<T, Revert>;
impl Revert {
    fn data(self) -> String {
        match self {
            Self::Arithmetic => format!("0x4e487b71{:064x}", 0x11),
            Self::Empty => "0x".into(),
            Self::Downcast(value) => format!(
                "{}{:064x}{value:064x}",
                crate::historical::hex(
                    &keccak256("SafeCastOverflowedUintDowncast(uint8,uint256)")[..4]
                ),
                128
            ),
        }
    }
}
fn u128_checked(v: U256) -> Calc<U256> {
    if v > U256::from(u128::MAX) {
        Err(Revert::Downcast(v))
    } else {
        Ok(v)
    }
}
fn half_mul(a: U256, b: U256, scale: U256) -> Calc<U256> {
    a.checked_mul(b)
        .and_then(|v| v.checked_add(scale / U256::from(2)))
        .map(|v| v / scale)
        .ok_or(Revert::Empty)
}
fn mul_div(a: U256, b: U256, scale: U256, ceil: bool) -> Calc<U256> {
    let v = a.checked_mul(b).ok_or(Revert::Empty)?;
    let q = v.checked_div(scale).ok_or(Revert::Empty)?;
    Ok(q + U256::from(ceil && v % scale != U256::ZERO))
}
fn integer(value: &str, bits: usize) -> Result<U256, String> {
    if value.is_empty()
        || value.len() > 78
        || !value.bytes().all(|b| b.is_ascii_digit())
        || (value.len() > 1 && value.starts_with('0'))
    {
        return Err("expected canonical decimal integer".into());
    }
    let v = U256::from_str_radix(value, 10).map_err(|_| "uint256 overflow")?;
    if bits == 128 && v > U256::from(u128::MAX) {
        return Err("uint128 overflow".into());
    }
    Ok(v)
}
fn linear(rate: U256, elapsed: U256) -> Calc<U256> {
    rate.checked_mul(elapsed)
        .and_then(|v| (v / U256::from(YEAR)).checked_add(RAY))
        .ok_or(Revert::Arithmetic)
}
fn compounded(rate: U256, elapsed: U256) -> Calc<U256> {
    if elapsed == U256::ZERO {
        return Ok(RAY);
    }
    // Exact polynomial from the retained MathUtils, including its unchecked
    // operations. The public input domain bounds rate to uint128 and time to uint40.
    let x = rate.wrapping_mul(elapsed) / U256::from(YEAR);
    let inner = (x / U256::from(2)).wrapping_add(half_mul(x, x / U256::from(6), RAY)?);
    Ok(RAY.wrapping_add(x).wrapping_add(half_mul(x, inner, RAY)?))
}

pub fn project(input: &ReserveInput) -> Result<ReserveReport, String> {
    if input.timestamp > MAX_U40 || input.last_update_timestamp > MAX_U40 {
        return Err("unsupported uint40 timestamp".into());
    }
    let parsed = [
        integer(&input.liquidity_index_ray, 128),
        integer(&input.variable_borrow_index_ray, 128),
        integer(&input.liquidity_rate_ray, 128),
        integer(&input.variable_borrow_rate_ray, 128),
        integer(&input.accrued_to_treasury_scaled, 128),
        integer(&input.total_scaled_variable_debt, 256),
        integer(&input.user_scaled_collateral, 256),
        integer(&input.user_scaled_variable_debt, 256),
    ];
    let mut values = [U256::ZERO; 8];
    for (out, v) in values.iter_mut().zip(parsed) {
        *out = v?;
    }
    let (projected, revert_data) = match kernel(input, values) {
        Ok(v) => (Some(v), None),
        Err(e) => (None, Some(e.data())),
    };
    Ok(ReserveReport {
        schema: "nqc-miner-aave-reserve-projection-v1".into(),
        profile: "ethereum-aave-pool-revision-11-reserve-update-v1".into(),
        input_sha256: digest(&serde_json::to_vec(input).map_err(|e| e.to_string())?),
        reference_liquidation_runtime_sha256: LIQUIDATION_RUNTIME_SHA256.into(),
        projection_passed: projected.is_some(),
        projected,
        revert_data,
        input_state_authenticated: false,
        token_implementation_verified: false,
        executable_eligibility_verified: false,
        activation_allowed: false,
    })
}

fn kernel(input: &ReserveInput, values: [U256; 8]) -> Calc<ProjectedReserve> {
    let [mut liquidity, mut borrow, liquidity_rate, borrow_rate, mut treasury, total_debt, collateral, debt] =
        values;
    let previous_borrow = borrow;
    if input.last_update_timestamp != input.timestamp {
        // Do not reject a future timestamp ahead of the original branch that
        // reads it: an idle reserve can skip both interest calculations.
        let elapsed = || {
            input
                .timestamp
                .checked_sub(input.last_update_timestamp)
                .map(U256::from)
                .ok_or(Revert::Arithmetic)
        };
        if liquidity_rate != U256::ZERO {
            liquidity = u128_checked(half_mul(
                linear(liquidity_rate, elapsed()?)?,
                liquidity,
                RAY,
            )?)?;
        }
        if total_debt != U256::ZERO {
            borrow = u128_checked(half_mul(compounded(borrow_rate, elapsed()?)?, borrow, RAY)?)?;
        }
        if input.reserve_factor_bps != 0 {
            let delta = borrow
                .checked_sub(previous_borrow)
                .ok_or(Revert::Arithmetic)?;
            let accrued = mul_div(total_debt, delta, RAY, false)?;
            let mint = half_mul(
                accrued,
                U256::from(input.reserve_factor_bps),
                U256::from(10000),
            )?;
            if mint != U256::ZERO {
                let scaled = u128_checked(mul_div(mint, RAY, liquidity, false)?)?;
                treasury = treasury
                    .checked_add(scaled)
                    .filter(|v| *v <= U256::from(u128::MAX))
                    .ok_or(Revert::Arithmetic)?;
            }
        }
    }
    Ok(ProjectedReserve {
        liquidity_index_ray: liquidity.to_string(),
        variable_borrow_index_ray: borrow.to_string(),
        accrued_to_treasury_scaled: treasury.to_string(),
        last_update_timestamp: input.timestamp,
        user_collateral_balance: mul_div(collateral, liquidity, RAY, false)?.to_string(),
        user_variable_debt_balance: mul_div(debt, borrow, RAY, true)?.to_string(),
    })
}
