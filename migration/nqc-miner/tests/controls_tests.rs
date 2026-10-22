use nqc_miner::controls::*;
use proptest::prelude::*;
use std::collections::BTreeMap;

fn hash(byte: u8) -> EvidenceHash {
    EvidenceHash::new([byte; 32]).unwrap()
}
fn identity() -> MineIdentity {
    MineIdentity::new("miner_chain1_market_a", 1, hash(1), hash(2)).unwrap()
}
fn canonical() -> CanonicalView {
    CanonicalView::new(1, 100, BTreeMap::from([(100, hash(10))])).unwrap()
}
fn scope() -> EvidenceScope {
    EvidenceScope::new(
        identity(),
        CanonicalBlock::new(100, hash(10)),
        90,
        95,
        200_000,
    )
    .unwrap()
}
fn test_evidence(kind: AdapterTestKind, report: u8) -> AdapterTestEvidence {
    AdapterTestEvidence::new(
        kind,
        scope(),
        CheckStatus::Pass,
        hash(report),
        hash(report + 10),
        1_000,
    )
    .unwrap()
}
fn certificate() -> AdapterCertification {
    AdapterCertification::new([
        test_evidence(AdapterTestKind::Differential, 30),
        test_evidence(AdapterTestKind::Properties, 31),
        test_evidence(AdapterTestKind::Fuzzing, 32),
    ])
    .unwrap()
}
fn gates() -> Vec<GateEvidence> {
    vec![
        GateEvidence::new(
            scope(),
            hash(20),
            EvidenceBasis::Historical,
            GateReport::Toxicity {
                transfer: CheckStatus::Pass,
                oracle: CheckStatus::Pass,
            },
        )
        .unwrap(),
        GateEvidence::new(
            scope(),
            hash(21),
            EvidenceBasis::Historical,
            GateReport::Adapter {
                certification: Box::new(certificate()),
            },
        )
        .unwrap(),
        GateEvidence::new(
            scope(),
            hash(22),
            EvidenceBasis::Historical,
            GateReport::Valuation {
                expected_net_centavos: 10_000,
                priority_score_micros: 100,
                scenarios: 1_000,
            },
        )
        .unwrap(),
        GateEvidence::new(
            scope(),
            hash(23),
            EvidenceBasis::Historical,
            GateReport::WindTunnel {
                net_centavos: 500,
                episodes: 30,
            },
        )
        .unwrap(),
        GateEvidence::new(
            EvidenceScope::new(
                identity(),
                CanonicalBlock::new(100, hash(10)),
                86_504,
                86_505,
                200_000,
            )
            .unwrap(),
            hash(24),
            EvidenceBasis::RealtimeShadow,
            GateReport::Shadow {
                net_centavos: 200,
                starts_at: 104,
                ends_at: 86_504,
                observations: 20,
            },
        )
        .unwrap(),
    ]
}
fn lifecycle() -> MineLifecycle {
    MineLifecycle::new(identity(), AdmissionPolicy::default(), 100).unwrap()
}
fn proposed() -> MineLifecycle {
    let mut value = lifecycle();
    for (evidence, at) in gates().into_iter().zip([101, 102, 103, 104, 86_506]) {
        value.advance(evidence, at, &canonical()).unwrap();
    }
    value
}
fn receipt(index: u64) -> RealizedReceipt {
    RealizedReceipt::new(
        1,
        EvidenceHash::sha256(&index.to_be_bytes()),
        CanonicalBlock::new(100, hash(10)),
        hash(90),
    )
    .unwrap()
}
fn funded_plan() -> BudgetPolicy {
    BudgetPolicy::new(200_000, 50_000).unwrap()
}

