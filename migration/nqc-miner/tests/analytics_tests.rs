use nqc_miner::analytics::*;
use proptest::prelude::*;

fn hash(n: u64) -> String {
    format!("0x{n:064x}")
}
fn address(n: u64) -> String {
    format!("0x{n:040x}")
}
fn event(number: u64) -> LiquidationObservation {
    LiquidationObservation {
        event_id: ChainEventId {
            chain_id: 1,
            block_hash: hash(number),
            transaction_hash: hash(number + 1_000),
            log_index: 0,
        },
        mine_id: "mine-a".into(),
        block_number: number,
        block_timestamp: number * 12,
        contract: address(10),
        topic0: hash(20),
        liquidator: address(30),
        first_eligible_block: Some(number.saturating_sub(10)),
        gross_bonus_microusd: Some(100_000_000),
        builder_tip_microusd: Some(1_000_000),
        canonical: true,
        finalized: true,
        evidence_class: EvidenceClass::Fixture,
    }
}
fn calibration() -> SaturationCalibration {
    SaturationCalibration {
        calibration_id: "synthetic-thresholds-v1".into(),
        evidence_class: EvidenceClass::Fixture,
        calibrated: true,
        minimum_events: 2,
        minimum_delay_observations: 2,
        minimum_tip_observations: 2,
        virgin_unique_max: 1,
        virgin_median_delay_min_blocks: 5,
        virgin_tip_share_max: 0.05,
        dead_unique_min: 3,
        dead_median_delay_max_blocks: 0,
        dead_tip_share_min: 0.9,
    }
}
fn saturation_input(events: Vec<LiquidationObservation>) -> SaturationInput {
    SaturationInput {
        mine_id: "mine-a".into(),
        chain_id: 1,
        first_block: 10,
        last_block: 100,
        scan_complete: true,
        evidence_class: EvidenceClass::Fixture,
        events,
    }
}
fn manifest() -> ScanManifest {
    ScanManifest {
        scan_id: "synthetic-scan-v1".into(),
        evidence_class: EvidenceClass::Fixture,
        ranges: vec![ScanRange {
            chain_id: 1,
            contract: address(10),
            topic0: hash(20),
            first_block: 10,
            last_block: 100,
            last_block_hash: hash(100),
            complete: true,
            finalized: true,
        }],
    }
}
fn watch() -> WatchInterval {
    WatchInterval {
        mine_id: "mine-a".into(),
        chain_id: 1,
        contract: address(10),
        topic0: hash(20),
        first_block: 10,
        last_block: None,
        registered_at_block: 9,
        evidence_class: EvidenceClass::Fixture,
    }
}

#[test]
fn no_observations_are_not_a_virgin_mine() {
    let report = saturation(&saturation_input(vec![]), &calibration()).unwrap();
    assert_eq!(report.state, SaturationState::InsufficientData);
    assert_eq!(report.mean_builder_tip_share, None);
    assert_eq!(report.median_delay_blocks, None);
}

#[test]
fn a_missing_tip_or_eligibility_measurement_is_not_zero() {
    let mut events = vec![event(20), event(30)];
    for e in &mut events {
        e.builder_tip_microusd = None;
        e.first_eligible_block = None;
    }
    let report = saturation(&saturation_input(events), &calibration()).unwrap();
    assert_eq!(report.state, SaturationState::InsufficientData);
    assert_eq!(report.mean_builder_tip_share, None);
    assert_eq!(report.median_delay_blocks, None);
}

#[test]
fn deduplication_cannot_inflate_sample_count() {
    let e = event(20);
    let report = saturation(&saturation_input(vec![e.clone(), e]), &calibration()).unwrap();
    assert_eq!(report.liquidations, 1);
    assert_eq!(report.deduplicated, 1);
    assert_eq!(report.state, SaturationState::InsufficientData);
}

