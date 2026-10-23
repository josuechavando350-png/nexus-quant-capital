//! Actual rewards proxy/controller under explicitly supplied synthetic state.
use super::*;
const REWARD_IMPL: &str = "0xe7b67f44ea304dd7f6d215b13686637ff64cd2b2";
const REWARD_ONE: &str = "0x000000000000000000000000000000000000a111";
const REWARD_TWO: &str = "0x000000000000000000000000000000000000a222";
fn real_fixture() -> Value {
    serde_json::from_str(include_str!("../../fixtures/aave_rewards_execution.json")).unwrap()
}
fn map_word(key: U256, slot: U256) -> U256 {
    U256::from_be_bytes(keccak256(decode_hex(&encoded(&[key, slot])).unwrap()).0)
}
#[derive(Clone, Debug)]
struct Reward {
    address: &'static str,
    index: U256,
    emission: U256,
    last: u32,
    end: u32,
    user_index: U256,
    accrued: u128,
}
impl Default for Reward {
    fn default() -> Self {
        Self {
            address: REWARD_ONE,
            index: U256::from(1_000_000),
            emission: U256::from(100),
            last: 900,
            end: 2000,
            user_index: U256::from(900_000),
            accrued: 7,
        }
    }
}
#[derive(Clone, Debug)]
struct Config {
    decimals: u8,
    now: u64,
    rewards: Vec<Reward>,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            decimals: 6,
            now: 1000,
            rewards: vec![Reward::default()],
        }
    }
}
fn asset_base(asset: &str) -> U256 {
    mapping(asset, 1)
}
fn reward_base(asset: &str, reward: &str) -> U256 {
    map_word(addr(reward), asset_base(asset))
}
fn packed_reward(r: &Reward, index: U256, last: u64) -> U256 {
    index
        | (r.emission << 104usize)
        | (U256::from(last) << 192usize)
        | (U256::from(r.end) << 224usize)
}
fn controller_storage(asset: &str, cfg: &Config) -> BTreeMap<String, String> {
    let base = asset_base(asset);
    let mut storage = BTreeMap::from([
        (
            implementation_slot().to_string(),
            addr(REWARD_IMPL).to_string(),
        ),
        (
            (base + U256::from(2)).to_string(),
            (U256::from(cfg.rewards.len()) | (U256::from(cfg.decimals) << 128usize)).to_string(),
        ),
    ]);
    for (i, r) in cfg.rewards.iter().enumerate() {
        let slot = reward_base(asset, r.address);
        storage.insert(
            map_word(U256::from(i), base + U256::from(1)).to_string(),
            addr(r.address).to_string(),
        );
        storage.insert(
            slot.to_string(),
            packed_reward(r, r.index, u64::from(r.last)).to_string(),
        );
        storage.insert(
            map_word(addr(USER), slot + U256::from(1)).to_string(),
            (r.user_index | (U256::from(r.accrued) << 104usize)).to_string(),
        );
    }
    storage
}
fn real_setup(c: &Case, cfg: &Config) -> (PinnedSnapshot, SandboxCall) {
    let (mut s, q) = setup(c, &proxy_fixture());
    let f = real_fixture();
    let mut rewards = account(
        REWARDS,
        f["contracts"]["RealRewardsProxy"]["runtime_code"]
            .as_str()
            .unwrap(),
    );
    rewards.storage = controller_storage(TOKEN, cfg);
    s.accounts.retain(|a| a.address != REWARDS);
    s.accounts.push(rewards);
    s.accounts.push(account(
        REWARD_IMPL,
        f["contracts"]["RewardsController"]["runtime_code"]
            .as_str()
            .unwrap(),
    ));
    s.timestamp = cfg.now;
    (s, q)
}
fn predicted_rewards(
    asset: &str,
    cfg: &Config,
    total: U256,
    balance: U256,
) -> (Vec<VmLog>, BTreeMap<String, String>) {
    assert!(cfg.decimals <= 36 && cfg.now <= u64::from(u32::MAX));
    let unit = U256::from(10).pow(U256::from(cfg.decimals));
    let mut logs = vec![];
    let mut changed = BTreeMap::new();
    let original = controller_storage(asset, cfg);
    for r in &cfg.rewards {
        let mut next = r.index;
        if r.emission != U256::ZERO
            && total != U256::ZERO
            && u64::from(r.last) != cfg.now
            && r.last < r.end
        {
            let elapsed = cfg.now.min(u64::from(r.end)) - u64::from(r.last);
            next += r.emission * U256::from(elapsed) * unit / total;
        }
        assert!(next < (U256::from(1) << 104usize));
        let accrued = if next != r.user_index && balance != U256::ZERO {
            balance * (next - r.user_index) / unit
        } else {
            U256::ZERO
        };
        let slot = reward_base(asset, r.address);
        changed.insert(
            slot.to_string(),
            packed_reward(r, next, cfg.now).to_string(),
        );
        changed.insert(
            map_word(addr(USER), slot + U256::from(1)).to_string(),
            (next | ((U256::from(r.accrued) + accrued) << 104usize)).to_string(),
        );
        if next != r.index || next != r.user_index {
            logs.push(event(
                REWARDS,
                "Accrued(address,address,address,uint256,uint256,uint256)",
                &[asset, r.address, USER],
                &[next, next, accrued],
            ));
        }
    }
    changed.retain(|k, v| original.get(k) != Some(v));
    (logs, changed)
}
fn check_real(c: &Case, cfg: &Config) -> SandboxOutcome {
    // This reference execution itself checks independent debt/token/rate arithmetic.
    let reference = check_success(c, &proxy_fixture());
    let (s, q) = real_setup(c, cfg);
    let out = simulate(&s, &q).unwrap();
    assert_eq!(
        out.status,
        VmStatus::Success,
        "{c:?} {cfg:?} {}",
        out.output
    );
    assert_eq!(out.output, reference.output);
    assert!(!out.canonical_state_authenticated);
    let (mut expected_logs, reward_changes) = if c.debt == U256::ZERO {
        (vec![], BTreeMap::new())
    } else {
        predicted_rewards(TOKEN, cfg, c.total, c.balance)
    };
    expected_logs.extend(reference.logs.into_iter().filter(|l| l.address != REWARDS));
    assert_eq!(out.logs, expected_logs, "{c:?} {cfg:?}");
    let mut expected: BTreeMap<_, _> = reference
        .account_deltas
        .into_iter()
        .filter(|d| !d.storage.is_empty() && d.address != REWARDS)
        .map(|d| (d.address, d.storage))
        .collect();
    if !reward_changes.is_empty() {
        expected.insert(REWARDS.into(), reward_changes);
    }
    let changed: BTreeMap<_, _> = out
        .account_deltas
        .iter()
        .filter(|d| !d.storage.is_empty())
        .map(|d| (d.address.clone(), d.storage.clone()))
        .collect();
    assert_eq!(changed, expected, "{c:?} {cfg:?}");
    out
}
fn check_real_revert(c: &Case, cfg: &Config, error: &str) {
    let (s, q) = real_setup(c, cfg);
    let out = simulate(&s, &q).unwrap();
    assert_eq!(out.status, VmStatus::Revert);
    assert_eq!(out.output, error);
    assert_no_contract_changes(&out);
}
#[test]
fn real_rewards_use_preburn_balance_and_supply_and_export_complete_example() {
    let c = Case::default();
    let cfg = Config::default();
    let out = check_real(&c, &cfg);
    assert_eq!(
        out.logs[0].data,
        encoded(&[
            U256::from(11_000_000),
            U256::from(11_000_000),
            U256::from(1010)
        ])
    );
    if let Ok(path) = std::env::var("NQC_MINER_REWARDS_EVIDENCE_DIR") {
        let directory = std::path::Path::new(&path);
        std::fs::create_dir(directory).unwrap();
        let (snapshot, call) = real_setup(&c, &cfg);
        for (name, value) in [
            (
                "input.json",
                serde_json::json!({"snapshot":snapshot,"call":call}),
            ),
            ("output.json", serde_json::to_value(&out).unwrap()),
        ] {
            use std::io::Write;
            let mut file = std::fs::File::create_new(directory.join(name)).unwrap();
            file.write_all(&serde_json::to_vec_pretty(&value).unwrap())
                .unwrap();
            file.write_all(b"\n").unwrap();
        }
    }
}
#[test]
fn actual_rewards_cover_empty_multiple_zero_emission_expired_and_same_timestamp() {
    let c = Case::default();
    check_real(
        &c,
        &Config {
            rewards: vec![],
            ..Config::default()
        },
    );
    check_real(
        &c,
        &Config {
            rewards: vec![
                Reward::default(),
                Reward {
                    address: REWARD_TWO,
                    emission: U256::from(79),
                    last: 950,
                    end: 975,
                    ..Reward::default()
                },
            ],
            ..Config::default()
        },
    );
    for r in [
        Reward {
            emission: U256::ZERO,
            ..Reward::default()
        },
        Reward {
            end: 900,
            ..Reward::default()
        },
        Reward {
            last: 1000,
            ..Reward::default()
        },
        Reward {
            last: 1000,
            user_index: U256::from(1_000_000),
            ..Reward::default()
        },
    ] {
        check_real(
            &c,
            &Config {
                rewards: vec![r],
                ..Config::default()
            },
        );
    }
    check_real(
        &Case {
            debt: U256::ZERO,
            repayment: U256::ZERO,
            ..Case::default()
        },
        &Config::default(),
    );
}
#[test]
fn seeded_real_rewards_accrual_and_full_debt_composition() {
    let mut rng = ChaCha8Rng::seed_from_u64(0x00ac_c8ed_2026);
    for i in 0..400 {
        let balance = rng.gen_range(10u128..1_000_000_000_000);
        let index = RAY + rng.gen_range(0..3 * RAY);
        let debt = ceil(U256::from(balance), U256::from(index));
        let c = Case {
            balance: U256::from(balance),
            total: U256::from(balance + rng.gen_range(0..10_000_000_000_000u128)),
            debt,
            repayment: debt / U256::from(2),
            index: U256::from(index),
            no_collateral: i % 3 == 0,
            factor: U256::from(rng.gen_range(0..=10000u64)),
            ..Case::default()
        };
        let now = rng.gen_range(10000..1_000_000u64);
        let mut rewards = vec![];
        for address in [REWARD_ONE, REWARD_TWO].iter().take(if i % 10 == 0 {
            0
        } else if i % 3 == 0 {
            2
        } else {
            1
        }) {
            let index = rng.gen_range(1..1_000_000_000_000u64);
            rewards.push(Reward {
                address,
                index: U256::from(index),
                emission: U256::from(rng.gen_range(0..1_000_000u64)),
                last: (now - rng.gen_range(0..10000)) as u32,
                end: (now + rng.gen_range(0..10000)) as u32,
                user_index: U256::from(rng.gen_range(0..=index)),
                accrued: rng.gen_range(0..1_000_000_000),
            });
        }
        check_real(
            &c,
            &Config {
                decimals: rng.gen_range(0..=18),
                now,
                rewards,
            },
        );
    }
    println!("400 seeded real-controller compositions with independent reward arithmetic, complete logs and storage; synthetic state only");
}
#[test]
fn rewards_index_cast_underflow_and_accrual_overflow_revert_token_and_pool() {
    let c = Case::default();
    check_real_revert(
        &c,
        &Config {
            rewards: vec![Reward {
                index: (U256::from(1) << 104usize) - U256::from(1),
                ..Reward::default()
            }],
            ..Config::default()
        },
        &abi_string_error("INDEX_OVERFLOW"),
    );
    check_real_revert(
        &c,
        &Config {
            now: u64::from(u32::MAX) + 1,
            ..Config::default()
        },
        &abi_string_error("SafeCast: value doesn't fit in 32 bits"),
    );
    check_real_revert(
        &c,
        &Config {
            rewards: vec![Reward {
                user_index: U256::from(11_000_001),
                ..Reward::default()
            }],
            ..Config::default()
        },
        &panic(),
    );
    check_real_revert(
        &c,
        &Config {
            rewards: vec![Reward {
                accrued: u128::MAX,
                ..Reward::default()
            }],
            ..Config::default()
        },
        &panic(),
    );
    check_real_revert(
        &c,
        &Config {
            now: 899,
            ..Config::default()
        },
        &panic(),
    );
    let c = Case {
        balance: U256::from(1) << 110usize,
        total: U256::from(1) << 111usize,
        ..Case::default()
    };
    let cfg = Config {
        decimals: 0,
        rewards: vec![Reward {
            index: U256::from(1) << 103usize,
            user_index: U256::ZERO,
            emission: U256::ZERO,
            ..Reward::default()
        }],
        ..Config::default()
    };
    check_real_revert(
        &c,
        &cfg,
        &abi_string_error("SafeCast: value doesn't fit in 128 bits"),
    );
}
#[test]
fn later_rate_failure_rolls_back_actual_rewards_changes_and_events() {
    check_real_revert(
        &Case {
            factor: U256::from(10001),
            ..Case::default()
        },
        &Config::default(),
        &panic(),
    );
    check_real_revert(
        &Case {
            virtual_balance: U256::from(u128::MAX),
            ..Case::default()
        },
        &Config::default(),
        &panic(),
    );
}
#[test]
fn real_rewards_missing_proxy_implementation_and_nested_storage_are_rejected() {
    let cfg = Config::default();
    let base = asset_base(TOKEN);
    let reward = reward_base(TOKEN, REWARD_ONE);
    let slots = [
        implementation_slot(),
        base + U256::from(2),
        map_word(U256::ZERO, base + U256::from(1)),
        reward,
        map_word(addr(USER), reward + U256::from(1)),
    ];
    for slot in slots {
        let (mut s, q) = real_setup(&Case::default(), &cfg);
        s.accounts
            .iter_mut()
            .find(|a| a.address == REWARDS)
            .unwrap()
            .storage
            .remove(&slot.to_string());
        assert!(simulate(&s, &q)
            .unwrap_err()
            .to_string()
            .contains("missing storage witness"));
    }
    let (mut s, q) = real_setup(&Case::default(), &cfg);
    s.accounts.retain(|a| a.address != REWARD_IMPL);
    assert!(simulate(&s, &q)
        .unwrap_err()
        .to_string()
        .contains("missing account witness"));
}
#[test]
fn second_proxy_family_dispatches_both_actual_token_getters_and_admin_routes() {
    let f = real_fixture();
    let samples: Vec<_> = f["proxy_samples"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|s| s["proxy_contract"] == "AuditedDebtProxy2")
        .collect();
    assert_eq!(samples.len(), 2);
    for sample in samples {
        let address = sample["proxy"].as_str().unwrap();
        let target = sample["implementation"].as_str().unwrap();
        let name = if sample["kind"] == "a_token" {
            "ATokenInstance"
        } else {
            "VariableDebtTokenInstance"
        };
        let (mut s, mut q) = direct_proxy(CALLER, selector("scaledTotalSupply()"));
        s.accounts
            .retain(|a| a.address != TOKEN && a.address != IMPL);
        let mut proxy = account(
            address,
            f["contracts"]["AuditedDebtProxy2"]["runtime_code"]
                .as_str()
                .unwrap(),
        );
        proxy
            .storage
            .insert(implementation_slot().to_string(), addr(target).to_string());
        let supply_slot = f["contracts"][name]["storage_layout"]["storage"]
            .as_array()
            .unwrap()
            .iter()
            .find(|v| v["label"] == "_totalSupply")
            .unwrap()["slot"]
            .as_str()
            .unwrap();
        proxy.storage.insert(supply_slot.into(), "34567".into());
        s.accounts.push(proxy);
        s.accounts.push(account(
            target,
            f["contracts"][name]["runtime_code"].as_str().unwrap(),
        ));
        q.to = address.into();
        for (caller, signature, expected) in [
            (CALLER, "scaledTotalSupply()", U256::from(34567)),
            (ADMIN, "admin()", addr(ADMIN)),
            (ADMIN, "implementation()", addr(target)),
        ] {
            q.caller = caller.into();
            q.calldata = selector(signature);
            let out = simulate(&s, &q).unwrap();
            assert_eq!(out.status, VmStatus::Success);
            assert_eq!(out.output, encoded(&[expected]));
            assert_no_contract_changes(&out);
        }
        q.caller = ADMIN.into();
        q.calldata = selector("scaledTotalSupply()");
        let out = simulate(&s, &q).unwrap();
        assert_eq!(out.status, VmStatus::Revert);
        assert_eq!(
            out.output,
            abi_string_error("Cannot call fallback function from the proxy admin")
        );
        assert_no_contract_changes(&out);
        q.caller = CALLER.into();
        q.calldata = selector("upgradeTo(address)") + &encoded(&[addr(target)])[2..];
        let out = simulate(&s, &q).unwrap();
        assert_eq!(out.status, VmStatus::Revert);
        assert_eq!(out.output, "0x");
        assert_no_contract_changes(&out);
    }
}

