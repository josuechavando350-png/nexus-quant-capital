//! All RPC responses here are synthetic test fixtures, never market evidence.
use nqc_miner::{
    bridge::ExportEnvelope,
    config::{DataClass, MinerConfig, ProviderSpec, ScanScope},
    discovery::{self, ContractScope, ProtocolFamily},
    ingestion::{self, IngestError, QuorumRpc, ReadRpc},
    journal::{self, Journal, Record},
    reporting,
};
use serde_json::{json, Value};
use std::{
    cell::Cell,
    fs,
    io::{Read, Write},
    net::TcpListener,
    path::Path,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    },
    thread,
    time::Duration,
};

fn h(n: u64) -> String {
    format!("0x{n:064x}")
}
fn addr(n: u64) -> String {
    format!("0x{n:040x}")
}
fn config() -> MinerConfig {
    MinerConfig {
        schema_version: 2,
        namespace: "nqc_miner_v1".into(),
        producer: "nqc-miner".into(),
        run_id: "fixture-pipeline".into(),
        // The class exercises historical admission in a fake in-memory transport only.
        data_class: DataClass::Historical,
        code_commit: "1".repeat(40),
        cargo_lock_sha256: "2".repeat(64),
        build_identity_sha256: Some("3".repeat(64)),
        observer_bridge_enabled: false,
        signing_enabled: false,
        gas_budget_mxn_centavos: 0,
        scopes: vec![ScanScope {
            id: "morpho-test".into(),
            chain_id: 1,
            protocol: "morpho-blue".into(),
            contract: addr(1),
            event_topics: discovery::event_topics(ProtocolFamily::MorphoBlue),
            from_block: 100,
            to_block: 102,
            chunk_blocks: 2,
            providers: vec![
                ProviderSpec {
                    id: "fixture-a".into(),
                    url_env: "NQC_MINER_RPC_A".into(),
                },
                ProviderSpec {
                    id: "fixture-b".into(),
                    url_env: "NQC_MINER_RPC_B".into(),
                },
            ],
            deployment_source: "https://example.invalid/synthetic-fixture-not-a-deployment".into(),
        }],
    }
}
fn log(block: u64, index: u32, tx: u64) -> Value {
    let data = format!(
        "0x{}{}{}{}{}",
        format_args!("{:064x}", 10),
        format_args!("{:064x}", 10),
        format_args!("{:064x}", 12),
        "0".repeat(64),
        "0".repeat(64)
    );
    json!({"address":addr(1),"blockNumber":format!("0x{block:x}"),"blockHash":h(block+1),"transactionHash":h(tx),
        "logIndex":format!("0x{index:x}"),"topics":[discovery::event_topics(ProtocolFamily::MorphoBlue)[1],h(9),h(3),h(4)],
        "data":data,"removed":false})
}
struct FakeRpc {
    id: String,
    chain: u64,
    logs: Vec<Value>,
    wrong_headers: bool,
    bad_parent: bool,
    anchor_mutation: bool,
    anchor_failure: bool,
    anchor_calls: Cell<u32>,
    fail_logs: bool,
    mutate_prior_after_logs: bool,
    logs_called: Cell<bool>,
}
impl FakeRpc {
    fn new(id: &str, logs: Vec<Value>) -> Self {
        Self {
            id: id.into(),
            chain: 1,
            logs,
            wrong_headers: false,
            bad_parent: false,
            anchor_mutation: false,
            anchor_failure: false,
            anchor_calls: Cell::new(0),
            fail_logs: false,
            mutate_prior_after_logs: false,
            logs_called: Cell::new(false),
        }
    }
}
impl ReadRpc for FakeRpc {
    fn id(&self) -> &str {
        &self.id
    }
    fn call(&self, method: &str, params: Value) -> Result<Value, IngestError> {
        match method {
            "eth_chainId" => Ok(json!(format!("0x{:x}", self.chain))),
            "eth_getBlockByNumber" => {
                let tag = params[0].as_str().unwrap();
                let n = if tag == "finalized" {
                    102
                } else {
                    u64::from_str_radix(&tag[2..], 16).unwrap()
                };
                let mut offset = if self.wrong_headers { 1000 } else { 0 };
                if self.mutate_prior_after_logs && self.logs_called.get() && n == 100 {
                    offset = 1000;
                }
                if tag == "0x66" && (self.anchor_mutation || self.anchor_failure) {
                    let calls = self.anchor_calls.get() + 1;
                    self.anchor_calls.set(calls);
                    if calls > 1 {
                        if self.anchor_failure {
                            return Err(IngestError::Provider(self.id.clone()));
                        }
                        offset = 1000;
                    }
                }
                Ok(json!({"number":format!("0x{n:x}"),"hash":h(n+1+offset),
                    "parentHash":if self.bad_parent&&n==102{h(9999)}else{h(n+offset)},"timestamp":format!("0x{:x}",1000+n)}))
            }
            "eth_getLogs" => {
                self.logs_called.set(true);
                if self.fail_logs {
                    return Err(IngestError::Provider(self.id.clone()));
                }
                let first = ingestion::quantity(&params[0]["fromBlock"])?;
                let last = ingestion::quantity(&params[0]["toBlock"])?;
                Ok(json!(self
                    .logs
                    .iter()
                    .filter(|l| {
                        let b = ingestion::quantity(&l["blockNumber"]).unwrap();
                        b >= first && b <= last
                    })
                    .collect::<Vec<_>>()))
            }
            _ => Err(IngestError::Rejected(
                "fixture transport only supports read methods".into(),
            )),
        }
    }
}
fn quorum(logs: Vec<Value>) -> QuorumRpc {
    QuorumRpc::new(
        1,
        vec![
            Box::new(FakeRpc::new("fixture-a", logs.clone())),
            Box::new(FakeRpc::new("fixture-b", logs)),
        ],
    )
    .unwrap()
}
fn observed(value: Value) -> Record {
    let log = ingestion::parse_log(&value, 1).unwrap();
    let decoded = discovery::decode_log(
        &ContractScope {
            chain_id: 1,
            address: addr(1),
            family: ProtocolFamily::MorphoBlue,
            from_block: 100,
            to_block: 102,
        },
        &log,
    )
    .unwrap();
    Record::Observed {
        scope_id: "morpho-test".into(),
        block_timestamp: 1000 + log.block_number,
        observed_at: 2000,
        providers: vec!["fixture-a".into(), "fixture-b".into()],
        log,
        decoded: Box::new(decoded),
    }
}
fn completed_empty() -> Record {
    Record::ChunkCompleted {
        scope_id: "morpho-test".into(),
        chain_id: 1,
        from_block: 100,
        to_block: 101,
        start_block_hash: h(101),
        start_parent_hash: h(100),
        end_block_hash: h(102),
        observed_at: 2000,
        providers: vec!["fixture-a".into(), "fixture-b".into()],
        event_count: 0,
        logs_sha256: nqc_miner::digest(b"[]"),
    }
}
fn scan(config: &MinerConfig, path: &Path, logs: Vec<Value>) -> journal::JournalSummary {
    let mut journal = Journal::open(path, config).unwrap();
    ingestion::scan_scope(&config.scopes[0], &quorum(logs), &mut journal, 2000).unwrap();
    journal.summary()
}

