use alloy_primitives::{keccak256, U256};
use nqc_miner::discovery::*;
use proptest::prelude::*;

fn h(b: u8) -> String {
    format!("0x{}", format!("{b:02x}").repeat(32))
}
fn a(b: u8) -> String {
    format!("0x{}", format!("{b:02x}").repeat(20))
}
fn word_address(b: u8) -> String {
    format!("{}{}", "00".repeat(12), format!("{b:02x}").repeat(20))
}
fn word(n: u128) -> String {
    format!("{n:064x}")
}
fn scope(family: ProtocolFamily) -> ContractScope {
    ContractScope {
        chain_id: 1,
        address: a(1),
        family,
        from_block: 10,
        to_block: 20,
    }
}
fn liquidation() -> RpcLog {
    RpcLog {
        chain_id: 1,
        address: a(1),
        block_number: 15,
        block_hash: h(2),
        transaction_hash: h(3),
        log_index: 0,
        topics: vec![
            format!(
                "{:#x}",
                keccak256(
                    "Liquidate(bytes32,address,address,uint256,uint256,uint256,uint256,uint256)"
                )
            ),
            h(4),
            format!("0x{}", word_address(5)),
            format!("0x{}", word_address(6)),
        ],
        data: format!(
            "0x{}{}{}{}{}",
            word(17),
            word(18),
            word(20),
            word(0),
            word(0)
        ),
        removed: false,
    }
}

#[test]
fn morpho_liquidation_abi_is_decoded_with_units_and_identity() {
    let result = decode_log(&scope(ProtocolFamily::MorphoBlue), &liquidation()).unwrap();
    let DecodedEvent::Liquidation(result) = result else {
        panic!("expected liquidation")
    };
    assert_eq!(result.repaid_assets, "17");
    assert_eq!(result.seized_assets, "20");
    assert_eq!(result.market_id, h(4));
    assert_eq!(result.liquidator, a(5));
    assert_eq!(result.borrower, a(6));
    assert_eq!(result.debt_token, None);
    assert_eq!(result.identity.event_id(), format!("1:{}:{}:0", h(2), h(3)));
}

#[test]
fn morpho_birth_checks_market_hash_and_never_certifies() {
    let data = format!(
        "0x{}{}{}{}{}",
        word_address(1),
        word_address(2),
        word_address(3),
        word_address(4),
        word(860_000_000_000_000_000)
    );
    let id = format!("{:#x}", keccak256(decode_hex(&data).unwrap()));
    let mut log = liquidation();
    log.topics = vec![
        format!(
            "{:#x}",
            keccak256("CreateMarket(bytes32,(address,address,address,address,uint256))")
        ),
        id.clone(),
    ];
    log.data = data;
    let DecodedEvent::Birth(birth) = decode_log(&scope(ProtocolFamily::MorphoBlue), &log).unwrap()
    else {
        panic!("expected birth")
    };
    assert_eq!(birth.market_id, id);
    assert_eq!(birth.oracle, Some(a(3)));
    assert!(!birth.protocol_certified);
    log.topics[1] = h(9);
    assert!(decode_log(&scope(ProtocolFamily::MorphoBlue), &log).is_err());
}