#[test]
fn exact_gate_order_reaches_advisory_proposal_but_never_active() {
    let mut value = lifecycle();
    let expected = [
        MineState::Classified,
        MineState::Valued,
        MineState::WindTunnel,
        MineState::Shadow,
        MineState::Proposed,
    ];
    for ((evidence, at), expected) in gates()
        .into_iter()
        .zip([101, 102, 103, 104, 86_506])
        .zip(expected)
    {
        assert_eq!(value.advance(evidence, at, &canonical()).unwrap(), expected);
    }
    let artifact = serde_json::to_value(value.proposal(86_507, &canonical()).unwrap()).unwrap();
    assert_eq!(artifact["operational_bridge"], "disabled");
    assert_eq!(artifact["external_approval_required"], true);
    assert_eq!(
        artifact["evidence_authenticity"],
        "external_verification_required"
    );
    let reference = ExternalApprovalReference::new("approval://external/opaque-reference").unwrap();
    assert_eq!(
        value.request_activation(&reference),
        Err(ControlError::OperationalBridgeDisabled)
    );
    assert_eq!(value.state(), MineState::Proposed);
    assert_eq!(
        value.advance(gates()[0].clone(), 86_508, &canonical()),
        Err(ControlError::OperationalBridgeDisabled)
    );
}

#[test]
fn unknown_or_failed_toxicity_never_advances() {
    for status in [CheckStatus::Unknown, CheckStatus::Fail] {
        for (transfer, oracle) in [(status, CheckStatus::Pass), (CheckStatus::Pass, status)] {
            let mut value = lifecycle();
            let evidence = GateEvidence::new(
                scope(),
                hash(20),
                EvidenceBasis::Historical,
                GateReport::Toxicity { transfer, oracle },
            )
            .unwrap();
            assert!(matches!(
                value.advance(evidence, 101, &canonical()),
                Err(ControlError::GateRejected(_))
            ));
            assert_eq!(value.state(), MineState::Detected);
            assert_eq!(value.journal().len(), 1);
        }
    }
}

#[test]
fn synthetic_fixture_evidence_cannot_be_promoted_to_proposal() {
    let mut value = lifecycle();
    let evidence = GateEvidence::new(
        scope(),
        hash(20),
        EvidenceBasis::Synthetic,
        GateReport::Toxicity {
            transfer: CheckStatus::Pass,
            oracle: CheckStatus::Pass,
        },
    )
    .unwrap();
    assert!(matches!(
        value.advance(evidence, 101, &canonical()),
        Err(ControlError::GateRejected(_))
    ));
}

#[test]
fn adapter_requires_all_three_distinct_test_families_and_artifacts() {
    assert!(AdapterCertification::new([
        test_evidence(AdapterTestKind::Differential, 30),
        test_evidence(AdapterTestKind::Differential, 31),
        test_evidence(AdapterTestKind::Fuzzing, 32),
    ])
    .is_err());
    assert!(AdapterCertification::new([
        test_evidence(AdapterTestKind::Differential, 30),
        test_evidence(AdapterTestKind::Properties, 30),
        test_evidence(AdapterTestKind::Fuzzing, 32),
    ])
    .is_err());
    for status in [CheckStatus::Unknown, CheckStatus::Fail] {
        let failed = AdapterTestEvidence::new(
            AdapterTestKind::Fuzzing,
            scope(),
            status,
            hash(32),
            hash(42),
            100,
        )
        .unwrap();
        assert!(AdapterCertification::new([
            test_evidence(AdapterTestKind::Differential, 30),
            test_evidence(AdapterTestKind::Properties, 31),
            failed
        ])
        .is_err());
    }
    assert!(AdapterTestEvidence::new(
        AdapterTestKind::Differential,
        scope(),
        CheckStatus::Pass,
        hash(30),
        hash(40),
        0
    )
    .is_err());
}

#[test]
fn adapter_reports_from_another_contract_or_block_cannot_be_combined() {
    let different = EvidenceScope::new(
        identity(),
        CanonicalBlock::new(99, hash(11)),
        90,
        95,
        200_000,
    )
    .unwrap();
    let test = AdapterTestEvidence::new(
        AdapterTestKind::Fuzzing,
        different,
        CheckStatus::Pass,
        hash(32),
        hash(42),
        100,
    )
    .unwrap();
    assert_eq!(
        AdapterCertification::new([
            test_evidence(AdapterTestKind::Differential, 30),
            test_evidence(AdapterTestKind::Properties, 31),
            test
        ]),
        Err(ControlError::WrongScope)
    );
}