#[test]
fn configuration_rejects_crossing_observer_money_and_foreign_creds() {
    let original = config();
    original.validate().unwrap();
    let mut c = original.clone();
    c.namespace = "observer".into();
    assert!(c.validate().is_err());
    let mut c = original.clone();
    c.observer_bridge_enabled = true;
    assert!(c.validate().is_err());
    let mut c = original.clone();
    c.signing_enabled = true;
    assert!(c.validate().is_err());
    let mut c = original.clone();
    c.gas_budget_mxn_centavos = 1;
    assert!(c.validate().is_err());
    let mut c = original.clone();
    c.scopes[0].providers[0].url_env = "OBSERVER_RPC".into();
    assert!(c.validate().is_err());
    let mut c = original;
    c.scopes.push(c.scopes[0].clone());
    c.scopes[1].id = "duplicate".into();
    assert!(c.validate().is_err());
}
#[test]
fn legacy_v1_is_offline_verifiable_but_never_live_rpc_eligible() {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("legacy");
    let mut legacy = config();
    legacy.schema_version = 1;
    legacy.build_identity_sha256 = None;
    legacy.validate().unwrap();
    assert!(ingestion::validate_runtime(&legacy).is_err());
    drop(Journal::open(&path, &legacy).unwrap());
    let summary = journal::verify(&path).unwrap();
    assert_eq!(summary.owner.schema, "nqc-miner-owner-v1");
    assert!(summary.owner.build_identity_sha256.is_none());
}

