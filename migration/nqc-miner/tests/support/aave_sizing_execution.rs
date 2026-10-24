//! Original close factor, collateral cap, fee and dust drive both delivery/payment modes.
//! Prices, aggregate account values, all state and Pool entry remain synthetic.
#[path = "aave_account_execution.rs"]
mod aave_account_execution;
use super::*;
use nqc_miner::aave_amounts::{calculate, AmountInput, Amounts};

#[derive(Clone, Debug)]
struct SizingCase {
    prelude: PreludeCase,
    debt_price: U256,
    total_debt: U256,
}
impl Default for SizingCase {
    fn default() -> Self {
        let mut p = PreludeCase::default();
        p.collateral.configuration |=
            (U256::from(10500) << 32usize) | (U256::from(1000) << 152usize);
        p.payment.underlying.transfer.price = U256::from(100_000_000_000u64);
        p.payment.underlying.transfer.total_base = U256::from(15_600_000_000_000u64);
        p.payment.wallet = U256::from(500);
        p.payment.allowance = U256::from(500);
        Self {
            prelude: p,
            debt_price: U256::from(100_000_000_000u64),
            total_debt: U256::from(16_600_000_000_000u64),
        }
    }
}
fn amount_input(c: &SizingCase) -> AmountInput {
    let p = &c.prelude;
    let d = project(&projection_input(p, true))
        .unwrap()
        .projected
        .unwrap();
    let a = project(&projection_input(p, false))
        .unwrap()
        .projected
        .unwrap();
    let field = |n: usize, mask: u64| (p.collateral.configuration >> n) & U256::from(mask);
    AmountInput {
        collateral_balance: a.user_collateral_balance,
        reserve_debt: d.user_variable_debt_balance,
        total_debt_base: c.total_debt.to_string(),
        health_factor_wad: p.health.to_string(),
        collateral_price: p.payment.underlying.transfer.price.to_string(),
        debt_price: c.debt_price.to_string(),
        collateral_decimals: field(48, 255).to::<u8>(),
        debt_decimals: ((p.debt.configuration >> 48usize) & U256::from(255)).to::<u8>(),
        liquidation_bonus_bps: field(32, 65535).to::<u16>(),
        liquidation_protocol_fee_bps: field(152, 65535).to::<u16>(),
        debt_to_cover: p.payment.underlying.transfer.debt.repayment.to_string(),
    }
}
fn sizing_setup(c: &SizingCase, receive: bool) -> (PinnedSnapshot, SandboxCall) {
    let (mut s, mut q) = prelude_setup(&c.prelude, receive);
    let f: Value =
        serde_json::from_str(include_str!("../../fixtures/aave_sizing_execution.json")).unwrap();
    let contract = &f["contracts"]["AaveSizingExecutionHarness"];
    let code = contract["runtime_code"].as_str().unwrap();
    let pool = s.accounts.iter_mut().find(|a| a.address == POOL).unwrap();
    pool.runtime_code = code.into();
    pool.code_hash = format!("{:#x}", keccak256(decode_hex(code).unwrap()));
    let old: Vec<U256> = q.calldata.as_bytes()[10..]
        .chunks(64)
        .map(|v| U256::from_str_radix(std::str::from_utf8(v).unwrap(), 16).unwrap())
        .collect();
    assert_eq!(old.len(), 33);
    let mut words = old[..7].to_vec();
    words.extend([old[9], c.debt_price, old[11], c.total_debt]);
    words.extend_from_slice(&old[12..]);
    let selectors = contract["selectors"].as_object().unwrap();
    assert_eq!(selectors.len(), 4); // Three original public constants also expose getters.
    let (signature, selector) = selectors
        .iter()
        .find(|(s, _)| s.starts_with("calculate("))
        .unwrap();
    assert_eq!(
        &hex(&keccak256(signature)[..4])[2..],
        selector.as_str().unwrap()
    );
    q.calldata = "0x".to_owned() + selector.as_str().unwrap() + &encoded(&words)[2..];
    (s, q)
}
fn amount_words(a: &Amounts) -> [U256; 6] {
    [
        &a.max_liquidatable_debt,
        &a.debt_to_liquidate,
        &a.collateral_to_liquidator,
        &a.protocol_fee_collateral,
        &a.reserve_debt_base,
        &a.reserve_collateral_base,
    ]
    .map(|s| num(s))
}
fn check_sizing(c: &SizingCase, receive: bool) -> SandboxOutcome {
    let input = amount_input(c);
    let amounts = calculate(&input).unwrap().amounts.unwrap();
    let mut p = c.prelude.clone();
    let t = &mut p.payment.underlying.transfer;
    t.debt.repayment = num(&amounts.debt_to_liquidate);
    t.amount = num(&amounts.collateral_to_liquidator);
    t.fee = num(&amounts.protocol_fee_collateral);
    t.unit = U256::from(10).pow(U256::from(input.collateral_decimals));
    let reference = check_prelude(&p, receive);
    let (s, q) = sizing_setup(c, receive);
    let out = simulate(&s, &q).unwrap();
    assert_eq!(
        out.status,
        VmStatus::Success,
        "{c:?} {receive} {}",
        out.output
    );
    assert_eq!(
        out.output,
        reference.output.clone() + &encoded(&amount_words(&amounts))[2..]
    );
    assert_eq!(out.logs, reference.logs);
    assert_eq!(storage_changes(&out), storage_changes(&reference));
    assert!(!out.canonical_state_authenticated);
    out
}
fn sizing_revert(c: &SizingCase, receive: bool, expected: &str) {
    let (s, q) = sizing_setup(c, receive);
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Revert, "{c:?}");
    assert_eq!(out.output, expected);
    assert_no_contract_changes(&out);
}
#[test]
fn computed_amounts_drive_both_delivery_payments_and_export_examples() {
    let c = SizingCase::default();
    for receive in [false, true] {
        let out = check_sizing(&c, receive);
        assert_eq!(
            &output_words(&out)[37..41],
            &[
                U256::from(166),
                U256::from(40),
                U256::from(41),
                U256::from(1)
            ]
        );
        if let Ok(path) = std::env::var("NQC_MINER_SIZING_EVIDENCE_DIR") {
            let dir =
                std::path::Path::new(&path).join(if receive { "atoken" } else { "underlying" });
            std::fs::create_dir_all(&dir).unwrap();
            let (snapshot, call) = sizing_setup(&c, receive);
            let input = amount_input(&c);
            let d = projection_input(&c.prelude, true);
            let a = projection_input(&c.prelude, false);
            for (name, value) in [
                (
                    "input.json",
                    serde_json::json!({"snapshot":snapshot,"call":call}),
                ),
                ("output.json", serde_json::to_value(out).unwrap()),
                (
                    "models.json",
                    serde_json::json!({"amount_input":input,"amount_expected":calculate(&input).unwrap(),
                    "debt_input":d,"debt_expected":project(&d).unwrap(),
                    "collateral_input":a,"collateral_expected":project(&a).unwrap()}),
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
fn seeded_bonus_fees_prices_indices_and_close_factor_match_complete_state_and_logs() {
    let mut rng = ChaCha8Rng::seed_from_u64(0x00a0_0026_2026);
    for n in 0..48 {
        let mut c = SizingCase::default();
        c.prelude.collateral.configuration &=
            !((U256::from(65535) << 32usize) | (U256::from(65535) << 152usize));
        c.prelude.collateral.configuration |= (U256::from(rng.gen_range(10000u64..=12000))
            << 32usize)
            | (U256::from(rng.gen_range(0u64..=10000)) << 152usize);
        c.prelude.debt.borrow_rate = U256::from(rng.gen_range(0..RAY / 5));
        c.prelude.collateral.liquidity_rate = U256::from(rng.gen_range(0..RAY / 5));
        c.prelude.payment.underlying.transfer.debt.repayment =
            U256::from(rng.gen_range(10u64..=100));
        c.debt_price *= U256::from(rng.gen_range(1u64..=3));
        if n % 2 == 0 {
            c.prelude.health = U256::from(970_000_000_000_000_000u64);
        }
        if n % 3 == 0 {
            c.prelude.payment.underlying.transfer.recipient = TREASURY;
        }
        if n % 4 == 0 {
            c.prelude
                .payment
                .underlying
                .transfer
                .rewards
                .rewards
                .clear();
        }
        for receive in [false, true] {
            check_sizing(&c, receive);
        }
    }
}
#[test]
fn close_factor_health_boundary_total_debt_and_request_caps_affect_actual_payment() {
    for health in [950_000_000_000_000_000u64, 950_000_000_000_000_001] {
        for total in [16_600_000_000_000u64, 40_000_000_000_000] {
            let mut c = SizingCase {
                total_debt: U256::from(total),
                ..SizingCase::default()
            };
            c.prelude.health = U256::from(health);
            c.prelude.payment.underlying.transfer.debt.repayment = U256::MAX;
            let expected_max = if health > 950_000_000_000_000_000 && total == 16_600_000_000_000 {
                83
            } else {
                166
            };
            for receive in [false, true] {
                let out = check_sizing(&c, receive);
                assert_eq!(output_words(&out)[37], U256::from(expected_max));
            }
        }
    }
}
#[test]
fn exact_dust_boundary_accepts_then_rejects_and_restores_initial_accrual() {
    let mut c = SizingCase {
        debt_price: U256::from(10_000_000_000u64),
        ..SizingCase::default()
    };
    c.prelude.payment.underlying.transfer.price = c.debt_price;
    c.prelude.collateral.configuration &=
        !((U256::from(65535) << 32usize) | (U256::from(65535) << 152usize));
    c.prelude.collateral.configuration |= U256::from(10000) << 32usize;
    for start in [&mut c.prelude.debt, &mut c.prelude.collateral] {
        start.last = 31_537_000;
        start.liquidity = U256::from(RAY);
        start.borrow = U256::from(RAY);
    }
    c.prelude.payment.underlying.transfer.debt.repayment = U256::from(90);
    for receive in [false, true] {
        check_sizing(&c, receive);
    }
    c.prelude.payment.underlying.transfer.debt.repayment = U256::from(91);
    let error = calculate(&amount_input(&c)).unwrap().revert_data.unwrap();
    assert_eq!(error, hex(&keccak256("MustNotLeaveDust()")[..4]));
    for receive in [false, true] {
        sizing_revert(&c, receive, &error);
    }
    let mut c = SizingCase {
        debt_price: U256::from(100_000_000),
        ..SizingCase::default()
    };
    c.prelude.payment.underlying.transfer.price = c.debt_price;
    for receive in [false, true] {
        sizing_revert(&c, receive, &error);
    }
}
#[test]
fn collateral_exhaustion_and_reserve_decimals_compute_repayment_and_fee() {
    let mut c = SizingCase::default();
    c.prelude.payment.underlying.transfer.balances[0] = U256::from(10);
    c.prelude.payment.underlying.transfer.debt.repayment = U256::MAX;
    for receive in [false, true] {
        let out = check_sizing(&c, receive);
        assert_eq!(output_words(&out)[18], U256::ZERO);
    }
    c.prelude.payment.underlying.transfer.total_base = U256::from(1_500_000_000_000u64);
    for receive in [false, true] {
        let out = check_sizing(&c, receive);
        assert_eq!(output_words(&out)[18], U256::from(1));
        assert!(output_words(&out)[38] < output_words(&out)[33]);
    }
    let mut c = SizingCase::default();
    c.prelude.debt.configuration |= U256::from(6) << 48usize;
    c.prelude.collateral.configuration |= U256::from(18) << 48usize;
    c.debt_price *= U256::from(10).pow(U256::from(6));
    c.prelude.payment.underlying.transfer.price *= U256::from(10).pow(U256::from(18));
    for receive in [false, true] {
        check_sizing(&c, receive);
    }
}
#[test]
fn arithmetic_errors_are_exact_and_initial_validation_precedes_sizing() {
    let mut cases = vec![SizingCase::default(); 4];
    cases[0].prelude.payment.underlying.transfer.price = U256::ZERO;
    cases[1].debt_price = U256::MAX;
    cases[2].prelude.collateral.configuration |= U256::from(78) << 48usize;
    cases[3].prelude.payment.underlying.transfer.price = U256::MAX;
    for c in cases {
        let error = calculate(&amount_input(&c)).unwrap().revert_data.unwrap();
        for receive in [false, true] {
            sizing_revert(&c, receive, &error);
        }
    }
    let mut c = SizingCase::default();
    c.prelude.health = U256::from(1_000_000_000_000_000_000u64);
    c.prelude.payment.underlying.transfer.price = U256::ZERO;
    for receive in [false, true] {
        sizing_revert(
            &c,
            receive,
            &hex(&keccak256("HealthFactorNotBelowThreshold()")[..4]),
        );
    }
}
#[test]
fn late_payment_failure_and_missing_witnesses_cannot_leave_computed_liquidation_effects() {
    for receive in [false, true] {
        let (s, q) = sizing_setup(&SizingCase::default(), receive);
        let mut paused = s.clone();
        paused
            .accounts
            .iter_mut()
            .find(|a| a.address == ASSET)
            .unwrap()
            .storage
            .insert("1".into(), (U256::from(1) << 160usize).to_string());
        payment_revert(&paused, &q, "Pausable: paused");
        for address in [WETH_DEBT, ASSET, REWARDS] {
            let mut missing = s.clone();
            missing.accounts.retain(|a| a.address != address);
            assert!(simulate(&missing, &q).is_err());
        }
    }
}
