use nqc666::{engine::*, financial::*, fixtures, prepared::Prepared, third_eye::*};

#[test]
fn prepared_equivalence_at_boundaries() {
    for n in [1, 4, 16] {
        let base = fixtures::financial(n, 666);
        for (recv, age, cut, quote, budget, now) in [
            (100000, 1000000, 10000000, 10000000, 500000, 200000),
            (1, 9, 100, 100, 1, 2),
            (u64::MAX - 100, 200, u64::MAX, u64::MAX, 1, u64::MAX - 50),
        ] {
            let mut c = base.clone();
            c.received_ns = recv;
            c.max_age_ns = age;
            c.cutoff_ns = cut;
            c.quote_expiry_ns = quote;
            c.send_budget_ns = budget;
            c.now_ns = now;
            let p = Prepared::new(&c).unwrap();
            let edge = recv
                .saturating_add(age)
                .min(cut - budget - 1)
                .min(quote - budget - 1);
            for t in [
                0,
                recv - 1,
                recv,
                now,
                edge,
                edge.saturating_add(1),
                u64::MAX,
            ] {
                for epoch in [0, 1, 2, u64::MAX] {
                    c.now_ns = t;
                    c.current_epoch = epoch;
                    let correct = screen(&c).reasons == 0;
                    assert_eq!(p.branchy(epoch, t), correct);
                    assert_eq!(p.packed(epoch, t), correct);
                    assert_eq!(p.compact().ready(epoch, t), correct);
                }
            }
        }
    }
}
#[test]
fn prepared_random_equivalence() {
    let mut rng = 666666u64;
    for _ in 0..100000 {
        rng ^= rng << 13;
        rng ^= rng >> 7;
        rng ^= rng << 17;
        let mut c = fixtures::financial(4, rng);
        let p = Prepared::new(&c).unwrap();
        c.now_ns = rng % 12000000;
        c.current_epoch = (rng >> 30) % 3;
        let expected = screen(&c).reasons == 0;
        assert_eq!(p.packed(c.current_epoch, c.now_ns), expected);
        assert_eq!(p.branchy(c.current_epoch, c.now_ns), expected);
        assert_eq!(p.compact().ready(c.current_epoch, c.now_ns), expected);
        assert_eq!(
            p.compact().ready_inline(c.current_epoch, c.now_ns),
            expected
        );
        let now = c.now_ns;
        let with_copy = screen(&c);
        c.now_ns = 0;
        assert_eq!(screen_at(&c, now), with_copy);
    }
}
#[test]
fn immutable_preparation_cannot_authorize_changed_money() {
    let mut c = fixtures::financial(4, 1);
    let p = Prepared::new(&c).unwrap();
    c.steps[0].funding_before += 1;
    assert!(p.packed(1, c.now_ns)); // scope deliberately limited: final guard is indispensable.
    assert_ne!(screen(&c).reasons, 0);
    assert!(Prepared::new(&c).is_none());
}
#[test]
fn all_single_guard_mutations_block() {
    let u = fixtures::update(fixtures::financial(4, 1), 0);
    let anchor = u.integrity.anchor;
    assert_eq!(guard(&u, anchor, 200000).reasons, 0);
    let mutations: Vec<fn(&mut Update)> = vec![
        |u| u.integrity.key.market = [0; 32],
        |u| u.integrity.key.borrower = [0; 20],
        |u| u.integrity.anchor.hash[0] ^= 1,
        |u| u.financial.state_indices[1] += 1,
        |u| u.integrity.plan_hash = [0; 32],
        |u| u.integrity.code_hash = [1; 32],
        |u| u.integrity.oracle_at = 0,
        |u| u.integrity.oracle_at = 200001,
        |u| u.integrity.oracle_max_age = 1,
        |u| u.integrity.route_through = 199999,
        |u| u.integrity.route_through = 700000,
        |u| u.integrity.oracle_max_age = 599999,
        |u| u.integrity.nonces[1] = 100,
        |u| u.integrity.nonce_start = u64::MAX,
        |u| u.integrity.dependencies[0] = 1,
        |u| u.integrity.dependencies[2] = 8,
        |u| u.integrity.success_mask = 7,
        |u| u.integrity.builder_paid = 0,
        |u| u.integrity.builder_paid = u128::MAX,
        |u| u.integrity.non_recourse = None,
        |u| u.integrity.non_recourse = Some(false),
        |u| u.integrity.financing_confirmed = None,
        |u| u.integrity.financing_confirmed = Some(false),
        |u| u.integrity.slippage_bps = 101,
        |u| u.integrity.max_slippage_bps = 10001,
        |u| u.integrity.quoted_net_lower = None,
        |u| u.integrity.quoted_net_lower = Some(u128::MAX),
        |u| u.integrity.quoted_net_lower = Some(0),
        |u| u.position.debt = None,
        |u| u.position.max_borrow = None,
        |u| u.position.debt = Some(10000),
        |u| u.financial.proposer_paid = 0,
        |u| u.position.basis = Basis::Unknown,
        |u| u.financial.operator_initial = 1,
        |u| u.financial.steps[0].funding_before += 1,
        |u| u.financial.steps[3].value_to_sponsor = 0,
        |u| u.financial.sponsor_other_inflows = 0,
        |u| u.financial.steps[1].gas_used = u64::MAX,
        |u| u.financial.evidence_mask = 0,
    ];
    for (j, mutate) in mutations.iter().enumerate() {
        let mut m = u.clone();
        mutate(&mut m);
        let r = guard(&m, anchor, 200000);
        assert_ne!(r.reasons, 0, "mutation {j}");
        assert!(!r.commercial_admission);
        let reference = guard_copy(&m, anchor, 200000);
        assert_eq!(r.reasons, reference.reasons);
        assert_eq!(r.financial, reference.financial);
    }
}
#[test]
fn third_eye_unknown_and_predictions_are_separate() {
    let p = Position {
        basis: Basis::SyntheticFixture,
        debt: Some(9999),
        max_borrow: Some(10000),
        near_bps: 100,
    };
    assert_eq!(
        assess(p, None, 1),
        Assessment {
            basis: Basis::SyntheticFixture,
            observed: Observed::Near,
            prediction: Prediction::Unknown
        }
    );
    let s = Scenario {
        interest_low: 2,
        interest_high: 3,
        future_max_borrow_low: 10000,
        future_max_borrow_high: 10000,
        through_ns: 10,
    };
    let a = assess(p, Some(s), 1);
    assert_eq!(a.observed, Observed::Near);
    assert_eq!(a.prediction, Prediction::CrossesUnderAssumptions);
    assert_eq!(assess(p, Some(s), 11).prediction, Prediction::Unknown);
    assert_eq!(
        assess(Position { debt: None, ..p }, Some(s), 1).observed,
        Observed::Unknown
    );
    assert_eq!(
        assess(
            Position {
                debt: Some(10000),
                ..p
            },
            None,
            1
        )
        .observed,
        Observed::Near
    );
    assert_eq!(
        assess(
            Position {
                debt: Some(10001),
                ..p
            },
            None,
            1
        )
        .observed,
        Observed::Eligible
    );
    assert_eq!(
        assess(
            Position {
                debt: Some(0),
                max_borrow: Some(0),
                ..p
            },
            None,
            1
        )
        .observed,
        Observed::Healthy
    );
    assert_eq!(
        assess(
            Position {
                debt: Some(u128::MAX),
                max_borrow: Some(u128::MAX),
                ..p
            },
            None,
            1
        )
        .observed,
        Observed::Unknown
    );
    assert_eq!(
        assess(
            p,
            Some(Scenario {
                interest_low: 4,
                ..s
            }),
            1
        )
        .prediction,
        Prediction::Unknown
    );
    assert_eq!(
        assess(
            p,
            Some(Scenario {
                interest_high: u128::MAX,
                ..s
            }),
            1
        )
        .prediction,
        Prediction::Unknown
    );
}
#[test]
fn expected_value_unknown_overflow_and_loss_block() {
    assert_eq!(expected_net(100, None, Some(0)), None);
    assert_eq!(expected_net(100, Some(1000000), None), None);
    assert_eq!(expected_net(100, Some(1000001), Some(0)), None);
    assert_eq!(expected_net(u128::MAX, Some(2), Some(0)), None);
    assert_eq!(expected_net(100, Some(500000), Some(100)), None);
    assert_eq!(expected_net(100, Some(500000), Some(1)), Some(49));
}
#[test]
fn updates_reorgs_nonce_and_invalid_events_invalidate_tickets() {
    let u = fixtures::update(fixtures::financial(4, 1), 0);
    let a = u.integrity.anchor;
    let mut e = Engine::new(a, vec![u.integrity.key]).unwrap();
    e.on_event(0, u.clone(), 200000).unwrap();
    let t = e.candidate(200000).unwrap();
    assert_eq!(e.finalize(t, 200000).reasons, 0);
    assert!(!e.finalize(t, 200000).commercial_admission);
    let mut changed = u.clone();
    changed.integrity.nonces[1] = 100;
    e.on_event(0, changed, 200000).unwrap();
    assert!(e.candidate(200000).is_none());
    assert_ne!(e.finalize(t, 200000).reasons, 0);
    e.on_event(0, u.clone(), 200000).unwrap();
    let t = e.candidate(200000).unwrap();
    let mut bad = u.clone();
    bad.integrity.key.market = [9; 32];
    assert!(e.on_event(0, bad, 200000).is_err());
    assert!(e.candidate(200000).is_none());
    assert_ne!(e.finalize(t, 200000).reasons, 0);
    e.on_event(0, u.clone(), 200000).unwrap();
    let t = e.candidate(200000).unwrap();
    e.reset_anchor(Anchor { hash: [1; 32], ..a }).unwrap();
    assert!(e.candidate(200000).is_none());
    assert_ne!(e.finalize(t, 200000).reasons, 0);
    e.reset_anchor(a).unwrap();
    e.on_event(0, u, 200000).unwrap();
    assert_ne!(e.finalize(t, 200000).reasons, 0); // ABA same anchor cannot reuse generation.
    assert!(e.candidate(2000000).is_none());
}
#[test]
fn tournament_matches_independent_full_scan() {
    let updates: Vec<_> = (0..CAPACITY)
        .map(|k| fixtures::update(fixtures::financial(4, k as u64), k))
        .collect();
    let mut e = Engine::new(
        updates[0].integrity.anchor,
        updates.iter().map(|u| u.integrity.key).collect(),
    )
    .unwrap();
    let mut reference = Engine::new(
        updates[0].integrity.anchor,
        updates.iter().map(|u| u.integrity.key).collect(),
    )
    .unwrap();
    let mut rng = 666u64;
    let mut oracle = vec![0u128; CAPACITY];
    for _ in 0..4096 {
        rng ^= rng << 13;
        rng ^= rng >> 7;
        rng ^= rng << 17;
        let slot = (rng as usize) % CAPACITY;
        let mut u = updates[slot].clone();
        let value = u128::from(rng % 100000);
        u.financial.operator_weth_new = value;
        u.integrity.quoted_net_lower = Some(value);
        if rng.is_multiple_of(7) {
            u.integrity.financing_confirmed = None;
            oracle[slot] = 0;
        } else {
            oracle[slot] = value / 2;
        }
        let slow = reference
            .on_event_reference(slot, u.clone(), 200000)
            .unwrap();
        assert_eq!(e.on_event(slot, u, 200000).unwrap(), slow);
        let t = e.candidate(200000);
        let rt = reference.candidate(200000);
        assert_eq!(t.map(Ticket::slot), rt.map(Ticket::slot));
        if let (Some(a), Some(b)) = (t, rt) {
            assert_eq!(
                e.finalize(a, 200000).reasons,
                reference.finalize_reference(b, 200000).reasons
            );
            assert_eq!(
                e.finalize(a, 200000).financial,
                reference.finalize_reference(b, 200000).financial
            );
        }
        let expected = *oracle.iter().max().unwrap();
        if expected == 0 {
            assert!(t.is_none());
        } else {
            let check = e.finalize(t.unwrap(), 200000);
            assert_eq!(check.reasons, 0);
            // Winner's net can be reconstructed from a separate copy using current max.
            // Expose rank only through the research ticket accessor, not financial authority.
            assert_eq!(oracle[t.unwrap().slot()], expected);
        }
    }
}
