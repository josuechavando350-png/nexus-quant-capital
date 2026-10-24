//! Observed DualAggregator runtime: supplied round state, bounded observed read samples.
use super::*;
fn dual_fixture() -> Value {
    serde_json::from_str(include_str!(
        "../../fixtures/aave_dual_aggregator_execution.json"
    ))
    .unwrap()
}
fn dual_slot(round: u32) -> U256 {
    map_word(U256::from(round), U256::from(17))
}
fn transmission(answer: U256, observed: u32, recorded: u32) -> U256 {
    (answer & ((U256::from(1) << 192usize) - U256::from(1)))
        | (U256::from(observed) << 192usize)
        | (U256::from(recorded) << 224usize)
}
fn dual_account(s: &mut PinnedSnapshot) -> &mut WitnessAccount {
    s.accounts
        .iter_mut()
        .find(|a| a.address == observed_aggregator())
        .unwrap()
}
fn hot(s: &mut PinnedSnapshot, latest: u32, secondary: u32, is_secondary: bool) {
    let word = (U256::from(latest) << 48usize)
        | (U256::from(secondary) << 80usize)
        | (U256::from(u8::from(is_secondary)) << 240usize);
    dual_account(s)
        .storage
        .insert("13".into(), word.to_string());
}
fn round(s: &mut PinnedSnapshot, id: u32, answer: U256, recorded: u32) {
    dual_account(s).storage.insert(
        dual_slot(id).to_string(),
        transmission(answer, recorded.saturating_sub(1), recorded).to_string(),
    );
}
fn dual_setup(c: &AccountCase, receive: bool) -> (PinnedSnapshot, SandboxCall) {
    let (mut s, q) = weth_feed_setup(c, receive);
    let f = dual_fixture();
    let a = dual_account(&mut s);
    a.runtime_code = f["contracts"]["DualAggregator"]["runtime_code"]
        .as_str()
        .unwrap()
        .into();
    a.code_hash = format!("{:#x}", keccak256(decode_hex(&a.runtime_code).unwrap()));
    a.storage.clear();
    a.storage.insert("18".into(), "60".into());
    hot(&mut s, 100, 99, false);
    let now = u32::try_from(s.timestamp).unwrap();
    round(
        &mut s,
        99,
        c.sizing.prelude.payment.underlying.transfer.price,
        now - 1,
    );
    round(&mut s, 100, U256::from(17), now - 1);
    (s, q)
}
fn check_dual(c: &AccountCase, receive: bool) -> SandboxOutcome {
    let reference = check_weth_feed(c, receive);
    let (s, q) = dual_setup(c, receive);
    let out = simulate(&s, &q).unwrap();
    assert_same_execution(&out, &reference);
    assert!(!out.canonical_state_authenticated);
    out
}
fn read_call(q: &SandboxCall, target: &str, selector: &str) -> SandboxCall {
    let mut call = q.clone();
    call.to = target.into();
    call.calldata = selector.into();
    call
}
fn price_call(q: &SandboxCall) -> SandboxCall {
    read_call(
        q,
        AAVE_ORACLE,
        &("0xb3596f07".to_owned() + &encoded(&[addr(COLLATERAL)])[2..]),
    )
}
fn read_price(s: &PinnedSnapshot, q: &SandboxCall, expected: U256) {
    let out = simulate(s, &price_call(q)).unwrap();
    assert_eq!(out.status, VmStatus::Success);
    assert_eq!(out.output, encoded(&[expected]));
    assert_no_contract_changes(&out);
}
fn export(path: &std::path::Path, values: &[(&str, Value)]) {
    use std::io::Write;
    std::fs::create_dir_all(path).unwrap();
    for (name, value) in values {
        let mut file = std::fs::File::create_new(path.join(name)).unwrap();
        file.write_all(&serde_json::to_vec_pretty(value).unwrap())
            .unwrap();
        file.write_all(b"\n").unwrap();
    }
}
#[test]
fn actual_dual_runtime_preserves_both_complete_payments_and_exports_witnesses() {
    for receive in [false, true] {
        let c = AccountCase::default();
        let out = check_dual(&c, receive);
        if let Ok(path) = std::env::var("NQC_MINER_DUAL_EVIDENCE_DIR") {
            let dir =
                std::path::Path::new(&path).join(if receive { "atoken" } else { "underlying" });
            let (s, q) = dual_setup(&c, receive);
            let mut extras = s.clone();
            add_fallback(&mut extras, &c);
            let fallback = extras
                .accounts
                .iter()
                .find(|a| a.address == FALLBACK)
                .unwrap();
            let slots: BTreeMap<String, String> = (0..=100)
                .map(|n| (n.to_string(), dual_slot(n).to_string()))
                .collect();
            export(
                &dir,
                &[
                    ("input.json", serde_json::json!({"snapshot":s,"call":q})),
                    ("output.json", serde_json::to_value(out).unwrap()),
                    (
                        "models.json",
                        serde_json::json!({"round_slots":slots,"aggregator":observed_aggregator(),"fallback_account":fallback}),
                    ),
                ],
            );
        }
    }
}
#[test]
fn seeded_full_composition_preserves_account_amounts_events_and_storage() {
    let mut rng = ChaCha8Rng::seed_from_u64(0x00d0_a120_2610);
    for n in 0..16 {
        let mut c = AccountCase::default();
        c.sizing.debt_price *= U256::from(rng.gen_range(1u64..=2));
        c.sizing.prelude.debt.borrow_rate = U256::from(rng.gen_range(0..RAY / 5));
        if n % 2 == 0 {
            c.category = 1;
            c.mode = [7500u64, 8500, 11000, 4, 0, 0].map(U256::from);
        }
        for receive in [false, true] {
            check_dual(&c, receive);
        }
    }
}
#[test]
fn python_slot_vectors_and_all_observed_transmission_keys_match_alloy_keccak() {
    let f = dual_fixture();
    for v in f["slot_vectors"].as_array().unwrap() {
        assert_eq!(
            map_word(
                num(v["key"].as_str().unwrap()),
                num(v["root"].as_str().unwrap())
            ),
            num_hex(v["slot"].as_str().unwrap())
        );
    }
    for h in f["dual_observations"].as_array().unwrap() {
        for t in h["transmissions"].as_array().unwrap() {
            assert_eq!(
                dual_slot(t["round"].as_u64().unwrap() as u32),
                num_hex(t["slot"].as_str().unwrap())
            );
        }
    }
}
#[test]
fn observed_slots_and_timestamp_reproduce_all_three_direct_proxy_and_oracle_reads() {
    let f = dual_fixture();
    for (index, h) in f["dual_observations"]
        .as_array()
        .unwrap()
        .iter()
        .enumerate()
    {
        let (mut s, q) = dual_setup(&AccountCase::default(), true);
        s.block_number = h["block"]["number"].as_u64().unwrap();
        s.block_hash = h["block"]["hash"].as_str().unwrap().into();
        s.timestamp = h["block"]["timestamp"].as_u64().unwrap();
        s.accounts.retain(|a| {
            [
                CALLER,
                COINBASE,
                AAVE_ORACLE,
                &weth_proxy(),
                &observed_aggregator(),
            ]
            .contains(&a.address.as_str())
        });
        let a = dual_account(&mut s);
        a.storage.clear();
        for (slot, key) in [("13", "hot_word"), ("18", "cutoff_word")] {
            a.storage
                .insert(slot.into(), num_hex(h[key].as_str().unwrap()).to_string());
        }
        for t in h["transmissions"].as_array().unwrap() {
            a.storage.insert(
                num_hex(t["slot"].as_str().unwrap()).to_string(),
                num_hex(t["word"].as_str().unwrap()).to_string(),
            );
        }
        let secondary = h["secondary_round_data"].as_str().unwrap();
        let words: Vec<U256> = decode_hex(secondary)
            .unwrap()
            .chunks_exact(32)
            .map(U256::from_be_slice)
            .collect();
        let mut phased = words.clone();
        phased[0] |= U256::from(2) << 64usize;
        phased[4] |= U256::from(2) << 64usize;
        for (mode, call, expected) in [
            ("oracle", price_call(&q), encoded(&[words[1]])),
            (
                "proxy_round",
                read_call(&q, &weth_proxy(), "0xfeaf968c"),
                encoded(&phased),
            ),
            (
                "direct_round",
                read_call(&q, &observed_aggregator(), "0xfeaf968c"),
                h["direct_round_data"].as_str().unwrap().to_owned(),
            ),
        ] {
            let out = simulate(&s, &call).unwrap();
            assert_eq!(out.status, VmStatus::Success);
            assert_eq!(out.output, expected);
            assert_no_contract_changes(&out);
            assert!(!out.canonical_state_authenticated);
            if let Ok(path) = std::env::var("NQC_MINER_DUAL_OBSERVED_DIR") {
                export(
                    &std::path::Path::new(&path).join(format!("{index:03}-{mode}")),
                    &[
                        ("input.json", serde_json::json!({"snapshot":s,"call":call})),
                        ("output.json", serde_json::to_value(out).unwrap()),
                    ],
                );
            }
        }
    }
}
#[test]
fn cutoff_equality_keeps_secondary_and_only_strict_expiry_selects_primary() {
    for receive in [false, true] {
        let c = AccountCase::default();
        let reference = check_dual(&c, receive);
        let price = c.sizing.prelude.payment.underlying.transfer.price;
        for age in [59u32, 60, 61] {
            let (mut s, q) = dual_setup(&c, receive);
            let now = s.timestamp as u32;
            round(
                &mut s,
                99,
                if age > 60 { U256::from(17) } else { price },
                now - age,
            );
            round(
                &mut s,
                100,
                if age > 60 { price } else { U256::from(17) },
                now - 61,
            );
            assert_same_execution(&simulate(&s, &q).unwrap(), &reference);
        }
    }
}
#[test]
fn bounded_search_includes_twentieth_round_but_skips_twenty_first_and_handles_zero() {
    let (base, q) = dual_setup(&AccountCase::default(), true);
    let price = U256::from(12345);
    let now = base.timestamp as u32;
    for qualifying in [Some(100), Some(81), None] {
        let mut s = base.clone();
        hot(&mut s, 100, 7, false);
        round(&mut s, 7, price, now - 100);
        for n in 81..=100 {
            round(
                &mut s,
                n,
                if Some(n) == qualifying {
                    price
                } else {
                    U256::from(17)
                },
                if Some(n) == qualifying { now - 61 } else { now },
            );
        }
        // Round 80 has no witness; the declared twenty-iteration bound must skip it.
        read_price(&s, &q, price);
    }
    let mut s = base.clone();
    hot(&mut s, 0, 0, false);
    round(&mut s, 0, price, 0);
    read_price(&s, &q, price);
    hot(&mut s, 3, 0, false);
    for n in 1..=3 {
        round(&mut s, n, U256::from(17), now);
    }
    read_price(&s, &q, price);
}
#[test]
fn same_block_secondary_report_hides_latest_round_only_from_primary_caller() {
    let (mut s, q) = dual_setup(&AccountCase::default(), true);
    let now = s.timestamp as u32;
    hot(&mut s, 100, 100, true);
    round(&mut s, 100, U256::from(222), now);
    round(&mut s, 99, U256::from(111), now - 1);
    read_price(&s, &q, U256::from(222));
    let direct = read_call(&q, &observed_aggregator(), "0x50d25bcd");
    let out = simulate(&s, &direct).unwrap();
    assert_eq!(out.output, encoded(&[U256::from(111)]));
    assert_eq!(out.status, VmStatus::Success);
    assert_no_contract_changes(&out);
    let mut missing = s.clone();
    dual_account(&mut missing)
        .storage
        .remove(&dual_slot(99).to_string());
    assert!(simulate(&missing, &direct).is_err());
    s.timestamp += 1;
    let out = simulate(&s, &direct).unwrap();
    assert_eq!(out.output, encoded(&[U256::from(222)]));
    assert_eq!(out.status, VmStatus::Success);
    s.timestamp -= 1;
    hot(&mut s, 100, 100, false);
    let out = simulate(&s, &direct).unwrap();
    assert_eq!(out.output, encoded(&[U256::from(222)]));
}
#[test]
fn signed_int192_answers_extend_correctly_and_nonpositive_values_use_original_fallback() {
    let c = AccountCase::default();
    let price = c.sizing.prelude.payment.underlying.transfer.price;
    for receive in [false, true] {
        let reference = check_dual(&c, receive);
        for value in [
            U256::ZERO,
            U256::MAX,
            U256::MAX - ((U256::from(1) << 191usize) - U256::from(1)),
        ] {
            let (mut s, q) = dual_setup(&c, receive);
            let now = s.timestamp as u32;
            round(&mut s, 99, value, now - 1);
            add_fallback(&mut s, &c);
            assert_same_execution(&simulate(&s, &q).unwrap(), &reference);
            let direct = read_call(&q, &weth_proxy(), "0x50d25bcd");
            let out = simulate(&s, &direct).unwrap();
            assert_eq!(out.status, VmStatus::Success);
            assert_eq!(out.output, encoded(&[value]));
        }
    }
    let (mut s, q) = dual_setup(&c, true);
    let now = s.timestamp as u32;
    let max = (U256::from(1) << 191usize) - U256::from(1);
    round(&mut s, 99, max, now - 1);
    read_price(&s, &q, max);
    assert_ne!(price, max);
}
#[test]
fn missing_state_fails_closed_and_uint32_timestamp_overflow_reverts_atomically() {
    for receive in [false, true] {
        let (s, q) = dual_setup(&AccountCase::default(), receive);
        for slot in [U256::from(13), U256::from(18), dual_slot(99)] {
            let mut missing = s.clone();
            assert!(dual_account(&mut missing)
                .storage
                .remove(&slot.to_string())
                .is_some());
            assert!(simulate(&missing, &q).is_err());
        }
        let mut missing = s.clone();
        missing
            .accounts
            .retain(|a| a.address != observed_aggregator());
        assert!(simulate(&missing, &q).is_err());
        let mut overflow = s.clone();
        round(&mut overflow, 99, U256::from(1), u32::MAX);
        let out = simulate(&overflow, &q).unwrap();
        assert_eq!(out.status, VmStatus::Revert);
        assert_eq!(
            out.output,
            "0x4e487b71".to_owned() + &encoded(&[U256::from(0x11)])[2..]
        );
        assert_no_contract_changes(&out);
        let direct = read_call(&q, &observed_aggregator(), "0x50d25bcd");
        let mut minimal = s.clone();
        dual_account(&mut minimal).storage.remove("18");
        dual_account(&mut minimal)
            .storage
            .remove(&dual_slot(99).to_string());
        let out = simulate(&minimal, &direct).unwrap();
        assert_eq!(out.status, VmStatus::Success);
        assert_eq!(out.output, encoded(&[U256::from(17)]));
    }
}
#[test]
fn late_usdc_failure_and_proxy_access_denial_revert_the_whole_actual_price_chain() {
    for receive in [false, true] {
        let (mut s, q) = dual_setup(&AccountCase::default(), receive);
        add_controller(&mut s);
        s.accounts
            .iter_mut()
            .find(|a| a.address == CONTROLLER)
            .unwrap()
            .storage
            .insert("0".into(), "0".into());
        payment_revert(&s, &q, "No access");
        let (mut s, q) = dual_setup(&AccountCase::default(), receive);
        s.accounts
            .iter_mut()
            .find(|a| a.address == ASSET)
            .unwrap()
            .storage
            .insert("1".into(), (U256::from(1) << 160usize).to_string());
        payment_revert(&s, &q, "Pausable: paused");
    }
}
