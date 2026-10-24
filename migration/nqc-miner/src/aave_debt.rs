//! Revision-11 _burnDebtTokens and reserve rate/virtual-balance bookkeeping.
//! External token and rate-strategy outcomes are explicitly supplied assumptions.
use crate::{aave_validation::LIQUIDATION_RUNTIME_SHA256, digest};
use alloy_primitives::{keccak256, U256};
use serde::{Deserialize, Serialize};

const RAY: U256 = U256::from_limbs([11515845246265065472, 54210108, 0, 0]);

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "status", rename_all = "snake_case", deny_unknown_fields)]
pub enum BurnOutcome {
    Return {
        no_more_debt: bool,
        next_scaled_variable_debt: String,
    },
    Revert {
        data: String,
    },
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "status", rename_all = "snake_case", deny_unknown_fields)]
pub enum RateOutcome {
    Return {
        liquidity_rate_ray: String,
        variable_borrow_rate_ray: String,
    },
    Revert {
        data: String,
    },
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DebtInput {
    pub borrower_reserve_debt: String,
    pub actual_debt_to_liquidate: String,
    pub has_no_collateral_left: bool,
    pub next_variable_borrow_index_ray: String,
    pub current_scaled_variable_debt: String,
    pub reserve_deficit: String,
    pub virtual_underlying_balance: String,
    pub reserve_id: u16,
    pub user_configuration: String,
    pub reserve_factor: String,
    pub token_burn: BurnOutcome,
    pub rate_quote: RateOutcome,
}
#[derive(Debug, Serialize, PartialEq, Eq)]
pub struct RateInputs {
    pub unbacked: String,
    pub liquidity_added: String,
    pub liquidity_taken: String,
    pub total_variable_debt: String,
    pub reserve_factor: String,
    pub using_virtual_balance: bool,
    /// The strategy is called before adding the repayment to virtual balance.
    pub virtual_underlying_balance_before_update: String,
}
#[derive(Debug, Serialize, PartialEq, Eq)]
pub struct DebtAmounts {
    pub burn_called: bool,
    pub scaled_debt_to_burn: String,
    pub next_scaled_variable_debt: String,
    pub outstanding_debt: String,
    pub new_reserve_deficit: String,
    pub user_configuration: String,
    pub new_virtual_underlying_balance: String,
    pub liquidity_rate_ray: String,
    pub variable_borrow_rate_ray: String,
    pub no_more_debt: bool,
    pub rate_inputs: RateInputs,
}
#[derive(Debug, Serialize)]
pub struct DebtReport {
    pub schema: String,
    pub profile: String,
    pub input_sha256: String,
    pub reference_liquidation_runtime_sha256: String,
    pub calculation_passed: bool,
    pub amounts: Option<DebtAmounts>,
    pub revert_data: Option<String>,
    pub external_outcomes_supplied: bool,
    pub token_implementation_verified: bool,
    pub rate_strategy_verified: bool,
    pub input_state_authenticated: bool,
    pub executable_eligibility_verified: bool,
    pub activation_allowed: bool,
}
enum Revert {
    Arithmetic,
    Empty,
    Downcast(U256),
    InvalidReserve,
    External(String),
}
impl Revert {
    fn data(self) -> String {
        match self {
            Self::Arithmetic => format!("0x4e487b71{:064x}", 0x11),
            Self::Empty => "0x".into(),
            Self::Downcast(v) => format!(
                "{}{:064x}{v:064x}",
                crate::historical::hex(
                    &keccak256("SafeCastOverflowedUintDowncast(uint8,uint256)")[..4]
                ),
                128
            ),
            Self::InvalidReserve => {
                crate::historical::hex(&keccak256("InvalidReserveIndex()")[..4])
            }
            Self::External(data) => data,
        }
    }
}
type Calc<T> = Result<T, Revert>;
fn integer(value: &str, bits: u16) -> Result<U256, String> {
    if value.is_empty()
        || value.len() > 78
        || !value.bytes().all(|b| b.is_ascii_digit())
        || (value.len() > 1 && value.starts_with('0'))
    {
        return Err("expected canonical decimal uint256".into());
    }
    let v = U256::from_str_radix(value, 10).map_err(|_| "uint256 overflow")?;
    if bits == 128 && v > U256::from(u128::MAX) {
        return Err("uint128 overflow".into());
    }
    Ok(v)
}
fn revert_bytes(value: &str) -> Result<String, String> {
    let raw = value
        .strip_prefix("0x")
        .ok_or("revert bytes require 0x prefix")?;
    if raw.len() > 8192
        || raw.len() % 2 != 0
        || !raw
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        return Err("expected canonical lowercase revert bytes, at most 4096 bytes".into());
    }
    Ok(value.into())
}
fn downcast(v: U256) -> Calc<U256> {
    if v > U256::from(u128::MAX) {
        Err(Revert::Downcast(v))
    } else {
        Ok(v)
    }
}
fn add128(a: U256, b: U256) -> Calc<U256> {
    a.checked_add(b)
        .filter(|v| *v <= U256::from(u128::MAX))
        .ok_or(Revert::Arithmetic)
}
fn mul_div(a: U256, b: U256, divisor: U256, ceil: bool) -> Calc<U256> {
    let product = a.checked_mul(b).ok_or(Revert::Empty)?;
    let quotient = product.checked_div(divisor).ok_or(Revert::Empty)?;
    Ok(quotient + U256::from(ceil && product % divisor != U256::ZERO))
}

