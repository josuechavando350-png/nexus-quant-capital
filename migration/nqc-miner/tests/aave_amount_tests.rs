use alloy_primitives::{keccak256, U256};
use nqc_miner::{aave_amounts::*, digest, discovery::decode_hex, evm::*};
use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;
use serde_json::Value;
use std::collections::BTreeMap;

fn input() -> AmountInput {
    AmountInput {
        collateral_balance: "20000000000".into(),
        reserve_debt: "10000000000".into(),
        total_debt_base: "1000000000000".into(),
        health_factor_wad: "970000000000000000".into(),
        collateral_price: "100000000".into(),
        debt_price: "100000000".into(),
        collateral_decimals: 6,
        debt_decimals: 6,
        liquidation_bonus_bps: 10500,
        liquidation_protocol_fee_bps: 1000,
        debt_to_cover: U256::MAX.to_string(),
    }
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
fn reference(value: &AmountInput, fixture: &Value) -> SandboxOutcome {
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
        accounts: vec![
            account(1, "0x"),
            account(2, fixture["runtime_code"].as_str().unwrap()),
            account(3, "0x"),
        ],
        ancestor_block_hashes: BTreeMap::new(),
    };
    let words = [
        value.collateral_balance.parse::<U256>().unwrap(),
        value.reserve_debt.parse().unwrap(),
        value.total_debt_base.parse().unwrap(),
        value.health_factor_wad.parse().unwrap(),
        value.collateral_price.parse().unwrap(),
        value.debt_price.parse().unwrap(),
        U256::from(value.collateral_decimals),
        U256::from(value.debt_decimals),
        U256::from(value.liquidation_bonus_bps),
        U256::from(value.liquidation_protocol_fee_bps),
        value.debt_to_cover.parse().unwrap(),
    ];
    let mut calldata = fixture["selector"].as_str().unwrap().to_owned();
    for word in words {
        calldata.push_str(&format!("{word:064x}"));
    }
    simulate(
        &snapshot,
        &SandboxCall {
            caller: address(1),
            to: address(2),
            calldata,
            value_wei: "0".into(),
            gas_limit: 2_000_000,
            gas_price_wei: "1".into(),
            nonce: 0,
        },
    )
    .unwrap()
}

#[test]
fn close_factor_uses_total_debt_and_strict_health_boundary() {
    let mut case = input();
    let amounts = calculate(&case).unwrap().amounts.unwrap();
    assert_eq!(amounts.max_liquidatable_debt, "5000000000");
    assert_eq!(amounts.collateral_to_liquidator, "5225000000");
    assert_eq!(amounts.protocol_fee_collateral, "25000000");
    case.total_debt_base = "1600000000000".into();
    assert_eq!(
        calculate(&case)
            .unwrap()
            .amounts
            .unwrap()
            .max_liquidatable_debt,
        "8000000000"
    );
    case.total_debt_base = "3000000000000".into();
    assert_eq!(
        calculate(&case)
            .unwrap()
            .amounts
            .unwrap()
            .max_liquidatable_debt,
        "10000000000"
    );
    case = input();
    case.health_factor_wad = "950000000000000000".into();
    assert_eq!(
        calculate(&case)
            .unwrap()
            .amounts
            .unwrap()
            .max_liquidatable_debt,
        "10000000000"
    );
    case.health_factor_wad = "950000000000000001".into();
    assert_eq!(
        calculate(&case)
            .unwrap()
            .amounts
            .unwrap()
            .max_liquidatable_debt,
        "5000000000"
    );
}

#[test]
fn dust_and_all_debt_exemption_are_distinct_from_initial_eligibility() {
    let mut case = input();
    case.reserve_debt = "1500000000".into();
    case.total_debt_base = "150000000000".into();
    case.debt_to_cover = "1000000000".into();
    let rejected = calculate(&case).unwrap();
    assert_eq!(
        rejected.revert_data.as_deref(),
        Some(nqc_miner::historical::hex(&keccak256("MustNotLeaveDust()")[..4]).as_str())
    );
    assert!(rejected.amounts.is_none());
    case.debt_to_cover = "1500000000".into();
    assert!(calculate(&case).unwrap().amount_calculation_passed);
    // This command does not turn even an unhealthy/healthy supplied input into eligibility.
    case.health_factor_wad = U256::MAX.to_string();
    let result = calculate(&case).unwrap();
    assert!(result.amount_calculation_passed);
    assert!(
        !result.initial_conditions_checked
            && !result.input_state_authenticated
            && !result.executable_eligibility_verified
            && !result.activation_allowed
    );
}

