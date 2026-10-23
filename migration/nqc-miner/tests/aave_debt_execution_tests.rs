//! Combined original Pool debt function + exact deployed token/strategy runtimes.
//! Original cases use a synthetic proxy; additional cases use the audited proxy.
//! Pool entrypoint, rewards behavior and execution state remain synthetic.
use alloy_primitives::{keccak256, U256};
use nqc_miner::{aave_debt::*, discovery::decode_hex, evm::*, historical::hex};
use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;
use serde_json::Value;
use std::collections::BTreeMap;

const POOL: &str = "0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2";
const TOKEN: &str = "0x72e95b8931767c79ba4eee721354d6e99a61d004";
const IMPL: &str = "0xb27c52c7f84819e3157993489741cb60786ae330";
const STRATEGY: &str = "0x9ec6f08190dea04a54f8afc53db96134e5e3fdfb";
const REWARDS: &str = "0x8164cc65827dcfe994ab23944cbc90e0aa80bfcb";
const ASSET: &str = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48";
const USER: &str = "0x000000000000000000000000000000000000cafe";
const CALLER: &str = "0x1111111111111111111111111111111111111111";
const COINBASE: &str = "0x3333333333333333333333333333333333333333";
const RAY: u128 = 1_000_000_000_000_000_000_000_000_000;
fn addr(value: &str) -> U256 {
    U256::from_str_radix(&value[2..], 16).unwrap()
}
fn fixture() -> Value {
    serde_json::from_str(include_str!("../fixtures/aave_debt_execution.json")).unwrap()
}
fn proxy_fixture() -> Value {
    serde_json::from_str(include_str!("../fixtures/aave_proxy_execution.json")).unwrap()
}
const ADMIN: &str = "0x64b761d848206f447fe2dd461b0c635ec39ebb27";
const ALTERNATE: &str = "0x4444444444444444444444444444444444444444";
fn implementation_slot() -> U256 {
    U256::from_be_bytes(keccak256("eip1967.proxy.implementation").0) - U256::from(1)
}
fn encoded(values: &[U256]) -> String {
    "0x".to_owned()
        + &values
            .iter()
            .map(|v| format!("{v:064x}"))
            .collect::<String>()
}
fn mapping(key: &str, slot: u64) -> U256 {
    U256::from_be_bytes(keccak256(decode_hex(&encoded(&[addr(key), U256::from(slot)])).unwrap()).0)
}
fn account(address: &str, code: &str) -> WitnessAccount {
    WitnessAccount {
        address: address.into(),
        exists: true,
        balance_wei: "1000000000000000000".into(),
        nonce: 0,
        runtime_code: code.into(),
        code_hash: format!("{:#x}", keccak256(decode_hex(code).unwrap())),
        storage: BTreeMap::new(),
    }
}
#[derive(Clone, Debug)]
struct Case {
    debt: U256,
    repayment: U256,
    no_collateral: bool,
    index: U256,
    cached: U256,
    deficit: U256,
    virtual_balance: U256,
    reserve_id: u16,
    config: U256,
    factor: U256,
    balance: U256,
    total: U256,
    previous_index: U256,
    delegation: u8,
    rates: [u32; 4],
    rewards_mode: u8,
}
impl Default for Case {
    fn default() -> Self {
        Self {
            debt: U256::from(150),
            repayment: U256::from(40),
            no_collateral: false,
            index: U256::from(3 * RAY / 2),
            cached: U256::from(9999),
            deficit: U256::from(5),
            virtual_balance: U256::from(200),
            reserve_id: 1,
            config: U256::from(255),
            factor: U256::from(1000),
            balance: U256::from(100),
            total: U256::from(1000),
            previous_index: U256::from(RAY),
            delegation: 2,
            rates: [8000, 100, 400, 6000],
            rewards_mode: 0,
        }
    }
}
fn setup(c: &Case, f: &Value) -> (PinnedSnapshot, SandboxCall) {
    let code = |name: &str| f["contracts"][name]["runtime_code"].as_str().unwrap();
    let mut pool = account(POOL, code("AaveDebtExecutionHarness"));
    pool.storage = (0..=10).map(|n| (n.to_string(), "0".into())).collect();
    let audited_proxy = f["contracts"].get("AuditedDebtProxy").is_some();
    let mut token = account(
        TOKEN,
        code(if audited_proxy {
            "AuditedDebtProxy"
        } else {
            "SyntheticDebtProxy"
        }),
    );
    if audited_proxy {
        token
            .storage
            .insert(implementation_slot().to_string(), addr(IMPL).to_string());
    }
    token.storage.insert(
        mapping(USER, 56).to_string(),
        (c.balance | (U256::from(c.delegation) << 120usize) | (c.previous_index << 128usize))
            .to_string(),
    );
    token.storage.insert("58".into(), c.total.to_string());
    let mut strategy = account(STRATEGY, code("DefaultReserveInterestRateStrategyV2"));
    strategy.storage.insert(
        mapping(ASSET, 0).to_string(),
        (U256::from(c.rates[0])
            | (U256::from(c.rates[1]) << 16usize)
            | (U256::from(c.rates[2]) << 48usize)
            | (U256::from(c.rates[3]) << 80usize))
            .to_string(),
    );
    let mut rewards = account(REWARDS, code("RewardsProbe"));
    rewards
        .storage
        .insert("0".into(), c.rewards_mode.to_string());
    rewards.storage.insert("1".into(), "0".into());
    let snapshot = PinnedSnapshot {
        schema_version: 1,
        kind: SnapshotKind::SyntheticFixture,
        chain_id: 1,
        block_number: 100,
        block_hash: format!("0x{}", "11".repeat(32)),
        state_root: format!("0x{}", "22".repeat(32)),
        timestamp: 1000,
        fork: EvmFork::Cancun,
        block_gas_limit: 30_000_000,
        base_fee_wei: "1".into(),
        beneficiary: COINBASE.into(),
        prevrandao: format!("0x{}", "44".repeat(32)),
        excess_blob_gas: Some(0),
        ancestor_block_hashes: BTreeMap::new(),
        accounts: vec![
            account(CALLER, "0x"),
            pool,
            token,
            account(IMPL, code("VariableDebtTokenInstance")),
            strategy,
            rewards,
            account(COINBASE, "0x"),
        ],
    };
    let signature =
        "calculate((uint256,uint256,bool,uint256,uint256,uint128,uint128,uint16,uint256,uint256))";
    let selector = hex(&keccak256(signature)[..4]);
    assert_eq!(
        &selector[2..],
        f["contracts"]["AaveDebtExecutionHarness"]["selectors"][signature]
    );
    let words = [
        c.debt,
        c.repayment,
        U256::from(c.no_collateral),
        c.index,
        c.cached,
        c.deficit,
        c.virtual_balance,
        U256::from(c.reserve_id),
        c.config,
        c.factor,
    ];
    let call = SandboxCall {
        caller: CALLER.into(),
        to: POOL.into(),
        calldata: selector + &encoded(&words)[2..],
        value_wei: "0".into(),
        gas_limit: 5_000_000,
        gas_price_wei: "1".into(),
        nonce: 0,
    };
    (snapshot, call)
}
fn execute(c: &Case, f: &Value) -> SandboxOutcome {
    let (s, q) = setup(c, f);
    simulate(&s, &q).unwrap()
}
fn ceil(a: U256, b: U256) -> U256 {
    let p = a * b;
    p / U256::from(RAY) + U256::from(p % U256::from(RAY) != U256::ZERO)
}
fn ray_mul(a: U256, b: U256) -> U256 {
    (a * b + U256::from(RAY / 2)) / U256::from(RAY)
}
fn ray_div(a: U256, b: U256) -> U256 {
    (a * U256::from(RAY) + b / U256::from(2)) / b
}
fn rates(c: &Case, total: U256, deficit: U256) -> (U256, U256) {
    let r = c
        .rates
        .map(|n| U256::from(n) * U256::from(100_000_000_000_000_000_000_000u128));
    if total == U256::ZERO {
        return (U256::ZERO, r[1]);
    }
    let available = c.virtual_balance + c.repayment;
    let borrow = ray_div(total, available + total);
    let supply = ray_div(total, available + total + deficit);
    let variable = if borrow > r[0] {
        r[1] + r[2] + ray_mul(r[3], ray_div(borrow - r[0], U256::from(RAY) - r[0]))
    } else {
        r[1] + ray_div(ray_mul(r[2], borrow), r[0])
    };
    (
        (ray_mul(variable, supply) * (U256::from(10000) - c.factor) + U256::from(5000))
            / U256::from(10000),
        variable,
    )
}
fn event(address: &str, signature: &str, indexed: &[&str], data: &[U256]) -> VmLog {
    VmLog {
        address: address.into(),
        topics: std::iter::once(format!("{:#x}", keccak256(signature)))
            .chain(indexed.iter().map(|a| encoded(&[addr(a)])))
            .collect(),
        data: encoded(data),
    }
}
fn check_success(c: &Case, f: &Value) -> SandboxOutcome {
    let burn = c.debt != U256::ZERO;
    let amount = if burn {
        (if c.no_collateral { c.debt } else { c.repayment }) * U256::from(RAY) / c.index
    } else {
        U256::ZERO
    };
    let balance = c.balance - amount;
    let supply = c.total - amount;
    let cached = if burn { supply } else { c.cached };
    let outstanding = c.debt - c.repayment;
    let deficit = c.deficit
        + if c.no_collateral {
            outstanding
        } else {
            U256::ZERO
        };
    let (liquidity, variable) = rates(c, ceil(cached, c.index), deficit);
    let predicted = nqc_miner::aave_debt::calculate(&DebtInput {
        borrower_reserve_debt: c.debt.to_string(),
        actual_debt_to_liquidate: c.repayment.to_string(),
        has_no_collateral_left: c.no_collateral,
        next_variable_borrow_index_ray: c.index.to_string(),
        current_scaled_variable_debt: c.cached.to_string(),
        reserve_deficit: c.deficit.to_string(),
        virtual_underlying_balance: c.virtual_balance.to_string(),
        reserve_id: c.reserve_id,
        user_configuration: c.config.to_string(),
        reserve_factor: c.factor.to_string(),
        token_burn: BurnOutcome::Return {
            no_more_debt: balance == U256::ZERO,
            next_scaled_variable_debt: supply.to_string(),
        },
        rate_quote: RateOutcome::Return {
            liquidity_rate_ray: liquidity.to_string(),
            variable_borrow_rate_ray: variable.to_string(),
        },
    })
    .unwrap()
    .amounts
    .unwrap();
    let config = predicted.user_configuration.parse::<U256>().unwrap();
    let index = if burn { c.index } else { c.previous_index };
    let actual = execute(c, f);
    assert_eq!(actual.status, VmStatus::Success, "{c:?}, {}", actual.output);
    assert!(!actual.canonical_state_authenticated);
    assert_eq!(actual.snapshot_kind, SnapshotKind::SyntheticFixture);
    assert_eq!(
        actual.output,
        encoded(&[
            cached,
            outstanding,
            deficit,
            config,
            c.virtual_balance + c.repayment,
            liquidity,
            variable,
            balance,
            index,
            supply
        ]),
        "{c:?}"
    );
    let zero = "0x0000000000000000000000000000000000000000";
    let mut logs = vec![];
    if burn {
        logs.push(event(
            REWARDS,
            "Callback(address,address,uint256,uint256,uint256,uint256,uint256)",
            &[TOKEN, USER],
            &[c.total, c.balance, supply, balance, index],
        ));
        let previous = ceil(c.balance, c.previous_index);
        let next = ceil(balance, c.index);
        let increase = ceil(c.balance, c.index) - previous;
        if next > previous {
            logs.push(event(
                TOKEN,
                "Transfer(address,address,uint256)",
                &[zero, USER],
                &[next - previous],
            ));
            logs.push(event(
                TOKEN,
                "Mint(address,address,uint256,uint256,uint256)",
                &[USER, USER],
                &[next - previous, increase, index],
            ));
        } else {
            logs.push(event(
                TOKEN,
                "Transfer(address,address,uint256)",
                &[USER, zero],
                &[previous - next],
            ));
            logs.push(event(
                TOKEN,
                "Burn(address,address,uint256,uint256,uint256)",
                &[USER, zero],
                &[previous - next, increase, index],
            ));
        }
    }
    if c.no_collateral && outstanding != U256::ZERO {
        logs.push(event(
            POOL,
            "DeficitCreated(address,address,uint256)",
            &[USER, ASSET],
            &[outstanding],
        ));
    }
    logs.push(event(
        POOL,
        "ReserveDataUpdated(address,uint256,uint256,uint256,uint256,uint256)",
        &[ASSET],
        &[liquidity, U256::ZERO, variable, U256::from(RAY), c.index],
    ));
    assert_eq!(actual.logs, logs, "events {c:?}");
    let (before, _) = setup(c, f);
    let mut expected: BTreeMap<String, BTreeMap<String, String>> = BTreeMap::new();
    expected.insert(
        POOL.into(),
        [
            (1, liquidity << 128usize),
            (2, variable << 128usize),
            (3, deficit | (U256::from(c.reserve_id) << 168usize)),
            (8, (c.virtual_balance + c.repayment) << 128usize),
            (10, config),
        ]
        .into_iter()
        .map(|(k, v)| (k.to_string(), v.to_string()))
        .collect(),
    );
    expected.insert(
        TOKEN.into(),
        [
            (
                mapping(USER, 56),
                (balance | (U256::from(c.delegation) << 120usize) | (index << 128usize))
                    .to_string(),
            ),
            (U256::from(58), supply.to_string()),
        ]
        .into_iter()
        .map(|(k, v)| (k.to_string(), v))
        .collect(),
    );
    expected.insert(
        REWARDS.into(),
        [("1".into(), U256::from(burn).to_string())]
            .into_iter()
            .collect(),
    );
    for (address, slots) in &mut expected {
        let old = &before
            .accounts
            .iter()
            .find(|a| &a.address == address)
            .unwrap()
            .storage;
        slots.retain(|k, v| old.get(k) != Some(v));
    }
    expected.retain(|_, slots| !slots.is_empty());
    let changed: BTreeMap<_, _> = actual
        .account_deltas
        .iter()
        .filter(|d| !d.storage.is_empty())
        .map(|d| (d.address.clone(), d.storage.clone()))
        .collect();
    assert_eq!(changed, expected, "exact contract storage {c:?}");
    actual
}
fn check_revert(c: &Case, f: &Value, data: &str) {
    let actual = execute(c, f);
    assert_eq!(actual.status, VmStatus::Revert, "{c:?}");
    assert_eq!(actual.output, data, "{c:?}");
    assert!(actual.logs.is_empty());
    assert!(
        actual.account_deltas.iter().all(|d| d.storage.is_empty()),
        "all callback/token/pool writes must roll back"
    );
}
fn selector(signature: &str) -> String {
    hex(&keccak256(signature)[..4])
}
fn panic() -> String {
    "0x4e487b71".to_owned() + &encoded(&[U256::from(0x11)])[2..]
}
#[test]
fn real_token_emits_mint_on_interest_heavy_burn_and_actual_rates_replace_quotes() {
    let c = Case::default();
    let f = fixture();
    let out = check_success(&c, &f);
    assert_eq!(
        out.logs[2].topics[0],
        format!(
            "{:#x}",
            keccak256("Mint(address,address,uint256,uint256,uint256)")
        )
    );
    assert_eq!(
        out.logs[0].data,
        encoded(&[
            U256::from(1000),
            U256::from(100),
            U256::from(974),
            U256::from(74),
            U256::from(3 * RAY / 2)
        ])
    );
    if let Ok(path) = std::env::var("NQC_MINER_EXECUTION_EVIDENCE_DIR") {
        let directory = std::path::Path::new(&path);
        std::fs::create_dir(directory).unwrap();
        let (snapshot, call) = setup(&c, &f);
        let input = serde_json::json!({"snapshot":snapshot,"call":call});
        for (name, bytes) in [
            ("input.json", serde_json::to_vec_pretty(&input).unwrap()),
            ("output.json", serde_json::to_vec_pretty(&out).unwrap()),
        ] {
            use std::io::Write;
            let mut file = std::fs::File::create_new(directory.join(name)).unwrap();
            file.write_all(&bytes).unwrap();
            file.write_all(b"\n").unwrap();
        }
    }
}
#[test]
fn full_partial_zero_and_exhausted_collateral_cover_true_token_return() {
    let f = fixture();
    let mut c = Case {
        repayment: U256::from(120),
        ..Case::default()
    };
    check_success(&c, &f);
    c.no_collateral = true;
    check_success(&c, &f);
    c.no_collateral = false;
    c.repayment = c.debt;
    check_success(&c, &f);
    c.debt = U256::ZERO;
    c.repayment = U256::ZERO;
    c.rewards_mode = 1;
    check_success(&c, &f);
    c.cached = U256::ZERO;
    c.factor = U256::from(10001);
    check_success(&c, &f);
}
#[test]
fn callback_failures_and_reentrant_burn_attempt_revert_entire_composition() {
    let f = fixture();
    let mut c = Case::default();
    for (mode, error) in [
        (1, selector("RewardsRejected()")),
        (2, "0x".into()),
        (3, selector("CallerMustBePool()")),
    ] {
        c.rewards_mode = mode;
        check_revert(&c, &f, &error);
    }
}
#[test]
fn later_pool_and_rate_failures_undo_successful_token_burn_and_callback() {
    let f = fixture();
    let mut c = Case {
        factor: U256::from(10001),
        ..Case::default()
    };
    check_revert(&c, &f, &panic());
    c = Case::default();
    c.no_collateral = true;
    c.reserve_id = 128;
    check_revert(&c, &f, &selector("InvalidReserveIndex()"));
    c = Case::default();
    c.repayment = c.debt + U256::from(1);
    check_revert(&c, &f, &panic());
    c = Case::default();
    c.virtual_balance = U256::from(u128::MAX);
    check_revert(&c, &f, &panic());
}
#[test]
fn token_zero_rounding_balance_supply_index_and_cast_boundaries() {
    let f = fixture();
    let mut c = Case {
        repayment: U256::from(1),
        ..Case::default()
    };
    check_revert(&c, &f, &selector("InvalidBurnAmount()"));
    c = Case::default();
    c.repayment = U256::from(1000);
    check_revert(&c, &f, &panic());
    c = Case::default();
    c.total = U256::from(1);
    check_revert(&c, &f, &panic());
    c = Case::default();
    c.previous_index = c.index + U256::from(RAY);
    check_revert(&c, &f, &panic());
    c = Case::default();
    c.index = U256::from(u128::MAX) + U256::from(1);
    c.repayment = c.index / U256::from(RAY) + U256::from(1);
    let data = selector("SafeCastOverflowedUintDowncast(uint8,uint256)")
        + &encoded(&[U256::from(128), c.index])[2..];
    check_revert(&c, &f, &data);
    c = Case::default();
    c.index = U256::ZERO;
    check_revert(&c, &f, "0x");
}
#[test]
fn actual_token_only_pool_guard_and_closed_state_missing_dependencies() {
    let f = fixture();
    let c = Case::default();
    let (s, mut q) = setup(&c, &f);
    q.to = TOKEN.into();
    q.calldata = selector("burn(address,uint256,uint256)")
        + &encoded(&[addr(USER), U256::from(1), U256::from(RAY)])[2..];
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Revert);
    assert_eq!(out.output, selector("CallerMustBePool()"));
    assert!(out.logs.is_empty());
    for address in [IMPL, STRATEGY, REWARDS] {
        let (mut s, q) = setup(&c, &f);
        s.accounts.retain(|a| a.address != address);
        assert!(simulate(&s, &q)
            .unwrap_err()
            .to_string()
            .contains("missing account witness"));
    }
    for (address, slot) in [
        (TOKEN, mapping(USER, 56)),
        (TOKEN, U256::from(58)),
        (STRATEGY, mapping(ASSET, 0)),
        (REWARDS, U256::from(1)),
    ] {
        let (mut s, q) = setup(&c, &f);
        s.accounts
            .iter_mut()
            .find(|a| a.address == address)
            .unwrap()
            .storage
            .remove(&slot.to_string());
        assert!(simulate(&s, &q)
            .unwrap_err()
            .to_string()
            .contains("missing storage witness"));
    }
}
#[test]
fn seeded_combined_execution_covers_rounding_usage_branches_and_packed_user_state() {
    let f = fixture();
    seeded_cases(&f);
}
fn seeded_cases(f: &Value) {
    let mut rng = ChaCha8Rng::seed_from_u64(0x000a_11ce_b0de);
    for i in 0..600 {
        let balance = rng.gen_range(10u128..1_000_000_000_000);
        let index = RAY + rng.gen_range(0..3 * RAY);
        let debt = ceil(U256::from(balance), U256::from(index));
        let mut c = Case {
            balance: U256::from(balance),
            total: U256::from(balance + rng.gen_range(0..10_000_000_000_000u128)),
            index: U256::from(index),
            previous_index: U256::from(RAY),
            debt,
            repayment: debt / U256::from(2),
            virtual_balance: U256::from(rng.gen_range(1..20_000_000_000_000u128)),
            deficit: U256::from(rng.gen_range(0..1_000_000u64)),
            factor: U256::from(rng.gen_range(0..=10000u64)),
            delegation: rng.gen_range(0..=255),
            rates: [
                rng.gen_range(100..=9900),
                rng.gen_range(0..500),
                rng.gen_range(0..1500),
                rng.gen_range(1500..10000),
            ],
            ..Case::default()
        };
        if i % 3 == 0 {
            c.no_collateral = true;
        } else if i % 3 == 1 {
            c.previous_index = c.index;
        }
        check_success(&c, f);
    }
    println!("600 seeded combined executions: exact outputs, complete logs and all changed contract slots; no historical eligibility claim");
}

