use nqc666::{engine as old, third_eye::Basis};
use nqc_666_event_pressure::{engine as new, fixtures};

fn engines<const B: bool, const S: bool>(rows: &[old::Update]) -> (old::Engine, new::Engine<B, S>) {
    let a = rows[0].integrity.anchor;
    let keys = rows.iter().map(|u| u.integrity.key).collect::<Vec<_>>();
    (
        old::Engine::new(a, keys.clone()).unwrap(),
        new::Engine::<B, S>::new(a, keys).unwrap(),
    )
}
fn checks(a: old::FinalCheck, b: old::FinalCheck) {
    assert_eq!(a.reasons, b.reasons);
    assert_eq!(a.financial, b.financial);
    assert!(!a.commercial_admission && !b.commercial_admission);
}
fn query<const B: bool, const S: bool>(
    a: &mut old::Engine,
    b: &mut new::Engine<B, S>,
    now: u64,
) -> Option<usize> {
    let x = a.candidate(now);
    let y = b.candidate(now);
    assert_eq!(x.map(|t| t.slot()), y.map(|t| t.slot()));
    if let (Some(x), Some(y)) = (x, y) {
        checks(a.finalize(x, now), b.finalize(y, now));
    }
    x.map(|t| t.slot())
}
fn fill<const B: bool, const S: bool>(
    a: &mut old::Engine,
    b: &mut new::Engine<B, S>,
    rows: &[old::Update],
) {
    for (slot, u) in rows.iter().enumerate() {
        assert_eq!(
            a.on_event(slot, u.clone(), fixtures::INSERT_AT),
            b.on_event(slot, u.clone(), fixtures::INSERT_AT)
        );
    }
}
#[test]
fn every_burst_size_ties_boundaries_and_backward_time() {
    for expired in 0..=256 {
        for seed in [1, 71, 666, 65_535] {
            let (rows, now) = fixtures::burst(expired, seed);
            let (mut a, mut b) = engines::<true, true>(&rows);
            fill(&mut a, &mut b, &rows);
            assert_eq!(
                query(&mut a, &mut b, now),
                (expired < 256).then_some((expired + seed as usize % 256) % 256)
            );
            // Retain precisely the same lower-priority ranks on a time reversal.
            for time in [now - 1, fixtures::INSERT_AT, 0, u64::MAX, now] {
                query(&mut a, &mut b, time);
            }
            let mut tied = rows.clone();
            for u in &mut tied {
                u.financial.operator_weth_new = 1_000_000;
                u.integrity.quoted_net_lower = Some(1_000_000);
            }
            fill(&mut a, &mut b, &tied);
            for time in [now - 1, now, fixtures::INSERT_AT] {
                query(&mut a, &mut b, time);
            }
        }
    }
}
#[test]
fn expired_losers_below_winner_survive_for_identical_rollback_semantics() {
    let (mut rows, now) = fixtures::burst(255, 0);
    // Winner at rank 96; ranks 97..254 are expired but MUST NOT be pruned yet.
    rows[96].integrity.route_through = 3_000_000;
    let (mut a, mut b) = engines::<true, true>(&rows);
    fill(&mut a, &mut b, &rows);
    assert_eq!(query(&mut a, &mut b, now), Some(96));
    let mut bad = rows[96].clone();
    bad.position.basis = Basis::Unknown;
    a.on_event(96, bad.clone(), now).unwrap();
    b.on_event(96, bad, now).unwrap();
    assert_eq!(query(&mut a, &mut b, fixtures::INSERT_AT), Some(97));
}
fn replay<const B: bool, const S: bool>() {
    let (rows, _) = fixtures::burst(128, 123);
    let anchor = rows[0].integrity.anchor;
    let (mut a, mut b) = engines::<B, S>(&rows);
    fill(&mut a, &mut b, &rows);
    let mut previous = None;
    let mut rng = 666_2026u64;
    for n in 0..100_000 {
        rng ^= rng << 13;
        rng ^= rng >> 7;
        rng ^= rng << 17;
        let slot = rng as usize % 256;
        let mut u = rows[slot].clone();
        let now = [200_000, 700_123, 700_122, 3_000_001, 0, u64::MAX][(rng >> 8) as usize % 6];
        u.financial.operator_weth_new = u128::from(1 + (rng >> 10) % 10_000_000);
        u.integrity.quoted_net_lower = Some(u.financial.operator_weth_new);
        match (rng >> 32) % 12 {
            0 => u.integrity.financing_confirmed = None,
            1 => u.position.basis = Basis::Unknown,
            2 => u.integrity.key.market[0] ^= 1,
            3 => u.integrity.anchor.hash[0] ^= 1,
            4 => u.financial.steps[0].funding_before += 1,
            5 => u.integrity.non_recourse = Some(false),
            6 => u.integrity.nonces[1] = 0,
            7 => u.integrity.oracle_max_age = 1,
            _ => (),
        }
        assert_eq!(
            a.on_event(slot, u.clone(), fixtures::INSERT_AT),
            b.on_event(slot, u, fixtures::INSERT_AT)
        );
        query(&mut a, &mut b, now);
        if let Some((x, y)) = previous {
            checks(a.finalize(x, now), b.finalize(y, now));
        }
        previous = a.candidate(now).zip(b.candidate(now));
        if n % 257 == 0 {
            let reorg = old::Anchor {
                hash: [0x56; 32],
                ..anchor
            };
            assert_eq!(a.reset_anchor(reorg), b.reset_anchor(reorg));
            if let Some((x, y)) = previous {
                checks(a.finalize(x, now), b.finalize(y, now));
            }
            assert_eq!(a.reset_anchor(anchor), b.reset_anchor(anchor));
            fill(&mut a, &mut b, &rows);
            if let Some((x, y)) = previous {
                checks(
                    a.finalize(x, fixtures::INSERT_AT),
                    b.finalize(y, fixtures::INSERT_AT),
                );
            }
        }
    }
}
#[test]
fn replay_400000_events_all_variants_tickets_reorgs_and_unknowns() {
    replay::<false, false>();
    replay::<true, false>();
    replay::<false, true>();
    replay::<true, true>();
}
#[test]
fn empty_partial_registries_and_invalid_resets() {
    let (rows, now) = fixtures::burst(255, 0);
    for len in [0, 1, 15, 16, 17, 63, 64, 128, 255, 256] {
        let keys: Vec<_> = rows[..len].iter().map(|u| u.integrity.key).collect();
        let anchor = rows[0].integrity.anchor;
        let mut a = old::Engine::new(anchor, keys.clone()).unwrap();
        let mut b = new::Engine::<true, true>::new(anchor, keys).unwrap();
        fill(&mut a, &mut b, &rows[..len]);
        assert_eq!(
            a.on_event(256, rows[0].clone(), now),
            b.on_event(256, rows[0].clone(), now)
        );
        assert_eq!(
            a.reset_anchor(old::Anchor { chain: 2, ..anchor }),
            b.reset_anchor(old::Anchor { chain: 2, ..anchor })
        );
        for t in [now, fixtures::INSERT_AT, u64::MAX] {
            query(&mut a, &mut b, t);
        }
    }
}
