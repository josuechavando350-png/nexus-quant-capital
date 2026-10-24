//! Original payment and event after collateral delivery; complete observed USDC.
//! Synthetic Pool, balances and approvals; no historical execution certification.
use super::*;
const USDC_IMPL: &str = "0x43506849d7c04f9138d1a2050bbf3a0c054402dd";
const DEBT_VAULT: &str = "0x98c23e9d8f34fefb1b7bd6a91b7ff122f4e16f5c";
fn payment_fixture() -> Value {
    serde_json::from_str(include_str!("../../fixtures/aave_payment_execution.json")).unwrap()
}
#[derive(Clone, Debug)]
struct PaymentCase {
    underlying: UnderCase,
    wallet: U256,
    vault: U256,
    allowance: U256,
}
impl Default for PaymentCase {
    fn default() -> Self {
        Self {
            underlying: UnderCase::default(),
            wallet: U256::from(100),
            vault: U256::from(200),
            allowance: U256::from(100),
        }
    }
}
fn allowance_slot(owner: &str) -> U256 {
    map_word(addr(POOL), mapping(owner, 10))
}
fn payment_setup(c: &PaymentCase) -> (PinnedSnapshot, SandboxCall) {
    let (mut s, q) = underlying_setup(&c.underlying);
    let f = payment_fixture();
    let code = |name: &str| f["contracts"][name]["runtime_code"].as_str().unwrap();
    let pool = s.accounts.iter_mut().find(|a| a.address == POOL).unwrap();
    pool.runtime_code = code("AavePaymentExecutionHarness").into();
    pool.code_hash = format!("{:#x}", keccak256(decode_hex(&pool.runtime_code).unwrap()));
    assert_eq!(
        &q.calldata[2..10],
        f["contracts"]["AavePaymentExecutionHarness"]["selectors"][UNDER_SIGNATURE]
    );
    let mut token = account(ASSET, code("usdc-proxy"));
    let proxy = &f["contracts"]["usdc-proxy"];
    for (field, value) in [
        ("implementation_slot", addr(USDC_IMPL)),
        (
            "admin_slot",
            addr(proxy["observed_admin_slot_word"].as_str().unwrap()),
        ),
    ] {
        token.storage.insert(
            addr(proxy[field].as_str().unwrap()).to_string(),
            value.to_string(),
        );
    }
    let owner = c.underlying.transfer.recipient;
    for (slot, value) in [
        (U256::from(1), U256::ZERO),
        (mapping(POOL, 9), U256::ZERO),
        (mapping(owner, 9), c.wallet),
        (mapping(DEBT_VAULT, 9), c.vault),
        (allowance_slot(owner), c.allowance),
    ] {
        token.storage.insert(slot.to_string(), value.to_string());
    }
    s.accounts.push(token);
    s.accounts
        .push(account(USDC_IMPL, code("usdc-implementation")));
    (s, q)
}
fn storage_changes(out: &SandboxOutcome) -> BTreeMap<String, BTreeMap<String, String>> {
    out.account_deltas
        .iter()
        .filter(|d| !d.storage.is_empty())
        .map(|d| (d.address.clone(), d.storage.clone()))
        .collect()
}
fn check_payment(c: &PaymentCase) -> SandboxOutcome {
    // Parent checker independently models every preceding storage change/log.
    let reference = check_underlying(&c.underlying);
    let (s, q) = payment_setup(c);
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Success, "{c:?} {}", out.output);
    assert!(!out.canonical_state_authenticated);
    let t = &c.underlying.transfer;
    let repay = t.debt.repayment;
    let mut expected = storage_changes(&reference);
    assert_eq!(
        out.output,
        reference.output
            + &encoded(&[c.wallet - repay, c.vault + repay, c.allowance - repay,])[2..]
    );
    let mut logs = reference.logs.clone();
    logs.push(event(
        ASSET,
        "Transfer(address,address,uint256)",
        &[t.recipient, DEBT_VAULT],
        &[repay],
    ));
    logs.push(event(
        POOL,
        "LiquidationCall(address,address,address,uint256,uint256,address,bool)",
        &[COLLATERAL, ASSET, USER],
        &[repay, t.amount, addr(t.recipient), U256::ZERO],
    ));
    assert_eq!(out.logs, logs);
    if repay != U256::ZERO {
        expected.insert(
            ASSET.into(),
            [
                (
                    mapping(t.recipient, 9).to_string(),
                    (c.wallet - repay).to_string(),
                ),
                (
                    mapping(DEBT_VAULT, 9).to_string(),
                    (c.vault + repay).to_string(),
                ),
                (
                    allowance_slot(t.recipient).to_string(),
                    (c.allowance - repay).to_string(),
                ),
            ]
            .into_iter()
            .collect(),
        );
    }
    assert_eq!(storage_changes(&out), expected);
    out
}
fn payment_revert(s: &PinnedSnapshot, q: &SandboxCall, error: &str) {
    let out = simulate(s, q).unwrap();
    assert_eq!(out.status, VmStatus::Revert);
    assert_eq!(out.output, abi_string_error(error));
    assert_no_contract_changes(&out);
}
#[test]
fn original_usdc_payment_and_liquidation_event_export_closed_example() {
    let c = PaymentCase::default();
    let out = check_payment(&c);
    if let Ok(path) = std::env::var("NQC_MINER_PAYMENT_EVIDENCE_DIR") {
        let dir = std::path::Path::new(&path);
        std::fs::create_dir(dir).unwrap();
        let (snapshot, call) = payment_setup(&c);
        for (name, value) in [
            (
                "input.json",
                serde_json::json!({"snapshot": snapshot, "call": call}),
            ),
            ("output.json", serde_json::to_value(out).unwrap()),
        ] {
            use std::io::Write;
            let mut f = std::fs::File::create_new(dir.join(name)).unwrap();
            f.write_all(&serde_json::to_vec_pretty(&value).unwrap())
                .unwrap();
            f.write_all(b"\n").unwrap();
        }
    }
}
#[test]
fn exact_allowance_balance_and_maximum_approval_are_decremented() {
    let c = PaymentCase::default();
    let repay = c.underlying.transfer.debt.repayment;
    check_payment(&PaymentCase {
        wallet: repay,
        allowance: repay,
        ..c.clone()
    });
    check_payment(&PaymentCase {
        allowance: U256::MAX,
        ..c.clone()
    });
    check_payment(&PaymentCase {
        vault: (U256::from(1) << 255usize) - U256::from(1) - repay,
        ..c
    });
}
#[test]
fn seeded_usdc_payment_composes_prior_burn_rates_fee_rewards_and_exact_events() {
    let mut rng = ChaCha8Rng::seed_from_u64(0x00de_b700_2026);
    for n in 0..120 {
        let mut c = PaymentCase::default();
        c.underlying.transfer.debt.repayment = U256::from(rng.gen_range(2u64..=140));
        c.underlying.transfer.amount = U256::from(rng.gen_range(1u64..=140));
        c.underlying.transfer.fee = U256::from(rng.gen_range(0u64..=10));
        if n % 5 == 0 {
            c.underlying.transfer.recipient = TREASURY;
        }
        if n % 3 == 0 {
            c.underlying.transfer.rewards.rewards.clear();
        }
        let repay = c.underlying.transfer.debt.repayment;
        c.wallet = repay + U256::from(rng.gen_range(0u64..10000));
        c.vault = U256::from(rng.gen_range(0u64..10000));
        c.allowance = if n % 7 == 0 {
            U256::MAX
        } else {
            repay + U256::from(rng.gen_range(0u64..10000))
        };
        check_payment(&c);
    }
}
#[test]
fn dust_debt_repayment_is_rejected_before_payment_without_any_persistent_changes() {
    let mut c = PaymentCase::default();
    c.underlying.transfer.debt.repayment = U256::from(1);
    let (s, q) = payment_setup(&c);
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Revert);
    assert_eq!(out.output, hex(&keccak256("InvalidBurnAmount()")[..4]));
    assert_no_contract_changes(&out);
}
#[test]
fn insufficient_usdc_balance_or_approval_rolls_back_delivered_weth_and_all_prior_effects() {
    let c = PaymentCase::default();
    let repay = c.underlying.transfer.debt.repayment;
    for (case, error) in [
        (
            PaymentCase {
                wallet: repay - U256::from(1),
                ..c.clone()
            },
            "ERC20: transfer amount exceeds balance",
        ),
        (
            PaymentCase {
                allowance: repay - U256::from(1),
                ..c
            },
            "ERC20: transfer amount exceeds allowance",
        ),
    ] {
        let (s, q) = payment_setup(&case);
        payment_revert(&s, &q, error);
    }
}
#[test]
fn paused_or_blacklisted_spender_liquidator_or_vault_rolls_back_entire_composition() {
    let c = PaymentCase::default();
    let (original, q) = payment_setup(&c);
    for (slot, mask, error) in [
        (U256::from(1), U256::from(1) << 160usize, "Pausable: paused"),
        (
            mapping(POOL, 9),
            U256::from(1) << 255usize,
            "Blacklistable: account is blacklisted",
        ),
        (
            mapping(CALLER, 9),
            U256::from(1) << 255usize,
            "Blacklistable: account is blacklisted",
        ),
        (
            mapping(DEBT_VAULT, 9),
            U256::from(1) << 255usize,
            "Blacklistable: account is blacklisted",
        ),
    ] {
        let mut s = original.clone();
        let state = &mut s
            .accounts
            .iter_mut()
            .find(|a| a.address == ASSET)
            .unwrap()
            .storage;
        let value = read_slot(state, slot) | mask;
        state.insert(slot.to_string(), value.to_string());
        payment_revert(&s, &q, error);
    }
}
#[test]
fn recipient_255_bit_overflow_reverts_after_attempted_sender_debit() {
    let c = PaymentCase {
        vault: (U256::from(1) << 255usize) - U256::from(1),
        ..PaymentCase::default()
    };
    let (s, q) = payment_setup(&c);
    payment_revert(&s, &q, "FiatTokenV2_2: Balance exceeds (2^255 - 1)");
}
#[test]
fn usdc_proxy_admin_cannot_use_fallback_and_failure_is_atomic() {
    let (mut s, q) = payment_setup(&PaymentCase::default());
    let f = payment_fixture();
    let slot = addr(f["contracts"]["usdc-proxy"]["admin_slot"].as_str().unwrap());
    s.accounts
        .iter_mut()
        .find(|a| a.address == ASSET)
        .unwrap()
        .storage
        .insert(slot.to_string(), addr(POOL).to_string());
    payment_revert(&s, &q, "Cannot call fallback function from the proxy admin");
}
#[test]
fn payment_missing_code_routing_pause_blacklist_balance_or_allowance_witness_fails_closed() {
    let (original, q) = payment_setup(&PaymentCase::default());
    let f = payment_fixture();
    for slot in [
        U256::from(1),
        mapping(POOL, 9),
        mapping(CALLER, 9),
        mapping(DEBT_VAULT, 9),
        allowance_slot(CALLER),
        addr(f["contracts"]["usdc-proxy"]["admin_slot"].as_str().unwrap()),
        addr(
            f["contracts"]["usdc-proxy"]["implementation_slot"]
                .as_str()
                .unwrap(),
        ),
    ] {
        let mut s = original.clone();
        assert!(s
            .accounts
            .iter_mut()
            .find(|a| a.address == ASSET)
            .unwrap()
            .storage
            .remove(&slot.to_string())
            .is_some());
        assert!(simulate(&s, &q).is_err(), "{slot}");
    }
    for address in [ASSET, USDC_IMPL] {
        let mut s = original.clone();
        s.accounts.retain(|a| a.address != address);
        assert!(simulate(&s, &q).is_err(), "{address}");
    }
}
#[test]
fn original_safe_transfer_wrapper_rejects_false_malformed_and_no_code_tokens_atomically() {
    let (original, q) = payment_setup(&PaymentCase::default());
    // Deliberate fault-injection stand-ins; these are never described as USDC.
    for (code, error) in [
        ("0x600060005260206000f3", "GPv2: failed transferFrom"),
        ("0x600160005360016000f3", "GPv2: malformed transfer result"),
        ("0x", "GPv2: not a contract"),
    ] {
        let mut s = original.clone();
        let a = s.accounts.iter_mut().find(|a| a.address == ASSET).unwrap();
        a.runtime_code = code.into();
        a.code_hash = format!("{:#x}", keccak256(decode_hex(code).unwrap()));
        payment_revert(&s, &q, error);
    }
}

#[path = "aave_delivery_execution.rs"]
mod delivery_execution;