#[test]
fn complete_low_competition_fixture_can_be_classified_only_as_fixture() {
    let report = saturation(
        &saturation_input(vec![event(20), event(30)]),
        &calibration(),
    )
    .unwrap();
    assert_eq!(report.state, SaturationState::Virgin);
    assert_eq!(report.evidence_class, EvidenceClass::Fixture);
    assert_eq!(report.median_delay_blocks, Some(10.0));
    assert_eq!(report.mean_builder_tip_share, Some(0.01));
}

#[test]
fn incomplete_or_uncalibrated_measurements_cannot_claim_market_state() {
    let mut input = saturation_input(vec![event(20), event(30)]);
    input.scan_complete = false;
    assert_eq!(
        saturation(&input, &calibration()).unwrap().state,
        SaturationState::IncompleteScan
    );
    input.scan_complete = true;
    let mut c = calibration();
    c.calibrated = false;
    assert_eq!(
        saturation(&input, &c).unwrap().state,
        SaturationState::Uncalibrated
    );
}

#[test]
fn dead_market_requires_all_measured_dimensions() {
    let mut events = vec![event(20), event(21), event(22)];
    for (i, e) in events.iter_mut().enumerate() {
        e.liquidator = address(100 + i as u64);
        e.first_eligible_block = Some(e.block_number);
        e.builder_tip_microusd = Some(95_000_000);
    }
    let report = saturation(&saturation_input(events), &calibration()).unwrap();
    assert_eq!(report.state, SaturationState::Dead);
    assert_eq!(report.unique_liquidators, 3);
    assert_eq!(report.median_delay_blocks, Some(0.0));
}

#[test]
fn orphaned_or_unfinalized_events_do_not_become_evidence() {
    let mut orphan = event(20);
    orphan.canonical = false;
    let mut pending = event(21);
    pending.finalized = false;
    let report = saturation(
        &saturation_input(vec![orphan, pending, event(22)]),
        &calibration(),
    )
    .unwrap();
    assert_eq!(report.liquidations, 1);
    assert_eq!(report.excluded_noncanonical, 1);
    assert_eq!(report.excluded_unfinalized, 1);
    assert_eq!(report.state, SaturationState::IncompleteScan);
}

#[test]
fn mixed_classes_and_mines_are_rejected() {
    let mut e = event(20);
    e.evidence_class = EvidenceClass::Realized;
    assert_eq!(
        saturation(&saturation_input(vec![e]), &calibration())
            .unwrap_err()
            .code,
        "mixed_evidence"
    );
    let mut e = event(20);
    e.mine_id = "mine-b".into();
    assert_eq!(
        saturation(&saturation_input(vec![e]), &calibration())
            .unwrap_err()
            .code,
        "outside_window"
    );
}

#[test]
fn duplicate_event_with_changed_profit_is_rejected() {
    let a = event(20);
    let mut b = a.clone();
    b.builder_tip_microusd = Some(0);
    assert_eq!(
        saturation(&saturation_input(vec![a, b]), &calibration())
            .unwrap_err()
            .code,
        "conflicting_event"
    );
}

#[test]
fn canonical_block_hash_and_transaction_location_conflicts_are_rejected() {
    let a = event(20);
    let mut b = event(20);
    b.event_id.block_hash = hash(5_000);
    b.event_id.transaction_hash = hash(5_001);
    assert_eq!(
        saturation(&saturation_input(vec![a.clone(), b]), &calibration())
            .unwrap_err()
            .code,
        "conflicting_block"
    );
    let mut moved = event(21);
    moved.event_id.transaction_hash = a.event_id.transaction_hash.clone();
    moved.event_id.log_index = 5;
    assert_eq!(
        saturation(&saturation_input(vec![a, moved]), &calibration())
            .unwrap_err()
            .code,
        "conflicting_transaction"
    );
}

