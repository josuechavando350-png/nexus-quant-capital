use nqc_miner::{
    config::MinerConfig,
    historical::{self, AaveReadPlan},
    ingestion::{HttpRpc, IngestError, QuorumRpc, ReadRpc},
};
use serde_json::{json, Value};
use std::{cell::RefCell, collections::BTreeMap, rc::Rc};

fn hash(n: u64) -> String {
    format!("0x{n:064x}")
}
fn address(n: u64) -> String {
    format!("0x{n:040x}")
}
fn words(values: &[u128]) -> Value {
    json!(format!(
        "0x{}",
        values
            .iter()
            .map(|v| format!("{v:064x}"))
            .collect::<String>()
    ))
}
fn config() -> MinerConfig {
    serde_json::from_value(json!({"schema_version":2,"namespace":"nqc_miner_v1","producer":"nqc-miner",
        "run_id":"historical-fixture","data_class":"synthetic","code_commit":"1".repeat(40),"cargo_lock_sha256":"2".repeat(64),
        "build_identity_sha256":"3".repeat(64),"observer_bridge_enabled":false,"signing_enabled":false,"gas_budget_mxn_centavos":0,
        "scopes":[{"id":"aave","chain_id":1,"protocol":"aave-v3","contract":address(1),
        "event_topics":nqc_miner::discovery::event_topics(nqc_miner::discovery::ProtocolFamily::AaveV3Pool),
        "from_block":10,"to_block":20,"chunk_blocks":1,"deployment_source":"https://github.com/aave/aave-v3-core",
        "providers":[{"id":"fixture-a","url_env":"NQC_MINER_RPC_A"},{"id":"fixture-b","url_env":"NQC_MINER_RPC_B"}]}]})).unwrap()
}
fn plan() -> AaveReadPlan {
    AaveReadPlan {
        schema_version: 1,
        scope_id: "aave".into(),
        borrower: address(2),
        assets: vec![address(5), address(6)],
        from_block: 10,
        to_block: 13,
        event_block: 14,
        event_block_hash: hash(14),
    }
}