#[test]
fn exhausted_collateral_uses_ceil_repayment_and_fee_without_dust_rejection() {
    let mut case = input();
    case.collateral_balance = "1000".into();
    case.reserve_debt = "1000".into();
    case.total_debt_base = "100000000000".into();
    case.collateral_decimals = 0;
    case.debt_decimals = 0;
    let result = calculate(&case).unwrap().amounts.unwrap();
    assert_eq!(result.debt_to_liquidate, "953");
    assert_eq!(result.collateral_to_liquidator, "995");
    assert_eq!(result.protocol_fee_collateral, "5");
    let fixture: Value =
        serde_json::from_str(include_str!("../fixtures/aave_amount_harness.json")).unwrap();
    let actual = reference(&case, &fixture);
    assert_eq!(actual.status, VmStatus::Success);
    let expected = [1000u64, 953, 995, 5, 100_000_000_000, 100_000_000_000]
        .iter()
        .fold("0x".to_owned(), |mut data, value| {
            data.push_str(&format!("{value:064x}"));
            data
        });
    assert_eq!(actual.output, expected);
}

#[test]
fn zero_prices_overflow_and_bad_encodings_are_not_silent_zero_outputs() {
    let mut case = input();
    case.collateral_price = "0".into();
    assert_eq!(
        calculate(&case).unwrap().revert_data,
        Some(format!("0x4e487b71{:064x}", 0x12))
    );
    case = input();
    case.collateral_decimals = 78;
    assert_eq!(
        calculate(&case).unwrap().revert_data,
        Some(format!("0x4e487b71{:064x}", 0x11))
    );
    case = input();
    case.reserve_debt = U256::MAX.to_string();
    assert_eq!(calculate(&case).unwrap().revert_data.as_deref(), Some("0x"));
    for bad in [
        "",
        "01",
        "1e18",
        "-1",
        "+1",
        "0x1",
        " 1",
        "1.0",
        "115792089237316195423570985008687907853269984665640564039457584007913129639936",
    ] {
        case = input();
        case.debt_to_cover = bad.into();
        assert!(calculate(&case).is_err());
    }
    let mut json = serde_json::to_value(input()).unwrap();
    json["extra"] = Value::Bool(true);
    assert!(serde_json::from_value::<AmountInput>(json).is_err());
}