pub fn calculate(input: &DebtInput) -> Result<DebtReport, String> {
    let numbers = [
        integer(&input.borrower_reserve_debt, 256),
        integer(&input.actual_debt_to_liquidate, 256),
        integer(&input.next_variable_borrow_index_ray, 256),
        integer(&input.current_scaled_variable_debt, 256),
        integer(&input.reserve_deficit, 128),
        integer(&input.virtual_underlying_balance, 128),
        integer(&input.user_configuration, 256),
        integer(&input.reserve_factor, 256),
    ];
    let mut values = [U256::ZERO; 8];
    for (out, v) in values.iter_mut().zip(numbers) {
        *out = v?;
    }
    let burn = match &input.token_burn {
        BurnOutcome::Return {
            no_more_debt,
            next_scaled_variable_debt,
        } => Ok((*no_more_debt, integer(next_scaled_variable_debt, 256)?)),
        BurnOutcome::Revert { data } => Err(revert_bytes(data)?),
    };
    let quote = match &input.rate_quote {
        RateOutcome::Return {
            liquidity_rate_ray,
            variable_borrow_rate_ray,
        } => Ok((
            integer(liquidity_rate_ray, 256)?,
            integer(variable_borrow_rate_ray, 256)?,
        )),
        RateOutcome::Revert { data } => Err(revert_bytes(data)?),
    };
    let (amounts, revert_data) = match kernel(input, values, burn, quote) {
        Ok(value) => (Some(value), None),
        Err(e) => (None, Some(e.data())),
    };
    Ok(DebtReport {
        schema: "nqc-miner-aave-debt-v1".into(),
        profile: "ethereum-aave-pool-revision-11-debt-bookkeeping-v1".into(),
        input_sha256: digest(&serde_json::to_vec(input).map_err(|e| e.to_string())?),
        reference_liquidation_runtime_sha256: LIQUIDATION_RUNTIME_SHA256.into(),
        calculation_passed: amounts.is_some(),
        amounts,
        revert_data,
        external_outcomes_supplied: true,
        token_implementation_verified: false,
        rate_strategy_verified: false,
        input_state_authenticated: false,
        executable_eligibility_verified: false,
        activation_allowed: false,
    })
}
fn kernel(
    input: &DebtInput,
    values: [U256; 8],
    burn: Result<(bool, U256), String>,
    quote: Result<(U256, U256), String>,
) -> Calc<DebtAmounts> {
    let [debt, repayment, index, mut next_scaled, mut deficit, virtual_balance, mut config, factor] =
        values;
    let mut no_more_debt = true;
    let mut scaled_burn = U256::ZERO;
    if debt != U256::ZERO {
        let amount = if input.has_no_collateral_left {
            debt
        } else {
            repayment
        };
        scaled_burn = mul_div(amount, RAY, index, false)?;
        (no_more_debt, next_scaled) = burn.map_err(Revert::External)?;
    }
    let outstanding = debt.checked_sub(repayment).ok_or(Revert::Arithmetic)?;
    if input.has_no_collateral_left && outstanding != U256::ZERO {
        deficit = add128(deficit, downcast(outstanding)?)?;
    }
    if no_more_debt {
        if input.reserve_id >= 128 {
            return Err(Revert::InvalidReserve);
        }
        config &= !(U256::from(1) << (usize::from(input.reserve_id) * 2));
    }
    let total_debt = mul_div(next_scaled, index, RAY, true)?;
    let (liquidity_rate, variable_rate) = quote.map_err(Revert::External)?;
    let liquidity_rate = downcast(liquidity_rate)?;
    let variable_rate = downcast(variable_rate)?;
    let new_virtual_balance = if repayment > U256::ZERO {
        add128(virtual_balance, downcast(repayment)?)?
    } else {
        virtual_balance
    };
    Ok(DebtAmounts {
        burn_called: debt != U256::ZERO,
        scaled_debt_to_burn: scaled_burn.to_string(),
        next_scaled_variable_debt: next_scaled.to_string(),
        outstanding_debt: outstanding.to_string(),
        new_reserve_deficit: deficit.to_string(),
        user_configuration: config.to_string(),
        new_virtual_underlying_balance: new_virtual_balance.to_string(),
        liquidity_rate_ray: liquidity_rate.to_string(),
        variable_borrow_rate_ray: variable_rate.to_string(),
        no_more_debt,
        rate_inputs: RateInputs {
            unbacked: deficit.to_string(),
            liquidity_added: repayment.to_string(),
            liquidity_taken: "0".into(),
            total_variable_debt: total_debt.to_string(),
            reserve_factor: factor.to_string(),
            using_virtual_balance: true,
            virtual_underlying_balance_before_update: virtual_balance.to_string(),
        },
    })
}
