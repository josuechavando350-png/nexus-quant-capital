//! Original receive-aToken/fee sequence plus real debt, token, rate and rewards code.
//! All balances, aggregate values and Pool entrypoint are explicitly synthetic.
use super::*;
const ATOKEN: &str = "0x4d5f47fa6a74757f35c14fd3a6ef8e3c9bc514e8";
const A_IMPL: &str = "0xadc45df3cf1584624c97338bef33363bf5b97ada";
const TREASURY: &str = "0x464c71f6c2f760dda6093dcb91c24c39e5d6e18c";
const COLLATERAL: &str = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2";
const ZERO: &str = "0x0000000000000000000000000000000000000000";
const SIGNATURE: &str = "calculate((uint256,uint256,uint256,uint256,uint128,uint128,uint16,uint256,uint256,address,address,uint256,uint256,uint256,uint256,uint256,uint256,uint16))";
fn transfer_fixture() -> Value {
    serde_json::from_str(include_str!("../../fixtures/aave_transfer_execution.json")).unwrap()
}
#[derive(Clone, Debug)]
struct TransferCase {
    debt: Case,
    rewards: Config,
    token: &'static str,
    recipient: &'static str,
    index: U256,
    amount: U256,
    fee: U256,
    balances: [U256; 3], // borrower, liquidator, treasury
    previous: [U256; 3],
    total: U256,
    price: U256,
    unit: U256,
    total_base: U256,
    reserve_id: u16,
}
impl Default for TransferCase {
    fn default() -> Self {
        Self {
            debt: Case::default(),
            rewards: Config::default(),
            token: ATOKEN,
            recipient: CALLER,
            index: U256::from(3 * RAY / 2),
            amount: U256::from(40),
            fee: U256::from(10),
            balances: [U256::from(100), U256::from(20), U256::from(7)],
            previous: [U256::from(RAY); 3],
            total: U256::from(1000),
            price: U256::from(1),
            unit: U256::from(1),
            total_base: U256::from(150),
            reserve_id: 2,
        }
    }
}
fn packed_user(balance: U256, delegation: u8, index: U256) -> U256 {
    balance | (U256::from(delegation) << 120usize) | (index << 128usize)
}
fn transfer_setup(c: &TransferCase) -> (PinnedSnapshot, SandboxCall) {
    let (mut s, mut q) = real_setup(&c.debt, &c.rewards);
    let f = transfer_fixture();
    let code = |name: &str| f["contracts"][name]["runtime_code"].as_str().unwrap();
    let pool = s.accounts.iter_mut().find(|a| a.address == POOL).unwrap();
    *pool = account(POOL, code("AaveTransferExecutionHarness"));
    pool.storage = (0..=20).map(|n| (n.to_string(), "0".into())).collect();
    let sample = f["proxy_samples"]
        .as_array()
        .unwrap()
        .iter()
        .find(|p| p["proxy"] == c.token && p["kind"] == "a_token")
        .unwrap();
    let mut token = account(c.token, code(sample["proxy_contract"].as_str().unwrap()));
    token
        .storage
        .insert(implementation_slot().to_string(), addr(A_IMPL).to_string());
    token.storage.insert("54".into(), c.total.to_string());
    for (i, user) in [USER, CALLER, TREASURY].iter().enumerate() {
        token.storage.insert(
            mapping(user, 52).to_string(),
            packed_user(c.balances[i], i as u8, c.previous[i]).to_string(),
        );
    }
    s.accounts.push(token);
    s.accounts.push(account(A_IMPL, code("ATokenInstance")));
    let rewards = s
        .accounts
        .iter_mut()
        .find(|a| a.address == REWARDS)
        .unwrap();
    rewards
        .storage
        .extend(controller_storage(c.token, &c.rewards));
    for r in &c.rewards.rewards {
        for user in [CALLER, TREASURY] {
            rewards.storage.insert(
                map_word(addr(user), reward_base(c.token, r.address) + U256::from(1)).to_string(),
                (r.user_index | (U256::from(r.accrued) << 104usize)).to_string(),
            );
        }
    }
    let d = &c.debt;
    let words = [
        d.debt,
        d.repayment,
        d.index,
        d.cached,
        d.deficit,
        d.virtual_balance,
        U256::from(d.reserve_id),
        d.config,
        d.factor,
        addr(c.token),
        addr(c.recipient),
        c.index,
        c.amount,
        c.fee,
        c.price,
        c.unit,
        c.total_base,
        U256::from(c.reserve_id),
    ];
    let selector = hex(&keccak256(SIGNATURE)[..4]);
    assert_eq!(
        &selector[2..],
        f["contracts"]["AaveTransferExecutionHarness"]["selectors"][SIGNATURE]
    );
    q.calldata = selector + &encoded(&words)[2..];
    (s, q)
}
fn floor_balance(balance: U256, index: U256) -> U256 {
    balance * index / U256::from(RAY)
}
fn scaled_ceil(amount: U256, index: U256) -> U256 {
    let p = amount * U256::from(RAY);
    p / index + U256::from(p % index != U256::ZERO)
}
fn read_slot(state: &BTreeMap<String, String>, slot: U256) -> U256 {
    state[&slot.to_string()].parse().unwrap()
}
fn accrue(
    c: &TransferCase,
    user: &str,
    balance: U256,
    state: &mut BTreeMap<String, String>,
    logs: &mut Vec<VmLog>,
) {
    let mask = (U256::from(1) << 104usize) - U256::from(1);
    let unit = U256::from(10).pow(U256::from(c.rewards.decimals));
    for r in &c.rewards.rewards {
        let base = reward_base(c.token, r.address);
        let packed = read_slot(state, base);
        let old_index = packed & mask;
        let last = ((packed >> 192usize) & U256::from(u32::MAX)).to::<u32>();
        let mut index = old_index;
        if r.emission != U256::ZERO
            && c.total != U256::ZERO
            && u64::from(last) != c.rewards.now
            && last < r.end
        {
            index += r.emission
                * U256::from(c.rewards.now.min(u64::from(r.end)) - u64::from(last))
                * unit
                / c.total;
        }
        let user_slot = map_word(addr(user), base + U256::from(1));
        let before = read_slot(state, user_slot);
        let user_index = before & mask;
        let newly = if user_index != index && balance != U256::ZERO {
            balance * (index - user_index) / unit
        } else {
            U256::ZERO
        };
        state.insert(
            base.to_string(),
            packed_reward(r, index, c.rewards.now).to_string(),
        );
        state.insert(
            user_slot.to_string(),
            (index | (((before >> 104usize) + newly) << 104usize)).to_string(),
        );
        if index != old_index || index != user_index {
            logs.push(event(
                REWARDS,
                "Accrued(address,address,address,uint256,uint256,uint256)",
                &[c.token, r.address, user],
                &[index, index, newly],
            ));
        }
    }
}
fn model_transfer(
    c: &TransferCase,
    to: &str,
    amount: U256,
    scaled: U256,
    token: &mut BTreeMap<String, String>,
    rewards: &mut BTreeMap<String, String>,
    logs: &mut Vec<VmLog>,
) {
    let from_slot = mapping(USER, 52);
    let to_slot = mapping(to, 52);
    let from = read_slot(token, from_slot);
    let recipient = read_slot(token, to_slot);
    let mask = (U256::from(1) << 120usize) - U256::from(1);
    let bal_from = from & mask;
    let bal_to = recipient & mask;
    let increase_from =
        floor_balance(bal_from, c.index) - floor_balance(bal_from, from >> 128usize);
    let increase_to = floor_balance(bal_to, c.index) - floor_balance(bal_to, recipient >> 128usize);
    let delegation_mask = U256::from(255) << 120usize;
    token.insert(
        from_slot.to_string(),
        ((bal_from - scaled) | (from & delegation_mask) | (c.index << 128usize)).to_string(),
    );
    let to_after_debit = read_slot(token, to_slot) & mask;
    token.insert(
        to_slot.to_string(),
        ((to_after_debit + scaled) | (recipient & delegation_mask) | (c.index << 128usize))
            .to_string(),
    );
    accrue(c, USER, bal_from, rewards, logs);
    if to != USER {
        accrue(c, to, bal_to, rewards, logs);
    }
    for (user, increase) in [
        (USER, increase_from),
        (to, if to == USER { U256::ZERO } else { increase_to }),
    ] {
        if increase != U256::ZERO {
            logs.push(event(
                c.token,
                "Transfer(address,address,uint256)",
                &[ZERO, user],
                &[increase],
            ));
            logs.push(event(
                c.token,
                "Mint(address,address,uint256,uint256,uint256)",
                &[POOL, user],
                &[increase, increase, c.index],
            ));
        }
    }
    logs.push(event(
        c.token,
        "Transfer(address,address,uint256)",
        &[USER, to],
        &[amount],
    ));
    logs.push(event(
        c.token,
        "BalanceTransfer(address,address,uint256,uint256)",
        &[USER, to],
        &[scaled, c.index],
    ));
}
fn effective_debt(c: &TransferCase) -> (Case, bool, bool) {
    let consumed =
        (scaled_ceil(c.amount, c.index) + scaled_ceil(c.fee, c.index)).min(c.balances[0]);
    let empty = floor_balance(consumed, c.index) * c.price / c.unit == c.total_base;
    let clear = consumed == c.balances[0] || empty;
    let mut d = c.debt.clone();
    d.no_collateral = empty;
    if clear {
        d.config &= !(U256::from(1) << (usize::from(c.reserve_id) * 2 + 1));
    }
    (d, empty, clear)
}
fn check_transfer(c: &TransferCase) -> SandboxOutcome {
    let (d, empty, clear) = effective_debt(c);
    let reference = check_real(&d, &c.rewards);
    let (s, q) = transfer_setup(c);
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Success, "{c:?} {}", out.output);
    assert!(!out.canonical_state_authenticated);
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
    after.get_mut(POOL).unwrap().insert(
        "14".into(),
        (U256::from(c.reserve_id) << 168usize).to_string(),
    );
    let mut token = after.remove(c.token).unwrap();
    let mut rewards = after.remove(REWARDS).unwrap();
    model_transfer(
        c,
        c.recipient,
        c.amount,
        scaled_ceil(c.amount, c.index),
        &mut token,
        &mut rewards,
        &mut logs,
    );
    let mut fee = c.fee;
    if fee != U256::ZERO {
        let balance =
            read_slot(&token, mapping(USER, 52)) & ((U256::from(1) << 120usize) - U256::from(1));
        let mut scaled = scaled_ceil(fee, c.index);
        if scaled > balance {
            scaled = balance;
            fee = floor_balance(balance, c.index);
        }
        model_transfer(
            c,
            TREASURY,
            fee,
            scaled,
            &mut token,
            &mut rewards,
            &mut logs,
        );
    }
    let mut words = vec![];
    for user in [USER, c.recipient, TREASURY] {
        words.push(
            read_slot(&token, mapping(user, 52)) & ((U256::from(1) << 120usize) - U256::from(1)),
        );
    }
    words.push(c.total);
    for user in [USER, c.recipient, TREASURY] {
        words.push(read_slot(&token, mapping(user, 52)) >> 128usize);
    }
    words.extend([fee, U256::from(empty)]);
    assert_eq!(
        out.output,
        reference.output + &encoded(&words)[2..],
        "{c:?}"
    );
    assert_eq!(out.logs, logs, "{c:?}");
    after.insert(c.token.into(), token);
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
fn check_transfer_revert(c: &TransferCase, error: &str) {
    let (s, q) = transfer_setup(c);
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Revert);
    assert_eq!(out.output, error);
    assert_no_contract_changes(&out);
}
#[test]
fn real_atoken_transfers_follow_debt_and_cap_fee_from_actual_post_transfer_balance() {
    let c = TransferCase::default();
    let out = check_transfer(&c);
    if let Ok(path) = std::env::var("NQC_MINER_TRANSFER_EVIDENCE_DIR") {
        let dir = std::path::Path::new(&path);
        std::fs::create_dir(dir).unwrap();
        let (snapshot, call) = transfer_setup(&c);
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
    check_transfer(&TransferCase {
        amount: U256::from(148),
        fee: U256::from(2),
        ..c.clone()
    });
    check_transfer(&TransferCase {
        amount: U256::from(150),
        fee: U256::from(2),
        ..c
    });
}
#[test]
fn actual_atoken_covers_zero_fee_zero_transfer_and_recipient_treasury_alias() {
    let c = TransferCase::default();
    for (amount, fee) in [(0, 0), (0, 10), (40, 0), (1, 1)] {
        check_transfer(&TransferCase {
            amount: U256::from(amount),
            fee: U256::from(fee),
            ..c.clone()
        });
    }
    check_transfer(&TransferCase {
        recipient: TREASURY,
        ..c.clone()
    });
    // Standalone sequence permits self-transfer; full liquidation validation rejects it.
    check_transfer(&TransferCase {
        recipient: USER,
        ..c.clone()
    });
    check_transfer(&TransferCase {
        rewards: Config {
            rewards: vec![],
            ..Config::default()
        },
        ..c
    });
}
#[test]
fn collateral_exhaustion_clears_flag_and_creates_deficit_in_same_transaction() {
    let c = TransferCase::default();
    check_transfer(&TransferCase {
        amount: U256::from(148),
        fee: U256::from(2),
        ..c.clone()
    });
    check_transfer(&TransferCase {
        amount: U256::from(148),
        fee: U256::from(2),
        total_base: U256::from(200),
        ..c.clone()
    });
    check_transfer(&TransferCase {
        price: U256::from(1),
        unit: U256::from(1000),
        total_base: U256::ZERO,
        ..c.clone()
    });
    check_transfer(&TransferCase {
        reserve_id: 127,
        debt: Case {
            config: U256::MAX,
            ..c.debt.clone()
        },
        amount: U256::from(148),
        fee: U256::from(2),
        ..c.clone()
    });
    check_transfer_revert(
        &TransferCase {
            reserve_id: 128,
            amount: U256::from(148),
            fee: U256::from(2),
            ..c.clone()
        },
        &hex(&keccak256("InvalidReserveIndex()")[..4]),
    );
    check_transfer(&TransferCase {
        debt: Case {
            config: U256::ZERO,
            ..c.debt.clone()
        },
        amount: U256::from(148),
        fee: U256::from(2),
        ..c
    });
}
#[test]
fn seeded_real_atoken_transfers_check_all_outputs_logs_and_changed_storage() {
    let mut rng = ChaCha8Rng::seed_from_u64(0x00a7_0ce0_2026);
    for n in 0..320 {
        let balance = rng.gen_range(2u64..100_000);
        let index = U256::from(RAY) + U256::from(rng.gen_range(0u128..3 * RAY));
        let max = floor_balance(U256::from(balance), index).to::<u64>();
        let amount = rng.gen_range(0..=max);
        let mut c = TransferCase {
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
        c.previous = [U256::from(RAY), index, U256::from(RAY)];
        c.rewards.decimals = (n % 19) as u8;
        c.rewards.rewards = match n % 3 {
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
        if n % 5 == 0 {
            c.total_base += U256::from(100);
        }
        if n % 7 == 0 {
            c.recipient = TREASURY;
        }
        if n % 11 == 0 {
            c.debt.debt = U256::ZERO;
            c.debt.repayment = U256::ZERO;
        }
        check_transfer(&c);
    }
}
#[test]
fn actual_transfers_execute_through_each_retained_atoken_proxy_family() {
    for token in [
        ATOKEN,
        "0x98c23e9d8f34fefb1b7bd6a91b7ff122f4e16f5c",
        "0x4f5923fc5fd4a93352581b38b7cd26943012decf",
        "0x2edff5af94334fbd7c38ae318edf1c40e072b73b",
    ] {
        check_transfer(&TransferCase {
            token,
            ..TransferCase::default()
        });
    }
}
#[test]
fn late_transfer_and_fee_failures_roll_back_debt_rates_flags_and_all_rewards() {
    let c = TransferCase::default();
    let panic = hex(&keccak256("Panic(uint256)")[..4]) + &encoded(&[U256::from(0x11)])[2..];
    check_transfer_revert(
        &TransferCase {
            amount: U256::from(151),
            ..c.clone()
        },
        &panic,
    );
    let max = (U256::from(1) << 120usize) - U256::from(1);
    check_transfer_revert(
        &TransferCase {
            balances: [c.balances[0], max, c.balances[2]],
            ..c.clone()
        },
        &panic,
    );
    check_transfer_revert(
        &TransferCase {
            balances: [c.balances[0], c.balances[1], max],
            ..c.clone()
        },
        &panic,
    );
    check_transfer_revert(
        &TransferCase {
            previous: [c.index + U256::from(RAY), c.previous[1], c.previous[2]],
            ..c.clone()
        },
        &panic,
    );
    // Failure occurs only during the treasury callback, after both token transfers.
    let (mut s, q) = transfer_setup(&c);
    let state = &mut s
        .accounts
        .iter_mut()
        .find(|a| a.address == REWARDS)
        .unwrap()
        .storage;
    let slot = map_word(
        addr(TREASURY),
        reward_base(c.token, REWARD_ONE) + U256::from(1),
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
fn transfer_missing_atoken_and_nested_reward_witnesses_fail_closed() {
    let c = TransferCase::default();
    let (original, q) = transfer_setup(&c);
    for (address, slot) in [
        (c.token, implementation_slot()),
        (c.token, mapping(USER, 52)),
        (c.token, mapping(CALLER, 52)),
        (c.token, mapping(TREASURY, 52)),
        (c.token, U256::from(54)),
        (
            REWARDS,
            map_word(
                addr(TREASURY),
                reward_base(c.token, REWARD_ONE) + U256::from(1),
            ),
        ),
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
    s.accounts.retain(|a| a.address != A_IMPL);
    assert!(simulate(&s, &q).is_err());
}
#[test]
fn transfer_entrypoint_denies_non_pool_and_reverts_index_cast_overflow() {
    let c = TransferCase::default();
    let maximum = (U256::from(1) << 120usize) - U256::from(1);
    let index = U256::from(u128::MAX);
    check_transfer(&TransferCase {
        balances: [maximum, U256::ZERO, U256::ZERO],
        total: maximum,
        index,
        previous: [index; 3],
        amount: floor_balance(U256::from(1), index),
        fee: U256::ZERO,
        total_base: floor_balance(maximum, index),
        rewards: Config {
            rewards: vec![],
            ..Config::default()
        },
        ..c.clone()
    });
    let (mut s, mut q) = transfer_setup(&c);
    q.to = c.token.into();
    q.calldata =
        hex(&keccak256("transferOnLiquidation(address,address,uint256,uint256,uint256)")[..4])
            + &encoded(&[addr(USER), addr(CALLER), c.amount, U256::from(27), c.index])[2..];
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Revert);
    assert_eq!(out.output, hex(&keccak256("CallerMustBePool()")[..4]));
    assert_no_contract_changes(&out);
    q.caller = POOL.into();
    q.nonce = 0;
    q.calldata =
        hex(&keccak256("transferOnLiquidation(address,address,uint256,uint256,uint256)")[..4])
            + &encoded(&[
                addr(USER),
                addr(CALLER),
                c.amount,
                U256::from(27),
                U256::from(1) << 128usize,
            ])[2..];
    s.accounts
        .iter_mut()
        .find(|a| a.address == POOL)
        .unwrap()
        .runtime_code = "0x".into();
    s.accounts
        .iter_mut()
        .find(|a| a.address == POOL)
        .unwrap()
        .code_hash = format!("{:#x}", keccak256([]));
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Revert);
    assert_eq!(
        out.output,
        hex(&keccak256("SafeCastOverflowedUintDowncast(uint8,uint256)")[..4])
            + &encoded(&[U256::from(128), U256::from(1) << 128usize])[2..]
    );
    assert_no_contract_changes(&out);
}
