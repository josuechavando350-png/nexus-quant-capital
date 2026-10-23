use alloy_primitives::{keccak256, U256};
use nqc_miner::{aave_reserve::*, digest, discovery::decode_hex, evm::*};
use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;
use serde_json::Value;
use std::collections::BTreeMap;
const RAY: u128 = 1_000_000_000_000_000_000_000_000_000;
fn input() -> ReserveInput {
    ReserveInput {
        liquidity_index_ray: RAY.to_string(),
        variable_borrow_index_ray: RAY.to_string(),
        liquidity_rate_ray: (RAY / 20).to_string(),
        variable_borrow_rate_ray: (RAY / 10).to_string(),
        accrued_to_treasury_scaled: "0".into(),
        last_update_timestamp: 1_000_000,
        reserve_factor_bps: 1000,
        total_scaled_variable_debt: "1000000000000".into(),
        user_scaled_collateral: "20000000000".into(),
        user_scaled_variable_debt: "10000000000".into(),
        timestamp: 1_000_000 + 31_536_000,
    }
}
fn address(b: u8) -> String {
    format!("0x{}", format!("{b:02x}").repeat(20))
}
fn hash(b: u8) -> String {
    format!("0x{}", format!("{b:02x}").repeat(32))
}
fn account(b: u8, code: &str) -> WitnessAccount {
    WitnessAccount {
        address: address(b),
        exists: true,
        balance_wei: "1000000000000000000".into(),
        nonce: 0,
        runtime_code: code.into(),
        code_hash: format!("{:#x}", keccak256(decode_hex(code).unwrap())),
        storage: BTreeMap::new(),
    }
}
fn fixture() -> Value {
    serde_json::from_str(include_str!("../fixtures/aave_reserve_harness.json")).unwrap()
}
fn reference(c: &ReserveInput, f: &Value, twice: bool) -> SandboxOutcome {
    let mut target = account(2, f["runtime_code"].as_str().unwrap());
    target.storage = f["explicit_zero_slots"]
        .as_array()
        .unwrap()
        .iter()
        .map(|s| (s.as_u64().unwrap().to_string(), "0".into()))
        .collect();
    let snapshot = PinnedSnapshot {
        schema_version: 1,
        kind: SnapshotKind::SyntheticFixture,
        chain_id: 1,
        block_number: 100,
        block_hash: hash(1),
        state_root: hash(2),
        timestamp: c.timestamp,
        fork: EvmFork::Cancun,
        block_gas_limit: 30_000_000,
        base_fee_wei: "1".into(),
        beneficiary: address(3),
        prevrandao: hash(4),
        excess_blob_gas: Some(0),
        accounts: vec![account(1, "0x"), target, account(3, "0x")],
        ancestor_block_hashes: BTreeMap::new(),
    };
    let words = [
        c.liquidity_index_ray.parse::<U256>().unwrap(),
        c.variable_borrow_index_ray.parse().unwrap(),
        c.liquidity_rate_ray.parse().unwrap(),
        c.variable_borrow_rate_ray.parse().unwrap(),
        c.accrued_to_treasury_scaled.parse().unwrap(),
        U256::from(c.last_update_timestamp),
        U256::from(c.reserve_factor_bps),
        c.total_scaled_variable_debt.parse().unwrap(),
        c.user_scaled_collateral.parse().unwrap(),
        c.user_scaled_variable_debt.parse().unwrap(),
        U256::from(twice),
    ];
    let mut calldata = f["selector"].as_str().unwrap().to_owned();
    for w in words {
        calldata.push_str(&format!("{w:064x}"));
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
fn expected_output(p: &ProjectedReserve) -> String {
    let timestamp = p.last_update_timestamp.to_string();
    let mut out = "0x".to_owned();
    for v in [
        &p.liquidity_index_ray,
        &p.variable_borrow_index_ray,
        &p.accrued_to_treasury_scaled,
        &timestamp,
        &p.user_collateral_balance,
        &p.user_variable_debt_balance,
        &p.liquidity_index_ray,
        &p.variable_borrow_index_ray,
        &timestamp,
    ] {
        out.push_str(&format!("{:064x}", v.parse::<U256>().unwrap()));
    }
    out
}

#[test]
fn one_year_interest_and_treasury_are_computed_and_no_authority_is_granted() {
    let r = project(&input()).unwrap();
    let p = r.projected.unwrap();
    assert_eq!(p.liquidity_index_ray, (RAY + RAY / 20).to_string());
    assert_eq!(p.user_collateral_balance, "21000000000");
    let debt = p.user_variable_debt_balance.parse::<u128>().unwrap();
    assert!(debt > 11_050_000_000 && debt < 11_052_000_000);
    assert!(p.accrued_to_treasury_scaled.parse::<u128>().unwrap() > 0);
    assert!(
        !r.input_state_authenticated
            && !r.token_implementation_verified
            && !r.activation_allowed
            && !r.executable_eligibility_verified
    );
    let f = fixture();
    let actual = reference(&input(), &f, false);
    assert_eq!(actual.status, VmStatus::Success);
    assert_eq!(actual.output, expected_output(&p));
}
#[test]
fn zero_debt_and_zero_liquidity_rate_skip_their_index_updates() {
    let mut c = input();
    c.total_scaled_variable_debt = "0".into();
    c.liquidity_rate_ray = "0".into();
    let p = project(&c).unwrap().projected.unwrap();
    assert_eq!(p.liquidity_index_ray, c.liquidity_index_ray);
    assert_eq!(p.variable_borrow_index_ray, c.variable_borrow_index_ray);
    assert_eq!(p.last_update_timestamp, c.timestamp);
    // A future timestamp is not unconditionally read by the original branches.
    c.timestamp = c.last_update_timestamp - 1;
    assert!(project(&c).unwrap().projection_passed);
    c.total_scaled_variable_debt = "1".into();
    assert_eq!(
        project(&c).unwrap().revert_data,
        Some(format!("0x4e487b71{:064x}", 0x11))
    );
}
#[test]
fn same_block_update_is_idempotent_and_collateral_floor_differs_from_debt_ceil() {
    let mut c = input();
    c.timestamp = c.last_update_timestamp;
    c.user_scaled_collateral = "1".into();
    c.user_scaled_variable_debt = "1".into();
    c.liquidity_index_ray = (RAY + 1).to_string();
    c.variable_borrow_index_ray = (RAY + 1).to_string();
    let p = project(&c).unwrap().projected.unwrap();
    assert_eq!(p.user_collateral_balance, "1");
    assert_eq!(p.user_variable_debt_balance, "2");
    let f = fixture();
    assert_eq!(reference(&c, &f, true).output, expected_output(&p));
    c = input();
    let p = project(&c).unwrap().projected.unwrap();
    assert_eq!(reference(&c, &f, true).output, expected_output(&p));
    c.liquidity_index_ray = p.liquidity_index_ray.clone();
    c.variable_borrow_index_ray = p.variable_borrow_index_ray.clone();
    c.accrued_to_treasury_scaled = p.accrued_to_treasury_scaled.clone();
    c.last_update_timestamp = p.last_update_timestamp;
    assert_eq!(project(&c).unwrap().projected.unwrap(), p);
}
#[test]
fn rejects_malformed_widths_and_preserves_downcast_vs_arithmetic_errors() {
    for bad in [
        "",
        "01",
        "-1",
        "1e27",
        "0x1",
        "1.0",
        " 1",
        "340282366920938463463374607431768211456",
    ] {
        let mut c = input();
        c.liquidity_rate_ray = bad.into();
        assert!(project(&c).is_err());
    }
    let mut c = input();
    c.timestamp = 1 << 40;
    assert!(project(&c).is_err());
    c = input();
    c.last_update_timestamp = 1 << 40;
    assert!(project(&c).is_err());
    c = input();
    c.liquidity_index_ray = u128::MAX.to_string();
    let r = project(&c).unwrap();
    assert!(r.projected.is_none());
    assert!(r
        .revert_data
        .unwrap()
        .starts_with(&nqc_miner::historical::hex(
            &keccak256("SafeCastOverflowedUintDowncast(uint8,uint256)")[..4]
        )));
    c = input();
    c.accrued_to_treasury_scaled = u128::MAX.to_string();
    assert_eq!(
        project(&c).unwrap().revert_data,
        Some(format!("0x4e487b71{:064x}", 0x11))
    );
    let mut data = serde_json::to_value(input()).unwrap();
    data["extra"] = Value::Bool(true);
    assert!(serde_json::from_value::<ReserveInput>(data).is_err());
}
#[test]
fn original_reserve_functions_match_boundaries_seeded_values_and_repeated_updates() {
    let f = fixture();
    assert_eq!(
        digest(&decode_hex(f["runtime_code"].as_str().unwrap()).unwrap()),
        f["runtime_sha256"]
    );
    assert_eq!(
        digest(include_bytes!("../fixtures/AaveReserveHarness.sol")),
        f["harness_source_sha256"]
    );
    let mut cases = vec![input()];
    for field in 0..9 {
        for n in [
            U256::ZERO,
            U256::from(1),
            U256::from(RAY - 1),
            U256::from(RAY),
            U256::from(RAY + 1),
            U256::from(u128::MAX),
        ] {
            let mut c = input();
            match field {
                0 => c.liquidity_index_ray = n.to_string(),
                1 => c.variable_borrow_index_ray = n.to_string(),
                2 => c.liquidity_rate_ray = n.to_string(),
                3 => c.variable_borrow_rate_ray = n.to_string(),
                4 => c.accrued_to_treasury_scaled = n.to_string(),
                5 => c.total_scaled_variable_debt = n.to_string(),
                6 => c.user_scaled_collateral = n.to_string(),
                7 => c.user_scaled_variable_debt = n.to_string(),
                _ => c.reserve_factor_bps = n.as_limbs()[0] as u16,
            }
            cases.push(c);
        }
    }
    for t in [0, 999_999, 1_000_000, 1_000_001, 32_536_000, (1 << 40) - 1] {
        for active in 0..4 {
            let mut c = input();
            c.timestamp = t;
            if active & 1 == 0 {
                c.liquidity_rate_ray = "0".into();
            }
            if active & 2 == 0 {
                c.total_scaled_variable_debt = "0".into();
            }
            cases.push(c);
        }
    }
    for field in 0..3 {
        let mut c = input();
        match field {
            0 => c.total_scaled_variable_debt = U256::MAX.to_string(),
            1 => c.user_scaled_collateral = U256::MAX.to_string(),
            _ => c.user_scaled_variable_debt = U256::MAX.to_string(),
        };
        cases.push(c);
    }
    let mut rng = ChaCha8Rng::seed_from_u64(0x4e51435f52455356);
    for i in 0..1024 {
        let mut c = input();
        c.liquidity_index_ray = rng.gen_range(RAY..4 * RAY).to_string();
        c.variable_borrow_index_ray = rng.gen_range(RAY..8 * RAY).to_string();
        c.liquidity_rate_ray = if i % 8 == 0 {
            "0".into()
        } else {
            rng.gen_range(1..3 * RAY).to_string()
        };
        c.variable_borrow_rate_ray = rng.gen_range(0..10 * RAY).to_string();
        c.reserve_factor_bps = [0, 1, 1000, 5000, 10000, 65535][rng.gen_range(0..6)];
        c.total_scaled_variable_debt = if i % 8 == 1 {
            "0".into()
        } else {
            rng.gen_range(1..10u128.pow(30)).to_string()
        };
        c.user_scaled_collateral = rng.gen_range(0..10u128.pow(27)).to_string();
        c.user_scaled_variable_debt = rng.gen_range(0..10u128.pow(27)).to_string();
        c.accrued_to_treasury_scaled = rng.gen_range(0..10u128.pow(22)).to_string();
        c.timestamp = c.last_update_timestamp + rng.gen_range(0..10 * 31_536_000);
        if i % 16 == 0 {
            c.timestamp = c.last_update_timestamp;
        }
        cases.push(c);
    }
    let mut counts = BTreeMap::<String, usize>::new();
    for (i, c) in cases.iter().enumerate() {
        let predicted = project(c).unwrap();
        for twice in [false, true] {
            let actual = reference(c, &f, twice);
            assert_eq!(actual.snapshot_kind, SnapshotKind::SyntheticFixture);
            assert!(!actual.canonical_state_authenticated);
            if let Some(p) = &predicted.projected {
                assert_eq!(
                    actual.status,
                    VmStatus::Success,
                    "case {i} twice={twice} {c:?}"
                );
                assert_eq!(
                    actual.output,
                    expected_output(p),
                    "case {i} twice={twice} {c:?}"
                );
            } else {
                assert_eq!(
                    actual.status,
                    VmStatus::Revert,
                    "case {i} twice={twice} {c:?}"
                );
                assert_eq!(
                    actual.output,
                    predicted.revert_data.as_ref().unwrap().as_str(),
                    "case {i} twice={twice} {c:?}"
                );
            }
        }
        let category = predicted
            .revert_data
            .map(|r| if r.len() > 10 { r[..10].to_owned() } else { r })
            .unwrap_or("success".into());
        *counts.entry(category).or_default() += 1;
    }
    assert_eq!(
        counts.len(),
        4,
        "success, empty revert, panic and safe-cast"
    );
    println!(
        "Reserve differential: {} inputs, {} executions; input outcomes {counts:?}",
        cases.len(),
        2 * cases.len()
    );
}