#[test]
fn standalone_controller_handles_zero_supply_zero_balance_and_floor_rounding() {
    // CALLER models an asset invoking handleAction; these balances are supplied.
    let cfg = Config {
        decimals: 0,
        ..Config::default()
    };
    for (total, balance) in [(0, 0), (0, 123), (1000, 0), (3, 1)] {
        let (mut s, mut q) = real_setup(&Case::default(), &cfg);
        s.accounts
            .iter_mut()
            .find(|a| a.address == REWARDS)
            .unwrap()
            .storage = controller_storage(CALLER, &cfg);
        q.to = REWARDS.into();
        q.calldata = selector("handleAction(address,uint256,uint256)")
            + &encoded(&[addr(USER), U256::from(total), U256::from(balance)])[2..];
        let out = simulate(&s, &q).unwrap();
        assert_eq!(out.status, VmStatus::Success);
        assert_eq!(out.output, "0x");
        let (logs, storage) =
            predicted_rewards(CALLER, &cfg, U256::from(total), U256::from(balance));
        assert_eq!(out.logs, logs);
        let changed: BTreeMap<_, _> = out
            .account_deltas
            .into_iter()
            .filter(|d| !d.storage.is_empty())
            .map(|d| (d.address, d.storage))
            .collect();
        assert_eq!(changed, BTreeMap::from([(REWARDS.into(), storage)]));
    }
    check_real(
        &Case::default(),
        &Config {
            now: u64::from(u32::MAX),
            ..Config::default()
        },
    );
    let max = (U256::from(1) << 104usize) - U256::from(1);
    check_real(
        &Case::default(),
        &Config {
            rewards: vec![Reward {
                index: max,
                user_index: max,
                emission: U256::ZERO,
                ..Reward::default()
            }],
            ..Config::default()
        },
    );
    check_real_revert(
        &Case::default(),
        &Config {
            rewards: vec![
                Reward::default(),
                Reward {
                    address: REWARD_TWO,
                    index: max,
                    ..Reward::default()
                },
            ],
            ..Config::default()
        },
        &abi_string_error("INDEX_OVERFLOW"),
    );
}