#[test]
fn v2_requires_build_identity_and_v1_cannot_claim_one() {
    let mut v2 = config();
    v2.build_identity_sha256 = None;
    assert!(v2.validate().is_err());

    let mut v1 = config();
    v1.schema_version = 1;
    assert!(v1.validate().is_err());
    v1.build_identity_sha256 = None;
    v1.validate().unwrap();
}

#[test]
fn existing_v2_journal_cannot_be_adopted_by_another_build_identity() {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("miner");
    let original = config();
    drop(Journal::open(&path, &original).unwrap());

    let mut different = original.clone();
    different.build_identity_sha256 = Some("4".repeat(64));
    assert!(different.validate().is_ok());
    assert!(Journal::open(&path, &different).is_err());

    let summary = journal::verify(&path).unwrap();
    assert_eq!(
        summary.owner.build_identity_sha256.as_deref(),
        original.build_identity_sha256.as_deref()
    );
}

#[test]
fn unowned_directory_is_never_adopted() {
    let tmp = tempfile::tempdir().unwrap();
    fs::write(tmp.path().join("observer.txt"), "untouched").unwrap();
    assert!(Journal::open(tmp.path(), &config()).is_err());
    assert_eq!(
        fs::read_to_string(tmp.path().join("observer.txt")).unwrap(),
        "untouched"
    );
}
#[test]
fn exclusive_lock_blocks_concurrent_writer_and_verifier() {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("miner");
    let first = Journal::open(&path, &config()).unwrap();
    assert!(Journal::open(&path, &config()).is_err());
    assert!(journal::verify(&path).is_err());
    drop(first);
    assert!(journal::verify(&path).is_ok());
}
#[test]
fn immutable_run_configuration_cannot_be_reused() {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("miner");
    drop(Journal::open(&path, &config()).unwrap());
    let mut c = config();
    c.run_id = "another-run".into();
    assert!(Journal::open(&path, &c).is_err());
    let mut c = config();
    c.data_class = DataClass::Shadow;
    assert!(Journal::open(&path, &c).is_err());
}
#[test]
fn finalized_scan_replays_idempotently_and_reports_only_scoped_coverage() {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("miner");
    let c = config();
    let logs = vec![log(100, 0, 81), log(101, 1, 82)];
    let first = scan(&c, &path, logs.clone());
    assert_eq!(first.canonical_events, 2);
    assert_eq!(first.provisional_events, 0);
    assert_eq!(first.completed_chunks, 2);
    let mut journal = Journal::open(&path, &c).unwrap();
    let report = ingestion::scan_scope(&c.scopes[0], &quorum(logs), &mut journal, 2001).unwrap();
    assert_eq!(report.new_events, 0);
    assert_eq!(report.new_chunks, 0);
    assert_eq!(report.resumed_after, Some(102));
    drop(journal);
    let report = reporting::report(&c, &path, &[]).unwrap();
    assert_eq!(report.coverage.unwrap().fraction, Some(0.0));
    assert_eq!(report.observed_liquidations, 2);
    assert!(report
        .saturations
        .iter()
        .all(|s| s.median_delay_blocks.is_none() && s.mean_builder_tip_share.is_none()));
    assert!(report.measured_realized_profit.is_none());
    assert!(!report.activation_permitted);
}
#[test]
fn no_events_does_not_mean_full_coverage_or_virgin_market() {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("miner");
    scan(&config(), &path, vec![]);
    let report = reporting::report(&config(), &path, &[]).unwrap();
    assert_eq!(report.coverage.unwrap().fraction, None);
    assert!(report.saturations.is_empty());
}
#[test]
fn logs_are_ordered_by_block_and_log_index_not_transaction_hash() {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("miner");
    let c = config();
    scan(&c, &path, vec![log(100, 2, 1), log(100, 1, 999)]);
    let (_, records) = journal::read_verified(&path).unwrap();
    let indices: Vec<_> = records
        .iter()
        .filter_map(|e| match &e.record {
            Record::Observed { log, .. } => Some(log.log_index),
            _ => None,
        })
        .collect();
    assert_eq!(indices, vec![1, 2]);
}
#[test]
fn provider_disagreement_does_not_complete_a_chunk() {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("miner");
    let c = config();
    let mut j = Journal::open(&path, &c).unwrap();
    let q = QuorumRpc::new(
        1,
        vec![
            Box::new(FakeRpc::new("fixture-a", vec![log(100, 0, 1)])),
            Box::new(FakeRpc::new("fixture-b", vec![])),
        ],
    )
    .unwrap();
    assert!(ingestion::scan_scope(&c.scopes[0], &q, &mut j, 2000).is_err());
    assert_eq!(j.summary().records, 0);
}
#[test]
fn wrong_chain_duplicate_and_removed_logs_are_rejected() {
    let mut wrong = FakeRpc::new("fixture-a", vec![]);
    wrong.chain = 2;
    assert!(QuorumRpc::new(
        1,
        vec![Box::new(wrong), Box::new(FakeRpc::new("fixture-b", vec![]))]
    )
    .is_err());
    let c = config();
    assert!(quorum(vec![log(100, 0, 1), log(100, 0, 1)])
        .logs(&c.scopes[0], 100, 101)
        .is_err());
    let mut removed = log(100, 0, 1);
    removed["removed"] = json!(true);
    assert!(quorum(vec![removed]).logs(&c.scopes[0], 100, 101).is_err());
}
#[test]
fn log_block_hash_must_match_quorum_header() {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("miner");
    let c = config();
    let mut j = Journal::open(&path, &c).unwrap();
    let mut bad = log(100, 0, 1);
    bad["blockHash"] = json!(h(999));
    assert!(ingestion::scan_scope(&c.scopes[0], &quorum(vec![bad]), &mut j, 2000).is_err());
    assert_eq!(j.summary().records, 0);
}
#[test]
fn failed_provider_never_advances_the_cursor() {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("miner");
    let c = config();
    let mut j = Journal::open(&path, &c).unwrap();
    let mut failed = FakeRpc::new("fixture-b", vec![]);
    failed.fail_logs = true;
    let q = QuorumRpc::new(
        1,
        vec![
            Box::new(FakeRpc::new("fixture-a", vec![])),
            Box::new(failed),
        ],
    )
    .unwrap();
    assert!(ingestion::scan_scope(&c.scopes[0], &q, &mut j, 2000).is_err());
    assert_eq!(j.summary().completed_chunks, 0);
}
#[test]
fn synthetic_class_and_foreign_scope_cannot_enter_live_scan_api() {
    let tmp = tempfile::tempdir().unwrap();
    let mut c = config();
    c.data_class = DataClass::Synthetic;
    let mut j = Journal::open(&tmp.path().join("a"), &c).unwrap();
    assert!(ingestion::scan_scope(&c.scopes[0], &quorum(vec![]), &mut j, 2000).is_err());
    drop(j);
    let c = config();
    let mut j = Journal::open(&tmp.path().join("b"), &c).unwrap();
    let mut scope = c.scopes[0].clone();
    scope.to_block = 101;
    assert!(ingestion::scan_scope(&scope, &quorum(vec![]), &mut j, 2000).is_err());
}
#[test]
fn interrupted_events_are_provisional_and_cannot_be_closed_as_empty() {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("miner");
    let c = config();
    let mut j = Journal::open(&path, &c).unwrap();
    j.append(observed(log(100, 0, 1))).unwrap();
    assert_eq!(j.summary().provisional_events, 1);
    assert_eq!(j.summary().canonical_events, 0);
    assert!(j.append(completed_empty()).is_err());
    drop(j);
    let report = reporting::report(&c, &path, &[]).unwrap();
    assert_eq!(report.observed_liquidations, 0);
    assert!(report.coverage.is_none());
    let mut j = Journal::open(&path, &c).unwrap();
    assert!(ingestion::scan_scope(&c.scopes[0], &quorum(vec![]), &mut j, 2000).is_err());
    assert_eq!(j.summary().provisional_events, 1);
}
#[test]
fn interrupted_scan_resumes_with_same_event_set_without_duplicates() {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("miner");
    let c = config();
    let l = log(100, 0, 1);
    let mut j = Journal::open(&path, &c).unwrap();
    j.append(observed(l.clone())).unwrap();
    drop(j);
    let summary = scan(&c, &path, vec![l]);
    assert_eq!(summary.canonical_events, 1);
    assert_eq!(summary.provisional_events, 0);
    assert_eq!(summary.records, 4);
    assert_eq!(summary.completed_scopes, 1);
}
#[test]
fn decoded_payload_cannot_disagree_with_raw_log() {
    let tmp = tempfile::tempdir().unwrap();
    let mut j = Journal::open(&tmp.path().join("miner"), &config()).unwrap();
    let mut record = observed(log(100, 0, 1));
    if let Record::Observed { decoded, .. } = &mut record {
        if let discovery::DecodedEvent::Liquidation(signal) = decoded.as_mut() {
            signal.liquidator = addr(999);
        } else {
            panic!()
        }
    } else {
        panic!()
    }
    assert!(j.append(record).is_err());
}
#[test]
fn same_log_index_with_conflicting_transaction_is_rejected() {
    let tmp = tempfile::tempdir().unwrap();
    let mut j = Journal::open(&tmp.path().join("miner"), &config()).unwrap();
    j.append(observed(log(100, 0, 1))).unwrap();
    assert!(j.append(observed(log(100, 0, 2))).is_err());
}
#[test]
fn torn_record_is_preserved_and_fails_verification() {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("miner");
    drop(Journal::open(&path, &config()).unwrap());
    fs::OpenOptions::new()
        .append(true)
        .open(path.join("events.jsonl"))
        .unwrap()
        .write_all(b"{\"sequence\":")
        .unwrap();
    let before = fs::read(path.join("events.jsonl")).unwrap();
    assert!(journal::verify(&path).is_err());
    assert_eq!(fs::read(path.join("events.jsonl")).unwrap(), before);
}
#[test]
fn tampered_manifest_and_hashchain_are_rejected() {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("miner");
    scan(&config(), &path, vec![]);
    let mut bytes = fs::read(path.join("events.jsonl")).unwrap();
    bytes[14] = b'9';
    fs::write(path.join("events.jsonl"), bytes).unwrap();
    assert!(journal::verify(&path).is_err());
    let other = tmp.path().join("other");
    drop(Journal::open(&other, &config()).unwrap());
    let mut c = config();
    c.run_id = "tampered".into();
    fs::write(other.join("config.json"), serde_json::to_vec(&c).unwrap()).unwrap();
    assert!(journal::verify(&other).is_err());
}
#[test]
fn persisted_reorg_quarantines_all_dependent_evidence() {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("miner");
    let c = config();
    scan(&c, &path, vec![log(100, 0, 1)]);
    let mut a = FakeRpc::new("fixture-a", vec![]);
    a.wrong_headers = true;
    let mut b = FakeRpc::new("fixture-b", vec![]);
    b.wrong_headers = true;
    let q = QuorumRpc::new(1, vec![Box::new(a), Box::new(b)]).unwrap();
    let mut j = Journal::open(&path, &c).unwrap();
    assert!(ingestion::scan_scope(&c.scopes[0], &q, &mut j, 2000).is_err());
    assert_eq!(j.summary().canonical_events, 0);
    assert_eq!(j.summary().invalidated_events, 1);
    assert_eq!(j.summary().completed_chunks, 0);
    drop(j);
    assert!(reporting::report(&c, &path, &[])
        .unwrap()
        .coverage
        .is_none());
}

