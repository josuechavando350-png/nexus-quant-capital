use alloy_primitives::{keccak256, U256};
use nqc_miner::{aave_validation::*, digest, discovery::decode_hex, evm::*};
use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

fn address(byte: u8) -> String {
    format!("0x{}", format!("{byte:02x}").repeat(20))
}
fn hash(byte: u8) -> String {
    format!("0x{}", format!("{byte:02x}").repeat(32))
}
fn valid() -> ValidationInput {
    ValidationInput {
        borrower: address(4),
        liquidator: address(5),
        collateral_configuration: (1u64 << 56).to_string(),
        debt_configuration: (1u64 << 56).to_string(),
        collateral_grace_until: 999,
        debt_grace_until: 999,
        collateral_reserve_id: 0,
        user_configuration: "2".into(),
        health_factor_wad: "999999999999999999".into(),
        selected_debt: "1".into(),
        timestamp: 1000,
    }
}
fn failure_cases() -> Vec<ValidationInput> {
    let mut cases = vec![valid(); 8];
    cases[0].liquidator = cases[0].borrower.clone();
    cases[1].debt_configuration = "0".into();
    cases[2].collateral_configuration = ((1u64 << 56) | (1u64 << 60)).to_string();
    cases[3].collateral_grace_until = 1000;
    cases[4].health_factor_wad = "1000000000000000000".into();
    cases[5].collateral_reserve_id = 128;
    cases[6].user_configuration = "1".into();
    cases[7].selected_debt = "0".into();
    cases
}

#[test]
fn each_initial_condition_has_exact_error_and_no_execution_credit() {
    let errors = [
        "SelfLiquidation",
        "ReserveInactive",
        "ReservePaused",
        "LiquidationGraceSentinelCheckFailed",
        "HealthFactorNotBelowThreshold",
        "InvalidReserveIndex",
        "CollateralCannotBeLiquidated",
        "SpecifiedCurrencyNotBorrowedByUser",
    ];
    for (case, error) in failure_cases().iter().zip(errors) {
        let result = validate(case).unwrap();
        assert_eq!(result.first_error.as_deref(), Some(error));
        assert_eq!(
            result.revert_selector.as_deref(),
            Some(nqc_miner::historical::hex(&keccak256(format!("{error}()"))[..4]).as_str())
        );
        assert!(!result.initial_conditions_passed && !result.activation_allowed);
        assert!(!result.conditions.last().unwrap().passed);
    }
    let result = validate(&valid()).unwrap();
    assert!(result.initial_conditions_passed);
    assert!(
        !result.executable_eligibility_verified
            && !result.input_state_authenticated
            && !result.input_implementation_verified
    );
    assert_eq!(result.conditions.len(), 8);
}

#[test]
fn strict_health_grace_and_bitmap_boundaries() {
    let mut case = valid();
    case.debt_grace_until = case.timestamp;
    assert_eq!(
        validate(&case).unwrap().first_error.as_deref(),
        Some("LiquidationGraceSentinelCheckFailed")
    );
    case = valid();
    case.collateral_reserve_id = 127;
    case.user_configuration = (U256::from(1u64) << 255usize).to_string();
    assert!(validate(&case).unwrap().initial_conditions_passed);
    case.collateral_reserve_id = 128;
    case.health_factor_wad = "1000000000000000000".into();
    assert_eq!(
        validate(&case).unwrap().first_error.as_deref(),
        Some("HealthFactorNotBelowThreshold")
    );
    case = valid();
    case.timestamp = 0;
    case.collateral_grace_until = 0;
    case.debt_grace_until = 0;
    assert!(!validate(&case).unwrap().initial_conditions_passed);
}

