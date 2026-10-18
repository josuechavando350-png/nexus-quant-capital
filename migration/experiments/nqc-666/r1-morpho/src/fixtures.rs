use crate::{
    adapter::Snapshot,
    math::{HealthInput, SCALE, WAD},
    uint::U256,
};
use nqc666::{engine::Update, fixtures, third_eye::Basis};
pub fn row(k: usize) -> (Snapshot, Update) {
    let u = fixtures::update(fixtures::financial(16, k as u64 + 1), k);
    let unit = [1_000_000u128, 1_000_000_000, WAD, WAD * 1000][k % 4];
    let assets = unit * (1000 + k as u128);
    let shares = assets * 1_000_000;
    let s = Snapshot {
        basis: Basis::SyntheticFixture,
        key: u.integrity.key,
        anchor: u.integrity.anchor,
        block_timestamp_s: 1_800_000_000,
        accrued_through_s: 1_800_000_000,
        oracle_observed_s: 1_799_999_990,
        oracle_max_age_s: 60,
        math: HealthInput {
            total_borrow_assets: assets,
            total_borrow_shares: shares,
            borrow_shares: shares / 100,
            collateral: unit * if k.is_multiple_of(3) { 20 } else { 5 },
            oracle_price: U256::from(SCALE + (k as u128 % 7) * SCALE / 100),
            lltv: 8 * WAD / 10,
        },
    };
    (s, u)
}