#[test]
fn mine_chain_source_and_adapter_must_match() {
    for wrong in [
        MineIdentity::new("other_mine", 1, hash(1), hash(2)).unwrap(),
        MineIdentity::new(identity().mine_id(), 2, hash(1), hash(2)).unwrap(),
        MineIdentity::new(identity().mine_id(), 1, hash(3), hash(2)).unwrap(),
        MineIdentity::new(identity().mine_id(), 1, hash(1), hash(3)).unwrap(),
    ] {
        let wrong_scope =
            EvidenceScope::new(wrong, CanonicalBlock::new(100, hash(10)), 90, 95, 200_000).unwrap();
        let evidence = GateEvidence::new(
            wrong_scope,
            hash(20),
            EvidenceBasis::Historical,
            GateReport::Toxicity {
                transfer: CheckStatus::Pass,
                oracle: CheckStatus::Pass,
            },
        )
        .unwrap();
        assert_eq!(
            lifecycle().advance(evidence, 101, &canonical()),
            Err(ControlError::WrongScope)
        );
    }
}

#[test]
fn stale_prior_evidence_invalidates_a_later_step() {
    let short_scope =
        EvidenceScope::new(identity(), CanonicalBlock::new(100, hash(10)), 90, 95, 102).unwrap();
    let evidence = GateEvidence::new(
        short_scope,
        hash(20),
        EvidenceBasis::Historical,
        GateReport::Toxicity {
            transfer: CheckStatus::Pass,
            oracle: CheckStatus::Pass,
        },
    )
    .unwrap();
    let mut value = lifecycle();
    value.advance(evidence, 101, &canonical()).unwrap();
    assert_eq!(
        value.advance(gates()[1].clone(), 102, &canonical()),
        Err(ControlError::ExpiredEvidence)
    );
    assert_eq!(value.state(), MineState::Classified);
    assert_eq!(value.journal().len(), 2);
}

#[test]
fn canonical_reorg_invalidates_old_gate_and_proposal() {
    let reorg = CanonicalView::new(1, 100, BTreeMap::from([(100, hash(11))])).unwrap();
    let mut value = lifecycle();
    value
        .advance(gates()[0].clone(), 101, &canonical())
        .unwrap();
    assert_eq!(
        value.advance(gates()[1].clone(), 102, &reorg),
        Err(ControlError::ReorganizedBlock)
    );
    assert_eq!(
        proposed().proposal(86_507, &reorg),
        Err(ControlError::ReorganizedBlock)
    );
}

#[test]
fn absent_or_unfinalized_block_is_not_assumed_canonical() {
    let absent = CanonicalView::new(1, 101, BTreeMap::from([(101, hash(11))])).unwrap();
    assert_eq!(
        scope().validate(&identity(), 100, &absent),
        Err(ControlError::MissingCanonicalBlock)
    );
    let behind = CanonicalView::new(1, 99, BTreeMap::from([(99, hash(11))])).unwrap();
    assert_eq!(
        scope().validate(&identity(), 100, &behind),
        Err(ControlError::UnfinalizedBlock)
    );
}

#[test]
fn nonpositive_or_undersampled_valuation_fails() {
    for (profit, score, scenarios) in [
        (0, 100, 1000),
        (-1, 100, 1000),
        (100, 0, 1000),
        (100, 100, 999),
    ] {
        let mut value = lifecycle();
        value
            .advance(gates()[0].clone(), 101, &canonical())
            .unwrap();
        value
            .advance(gates()[1].clone(), 102, &canonical())
            .unwrap();
        let evidence = GateEvidence::new(
            scope(),
            hash(22),
            EvidenceBasis::Historical,
            GateReport::Valuation {
                expected_net_centavos: profit,
                priority_score_micros: score,
                scenarios,
            },
        )
        .unwrap();
        assert!(matches!(
            value.advance(evidence, 103, &canonical()),
            Err(ControlError::GateRejected(_))
        ));
        assert_eq!(value.state(), MineState::Valued);
    }
}

