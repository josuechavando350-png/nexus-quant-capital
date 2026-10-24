//! Actual WETH feed proxy; aggregator answers and controller are explicit doubles.
use super::*;
const CONTROLLER: &str = "0x8888888888888888888888888888888888888888";
fn weth_feed_fixture() -> Value {
    serde_json::from_str(include_str!("../../fixtures/aave_weth_feed_execution.json")).unwrap()
}
fn weth_proxy() -> String {
    feed_addresses(&oracle_fixture())[1].clone()
}
fn observed_aggregator() -> String {
    weth_feed_fixture()["weth_feed_observations"][0]["aggregator"]
        .as_str()
        .unwrap()
        .into()
}
fn weth_feed_setup(c: &AccountCase, receive: bool) -> (PinnedSnapshot, SandboxCall) {
    let (mut s, q) = oracle_setup(c, receive);
    let f = weth_feed_fixture();
    let proxy = weth_proxy();
    let aggregator = observed_aggregator();
    let mut downstream = s
        .accounts
        .iter()
        .find(|a| a.address == proxy)
        .unwrap()
        .clone();
    downstream.address = aggregator;
    s.accounts.push(downstream);
    let a = s.accounts.iter_mut().find(|a| a.address == proxy).unwrap();
    a.runtime_code = f["contracts"]["EACAggregatorProxy"]["runtime_code"]
        .as_str()
        .unwrap()
        .into();
    a.code_hash = format!("{:#x}", keccak256(decode_hex(&a.runtime_code).unwrap()));
    a.storage.clear();
    let o = &f["weth_feed_observations"][0];
    // These observations select the route; the remaining witness is artificial.
    assert_eq!(o["controller"].as_str().unwrap(), ZERO);
    for (slot, word) in [("2", "phase_word"), ("5", "controller_word")] {
        a.storage
            .insert(slot.into(), num_hex(o[word].as_str().unwrap()).to_string());
    }
    (s, q)
}
fn add_controller(s: &mut PinnedSnapshot) -> WitnessAccount {
    let f = weth_feed_fixture();
    let mut a = account(
        CONTROLLER,
        f["contracts"]["SyntheticFeedAccessController"]["runtime_code"]
            .as_str()
            .unwrap(),
    );
    for (slot, value) in [
        (0, U256::from(1)),
        (1, U256::ZERO),
        (2, addr(AAVE_ORACLE)),
        (3, addr(&weth_proxy())),
    ] {
        a.storage.insert(slot.to_string(), value.to_string());
    }
    s.accounts.push(a.clone());
    s.accounts
        .iter_mut()
        .find(|a| a.address == weth_proxy())
        .unwrap()
        .storage
        .insert("5".into(), addr(CONTROLLER).to_string());
    a
}
fn check_weth_feed(c: &AccountCase, receive: bool) -> SandboxOutcome {
    let reference = check_oracle(c, receive);
    let (s, q) = weth_feed_setup(c, receive);
    let out = simulate(&s, &q).unwrap();
    assert_same_execution(&out, &reference);
    assert!(!out.canonical_state_authenticated);
    out
}
fn caller_sensitive_account(c: &AccountCase) -> WitnessAccount {
    let f = weth_feed_fixture();
    let mut a = account(
        &observed_aggregator(),
        f["contracts"]["SyntheticCallerSensitiveFeed"]["runtime_code"]
            .as_str()
            .unwrap(),
    );
    for (slot, value) in [
        (0, addr(&weth_proxy())),
        (1, c.sizing.prelude.payment.underlying.transfer.price),
        (2, U256::from(17)),
    ] {
        a.storage.insert(slot.to_string(), value.to_string());
    }
    a
}
#[test]
fn observed_weth_proxy_preserves_both_complete_payments_and_exports_evidence() {
    for receive in [false, true] {
        let out = check_weth_feed(&AccountCase::default(), receive);
        if let Ok(path) = std::env::var("NQC_MINER_WETH_FEED_EVIDENCE_DIR") {
            let dir =
                std::path::Path::new(&path).join(if receive { "atoken" } else { "underlying" });
            std::fs::create_dir_all(&dir).unwrap();
            let (snapshot, call) = weth_feed_setup(&AccountCase::default(), receive);
            let mut extras = snapshot.clone();
            let controller = add_controller(&mut extras);
            add_fallback(&mut extras, &AccountCase::default());
            let fallback = extras
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
                    serde_json::json!({"controller_account":controller,"fallback_account":fallback,
                    "proxy":weth_proxy(),"aggregator":observed_aggregator(),"collateral":COLLATERAL,
                    "caller_sensitive_account":caller_sensitive_account(&AccountCase::default())}),
                ),
            ] {
                use std::io::Write;
                let mut file = std::fs::File::create_new(dir.join(name)).unwrap();
                file.write_all(&serde_json::to_vec_pretty(&value).unwrap())
                    .unwrap();
                file.write_all(b"\n").unwrap();
            }
        }
    }
}
#[test]
fn downstream_observes_proxy_caller_even_when_direct_price_is_different() {
    for receive in [false, true] {
        let c = AccountCase::default();
        let reference = check_weth_feed(&c, receive);
        let (mut s, q) = weth_feed_setup(&c, receive);
        let a = s
            .accounts
            .iter_mut()
            .find(|a| a.address == observed_aggregator())
            .unwrap();
        *a = caller_sensitive_account(&c);
        assert_same_execution(&simulate(&s, &q).unwrap(), &reference);
        let mut direct = q.clone();
        direct.to = observed_aggregator();
        direct.calldata = "0x50d25bcd".into();
        let out = simulate(&s, &direct).unwrap();
        assert_eq!(out.status, VmStatus::Success);
        assert_eq!(out.output, encoded(&[U256::from(17)]));
        assert_no_contract_changes(&out);
    }
}
#[test]
fn seeded_prices_emode_and_rates_preserve_full_effects_through_real_proxy() {
    let mut rng = ChaCha8Rng::seed_from_u64(0x00fe_ed20_2610);
    for n in 0..16 {
        let mut c = AccountCase::default();
        c.sizing.debt_price *= U256::from(rng.gen_range(1u64..=2));
        c.sizing.prelude.debt.borrow_rate = U256::from(rng.gen_range(0..RAY / 5));
        if n % 2 == 0 {
            c.category = 1;
            c.mode = [7500u64, 8500, 11000, 4, 0, 0].map(U256::from);
        }
        for receive in [false, true] {
            check_weth_feed(&c, receive);
        }
    }
}
#[test]
fn signed_aggregator_answers_reach_oracle_fallback_and_positive_limit_is_unchanged() {
    for receive in [false, true] {
        let c = AccountCase::default();
        let reference = check_weth_feed(&c, receive);
        for value in [U256::ZERO, U256::MAX, U256::from(1) << 255usize] {
            let (mut s, q) = weth_feed_setup(&c, receive);
            add_fallback(&mut s, &c);
            s.accounts
                .iter_mut()
                .find(|a| a.address == observed_aggregator())
                .unwrap()
                .storage
                .insert("0".into(), value.to_string());
            assert_same_execution(&simulate(&s, &q).unwrap(), &reference);
        }
    }
    let (mut s, mut q) = weth_feed_setup(&AccountCase::default(), true);
    let max = (U256::from(1) << 255usize) - U256::from(1);
    s.accounts
        .iter_mut()
        .find(|a| a.address == observed_aggregator())
        .unwrap()
        .storage
        .insert("0".into(), max.to_string());
    q.to = AAVE_ORACLE.into();
    q.calldata = "0xb3596f07".to_owned() + &encoded(&[addr(COLLATERAL)])[2..];
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Success);
    assert_eq!(out.output, encoded(&[max]));
    assert_no_contract_changes(&out);
}
#[test]
fn controller_checks_actual_oracle_caller_proxy_and_calldata_with_atomic_denial() {
    for receive in [false, true] {
        let c = AccountCase::default();
        let reference = check_weth_feed(&c, receive);
        let (mut s, q) = weth_feed_setup(&c, receive);
        add_controller(&mut s);
        assert_same_execution(&simulate(&s, &q).unwrap(), &reference);
        for (slot, value, message) in [
            (0, U256::ZERO, "No access"),
            (1, U256::from(1), "synthetic controller blocked"),
            (2, addr(CALLER), "No access"),
            (3, addr(CALLER), "No access"),
        ] {
            let mut denied = s.clone();
            denied
                .accounts
                .iter_mut()
                .find(|a| a.address == CONTROLLER)
                .unwrap()
                .storage
                .insert(slot.to_string(), value.to_string());
            payment_revert(&denied, &q, message);
        }
        let mut direct = q.clone();
        direct.to = weth_proxy();
        direct.calldata = "0x50d25bcd".into();
        payment_revert(&s, &direct, "No access");
    }
}
#[test]
fn missing_proxy_route_controller_and_aggregator_witnesses_fail_closed() {
    for receive in [false, true] {
        let (mut s, q) = weth_feed_setup(&AccountCase::default(), receive);
        add_controller(&mut s);
        for address in [weth_proxy(), observed_aggregator(), CONTROLLER.into()] {
            let mut missing = s.clone();
            missing.accounts.retain(|a| a.address != address);
            assert!(simulate(&missing, &q).is_err());
        }
        for (address, slot) in [
            (weth_proxy(), "2"),
            (weth_proxy(), "5"),
            (observed_aggregator(), "0"),
            (CONTROLLER.into(), "0"),
            (CONTROLLER.into(), "2"),
        ] {
            let mut missing = s.clone();
            assert!(missing
                .accounts
                .iter_mut()
                .find(|a| a.address == address)
                .unwrap()
                .storage
                .remove(slot)
                .is_some());
            assert!(simulate(&missing, &q).is_err());
        }
    }
}
#[test]
fn aggregator_revert_empty_and_malformed_controller_returns_never_trigger_fallback() {
    for receive in [false, true] {
        for which in 0..3 {
            let c = AccountCase::default();
            let (mut s, q) = weth_feed_setup(&c, receive);
            add_fallback(&mut s, &c);
            if which == 2 {
                add_controller(&mut s);
            }
            let target = if which == 2 {
                CONTROLLER.into()
            } else {
                observed_aggregator()
            };
            let a = s.accounts.iter_mut().find(|a| a.address == target).unwrap();
            if which == 0 {
                a.storage.insert("1".into(), "1".into());
            } else {
                a.runtime_code = "0x60006000f3".into();
                a.code_hash = format!("{:#x}", keccak256(decode_hex(&a.runtime_code).unwrap()));
            }
            let out = simulate(&s, &q).unwrap();
            assert_eq!(out.status, VmStatus::Revert);
            assert_eq!(
                out.output,
                if which == 0 {
                    abi_string_error("synthetic feed blocked")
                } else {
                    "0x".into()
                }
            );
            assert_no_contract_changes(&out);
        }
    }
}
#[test]
fn packed_phase_extremes_alternate_aggregator_and_observed_routes_use_only_current_phase() {
    let f = weth_feed_fixture();
    for receive in [false, true] {
        let c = AccountCase::default();
        let reference = check_weth_feed(&c, receive);
        for o in f["weth_feed_observations"].as_array().unwrap() {
            let (mut s, q) = weth_feed_setup(&c, receive);
            s.accounts
                .iter_mut()
                .find(|a| a.address == observed_aggregator())
                .unwrap()
                .address = o["aggregator"].as_str().unwrap().into();
            s.accounts
                .iter_mut()
                .find(|a| a.address == weth_proxy())
                .unwrap()
                .storage
                .insert(
                    "2".into(),
                    num_hex(o["phase_word"].as_str().unwrap()).to_string(),
                );
            assert_same_execution(&simulate(&s, &q).unwrap(), &reference);
        }
        for phase in [0u64, 1, 65535] {
            let (mut s, q) = weth_feed_setup(&c, receive);
            s.accounts
                .iter_mut()
                .find(|a| a.address == observed_aggregator())
                .unwrap()
                .address = ALTERNATE.into();
            // Upper unused bits and phase ID must not corrupt the 160-bit address.
            let word = (U256::MAX << 176usize) | (addr(ALTERNATE) << 16usize) | U256::from(phase);
            s.accounts
                .iter_mut()
                .find(|a| a.address == weth_proxy())
                .unwrap()
                .storage
                .insert("2".into(), word.to_string());
            assert_same_execution(&simulate(&s, &q).unwrap(), &reference);
        }
    }
}
#[test]
fn late_usdc_failure_rolls_back_reserves_rewards_and_transfers_after_feed_proxy_execution() {
    for receive in [false, true] {
        let (mut s, q) = weth_feed_setup(&AccountCase::default(), receive);
        s.accounts
            .iter_mut()
            .find(|a| a.address == ASSET)
            .unwrap()
            .storage
            .insert("1".into(), (U256::from(1) << 160usize).to_string());
        payment_revert(&s, &q, "Pausable: paused");
    }
}