struct FakeRpc {
    id: String,
    fault: &'static str,
    headers: RefCell<BTreeMap<u64, usize>>,
    calls: Rc<RefCell<Vec<Value>>>,
}
impl ReadRpc for FakeRpc {
    fn id(&self) -> &str {
        &self.id
    }
    fn call(&self, method: &str, params: Value) -> Result<Value, IngestError> {
        match method {
            "eth_chainId" => Ok(json!(if self.fault == "chain" { "0x2" } else { "0x1" })),
            "eth_getBlockByNumber" => {
                let n = if params[0] == "finalized" {
                    if self.fault == "unfinalized" {
                        13
                    } else {
                        20
                    }
                } else {
                    u64::from_str_radix(params[0].as_str().unwrap().trim_start_matches("0x"), 16)
                        .unwrap()
                };
                let mut counts = self.headers.borrow_mut();
                let count = counts.entry(n).or_default();
                *count += 1;
                let reorg = self.fault == "interior-reorg" && n == 11 && *count >= 3
                    || self.fault == "anchor-reorg" && n == 20 && *count >= 3;
                Ok(
                    json!({"number":format!("0x{n:x}"),"hash":hash(if reorg {n+100} else {n}),
                    "parentHash":hash(if self.fault=="parent" && n==12 || self.fault=="event-parent" && n==14 {1} else {n-1}),
                    "timestamp":format!("0x{:x}",if self.fault=="same-time" {100} else if self.fault=="time" && n==12 {1} else {n*12})}),
                )
            }
            "eth_call" => {
                historical::validate_call_params(&params)?;
                self.calls.borrow_mut().push(params.clone());
                let n = u64::from_str_radix(
                    params[1]["blockHash"]
                        .as_str()
                        .unwrap()
                        .trim_start_matches("0x"),
                    16,
                )
                .unwrap();
                let data = params[0]["data"].as_str().unwrap();
                let to = params[0]["to"].as_str().unwrap();
                let signature =
                    |s: &str, a: Option<&str>| historical::calldata(s, a).unwrap() == data;
                let upgrade = self.fault == "upgrade" && n >= 12;
                if self.fault == "unavailable" {
                    return Err(IngestError::Provider(self.id.clone()));
                }
                if signature("ADDRESSES_PROVIDER()", None) {
                    assert_eq!(to, address(1));
                    if self.fault == "bad-address" {
                        return Ok(json!(format!("0x01{}", "00".repeat(31))));
                    }
                    return Ok(words(&[if self.fault == "zero-provider" { 0 } else { 3 }]));
                }
                if signature("getPriceOracle()", None) {
                    assert_eq!(to, address(3));
                    return Ok(words(&[if upgrade || self.fault == "disagree" {
                        7
                    } else {
                        4
                    }]));
                }
                if signature("BASE_CURRENCY()", None) {
                    assert_eq!(to, address(if upgrade { 7 } else { 4 }));
                    return Ok(words(&[if upgrade { 8 } else { 0 }]));
                }
                if signature("BASE_CURRENCY_UNIT()", None) {
                    return Ok(words(&[if self.fault == "zero-unit" {
                        0
                    } else if upgrade {
                        1_000_000_000_000_000_000
                    } else {
                        100_000_000
                    }]));
                }
                if signature("getUserAccountData(address)", Some(&address(2))) {
                    assert_eq!(to, address(1));
                    if self.fault == "null" {
                        return Ok(Value::Null);
                    }
                    if self.fault == "short" {
                        return Ok(words(&[1]));
                    }
                    if self.fault == "long" {
                        return Ok(words(&[1; 7]));
                    }
                    if self.fault == "bad-hex" {
                        return Ok(json!("0xzz"));
                    }
                    let hf = if n == 11 {
                        1_100_000_000_000_000_000
                    } else {
                        900_000_000_000_000_000
                    };
                    let hf = if self.fault == "at-threshold" {
                        1_000_000_000_000_000_000
                    } else {
                        hf
                    };
                    return Ok(words(&[
                        20_000_000_000,
                        if self.fault == "zero-debt" {
                            0
                        } else {
                            10_000_000_000
                        },
                        0,
                        if self.fault == "bad-bps" { 10001 } else { 8000 },
                        7500,
                        hf,
                    ]));
                }
                if signature("getAssetPrice(address)", Some(&address(5)))
                    || signature("getAssetPrice(address)", Some(&address(6)))
                {
                    assert_eq!(to, address(if upgrade { 7 } else { 4 }));
                    return Ok(words(&[if self.fault == "zero-price" {
                        0
                    } else {
                        2391_12345678
                    }]));
                }
                panic!("unexpected getter");
            }
            _ => panic!("unexpected method"),
        }
    }
}
type ObservedCalls = Rc<RefCell<Vec<Value>>>;
fn quorum(a: &'static str, b: &'static str) -> (QuorumRpc, ObservedCalls) {
    let calls = Rc::new(RefCell::new(Vec::new()));
    let providers: Vec<Box<dyn ReadRpc>> = vec![("fixture-a", a), ("fixture-b", b)]
        .into_iter()
        .map(|(id, fault)| {
            Box::new(FakeRpc {
                id: id.into(),
                fault,
                headers: RefCell::new(BTreeMap::new()),
                calls: calls.clone(),
            }) as Box<dyn ReadRpc>
        })
        .collect();
    (QuorumRpc::new(1, providers).unwrap(), calls)
}