#[test]
fn extracted_solidity_kernel_matches_boundaries_and_seeded_inputs() {
    let fixture: Value =
        serde_json::from_str(include_str!("../fixtures/aave_amount_harness.json")).unwrap();
    assert_eq!(
        digest(&decode_hex(fixture["runtime_code"].as_str().unwrap()).unwrap()),
        fixture["runtime_sha256"]
    );
    assert_eq!(
        digest(include_bytes!("../fixtures/AaveAmountHarness.sol")),
        fixture["harness_source_sha256"]
    );
    let mut cases = vec![input()];
    // Exact crossings of the $2,000 close-factor threshold and $1,000 dust threshold.
    for debt in [
        999_999_999u64,
        1_000_000_000,
        1_000_000_001,
        1_999_999_999,
        2_000_000_000,
        2_000_000_001,
    ] {
        for health in [
            949_999_999_999_999_999u64,
            950_000_000_000_000_000,
            950_000_000_000_000_001,
        ] {
            for collateral in [
                1_999_999_999u64,
                2_000_000_000,
                2_000_000_001,
                20_000_000_000,
            ] {
                let mut c = input();
                c.reserve_debt = debt.to_string();
                c.total_debt_base = (debt * 100).to_string();
                c.health_factor_wad = health.to_string();
                c.collateral_balance = collateral.to_string();
                cases.push(c);
            }
        }
    }
    for field in 0..11 {
        for value in [
            U256::ZERO,
            U256::from(1),
            U256::from(9999),
            U256::from(10000),
            U256::from(65535),
            U256::MAX,
        ] {
            let mut c = input();
            match field {
                0 => c.collateral_balance = value.to_string(),
                1 => c.reserve_debt = value.to_string(),
                2 => c.total_debt_base = value.to_string(),
                3 => c.health_factor_wad = value.to_string(),
                4 => c.collateral_price = value.to_string(),
                5 => c.debt_price = value.to_string(),
                6 => c.debt_to_cover = value.to_string(),
                7 => c.collateral_decimals = value.as_limbs()[0] as u8,
                8 => c.debt_decimals = value.as_limbs()[0] as u8,
                9 => c.liquidation_bonus_bps = value.as_limbs()[0] as u16,
                _ => c.liquidation_protocol_fee_bps = value.as_limbs()[0] as u16,
            }
            cases.push(c);
        }
    }
    for decimals in [0, 6, 8, 18, 36, 76, 77, 78, 255] {
        let mut c = input();
        c.collateral_decimals = decimals;
        cases.push(c);
        let mut c = input();
        c.debt_decimals = decimals;
        cases.push(c);
    }
    let mut rng = ChaCha8Rng::seed_from_u64(0x4e51435f414d4f55);
    for _ in 0..2048 {
        let mut c = input();
        c.collateral_decimals = [0, 6, 8, 18][rng.gen_range(0..4)];
        c.debt_decimals = [0, 6, 8, 18][rng.gen_range(0..4)];
        let cu = U256::from(10).pow(U256::from(c.collateral_decimals));
        let du = U256::from(10).pow(U256::from(c.debt_decimals));
        c.collateral_balance = (U256::from(rng.gen_range(0..40000u64)) * cu
            + U256::from(rng.gen_range(0..10u64)))
        .to_string();
        let debt =
            U256::from(rng.gen_range(1..30000u64)) * du + U256::from(rng.gen_range(0..10u64));
        let price = U256::from(rng.gen_range(1..500_000_000_000u64));
        c.reserve_debt = debt.to_string();
        c.debt_price = price.to_string();
        c.total_debt_base =
            (debt * price / du + U256::from(rng.gen_range(0..3_000_000_000_000u64))).to_string();
        c.collateral_price = rng.gen_range(1..500_000_000_000u64).to_string();
        c.health_factor_wad = rng
            .gen_range(900_000_000_000_000_000u64..1_010_000_000_000_000_000)
            .to_string();
        c.liquidation_bonus_bps =
            [0, 9999, 10000, 10001, 10500, 11000, 15000, 65535][rng.gen_range(0..8)];
        c.liquidation_protocol_fee_bps = [0, 1, 1000, 3333, 10000, 65535][rng.gen_range(0..6)];
        c.debt_to_cover = if rng.gen_ratio(1, 3) {
            U256::MAX.to_string()
        } else {
            (debt * U256::from(rng.gen_range(0..11000u64)) / U256::from(10000)).to_string()
        };
        cases.push(c);
    }
    let mut outcomes = BTreeMap::<String, usize>::new();
    for (i, c) in cases.iter().enumerate() {
        let predicted = calculate(c).unwrap();
        let actual = reference(c, &fixture);
        assert_eq!(actual.snapshot_kind, SnapshotKind::SyntheticFixture);
        assert!(!actual.canonical_state_authenticated);
        if let Some(amounts) = predicted.amounts {
            assert_eq!(actual.status, VmStatus::Success, "case {i}: {c:?}");
            let mut expected = "0x".to_owned();
            for v in [
                &amounts.max_liquidatable_debt,
                &amounts.debt_to_liquidate,
                &amounts.collateral_to_liquidator,
                &amounts.protocol_fee_collateral,
                &amounts.reserve_debt_base,
                &amounts.reserve_collateral_base,
            ] {
                expected.push_str(&format!("{:064x}", v.parse::<U256>().unwrap()));
            }
            assert_eq!(actual.output, expected, "case {i}: {c:?}");
            *outcomes.entry("success".into()).or_default() += 1;
        } else {
            assert_eq!(actual.status, VmStatus::Revert, "case {i}: {c:?}");
            let expected = predicted.revert_data.unwrap();
            assert_eq!(actual.output, expected, "case {i}: {c:?}");
            *outcomes.entry(expected).or_default() += 1;
        }
    }
    assert_eq!(
        outcomes.len(),
        5,
        "success, dust, empty, arithmetic and divide-by-zero"
    );
    println!(
        "Differential amount cases: {}; outcomes: {outcomes:?}",
        cases.len()
    );
}
