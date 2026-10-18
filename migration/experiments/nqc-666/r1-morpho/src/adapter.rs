use crate::math::{self, HealthInput, WAD};
use nqc666::{
    engine::{Anchor, Engine, Key, Update},
    third_eye::{Assessment, Basis, Position},
};

#[derive(Clone, Copy, Debug)]
pub struct Snapshot {
    pub basis: Basis,
    pub key: Key,
    pub anchor: Anchor,
    pub block_timestamp_s: u64,
    /// Must already reflect accrual at the same block timestamp.
    pub accrued_through_s: u64,
    pub oracle_observed_s: u64,
    pub oracle_max_age_s: u64,
    pub math: HealthInput,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Rejection {
    Unknown,
    Identity,
    Time,
    Inputs,
    Arithmetic,
    Representation,
    Engine,
}
pub fn position<const FAST: bool>(
    s: Snapshot,
    key: Key,
    anchor: Anchor,
    near_bps: u16,
) -> Result<Position, Rejection> {
    if s.basis == Basis::Unknown {
        return Err(Rejection::Unknown);
    }
    if s.key != key
        || s.anchor != anchor
        || anchor.chain != 1
        || anchor.block == 0
        || anchor.hash == [0; 32]
        || key.market == [0; 32]
        || key.borrower == [0; 20]
    {
        return Err(Rejection::Identity);
    }
    if s.block_timestamp_s == 0
        || s.accrued_through_s != s.block_timestamp_s
        || s.oracle_observed_s == 0
        || s.oracle_observed_s > s.block_timestamp_s
        || s.oracle_max_age_s == 0
        || s.block_timestamp_s - s.oracle_observed_s > s.oracle_max_age_s
    {
        return Err(Rejection::Time);
    }
    let v = s.math;
    if near_bps > 10000
        || v.lltv >= WAD
        || v.oracle_price == crate::uint::U256::ZERO
        || v.borrow_shares > v.total_borrow_shares
    {
        return Err(Rejection::Inputs);
    }
    let h = math::health::<FAST>(v).map_err(|_| Rejection::Arithmetic)?;
    let debt = h.debt.as_u128().ok_or(Rejection::Representation)?;
    let cap = h.cap.as_u128().ok_or(Rejection::Representation)?;
    Ok(Position {
        basis: s.basis,
        debt: Some(debt),
        max_borrow: Some(cap),
        near_bps,
    })
}
/// A failed adapter still delivers an Unknown update, invalidating any old candidate/ticket.
/// Every row remains a fixture; commercial admission is false in the underlying engine.
pub fn on_snapshot<const FAST: bool>(
    engine: &mut Engine,
    slot: usize,
    s: Snapshot,
    mut u: Update,
    now_ns: u64,
) -> Result<Assessment, Rejection> {
    let result = position::<FAST>(s, u.integrity.key, u.integrity.anchor, u.position.near_bps);
    u.position = result.unwrap_or(Position {
        basis: Basis::Unknown,
        debt: None,
        max_borrow: None,
        near_bps: 0,
    });
    // A supplied-rate projection cannot silently become an observed snapshot.
    u.scenario = None;
    let assessment = engine
        .on_event(slot, u, now_ns)
        .map_err(|_| Rejection::Engine)?;
    result.map(|_| assessment)
}