#[test]
fn aave_reserve_and_liquidation_decoders_are_not_interchangeable() {
    let mut log = liquidation();
    log.topics = vec![
        format!(
            "{:#x}",
            keccak256("ReserveInitialized(address,address,address,address,address)")
        ),
        format!("0x{}", word_address(2)),
        format!("0x{}", word_address(3)),
    ];
    log.data = format!(
        "0x{}{}{}",
        word_address(4),
        word_address(5),
        word_address(6)
    );
    let DecodedEvent::Birth(birth) =
        decode_log(&scope(ProtocolFamily::AaveV3Configurator), &log).unwrap()
    else {
        panic!("expected reserve")
    };
    assert_eq!(birth.loan_token, Some(a(2)));
    assert_eq!(birth.related_tokens, vec![a(3), a(4), a(5)]);
    assert!(decode_log(&scope(ProtocolFamily::AaveV3Pool), &log).is_err());
    log.topics = vec![
        format!(
            "{:#x}",
            keccak256("LiquidationCall(address,address,address,uint256,uint256,address,bool)")
        ),
        format!("0x{}", word_address(2)),
        format!("0x{}", word_address(3)),
        format!("0x{}", word_address(4)),
    ];
    log.data = format!("0x{}{}{}{}", word(50), word(60), word_address(5), word(1));
    let DecodedEvent::Liquidation(liq) =
        decode_log(&scope(ProtocolFamily::AaveV3Pool), &log).unwrap()
    else {
        panic!("expected liq")
    };
    assert_eq!(liq.receive_a_token, Some(true));
    assert_eq!(liq.market_id, format!("{}:{}:{}", a(1), a(2), a(3)));
    log.data = format!("0x{}{}{}{}", word(50), word(60), word_address(5), word(2));
    assert!(decode_log(&scope(ProtocolFamily::AaveV3Pool), &log).is_err());
}

#[test]
fn rejects_reorgs_chain_contract_and_scope_confusion() {
    let original = liquidation();
    for kind in 0..5 {
        let mut log = original.clone();
        match kind {
            0 => log.removed = true,
            1 => log.chain_id = 8453,
            2 => log.address = a(2),
            3 => log.block_number = 21,
            _ => log.block_hash = h(0),
        };
        assert!(decode_log(&scope(ProtocolFamily::MorphoBlue), &log).is_err());
    }
}

#[test]
fn rejects_noncanonical_lengths_addresses_and_hex() {
    let mut log = liquidation();
    log.data.push_str("00");
    assert!(decode_log(&scope(ProtocolFamily::MorphoBlue), &log).is_err());
    log = liquidation();
    log.topics[2] = h(0xff);
    assert!(decode_log(&scope(ProtocolFamily::MorphoBlue), &log).is_err());
    assert!(decode_hex("0x0").is_err());
    assert!(decode_hex("0xgg").is_err());
    assert!(decode_hex("00").is_err());
}

#[test]
fn proxy_identity_must_match_both_code_hashes() {
    let mut binding = CodeBinding {
        chain_id: 1,
        contract: a(1),
        block_hash: h(2),
        runtime_code_hash: h(3),
        expected_runtime_code_hash: h(3),
        proxy_implementation: Some(a(4)),
        implementation_code_hash: Some(h(5)),
        expected_implementation_code_hash: Some(h(5)),
    };
    binding.verify_supplied_hashes().unwrap();
    binding.implementation_code_hash = Some(h(6));
    assert!(binding.verify_supplied_hashes().is_err());
    binding.implementation_code_hash = None;
    assert!(binding.verify_supplied_hashes().is_err());
}

#[test]
fn minhash_is_stable_and_selector_extraction_skips_push_data() {
    let mut code = vec![0x7f];
    code.extend([0x63; 32]);
    code.extend([0x63, 0xde, 0xad, 0xbe, 0xef, 0x00]);
    let fingerprint = bytecode_fingerprint(&code, 3, 16).unwrap();
    assert_eq!(
        fingerprint.selectors.iter().cloned().collect::<Vec<_>>(),
        vec!["0xdeadbeef"]
    );
    let same = bytecode_fingerprint(&code, 3, 16).unwrap();
    assert_eq!(fingerprint, same);
    let similarity = compare_fingerprints(&fingerprint, &same).unwrap();
    assert_eq!(similarity.bytecode_jaccard_estimate, 1.0);
    assert_eq!(similarity.selector_jaccard, Some(1.0));
    assert!(!similarity.semantic_equivalence_certified);
    assert!(!fingerprint.selector_scan_truncated);
    assert!(bytecode_fingerprint(&[], 1, 16).is_err());
}

