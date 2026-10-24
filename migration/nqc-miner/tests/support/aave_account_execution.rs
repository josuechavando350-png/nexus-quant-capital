//! Original GenericLogic over two observed token paths and an explicit synthetic oracle.
use super::*;
const ORACLE: &str = "0x5555555555555555555555555555555555555555";
#[derive(Clone, Debug)]
struct AccountCase {
    sizing: SizingCase,
    category: u8,
    mode: [U256; 6],
}
impl Default for AccountCase {
    fn default() -> Self {
        let mut sizing = SizingCase::default();
        sizing.prelude.payment.underlying.transfer.debt.config = U256::from(36);
        sizing.prelude.collateral.configuration |= U256::from(7500) | (U256::from(8000) << 16usize);
        Self {
            sizing,
            category: 0,
            mode: [U256::ZERO; 6],
        }
    }
}
fn account_fixture() -> Value {
    serde_json::from_str(include_str!("../../fixtures/aave_account_execution.json")).unwrap()
}
fn account_setup(c: &AccountCase, receive: bool) -> (PinnedSnapshot, SandboxCall) {
    let (mut s, mut q) = sizing_setup(&c.sizing, receive);
    let f = account_fixture();
    let contract = &f["contracts"]["AaveAccountExecutionHarness"];
    let pool = s.accounts.iter_mut().find(|a| a.address == POOL).unwrap();
    pool.runtime_code = contract["runtime_code"].as_str().unwrap().into();
    pool.code_hash = format!("{:#x}", keccak256(decode_hex(&pool.runtime_code).unwrap()));
    for address in [ASSET, COLLATERAL] {
        let base = mapping(address, 21);
        for offset in 0..10 {
            pool.storage
                .insert((base + U256::from(offset)).to_string(), "0".into());
        }
    }
    for id in 0..128 {
        pool.storage.insert(
            map_word(U256::from(id), U256::from(22)).to_string(),
            "0".into(),
        );
    }
    let base = map_word(U256::from(c.category), U256::from(23));
    for offset in 0..3 {
        pool.storage
            .insert((base + U256::from(offset)).to_string(), "0".into());
    }
    let old: Vec<U256> = q.calldata.as_bytes()[10..]
        .chunks(64)
        .map(|v| U256::from_str_radix(std::str::from_utf8(v).unwrap(), 16).unwrap())
        .collect();
    assert_eq!(old.len(), 32);
    let mut words = old[..7].to_vec();
    words.extend_from_slice(&old[11..31]);
    words.push(U256::from(c.category));
    words.extend(c.mode);
    let (signature, selector) = contract["selectors"]
        .as_object()
        .unwrap()
        .iter()
        .find(|(s, _)| s.starts_with("calculate("))
        .unwrap();
    assert_eq!(
        &hex(&keccak256(signature)[..4])[2..],
        selector.as_str().unwrap()
    );
    q.calldata = "0x".to_owned() + selector.as_str().unwrap() + &encoded(&words)[2..];
    let mut oracle = account(
        ORACLE,
        f["contracts"]["SyntheticAccountOracle"]["runtime_code"]
            .as_str()
            .unwrap(),
    );
    oracle.storage.insert("1".into(), "0".into());
    oracle.storage.insert(
        mapping(ASSET, 0).to_string(),
        c.sizing.debt_price.to_string(),
    );
    oracle.storage.insert(
        mapping(COLLATERAL, 0).to_string(),
        c.sizing
            .prelude
            .payment
            .underlying
            .transfer
            .price
            .to_string(),
    );
    s.accounts.push(oracle);
    (s, q)
}
// Independent integer expectation for the supported USDC-borrow / WETH-collateral flags.
// Other set bits explicitly point to list gaps; reverse-role token state is not invented.
fn account_model(c: &AccountCase) -> [U256; 4] {
    let p = &c.sizing.prelude;
    let t = &p.payment.underlying.transfer;
    let a = project(&projection_input(p, false))
        .unwrap()
        .projected
        .unwrap();
    let d = project(&projection_input(p, true))
        .unwrap()
        .projected
        .unwrap();
    let mask = U256::from(65535);
    let unit = |cfg: U256| U256::from(10).pow((cfg >> 48usize) & U256::from(255));
    let coll =
        if (t.debt.config >> (2 * usize::from(t.reserve_id) + 1)) & U256::from(1) != U256::ZERO {
            num(&a.user_collateral_balance) * t.price / unit(p.collateral.configuration)
        } else {
            U256::ZERO
        };
    let debt =
        if (t.debt.config >> (2 * usize::from(t.debt.reserve_id))) & U256::from(1) != U256::ZERO {
            let product = num(&d.user_variable_debt_balance) * c.sizing.debt_price;
            let divisor = unit(p.debt.configuration);
            product / divisor + U256::from(product % divisor != U256::ZERO)
        } else {
            U256::ZERO
        };
    let enabled =
        c.category != 0 && (c.mode[3] >> usize::from(t.reserve_id)) & U256::from(1) != U256::ZERO;
    let threshold = if enabled {
        c.mode[1]
    } else {
        (p.collateral.configuration >> 16usize) & mask
    };
    let bonus = if enabled {
        c.mode[2]
    } else {
        (p.collateral.configuration >> 32usize) & mask
    };
    let health = if debt == U256::ZERO {
        U256::MAX
    } else {
        ((coll * threshold * U256::from(1_000_000_000_000_000_000u64) + debt / U256::from(2))
            / debt)
            / U256::from(10000)
    };
    [health, coll, debt, bonus]
}
fn account_reference(c: &AccountCase) -> (PreludeCase, Amounts, AmountInput) {
    let [health, coll, debt, bonus] = account_model(c);
    let mut sizing = c.sizing.clone();
    sizing.prelude.health = health;
    sizing.prelude.payment.underlying.transfer.total_base = coll;
    sizing.total_debt = debt;
    let mut input = amount_input(&sizing);
    input.liquidation_bonus_bps = bonus.to::<u16>();
    let a = calculate(&input).unwrap().amounts.unwrap();
    let mut p = sizing.prelude;
    p.payment.underlying.transfer.debt.repayment = num(&a.debt_to_liquidate);
    p.payment.underlying.transfer.amount = num(&a.collateral_to_liquidator);
    p.payment.underlying.transfer.fee = num(&a.protocol_fee_collateral);
    p.payment.underlying.transfer.unit = U256::from(10).pow(U256::from(input.collateral_decimals));
    (p, a, input)
}
fn account_copy_slots(c: &AccountCase) -> BTreeMap<String, String> {
    let p = &c.sizing.prelude;
    let mut slots = BTreeMap::new();
    let mut put = |slot: U256, value: U256| {
        if value != U256::ZERO {
            slots.insert(slot.to_string(), value.to_string());
        }
    };
    for (debt, asset, token, vault) in [
        (true, ASSET, TOKEN, DEBT_VAULT),
        (
            false,
            COLLATERAL,
            WETH_DEBT,
            p.payment.underlying.transfer.token,
        ),
    ] {
        let start = if debt { &p.debt } else { &p.collateral };
        let r = project(&projection_input(p, debt))
            .unwrap()
            .projected
            .unwrap();
        let id = if debt {
            p.payment.underlying.transfer.debt.reserve_id
        } else {
            p.payment.underlying.transfer.reserve_id
        };
        let deficit = if debt {
            p.payment.underlying.transfer.debt.deficit
        } else {
            p.payment.underlying.deficit
        };
        let virtual_balance = if debt {
            p.payment.underlying.transfer.debt.virtual_balance
        } else {
            p.payment.underlying.virtual_balance
        };
        let base = mapping(asset, 21);
        for (offset, value) in [
            (0, start.configuration),
            (
                1,
                num(&r.liquidity_index_ray) | (start.liquidity_rate << 128usize),
            ),
            (
                2,
                num(&r.variable_borrow_index_ray) | (start.borrow_rate << 128usize),
            ),
            (
                3,
                deficit
                    | (U256::from(r.last_update_timestamp) << 128usize)
                    | (U256::from(id) << 168usize)
                    | (U256::from(start.grace) << 184usize),
            ),
            (4, addr(vault)),
            (6, addr(token)),
            (
                8,
                num(&r.accrued_to_treasury_scaled) | (virtual_balance << 128usize),
            ),
        ] {
            put(base + U256::from(offset), value);
        }
        put(map_word(U256::from(id), U256::from(22)), addr(asset));
    }
    let base = map_word(U256::from(c.category), U256::from(23));
    put(
        base,
        c.mode[0]
            | (c.mode[1] << 16usize)
            | (c.mode[2] << 32usize)
            | (c.mode[3] << 48usize)
            | (c.mode[4] << 176usize),
    );
    put(base + U256::from(2), c.mode[5] << 128usize);
    slots
}
fn check_account(c: &AccountCase, receive: bool) -> SandboxOutcome {
    let (p, amounts, _) = account_reference(c);
    let reference = check_prelude(&p, receive);
    let (s, q) = account_setup(c, receive);
    let out = simulate(&s, &q).unwrap();
    assert_eq!(
        out.status,
        VmStatus::Success,
        "{c:?} {receive} {}",
        out.output
    );
    assert_eq!(
        out.output,
        reference.output.clone()
            + &encoded(&amount_words(&amounts))[2..]
            + &encoded(&account_model(c))[2..]
    );
    assert_eq!(out.logs, reference.logs);
    let mut expected = storage_changes(&reference);
    expected
        .get_mut(POOL)
        .unwrap()
        .extend(account_copy_slots(c));
    assert_eq!(storage_changes(&out), expected);
    assert!(!out.canonical_state_authenticated);
    out
}
fn account_revert(c: &AccountCase, receive: bool, expected: &str) {
    let (s, q) = account_setup(c, receive);
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Revert);
    assert_eq!(out.output, expected);
    assert_no_contract_changes(&out);
}
#[test]
fn original_account_health_and_prices_drive_both_payments_and_export_examples() {
    let c = AccountCase::default();
    for receive in [false, true] {
        let out = check_account(&c, receive);
        if let Ok(path) = std::env::var("NQC_MINER_ACCOUNT_EVIDENCE_DIR") {
            let dir =
                std::path::Path::new(&path).join(if receive { "atoken" } else { "underlying" });
            std::fs::create_dir_all(&dir).unwrap();
            let (snapshot, call) = account_setup(&c, receive);
            let (_, _, input) = account_reference(&c);
            for (name, value) in [
                (
                    "input.json",
                    serde_json::json!({"snapshot":snapshot,"call":call}),
                ),
                ("output.json", serde_json::to_value(out).unwrap()),
                (
                    "models.json",
                    serde_json::json!({"account_expected":account_model(&c).map(|v|v.to_string()),
                    "amount_input":input,"amount_expected":calculate(&input).unwrap(),
                    "debt_input":projection_input(&c.sizing.prelude,true),"collateral_input":projection_input(&c.sizing.prelude,false)}),
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
fn seeded_thresholds_prices_indices_and_emode_select_actual_health_bonus_and_payment() {
    let mut rng = ChaCha8Rng::seed_from_u64(0x00ac_c026_2026);
    for n in 0..32 {
        let mut c = AccountCase::default();
        let cfg = &mut c.sizing.prelude.collateral.configuration;
        *cfg = (*cfg & !(U256::from(65535) << 16usize))
            | (U256::from(rng.gen_range(6500u64..=9000)) << 16usize);
        c.sizing.prelude.debt.borrow_rate = U256::from(rng.gen_range(0..RAY / 5));
        c.sizing.prelude.collateral.liquidity_rate = U256::from(rng.gen_range(0..RAY / 12));
        c.sizing.debt_price *= U256::from(rng.gen_range(1u64..=2));
        if n % 2 == 0 {
            c.category = 1;
            c.mode = [
                U256::from(7500),
                U256::from(8500),
                U256::from(11000),
                U256::from(4),
                U256::from(n % 4 == 0),
                U256::from(if n % 3 == 0 { 4 } else { 0 }),
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
            check_account(&c, receive);
        }
    }
}
#[test]
fn computed_health_at_one_rejects_and_one_base_step_below_succeeds() {
    let mut c = AccountCase::default();
    for start in [&mut c.sizing.prelude.debt, &mut c.sizing.prelude.collateral] {
        start.borrow = U256::from(RAY);
        start.liquidity = U256::from(RAY);
        start.last = 31_537_000;
    }
    c.sizing.debt_price = U256::from(80_000_000_000u64);
    assert_eq!(
        account_model(&c)[0],
        U256::from(1_000_000_000_000_000_000u64)
    );
    for receive in [false, true] {
        account_revert(
            &c,
            receive,
            &hex(&keccak256("HealthFactorNotBelowThreshold()")[..4]),
        );
    }
    c.sizing.debt_price += U256::from(1);
    for receive in [false, true] {
        check_account(&c, receive);
    }
}
#[test]
fn emode_bitmap_selects_threshold_bonus_and_can_flip_initial_eligibility() {
    assert_eq!(
        map_word(U256::from(7), U256::from(23)),
        num("113479202300186194305725673295787536031689033807992212058168757665848295403366")
    );
    let mut c = AccountCase {
        category: 7,
        mode: [
            U256::from(9000),
            U256::from(11000),
            U256::from(12000),
            U256::from(4),
            U256::ZERO,
            U256::ZERO,
        ],
        ..AccountCase::default()
    };
    for receive in [false, true] {
        account_revert(
            &c,
            receive,
            &hex(&keccak256("HealthFactorNotBelowThreshold()")[..4]),
        );
    }
    c.mode[3] = U256::ZERO;
    c.mode[4] = U256::from(1);
    for receive in [false, true] {
        check_account(&c, receive);
    }
    c.mode[3] = U256::from(4);
    c.mode[1] = U256::from(9000);
    for receive in [false, true] {
        let out = check_account(&c, receive);
        assert_eq!(output_words(&out)[46], U256::from(12000));
    }
}
#[test]
fn oracle_failure_precedes_validation_but_reserve_failure_precedes_oracle() {
    for receive in [false, true] {
        let mut c = AccountCase::default();
        c.sizing.prelude.payment.underlying.transfer.recipient = USER;
        let (mut s, q) = account_setup(&c, receive);
        s.accounts
            .iter_mut()
            .find(|a| a.address == ORACLE)
            .unwrap()
            .storage
            .insert("1".into(), "1".into());
        let out = simulate(&s, &q).unwrap();
        assert_eq!(out.status, VmStatus::Revert);
        assert_eq!(out.output, abi_string_error("synthetic oracle blocked"));
        assert_no_contract_changes(&out);
        c.sizing.prelude.debt.last = 31_537_001;
        let error = project(&projection_input(&c.sizing.prelude, true))
            .unwrap()
            .revert_data
            .unwrap();
        let (mut s, q) = account_setup(&c, receive);
        s.accounts.retain(|a| a.address != ORACLE);
        let out = simulate(&s, &q).unwrap();
        assert_eq!(out.output, error);
        assert_no_contract_changes(&out);
    }
}
#[test]
fn empty_and_gap_flags_and_zero_debt_price_use_original_no_debt_health_rule() {
    for bits in [U256::ZERO, U256::from(1) << 254usize, U256::from(32)] {
        let mut c = AccountCase::default();
        c.sizing.prelude.payment.underlying.transfer.debt.config = bits;
        for receive in [false, true] {
            account_revert(
                &c,
                receive,
                &hex(&keccak256("HealthFactorNotBelowThreshold()")[..4]),
            );
        }
    }
    let mut c = AccountCase::default();
    c.sizing.debt_price = U256::ZERO;
    for receive in [false, true] {
        account_revert(
            &c,
            receive,
            &hex(&keccak256("HealthFactorNotBelowThreshold()")[..4]),
        );
    }
    let mut c = AccountCase::default();
    c.sizing.prelude.payment.underlying.transfer.debt.config |= U256::from(1) << 254usize;
    for receive in [false, true] {
        check_account(&c, receive);
    }
}
#[test]
fn missing_oracle_price_list_and_token_witnesses_fail_closed_and_late_payment_rolls_back_copies() {
    for receive in [false, true] {
        let (s, q) = account_setup(&AccountCase::default(), receive);
        for (address, slot) in [
            (ORACLE, mapping(ASSET, 0)),
            (ORACLE, mapping(COLLATERAL, 0)),
            (TOKEN, mapping(USER, 56)),
            (POOL, map_word(U256::from(1), U256::from(22))),
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
        let mut paused = s;
        paused
            .accounts
            .iter_mut()
            .find(|a| a.address == ASSET)
            .unwrap()
            .storage
            .insert("1".into(), (U256::from(1) << 160usize).to_string());
        payment_revert(&paused, &q, "Pausable: paused");
    }
}
#[test]
fn account_overflow_zero_collateral_price_and_malformed_oracle_revert_atomically() {
    let panic = |code: u64| format!("0x4e487b71{code:064x}");
    for (price, error) in [(U256::MAX, panic(0x11)), (U256::ZERO, panic(0x12))] {
        let mut c = AccountCase::default();
        c.sizing.prelude.payment.underlying.transfer.price = price;
        for receive in [false, true] {
            account_revert(&c, receive, &error);
        }
    }
    for receive in [false, true] {
        let (mut s, q) = account_setup(&AccountCase::default(), receive);
        let oracle = s.accounts.iter_mut().find(|a| a.address == ORACLE).unwrap();
        oracle.runtime_code = "0x60006000f3".into();
        oracle.code_hash = format!(
            "{:#x}",
            keccak256(decode_hex(&oracle.runtime_code).unwrap())
        );
        let out = simulate(&s, &q).unwrap();
        assert_eq!(out.status, VmStatus::Revert);
        assert_eq!(out.output, "0x");
        assert_no_contract_changes(&out);
    }
}
#[test]
fn former_supplied_health_and_aggregate_values_have_no_effect_on_new_abi() {
    let mut c = AccountCase::default();
    c.sizing.prelude.health = U256::MAX;
    c.sizing.total_debt = U256::MAX;
    c.sizing.prelude.payment.underlying.transfer.total_base = U256::MAX;
    for receive in [false, true] {
        let expected = check_account(&AccountCase::default(), receive);
        let out = check_account(&c, receive);
        assert_eq!(out, expected);
    }
}