#[test]
fn real_strategy_kink_zero_total_and_maximum_packed_balance() {
    let f = fixture();
    let mut c = Case {
        index: U256::from(RAY),
        debt: U256::from(100),
        total: U256::from(840),
        virtual_balance: U256::from(160),
        deficit: U256::ZERO,
        rates: [8000, 0, 400, 6000],
        ..Case::default()
    };
    let at = check_success(&c, &f);
    let decode = |out: &SandboxOutcome| {
        let bytes = decode_hex(&out.output).unwrap();
        U256::from_be_slice(&bytes[6 * 32..7 * 32])
    };
    assert_eq!(decode(&at), U256::from(RAY / 25));
    c.virtual_balance += U256::from(1);
    assert!(decode(&check_success(&c, &f)) < decode(&at));
    c.virtual_balance -= U256::from(2);
    assert!(decode(&check_success(&c, &f)) > decode(&at));
    c = Case {
        index: U256::from(RAY),
        balance: (U256::from(1) << 120usize) - U256::from(1),
        deficit: U256::ZERO,
        virtual_balance: U256::ZERO,
        delegation: 255,
        factor: U256::from(10001),
        ..Case::default()
    };
    c.total = c.balance;
    c.debt = c.balance;
    c.repayment = c.debt;
    check_success(&c, &f);
    c = Case {
        balance: U256::from(1),
        total: U256::from(1),
        debt: U256::from(2),
        repayment: U256::from(2),
        ..Case::default()
    };
    check_success(&c, &f);
}