#[test]
fn saturation_rejects_distinct_transactions_at_the_same_block_log_position() {
    let a = event(20);
    let mut b = a.clone();
    b.event_id.transaction_hash = hash(5_001);
    b.liquidator = address(99);
    for events in [vec![a.clone(), b.clone()], vec![b, a]] {
        assert_eq!(
            saturation(&saturation_input(events), &calibration())
                .unwrap_err()
                .code,
            "conflicting_log_index"
        );
    }
}

#[test]
fn unknown_or_zero_bonus_does_not_produce_a_zero_tip_fraction() {
    let mut e = event(20);
    e.gross_bonus_microusd = Some(0);
    let report = saturation(&saturation_input(vec![e]), &calibration()).unwrap();
    assert_eq!(report.mean_builder_tip_share, None);
    assert_eq!(report.tip_observations, 0);
}

#[test]
fn coverage_is_prospective_and_never_repaired_by_later_discovery() {
    let mut w = watch();
    w.first_block = 21;
    w.registered_at_block = 20;
    let report = coverage(&manifest(), &[event(20), event(30)], &[w]).unwrap();
    assert_eq!(report.fraction, Some(0.5));
    assert_eq!(report.watched_when_liquidated, 1);
    assert_eq!(
        report.blindspots[0].reason,
        BlindspotReason::DiscoveredLater
    );
}

#[test]
fn backdated_watch_registration_is_rejected() {
    let mut w = watch();
    w.registered_at_block = 50;
    assert_eq!(
        coverage(&manifest(), &[event(20)], &[w]).unwrap_err().code,
        "invalid_watch"
    );
}

#[test]
fn coverage_has_no_denominator_when_scan_empty_or_incomplete() {
    let empty = coverage(&manifest(), &[], &[]).unwrap();
    assert_eq!(empty.status, CoverageStatus::NoLiquidations);
    assert_eq!(empty.fraction, None);
    let mut m = manifest();
    m.ranges[0].complete = false;
    let incomplete = coverage(&m, &[event(20)], &[watch()]).unwrap();
    assert_eq!(incomplete.status, CoverageStatus::IncompleteScan);
    assert_eq!(incomplete.fraction, None);
}

#[test]
fn coverage_cannot_silently_exclude_unknown_scopes() {
    let mut e = event(20);
    e.contract = address(11);
    assert_eq!(
        coverage(&manifest(), &[e], &[]).unwrap_err().code,
        "outside_scan"
    );
    let mut e = event(20);
    e.topic0 = hash(21);
    assert_eq!(
        coverage(&manifest(), &[e], &[]).unwrap_err().code,
        "outside_scan"
    );
}

#[test]
fn overlapping_ranges_are_not_a_valid_coverage_denominator() {
    let mut m = manifest();
    m.ranges.push(m.ranges[0].clone());
    assert_eq!(coverage(&m, &[], &[]).unwrap_err().code, "overlapping_scan");
}

#[test]
fn scan_end_hash_is_bound_to_canonical_events() {
    let mut e = event(100);
    e.event_id.block_hash = hash(101);
    assert_eq!(
        coverage(&manifest(), &[e], &[]).unwrap_err().code,
        "scan_hash_mismatch"
    );
}

#[test]
fn retired_watch_does_not_cover_future_events() {
    let mut w = watch();
    w.last_block = Some(20);
    let result = coverage(&manifest(), &[event(20), event(21)], &[w]).unwrap();
    assert_eq!(result.fraction, Some(0.5));
    assert_eq!(
        result.blindspots[0].reason,
        BlindspotReason::OutsideWatchInterval
    );
}

#[test]
fn coverage_is_chain_specific_and_duplicate_safe() {
    let e = event(20);
    let result = coverage(&manifest(), &[e.clone(), e], &[watch(), watch()]).unwrap();
    assert_eq!(result.total_finalized_liquidations, 1);
    assert_eq!(result.watched_when_liquidated, 1);
    assert_eq!(result.fraction, Some(1.0));
    let mut wrong_chain = watch();
    wrong_chain.chain_id = 8453;
    let result = coverage(&manifest(), &[event(20)], &[wrong_chain]).unwrap();
    assert_eq!(result.fraction, Some(0.0));
    assert_eq!(
        result.blindspots[0].reason,
        BlindspotReason::UnregisteredScope
    );
}