#[test]
fn shadow_requires_realtime_observations_after_shadow_admission() {
    for (basis, start, end, observations) in [
        (EvidenceBasis::Historical, 104, 86_504, 20),
        (EvidenceBasis::RealtimeShadow, 104, 86_503, 20),
        (EvidenceBasis::RealtimeShadow, 104, 86_504, 9),
        (EvidenceBasis::RealtimeShadow, 100, 86_500, 20),
    ] {
        let mut value = lifecycle();
        for (gate, at) in gates().into_iter().take(4).zip([101, 102, 103, 104]) {
            value.advance(gate, at, &canonical()).unwrap();
        }
        let report = GateReport::Shadow {
            net_centavos: 100,
            starts_at: start,
            ends_at: end,
            observations,
        };
        let evidence = GateEvidence::new(
            EvidenceScope::new(
                identity(),
                CanonicalBlock::new(100, hash(10)),
                86_504,
                86_505,
                200_000,
            )
            .unwrap(),
            hash(24),
            basis,
            report,
        )
        .unwrap();
        assert!(matches!(
            value.advance(evidence, 86_506, &canonical()),
            Err(ControlError::GateRejected(_))
        ));
        assert_eq!(value.state(), MineState::Shadow);
    }
}

#[test]
fn retirement_and_reactivation_reset_all_gates() {
    let mut value = proposed();
    value.retire("margin lost", 86_507).unwrap();
    assert_eq!(value.state(), MineState::Retired);
    assert_eq!(
        value.advance(gates()[0].clone(), 86_508, &canonical()),
        Err(ControlError::WrongState)
    );
    value
        .reactivate(identity(), "new evidence required", 86_509)
        .unwrap();
    assert_eq!(value.state(), MineState::Detected);
    assert_eq!(
        value.advance(gates()[1].clone(), 86_510, &canonical()),
        Err(ControlError::WrongGate)
    );
    value
        .advance(gates()[0].clone(), 86_510, &canonical())
        .unwrap();
    assert_eq!(value.state(), MineState::Classified);
    assert!(value.proposal(86_511, &canonical()).is_err());
}

#[test]
fn retirement_reason_is_required_and_mine_cannot_change_on_restart() {
    let mut value = lifecycle();
    assert!(value.retire(" ", 101).is_err());
    value.retire("reorg", 101).unwrap();
    let other = MineIdentity::new("other", 1, hash(1), hash(2)).unwrap();
    assert_eq!(
        value.reactivate(other, "not same mine", 102),
        Err(ControlError::WrongScope)
    );
}

#[test]
fn journal_replays_deterministically_and_roundtrips() {
    let value = proposed();
    let serialized = serde_json::to_vec(value.journal()).unwrap();
    let entries: Vec<JournalEntry> = serde_json::from_slice(&serialized).unwrap();
    let replayed = MineLifecycle::replay(&entries, &canonical(), 86_507).unwrap();
    assert_eq!(replayed.state(), MineState::Proposed);
    assert_eq!(serde_json::to_vec(replayed.journal()).unwrap(), serialized);
    assert_eq!(value.journal(), proposed().journal());
    assert_eq!(value.journal()[5].sequence(), 5);
}

#[test]
fn retired_history_replays_after_reorg_and_expiry_without_current_old_blocks() {
    let mut value = lifecycle();
    value
        .advance(gates()[0].clone(), 101, &canonical())
        .unwrap();
    value
        .retire("finalized history changed; keep the audit trail", 102)
        .unwrap();
    let changed = CanonicalView::new(1, 101, BTreeMap::from([(101, hash(11))])).unwrap();
    let serialized = serde_json::to_vec(value.journal()).unwrap();
    let entries: Vec<JournalEntry> = serde_json::from_slice(&serialized).unwrap();

    // Historical evidence has expired and its block is absent from the current view.
    // Retirement must remain auditable, while carrying no accepted gate evidence.
    let replayed = MineLifecycle::replay(&entries, &changed, 200_001).unwrap();
    assert_eq!(replayed.state(), MineState::Retired);
    assert_eq!(serde_json::to_vec(replayed.journal()).unwrap(), serialized);
    assert!(replayed.proposal(200_001, &changed).is_err());
}