#[test]
fn empty_scopes_cannot_complete_on_different_chain_histories() {
    for second_start in [100, 102] {
        let tmp = tempfile::tempdir().unwrap();
        let path = tmp.path().join("miner");
        let mut c = config();
        c.scopes[0].to_block = 100;
        let mut second = c.scopes[0].clone();
        second.id = "second-market".into();
        second.contract = addr(2);
        second.from_block = second_start;
        second.to_block = second_start;
        c.scopes.push(second);
        let mut j = Journal::open(&path, &c).unwrap();
        ingestion::scan_scope(&c.scopes[0], &quorum(vec![]), &mut j, 2000).unwrap();
        let mut a = FakeRpc::new("fixture-a", vec![]);
        a.wrong_headers = true;
        let mut b = FakeRpc::new("fixture-b", vec![]);
        b.wrong_headers = true;
        let changed = QuorumRpc::new(1, vec![Box::new(a), Box::new(b)]).unwrap();
        assert!(ingestion::scan_scope(&c.scopes[1], &changed, &mut j, 2000).is_err());
        assert_eq!(j.summary().invalidated_from.get(&1), Some(&100));
        assert_eq!(j.summary().completed_scopes, 0);
        drop(j);
        let report = reporting::report(&c, &path, &[]).unwrap();
        assert!(report.scope_completion.iter().all(|scope| !scope.complete));
        assert!(report.coverage.is_none());
    }
}