fn assert_no_contract_changes(out: &SandboxOutcome) {
    assert!(out.logs.is_empty());
    assert!(out.account_deltas.iter().all(|d| d.storage.is_empty()));
}
fn direct_proxy(caller: &str, calldata: String) -> (PinnedSnapshot, SandboxCall) {
    let (mut s, mut q) = setup(&Case::default(), &proxy_fixture());
    s.accounts.push(account(ADMIN, "0x"));
    q.caller = caller.into();
    q.to = TOKEN.into();
    q.calldata = calldata;
    (s, q)
}
fn abi_string_error(message: &str) -> String {
    let mut data = message.as_bytes().to_vec();
    data.resize(data.len().div_ceil(32) * 32, 0);
    selector("Error(string)")
        + &encoded(&[U256::from(32), U256::from(message.len())])[2..]
        + &hex(&data)[2..]
}
fn address_bytes_call(signature: &str, address: &str, data: &str) -> String {
    let mut bytes = decode_hex(data).unwrap();
    let size = bytes.len();
    bytes.resize(size.div_ceil(32) * 32, 0);
    selector(signature)
        + &encoded(&[addr(address), U256::from(64), U256::from(size)])[2..]
        + &hex(&bytes)[2..]
}
#[test]
fn audited_proxy_executes_complete_debt_case_and_exports_reproducible_example() {
    let f = proxy_fixture();
    let c = Case::default();
    let out = check_success(&c, &f);
    if let Ok(path) = std::env::var("NQC_MINER_PROXY_EVIDENCE_DIR") {
        let directory = std::path::Path::new(&path);
        std::fs::create_dir(directory).unwrap();
        let (snapshot, call) = setup(&c, &f);
        let input = serde_json::json!({"snapshot":snapshot,"call":call});
        for (name, bytes) in [
            ("input.json", serde_json::to_vec_pretty(&input).unwrap()),
            ("output.json", serde_json::to_vec_pretty(&out).unwrap()),
        ] {
            use std::io::Write;
            let mut file = std::fs::File::create_new(directory.join(name)).unwrap();
            file.write_all(&bytes).unwrap();
            file.write_all(b"\n").unwrap();
        }
    }
}
#[test]
fn audited_proxy_runs_600_seeded_debt_token_rate_cases() {
    seeded_cases(&proxy_fixture());
}
#[test]
fn audited_proxy_bubbles_token_callback_and_later_failures_with_full_rollback() {
    let f = proxy_fixture();
    for (mode, error) in [
        (1, selector("RewardsRejected()")),
        (2, "0x".into()),
        (3, selector("CallerMustBePool()")),
    ] {
        check_revert(
            &Case {
                rewards_mode: mode,
                ..Case::default()
            },
            &f,
            &error,
        );
    }
    for c in [
        Case {
            factor: U256::from(10001),
            ..Case::default()
        },
        Case {
            virtual_balance: U256::from(u128::MAX),
            ..Case::default()
        },
        Case {
            total: U256::from(1),
            ..Case::default()
        },
    ] {
        check_revert(&c, &f, &panic());
    }
    check_revert(
        &Case {
            repayment: U256::from(1),
            ..Case::default()
        },
        &f,
        &selector("InvalidBurnAmount()"),
    );
}
#[test]
fn ten_historical_proxy_code_slot_samples_dispatch_to_actual_token_getters() {
    let f = proxy_fixture();
    let samples = f["proxy_samples"].as_array().unwrap();
    assert_eq!(samples.len(), 10);
    for sample in samples {
        let address = sample["proxy"].as_str().unwrap();
        let target = sample["implementation"].as_str().unwrap();
        let contract = if sample["kind"] == "a_token" {
            "ATokenInstance"
        } else {
            "VariableDebtTokenInstance"
        };
        let (mut s, mut q) = direct_proxy(CALLER, selector("scaledTotalSupply()"));
        s.accounts
            .retain(|a| a.address != TOKEN && a.address != IMPL);
        let mut proxy = account(
            address,
            f["contracts"]["AuditedDebtProxy"]["runtime_code"]
                .as_str()
                .unwrap(),
        );
        assert_eq!(sample["implementation_slot_word"], encoded(&[addr(target)]));
        proxy
            .storage
            .insert(implementation_slot().to_string(), addr(target).to_string());
        let supply_slot = f["contracts"][contract]["storage_layout"]["storage"]
            .as_array()
            .unwrap()
            .iter()
            .find(|field| field["label"] == "_totalSupply")
            .unwrap()["slot"]
            .as_str()
            .unwrap();
        proxy.storage.insert(supply_slot.into(), "123456".into());
        s.accounts.push(proxy);
        s.accounts.push(account(
            target,
            f["contracts"][contract]["runtime_code"].as_str().unwrap(),
        ));
        q.to = address.into();
        for (caller, signature, expected) in [
            (CALLER, "scaledTotalSupply()", U256::from(123456)),
            (ADMIN, "admin()", addr(ADMIN)),
            (ADMIN, "implementation()", addr(target)),
        ] {
            q.caller = caller.into();
            q.calldata = selector(signature);
            let out = simulate(&s, &q).unwrap();
            assert_eq!(out.status, VmStatus::Success, "{address} {signature}");
            assert_eq!(out.output, encoded(&[expected]));
            assert_no_contract_changes(&out);
            assert!(!out.canonical_state_authenticated);
        }
    }
}
#[test]
fn immutable_admin_cannot_fallback_and_nonadmin_cannot_use_proxy_admin_routes() {
    for data in [
        selector("scaledTotalSupply()"),
        "0x12345678".into(),
        "0x".into(),
    ] {
        let (s, q) = direct_proxy(ADMIN, data);
        let out = simulate(&s, &q).unwrap();
        assert_eq!(out.status, VmStatus::Revert);
        assert_eq!(
            out.output,
            abi_string_error("Cannot call fallback function from the proxy admin")
        );
        assert_no_contract_changes(&out);
    }
    for data in [
        selector("admin()"),
        selector("implementation()"),
        selector("upgradeTo(address)") + &encoded(&[addr(IMPL)])[2..],
        address_bytes_call(
            "upgradeToAndCall(address,bytes)",
            IMPL,
            &selector("scaledTotalSupply()"),
        ),
    ] {
        let (s, q) = direct_proxy(CALLER, data);
        let out = simulate(&s, &q).unwrap();
        assert_eq!(out.status, VmStatus::Revert);
        assert_eq!(out.output, "0x");
        assert_no_contract_changes(&out);
    }
}
#[test]
fn actual_proxy_upgrade_changes_slot_and_dispatches_locally_without_touching_implementation() {
    let f = proxy_fixture();
    let (mut s, q) = direct_proxy(
        ADMIN,
        selector("upgradeTo(address)") + &encoded(&[addr(ALTERNATE)])[2..],
    );
    s.accounts.push(account(
        ALTERNATE,
        f["contracts"]["VariableDebtTokenInstance"]["runtime_code"]
            .as_str()
            .unwrap(),
    ));
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Success);
    assert_eq!(out.output, "0x");
    assert_eq!(
        out.logs,
        vec![event(TOKEN, "Upgraded(address)", &[ALTERNATE], &[])]
    );
    let changed: BTreeMap<_, _> = out
        .account_deltas
        .iter()
        .filter(|d| !d.storage.is_empty())
        .map(|d| (d.address.clone(), d.storage.clone()))
        .collect();
    assert_eq!(
        changed,
        BTreeMap::from([(
            TOKEN.into(),
            BTreeMap::from([(
                implementation_slot().to_string(),
                addr(ALTERNATE).to_string()
            )])
        )])
    );
    let token = s.accounts.iter_mut().find(|a| a.address == TOKEN).unwrap();
    token.storage.insert(
        implementation_slot().to_string(),
        addr(ALTERNATE).to_string(),
    );
    // Removing the old target proves that the subsequent getter follows the slot.
    s.accounts.retain(|a| a.address != IMPL);
    let mut q = q;
    q.caller = CALLER.into();
    q.calldata = selector("scaledTotalSupply()");
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Success);
    assert_eq!(out.output, encoded(&[U256::from(1000)]));
    assert_no_contract_changes(&out);
}
#[test]
fn proxy_upgrade_and_call_failure_rolls_back_slot_and_event_and_reinitialization_fails() {
    let f = proxy_fixture();
    for data in [
        selector("scaledTotalSupply()"),
        selector("burn(address,uint256,uint256)")
            + &encoded(&[addr(USER), U256::from(1), U256::from(RAY)])[2..],
    ] {
        let (mut s, q) = direct_proxy(
            ADMIN,
            address_bytes_call("upgradeToAndCall(address,bytes)", ALTERNATE, &data),
        );
        s.accounts.push(account(
            ALTERNATE,
            f["contracts"]["VariableDebtTokenInstance"]["runtime_code"]
                .as_str()
                .unwrap(),
        ));
        let out = simulate(&s, &q).unwrap();
        assert_eq!(out.output, "0x");
        if data == selector("scaledTotalSupply()") {
            assert_eq!(out.status, VmStatus::Success);
            assert_eq!(
                out.logs,
                vec![event(TOKEN, "Upgraded(address)", &[ALTERNATE], &[])]
            );
            let storage: BTreeMap<_, _> = out
                .account_deltas
                .iter()
                .filter(|d| !d.storage.is_empty())
                .map(|d| (d.address.clone(), d.storage.clone()))
                .collect();
            assert_eq!(
                storage,
                BTreeMap::from([(
                    TOKEN.into(),
                    BTreeMap::from([(
                        implementation_slot().to_string(),
                        addr(ALTERNATE).to_string()
                    )])
                )])
            );
        } else {
            assert_eq!(out.status, VmStatus::Revert);
            assert_no_contract_changes(&out);
        }
    }
    let (mut s, q) = direct_proxy(
        ADMIN,
        selector("upgradeTo(address)") + &encoded(&[addr(ALTERNATE)])[2..],
    );
    s.accounts.push(account(ALTERNATE, "0x"));
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Revert);
    assert_eq!(
        out.output,
        abi_string_error("Cannot set a proxy implementation to a non-contract address")
    );
    assert_no_contract_changes(&out);
    for caller in [CALLER, ADMIN] {
        let (s, q) = direct_proxy(
            caller,
            address_bytes_call("initialize(address,bytes)", IMPL, "0x"),
        );
        let out = simulate(&s, &q).unwrap();
        assert_eq!(out.status, VmStatus::Revert);
        assert_eq!(out.output, "0x");
        assert_no_contract_changes(&out);
    }
}
#[test]
fn actual_proxy_requires_slot_and_implementation_witnesses() {
    let f = proxy_fixture();
    for slot_missing in [true, false] {
        let (mut s, q) = setup(&Case::default(), &f);
        if slot_missing {
            s.accounts
                .iter_mut()
                .find(|a| a.address == TOKEN)
                .unwrap()
                .storage
                .remove(&implementation_slot().to_string());
        } else {
            s.accounts.retain(|a| a.address != IMPL);
        }
        let error = simulate(&s, &q).unwrap_err().to_string();
        assert!(
            error.contains(if slot_missing {
                "missing storage witness"
            } else {
                "missing account witness"
            }),
            "{error}"
        );
    }
}

#[path = "support/aave_rewards_execution.rs"]
mod rewards_execution;