#[test]
fn reactivation_replays_new_gates_without_requiring_retired_fork_canonicality() {
    let mut value = lifecycle();
    value
        .advance(gates()[0].clone(), 101, &canonical())
        .unwrap();
    value
        .retire("reorg requires a fresh admission cycle", 102)
        .unwrap();
    let new_identity = MineIdentity::new("miner_chain1_market_a", 1, hash(3), hash(4)).unwrap();
    value
        .reactivate(new_identity.clone(), "retry pinned source and adapter", 103)
        .unwrap();
    let changed = CanonicalView::new(1, 100, BTreeMap::from([(100, hash(11))])).unwrap();
    let restarted: Vec<JournalEntry> =
        serde_json::from_slice(&serde_json::to_vec(value.journal()).unwrap()).unwrap();
    assert_eq!(
        MineLifecycle::replay(&restarted, &changed, 104)
            .unwrap()
            .state(),
        MineState::Detected
    );
    let new_gate = GateEvidence::new(
        EvidenceScope::new(
            new_identity.clone(),
            CanonicalBlock::new(100, hash(11)),
            103,
            104,
            200_000,
        )
        .unwrap(),
        hash(25),
        EvidenceBasis::Historical,
        GateReport::Toxicity {
            transfer: CheckStatus::Pass,
            oracle: CheckStatus::Pass,
        },
    )
    .unwrap();
    value.advance(new_gate, 105, &changed).unwrap();
    let serialized = serde_json::to_vec(value.journal()).unwrap();
    let entries: Vec<JournalEntry> = serde_json::from_slice(&serialized).unwrap();
    let replayed = MineLifecycle::replay(&entries, &changed, 106).unwrap();
    assert_eq!(replayed.state(), MineState::Classified);
    assert_eq!(replayed.identity(), &new_identity);
    assert_eq!(serde_json::to_vec(replayed.journal()).unwrap(), serialized);
    // The new cycle is still tied to its current block, and is not exempt from reorg checks.
    assert!(matches!(
        MineLifecycle::replay(&entries, &canonical(), 106),
        Err(ControlError::ReorganizedBlock)
    ));
}

#[test]
fn replay_rejects_current_reorg_even_when_historical_context_was_valid() {
    let changed = CanonicalView::new(1, 100, BTreeMap::from([(100, hash(11))])).unwrap();
    assert!(matches!(
        MineLifecycle::replay(proposed().journal(), &changed, 86_507),
        Err(ControlError::ReorganizedBlock)
    ));
}

#[test]
fn historical_context_is_required_validated_and_integrity_bound() {
    let mut value = lifecycle();
    value
        .advance(gates()[0].clone(), 101, &canonical())
        .unwrap();
    value.retire("close the admission cycle", 102).unwrap();
    let original = serde_json::to_value(value.journal()).unwrap();

    let mut missing = original.clone();
    missing[1]["action"]
        .as_object_mut()
        .unwrap()
        .remove("canonical_context");
    assert!(serde_json::from_value::<Vec<JournalEntry>>(missing).is_err());
    let mut malformed = original.clone();
    malformed[1]["action"]["canonical_context"]["chain_id"] = serde_json::json!(0);
    assert!(serde_json::from_value::<Vec<JournalEntry>>(malformed).is_err());
    let mut duplicate_block = original.clone();
    let blocks = duplicate_block[1]["action"]["canonical_context"]["blocks"]
        .as_array_mut()
        .unwrap();
    blocks.push(blocks[0].clone());
    assert!(serde_json::from_value::<Vec<JournalEntry>>(duplicate_block).is_err());

    let mut wrong_hash = original.clone();
    wrong_hash[1]["action"]["canonical_context"]["blocks"][0]["hash"] = serde_json::json!(hash(99));
    let entries: Vec<JournalEntry> = serde_json::from_value(wrong_hash).unwrap();
    assert!(matches!(
        MineLifecycle::replay(&entries, &canonical(), 103),
        Err(ControlError::ReorganizedBlock)
    ));

    // A semantically compatible change to the finalized head still changes the journal digest.
    let mut replaced_head = original;
    replaced_head[1]["action"]["canonical_context"]["finalized_head"] = serde_json::json!(101);
    replaced_head[1]["action"]["canonical_context"]["blocks"]
        .as_array_mut()
        .unwrap()
        .push(serde_json::json!({"number": 101, "hash": hash(11)}));
    let entries: Vec<JournalEntry> = serde_json::from_value(replaced_head).unwrap();
    assert!(matches!(
        MineLifecycle::replay(&entries, &canonical(), 103),
        Err(ControlError::ReplayMismatch)
    ));
}

