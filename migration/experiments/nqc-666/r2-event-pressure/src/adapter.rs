//! R1 snapshot ingress with identical fail-closed semantics, targeting the R2 engine.
use crate::engine::Engine;
use nqc666::{
    engine::Update,
    third_eye::{Assessment, Basis, Position},
};
pub use nqc_666_morpho_math::adapter::{position, Rejection, Snapshot};

/// A failed adapter still delivers an Unknown update, invalidating any old candidate/ticket.
/// Every row remains a fixture; commercial admission is false in the underlying engine.
pub fn on_snapshot<const FAST: bool, const BULK: bool, const SINGLE_WRITE: bool>(
    engine: &mut Engine<BULK, SINGLE_WRITE>,
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
