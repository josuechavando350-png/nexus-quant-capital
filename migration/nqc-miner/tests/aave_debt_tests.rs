use alloy_primitives::{keccak256, U256};
use nqc_miner::{aave_debt::*, digest, discovery::decode_hex, evm::*};
use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;
use serde_json::Value;
use std::collections::BTreeMap;
const RAY: u128 = 1_000_000_000_000_000_000_000_000_000;
fn input() -> DebtInput {
    DebtInput {
        borrower_reserve_debt: "100".into(),
        actual_debt_to_liquidate: "40".into(),
        has_no_collateral_left: false,
        next_variable_borrow_index_ray: (3 * RAY / 2).to_string(),
        current_scaled_variable_debt: "1000".into(),
        reserve_deficit: "5".into(),
        virtual_underlying_balance: "200".into(),
        reserve_id: 1,
        user_configuration: "255".into(),
        reserve_factor: "1000".into(),
        token_burn: BurnOutcome::Return {
            no_more_debt: false,
            next_scaled_variable_debt: "974".into(),
        },
        rate_quote: RateOutcome::Return {
            liquidity_rate_ray: (RAY / 20).to_string(),
            variable_borrow_rate_ray: (RAY / 10).to_string(),
        },
    }
}
fn fixture() -> Value {
    serde_json::from_str(include_str!("../fixtures/aave_debt_harness.json")).unwrap()
}
fn address(byte: u8) -> String {
    format!("0x{:02x}", byte).to_owned() + &format!("{byte:02x}").repeat(19)
}
fn hash(byte: u8) -> String {
    format!("0x{}", format!("{byte:02x}").repeat(32))
}
fn account(byte: u8, code: &str) -> WitnessAccount {
    WitnessAccount {
        address: address(byte),
        exists: true,
        balance_wei: "1000000000000000000".into(),
        nonce: 0,
        runtime_code: code.into(),
        code_hash: format!("{:#x}", keccak256(decode_hex(code).unwrap())),
        storage: BTreeMap::new(),
    }
}
fn reference(value: &DebtInput, fixture: &Value, probe: bool) -> SandboxOutcome {
    let mut target = account(2, fixture["runtime_code"].as_str().unwrap());
    target.storage = fixture["explicit_zero_slots"]
        .as_array()
        .unwrap()
        .iter()
        .map(|slot| (slot.as_u64().unwrap().to_string(), "0".into()))
        .collect();
    // Explicit synthetic zeros for dynamic bytes payload roots; no fallback reads.
    for root in fixture["dynamic_bytes_slots"].as_array().unwrap() {
        let start = U256::from_be_bytes(
            keccak256(U256::from(root.as_u64().unwrap()).to_be_bytes::<32>()).0,
        );
        for offset in 0..fixture["dynamic_bytes_zero_words_per_root"]
            .as_u64()
            .unwrap()
        {
            target
                .storage
                .insert((start + U256::from(offset)).to_string(), "0".into());
        }
    }
    let snapshot = PinnedSnapshot {
        schema_version: 1,
        kind: SnapshotKind::SyntheticFixture,
        chain_id: 1,
        block_number: 100,
        block_hash: hash(1),
        state_root: hash(2),
        timestamp: 1000,
        fork: EvmFork::Cancun,
        block_gas_limit: 30_000_000,
        base_fee_wei: "1".into(),
        beneficiary: address(3),
        prevrandao: hash(4),
        excess_blob_gas: Some(0),
        accounts: vec![account(1, "0x"), target, account(3, "0x")],
        ancestor_block_hashes: BTreeMap::new(),
    };
    let (no_more, next_scaled, burn_fails, burn_failure) = match &value.token_burn {
        BurnOutcome::Return {
            no_more_debt,
            next_scaled_variable_debt,
        } => (
            *no_more_debt,
            next_scaled_variable_debt.parse::<U256>().unwrap(),
            false,
            vec![],
        ),
        BurnOutcome::Revert { data } => (false, U256::ZERO, true, decode_hex(data).unwrap()),
    };
    let (liquidity, variable, rate_fails, rate_failure) = match &value.rate_quote {
        RateOutcome::Return {
            liquidity_rate_ray,
            variable_borrow_rate_ray,
        } => (
            liquidity_rate_ray.parse::<U256>().unwrap(),
            variable_borrow_rate_ray.parse::<U256>().unwrap(),
            false,
            vec![],
        ),
        RateOutcome::Revert { data } => (U256::ZERO, U256::ZERO, true, decode_hex(data).unwrap()),
    };
    // Canonical ABI: two argument heads, then the 18-field dynamic tuple.
    let padded_burn = burn_failure.len().div_ceil(32) * 32;
    let words = [
        value.borrower_reserve_debt.parse::<U256>().unwrap(),
        value.actual_debt_to_liquidate.parse().unwrap(),
        U256::from(value.has_no_collateral_left),
        value.next_variable_borrow_index_ray.parse().unwrap(),
        value.current_scaled_variable_debt.parse().unwrap(),
        U256::from(no_more),
        next_scaled,
        value.reserve_deficit.parse().unwrap(),
        value.virtual_underlying_balance.parse().unwrap(),
        U256::from(value.reserve_id),
        value.user_configuration.parse().unwrap(),
        value.reserve_factor.parse().unwrap(),
        liquidity,
        variable,
        U256::from(burn_fails),
        U256::from(18 * 32),
        U256::from(rate_fails),
        U256::from(18 * 32 + 32 + padded_burn),
    ];
    let signature="calculate((uint256,uint256,bool,uint256,uint256,bool,uint256,uint128,uint128,uint16,uint256,uint256,uint256,uint256,bool,bytes,bool,bytes),bool)";
    assert_eq!(
        nqc_miner::historical::hex(&keccak256(signature)[..4]),
        fixture["selector"]
    );
    let mut data = keccak256(signature)[..4].to_vec();
    for word in [U256::from(64), U256::from(probe)]
        .iter()
        .chain(words.iter())
    {
        data.extend_from_slice(&word.to_be_bytes::<32>());
    }
    for bytes in [&burn_failure, &rate_failure] {
        data.extend_from_slice(&U256::from(bytes.len()).to_be_bytes::<32>());
        data.extend_from_slice(bytes);
        data.resize(data.len() + ((32 - bytes.len() % 32) % 32), 0);
    }
    let calldata = nqc_miner::historical::hex(&data);
    simulate(
        &snapshot,
        &SandboxCall {
            caller: address(1),
            to: address(2),
            calldata,
            value_wei: "0".into(),
            gas_limit: 10_000_000,
            gas_price_wei: "1".into(),
            nonce: 0,
        },
    )
    .unwrap()
}