#[test]
fn retired_history_still_requires_original_gate_shape_time_and_admission() {
    let mut value = lifecycle();
    value
        .advance(gates()[0].clone(), 101, &canonical())
        .unwrap();
    value.retire("close the admission cycle", 102).unwrap();
    let original = serde_json::to_value(value.journal()).unwrap();
    let mut future = original.clone();
    future[1]["action"]["evidence"]["scope"]["produced_at"] = serde_json::json!(200);
    let entries: Vec<JournalEntry> = serde_json::from_value(future).unwrap();
    assert!(matches!(
        MineLifecycle::replay(&entries, &canonical(), 103),
        Err(ControlError::FutureEvidence)
    ));

    let mut malformed = original.clone();
    malformed[1]["action"]["evidence"]["scope"]["expires_at"] = serde_json::json!(90);
    let entries: Vec<JournalEntry> = serde_json::from_value(malformed).unwrap();
    assert!(matches!(
        MineLifecycle::replay(&entries, &canonical(), 103),
        Err(ControlError::InvalidInput(_))
    ));

    let mut failed_gate = original;
    failed_gate[1]["action"]["evidence"]["report"]["transfer"] = serde_json::json!("fail");
    let entries: Vec<JournalEntry> = serde_json::from_value(failed_gate).unwrap();
    assert!(matches!(
        MineLifecycle::replay(&entries, &canonical(), 103),
        Err(ControlError::GateRejected(_))
    ));
}

#[test]
fn transition_context_retains_only_relevant_blocks_and_finalized_head() {
    let view = CanonicalView::new(
        1,
        101,
        BTreeMap::from([(50, hash(50)), (100, hash(10)), (101, hash(11))]),
    )
    .unwrap();
    let mut value = lifecycle();
    value.advance(gates()[0].clone(), 101, &view).unwrap();
    let serialized = serde_json::to_value(value.journal()).unwrap();
    let blocks = serialized[1]["action"]["canonical_context"]["blocks"]
        .as_array()
        .unwrap();
    assert_eq!(blocks.len(), 2);
    assert_eq!(blocks[0]["number"], 100);
    assert_eq!(blocks[1]["number"], 101);
    let replayed = MineLifecycle::replay(value.journal(), &view, 102).unwrap();
    assert_eq!(value.journal(), replayed.journal());
}

#[test]
fn modified_journal_cannot_inject_live_state_or_forge_chain_tip() {
    let value = proposed();
    for (index, field, replacement) in [
        (0, "to", serde_json::json!("active")),
        (5, "to", serde_json::json!("active")),
        (5, "entry_hash", serde_json::json!(hash(99))),
        (3, "sequence", serde_json::json!(99)),
    ] {
        let mut json = serde_json::to_value(value.journal()).unwrap();
        json[index][field] = replacement;
        let entries: Vec<JournalEntry> = serde_json::from_value(json).unwrap();
        assert!(MineLifecycle::replay(&entries, &canonical(), 86_507).is_err());
    }
}

#[test]
fn replay_rejects_stale_current_evidence_and_future_log_time() {
    assert!(matches!(
        MineLifecycle::replay(proposed().journal(), &canonical(), 200_000),
        Err(ControlError::ExpiredEvidence)
    ));
    assert!(matches!(
        MineLifecycle::replay(proposed().journal(), &canonical(), 86_000),
        Err(ControlError::ClockRegression)
    ));
}

#[test]
fn deserialization_does_not_bypass_scope_validation() {
    let mut malformed = serde_json::to_value(&gates()[0]).unwrap();
    malformed["scope"]["produced_at"] = serde_json::json!(0);
    malformed["scope"]["expires_at"] = serde_json::json!(0);
    let evidence: GateEvidence = serde_json::from_value(malformed).unwrap();
    assert!(matches!(
        lifecycle().advance(evidence, 101, &canonical()),
        Err(ControlError::InvalidInput(_))
    ));
}

