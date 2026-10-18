use crate::uint::{Arithmetic, U256};
pub const WAD: u128 = 1_000_000_000_000_000_000;
pub const SCALE: u128 = WAD * WAD;
pub const VIRTUAL_SHARES: u128 = 1_000_000;

pub fn mul_div<const FAST: bool>(x: U256, y: U256, d: U256, up: bool) -> Result<U256, Arithmetic> {
    let product = x.checked_mul::<FAST>(y)?;
    // Preserve Solidity's checked intermediate addition, even when the quotient would fit.
    let numerator = if up {
        product.checked_add(d.checked_sub(1u128.into())?)?
    } else {
        product
    };
    numerator.checked_div::<FAST>(d)
}
pub fn to_assets<const FAST: bool>(
    s: U256,
    a: U256,
    total_s: U256,
    up: bool,
) -> Result<U256, Arithmetic> {
    mul_div::<FAST>(
        s,
        a.checked_add(1u128.into())?,
        total_s.checked_add(VIRTUAL_SHARES.into())?,
        up,
    )
}
pub fn taylor<const FAST: bool>(rate: U256, elapsed: U256) -> Result<U256, Arithmetic> {
    let first = rate.checked_mul::<FAST>(elapsed)?;
    let second = mul_div::<FAST>(first, first, (2 * WAD).into(), false)?;
    let third = mul_div::<FAST>(second, first, (3 * WAD).into(), false)?;
    first.checked_add(second)?.checked_add(third)
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct HealthInput {
    pub total_borrow_assets: u128,
    pub total_borrow_shares: u128,
    pub borrow_shares: u128,
    pub collateral: u128,
    pub oracle_price: U256,
    pub lltv: u128,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Health {
    pub debt: U256,
    pub cap: U256,
    pub eligible: bool,
}
/// Exact formula components; not a storage reader or the complete Morpho health-check control flow.
#[inline(never)]
pub fn health<const FAST: bool>(v: HealthInput) -> Result<Health, Arithmetic> {
    let debt = to_assets::<FAST>(
        v.borrow_shares.into(),
        v.total_borrow_assets.into(),
        v.total_borrow_shares.into(),
        true,
    )?;
    let value = mul_div::<FAST>(v.collateral.into(), v.oracle_price, SCALE.into(), false)?;
    let cap = mul_div::<FAST>(value, v.lltv.into(), WAD.into(), false)?;
    Ok(Health {
        debt,
        cap,
        eligible: debt > cap,
    })
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Market {
    pub supply_assets: u128,
    pub supply_shares: u128,
    pub borrow_assets: u128,
    pub borrow_shares: u128,
    pub last_update_s: u64,
    pub fee: u128,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Rate {
    Unknown,
    ZeroIrm,
    /// An explicitly supplied rate: does NOT simulate an IRM or authenticate its output.
    Supplied(U256),
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Projection {
    pub market: Market,
    pub interest: u128,
    pub fee_shares: u128,
}
/// Exact arithmetic on a supplied-rate scenario. This never produces an observed snapshot.
pub fn project<const FAST: bool>(m: Market, timestamp_s: u64, rate: Rate) -> Option<Projection> {
    if m.last_update_s == 0 || timestamp_s < m.last_update_s || m.fee > WAD / 4 {
        return None;
    }
    let elapsed = timestamp_s - m.last_update_s;
    let interest = match rate {
        Rate::Unknown => return None,
        Rate::ZeroIrm => 0,
        Rate::Supplied(r) => mul_div::<FAST>(
            m.borrow_assets.into(),
            taylor::<FAST>(r, (elapsed as u128).into()).ok()?,
            WAD.into(),
            false,
        )
        .ok()?
        .as_u128()?,
    };
    let supply = m.supply_assets.checked_add(interest)?;
    let borrow = m.borrow_assets.checked_add(interest)?;
    let fee = mul_div::<FAST>(interest.into(), m.fee.into(), WAD.into(), false)
        .ok()?
        .as_u128()?;
    let fee_shares = mul_div::<FAST>(
        fee.into(),
        U256::from(m.supply_shares)
            .checked_add(VIRTUAL_SHARES.into())
            .ok()?,
        U256::from(supply.checked_sub(fee)?)
            .checked_add(1u128.into())
            .ok()?,
        false,
    )
    .ok()?
    .as_u128()?;
    Some(Projection {
        market: Market {
            supply_assets: supply,
            borrow_assets: borrow,
            supply_shares: m.supply_shares.checked_add(fee_shares)?,
            last_update_s: timestamp_s,
            ..m
        },
        interest,
        fee_shares,
    })
}