#[test]
fn malformed_input_and_future_timestamp_are_rejected() {
    for number in [
        "",
        "01",
        "-1",
        "1.0",
        "1e18",
        "0x1",
        "+1",
        " 1",
        "115792089237316195423570985008687907853269984665640564039457584007913129639936",
    ] {
        let mut case = valid();
        case.selected_debt = number.into();
        assert!(validate(&case).is_err());
    }
    let mut case = valid();
    case.timestamp = 1 << 40;
    assert!(validate(&case).is_err());
    case = valid();
    case.liquidator = "0x123".into();
    assert!(validate(&case).is_err());
    let mut json = serde_json::to_value(valid()).unwrap();
    json["extra"] = Value::Bool(true);
    assert!(serde_json::from_value::<ValidationInput>(json).is_err());
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
fn reference(input: &ValidationInput, fixture: &Value) -> SandboxOutcome {
    let code = fixture["runtime_code"].as_str().unwrap();
    let mut target = account(2, code);
    // All harness slots are explicitly zero in this synthetic fixture. Missing
    // historical storage is never defaulted this way.
    target.storage = (0..21).map(|slot| (slot.to_string(), "0".into())).collect();
    let snapshot = PinnedSnapshot {
        schema_version: 1,
        kind: SnapshotKind::SyntheticFixture,
        chain_id: 1,
        block_number: 100,
        block_hash: hash(1),
        state_root: hash(2),
        timestamp: input.timestamp,
        fork: EvmFork::Cancun,
        block_gas_limit: 30_000_000,
        base_fee_wei: "1".into(),
        beneficiary: address(3),
        prevrandao: hash(4),
        excess_blob_gas: Some(0),
        accounts: vec![account(1, "0x"), target, account(3, "0x")],
        ancestor_block_hashes: BTreeMap::new(),
    };
    let mut calldata = fixture["selector"].as_str().unwrap().to_string();
    let words = [
        U256::from_str_radix(&input.borrower[2..], 16).unwrap(),
        U256::from_str_radix(&input.liquidator[2..], 16).unwrap(),
        input.collateral_configuration.parse().unwrap(),
        input.debt_configuration.parse().unwrap(),
        U256::from(input.collateral_grace_until),
        U256::from(input.debt_grace_until),
        U256::from(input.collateral_reserve_id),
        input.user_configuration.parse().unwrap(),
        input.health_factor_wad.parse().unwrap(),
        input.selected_debt.parse().unwrap(),
    ];
    for word in words {
        calldata.push_str(&format!("{word:064x}"));
    }
    let call = SandboxCall {
        caller: address(1),
        to: address(2),
        calldata,
        value_wei: "0".into(),
        gas_limit: 1_000_000,
        gas_price_wei: "1".into(),
        nonce: 0,
    };
    simulate(&snapshot, &call).unwrap()
}

#[test]
fn compiled_unchanged_solidity_function_matches_boundaries_and_seeded_cases() {
    let fixture: Value =
        serde_json::from_str(include_str!("../fixtures/aave_validation_harness.json")).unwrap();
    assert_eq!(
        digest(&decode_hex(fixture["runtime_code"].as_str().unwrap()).unwrap()),
        fixture["runtime_sha256"]
    );
    assert_eq!(
        digest(include_bytes!("../fixtures/AaveValidationHarness.sol")),
        fixture["harness_source_sha256"]
    );
    let mut cases = failure_cases();
    cases.push(valid());
    for id in [0, 1, 63, 64, 126, 127, 128, u16::MAX] {
        let mut case = valid();
        case.collateral_reserve_id = id;
        case.user_configuration = U256::MAX.to_string();
        cases.push(case);
    }
    for timestamp in [0, 1, 999, 1000, 1001, (1 << 40) - 1] {
        let mut case = valid();
        case.timestamp = timestamp;
        cases.push(case);
    }
    for health in [
        U256::ZERO,
        U256::from(999_999_999_999_999_999u64),
        U256::from(1_000_000_000_000_000_000u64),
        U256::MAX,
    ] {
        let mut case = valid();
        case.health_factor_wad = health.to_string();
        cases.push(case);
    }
    let mut rng = ChaCha8Rng::seed_from_u64(0x4e51435f41415645);
    for _ in 0..512 {
        let mut case = valid();
        if rng.gen_ratio(1, 10) {
            case.liquidator = case.borrower.clone();
        }
        for configuration in [
            &mut case.collateral_configuration,
            &mut case.debt_configuration,
        ] {
            let mut value = U256::from_be_bytes(rng.gen::<[u8; 32]>());
            value.set_bit(56, rng.gen_ratio(9, 10));
            value.set_bit(60, rng.gen_ratio(1, 10));
            *configuration = value.to_string();
        }
        case.collateral_grace_until = rng.gen_range(998..1002);
        case.debt_grace_until = rng.gen_range(998..1002);
        case.collateral_reserve_id = rng.gen_range(0..130);
        case.user_configuration = U256::from_be_bytes(rng.gen::<[u8; 32]>()).to_string();
        case.health_factor_wad =
            (rng.gen_range(999_999_999_999_999_998u64..1_000_000_000_000_000_002)).to_string();
        case.selected_debt = if rng.gen_ratio(1, 4) {
            "0".into()
        } else {
            U256::from_be_bytes(rng.gen::<[u8; 32]>()).to_string()
        };
        cases.push(case);
    }
    let mut outcomes = BTreeSet::new();
    for (i, case) in cases.iter().enumerate() {
        let predicted = validate(case).unwrap();
        let actual = reference(case, &fixture);
        assert_eq!(actual.snapshot_kind, SnapshotKind::SyntheticFixture);
        assert!(!actual.canonical_state_authenticated);
        if predicted.initial_conditions_passed {
            assert_eq!(actual.status, VmStatus::Success, "case {i}");
            assert_eq!(actual.output, "0x");
        } else {
            assert_eq!(actual.status, VmStatus::Revert, "case {i}");
            assert_eq!(
                Some(actual.output.as_str()),
                predicted.revert_selector.as_deref(),
                "case {i}"
            );
        }
        outcomes.insert(predicted.first_error);
    }
    assert_eq!(outcomes.len(), 9);
    eprintln!(
        "{} synthetic differential cases; all eight errors and success covered",
        cases.len()
    );
}

#[test]
fn captured_end_of_block_inputs_match_reference_without_claiming_transaction_state() {
    let fixture: Value =
        serde_json::from_str(include_str!("../fixtures/aave_validation_harness.json")).unwrap();
    for index in 0..3 {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join(format!(
            "evidence/aave-conditions-20261023/public/conditions-{index:03}.json"
        ));
        let report: Value = serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
        assert_eq!(report["transaction_prestate"], false);
        let input: ValidationInput = serde_json::from_value(report["inputs"].clone()).unwrap();
        let predicted = validate(&input).unwrap();
        let actual = reference(&input, &fixture);
        assert_eq!(actual.snapshot_kind, SnapshotKind::SyntheticFixture);
        assert!(!actual.canonical_state_authenticated);
        if predicted.initial_conditions_passed {
            assert_eq!(actual.status, VmStatus::Success);
            assert_eq!(actual.output, "0x");
        } else {
            assert_eq!(actual.status, VmStatus::Revert);
            assert_eq!(
                Some(actual.output.as_str()),
                predicted.revert_selector.as_deref()
            );
        }
    }
}