#[test]
fn default_budget_is_zero_and_references_never_enable_money() {
    let default = BudgetPolicy::default();
    assert_eq!(default.total_gas_centavos(), 0);
    assert_eq!(default.top_up_centavos(), 0);
    let ledger = BudgetLedger::default();
    assert_eq!(ledger.halt_reason(), Some(BudgetHalt::NoBudget));
    assert!(!ledger.spending_enabled());
    assert!(ledger.assess_top_up(1).is_err());
    let reference = ExternalApprovalReference::new("approval://external/opaque-reference").unwrap();
    assert_eq!(
        ledger.request_spend(1, &reference),
        Err(ControlError::OperationalBridgeDisabled)
    );
    assert_eq!(
        BudgetLedger::new(funded_plan()).request_spend(1, &reference),
        Err(ControlError::OperationalBridgeDisabled)
    );
}

#[test]
fn hard_budget_caps_are_integer_centavos() {
    assert!(BudgetPolicy::new(200_001, 50_000).is_err());
    assert!(BudgetPolicy::new(200_000, 50_001).is_err());
    assert!(BudgetPolicy::new(40_000, 50_000).is_err());
    assert!(BudgetPolicy::new(0, 1).is_err());
    assert!(BudgetPolicy::new(1, 0).is_err());
    let mut ledger = BudgetLedger::new(funded_plan());
    assert!(ledger.assess_top_up(50_000).is_ok());
    assert_eq!(ledger.assess_top_up(50_001), Err(ControlError::BudgetLimit));
    for i in 0..4 {
        ledger
            .record_observed_top_up(50_000, &receipt(i), &canonical())
            .unwrap();
    }
    assert_eq!(ledger.assess_top_up(1), Err(ControlError::BudgetLimit));
}

#[test]
fn paper_profit_never_avoids_no_capture_stop() {
    let mut ledger = BudgetLedger::new(funded_plan());
    ledger
        .record_paper_result(PaperResultKind::Simulated, 1_000_000_000)
        .unwrap();
    ledger
        .record_paper_result(PaperResultKind::Shadow, 1_000_000_000)
        .unwrap();
    ledger
        .record_realized_gas(99_999, &receipt(1), &canonical())
        .unwrap();
    assert_eq!(ledger.halt_reason(), None);
    ledger
        .record_realized_gas(1, &receipt(2), &canonical())
        .unwrap();
    assert_eq!(ledger.halt_reason(), Some(BudgetHalt::NoRealizedCapture));
    assert_eq!(ledger.realized_capture_count(), 0);
    assert_eq!(ledger.realized_net_centavos(), 0);
    assert_eq!(ledger.assess_top_up(1), Err(ControlError::BudgetHalted));
    ledger
        .record_realized_capture(100, &receipt(3), &canonical())
        .unwrap();
    assert_eq!(ledger.halt_reason(), Some(BudgetHalt::NoRealizedCapture));
}

#[test]
fn a_capture_before_threshold_changes_accounting_but_never_total_cap() {
    let mut ledger = BudgetLedger::new(funded_plan());
    ledger
        .record_realized_capture(100, &receipt(1), &canonical())
        .unwrap();
    ledger
        .record_realized_gas(100_000, &receipt(2), &canonical())
        .unwrap();
    assert_eq!(ledger.halt_reason(), None);
    ledger
        .record_realized_gas(100_000, &receipt(3), &canonical())
        .unwrap();
    assert_eq!(ledger.halt_reason(), Some(BudgetHalt::BudgetExhausted));
    assert!(!ledger.spending_enabled());
}

#[test]
fn overspending_remains_visible_and_receipts_cannot_be_double_counted() {
    let mut ledger = BudgetLedger::new(funded_plan());
    ledger
        .record_realized_gas(200_001, &receipt(1), &canonical())
        .unwrap();
    assert_eq!(ledger.gas_consumed_centavos(), 200_001);
    assert_eq!(ledger.halt_reason(), Some(BudgetHalt::BudgetExhausted));
    assert_eq!(
        ledger.record_realized_gas(1, &receipt(1), &canonical()),
        Err(ControlError::DuplicateReceipt)
    );
    assert_eq!(ledger.gas_consumed_centavos(), 200_001);
    assert_eq!(ledger.accounting_records().len(), 1);
}