#[test]
fn reads_every_block_and_preserves_non_monotonic_breach_episodes() {
    let (q, calls) = quorum("", "");
    let report = historical::read_aave(&config(), &plan(), &q).unwrap();
    assert_eq!(report.samples.len(), 4);
    assert_eq!(calls.borrow().len(), 4 * 7 * 2);
    assert_eq!(report.breach_episodes.len(), 2);
    let a = &report.breach_episodes[0];
    assert_eq!(
        (
            a.first_sampled_block,
            a.last_sampled_block,
            a.left_censored,
            a.right_censored
        ),
        (10, 10, true, false)
    );
    let b = &report.breach_episodes[1];
    assert_eq!(
        (
            b.first_sampled_block,
            b.last_sampled_block,
            b.left_censored,
            b.right_censored
        ),
        (12, 13, false, true)
    );
    assert!(report.first_eligible_block.is_none() && report.liquidation_delay_blocks.is_none());
    assert!(
        !report.executable_eligibility_verified
            && !report.activation_allowed
            && !report.economic_certification
    );
    assert!(report.provider_agreement_is_not_state_authentication);
    assert!(!report.source_journal_binding_verified && !report.prices_freshness_verified);
    for s in &report.samples {
        assert!(s.base_currency_is_usd_by_interface);
        assert_eq!(s.base_currency_unit, "100000000");
        assert_eq!(s.prices[0].price_base, "239112345678");
        assert_eq!(s.calls.len(), 7);
        for c in &s.calls {
            assert_eq!(
                c.params[1],
                json!({"blockHash":s.block.hash,"requireCanonical":true})
            );
            assert_eq!(c.replies.len(), 2);
            assert_eq!(c.replies[0].result, c.replies[1].result);
        }
    }
}

#[test]
fn zero_debt_and_exact_threshold_do_not_create_breach() {
    for fault in ["zero-debt", "at-threshold"] {
        let (q, _) = quorum(fault, fault);
        let report = historical::read_aave(&config(), &plan(), &q).unwrap();
        assert!(report.breach_episodes.is_empty());
    }
}

#[test]
fn detects_oracle_changes_without_converting_non_usd_or_aggregating_prices() {
    let (q, _) = quorum("upgrade", "upgrade");
    let report = historical::read_aave(&config(), &plan(), &q).unwrap();
    assert!(report.oracle_configuration_changed);
    assert_eq!(report.samples[2].oracle, address(7));
    assert_eq!(report.samples[2].base_currency_unit, "1000000000000000000");
    assert!(!report.samples[2].base_currency_is_usd_by_interface);
}

#[test]
fn rejects_disagreement_and_archive_unavailability() {
    let (q, _) = quorum("", "disagree");
    assert!(matches!(
        historical::read_aave(&config(), &plan(), &q),
        Err(IngestError::Disagreement(_))
    ));
    let (q, _) = quorum("", "unavailable");
    assert!(matches!(
        historical::read_aave(&config(), &plan(), &q),
        Err(IngestError::Provider(_))
    ));
}

#[test]
fn rejects_malformed_or_zero_abi_results_and_out_of_range_basis_points() {
    for fault in [
        "null",
        "short",
        "long",
        "bad-hex",
        "bad-address",
        "zero-provider",
        "zero-unit",
        "zero-price",
        "bad-bps",
    ] {
        let (q, _) = quorum(fault, fault);
        assert!(
            historical::read_aave(&config(), &plan(), &q).is_err(),
            "{fault}"
        );
    }
}

#[test]
fn revalidates_interior_event_parent_and_finalized_anchor() {
    for fault in [
        "interior-reorg",
        "anchor-reorg",
        "parent",
        "event-parent",
        "time",
        "unfinalized",
    ] {
        let (q, _) = quorum(fault, fault);
        assert!(
            historical::read_aave(&config(), &plan(), &q).is_err(),
            "{fault}"
        );
    }
}

#[test]
fn permits_equal_timestamps_for_multiple_l2_blocks_in_one_second() {
    let (q, _) = quorum("same-time", "same-time");
    assert!(historical::read_aave(&config(), &plan(), &q).is_ok());
}

#[test]
fn checks_chain_provider_order_and_expected_event_hash() {
    let (q, _) = quorum("", "");
    let mut c = config();
    c.scopes[0].chain_id = 2;
    assert!(historical::read_aave(&c, &plan(), &q).is_err());
    c = config();
    c.scopes[0].providers.reverse();
    assert!(historical::read_aave(&c, &plan(), &q).is_err());
    let mut p = plan();
    p.event_block_hash = hash(99);
    assert!(historical::read_aave(&config(), &p, &q).is_err());
}

