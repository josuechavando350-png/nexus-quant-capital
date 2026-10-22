//! Synthetic transports only: these tests make no market/economic claims.
use nqc_miner::{
    collector::{window_config, Collector, PollResult},
    config::{DataClass, MinerConfig, ProviderSpec, ScanScope},
    discovery::{event_topics, ProtocolFamily},
    ingestion::{IngestError, QuorumRpc, ReadRpc},
    journal::{self, Journal},
};
use serde_json::{json, Value};
use std::{
    cell::Cell,
    fs,
    path::Path,
    process::{Command, Stdio},
    rc::Rc,
    thread,
    time::Duration,
};

fn hash(n: u64) -> String {
    format!("0x{n:064x}")
}
fn plan() -> MinerConfig {
    MinerConfig {
        schema_version: 2,
        namespace: "nqc_miner_v1".into(),
        producer: "nqc-miner".into(),
        run_id: "collector-fixture".into(),
        data_class: DataClass::Historical,
        code_commit: "1".repeat(40),
        cargo_lock_sha256: "2".repeat(64),
        build_identity_sha256: Some("3".repeat(64)),
        observer_bridge_enabled: false,
        signing_enabled: false,
        gas_budget_mxn_centavos: 0,
        scopes: vec![ScanScope {
            id: "fixture".into(),
            chain_id: 1,
            protocol: "aave-v3".into(),
            contract: format!("0x{:040x}", 1),
            event_topics: event_topics(ProtocolFamily::AaveV3Pool),
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
            deployment_source: "https://example.invalid/synthetic-only".into(),
        }],
    }
}
#[derive(Default)]
struct Faults {
    head: Cell<u64>,
    fail_log_from: Cell<u64>,
    mutate: Cell<u64>,
    bad_parent: Cell<u64>,
}
struct Rpc {
    id: &'static str,
    faults: Rc<Faults>,
}
impl ReadRpc for Rpc {
    fn id(&self) -> &str {
        self.id
    }
    fn call(&self, method: &str, params: Value) -> Result<Value, IngestError> {
        match method {
            "eth_chainId" => Ok(json!("0x1")),
            "eth_getBlockByNumber" => {
                let tag = params[0].as_str().unwrap();
                let n = if tag == "finalized" {
                    self.faults.head.get()
                } else {
                    u64::from_str_radix(&tag[2..], 16).unwrap()
                };
                Ok(json!({"number":format!("0x{n:x}"),
                    "hash":hash(n + 1 + if self.faults.mutate.get() == n {1000} else {0}),
                    "parentHash":hash(n + if self.faults.bad_parent.get() == n {1000} else {0}),
                    "timestamp":format!("0x{:x}",n+1000)}))
            }
            "eth_getLogs" => {
                let n = u64::from_str_radix(
                    params[0]["fromBlock"]
                        .as_str()
                        .unwrap()
                        .trim_start_matches("0x"),
                    16,
                )
                .unwrap();
                if self.faults.fail_log_from.get() == n {
                    return Err(IngestError::Provider(self.id.into()));
                }
                Ok(json!([]))
            }
            _ => panic!("non-read-only RPC method"),
        }
    }
}
fn quorum(faults: &Rc<Faults>) -> QuorumRpc {
    QuorumRpc::new(
        1,
        vec![
            Box::new(Rpc {
                id: "fixture-a",
                faults: faults.clone(),
            }),
            Box::new(Rpc {
                id: "fixture-b",
                faults: faults.clone(),
            }),
        ],
    )
    .unwrap()
}
fn faults() -> Rc<Faults> {
    Rc::new(Faults {
        head: Cell::new(200),
        ..Faults::default()
    })
}
fn child_path(root: &Path, n: u64) -> std::path::PathBuf {
    root.join(format!("window-{n:020}"))
}

