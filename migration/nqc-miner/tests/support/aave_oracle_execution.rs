//! Observed, fully recompiled AaveOracle with explicit synthetic feed/fallback code.
#[path = "aave_weth_feed_execution.rs"]
mod aave_weth_feed_execution;
use super::*;
const AAVE_ORACLE: &str = "0x54586be62e3c3580375ae3723c145253060ca0c2";
const FALLBACK: &str = "0x7777777777777777777777777777777777777777";
const ZERO: &str = "0x0000000000000000000000000000000000000000";
fn oracle_fixture() -> Value {
    serde_json::from_str(include_str!("../../fixtures/aave_oracle_execution.json")).unwrap()
}
fn feed_addresses(f: &Value) -> Vec<String> {
    f["oracle_observations"][0]["feeds"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v["source"].as_str().unwrap().to_owned())
        .collect()
}
fn oracle_setup(c: &AccountCase, receive: bool) -> (PinnedSnapshot, SandboxCall) {
    let (mut s, mut q) = account_setup(c, receive);
    let f = oracle_fixture();
    let pool = s.accounts.iter_mut().find(|a| a.address == POOL).unwrap();
    pool.runtime_code = f["contracts"]["AaveOracleExecutionHarness"]["runtime_code"]
        .as_str()
        .unwrap()
        .into();
    pool.code_hash = format!("{:#x}", keccak256(decode_hex(&pool.runtime_code).unwrap()));
    let signature = f["contracts"]["AaveOracleExecutionHarness"]["selectors"]
        .as_object()
        .unwrap()
        .iter()
        .find(|(k, _)| k.starts_with("calculate("))
        .unwrap();
    assert_eq!(
        &hex(&keccak256(signature.0)[..4])[2..],
        signature.1.as_str().unwrap()
    );
    q.calldata = "0x".to_owned() + signature.1.as_str().unwrap() + &q.calldata[10..];
    s.accounts.retain(|a| a.address != ORACLE);
    let sources = feed_addresses(&f);
    assert_eq!(sources.len(), 2);
    assert_ne!(sources[0], sources[1]);
    let mut oracle = account(
        AAVE_ORACLE,
        f["contracts"]["AaveOracle"]["runtime_code"]
            .as_str()
            .unwrap(),
    );
    oracle.storage.insert(
        "1".into(),
        num_hex(
            f["oracle_observations"][0]["fallback_word"]
                .as_str()
                .unwrap(),
        )
        .to_string(),
    );
    for (asset, source, price) in [
        (ASSET, &sources[0], c.sizing.debt_price),
        (
            COLLATERAL,
            &sources[1],
            c.sizing.prelude.payment.underlying.transfer.price,
        ),
    ] {
        oracle
            .storage
            .insert(mapping(asset, 0).to_string(), addr(source).to_string());
        let mut feed = account(
            source,
            f["contracts"]["SyntheticOracleFeed"]["runtime_code"]
                .as_str()
                .unwrap(),
        );
        feed.storage.insert("0".into(), price.to_string());
        feed.storage.insert("1".into(), "0".into());
        s.accounts.push(feed);
    }
    s.accounts.push(oracle);
    (s, q)
}
fn num_hex(v: &str) -> U256 {
    U256::from_str_radix(&v[2..], 16).unwrap()
}
fn check_oracle(c: &AccountCase, receive: bool) -> SandboxOutcome {
    let reference = check_account(c, receive);
    let (s, q) = oracle_setup(c, receive);
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Success, "{}", out.output);
    assert_eq!(out.output, reference.output);
    assert_eq!(out.logs, reference.logs);
    assert_eq!(storage_changes(&out), storage_changes(&reference));
    assert!(!out.canonical_state_authenticated);
    out
}
fn add_fallback(s: &mut PinnedSnapshot, c: &AccountCase) {
    let f = oracle_fixture();
    let mut fallback = account(
        FALLBACK,
        f["contracts"]["SyntheticFallbackOracle"]["runtime_code"]
            .as_str()
            .unwrap(),
    );
    fallback.storage.insert("1".into(), "0".into());
    fallback.storage.insert(
        mapping(ASSET, 0).to_string(),
        c.sizing.debt_price.to_string(),
    );
    fallback.storage.insert(
        mapping(COLLATERAL, 0).to_string(),
        c.sizing
            .prelude
            .payment
            .underlying
            .transfer
            .price
            .to_string(),
    );
    s.accounts.push(fallback);
    s.accounts
        .iter_mut()
        .find(|a| a.address == AAVE_ORACLE)
        .unwrap()
        .storage
        .insert("1".into(), addr(FALLBACK).to_string());
}
fn assert_same_execution(out: &SandboxOutcome, reference: &SandboxOutcome) {
    assert_eq!(out.status, VmStatus::Success);
    assert_eq!(out.output, reference.output);
    assert_eq!(out.logs, reference.logs);
    assert_eq!(storage_changes(out), storage_changes(reference));
}
#[test]
fn actual_oracle_runtime_and_observed_source_routes_preserve_both_complete_payments() {
    let c = AccountCase::default();
    for receive in [false, true] {
        let out = check_oracle(&c, receive);
        if let Ok(path) = std::env::var("NQC_MINER_ORACLE_EVIDENCE_DIR") {
            let dir =
                std::path::Path::new(&path).join(if receive { "atoken" } else { "underlying" });
            std::fs::create_dir_all(&dir).unwrap();
            let (snapshot, call) = oracle_setup(&c, receive);
            let mut fallback_snapshot = snapshot.clone();
            add_fallback(&mut fallback_snapshot, &c);
            let fallback_account = fallback_snapshot
                .accounts
                .iter()
                .find(|a| a.address == FALLBACK)
                .unwrap();
            for (name, value) in [
                (
                    "input.json",
                    serde_json::json!({"snapshot":snapshot,"call":call}),
                ),
                ("output.json", serde_json::to_value(out).unwrap()),
                (
                    "models.json",
                    serde_json::json!({"fallback_account":fallback_account,
                    "base_currency_slot":mapping(ZERO,0).to_string(),
                    "feed_addresses":feed_addresses(&oracle_fixture())}),
                ),
            ] {
                use std::io::Write;
                let mut f = std::fs::File::create_new(dir.join(name)).unwrap();
                f.write_all(&serde_json::to_vec_pretty(&value).unwrap())
                    .unwrap();
                f.write_all(b"\n").unwrap();
            }
        }
    }
}
#[test]
fn seeded_prices_thresholds_and_emode_match_prior_account_composition() {
    let mut rng = ChaCha8Rng::seed_from_u64(0x00a0_ac1e_2026);
    for n in 0..24 {
        let mut c = AccountCase::default();
        c.sizing.debt_price *= U256::from(rng.gen_range(1u64..=2));
        c.sizing.prelude.debt.borrow_rate = U256::from(rng.gen_range(0..RAY / 5));
        if n % 2 == 0 {
            c.category = 1;
            c.mode = [
                U256::from(7500),
                U256::from(8500),
                U256::from(11000),
                U256::from(4),
                U256::ZERO,
                U256::ZERO,
            ];
        }
        if n % 3 == 0 {
            c.sizing
                .prelude
                .payment
                .underlying
                .transfer
                .rewards
                .rewards
                .clear();
        }
        for receive in [false, true] {
            check_oracle(&c, receive);
        }
    }
}
#[test]
fn missing_source_zero_and_negative_signed_answers_use_original_fallback_for_both_assets() {
    let c = AccountCase::default();
    let sources = feed_addresses(&oracle_fixture());
    for receive in [false, true] {
        let reference = check_oracle(&c, receive);
        for index in 0..2 {
            for answer in [
                None,
                Some(U256::ZERO),
                Some(U256::MAX),
                Some(U256::from(1) << 255usize),
            ] {
                let (mut s, q) = oracle_setup(&c, receive);
                add_fallback(&mut s, &c);
                if let Some(value) = answer {
                    s.accounts
                        .iter_mut()
                        .find(|a| a.address == sources[index])
                        .unwrap()
                        .storage
                        .insert("0".into(), value.to_string());
                } else {
                    let asset = [ASSET, COLLATERAL][index];
                    s.accounts
                        .iter_mut()
                        .find(|a| a.address == AAVE_ORACLE)
                        .unwrap()
                        .storage
                        .insert(mapping(asset, 0).to_string(), "0".into());
                    s.accounts.retain(|a| a.address != sources[index]);
                }
                assert_same_execution(&simulate(&s, &q).unwrap(), &reference);
            }
        }
    }
}
#[test]
fn positive_source_ignores_fallback_but_source_revert_and_malformed_return_do_not_trigger_it() {
    let c = AccountCase::default();
    let sources = feed_addresses(&oracle_fixture());
    for receive in [false, true] {
        let reference = check_oracle(&c, receive);
        let (mut s, q) = oracle_setup(&c, receive);
        // An absent fallback witness is unnecessary when both answers are positive.
        assert!(s
            .accounts
            .iter_mut()
            .find(|a| a.address == AAVE_ORACLE)
            .unwrap()
            .storage
            .remove("1")
            .is_some());
        assert_same_execution(&simulate(&s, &q).unwrap(), &reference);
        for malformed in [false, true] {
            let (mut s, q) = oracle_setup(&c, receive);
            add_fallback(&mut s, &c);
            let feed = s
                .accounts
                .iter_mut()
                .find(|a| a.address == sources[0])
                .unwrap();
            if malformed {
                feed.runtime_code = "0x60006000f3".into();
                feed.code_hash =
                    format!("{:#x}", keccak256(decode_hex(&feed.runtime_code).unwrap()));
            } else {
                feed.storage.insert("1".into(), "1".into());
            }
            let out = simulate(&s, &q).unwrap();
            assert_eq!(out.status, VmStatus::Revert);
            assert_eq!(
                out.output,
                if malformed {
                    "0x".to_owned()
                } else {
                    abi_string_error("synthetic feed blocked")
                }
            );
            assert_no_contract_changes(&out);
        }
    }
}
#[test]
fn fallback_failure_zero_address_and_late_usdc_failure_revert_complete_composition() {
    let c = AccountCase::default();
    let sources = feed_addresses(&oracle_fixture());
    for receive in [false, true] {
        let (mut s, q) = oracle_setup(&c, receive);
        add_fallback(&mut s, &c);
        s.accounts
            .iter_mut()
            .find(|a| a.address == sources[0])
            .unwrap()
            .storage
            .insert("0".into(), "0".into());
        s.accounts
            .iter_mut()
            .find(|a| a.address == FALLBACK)
            .unwrap()
            .storage
            .insert("1".into(), "1".into());
        let out = simulate(&s, &q).unwrap();
        assert_eq!(out.status, VmStatus::Revert);
        assert_eq!(out.output, abi_string_error("synthetic fallback blocked"));
        assert_no_contract_changes(&out);
        s.accounts
            .iter_mut()
            .find(|a| a.address == AAVE_ORACLE)
            .unwrap()
            .storage
            .insert("1".into(), "0".into());
        s.accounts.push(account(ZERO, "0x"));
        let out = simulate(&s, &q).unwrap();
        assert_eq!(out.status, VmStatus::Revert);
        assert_eq!(out.output, "0x");
        assert_no_contract_changes(&out);
        let (mut s, q) = oracle_setup(&c, receive);
        s.accounts
            .iter_mut()
            .find(|a| a.address == ASSET)
            .unwrap()
            .storage
            .insert("1".into(), (U256::from(1) << 160usize).to_string());
        payment_revert(&s, &q, "Pausable: paused");
    }
}
#[test]
fn missing_routing_feed_account_and_answer_witnesses_fail_closed() {
    let sources = feed_addresses(&oracle_fixture());
    for receive in [false, true] {
        let (s, q) = oracle_setup(&AccountCase::default(), receive);
        for address in [AAVE_ORACLE, &sources[0], &sources[1]] {
            let mut missing = s.clone();
            missing.accounts.retain(|a| a.address != address);
            assert!(simulate(&missing, &q).is_err());
        }
        for (address, slot) in [
            (AAVE_ORACLE, mapping(ASSET, 0)),
            (AAVE_ORACLE, mapping(COLLATERAL, 0)),
            (&sources[0], U256::ZERO),
            (&sources[1], U256::ZERO),
        ] {
            let mut missing = s.clone();
            assert!(missing
                .accounts
                .iter_mut()
                .find(|a| a.address == address)
                .unwrap()
                .storage
                .remove(&slot.to_string())
                .is_some());
            assert!(simulate(&missing, &q).is_err());
        }
    }
}
#[test]
fn original_base_currency_and_maximum_signed_positive_answers_are_exact_read_only_calls() {
    let f = oracle_fixture();
    let sources = feed_addresses(&f);
    let (mut s, mut q) = oracle_setup(&AccountCase::default(), true);
    q.to = AAVE_ORACLE.into();
    let selector = f["contracts"]["AaveOracle"]["selectors"]["getAssetPrice(address)"]
        .as_str()
        .unwrap();
    s.accounts
        .iter_mut()
        .find(|a| a.address == AAVE_ORACLE)
        .unwrap()
        .storage
        .insert(mapping(ZERO, 0).to_string(), "0".into());
    q.calldata = "0x".to_owned() + selector + &encoded(&[U256::ZERO])[2..];
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Success);
    assert_eq!(out.output, encoded(&[U256::from(100_000_000)]));
    assert_no_contract_changes(&out);
    let max = (U256::from(1) << 255usize) - U256::from(1);
    s.accounts
        .iter_mut()
        .find(|a| a.address == sources[0])
        .unwrap()
        .storage
        .insert("0".into(), max.to_string());
    q.calldata = "0x".to_owned() + selector + &encoded(&[addr(ASSET)])[2..];
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Success);
    assert_eq!(out.output, encoded(&[max]));
    assert_no_contract_changes(&out);
}