#[test]
fn coverage_rejects_block_global_log_collisions_across_contracts() {
    let a = event(20);
    let mut b = a.clone();
    b.event_id.transaction_hash = hash(5_001);
    b.contract = address(11);
    let mut m = manifest();
    let mut second_contract = m.ranges[0].clone();
    second_contract.contract = b.contract.clone();
    m.ranges.push(second_contract);
    for events in [vec![a.clone(), b.clone()], vec![b, a]] {
        assert_eq!(
            coverage(&m, &events, &[]).unwrap_err().code,
            "conflicting_log_index"
        );
    }
}

#[test]
fn valid_same_block_events_are_ordered_by_log_position_not_transaction_hash() {
    let mut later = event(20);
    later.event_id.transaction_hash = hash(1_000);
    later.event_id.log_index = 9;
    let mut earlier = later.clone();
    earlier.event_id.transaction_hash = hash(9_000);
    earlier.event_id.log_index = 2;
    let events = vec![later.clone(), earlier.clone(), later];
    let report = coverage(&manifest(), &events, &[]).unwrap();
    assert_eq!(report.total_finalized_liquidations, 2);
    assert_eq!(report.blindspots[0].event_id, earlier.event_id);
    assert_eq!(report.blindspots[1].event_id.log_index, 9);
    let saturated = saturation(&saturation_input(events), &calibration()).unwrap();
    assert_eq!(saturated.liquidations, 2);
    assert_eq!(saturated.deduplicated, 1);
}

fn history() -> Vec<DailyEconomics> {
    (0..30)
        .map(|i| DailyEconomics {
            day_start_unix: i * 86_400,
            evidence_class: EvidenceClass::Fixture,
            gross_available_bonus_microusd: 100_000_000,
            successful_attempt_gas_microusd: 2_000_000,
            failed_attempt_gas_microusd: 1_000_000,
            other_execution_cost_microusd: 1_000_000,
        })
        .collect()
}
fn value_config() -> ValuationConfig {
    ValuationConfig {
        input_class: EvidenceClass::Fixture,
        horizon_days: 30,
        scenarios: 1_000,
        bootstrap_block_days: 5,
        minimum_history_days: 30,
        capture_share: 0.5,
        builder_share: 0.2,
        daily_operating_cost_microusd: 1_000_000,
        adapter_hours: 2.0,
        adapter_hourly_rate_microusd: 10_000_000,
        setup_compute_cost_microusd: 5_000_000,
        seed: 7,
    }
}

#[test]
fn valuation_matches_an_independent_constant_cashflow_calculation() {
    let result = value_month(&history(), &value_config()).unwrap();
    // $100 * 0.5 * 0.8 - $2 successful gas - $1 failed gas - $1 route cost - $1 operations = $35/day.
    assert_eq!(result.expected_net_microusd, 1_050_000_000.0);
    assert_eq!(result.p05_net_microusd, 1_050_000_000.0);
    assert_eq!(result.p95_net_microusd, 1_050_000_000.0);
    assert_eq!(result.priority_score, 42.0); // $1050 / (2h * $10/h + $5 compute).
    assert!(result.output_is_simulation);
    assert_eq!(result.input_class, EvidenceClass::Fixture);
}

#[test]
fn zero_captures_still_pay_all_attempt_costs() {
    let mut cfg = value_config();
    cfg.capture_share = 0.0;
    let result = value_month(&history(), &cfg).unwrap();
    assert_eq!(result.expected_net_microusd, -150_000_000.0);
    assert_eq!(result.probability_net_positive, 0.0);
}

