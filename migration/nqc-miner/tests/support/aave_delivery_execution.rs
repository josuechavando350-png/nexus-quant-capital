//! One original if/else delivery branch followed by actual observed USDC payment.
//! All execution state and Pool entry remain synthetic; fixed distinct assets.
use super::*;
const DELIVERY_SIGNATURE: &str = "calculate((uint256,uint256,uint256,uint256,uint128,uint128,uint16,uint256,uint256,address,address,uint256,uint256,uint256,uint256,uint256,uint256,uint16,uint128,uint256,uint256,uint256,uint128,bool))";
fn delivery_fixture() -> Value {
    serde_json::from_str(include_str!("../../fixtures/aave_delivery_execution.json")).unwrap()
}
fn delivery_setup(c: &PaymentCase, receive_atoken: bool) -> (PinnedSnapshot, SandboxCall) {
    let (mut s, mut q) = payment_setup(c);
    let f = delivery_fixture();
    let code = f["contracts"]["AaveDeliveryExecutionHarness"]["runtime_code"]
        .as_str()
        .unwrap();
    let pool = s.accounts.iter_mut().find(|a| a.address == POOL).unwrap();
    pool.runtime_code = code.into();
    pool.code_hash = format!("{:#x}", keccak256(decode_hex(code).unwrap()));
    let selector = hex(&keccak256(DELIVERY_SIGNATURE)[..4]);
    assert_eq!(
        &selector[2..],
        f["contracts"]["AaveDeliveryExecutionHarness"]["selectors"][DELIVERY_SIGNATURE]
    );
    q.calldata = selector + &q.calldata[10..] + &encoded(&[U256::from(receive_atoken)])[2..];
    if receive_atoken {
        // These witnesses must not be needed by the receive-aToken path.
        s.accounts.retain(|a| a.address != COLLATERAL);
        s.accounts
            .iter_mut()
            .find(|a| a.address == c.underlying.transfer.token)
            .unwrap()
            .storage
            .remove("61");
        s.accounts
            .iter_mut()
            .find(|a| a.address == STRATEGY)
            .unwrap()
            .storage
            .remove(&mapping(COLLATERAL, 0).to_string());
    }
    (s, q)
}
fn check_delivery(c: &PaymentCase, receive_atoken: bool) -> SandboxOutcome {
    let (s, q) = delivery_setup(c, receive_atoken);
    let out = simulate(&s, &q).unwrap();
    assert_eq!(
        out.status,
        VmStatus::Success,
        "{receive_atoken} {c:?} {}",
        out.output
    );
    assert!(!out.canonical_state_authenticated);
    if !receive_atoken {
        let reference = check_payment(c);
        // Remove only the two legacy diagnostic WETH balance words.
        assert_eq!(
            out.output,
            reference.output[..2 + 22 * 64].to_owned() + &reference.output[2 + 24 * 64..]
        );
        assert_eq!(out.logs, reference.logs);
        assert_eq!(storage_changes(&out), storage_changes(&reference));
        return out;
    }
    let t = &c.underlying.transfer;
    let reference = check_transfer(t);
    let repay = t.debt.repayment;
    let mut expected = storage_changes(&reference);
    assert_eq!(
        out.output,
        reference.output
            + &encoded(&[
                c.underlying.virtual_balance,
                U256::ZERO,
                U256::ZERO,
                c.wallet - repay,
                c.vault + repay,
                c.allowance - repay,
            ])[2..]
    );
    let mut logs = reference.logs;
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
        &[repay, t.amount, addr(t.recipient), U256::from(1)],
    ));
    assert_eq!(out.logs, logs);
    let pool = expected.get_mut(POOL).unwrap();
    for (slot, value) in [
        (
            14,
            c.underlying.deficit | (U256::from(t.reserve_id) << 168usize),
        ),
        (19, c.underlying.virtual_balance << 128usize),
    ] {
        if value == U256::ZERO {
            pool.remove(&slot.to_string());
        } else {
            pool.insert(slot.to_string(), value.to_string());
        }
    }
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
    assert!(out.logs.iter().all(|l| l.address != COLLATERAL));
    out
}
#[test]
fn both_original_delivery_branches_pay_usdc_and_export_distinct_closed_examples() {
    let c = PaymentCase::default();
    for receive in [false, true] {
        let out = check_delivery(&c, receive);
        if let Ok(path) = std::env::var("NQC_MINER_DELIVERY_EVIDENCE_DIR") {
            let dir =
                std::path::Path::new(&path).join(if receive { "atoken" } else { "underlying" });
            std::fs::create_dir_all(&dir).unwrap();
            let (snapshot, call) = delivery_setup(&c, receive);
            for (name, value) in [
                (
                    "input.json",
                    serde_json::json!({"snapshot":snapshot,"call":call}),
                ),
                ("output.json", serde_json::to_value(&out).unwrap()),
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
fn seeded_both_modes_match_independent_delivery_models_and_payment_state() {
    let mut rng = ChaCha8Rng::seed_from_u64(0x00ac_7000_2026);
    for n in 0..80 {
        let mut c = PaymentCase::default();
        c.underlying.transfer.amount = U256::from(rng.gen_range(1u64..=140));
        c.underlying.transfer.fee = U256::from(rng.gen_range(0u64..=10));
        c.underlying.transfer.debt.repayment = U256::from(rng.gen_range(2u64..=140));
        if n % 5 == 0 {
            c.underlying.transfer.recipient = TREASURY;
        }
        if n % 3 == 0 {
            c.underlying.transfer.rewards.rewards.clear();
        }
        let repay = c.underlying.transfer.debt.repayment;
        c.wallet = repay + U256::from(rng.gen_range(0u64..10000));
        c.allowance = if n % 4 == 0 { U256::MAX } else { repay };
        c.vault = U256::from(rng.gen_range(0u64..10000));
        for receive in [false, true] {
            check_delivery(&c, receive);
        }
    }
}
#[test]
fn exhausted_collateral_capped_fee_zero_fee_and_treasury_alias_work_in_both_modes() {
    for (amount, fee, recipient) in [
        (40, 0, CALLER),
        (148, 10, CALLER),
        (150, 10, CALLER),
        (40, 10, TREASURY),
    ] {
        let mut c = PaymentCase::default();
        c.underlying.transfer.amount = U256::from(amount);
        c.underlying.transfer.fee = U256::from(fee);
        c.underlying.transfer.recipient = recipient;
        for receive in [false, true] {
            check_delivery(&c, receive);
        }
    }
}
#[test]
fn atoken_mode_does_not_access_weth_or_collateral_rate_witnesses_or_burn_supply() {
    let mut c = PaymentCase::default();
    // These invalid burn-path values are irrelevant to aToken transfer.
    c.underlying.virtual_balance = U256::ZERO;
    c.underlying.vault = U256::ZERO;
    c.underlying.factor = U256::from(10001);
    let out = check_delivery(&c, true);
    let token = storage_changes(&out).remove(ATOKEN).unwrap();
    assert!(
        !token.contains_key("54"),
        "aToken total supply must stay unchanged"
    );
    let (s, q) = delivery_setup(&c, false);
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Revert);
    assert_no_contract_changes(&out);
}
#[test]
fn underlying_mode_still_requires_weth_and_collateral_rate_witnesses() {
    let (original, q) = delivery_setup(&PaymentCase::default(), false);
    for address in [COLLATERAL, STRATEGY] {
        let mut s = original.clone();
        if address == COLLATERAL {
            s.accounts.retain(|a| a.address != COLLATERAL);
        } else {
            s.accounts
                .iter_mut()
                .find(|a| a.address == STRATEGY)
                .unwrap()
                .storage
                .remove(&mapping(COLLATERAL, 0).to_string());
        }
        assert!(simulate(&s, &q).is_err());
    }
}
#[test]
fn all_usdc_payment_rejections_roll_back_both_collateral_modes() {
    let c = PaymentCase::default();
    let f = payment_fixture();
    for receive in [false, true] {
        let (original, q) = delivery_setup(&c, receive);
        for (slot, value, error) in [
            (
                mapping(CALLER, 9),
                U256::from(39),
                "ERC20: transfer amount exceeds balance",
            ),
            (
                allowance_slot(CALLER),
                U256::from(39),
                "ERC20: transfer amount exceeds allowance",
            ),
            (U256::from(1), U256::from(1) << 160usize, "Pausable: paused"),
            (
                mapping(POOL, 9),
                U256::from(1) << 255usize,
                "Blacklistable: account is blacklisted",
            ),
            (
                mapping(CALLER, 9),
                (U256::from(1) << 255usize) | c.wallet,
                "Blacklistable: account is blacklisted",
            ),
            (
                mapping(DEBT_VAULT, 9),
                (U256::from(1) << 255usize) | c.vault,
                "Blacklistable: account is blacklisted",
            ),
            (
                mapping(DEBT_VAULT, 9),
                (U256::from(1) << 255usize) - U256::from(1),
                "FiatTokenV2_2: Balance exceeds (2^255 - 1)",
            ),
            (
                addr(f["contracts"]["usdc-proxy"]["admin_slot"].as_str().unwrap()),
                addr(POOL),
                "Cannot call fallback function from the proxy admin",
            ),
        ] {
            let mut s = original.clone();
            s.accounts
                .iter_mut()
                .find(|a| a.address == ASSET)
                .unwrap()
                .storage
                .insert(slot.to_string(), value.to_string());
            payment_revert(&s, &q, error);
        }
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
}
#[test]
fn missing_usdc_account_implementation_routing_and_approval_fail_closed_in_both_modes() {
    let c = PaymentCase::default();
    let f = payment_fixture();
    for receive in [false, true] {
        let (original, q) = delivery_setup(&c, receive);
        for slot in [
            allowance_slot(CALLER),
            mapping(CALLER, 9),
            mapping(DEBT_VAULT, 9),
            mapping(POOL, 9),
            U256::from(1),
            addr(
                f["contracts"]["usdc-proxy"]["implementation_slot"]
                    .as_str()
                    .unwrap(),
            ),
            addr(f["contracts"]["usdc-proxy"]["admin_slot"].as_str().unwrap()),
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
            assert!(simulate(&s, &q).is_err());
        }
        for address in [ASSET, USDC_IMPL] {
            let mut s = original.clone();
            s.accounts.retain(|a| a.address != address);
            assert!(simulate(&s, &q).is_err());
        }
    }
}
#[test]
fn treasury_failure_precedes_payment_pause_and_reverts_both_modes() {
    let mut c = PaymentCase::default();
    c.underlying.transfer.balances[2] = (U256::from(1) << 120usize) - U256::from(1);
    for receive in [false, true] {
        let (mut s, q) = delivery_setup(&c, receive);
        s.accounts
            .iter_mut()
            .find(|a| a.address == ASSET)
            .unwrap()
            .storage
            .insert("1".into(), (U256::from(1) << 160usize).to_string());
        let out = simulate(&s, &q).unwrap();
        assert_eq!(out.status, VmStatus::Revert);
        assert_eq!(
            out.output,
            hex(&keccak256("Panic(uint256)")[..4]) + &encoded(&[U256::from(0x11)])[2..]
        );
        assert_no_contract_changes(&out);
    }
}
#[test]
fn invalid_boolean_or_truncated_mode_is_rejected_before_contract_changes() {
    let (s, q) = delivery_setup(&PaymentCase::default(), true);
    for payload in [
        q.calldata[..q.calldata.len() - 64].to_string(),
        q.calldata[..q.calldata.len() - 64].to_owned() + &encoded(&[U256::from(2)])[2..],
    ] {
        let mut q = q.clone();
        q.calldata = payload;
        let out = simulate(&s, &q).unwrap();
        assert_eq!(out.status, VmStatus::Revert);
        assert_eq!(out.output, "0x");
        assert_no_contract_changes(&out);
    }
}

#[path = "aave_prelude_execution.rs"]
mod prelude_execution;