#[test]
fn incomplete_push_tail_is_preserved_without_certifying_runtime() {
    let code = [0x00, 0x61, 0x00]; // STOP followed by an incomplete PUSH2 tail.
    let fingerprint = bytecode_fingerprint(&code, 1, 16).unwrap();
    assert!(fingerprint.selector_scan_truncated);
    assert!(fingerprint.selectors.is_empty());
    assert_eq!(fingerprint.byte_length, code.len());
    assert_eq!(
        fingerprint.runtime_keccak256,
        format!("{:#x}", alloy_primitives::keccak256(code))
    );
    let other = bytecode_fingerprint(&[0x00, 0x61, 0xff], 1, 16).unwrap();
    assert_ne!(fingerprint.runtime_keccak256, other.runtime_keccak256);
    assert_ne!(fingerprint.minhash, other.minhash);
    let with_candidate =
        bytecode_fingerprint(&[0x63, 0xde, 0xad, 0xbe, 0xef, 0x63, 0x01], 1, 16).unwrap();
    assert!(with_candidate.selector_scan_truncated);
    assert_eq!(
        with_candidate.selectors.iter().cloned().collect::<Vec<_>>(),
        vec!["0xdeadbeef"]
    );
    let similarity = compare_fingerprints(&fingerprint, &fingerprint).unwrap();
    assert_eq!(similarity.bytecode_jaccard_estimate, 1.0);
    assert!(!similarity.semantic_equivalence_certified);
}

fn operation(id: u8, predecessor: Option<String>) -> TimelockOperation {
    TimelockOperation {
        chain_id: 1,
        contract: a(1),
        operation_id: h(id),
        queued_at: 10,
        earliest_execution_timestamp: 20,
        predecessor,
        payload_hash: h(9),
        status: TimelockStatus::Queued,
        actual_execution: None,
    }
}
#[test]
fn timelocks_respect_predecessors_cancellation_and_actual_execution() {
    let mut book = TimelockBook::default();
    book.queue(operation(1, None)).unwrap();
    book.queue(operation(2, Some(h(1)))).unwrap();
    assert!(book.eligible(19).is_empty());
    assert_eq!(book.eligible(20).len(), 1);
    assert!(book.mark_executed(1, &a(1), &h(2), 20, 100, &h(8)).is_err());
    book.mark_executed(1, &a(1), &h(1), 22, 101, &h(8)).unwrap();
    assert_eq!(book.eligible(22).len(), 1);
    book.cancel(1, &a(1), &h(2)).unwrap();
    assert!(book.eligible(500).is_empty());
    assert!(book
        .mark_executed(1, &a(1), &h(2), 500, 999, &h(8))
        .is_err());
    assert_eq!(
        book.operation(1, &a(1), &h(1)).unwrap().actual_execution,
        Some((22, 101, h(8)))
    );
}

#[test]
fn exact_morpho_rounding_and_overflow() {
    assert_eq!(
        morpho_taylor_compounded(U256::from(WAD), 1).unwrap(),
        U256::from(1_666_666_666_666_666_666u128)
    );
    assert_eq!(morpho_taylor_compounded(U256::MAX, 0).unwrap(), U256::ZERO);
    assert!(morpho_taylor_compounded(U256::MAX, 1).is_err());
    let snapshot = MorphoInterestSnapshot {
        chain_id: 1,
        market_id: h(1),
        block_hash: h(2),
        timestamp: 100,
        total_borrow_assets: 100,
        total_borrow_shares: 100_000_000,
        borrower_shares: 50_000_000,
        rate_wad_per_second: WAD.to_string(),
        maximum_healthy_debt_assets: 50,
    };
    assert_eq!(snapshot.project(100).unwrap().debt_assets, "50");
    assert!(
        !snapshot
            .project(100)
            .unwrap()
            .liquidatable_under_fixed_assumptions
    );
    assert_eq!(
        snapshot.first_crossing(200).unwrap().unwrap().timestamp,
        101
    );
    assert!(snapshot.project(99).is_err());
    let mut overflowing = snapshot.clone();
    overflowing.total_borrow_assets = u128::MAX;
    assert!(overflowing.project(101).is_err());
}