#[test]
fn windows_are_contiguous_and_identity_bound() {
    let c = plan();
    let a = window_config(&c, 0).unwrap();
    let b = window_config(&c, 1).unwrap();
    assert_eq!((a.scopes[0].from_block, a.scopes[0].to_block), (100, 102));
    assert_eq!((b.scopes[0].from_block, b.scopes[0].to_block), (103, 105));
    assert_ne!(a.run_id, b.run_id);
    let mut changed = c.clone();
    changed.run_id = "another-collector".into();
    assert_ne!(a.run_id, window_config(&changed, 0).unwrap().run_id);
    assert!(window_config(&c, 10_000).is_err());
    changed.scopes[0].from_block = u64::MAX - 2;
    changed.scopes[0].to_block = u64::MAX - 1;
    assert!(window_config(&changed, 1).is_err());
}
#[test]
fn collector_refuses_shadow_synthetic_legacy_and_multiple_scopes() {
    for class in [DataClass::Shadow, DataClass::Synthetic] {
        let mut c = plan();
        c.data_class = class;
        assert!(window_config(&c, 0).is_err());
    }
    let mut c = plan();
    c.schema_version = 1;
    c.build_identity_sha256 = None;
    assert!(window_config(&c, 0).is_err());
    let mut c = plan();
    let mut second = c.scopes[0].clone();
    second.id = "second".into();
    second.chain_id = 2;
    c.scopes.push(second);
    assert!(window_config(&c, 0).is_err());
}
#[test]
fn waiting_does_not_create_or_advance_window() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("miner");
    let f = faults();
    f.head.set(101);
    let mut collector = Collector::open(&root, &plan()).unwrap();
    assert_eq!(
        collector.poll(&quorum(&f), 2000).unwrap(),
        PollResult::Waiting {
            next_to_block: 102,
            common_finalized: 101
        }
    );
    assert!(!child_path(&root, 0).exists());
    assert_eq!(collector.status().unwrap().completed_windows, 0);
}
#[test]
fn restart_reconstructs_progress_without_duplicate_windows() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("miner");
    let f = faults();
    let mut collector = Collector::open(&root, &plan()).unwrap();
    collector.poll(&quorum(&f), 2000).unwrap();
    let before = fs::read(child_path(&root, 0).join("events.jsonl")).unwrap();
    let tip = collector.status().unwrap().collection_sha256;
    drop(collector);
    let mut collector = Collector::open(&root, &plan()).unwrap();
    assert_eq!(collector.status().unwrap().collection_sha256, tip);
    assert_eq!(collector.status().unwrap().next_from_block, Some(103));
    collector.poll(&quorum(&f), 2000).unwrap();
    assert_eq!(collector.status().unwrap().completed_windows, 2);
    assert_eq!(
        fs::read(child_path(&root, 0).join("events.jsonl")).unwrap(),
        before
    );
    drop(collector);
    assert_eq!(
        Collector::open(&root, &plan())
            .unwrap()
            .status()
            .unwrap()
            .completed_windows,
        2
    );
}
#[test]
fn partial_window_resumes_after_provider_failure() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("miner");
    let f = faults();
    f.fail_log_from.set(102);
    let mut collector = Collector::open(&root, &plan()).unwrap();
    assert!(matches!(
        collector.poll(&quorum(&f), 2000),
        Err(IngestError::Provider(_))
    ));
    assert_eq!(collector.status().unwrap().completed_windows, 0);
    assert!(collector.status().unwrap().incomplete_window);
    drop(collector);
    assert_eq!(
        journal::verify(&child_path(&root, 0))
            .unwrap()
            .completed_chunks,
        1
    );
    f.fail_log_from.set(0);
    let mut collector = Collector::open(&root, &plan()).unwrap();
    collector.poll(&quorum(&f), 2000).unwrap();
    drop(collector);
    let summary = journal::verify(&child_path(&root, 0)).unwrap();
    assert_eq!(summary.completed_chunks, 2);
    assert_eq!(summary.completed_scopes, 1);
}
#[test]
fn changed_finalized_history_durably_quarantines_whole_collection() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("miner");
    let f = faults();
    let mut collector = Collector::open(&root, &plan()).unwrap();
    collector.poll(&quorum(&f), 2000).unwrap();
    f.mutate.set(102);
    assert!(collector.poll(&quorum(&f), 2000).is_err());
    assert!(collector.status().is_err());
    drop(collector);
    assert!(Collector::open(&root, &plan()).is_err());
    assert_eq!(
        journal::verify(&root).unwrap().invalidated_from.get(&1),
        Some(&100)
    );
    assert!(!child_path(&root, 1).exists());
}
#[test]
fn broken_window_boundary_quarantines_without_skipping() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("miner");
    let f = faults();
    let mut collector = Collector::open(&root, &plan()).unwrap();
    collector.poll(&quorum(&f), 2000).unwrap();
    f.bad_parent.set(103);
    assert!(collector.poll(&quorum(&f), 2000).is_err());
    assert!(collector.status().is_err());
    assert!(!child_path(&root, 1).exists());
}
#[test]
fn disagreement_is_rejected_without_claiming_success() {
    let temp = tempfile::tempdir().unwrap();
    let f = faults();
    let bad = faults();
    bad.mutate.set(200);
    let q = QuorumRpc::new(
        1,
        vec![
            Box::new(Rpc {
                id: "fixture-a",
                faults: f,
            }),
            Box::new(Rpc {
                id: "fixture-b",
                faults: bad,
            }),
        ],
    )
    .unwrap();
    let mut collector = Collector::open(&temp.path().join("miner"), &plan()).unwrap();
    assert!(matches!(
        collector.poll(&q, 2000),
        Err(IngestError::Disagreement(_))
    ));
    assert_eq!(collector.status().unwrap().completed_windows, 0);
}
#[test]
fn foreign_owner_data_and_concurrent_collectors_rejected() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("miner");
    let collector = Collector::open(&root, &plan()).unwrap();
    assert!(Collector::open(&root, &plan()).is_err());
    drop(collector);
    let mut changed = plan();
    changed.run_id = "foreign".into();
    assert!(Collector::open(&root, &changed).is_err());
    fs::write(root.join("observer.txt"), "untouched").unwrap();
    assert!(Collector::open(&root, &plan()).is_err());
    assert_eq!(
        fs::read_to_string(root.join("observer.txt")).unwrap(),
        "untouched"
    );
}
#[test]
fn missing_and_truncated_evidence_never_advance_cursor() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("miner");
    let f = faults();
    let mut collector = Collector::open(&root, &plan()).unwrap();
    collector.poll(&quorum(&f), 2000).unwrap();
    collector.poll(&quorum(&f), 2000).unwrap();
    drop(collector);
    let old = child_path(&root, 0);
    let moved = temp.path().join("retained");
    fs::rename(&old, &moved).unwrap();
    assert!(Collector::open(&root, &plan()).is_err());
    fs::rename(&moved, &old).unwrap();
    let journal = old.join("events.jsonl");
    let original = fs::read(&journal).unwrap();
    fs::write(&journal, &original[..original.len() - 2]).unwrap();
    assert!(Collector::open(&root, &plan()).is_err());
    assert_eq!(fs::read(&journal).unwrap(), original[..original.len() - 2]);
}
#[test]
fn legacy_lock_is_never_automatically_removed() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("miner");
    drop(Journal::open(&root, &plan()).unwrap());
    fs::write(root.join("writer.lock"), "12345\n").unwrap();
    assert!(Journal::open(&root, &plan()).is_err());
    assert_eq!(
        fs::read_to_string(root.join("writer.lock")).unwrap(),
        "12345\n"
    );
}
#[cfg(unix)]
#[test]
fn symlink_state_and_lock_rejected() {
    use std::os::unix::fs::symlink;
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("miner");
    drop(Collector::open(&root, &plan()).unwrap());
    let link = temp.path().join("link");
    symlink(&root, &link).unwrap();
    assert!(Collector::open(&link, &plan()).is_err());
    fs::rename(root.join("writer.lock"), temp.path().join("foreign-lock")).unwrap();
    symlink(temp.path().join("foreign-lock"), root.join("writer.lock")).unwrap();
    assert!(Collector::open(&root, &plan()).is_err());
}
// This helper only runs a child workload when its parent supplies an isolated path.
#[test]
fn crash_child() {
    if let Some(path) = std::env::var_os("NQC_MINER_TEST_CRASH_DIR") {
        let root = Path::new(&path).join("miner");
        let f = faults();
        let mut collector = Collector::open(&root, &plan()).unwrap();
        collector.poll(&quorum(&f), 2000).unwrap();
        let _partial =
            Journal::open(&child_path(&root, 1), &window_config(&plan(), 1).unwrap()).unwrap();
        fs::write(Path::new(&path).join("ready"), b"ready").unwrap();
        loop {
            thread::sleep(Duration::from_secs(1));
        }
    }
}
#[test]
fn killed_process_releases_collection_and_journal_locks() {
    let temp = tempfile::tempdir().unwrap();
    let mut child = Command::new(std::env::current_exe().unwrap())
        .args(["--exact", "crash_child", "--nocapture"])
        .env("NQC_MINER_TEST_CRASH_DIR", temp.path())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    for _ in 0..500 {
        if temp.path().join("ready").exists() {
            break;
        }
        thread::sleep(Duration::from_millis(10));
    }
    let ready = temp.path().join("ready").exists();
    let locked = Collector::open(&temp.path().join("miner"), &plan()).is_err();
    child.kill().unwrap();
    child.wait().unwrap();
    assert!(ready && locked);
    let mut collector = Collector::open(&temp.path().join("miner"), &plan()).unwrap();
    assert_eq!(collector.status().unwrap().completed_windows, 1);
    assert!(collector.status().unwrap().incomplete_window);
    collector.poll(&quorum(&faults()), 2000).unwrap();
    assert_eq!(collector.status().unwrap().completed_windows, 2);
}