#[test]
fn bootstrap_is_reproducible_and_returns_distribution_not_a_single_number() {
    let mut hist = history();
    for (i, day) in hist.iter_mut().enumerate() {
        day.gross_available_bonus_microusd = i as u64 * 10_000_000;
    }
    let cfg = value_config();
    let a = value_month(&hist, &cfg).unwrap();
    let b = value_month(&hist, &cfg).unwrap();
    assert_eq!(a, b);
    assert!(a.p05_net_microusd < a.p95_net_microusd);
    assert_eq!(a.scenarios_net_microusd.len(), 1_000);
    let mut other_seed = value_config();
    other_seed.seed += 1;
    assert_ne!(
        a.scenarios_net_microusd,
        value_month(&hist, &other_seed)
            .unwrap()
            .scenarios_net_microusd
    );
}

#[test]
fn valuation_rejects_unknown_days_nonfinite_rates_and_zero_effort() {
    let mut hist = history();
    hist.remove(10);
    let mut cfg = value_config();
    cfg.minimum_history_days = 20;
    assert_eq!(
        value_month(&hist, &cfg).unwrap_err().code,
        "noncontiguous_history"
    );
    cfg.capture_share = f64::NAN;
    assert_eq!(
        value_month(&history(), &cfg).unwrap_err().code,
        "invalid_assumption"
    );
    let mut cfg = value_config();
    cfg.adapter_hours = 0.0;
    cfg.setup_compute_cost_microusd = 0;
    assert_eq!(
        value_month(&history(), &cfg).unwrap_err().code,
        "zero_effort_cost"
    );
}

#[test]
fn valuation_rejects_a_nonfinite_priority_and_mixed_history() {
    let mut cfg = value_config();
    cfg.adapter_hours = f64::MIN_POSITIVE;
    cfg.setup_compute_cost_microusd = 0;
    cfg.adapter_hourly_rate_microusd = 1;
    assert_eq!(
        value_month(&history(), &cfg).unwrap_err().code,
        "nonfinite_score"
    );
    let mut hist = history();
    hist[0].evidence_class = EvidenceClass::Historical;
    assert_eq!(
        value_month(&hist, &value_config()).unwrap_err().code,
        "mixed_evidence"
    );
}

#[test]
fn an_explicit_zero_day_is_valid_but_not_implicitly_filled() {
    let mut hist = history();
    hist[2].gross_available_bonus_microusd = 0;
    assert!(value_month(&hist, &value_config()).is_ok());
    hist[2].day_start_unix = hist[1].day_start_unix;
    assert_eq!(
        value_month(&hist, &value_config()).unwrap_err().code,
        "noncontiguous_history"
    );
}

fn rival_config() -> RivalConfig {
    RivalConfig {
        chain_id: 1,
        mine_id: "mine-a".into(),
        evidence_class: EvidenceClass::Fixture,
        hazard: 0.02,
        prior_alpha: 1.0,
        prior_beta: 1.0,
        alarm_probability: 0.25,
        minimum_samples: 10,
        max_hypotheses: 64,
    }
}
fn competition(block: u64, elevated: bool) -> CompetitionSample {
    CompetitionSample {
        sample_id: format!("sample-{block}"),
        chain_id: 1,
        mine_id: "mine-a".into(),
        block_number: block,
        block_hash: hash(block),
        canonical: true,
        finalized: true,
        evidence_class: EvidenceClass::Fixture,
        elevated_competition: elevated,
        liquidators: vec![address(10)],
    }
}

#[test]
fn rival_update_is_idempotent_and_rejects_out_of_order_data() {
    let mut monitor = RivalMonitor::new(rival_config()).unwrap();
    let sample = competition(10, false);
    let first = monitor.update(&sample).unwrap();
    assert_eq!(monitor.update(&sample).unwrap(), first);
    assert_eq!(
        monitor.update(&competition(9, false)).unwrap_err().code,
        "nonmonotonic_sample"
    );
    let mut conflict = sample.clone();
    conflict.elevated_competition = true;
    assert_eq!(
        monitor.update(&conflict).unwrap_err().code,
        "nonmonotonic_sample"
    );
}