#[test]
fn earlier_scope_is_revalidated_after_later_scope_finishes() {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("miner");
    let mut c = config();
    c.scopes[0].to_block = 100;
    let mut second = c.scopes[0].clone();
    second.id = "second-market".into();
    second.contract = addr(2);
    second.from_block = 102;
    second.to_block = 102;
    c.scopes.push(second);
    let mut j = Journal::open(&path, &c).unwrap();
    ingestion::scan_scope(&c.scopes[0], &quorum(vec![]), &mut j, 2000).unwrap();
    let mut a = FakeRpc::new("fixture-a", vec![]);
    a.mutate_prior_after_logs = true;
    let mut b = FakeRpc::new("fixture-b", vec![]);
    b.mutate_prior_after_logs = true;
    let changed = QuorumRpc::new(1, vec![Box::new(a), Box::new(b)]).unwrap();
    assert!(ingestion::scan_scope(&c.scopes[1], &changed, &mut j, 2000).is_err());
    assert_eq!(j.summary().invalidated_from.get(&1), Some(&100));
    assert_eq!(j.summary().completed_scopes, 0);
}

#[test]
fn journal_rejects_conflicting_empty_chunks_across_scopes() {
    let tmp = tempfile::tempdir().unwrap();
    let mut c = config();
    c.scopes[0].to_block = 100;
    let mut second = c.scopes[0].clone();
    second.id = "second-market".into();
    second.contract = addr(2);
    c.scopes.push(second);
    let mut j = Journal::open(&tmp.path().join("miner"), &c).unwrap();
    ingestion::scan_scope(&c.scopes[0], &quorum(vec![]), &mut j, 2000).unwrap();
    let before = j.summary().records;
    assert!(j
        .append(Record::ChunkCompleted {
            scope_id: "second-market".into(),
            chain_id: 1,
            from_block: 100,
            to_block: 100,
            start_block_hash: h(1101),
            start_parent_hash: h(1100),
            end_block_hash: h(1101),
            observed_at: 2000,
            providers: vec!["fixture-a".into(), "fixture-b".into()],
            event_count: 0,
            logs_sha256: nqc_miner::digest(b"[]"),
        })
        .is_err());
    assert_eq!(j.summary().records, before);
}
#[test]
fn adjacent_chunk_parent_mismatch_quarantines_earlier_chunks() {
    let tmp = tempfile::tempdir().unwrap();
    let c = config();
    let mut a = FakeRpc::new("fixture-a", vec![log(100, 0, 1)]);
    a.bad_parent = true;
    let mut b = FakeRpc::new("fixture-b", vec![log(100, 0, 1)]);
    b.bad_parent = true;
    let q = QuorumRpc::new(1, vec![Box::new(a), Box::new(b)]).unwrap();
    let mut j = Journal::open(&tmp.path().join("miner"), &c).unwrap();
    assert!(ingestion::scan_scope(&c.scopes[0], &q, &mut j, 2000).is_err());
    assert_eq!(j.summary().invalidated_events, 1);
}
#[test]
fn final_anchor_change_cannot_return_complete() {
    let tmp = tempfile::tempdir().unwrap();
    let mut c = config();
    c.scopes[0].to_block = 100;
    let mut a = FakeRpc::new("fixture-a", vec![log(100, 0, 1)]);
    a.anchor_mutation = true;
    let mut b = FakeRpc::new("fixture-b", vec![log(100, 0, 1)]);
    b.anchor_mutation = true;
    let q = QuorumRpc::new(1, vec![Box::new(a), Box::new(b)]).unwrap();
    let mut j = Journal::open(&tmp.path().join("miner"), &c).unwrap();
    assert!(ingestion::scan_scope(&c.scopes[0], &q, &mut j, 2000).is_err());
    assert_eq!(j.summary().invalidated_events, 1);
}
#[test]
fn unfinalized_range_cannot_be_scanned() {
    let tmp = tempfile::tempdir().unwrap();
    let mut c = config();
    c.scopes[0].to_block = 103;
    let mut j = Journal::open(&tmp.path().join("miner"), &c).unwrap();
    assert!(ingestion::scan_scope(&c.scopes[0], &quorum(vec![]), &mut j, 2000).is_err());
    assert_eq!(j.summary().records, 0);
}
#[test]
fn failed_final_anchor_recheck_is_incomplete_until_successful_retry() {
    let tmp = tempfile::tempdir().unwrap();
    let path = tmp.path().join("miner");
    let mut c = config();
    c.scopes[0].to_block = 100;
    let mut a = FakeRpc::new("fixture-a", vec![log(100, 0, 1)]);
    a.anchor_failure = true;
    let mut b = FakeRpc::new("fixture-b", vec![log(100, 0, 1)]);
    b.anchor_failure = true;
    let q = QuorumRpc::new(1, vec![Box::new(a), Box::new(b)]).unwrap();
    let mut j = Journal::open(&path, &c).unwrap();
    assert!(ingestion::scan_scope(&c.scopes[0], &q, &mut j, 2000).is_err());
    assert_eq!(j.summary().completed_chunks, 1);
    assert_eq!(j.summary().completed_scopes, 0);
    drop(j);
    let report = reporting::report(&c, &path, &[]).unwrap();
    assert!(!report.scope_completion[0].complete);
    assert!(report.coverage.is_none());
    let summary = scan(&c, &path, vec![log(100, 0, 1)]);
    assert_eq!(summary.completed_scopes, 1);
    assert_eq!(summary.canonical_events, 1);
}
fn local_http_rpc(responses: Vec<String>) -> (String, Arc<AtomicUsize>, thread::JoinHandle<()>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let hits = Arc::new(AtomicUsize::new(0));
    let observed = Arc::clone(&hits);
    let handle = thread::spawn(move || {
        for response in responses {
            let (mut stream, _) = listener.accept().unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(1)))
                .unwrap();
            let mut request = [0u8; 4096];
            let _ = stream.read(&mut request);
            observed.fetch_add(1, Ordering::SeqCst);
            stream.write_all(response.as_bytes()).unwrap();
            stream.flush().unwrap();
        }
    });
    (
        format!("http://{address}/private-path?token=never-print-this"),
        hits,
        handle,
    )
}