fn encoded(words: &[U256]) -> String {
    "0x".to_owned()
        + &words
            .iter()
            .map(|v| format!("{v:064x}"))
            .collect::<String>()
}
fn expected(p: &DebtAmounts) -> String {
    encoded(&[
        U256::from(p.burn_called),
        p.scaled_debt_to_burn.parse().unwrap(),
        p.next_scaled_variable_debt.parse().unwrap(),
        p.outstanding_debt.parse().unwrap(),
        p.new_reserve_deficit.parse().unwrap(),
        p.user_configuration.parse().unwrap(),
        p.new_virtual_underlying_balance.parse().unwrap(),
        p.liquidity_rate_ray.parse().unwrap(),
        p.variable_borrow_rate_ray.parse().unwrap(),
        U256::from(p.no_more_debt),
    ])
}
fn compare(c: &DebtInput, f: &Value) -> (String, usize) {
    let predicted = nqc_miner::aave_debt::calculate(c).unwrap();
    let actual = reference(c, f, false);
    assert_eq!(actual.snapshot_kind, SnapshotKind::SyntheticFixture);
    assert!(!actual.canonical_state_authenticated);
    if let Some(p) = predicted.amounts {
        assert_eq!(actual.status, VmStatus::Success, "{c:?}");
        assert_eq!(actual.output, expected(&p), "{c:?}");
        let probe = reference(c, f, true);
        let r = &p.rate_inputs;
        assert_eq!(probe.status, VmStatus::Revert);
        assert_eq!(
            probe.output,
            encoded(&[
                r.unbacked.parse().unwrap(),
                r.liquidity_added.parse().unwrap(),
                U256::ZERO,
                r.total_variable_debt.parse().unwrap(),
                r.reserve_factor.parse().unwrap(),
                U256::from(0xD00Du64),
                U256::from(1),
                r.virtual_underlying_balance_before_update.parse().unwrap()
            ]),
            "rate inputs {c:?}"
        );
        assert!(probe.logs.is_empty(), "probe revert must roll back logs");
        // Only the original library emits: optional deficit, then reserve update.
        let deficit_event = c.has_no_collateral_left && p.outstanding_debt != "0";
        assert_eq!(actual.logs.len(), 1 + usize::from(deficit_event));
        if deficit_event {
            let log = &actual.logs[0];
            assert_eq!(log.address, address(2));
            assert_eq!(
                log.topics,
                vec![
                    format!(
                        "{:#x}",
                        keccak256("DeficitCreated(address,address,uint256)")
                    ),
                    format!("0x{:064x}", 0xCAFEu64),
                    format!("0x{:064x}", 0xD00Du64)
                ]
            );
            assert_eq!(log.data, encoded(&[p.outstanding_debt.parse().unwrap()]));
        }
        let log = actual.logs.last().unwrap();
        assert_eq!(log.address, address(2));
        assert_eq!(
            log.topics,
            vec![
                format!(
                    "{:#x}",
                    keccak256(
                        "ReserveDataUpdated(address,uint256,uint256,uint256,uint256,uint256)"
                    )
                ),
                format!("0x{:064x}", 0xD00Du64)
            ]
        );
        assert_eq!(
            log.data,
            encoded(&[
                p.liquidity_rate_ray.parse().unwrap(),
                U256::ZERO,
                p.variable_borrow_rate_ray.parse().unwrap(),
                U256::from(RAY),
                c.next_variable_borrow_index_ray.parse().unwrap()
            ])
        );
        ("success".into(), 2)
    } else {
        assert_eq!(actual.status, VmStatus::Revert, "{c:?}");
        let data = predicted.revert_data.unwrap();
        assert_eq!(actual.output, data, "{c:?}");
        assert!(actual.logs.is_empty());
        assert!(
            actual
                .account_deltas
                .iter()
                .all(|d| d.address != address(2) || d.storage.is_empty()),
            "revert must roll back contract storage"
        );
        (
            if data.len() > 10 {
                data[..10].into()
            } else {
                data
            },
            1,
        )
    }
}
#[test]
fn partial_burn_floors_and_strategy_sees_deficit_and_pre_repayment_liquidity() {
    let c = input();
    let p = nqc_miner::aave_debt::calculate(&c)
        .unwrap()
        .amounts
        .unwrap();
    assert_eq!(p.scaled_debt_to_burn, "26");
    assert_eq!(p.outstanding_debt, "60");
    assert_eq!(p.new_reserve_deficit, "5");
    assert_eq!(p.user_configuration, "255");
    assert_eq!(p.new_virtual_underlying_balance, "240");
    assert_eq!(
        p.rate_inputs.virtual_underlying_balance_before_update,
        "200"
    );
    assert_eq!(p.rate_inputs.total_variable_debt, "1461");
    compare(&c, &fixture());
}
#[test]
fn no_collateral_burns_all_debt_and_accrues_only_unpaid_debt() {
    let mut c = input();
    c.has_no_collateral_left = true;
    c.token_burn = BurnOutcome::Return {
        no_more_debt: true,
        next_scaled_variable_debt: "933".into(),
    };
    let p = nqc_miner::aave_debt::calculate(&c)
        .unwrap()
        .amounts
        .unwrap();
    assert_eq!(p.scaled_debt_to_burn, "66");
    assert_eq!(p.new_reserve_deficit, "65");
    assert_eq!(p.rate_inputs.unbacked, "65");
    assert_eq!(p.rate_inputs.total_variable_debt, "1400");
    assert_eq!(p.user_configuration, "251");
    assert_eq!(p.next_scaled_variable_debt, "933");
    compare(&c, &fixture());
    c.actual_debt_to_liquidate = "100".into();
    assert_eq!(
        nqc_miner::aave_debt::calculate(&c)
            .unwrap()
            .amounts
            .unwrap()
            .new_reserve_deficit,
        "5"
    );
    compare(&c, &fixture());
}
#[test]
fn zero_debt_skips_token_and_clears_legacy_flag_using_unchanged_cached_total() {
    let mut c = input();
    c.borrower_reserve_debt = "0".into();
    c.actual_debt_to_liquidate = "0".into();
    c.token_burn = BurnOutcome::Revert {
        data: "0xdeadbeef".into(),
    };
    let p = nqc_miner::aave_debt::calculate(&c)
        .unwrap()
        .amounts
        .unwrap();
    assert!(!p.burn_called && p.no_more_debt);
    assert_eq!(p.scaled_debt_to_burn, "0");
    assert_eq!(p.next_scaled_variable_debt, "1000");
    assert_eq!(p.user_configuration, "251");
    compare(&c, &fixture());
    c.reserve_id = 128;
    assert!(nqc_miner::aave_debt::calculate(&c)
        .unwrap()
        .amounts
        .is_none());
    compare(&c, &fixture());
    c = input();
    c.reserve_id = 65535;
    compare(&c, &fixture()); // Unused index is not validated if token says debt remains.
}
#[test]
fn external_reverts_and_casts_preserve_first_error_and_rollback_logs() {
    let mut c = input();
    c.actual_debt_to_liquidate = "101".into();
    c.token_burn = BurnOutcome::Revert {
        data: "0xdeadbeef".into(),
    };
    assert_eq!(
        nqc_miner::aave_debt::calculate(&c).unwrap().revert_data,
        Some("0xdeadbeef".into())
    );
    compare(&c, &fixture());
    c.next_variable_borrow_index_ray = "0".into();
    assert_eq!(
        nqc_miner::aave_debt::calculate(&c).unwrap().revert_data,
        Some("0x".into())
    );
    compare(&c, &fixture());
    for data in [
        "0x".to_owned(),
        "0x".to_owned() + &"a5".repeat(64),
        "0x".to_owned() + &"19".repeat(4096),
    ] {
        c = input();
        c.rate_quote = RateOutcome::Revert { data: data.clone() };
        assert_eq!(
            nqc_miner::aave_debt::calculate(&c).unwrap().revert_data,
            Some(data)
        );
        compare(&c, &fixture());
    }
    c = input();
    c.has_no_collateral_left = true;
    c.reserve_deficit = u128::MAX.to_string();
    assert_eq!(
        nqc_miner::aave_debt::calculate(&c).unwrap().revert_data,
        Some(format!("0x4e487b71{:064x}", 0x11))
    );
    compare(&c, &fixture());
    c = input();
    c.rate_quote = RateOutcome::Return {
        liquidity_rate_ray: (U256::from(u128::MAX) + U256::from(1)).to_string(),
        variable_borrow_rate_ray: "0".into(),
    };
    assert!(nqc_miner::aave_debt::calculate(&c)
        .unwrap()
        .revert_data
        .unwrap()
        .starts_with("0x6dfcc650"));
    compare(&c, &fixture());
}
#[test]
fn deficit_repayment_and_second_rate_casts_and_zero_debt_index_boundary() {
    let max = U256::from(u128::MAX);
    let mut c = input();
    c.has_no_collateral_left = true;
    c.borrower_reserve_debt = (max + U256::from(100)).to_string();
    let downcast = |v: U256| format!("0x6dfcc650{:064x}{v:064x}", 128);
    assert_eq!(
        nqc_miner::aave_debt::calculate(&c).unwrap().revert_data,
        Some(downcast(max + U256::from(60)))
    );
    compare(&c, &fixture());
    c = input();
    c.borrower_reserve_debt = (max + U256::from(1)).to_string();
    c.actual_debt_to_liquidate = c.borrower_reserve_debt.clone();
    assert_eq!(
        nqc_miner::aave_debt::calculate(&c).unwrap().revert_data,
        Some(downcast(max + U256::from(1)))
    );
    compare(&c, &fixture());
    c = input();
    c.rate_quote = RateOutcome::Return {
        liquidity_rate_ray: "1".into(),
        variable_borrow_rate_ray: (max + U256::from(1)).to_string(),
    };
    assert_eq!(
        nqc_miner::aave_debt::calculate(&c).unwrap().revert_data,
        Some(downcast(max + U256::from(1)))
    );
    compare(&c, &fixture());
    c = input();
    c.borrower_reserve_debt = "0".into();
    c.actual_debt_to_liquidate = "0".into();
    c.next_variable_borrow_index_ray = "0".into();
    c.token_burn = BurnOutcome::Revert {
        data: "0xdeadbeef".into(),
    };
    assert!(
        nqc_miner::aave_debt::calculate(&c)
            .unwrap()
            .calculation_passed
    );
    compare(&c, &fixture());
    c = input();
    c.next_variable_borrow_index_ray = U256::MAX.to_string();
    c.rate_quote = RateOutcome::Revert {
        data: "0x1234".into(),
    };
    assert_eq!(
        nqc_miner::aave_debt::calculate(&c).unwrap().revert_data,
        Some("0x".into())
    );
    compare(&c, &fixture());
}
#[test]
fn strict_outcomes_bounds_and_no_execution_authority() {
    let r = nqc_miner::aave_debt::calculate(&input()).unwrap();
    assert!(r.external_outcomes_supplied);
    assert!(
        !r.token_implementation_verified
            && !r.rate_strategy_verified
            && !r.input_state_authenticated
            && !r.executable_eligibility_verified
            && !r.activation_allowed
    );
    for bad in ["", "01", "1e27", "-1", " 1"] {
        let mut c = input();
        c.borrower_reserve_debt = bad.into();
        assert!(nqc_miner::aave_debt::calculate(&c).is_err());
    }
    let mut c = input();
    c.reserve_deficit = (U256::from(u128::MAX) + U256::from(1)).to_string();
    assert!(nqc_miner::aave_debt::calculate(&c).is_err());
    for data in [
        "0xA5".to_owned(),
        "0x1".into(),
        "0xzz".into(),
        "0x".to_owned() + &"00".repeat(4097),
    ] {
        c = input();
        c.token_burn = BurnOutcome::Revert { data };
        assert!(nqc_miner::aave_debt::calculate(&c).is_err());
    }
    let mut v = serde_json::to_value(input()).unwrap();
    v["token_burn"]["hidden"] = Value::Bool(true);
    assert!(serde_json::from_value::<DebtInput>(v).is_err());
}
#[test]
fn original_function_matches_boundaries_external_failures_and_seeded_states() {
    let f = fixture();
    assert_eq!(
        digest(&decode_hex(f["runtime_code"].as_str().unwrap()).unwrap()),
        f["runtime_sha256"]
    );
    assert_eq!(
        digest(include_bytes!("../fixtures/AaveDebtHarness.sol")),
        f["harness_source_sha256"]
    );
    let mut cases = vec![input()];
    for field in 0..10 {
        for value in [
            U256::ZERO,
            U256::from(1),
            U256::from(RAY),
            U256::from(u128::MAX),
            U256::from(u128::MAX) + U256::from(1),
            U256::MAX,
        ] {
            let mut c = input();
            match field {
                0 => c.borrower_reserve_debt = value.to_string(),
                1 => c.actual_debt_to_liquidate = value.to_string(),
                2 => c.next_variable_borrow_index_ray = value.to_string(),
                3 => c.current_scaled_variable_debt = value.to_string(),
                4 => {
                    if value > U256::from(u128::MAX) {
                        continue;
                    }
                    c.reserve_deficit = value.to_string();
                    c.has_no_collateral_left = true;
                }
                5 => {
                    if value > U256::from(u128::MAX) {
                        continue;
                    }
                    c.virtual_underlying_balance = value.to_string();
                }
                6 => c.user_configuration = value.to_string(),
                7 => c.reserve_factor = value.to_string(),
                8 => {
                    c.token_burn = BurnOutcome::Return {
                        no_more_debt: true,
                        next_scaled_variable_debt: value.to_string(),
                    }
                }
                _ => {
                    c.rate_quote = RateOutcome::Return {
                        liquidity_rate_ray: value.to_string(),
                        variable_borrow_rate_ray: value.to_string(),
                    }
                }
            };
            cases.push(c);
        }
    }
    for id in [0, 1, 127, 128, 65535] {
        for no_more in [false, true] {
            let mut c = input();
            c.reserve_id = id;
            c.token_burn = BurnOutcome::Return {
                no_more_debt: no_more,
                next_scaled_variable_debt: "1".into(),
            };
            cases.push(c);
        }
    }
    let mut rng = ChaCha8Rng::seed_from_u64(0x4e51435f44454254);
    for i in 0..512 {
        let mut c = input();
        let debt = rng.gen_range(0..10u128.pow(28));
        c.borrower_reserve_debt = debt.to_string();
        c.actual_debt_to_liquidate = rng.gen_range(0..=debt).to_string();
        c.has_no_collateral_left = i % 2 == 0;
        c.next_variable_borrow_index_ray = rng.gen_range(RAY..8 * RAY).to_string();
        c.current_scaled_variable_debt = rng.gen_range(0..10u128.pow(29)).to_string();
        c.reserve_deficit = rng.gen_range(0..10u128.pow(28)).to_string();
        c.virtual_underlying_balance = rng.gen_range(0..10u128.pow(28)).to_string();
        c.reserve_id = rng.gen_range(0..128);
        c.user_configuration = format!("{}", rng.gen::<u128>());
        c.reserve_factor = rng.gen_range(0..65536).to_string();
        c.token_burn = if i % 16 == 0 {
            BurnOutcome::Revert {
                data: "0x".to_owned() + &"13".repeat(i % 65),
            }
        } else {
            BurnOutcome::Return {
                no_more_debt: i % 3 == 0,
                next_scaled_variable_debt: rng.gen_range(0..10u128.pow(29)).to_string(),
            }
        };
        c.rate_quote = if i % 16 == 1 {
            RateOutcome::Revert {
                data: "0x76543210".into(),
            }
        } else {
            RateOutcome::Return {
                liquidity_rate_ray: rng.gen_range(0..RAY).to_string(),
                variable_borrow_rate_ray: rng.gen_range(0..4 * RAY).to_string(),
            }
        };
        cases.push(c);
    }
    let mut counts = BTreeMap::<String, usize>::new();
    let mut executions = 0;
    for c in &cases {
        let (category, n) = compare(c, &f);
        *counts.entry(category).or_default() += 1;
        executions += n;
    }
    assert!(counts.len() >= 6);
    println!("Debt differential: {} inputs, {executions} executions including rate probes; outcomes {counts:?}",cases.len());
}