#[test]
fn oversized_observed_topup_is_retained_as_a_breach() {
    let mut ledger = BudgetLedger::new(funded_plan());
    ledger
        .record_observed_top_up(50_001, &receipt(1), &canonical())
        .unwrap();
    assert_eq!(ledger.halt_reason(), Some(BudgetHalt::TopUpLimitBreached));
    assert_eq!(ledger.accounting_records().len(), 1);
}

#[test]
fn noncanonical_accounting_is_rejected_and_later_reorg_latches_stop() {
    let mut ledger = BudgetLedger::new(funded_plan());
    let reorg = CanonicalView::new(1, 100, BTreeMap::from([(100, hash(11))])).unwrap();
    assert_eq!(
        ledger.record_realized_capture(100, &receipt(1), &reorg),
        Err(ControlError::ReorganizedBlock)
    );
    assert_eq!(ledger.realized_capture_count(), 0);
    ledger
        .record_realized_capture(100, &receipt(1), &canonical())
        .unwrap();
    assert_eq!(
        ledger.audit_canonical(&reorg),
        Err(ControlError::ReorganizedBlock)
    );
    assert_eq!(
        ledger.halt_reason(),
        Some(BudgetHalt::ReorganizedAccountingEvidence)
    );
}

proptest! {
    #[test]
    fn arbitrary_skipped_gate_never_changes_detected_state(index in 1_usize..5) {
        let mut value = lifecycle();
        let before = serde_json::to_vec(value.journal()).unwrap();
        prop_assert_eq!(value.advance(gates()[index].clone(), 86_506, &canonical()), Err(ControlError::WrongGate));
        prop_assert_eq!(value.state(), MineState::Detected);
        prop_assert_eq!(serde_json::to_vec(value.journal()).unwrap(), before);
    }
    #[test]
    fn expiry_and_future_boundaries_fail_closed(now in 0_u64..100) {
        let evidence = EvidenceScope::new(identity(), CanonicalBlock::new(100, hash(10)), 10, 20, 70).unwrap();
        let result = evidence.validate(&identity(), now, &canonical());
        if now < 20 { prop_assert_eq!(result, Err(ControlError::FutureEvidence)); }
        else if now >= 70 { prop_assert_eq!(result, Err(ControlError::ExpiredEvidence)); }
        else { prop_assert!(result.is_ok()); }
    }
    #[test]
    fn any_paper_profit_is_never_realized_or_spendable(paper in any::<i64>()) {
        let mut ledger = BudgetLedger::new(funded_plan());
        ledger.record_paper_result(PaperResultKind::Simulated, paper).unwrap();
        ledger.record_paper_result(PaperResultKind::Shadow, paper).unwrap();
        prop_assert_eq!(ledger.realized_capture_count(), 0);
        prop_assert_eq!(ledger.realized_net_centavos(), 0);
        prop_assert!(!ledger.spending_enabled());
        prop_assert_eq!(ledger.simulated_net_centavos(), i128::from(paper));
        prop_assert_eq!(ledger.shadow_net_centavos(), i128::from(paper));
    }
    #[test]
    fn gas_accounting_is_exact_and_stop_is_monotonic(amounts in prop::collection::vec(1_u64..10_000, 1..100)) {
        let mut ledger = BudgetLedger::new(funded_plan());
        let mut sum = 0;
        let mut stopped = false;
        for (i, amount) in amounts.iter().enumerate() {
            ledger.record_realized_gas(*amount, &receipt(i as u64), &canonical()).unwrap();
            sum += amount;
            prop_assert_eq!(ledger.gas_consumed_centavos(), sum);
            if sum >= NO_CAPTURE_STOP_CENTAVOS { stopped = true; }
            if stopped { prop_assert!(ledger.halt_reason().is_some()); }
            prop_assert!(!ledger.spending_enabled());
        }
    }
    #[test]
    fn evidence_hashes_roundtrip_without_truncation(bytes in any::<[u8; 32]>()) {
        prop_assume!(bytes != [0; 32]);
        let hash = EvidenceHash::new(bytes).unwrap();
        prop_assert_eq!(EvidenceHash::from_hex(&hash.to_hex()).unwrap(), hash);
        let json = serde_json::to_string(&hash).unwrap();
        prop_assert_eq!(serde_json::from_str::<EvidenceHash>(&json).unwrap(), hash);
    }
}