#[test]
fn graph_never_uses_future_or_low_confidence_edges_as_identity() {
    let mut graph = EvidenceGraph::default();
    let node = |chain, b| AddressNode {
        chain_id: chain,
        address: a(b),
    };
    graph
        .add(AssociationEdge {
            a: node(1, 1),
            b: node(8453, 2),
            reason: AssociationReason::CommonFunding,
            confidence_bps: 7000,
            evidence_hash: h(1),
            observed_at: 10,
        })
        .unwrap();
    graph
        .add(AssociationEdge {
            a: node(8453, 2),
            b: node(42161, 3),
            reason: AssociationReason::OperationPattern,
            confidence_bps: 9000,
            evidence_hash: h(2),
            observed_at: 20,
        })
        .unwrap();
    assert_eq!(graph.cluster(&node(1, 1), 6000, 15).unwrap().nodes.len(), 2);
    let cluster = graph.cluster(&node(1, 1), 6000, 25).unwrap();
    assert_eq!(cluster.nodes.len(), 3);
    assert!(!cluster.identity_proven);
    assert_eq!(graph.cluster(&node(1, 1), 8000, 25).unwrap().nodes.len(), 1);
}

#[test]
fn incentive_and_maturity_signals_are_time_bounded_and_not_liquidations() {
    let campaign = IncentiveCampaign {
        campaign_id: "campaign-1".into(),
        chain_id: 1,
        market_id: h(1),
        starts_at: 1,
        ends_at: 100,
        observed_at: 2,
        source_hash: h(2),
        cancelled: false,
    };
    let samples = vec![
        LeverageSample {
            timestamp: 80,
            supplied_value_microusd: 200,
            borrowed_value_microusd: 100,
        },
        LeverageSample {
            timestamp: 95,
            supplied_value_microusd: 200,
            borrowed_value_microusd: 199,
        },
    ];
    let signal = campaign.end_signal(90, 20, &samples).unwrap().unwrap();
    assert_eq!(signal.borrow_to_supply_bps, Some(5000));
    assert!(!signal.implies_liquidation);
    assert!(campaign.end_signal(101, 20, &samples).unwrap().is_none());
    let maturity = Maturity {
        chain_id: 1,
        market_id: h(1),
        maturity_timestamp: 100,
        source_hash: h(2),
        observed_at: 2,
    };
    assert_eq!(
        approaching_maturities(std::slice::from_ref(&maturity), 90, 20)
            .unwrap()
            .len(),
        1
    );
    assert!(approaching_maturities(&[maturity], u64::MAX, 20).is_err());
}

proptest! {
    #[test]
    fn arbitrary_bytes_never_panic_in_decoder(data in prop::collection::vec(any::<u8>(),0..512)){
        let mut log=liquidation();log.data=format!("0x{}",data.iter().map(|x|format!("{x:02x}")).collect::<String>());
        let _=decode_log(&scope(ProtocolFamily::MorphoBlue),&log);
    }
    #[test]
    fn taylor_projection_is_monotone(rate in 0u64..1_000_000_000_000,elapsed in 0u64..100_000){
        let a=morpho_taylor_compounded(U256::from(rate),elapsed).unwrap();
        let b=morpho_taylor_compounded(U256::from(rate),elapsed+1).unwrap();prop_assert!(b>=a);
    }
    #[test]
    fn fingerprints_of_valid_small_programs_are_deterministic(program in prop::collection::vec(0u8..0x60,8..64)){
        let a=bytecode_fingerprint(&program,3,8).unwrap();let b=bytecode_fingerprint(&program,3,8).unwrap();prop_assert_eq!(a,b);
    }
}

#[test]
fn snapshot_integer_serialization_preserves_full_u128() {
    let snapshot = MorphoInterestSnapshot {
        chain_id: 1,
        market_id: h(1),
        block_hash: h(2),
        timestamp: 1,
        total_borrow_assets: u128::MAX,
        total_borrow_shares: 0,
        borrower_shares: 0,
        rate_wad_per_second: "0".into(),
        maximum_healthy_debt_assets: u128::MAX,
    };
    let text = serde_json::to_string(&snapshot).unwrap();
    let decoded: MorphoInterestSnapshot = serde_json::from_str(&text).unwrap();
    assert_eq!(snapshot, decoded);
}
