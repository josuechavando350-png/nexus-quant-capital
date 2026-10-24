//! Initial reserve cache/update and validation before both original delivery paths.
//! Health and amounts are supplied; state and Pool entry remain synthetic.
use super::*;
use nqc_miner::aave_reserve::{project, ProjectedReserve, ReserveInput};
use nqc_miner::aave_validation::{validate, ValidationInput};
const WETH_DEBT: &str = "0xea51d7853eefb32b6ee06b1c12e6dcca88be0ffe";
#[derive(Clone, Debug)]
struct Start {
    liquidity: U256,
    borrow: U256,
    liquidity_rate: U256,
    borrow_rate: U256,
    accrued: U256,
    last: u64,
    configuration: U256,
    grace: u64,
}
impl Start {
    fn words(&self) -> [U256; 8] {
        [
            self.liquidity,
            self.borrow,
            self.liquidity_rate,
            self.borrow_rate,
            self.accrued,
            U256::from(self.last),
            self.configuration,
            U256::from(self.grace),
        ]
    }
}
#[derive(Clone, Debug)]
struct PreludeCase {
    payment: PaymentCase,
    debt: Start,
    collateral: Start,
    health: U256,
}
impl Default for PreludeCase {
    fn default() -> Self {
        let mut payment = PaymentCase::default();
        payment.underlying.transfer.rewards.now = 31_537_000;
        let debt = Start {
            liquidity: U256::from(11 * RAY / 10),
            borrow: U256::from(3 * RAY / 2),
            liquidity_rate: U256::from(RAY / 20),
            borrow_rate: U256::from(RAY / 10),
            accrued: U256::from(7),
            last: 1000,
            configuration: (U256::from(1) << 56usize) | (U256::from(1000) << 64usize),
            grace: 0,
        };
        let collateral = Start {
            liquidity: U256::from(3 * RAY / 2),
            borrow: U256::from(12 * RAY / 10),
            liquidity_rate: U256::from(RAY / 25),
            borrow_rate: U256::from(RAY / 12),
            accrued: U256::from(11),
            ..debt.clone()
        };
        Self {
            payment,
            debt,
            collateral,
            health: U256::from(900_000_000_000_000_000u64),
        }
    }
}
fn prelude_fixture() -> Value {
    serde_json::from_str(include_str!("../../fixtures/aave_prelude_execution.json")).unwrap()
}
fn projection_input(c: &PreludeCase, debt: bool) -> ReserveInput {
    let t = &c.payment.underlying.transfer;
    let start = if debt { &c.debt } else { &c.collateral };
    ReserveInput {
        liquidity_index_ray: start.liquidity.to_string(),
        variable_borrow_index_ray: start.borrow.to_string(),
        liquidity_rate_ray: start.liquidity_rate.to_string(),
        variable_borrow_rate_ray: start.borrow_rate.to_string(),
        accrued_to_treasury_scaled: start.accrued.to_string(),
        last_update_timestamp: start.last,
        reserve_factor_bps: ((start.configuration >> 64usize) & U256::from(65535)).to::<u16>(),
        total_scaled_variable_debt: if debt {
            t.debt.total
        } else {
            c.payment.underlying.scaled_debt
        }
        .to_string(),
        user_scaled_collateral: if debt { U256::ZERO } else { t.balances[0] }.to_string(),
        user_scaled_variable_debt: if debt { t.debt.balance } else { U256::ZERO }.to_string(),
        timestamp: t.rewards.now,
    }
}
fn conditions(c: &PreludeCase, selected: U256) -> ValidationInput {
    let t = &c.payment.underlying.transfer;
    ValidationInput {
        borrower: USER.into(),
        liquidator: t.recipient.into(),
        collateral_configuration: c.collateral.configuration.to_string(),
        debt_configuration: c.debt.configuration.to_string(),
        collateral_grace_until: c.collateral.grace,
        debt_grace_until: c.debt.grace,
        collateral_reserve_id: t.reserve_id,
        user_configuration: t.debt.config.to_string(),
        health_factor_wad: c.health.to_string(),
        selected_debt: selected.to_string(),
        timestamp: t.rewards.now,
    }
}
fn prelude_setup(c: &PreludeCase, receive: bool) -> (PinnedSnapshot, SandboxCall) {
    let (mut s, mut q) = delivery_setup(&c.payment, receive);
    let f = prelude_fixture();
    let contract = &f["contracts"]["AavePreludeExecutionHarness"];
    let code = contract["runtime_code"].as_str().unwrap();
    let pool = s.accounts.iter_mut().find(|a| a.address == POOL).unwrap();
    pool.runtime_code = code.into();
    pool.code_hash = format!("{:#x}", keccak256(decode_hex(code).unwrap()));
    let t = &c.payment.underlying.transfer;
    let u = &c.payment.underlying;
    let d = &t.debt;
    let mut words = vec![
        d.repayment,
        d.deficit,
        d.virtual_balance,
        U256::from(d.reserve_id),
        d.config,
        addr(t.token),
        addr(t.recipient),
        t.amount,
        t.fee,
        t.price,
        t.unit,
        t.total_base,
        U256::from(t.reserve_id),
        u.virtual_balance,
        u.deficit,
        U256::from(receive),
    ];
    words.extend(c.debt.words());
    words.extend(c.collateral.words());
    words.push(c.health);
    let selectors = contract["selectors"].as_object().unwrap();
    assert_eq!(selectors.len(), 1);
    let (signature, selector) = selectors.iter().next().unwrap();
    assert_eq!(
        &hex(&keccak256(signature)[..4])[2..],
        selector.as_str().unwrap()
    );
    q.calldata = "0x".to_owned() + selector.as_str().unwrap() + &encoded(&words)[2..];
    let mut token = account(
        WETH_DEBT,
        f["contracts"]["AuditedDebtProxy"]["runtime_code"]
            .as_str()
            .unwrap(),
    );
    token
        .storage
        .insert(implementation_slot().to_string(), addr(IMPL).to_string());
    token.storage.insert("58".into(), u.scaled_debt.to_string());
    s.accounts.push(token);
    (s, q)
}
fn num(s: &str) -> U256 {
    s.parse().unwrap()
}
fn output_words(out: &SandboxOutcome) -> Vec<U256> {
    out.output.as_bytes()[2..]
        .chunks(64)
        .map(|s| U256::from_str_radix(std::str::from_utf8(s).unwrap(), 16).unwrap())
        .collect()
}
fn normalize(c: &PreludeCase, d: &ProjectedReserve, a: &ProjectedReserve) -> PaymentCase {
    let mut p = c.payment.clone();
    p.underlying.transfer.debt.debt = num(&d.user_variable_debt_balance);
    p.underlying.transfer.debt.index = num(&d.variable_borrow_index_ray);
    p.underlying.transfer.debt.cached = p.underlying.transfer.debt.total;
    p.underlying.transfer.debt.factor = U256::from(projection_input(c, true).reserve_factor_bps);
    p.underlying.transfer.index = num(&a.liquidity_index_ray);
    p.underlying.borrow_index = num(&a.variable_borrow_index_ray);
    p.underlying.factor = U256::from(projection_input(c, false).reserve_factor_bps);
    p
}
fn check_prelude(c: &PreludeCase, receive: bool) -> SandboxOutcome {
    let d = project(&projection_input(c, true))
        .unwrap()
        .projected
        .unwrap();
    let a = project(&projection_input(c, false))
        .unwrap()
        .projected
        .unwrap();
    assert!(
        validate(&conditions(c, num(&d.user_variable_debt_balance)))
            .unwrap()
            .initial_conditions_passed
    );
    let p = normalize(c, &d, &a);
    let reference = check_delivery(&p, receive);
    let (s, q) = prelude_setup(c, receive);
    let out = simulate(&s, &q).unwrap();
    assert_eq!(
        out.status,
        VmStatus::Success,
        "{c:?} {receive} {}",
        out.output
    );
    let mut words = output_words(&reference);
    if receive {
        words[20] = c.collateral.liquidity_rate;
        words[21] = c.collateral.borrow_rate;
    }
    let mut expected = storage_changes(&reference);
    let pool = expected.get_mut(POOL).unwrap();
    for (slot, value) in [
        (0, c.debt.configuration),
        (1, num(&d.liquidity_index_ray) | (words[5] << 128usize)),
        (
            2,
            num(&d.variable_borrow_index_ray) | (words[6] << 128usize),
        ),
        (
            3,
            words[2]
                | (U256::from(d.last_update_timestamp) << 128usize)
                | (U256::from(p.underlying.transfer.debt.reserve_id) << 168usize)
                | (U256::from(c.debt.grace) << 184usize),
        ),
        (4, addr(DEBT_VAULT)),
        (6, addr(TOKEN)),
        (
            8,
            num(&d.accrued_to_treasury_scaled) | (words[4] << 128usize),
        ),
        (11, c.collateral.configuration),
        (12, num(&a.liquidity_index_ray) | (words[20] << 128usize)),
        (
            13,
            num(&a.variable_borrow_index_ray) | (words[21] << 128usize),
        ),
        (
            14,
            p.underlying.deficit
                | (U256::from(a.last_update_timestamp) << 128usize)
                | (U256::from(p.underlying.transfer.reserve_id) << 168usize)
                | (U256::from(c.collateral.grace) << 184usize),
        ),
        (15, addr(p.underlying.transfer.token)),
        (17, addr(WETH_DEBT)),
        (
            19,
            num(&a.accrued_to_treasury_scaled) | (words[19] << 128usize),
        ),
    ] {
        if value == U256::ZERO {
            pool.remove(&slot.to_string());
        } else {
            pool.insert(slot.to_string(), value.to_string());
        }
    }
    assert_eq!(storage_changes(&out), expected, "complete state {receive}");
    let mut logs = reference.logs;
    let topic = format!(
        "{:#x}",
        keccak256("ReserveDataUpdated(address,uint256,uint256,uint256,uint256,uint256)")
    );
    let log = logs
        .iter_mut()
        .find(|l| {
            l.address == POOL && l.topics[0] == topic && l.topics[1] == encoded(&[addr(ASSET)])
        })
        .unwrap();
    log.data = log.data[..2 + 3 * 64].to_owned()
        + &encoded(&[num(&d.liquidity_index_ray)])[2..]
        + &log.data[2 + 4 * 64..];
    assert_eq!(out.logs, logs);
    words.extend([
        num(&d.liquidity_index_ray),
        num(&d.variable_borrow_index_ray),
        num(&d.accrued_to_treasury_scaled),
        U256::from(d.last_update_timestamp),
        num(&a.liquidity_index_ray),
        num(&a.variable_borrow_index_ray),
        num(&a.accrued_to_treasury_scaled),
        U256::from(a.last_update_timestamp),
        num(&d.user_variable_debt_balance),
        num(&a.user_collateral_balance),
        p.underlying.transfer.debt.total,
        p.underlying.scaled_debt,
    ]);
    assert_eq!(out.output, encoded(&words));
    assert!(!out.canonical_state_authenticated);
    out
}
#[test]
fn actual_token_caches_updated_indices_validation_and_both_payments_export_examples() {
    let c = PreludeCase::default();
    for receive in [false, true] {
        let out = check_prelude(&c, receive);
        if let Ok(path) = std::env::var("NQC_MINER_PRELUDE_EVIDENCE_DIR") {
            let dir =
                std::path::Path::new(&path).join(if receive { "atoken" } else { "underlying" });
            std::fs::create_dir_all(&dir).unwrap();
            let (snapshot, call) = prelude_setup(&c, receive);
            let d = project(&projection_input(&c, true)).unwrap();
            let a = project(&projection_input(&c, false)).unwrap();
            let v = conditions(
                &c,
                num(&d.projected.as_ref().unwrap().user_variable_debt_balance),
            );
            for (name, value) in [
                (
                    "input.json",
                    serde_json::json!({"snapshot":snapshot,"call":call}),
                ),
                ("output.json", serde_json::to_value(out).unwrap()),
                (
                    "models.json",
                    serde_json::json!({"debt_input":projection_input(&c,true),"debt_expected":d,
                    "collateral_input":projection_input(&c,false),"collateral_expected":a,
                    "conditions_input":v,"conditions_expected":validate(&v).unwrap()}),
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
fn seeded_interest_reserve_factors_balances_and_two_delivery_modes_match_models() {
    let mut rng = ChaCha8Rng::seed_from_u64(0x00ca_ce20_2026);
    for n in 0..32 {
        let mut c = PreludeCase::default();
        for start in [&mut c.debt, &mut c.collateral] {
            start.last = 31_537_000 - rng.gen_range(0..=31_536_000u64);
            start.liquidity = U256::from(RAY + rng.gen_range(0..RAY));
            start.borrow = U256::from(RAY + rng.gen_range(0..RAY));
            start.liquidity_rate = U256::from(rng.gen_range(0..RAY / 3));
            start.borrow_rate = U256::from(rng.gen_range(0..RAY / 3));
            start.configuration =
                (U256::from(1) << 56usize) | (U256::from(rng.gen_range(0u64..=10000)) << 64usize);
        }
        c.payment.underlying.transfer.debt.repayment = U256::from(rng.gen_range(10u64..=60));
        c.payment.underlying.transfer.amount = U256::from(rng.gen_range(10u64..=80));
        c.payment.underlying.transfer.fee = U256::from(rng.gen_range(0u64..=10));
        if n % 4 == 0 {
            c.payment.underlying.transfer.recipient = TREASURY;
        }
        if n % 3 == 0 {
            c.payment.underlying.transfer.rewards.rewards.clear();
        }
        for receive in [false, true] {
            check_prelude(&c, receive);
        }
    }
}
fn expect_revert(c: &PreludeCase, receive: bool, error: &str) {
    let (s, q) = prelude_setup(c, receive);
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Revert);
    assert_eq!(out.output, error);
    assert_no_contract_changes(&out);
}
#[test]
fn every_initial_validation_failure_rolls_back_prior_index_and_treasury_updates() {
    let mut cases = vec![PreludeCase::default(); 8];
    cases[0].payment.underlying.transfer.recipient = USER;
    cases[1].debt.configuration = U256::ZERO;
    cases[2].collateral.configuration |= U256::from(1) << 60usize;
    cases[3].debt.grace = 31_537_000;
    cases[4].health = U256::from(1_000_000_000_000_000_000u64);
    cases[5].payment.underlying.transfer.reserve_id = 128;
    cases[6].payment.underlying.transfer.debt.config = U256::ZERO;
    cases[7].payment.underlying.transfer.debt.balance = U256::ZERO;
    for c in cases {
        let d = project(&projection_input(&c, true))
            .unwrap()
            .projected
            .unwrap();
        let error = validate(&conditions(&c, num(&d.user_variable_debt_balance)))
            .unwrap()
            .revert_selector
            .unwrap();
        for receive in [false, true] {
            expect_revert(&c, receive, &error);
        }
    }
}
#[test]
fn earlier_reserve_failure_wins_over_health_and_rolls_back_both_reserves() {
    for collateral in [false, true] {
        for downcast in [false, true] {
            let mut c = PreludeCase {
                health: U256::MAX,
                ..PreludeCase::default()
            };
            let start = if collateral {
                &mut c.collateral
            } else {
                &mut c.debt
            };
            if downcast {
                start.liquidity = U256::from(u128::MAX);
            } else {
                start.accrued = U256::from(u128::MAX);
            }
            let error = project(&projection_input(&c, !collateral))
                .unwrap()
                .revert_data
                .unwrap();
            for receive in [false, true] {
                expect_revert(&c, receive, &error);
            }
        }
    }
    let mut c = PreludeCase::default();
    c.debt.last = 31_537_001;
    c.health = U256::MAX;
    let error = project(&projection_input(&c, true))
        .unwrap()
        .revert_data
        .unwrap();
    let (mut s, q) = prelude_setup(&c, true);
    s.accounts.retain(|a| a.address != WETH_DEBT);
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.output, error);
    assert_eq!(out.status, VmStatus::Revert);
    assert_no_contract_changes(&out);
}
#[test]
fn same_timestamp_skips_interest_and_zero_rates_preserve_indices() {
    let mut c = PreludeCase::default();
    c.debt.last = 31_537_000;
    c.collateral.last = 31_537_000;
    c.debt.liquidity_rate = U256::from(u128::MAX);
    c.collateral.liquidity_rate = U256::from(u128::MAX);
    for receive in [false, true] {
        check_prelude(&c, receive);
    }
    let mut c = PreludeCase::default();
    for start in [&mut c.debt, &mut c.collateral] {
        start.liquidity_rate = U256::ZERO;
        start.borrow_rate = U256::ZERO;
    }
    c.payment.underlying.scaled_debt = U256::ZERO;
    for receive in [false, true] {
        check_prelude(&c, receive);
    }
}
#[test]
fn late_usdc_failure_reverts_initial_accrual_and_all_later_effects_in_both_modes() {
    for receive in [false, true] {
        let (mut s, q) = prelude_setup(&PreludeCase::default(), receive);
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
fn both_modes_require_actual_collateral_debt_total_and_implementation_witnesses() {
    for receive in [false, true] {
        let (original, q) = prelude_setup(&PreludeCase::default(), receive);
        for address in [WETH_DEBT, TOKEN] {
            for slot in [U256::from(58), implementation_slot()] {
                let mut s = original.clone();
                assert!(s
                    .accounts
                    .iter_mut()
                    .find(|a| a.address == address)
                    .unwrap()
                    .storage
                    .remove(&slot.to_string())
                    .is_some());
                assert!(simulate(&s, &q).is_err());
            }
        }
        let mut s = original;
        s.accounts.retain(|a| a.address != WETH_DEBT);
        assert!(simulate(&s, &q).is_err());
    }
}