#[test]
fn rival_same_block_conflict_cannot_mutate_causal_history() {
    let mut monitor = RivalMonitor::new(rival_config()).unwrap();
    monitor.update(&competition(10, false)).unwrap();
    let mut control = monitor.clone();
    let mut same_block = competition(10, true);
    same_block.sample_id = "different-sample-at-same-block".into();
    same_block.liquidators.push(address(42));
    assert_eq!(
        monitor.update(&same_block).unwrap_err().code,
        "nonmonotonic_sample"
    );
    let mut next = competition(11, false);
    next.liquidators.push(address(42));
    let signal = monitor.update(&next).unwrap();
    assert_eq!(signal, control.update(&next).unwrap());
    assert_eq!(signal.sample_count, 2);
    assert_eq!(signal.new_liquidators, vec![address(42)]);
}

#[test]
fn rival_monitor_detects_unseen_liquidators_without_claiming_entity_identity() {
    let mut monitor = RivalMonitor::new(rival_config()).unwrap();
    assert!(monitor
        .update(&competition(10, false))
        .unwrap()
        .new_liquidators
        .is_empty());
    let mut newcomer = competition(11, false);
    newcomer.liquidators.push(address(11));
    let alert = monitor.update(&newcomer).unwrap();
    assert_eq!(alert.new_liquidators, vec![address(11)]);
    assert!(alert.request_revaluation);
    assert!(!alert.regime_alarm);
}

#[test]
fn bayesian_change_likelihood_increases_after_a_stable_low_competition_period() {
    let mut monitor = RivalMonitor::new(rival_config()).unwrap();
    let mut baseline = 0.0;
    for block in 1..=200 {
        baseline = monitor
            .update(&competition(block, false))
            .unwrap()
            .changepoint_probability;
    }
    let changed = monitor.update(&competition(201, true)).unwrap();
    assert!(changed.changepoint_probability > baseline * 5.0);
    assert!(changed.regime_alarm);
    assert!(changed.probability_discarded_by_pruning >= 0.0);
    assert!(changed.probability_discarded_by_pruning < 1.0);
}

#[test]
fn reorg_reset_does_not_retain_the_old_rival_posterior() {
    let mut monitor = RivalMonitor::new(rival_config()).unwrap();
    for block in 1..10 {
        monitor.update(&competition(block, false)).unwrap();
    }
    monitor.reset_after_reorg();
    let rebuilt = monitor.update(&competition(1, true)).unwrap();
    assert_eq!(rebuilt.sample_count, 1);
    assert_eq!(rebuilt.changepoint_probability, 0.0);
    assert!(!rebuilt.regime_alarm);
}

#[test]
fn rival_observations_require_canonical_finality_and_unique_ids() {
    let mut monitor = RivalMonitor::new(rival_config()).unwrap();
    let mut pending = competition(1, true);
    pending.finalized = false;
    assert_eq!(
        monitor.update(&pending).unwrap_err().code,
        "unconfirmed_sample"
    );
    monitor.update(&competition(1, false)).unwrap();
    monitor.update(&competition(2, false)).unwrap();
    let mut reused = competition(3, false);
    reused.sample_id = "sample-1".into();
    assert_eq!(
        monitor.update(&reused).unwrap_err().code,
        "reused_sample_identity"
    );
}