fn http_response(status: &str, extra_headers: &str, body: &str) -> String {
    format!(
        "HTTP/1.1 {status}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n{extra_headers}\r\n{body}",
        body.len()
    )
}

#[test]
fn http_rate_limit_is_retried_and_then_succeeds() {
    let body = r#"{"jsonrpc":"2.0","id":1,"result":"0x1"}"#;
    let responses = vec![
        http_response("429 Too Many Requests", "Retry-After: 0\r\n", ""),
        http_response("200 OK", "", body),
    ];
    let (url, hits, handle) = local_http_rpc(responses);
    let rpc = ingestion::HttpRpc::new("fixture-http", &url).unwrap();
    assert_eq!(rpc.call("eth_chainId", json!([])).unwrap(), json!("0x1"));
    handle.join().unwrap();
    assert_eq!(hits.load(Ordering::SeqCst), 2);
}

#[test]
fn nonretryable_http_failure_is_single_shot_and_redacts_endpoint() {
    let responses = vec![http_response("401 Unauthorized", "", "")];
    let (url, hits, handle) = local_http_rpc(responses);
    let rpc = ingestion::HttpRpc::new("fixture-http", &url).unwrap();
    let error = rpc.call("eth_chainId", json!([])).unwrap_err().to_string();
    handle.join().unwrap();
    assert_eq!(hits.load(Ordering::SeqCst), 1);
    assert!(error.contains("fixture-http"));
    assert!(!error.contains("private-path"));
    assert!(!error.contains("never-print-this"));
    assert!(!error.contains("token="));
}

