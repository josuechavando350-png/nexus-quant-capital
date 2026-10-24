use alloy_primitives::{keccak256, U256};
use nqc_miner::{aave_collateral::*, digest, discovery::decode_hex, evm::*};
use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;
use serde_json::Value;
use std::collections::BTreeMap;
const RAY: u128 = 1_000_000_000_000_000_000_000_000_000;
fn input() -> CollateralInput {
    CollateralInput {
        liquidity_index_ray: (RAY * 3 / 2).to_string(),
        borrower_scaled_collateral_balance: "3".into(),
        collateral_to_liquidator: "2".into(),
        protocol_fee_collateral: "1".into(),
        collateral_price: "1".into(),
        collateral_decimals: 0,
        total_collateral_base: "4".into(),
        post_liquidator_scaled_balance: "1".into(),
    }
}
fn fixture() -> Value {
    serde_json::from_str(include_str!("../fixtures/aave_collateral_harness.json")).unwrap()
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
fn reference(value: &CollateralInput, fixture: &Value) -> SandboxOutcome {
    let mut target = account(2, fixture["runtime_code"].as_str().unwrap());
    target.storage = fixture["explicit_zero_slots"]
        .as_array()
        .unwrap()
        .iter()
        .map(|slot| (slot.as_u64().unwrap().to_string(), "0".into()))
        .collect();
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
    let words = [
        value.liquidity_index_ray.parse::<U256>().unwrap(),
        value.borrower_scaled_collateral_balance.parse().unwrap(),
        value.collateral_to_liquidator.parse().unwrap(),
        value.protocol_fee_collateral.parse().unwrap(),
        value.collateral_price.parse().unwrap(),
        U256::from(value.collateral_decimals),
        value.total_collateral_base.parse().unwrap(),
        value.post_liquidator_scaled_balance.parse().unwrap(),
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

fn expected(p: &CollateralAmounts) -> String {
    let words = [
        p.scaled_collateral_consumed.parse::<U256>().unwrap(),
        p.consumed_collateral_base.parse().unwrap(),
        U256::from(p.reserve_fully_consumed),
        U256::from(p.has_no_collateral_left),
        U256::from(p.clear_collateral_flag),
        U256::from(p.fee_transfer_required),
        p.final_protocol_fee_collateral.parse().unwrap(),
        p.final_protocol_fee_scaled.parse().unwrap(),
    ];
    "0x".to_owned()
        + &words
            .iter()
            .map(|w| format!("{w:064x}"))
            .collect::<String>()
}
fn compare(c: &CollateralInput, f: &Value) -> String {
    let predicted = calculate(c).unwrap();
    let actual = reference(c, f);
    assert_eq!(actual.snapshot_kind, SnapshotKind::SyntheticFixture);
    assert!(!actual.canonical_state_authenticated);
    if let Some(p) = predicted.amounts {
        assert_eq!(actual.status, VmStatus::Success, "{c:?}");
        assert_eq!(actual.output, expected(&p), "{c:?}");
        "success".into()
    } else {
        assert_eq!(actual.status, VmStatus::Revert, "{c:?}");
        let data = predicted.revert_data.unwrap();
        assert_eq!(actual.output, data, "{c:?}");
        if data.len() > 10 {
            data[..10].into()
        } else {
            data
        }
    }
}
#[test]
fn independent_ceil_consumption_can_exhaust_more_than_unscaled_arithmetic() {
    let c = input();
    let p = calculate(&c).unwrap().amounts.unwrap();
    // 2+1 underlying < floor(3*1.5)=4, but ceil(2/1.5)+ceil(1/1.5)=3.
    assert_eq!(p.scaled_collateral_consumed, "3");
    assert_eq!(p.consumed_collateral_base, "4");
    assert!(p.reserve_fully_consumed && p.has_no_collateral_left && p.clear_collateral_flag);
    compare(&c, &fixture());
    let mut c = c;
    c.total_collateral_base = "10".into(); // Another reserve still supplies collateral.
    let p = calculate(&c).unwrap().amounts.unwrap();
    assert!(p.reserve_fully_consumed && !p.has_no_collateral_left && p.clear_collateral_flag);
    compare(&c, &fixture());
}
#[test]
fn worthless_dust_can_clear_the_flag_with_scaled_collateral_remaining() {
    let mut c = input();
    c.liquidity_index_ray = RAY.to_string();
    c.protocol_fee_collateral = "0".into();
    c.collateral_decimals = 1;
    c.total_collateral_base = "0".into();
    let p = calculate(&c).unwrap().amounts.unwrap();
    assert_eq!(p.scaled_collateral_consumed, "2");
    assert!(!p.reserve_fully_consumed && p.has_no_collateral_left && p.clear_collateral_flag);
    assert!(!p.fee_transfer_required);
    compare(&c, &fixture());
}
#[test]
fn fee_cap_uses_supplied_post_transfer_balance_and_still_calls_on_zero_cap() {
    let mut c = input();
    c.protocol_fee_collateral = "2".into();
    let p = calculate(&c).unwrap().amounts.unwrap();
    assert_eq!(p.final_protocol_fee_collateral, "1");
    assert_eq!(p.final_protocol_fee_scaled, "1");
    compare(&c, &fixture());
    c.post_liquidator_scaled_balance = "0".into();
    let p = calculate(&c).unwrap().amounts.unwrap();
    assert!(p.fee_transfer_required);
    assert_eq!(p.final_protocol_fee_collateral, "0");
    assert_eq!(p.final_protocol_fee_scaled, "0");
    compare(&c, &fixture());
    c.post_liquidator_scaled_balance = "2".into(); // Equal cap threshold does not round fee down.
    let p = calculate(&c).unwrap().amounts.unwrap();
    assert_eq!(p.final_protocol_fee_collateral, "2");
    compare(&c, &fixture());
}
#[test]
fn malformed_inputs_are_distinct_from_solidity_reverts_and_no_authority_is_granted() {
    let report = calculate(&input()).unwrap();
    assert!(report.post_liquidator_balance_supplied);
    assert!(
        !report.token_operations_executed
            && !report.input_state_authenticated
            && !report.executable_eligibility_verified
            && !report.activation_allowed
    );
    for bad in [
        "",
        "01",
        "-1",
        "1.0",
        "0x1",
        "1e27",
        " 1",
        "115792089237316195423570985008687907853269984665640564039457584007913129639936",
    ] {
        let mut c = input();
        c.liquidity_index_ray = bad.into();
        assert!(calculate(&c).is_err());
    }
    let mut data = serde_json::to_value(input()).unwrap();
    data["extra"] = Value::Bool(true);
    assert!(serde_json::from_value::<CollateralInput>(data).is_err());
    let mut c = input();
    c.liquidity_index_ray = "0".into();
    let p = calculate(&c).unwrap();
    assert!(p.amounts.is_none());
    assert_eq!(p.revert_data, Some("0x".into()));
    c.collateral_decimals = 78; // Exponent overflow precedes the divide-by-zero helper.
    assert_eq!(
        calculate(&c).unwrap().revert_data,
        Some(format!("0x4e487b71{:064x}", 0x11))
    );
    compare(&c, &fixture());
}
#[test]
fn original_excerpts_match_boundaries_and_seeded_inputs_with_full_revert_bytes() {
    let f = fixture();
    assert_eq!(
        digest(&decode_hex(f["runtime_code"].as_str().unwrap()).unwrap()),
        f["runtime_sha256"]
    );
    assert_eq!(
        digest(include_bytes!("../fixtures/AaveCollateralHarness.sol")),
        f["harness_source_sha256"]
    );
    let mut cases = vec![input()];
    for field in 0..7 {
        for v in [
            U256::ZERO,
            U256::from(1),
            U256::from(2),
            U256::from(RAY - 1),
            U256::from(RAY),
            U256::from(RAY + 1),
            U256::from(u128::MAX),
            U256::MAX,
        ] {
            let mut c = input();
            match field {
                0 => c.liquidity_index_ray = v.to_string(),
                1 => c.borrower_scaled_collateral_balance = v.to_string(),
                2 => c.collateral_to_liquidator = v.to_string(),
                3 => c.protocol_fee_collateral = v.to_string(),
                4 => c.collateral_price = v.to_string(),
                5 => c.total_collateral_base = v.to_string(),
                _ => c.post_liquidator_scaled_balance = v.to_string(),
            }
            cases.push(c);
        }
    }
    for decimals in [0, 6, 8, 18, 77, 78, 255] {
        let mut c = input();
        c.collateral_decimals = decimals;
        cases.push(c);
    }
    let mut c = input();
    c.liquidity_index_ray = "1".into();
    c.collateral_to_liquidator = (U256::MAX / U256::from(RAY)).to_string();
    c.protocol_fee_collateral = c.collateral_to_liquidator.clone();
    cases.push(c);
    let mut rng = ChaCha8Rng::seed_from_u64(0x4e51435f434f4c4c);
    for i in 0..1024 {
        let mut c = input();
        let index = rng.gen_range(RAY..5 * RAY);
        let scaled = rng.gen_range(0..10u128.pow(27));
        let underlying = U256::from(scaled) * U256::from(index) / U256::from(RAY);
        c.liquidity_index_ray = index.to_string();
        c.borrower_scaled_collateral_balance = scaled.to_string();
        let liquidator = rng.gen_range(0..=underlying.to::<u128>());
        let fee = rng.gen_range(0..=underlying.to::<u128>() - liquidator);
        c.collateral_to_liquidator = liquidator.to_string();
        c.protocol_fee_collateral = if i % 8 == 0 {
            "0".into()
        } else {
            fee.to_string()
        };
        c.collateral_price = rng.gen_range(1..10u128.pow(18)).to_string();
        c.collateral_decimals = [0, 6, 8, 18, 77][rng.gen_range(0..5)];
        let base = underlying * c.collateral_price.parse::<U256>().unwrap()
            / U256::from(10).pow(U256::from(c.collateral_decimals));
        c.total_collateral_base = (base + U256::from(if i % 2 == 0 { 0 } else { 1 })).to_string();
        c.post_liquidator_scaled_balance = if i % 8 == 1 {
            "0".into()
        } else {
            rng.gen_range(0..=scaled).to_string()
        };
        cases.push(c);
    }
    let mut counts = BTreeMap::<String, usize>::new();
    for c in &cases {
        *counts.entry(compare(c, &f)).or_default() += 1;
    }
    assert_eq!(
        counts.len(),
        3,
        "success, empty revert and arithmetic panic"
    );
    println!(
        "Collateral differential: {} executions; outcomes {counts:?}",
        cases.len()
    );
}