fn arm(id: &str, cost: u64) -> ResearchArm {
    ResearchArm {
        mine_id: id.into(),
        request_cost_units: cost,
        eligible: true,
        prior_alpha: 1.0,
        prior_beta: 1.0,
    }
}
fn outcome(number: u64, net: i64) -> RealizedOutcome {
    RealizedOutcome {
        outcome_id: format!("realized-{number}"),
        mine_id: "mine-a".into(),
        settlement_event: ChainEventId {
            chain_id: 1,
            block_hash: hash(number),
            transaction_hash: hash(number + 1_000),
            log_index: 0,
        },
        evidence_class: EvidenceClass::Realized,
        canonical: true,
        finalized: true,
        net_microusd: net,
        verification_reference: format!("receipt-digest-{number}"),
    }
}

#[test]
fn budget_defaults_to_zero_and_plans_never_authorize_spending() {
    let bandit = ThompsonBandit::new(vec![arm("mine-a", 10)]).unwrap();
    let plan = bandit.allocate(ResearchBudget::default(), 1).unwrap();
    assert_eq!(plan.total_units, 0);
    assert!(plan.allocations.is_empty());
    assert!(!plan.authorizes_spending);
}

#[test]
fn thompson_plan_is_seeded_integer_capped_and_does_not_split_requests() {
    let bandit = ThompsonBandit::new(vec![
        arm("mine-a", 10),
        arm("mine-b", 20),
        arm("mine-c", 40),
    ])
    .unwrap();
    let a = bandit
        .allocate(ResearchBudget { total_units: 35 }, 4)
        .unwrap();
    let b = bandit
        .allocate(ResearchBudget { total_units: 35 }, 4)
        .unwrap();
    assert_eq!(a, b);
    assert_eq!(a.total_units, 30);
    assert_eq!(a.unallocated_units, 5);
    assert_eq!(a.allocations.len(), 2);
}

#[test]
fn only_finalized_realized_net_can_change_posterior() {
    let mut bandit = ThompsonBandit::new(vec![arm("mine-a", 10)]).unwrap();
    for class in [
        EvidenceClass::Fixture,
        EvidenceClass::Historical,
        EvidenceClass::Shadow,
    ] {
        let mut fake = outcome(1, 100);
        fake.evidence_class = class;
        assert_eq!(
            bandit.record_realized(fake).unwrap_err().code,
            "not_realized"
        );
    }
    let mut fake = outcome(1, 100);
    fake.finalized = false;
    assert_eq!(
        bandit.record_realized(fake).unwrap_err().code,
        "not_realized"
    );
    assert_eq!(bandit.posteriors()[0].realized_observations, 0);
}

#[test]
fn realized_settlements_are_deduplicated_by_physical_event_and_id() {
    let mut bandit = ThompsonBandit::new(vec![arm("mine-a", 10)]).unwrap();
    assert_eq!(
        bandit.record_realized(outcome(1, 100)).unwrap(),
        RecordOutcome::Applied
    );
    assert_eq!(
        bandit.record_realized(outcome(1, 100)).unwrap(),
        RecordOutcome::AlreadyApplied
    );
    let mut duplicate_receipt = outcome(1, 100);
    duplicate_receipt.outcome_id = "different-id".into();
    assert_eq!(
        bandit.record_realized(duplicate_receipt).unwrap_err().code,
        "conflicting_outcome"
    );
    let mut duplicate_id = outcome(2, 100);
    duplicate_id.outcome_id = "realized-1".into();
    assert_eq!(
        bandit.record_realized(duplicate_id).unwrap_err().code,
        "reused_outcome_id"
    );
    assert_eq!(bandit.posteriors()[0].alpha, 2.0);
    assert_eq!(bandit.posteriors()[0].realized_observations, 1);
}