#[test]
fn plan_validation_prevents_gaps_post_event_shadow_and_unbounded_reads() {
    let base = serde_json::to_value(plan()).unwrap();
    let changes = [
        ("schema_version", json!(2)),
        ("scope_id", json!("foreign")),
        ("borrower", json!(address(0))),
        ("assets", json!([])),
        ("assets", json!([address(5), address(5)])),
        ("from_block", json!(9)),
        ("from_block", json!(14)),
        ("to_block", json!(14)),
        ("event_block", json!(16)),
        ("event_block_hash", json!(hash(0))),
    ];
    for (field, value) in changes {
        let mut v = base.clone();
        v[field] = value;
        let p: AaveReadPlan = serde_json::from_value(v).unwrap();
        assert!(p.validate(&config()).is_err(), "{field}");
    }
    let mut c = config();
    c.data_class = nqc_miner::config::DataClass::Shadow;
    assert!(plan().validate(&c).is_err());
    c = config();
    c.scopes[0].to_block = 1000;
    let mut p = plan();
    p.to_block = 74;
    p.event_block = 75;
    assert!(p.validate(&c).is_err());
    p.to_block = 73;
    p.event_block = 74;
    assert!(p.validate(&c).is_ok());
}

#[test]
fn getter_allowlist_rejects_unpinned_overrides_values_and_arbitrary_calldata_before_network() {
    let original = historical::call_params(
        &hash(10),
        &address(1),
        &historical::calldata("getUserAccountData(address)", Some(&address(2))).unwrap(),
    );
    historical::validate_call_params(&original).unwrap();
    let rpc = HttpRpc::new("fixture-http", "http://127.0.0.1:1").unwrap();
    let mut mutations = vec![];
    let mut v = original.clone();
    v[1] = json!("latest");
    mutations.push(v);
    let mut v = original.clone();
    v[1] = json!({"blockNumber":"0xa"});
    mutations.push(v);
    let mut v = original.clone();
    v[1]["requireCanonical"] = json!(false);
    mutations.push(v);
    let mut v = original.clone();
    v[1]["requireCanonical"] = json!(1);
    mutations.push(v);
    let mut v = original.clone();
    v[0]["value"] = json!("0x1");
    mutations.push(v);
    let mut v = original.clone();
    v[0]["gas"] = json!("0xffffff");
    mutations.push(v);
    let mut v = original.clone();
    v[0]["from"] = json!(address(8));
    mutations.push(v);
    let mut v = original.clone();
    v[0]["data"] = json!("0xdeadbeef");
    mutations.push(v);
    let mut v = original.clone();
    v[0]["data"] = json!(format!("0xbf92857c{}", "ff".repeat(32)));
    mutations.push(v);
    let mut v = original.clone();
    v.as_array_mut().unwrap().push(json!({}));
    mutations.push(v);
    for params in mutations {
        assert!(historical::validate_call_params(&params).is_err());
        assert!(matches!(
            rpc.call("eth_call", params),
            Err(IngestError::Rejected(_))
        ));
    }
}

#[test]
fn selectors_encoding_unknown_json_fields_and_ambiguous_types_are_rejected() {
    assert!(historical::calldata(
        "liquidationCall(address,address,address,uint256,bool)",
        None
    )
    .is_err());
    assert!(historical::calldata("getAssetPrice(address)", Some(&address(0))).is_err());
    assert_eq!(
        &historical::calldata("getUserAccountData(address)", Some(&address(2))).unwrap()[..10],
        "0xbf92857c"
    );
    let mut v = serde_json::to_value(plan()).unwrap();
    v["first_eligible_block"] = json!(10);
    assert!(serde_json::from_value::<AaveReadPlan>(v).is_err());
    let mut v = serde_json::to_value(plan()).unwrap();
    v["event_block"] = json!(true);
    assert!(serde_json::from_value::<AaveReadPlan>(v).is_err());
}
