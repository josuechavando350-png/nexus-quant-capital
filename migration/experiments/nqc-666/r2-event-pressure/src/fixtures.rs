//! Synthetic pressure fixtures, never observations or financing commitments.
use nqc666::{engine::Update, fixtures};
pub const INSERT_AT: u64 = 200_000;
pub fn burst(expired: usize, seed: u64) -> (Vec<Update>, u64) {
    assert!(expired <= 256);
    let now = 700_000 + seed % 1000;
    let mut rows: Vec<_> = (0..256)
        .map(|slot| fixtures::update(fixtures::financial(16, seed + slot as u64), slot))
        .collect();
    for rank in 0..256 {
        let slot = (rank + (seed as usize % 256)) % 256;
        let u = &mut rows[slot];
        u.financial.max_age_ns = 3_000_000;
        u.integrity.oracle_max_age = 3_000_000;
        u.integrity.route_through =
            now + u.financial.send_budget_ns + if rank < expired { 0 } else { 1_000_000 };
        let net = 1_000_000 + (256 - rank) as u128 * 1000 + u128::from(seed % 997);
        u.financial.operator_weth_new = net;
        u.integrity.quoted_net_lower = Some(net);
    }
    (rows, now)
}