#[test]
fn reorg_retraction_restores_only_the_removed_outcome_contribution() {
    let mut bandit = ThompsonBandit::new(vec![arm("mine-a", 10)]).unwrap();
    bandit.record_realized(outcome(1, 100)).unwrap();
    bandit.record_realized(outcome(2, -10)).unwrap();
    assert_eq!(bandit.retract_block(1, &hash(1)).unwrap(), 1);
    let posterior = &bandit.posteriors()[0];
    assert_eq!(
        (
            posterior.alpha,
            posterior.beta,
            posterior.realized_observations
        ),
        (1.0, 2.0, 1)
    );
    assert_eq!(bandit.retract_block(1, &hash(1)).unwrap(), 0);
    let mut replacement = outcome(1, 100);
    replacement.settlement_event.block_hash = hash(3);
    bandit.record_realized(replacement).unwrap();
    assert_eq!(bandit.posteriors()[0].alpha, 2.0);
}

#[test]
fn ineligible_mines_cannot_receive_research_allocation() {
    let mut excluded = arm("mine-a", 10);
    excluded.eligible = false;
    let bandit = ThompsonBandit::new(vec![excluded, arm("mine-b", 20)]).unwrap();
    let plan = bandit
        .allocate(
            ResearchBudget {
                total_units: u64::MAX,
            },
            8,
        )
        .unwrap();
    assert_eq!(plan.allocations.len(), 1);
    assert_eq!(plan.allocations[0].mine_id, "mine-b");
    assert_eq!(plan.total_units, 20);
}

#[test]
fn invalid_beta_priors_are_rejected_before_sampling() {
    for prior in [f64::NAN, f64::INFINITY, -1.0, 0.0, 1e-200] {
        let mut a = arm("mine-a", 1);
        a.prior_alpha = prior;
        assert_eq!(
            ThompsonBandit::new(vec![a]).unwrap_err().code,
            "invalid_arm"
        );
    }
}

proptest! {
    #[test]
    fn any_research_budget_remains_conserved(
        costs in prop::collection::vec(1u64..1_000_000, 1..30), budget in any::<u64>(), seed in any::<u64>()
    ) {
        let arms = costs.iter().enumerate().map(|(i,c)| arm(&format!("mine-{i}"), *c)).collect();
        let bandit = ThompsonBandit::new(arms).unwrap();
        let plan = bandit.allocate(ResearchBudget { total_units: budget }, seed).unwrap();
        prop_assert!(plan.total_units <= budget);
        prop_assert_eq!(plan.total_units.checked_add(plan.unallocated_units), Some(budget));
        prop_assert_eq!(plan.allocations.iter().map(|a| a.units as u128).sum::<u128>(), plan.total_units as u128);
        prop_assert!(!plan.authorizes_spending);
    }

    #[test]
    fn duplicate_input_never_changes_saturation_measurements(count in 2usize..30, copies in 1usize..10) {
        let events: Vec<_> = (0..count).map(|i| event(20 + i as u64)).collect();
        let repeated: Vec<_> = (0..copies).flat_map(|_| events.clone()).collect();
        let a = saturation(&saturation_input(events), &calibration()).unwrap();
        let b = saturation(&saturation_input(repeated), &calibration()).unwrap();
        prop_assert_eq!(a.state,b.state);
        prop_assert_eq!(a.liquidations,b.liquidations);
        prop_assert_eq!(a.median_delay_blocks,b.median_delay_blocks);
        prop_assert_eq!(a.mean_builder_tip_share,b.mean_builder_tip_share);
    }

    #[test]
    fn extra_failed_gas_never_improves_the_same_seed_valuation(extra in 1u64..1_000_000, seed in any::<u64>()) {
        let mut cfg = value_config(); cfg.scenarios = 10; cfg.seed = seed;
        let hist = history(); let mut more_cost = hist.clone();
        for d in &mut more_cost { d.failed_attempt_gas_microusd += extra; }
        let a = value_month(&hist, &cfg).unwrap(); let b = value_month(&more_cost, &cfg).unwrap();
        for (x,y) in a.scenarios_net_microusd.iter().zip(&b.scenarios_net_microusd) {
            prop_assert!(*y <= *x);
            prop_assert!(((*x - *y) - extra as f64 * 30.0).abs() < 0.001);
        }
    }
}