#[test]
fn rpc_method_allowlist_and_url_rules_prevent_signing() {
    let rpc = ingestion::HttpRpc::new("local", "http://127.0.0.1:1").unwrap();
    for method in [
        "eth_sendRawTransaction",
        "eth_sendTransaction",
        "eth_sign",
        "personal_unlockAccount",
    ] {
        assert!(rpc.call(method, json!([])).is_err());
    }
    assert!(ingestion::HttpRpc::new("bad", "http://remote.invalid").is_err());
    assert!(ingestion::HttpRpc::new("bad", "https://user:password@example.invalid").is_err());
}
#[test]
fn bridge_is_review_only_and_has_no_delivery_capability() {
    let envelope =
        ExportEnvelope::research_only("test", DataClass::Synthetic, json!({"test":true})).unwrap();
    assert!(envelope.deliver_to_observer().is_err());
    let json = serde_json::to_value(envelope).unwrap();
    assert_eq!(json["grants_execution_authority"], false);
    assert_eq!(json["namespace"], "nqc_miner_v1");
}
#[cfg(unix)]
#[test]
fn symlink_cannot_redirect_miner_state_into_observer() {
    let tmp = tempfile::tempdir().unwrap();
    let observer = tmp.path().join("observer");
    fs::create_dir(&observer).unwrap();
    let link = tmp.path().join("link");
    std::os::unix::fs::symlink(&observer, &link).unwrap();
    assert!(Journal::open(&link.join("miner"), &config()).is_err());
    assert!(!observer.join("miner").exists());
}
