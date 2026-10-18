// Original R1 adapter test; only the Engine/adapter imports target R2.
use nqc666::third_eye::Basis;
use nqc_666_event_pressure::adapter;
type Engine = nqc_666_event_pressure::engine::Engine<true, true>;
use nqc_666_morpho_math::{
    adapter::Rejection,
    fixtures,
    math::{SCALE, WAD},
    uint::U256,
};

#[test]
fn adapter_mutations_block_and_unknown_replaces_old_ticket() {
    let (s, u) = fixtures::row(1);
    let key = u.integrity.key;
    let anchor = u.integrity.anchor;
    let now = u.financial.now_ns;
    let mutations: Vec<fn(&mut adapter::Snapshot)> = vec![
        |s| s.basis = Basis::Unknown,
        |s| s.key.borrower[0] ^= 1,
        |s| s.key.market[0] ^= 1,
        |s| s.anchor.block += 1,
        |s| s.anchor.hash[0] ^= 1,
        |s| s.anchor.chain = 2,
        |s| s.block_timestamp_s = 0,
        |s| s.accrued_through_s -= 1,
        |s| s.accrued_through_s += 1,
        |s| s.oracle_observed_s = 0,
        |s| s.oracle_observed_s = s.block_timestamp_s + 1,
        |s| s.oracle_max_age_s = 9,
        |s| s.oracle_max_age_s = 0,
        |s| s.math.oracle_price = U256::ZERO,
        |s| s.math.oracle_price = U256::MAX,
        |s| s.math.borrow_shares = s.math.total_borrow_shares + 1,
        |s| s.math.lltv = WAD,
        |s| {
            s.math.collateral = 1;
            s.math.oracle_price = U256::from(SCALE)
                .checked_mul::<true>(u128::MAX.into())
                .unwrap()
                .checked_mul::<true>(2u128.into())
                .unwrap();
        },
    ];
    for (j, m) in mutations.iter().enumerate() {
        let mut engine = Engine::new(anchor, vec![key]).unwrap();
        adapter::on_snapshot::<true, true, true>(&mut engine, 0, s, u.clone(), now).unwrap();
        let old = engine.candidate(now).unwrap();
        assert!(!engine.finalize(old, now).commercial_admission);
        let mut bad = s;
        m(&mut bad);
        assert!(
            adapter::on_snapshot::<true, true, true>(&mut engine, 0, bad, u.clone(), now).is_err(),
            "{j}"
        );
        assert!(engine.candidate(now).is_none(), "{j}");
        assert_ne!(engine.finalize(old, now).reasons, 0, "{j}");
    }
    assert_eq!(
        adapter::position::<true>(s, key, anchor, 10001).unwrap_err(),
        Rejection::Inputs
    );
}
