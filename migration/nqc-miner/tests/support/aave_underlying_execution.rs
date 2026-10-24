//! Complete observed WETH runtime; source executable prefix matches, metadata does not.
//! Original collateral burn helper, actual aToken/rewards/rates; synthetic Pool/state.
use super::*;
const UNDER_SIGNATURE: &str = "calculate((uint256,uint256,uint256,uint256,uint128,uint128,uint16,uint256,uint256,address,address,uint256,uint256,uint256,uint256,uint256,uint256,uint16,uint128,uint256,uint256,uint256,uint128))";
fn underlying_fixture() -> Value {
    serde_json::from_str(include_str!(
        "../../fixtures/aave_underlying_execution.json"
    ))
    .unwrap()
}
#[derive(Clone, Debug)]
struct UnderCase {
    transfer: TransferCase,
    virtual_balance: U256,
    scaled_debt: U256,
    borrow_index: U256,
    factor: U256,
    deficit: U256,
    vault: U256,
    wallet: U256,
    rates: [u32; 4],
}
impl Default for UnderCase {
    fn default() -> Self {
        Self {
            transfer: TransferCase::default(),
            virtual_balance: U256::from(1000),
            scaled_debt: U256::from(2000),
            borrow_index: U256::from(12 * RAY / 10),
            factor: U256::from(1000),
            deficit: U256::from(3),
            vault: U256::from(1000),
            wallet: U256::from(13),
            rates: [8000, 100, 400, 6000],
        }
    }
}
fn underlying_setup(c: &UnderCase) -> (PinnedSnapshot, SandboxCall) {
    let t = &c.transfer;
    let (mut s, mut q) = transfer_setup(t);
    let f = underlying_fixture();
    let code = f["contracts"]["AaveUnderlyingExecutionHarness"]["runtime_code"]
        .as_str()
        .unwrap();
    let pool = s.accounts.iter_mut().find(|a| a.address == POOL).unwrap();
    pool.runtime_code = code.into();
    pool.code_hash = format!("{:#x}", keccak256(decode_hex(code).unwrap()));
    let token = s
        .accounts
        .iter_mut()
        .find(|a| a.address == t.token)
        .unwrap();
    token
        .storage
        .insert("61".into(), addr(COLLATERAL).to_string());
    let mut weth = account(
        COLLATERAL,
        f["contracts"]["WETH9"]["runtime_code"].as_str().unwrap(),
    );
    weth.storage
        .insert(mapping(t.token, 3).to_string(), c.vault.to_string());
    weth.storage
        .insert(mapping(t.recipient, 3).to_string(), c.wallet.to_string());
    s.accounts.push(weth);
    s.accounts
        .iter_mut()
        .find(|a| a.address == STRATEGY)
        .unwrap()
        .storage
        .insert(
            mapping(COLLATERAL, 0).to_string(),
            (U256::from(c.rates[0])
                | (U256::from(c.rates[1]) << 16usize)
                | (U256::from(c.rates[2]) << 48usize)
                | (U256::from(c.rates[3]) << 80usize))
                .to_string(),
        );
    let selector = hex(&keccak256(UNDER_SIGNATURE)[..4]);
    assert_eq!(
        &selector[2..],
        f["contracts"]["AaveUnderlyingExecutionHarness"]["selectors"][UNDER_SIGNATURE]
    );
    q.calldata = selector
        + &q.calldata[10..]
        + &encoded(&[
            c.virtual_balance,
            c.scaled_debt,
            c.borrow_index,
            c.factor,
            c.deficit,
        ])[2..];
    (s, q)
}
fn model_burn(
    c: &UnderCase,
    token: &mut BTreeMap<String, String>,
    rewards: &mut BTreeMap<String, String>,
    logs: &mut Vec<VmLog>,
) -> U256 {
    let t = &c.transfer;
    let scaled = scaled_ceil(t.amount, t.index);
    let slot = mapping(USER, 52);
    let prior = read_slot(token, slot);
    let balance = prior & ((U256::from(1) << 120usize) - U256::from(1));
    let previous = floor_balance(balance, prior >> 128usize);
    let next = floor_balance(balance - scaled, t.index);
    let increase = floor_balance(balance, t.index) - previous;
    token.insert(
        slot.to_string(),
        ((balance - scaled) | (prior & (U256::from(255) << 120usize)) | (t.index << 128usize))
            .to_string(),
    );
    token.insert("54".into(), (t.total - scaled).to_string());
    accrue(t, USER, balance, rewards, logs);
    if next > previous {
        logs.push(event(
            t.token,
            "Transfer(address,address,uint256)",
            &[ZERO, USER],
            &[next - previous],
        ));
        logs.push(event(
            t.token,
            "Mint(address,address,uint256,uint256,uint256)",
            &[USER, USER],
            &[next - previous, increase, t.index],
        ));
    } else {
        logs.push(event(
            t.token,
            "Transfer(address,address,uint256)",
            &[USER, ZERO],
            &[previous - next],
        ));
        logs.push(event(
            t.token,
            "Burn(address,address,uint256,uint256,uint256)",
            &[USER, t.recipient],
            &[previous - next, increase, t.index],
        ));
    }
    logs.push(event(
        COLLATERAL,
        "Transfer(address,address,uint256)",
        &[t.token, t.recipient],
        &[t.amount],
    ));
    scaled
}
fn check_underlying(c: &UnderCase) -> SandboxOutcome {
    let t = &c.transfer;
    let (d, empty, clear) = effective_debt(t);
    let reference = check_real(&d, &t.rewards);
    let (s, q) = underlying_setup(c);
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Success, "{c:?} {}", out.output);
    assert!(!out.canonical_state_authenticated);
    let rate_case = Case {
        virtual_balance: c.virtual_balance - t.amount,
        repayment: U256::ZERO,
        rates: c.rates,
        factor: c.factor,
        ..Case::default()
    };
    let (liquidity, variable) = rates(&rate_case, ceil(c.scaled_debt, c.borrow_index), c.deficit);
    let mut logs = vec![];
    if clear {
        logs.push(event(
            POOL,
            "ReserveUsedAsCollateralDisabled(address,address)",
            &[COLLATERAL, USER],
            &[],
        ));
    }
    logs.extend(reference.logs);
    logs.push(event(
        POOL,
        "ReserveDataUpdated(address,uint256,uint256,uint256,uint256,uint256)",
        &[COLLATERAL],
        &[liquidity, U256::ZERO, variable, t.index, c.borrow_index],
    ));
    let before: BTreeMap<_, _> = s
        .accounts
        .iter()
        .map(|a| (a.address.clone(), a.storage.clone()))
        .collect();
    let mut after = before.clone();
    for delta in reference.account_deltas {
        if !delta.storage.is_empty() {
            after.get_mut(&delta.address).unwrap().extend(delta.storage);
        }
    }
    let pool = after.get_mut(POOL).unwrap();
    for (slot, value) in [
        (12, liquidity << 128usize),
        (13, variable << 128usize),
        (14, c.deficit | (U256::from(t.reserve_id) << 168usize)),
        (19, (c.virtual_balance - t.amount) << 128usize),
    ] {
        pool.insert(slot.to_string(), value.to_string());
    }
    let mut token = after.remove(t.token).unwrap();
    let mut rewards = after.remove(REWARDS).unwrap();
    let scaled = model_burn(c, &mut token, &mut rewards, &mut logs);
    let mut fee = t.fee;
    let mut post = t.clone();
    post.total -= scaled;
    if fee != U256::ZERO {
        let balance =
            read_slot(&token, mapping(USER, 52)) & ((U256::from(1) << 120usize) - U256::from(1));
        let mut amount_scaled = scaled_ceil(fee, t.index);
        if amount_scaled > balance {
            amount_scaled = balance;
            fee = floor_balance(balance, t.index);
        }
        model_transfer(
            &post,
            TREASURY,
            fee,
            amount_scaled,
            &mut token,
            &mut rewards,
            &mut logs,
        );
    }
    let received = c.wallet.wrapping_add(t.amount);
    let weth = after.get_mut(COLLATERAL).unwrap();
    weth.insert(
        mapping(t.token, 3).to_string(),
        (c.vault - t.amount).to_string(),
    );
    weth.insert(mapping(t.recipient, 3).to_string(), received.to_string());
    let mut words = vec![];
    for user in [USER, t.recipient, TREASURY] {
        words.push(
            read_slot(&token, mapping(user, 52)) & ((U256::from(1) << 120usize) - U256::from(1)),
        );
    }
    words.push(t.total - scaled);
    for user in [USER, t.recipient, TREASURY] {
        words.push(read_slot(&token, mapping(user, 52)) >> 128usize);
    }
    words.extend([
        fee,
        U256::from(empty),
        c.virtual_balance - t.amount,
        liquidity,
        variable,
        c.vault - t.amount,
        received,
    ]);
    assert_eq!(
        out.output,
        reference.output + &encoded(&words)[2..],
        "{c:?}"
    );
    assert_eq!(out.logs, logs, "{c:?}");
    after.insert(t.token.into(), token);
    after.insert(REWARDS.into(), rewards);
    let expected: BTreeMap<_, _> = after
        .into_iter()
        .filter_map(|(address, mut slots)| {
            slots.retain(|k, v| before[&address].get(k) != Some(v));
            if slots.is_empty() {
                None
            } else {
                Some((address, slots))
            }
        })
        .collect();
    let actual: BTreeMap<_, _> = out
        .account_deltas
        .iter()
        .filter(|d| !d.storage.is_empty())
        .map(|d| (d.address.clone(), d.storage.clone()))
        .collect();
    assert_eq!(actual, expected, "{c:?}");
    out
}
fn underlying_revert(c: &UnderCase, error: &str) {
    let (s, q) = underlying_setup(c);
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Revert);
    assert_eq!(out.output, error);
    assert_no_contract_changes(&out);
}
#[test]
fn original_collateral_burn_transfers_actual_weth_and_exports_closed_example() {
    let c = UnderCase::default();
    let out = check_underlying(&c);
    if let Ok(path) = std::env::var("NQC_MINER_UNDERLYING_EVIDENCE_DIR") {
        let dir = std::path::Path::new(&path);
        std::fs::create_dir(dir).unwrap();
        let (snapshot, call) = underlying_setup(&c);
        for (name, value) in [
            (
                "input.json",
                serde_json::json!({"snapshot":snapshot,"call":call}),
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
fn burn_exhaustion_cap_zero_fee_and_interest_mint_burn_branches() {
    let c = UnderCase::default();
    for (amount, fee) in [(1, 0), (40, 0), (100, 10), (148, 2), (150, 2)] {
        check_underlying(&UnderCase {
            transfer: TransferCase {
                amount: U256::from(amount),
                fee: U256::from(fee),
                ..c.transfer.clone()
            },
            ..c.clone()
        });
    }
    check_underlying(&UnderCase {
        transfer: TransferCase {
            recipient: TREASURY,
            ..c.transfer.clone()
        },
        ..c.clone()
    });
    check_underlying(&UnderCase {
        scaled_debt: U256::ZERO,
        ..c.clone()
    });
    check_underlying(&UnderCase {
        virtual_balance: c.transfer.amount,
        ..c.clone()
    });
    check_underlying(&UnderCase {
        transfer: TransferCase {
            rewards: Config {
                rewards: vec![],
                ..Config::default()
            },
            ..c.transfer
        },
        ..c
    });
}
#[test]
fn seeded_original_burn_actual_weth_and_capped_fee_match_independent_results() {
    let mut rng = ChaCha8Rng::seed_from_u64(0x00be_7000_2026);
    for n in 0..240 {
        let balance = rng.gen_range(2u64..100_000);
        let index = U256::from(RAY) + U256::from(rng.gen_range(0u128..3 * RAY));
        let max = floor_balance(U256::from(balance), index).to::<u64>();
        let amount = rng.gen_range(1..=max);
        let mut t = TransferCase {
            index,
            amount: U256::from(amount),
            fee: U256::from(rng.gen_range(0..=max - amount)),
            balances: [
                U256::from(balance),
                U256::from(rng.gen_range(0u64..5000)),
                U256::from(rng.gen_range(0u64..5000)),
            ],
            total: U256::from(balance + 20_000),
            total_base: floor_balance(U256::from(balance), index),
            ..TransferCase::default()
        };
        t.rewards.rewards = match n % 3 {
            0 => vec![],
            1 => vec![Reward::default()],
            _ => vec![
                Reward::default(),
                Reward {
                    address: REWARD_TWO,
                    emission: U256::from(43),
                    ..Reward::default()
                },
            ],
        };
        t.rewards.decimals = (n % 19) as u8;
        if n % 7 == 0 {
            t.recipient = TREASURY;
        }
        if n % 5 == 0 {
            t.total_base += U256::from(100);
        }
        let c = UnderCase {
            transfer: t,
            virtual_balance: U256::from(amount + rng.gen_range(0u64..200_000)),
            scaled_debt: U256::from(rng.gen_range(0u64..2_000_000)),
            factor: U256::from(rng.gen_range(0u64..=10_000)),
            deficit: U256::from(rng.gen_range(0u64..3000)),
            vault: U256::from(amount + 5000),
            wallet: U256::from(rng.gen_range(0u64..5000)),
            ..UnderCase::default()
        };
        check_underlying(&c);
    }
}
#[test]
fn underlying_insufficient_balance_reverts_prior_debt_rates_burn_and_rewards() {
    let c = UnderCase::default();
    underlying_revert(
        &UnderCase {
            vault: c.transfer.amount - U256::from(1),
            ..c
        },
        "0x",
    );
}
#[test]
fn post_weth_fee_and_reward_failure_roll_back_the_underlying_transfer_too() {
    let c = UnderCase::default();
    let panic = hex(&keccak256("Panic(uint256)")[..4]) + &encoded(&[U256::from(0x11)])[2..];
    let mut t = c.transfer.clone();
    t.balances[2] = (U256::from(1) << 120usize) - U256::from(1);
    underlying_revert(
        &UnderCase {
            transfer: t,
            ..c.clone()
        },
        &panic,
    );
    let (mut s, q) = underlying_setup(&c);
    let state = &mut s
        .accounts
        .iter_mut()
        .find(|a| a.address == REWARDS)
        .unwrap()
        .storage;
    let slot = map_word(
        addr(TREASURY),
        reward_base(ATOKEN, REWARD_ONE) + U256::from(1),
    );
    state.insert(
        slot.to_string(),
        (U256::from(900_000) | (U256::from(u128::MAX) << 104usize)).to_string(),
    );
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Revert);
    assert_eq!(out.output, panic);
    assert_no_contract_changes(&out);
}
#[test]
fn collateral_reserve_failure_and_zero_burn_revert_earlier_debt() {
    let c = UnderCase::default();
    let panic = hex(&keccak256("Panic(uint256)")[..4]) + &encoded(&[U256::from(0x11)])[2..];
    underlying_revert(
        &UnderCase {
            virtual_balance: c.transfer.amount - U256::from(1),
            ..c.clone()
        },
        &panic,
    );
    underlying_revert(
        &UnderCase {
            factor: U256::from(10001),
            ..c.clone()
        },
        &panic,
    );
    underlying_revert(
        &UnderCase {
            transfer: TransferCase {
                amount: U256::ZERO,
                ..c.transfer.clone()
            },
            ..c
        },
        &hex(&keccak256("InvalidBurnAmount()")[..4]),
    );
}
#[test]
fn missing_underlying_code_balance_slot_token_asset_or_rate_witness_fails_closed() {
    let c = UnderCase::default();
    let (original, q) = underlying_setup(&c);
    for (address, slot) in [
        (COLLATERAL, mapping(ATOKEN, 3)),
        (COLLATERAL, mapping(CALLER, 3)),
        (ATOKEN, U256::from(61)),
        (STRATEGY, mapping(COLLATERAL, 0)),
    ] {
        let mut s = original.clone();
        assert!(s
            .accounts
            .iter_mut()
            .find(|a| a.address == address)
            .unwrap()
            .storage
            .remove(&slot.to_string())
            .is_some());
        assert!(simulate(&s, &q).is_err(), "{address} {slot}");
    }
    let mut s = original;
    s.accounts.retain(|a| a.address != COLLATERAL);
    assert!(simulate(&s, &q).is_err());
}
#[test]
fn legacy_weth_uint256_recipient_addition_wraps_in_artificial_boundary_state() {
    // Solidity 0.4.19 has unchecked uint256 arithmetic. This supplied state is
    // deliberately impossible as a normally backed WETH ledger; no economic claim.
    check_underlying(&UnderCase {
        wallet: U256::MAX,
        ..UnderCase::default()
    });
}

#[path = "aave_payment_execution.rs"]
mod payment_execution;
