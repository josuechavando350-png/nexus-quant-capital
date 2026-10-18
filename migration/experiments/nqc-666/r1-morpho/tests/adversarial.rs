use nqc666::{
    engine::Engine,
    third_eye::{Basis, Observed},
};
use nqc_666_morpho_math::{
    adapter::{self, Rejection},
    fixtures,
    math::{self, Market, Rate, SCALE, WAD},
    uint::{Arithmetic, U256},
};
#[test]
fn overflow_and_solidity_round_up_failure_are_preserved() {
    assert_eq!(
        U256::MAX.checked_add(1u128.into()),
        Err(Arithmetic::Overflow)
    );
    assert_eq!(
        U256::ZERO.checked_sub(1u128.into()),
        Err(Arithmetic::Overflow)
    );
    assert_eq!(
        math::mul_div::<true>(U256::MAX, 1u128.into(), 2u128.into(), true),
        Err(Arithmetic::Overflow)
    );
    assert_eq!(
        math::mul_div::<true>(1u128.into(), 1u128.into(), U256::ZERO, true),
        Err(Arithmetic::Overflow)
    );
    assert_eq!(
        math::mul_div::<true>(1u128.into(), 1u128.into(), U256::ZERO, false),
        Err(Arithmetic::DivisionByZero)
    );
    assert_eq!(U256::MAX.checked_mul::<true>(U256::ZERO), Ok(U256::ZERO));
    for v in [
        U256::ZERO,
        U256::MAX,
        U256::from(u128::MAX),
        U256([1, 2, 3, 4]),
    ] {
        for d in [1u128, WAD, SCALE, u128::MAX] {
            assert_eq!(
                v.checked_div::<true>(d.into()),
                v.checked_div::<false>(d.into())
            );
        }
        assert_eq!(U256::from_hex(&v.hex()), Some(v));
    }
}
#[test]
fn share_rounding_and_equality_boundary() {
    let mut s = fixtures::row(0).0;
    s.math.total_borrow_assets = 99;
    s.math.total_borrow_shares = 99_000_000;
    s.math.borrow_shares = 1_000_000;
    s.math.collateral = 2;
    s.math.oracle_price = SCALE.into();
    s.math.lltv = WAD / 2;
    let a = math::health::<true>(s.math).unwrap();
    assert_eq!(a.debt, 1u128.into());
    assert_eq!(a.cap, 1u128.into());
    assert!(!a.eligible);
    s.math.borrow_shares += 1;
    let a = math::health::<true>(s.math).unwrap();
    assert_eq!(a.debt, 2u128.into());
    assert!(a.eligible);
    assert_eq!(math::health::<true>(s.math), math::health::<false>(s.math));
}
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
        adapter::on_snapshot::<true>(&mut engine, 0, s, u.clone(), now).unwrap();
        let old = engine.candidate(now).unwrap();
        assert!(!engine.finalize(old, now).commercial_admission);
        let mut bad = s;
        m(&mut bad);
        assert!(
            adapter::on_snapshot::<true>(&mut engine, 0, bad, u.clone(), now).is_err(),
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
#[test]
fn projection_is_separate_and_missing_rate_unknown() {
    let m = Market {
        supply_assets: 1_000_000 * WAD,
        supply_shares: 1_000_000_000_000 * WAD,
        borrow_assets: 100_000 * WAD,
        borrow_shares: 100_000_000_000 * WAD,
        last_update_s: 100,
        fee: WAD / 10,
    };
    assert!(math::project::<true>(m, 101, Rate::Unknown).is_none());
    assert!(math::project::<true>(m, 99, Rate::ZeroIrm).is_none());
    assert_eq!(
        math::project::<true>(m, 101, Rate::ZeroIrm)
            .unwrap()
            .interest,
        0
    );
    for t in [100, 101, 3600, 86400] {
        let r = Rate::Supplied(1_000_000_000u128.into());
        assert_eq!(
            math::project::<true>(m, t, r),
            math::project::<false>(m, t, r)
        );
    }
    assert!(math::project::<true>(m, u64::MAX, Rate::Supplied(U256::MAX)).is_none());
    assert!(math::project::<true>(
        Market {
            fee: WAD / 4 + 1,
            ..m
        },
        101,
        Rate::ZeroIrm
    )
    .is_none());
}
#[test]
fn integrated_trace_matches_reference_and_keeps_admission_false() {
    let rows: Vec<_> = (0..256).map(fixtures::row).collect();
    let anchor = rows[0].1.integrity.anchor;
    let keys: Vec<_> = rows.iter().map(|r| r.1.integrity.key).collect();
    let mut fast = Engine::new(anchor, keys.clone()).unwrap();
    let mut reference = Engine::new(anchor, keys).unwrap();
    let mut rng = 66601u64;
    for n in 0..4096 {
        rng ^= rng << 13;
        rng ^= rng >> 7;
        rng ^= rng << 17;
        let slot = rng as usize % 256;
        let (mut s, u) = rows[slot].clone();
        if n % 11 == 0 {
            s.accrued_through_s -= 1;
        }
        let now = u.financial.now_ns;
        assert_eq!(
            adapter::on_snapshot::<true>(&mut fast, slot, s, u.clone(), now),
            adapter::on_snapshot::<false>(&mut reference, slot, s, u, now)
        );
        let a = fast.candidate(now);
        let b = reference.candidate(now);
        assert_eq!(a.map(|x| x.slot()), b.map(|x| x.slot()));
        if let (Some(a), Some(b)) = (a, b) {
            let a = fast.finalize(a, now);
            let b = reference.finalize(b, now);
            assert_eq!(a.reasons, b.reasons);
            assert_eq!(a.financial, b.financial);
            assert!(!a.commercial_admission);
        }
    }
    let p = adapter::position::<true>(rows[0].0, rows[0].0.key, anchor, 100).unwrap();
    assert_ne!(
        nqc666::third_eye::assess(p, None, 0).observed,
        Observed::Eligible
    );
}
