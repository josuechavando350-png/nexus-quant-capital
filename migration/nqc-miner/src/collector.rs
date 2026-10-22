//! Rolling historical collection. Each window retains a complete, immutable
//! config and the existing hash-chained journal. No mutable cursor is trusted.
use crate::{
    config::{DataClass, MinerConfig},
    digest,
    ingestion::{self, IngestError, QuorumRpc},
    journal::{self, Journal, JournalError, Record},
};
use serde::Serialize;
use std::{
    collections::BTreeMap,
    fs::{self, File, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
};

const MAX_WINDOWS: u64 = 10_000;
const MARKER: &str = "collector.json";

fn reject(message: &str) -> IngestError {
    IngestError::Rejected(message.into())
}
fn io(error: std::io::Error) -> IngestError {
    JournalError::Io(error).into()
}

/// A collector has one explicit chain/contract/topic scope. Separate collectors
/// provide independent lag and failure domains; catch-up is always historical.
pub fn window_config(plan: &MinerConfig, index: u64) -> Result<MinerConfig, IngestError> {
    ingestion::validate_runtime(plan)?;
    if plan.scopes.len() != 1 || plan.data_class != DataClass::Historical || index >= MAX_WINDOWS {
        return Err(reject(
            "collector requires one historical scope and at most 10000 windows",
        ));
    }
    let base = &plan.scopes[0];
    let width = base.to_block - base.from_block + 1;
    let offset = index
        .checked_mul(width)
        .ok_or_else(|| reject("collector range overflow"))?;
    let mut config = plan.clone();
    config.scopes[0].from_block = base
        .from_block
        .checked_add(offset)
        .ok_or_else(|| reject("collector range overflow"))?;
    config.scopes[0].to_block = base
        .to_block
        .checked_add(offset)
        .filter(|n| *n < u64::MAX)
        .ok_or_else(|| reject("collector range overflow"))?;
    config.run_id = format!(
        "window-{}",
        digest(
            format!(
                "{}:{index}",
                plan.integrity_hash().map_err(|e| reject(&e.to_string()))?
            )
            .as_bytes()
        )
    );
    config.validate().map_err(|e| reject(&e.to_string()))?;
    Ok(config)
}

#[derive(Debug, Serialize)]
pub struct CollectorStatus {
    pub schema: &'static str,
    pub run_id: String,
    pub plan_sha256: String,
    pub completed_windows: u64,
    pub incomplete_window: bool,
    pub next_from_block: Option<u64>,
    pub canonical_events_in_completed_windows: u64,
    pub collection_sha256: String,
    pub integrity_verified: bool,
    pub chain_authenticity_verified: bool,
    pub data_class: DataClass,
    pub observer_bridge_enabled: bool,
    pub signing_enabled: bool,
    pub economic_certification: bool,
}

#[derive(Debug, Serialize, PartialEq, Eq)]
#[serde(tag = "status", rename_all = "snake_case")]
pub enum PollResult {
    Waiting {
        next_to_block: u64,
        common_finalized: u64,
    },
    Completed {
        window_index: u64,
        from_block: u64,
        to_block: u64,
    },
}

pub struct Collector {
    root: PathBuf,
    plan: MinerConfig,
    // Locks the whole collection before child journals are inspected or opened.
    control: Journal,
    completed: u64,
    incomplete: bool,
    events: u64,
    tip: String,
    last_end_hash: Option<String>,
    commitments: BTreeMap<(u64, u64), String>,
}

impl Collector {
    pub fn open(root: &Path, plan: &MinerConfig) -> Result<Self, IngestError> {
        window_config(plan, 0)?;
        journal::reject_symlink(root)?;
        let fresh = !root.exists();
        let control = Journal::open(root, plan)?;
        let marker = serde_json::json!({"schema":"nqc-miner-collector-v1",
            "plan_sha256":plan.integrity_hash().map_err(|e| reject(&e.to_string()))?});
        let marker_bytes = serde_json::to_vec(&marker).map_err(JournalError::Json)?;
        if fresh {
            let mut file = OpenOptions::new()
                .create_new(true)
                .write(true)
                .open(root.join(MARKER))
                .map_err(io)?;
            file.write_all(&marker_bytes).map_err(io)?;
            file.sync_all().map_err(io)?;
            File::open(root).map_err(io)?.sync_all().map_err(io)?;
        }
        journal::reject_symlink(&root.join(MARKER))?;
        if fs::read(root.join(MARKER)).map_err(io)? != marker_bytes || !control.records().is_empty()
        {
            return Err(reject(
                "collection is foreign, quarantined or has unexpected control records",
            ));
        }
        let mut indices = Vec::new();
        for entry in fs::read_dir(root).map_err(io)? {
            let entry = entry.map_err(io)?;
            let name = entry
                .file_name()
                .into_string()
                .map_err(|_| reject("invalid collection entry"))?;
            if [
                MARKER,
                "owner.json",
                "config.json",
                "events.jsonl",
                "writer.lock",
            ]
            .contains(&name.as_str())
            {
                continue;
            }
            let index = name
                .strip_prefix("window-")
                .and_then(|s| s.parse::<u64>().ok())
                .filter(|i| name == format!("window-{i:020}") && *i < MAX_WINDOWS)
                .ok_or_else(|| {
                    reject("unexpected collection entry; refusing to adopt foreign data")
                })?;
            journal::reject_symlink(&entry.path())?;
            if !entry.file_type().map_err(io)?.is_dir() {
                return Err(reject("window is not a directory"));
            }
            indices.push(index);
        }
        indices.sort_unstable();
        let mut collector = Self {
            root: root.into(),
            plan: plan.clone(),
            control,
            completed: 0,
            incomplete: false,
            events: 0,
            tip: "0".repeat(64),
            last_end_hash: None,
            commitments: BTreeMap::new(),
        };
        for (expected, index) in indices.iter().enumerate() {
            if *index != expected as u64 || collector.incomplete {
                return Err(reject(
                    "missing window or a window follows incomplete evidence",
                ));
            }
            let config = window_config(plan, *index)?;
            let window = Journal::open(&collector.window_path(*index), &config)?;
            collector.inspect(&window)?;
            if window.summary().completed_scopes == 1 {
                collector.accept(&window)?;
            } else {
                collector.incomplete = true;
            }
        }
        Ok(collector)
    }

    fn window_path(&self, index: u64) -> PathBuf {
        self.root.join(format!("window-{index:020}"))
    }

    fn quarantine(&mut self) -> Result<(), IngestError> {
        if self.control.records().is_empty() {
            self.control.append(Record::Invalidated {
                chain_id: self.plan.scopes[0].chain_id,
                from_block: self.plan.scopes[0].from_block,
                reason: "collector canonical history changed; entire collection quarantined".into(),
            })?;
        }
        Err(reject(
            "collector canonical history changed; entire collection quarantined",
        ))
    }

    fn inspect(&mut self, window: &Journal) -> Result<(), IngestError> {
        let summary = window.summary();
        if !summary.invalidated_from.is_empty() {
            return self.quarantine();
        }
        for (key, hash) in journal::known_block_hashes(window.records())? {
            if self
                .commitments
                .get(&key)
                .is_some_and(|previous| previous != &hash)
            {
                return self.quarantine();
            }
        }
        let first_parent = window.records().iter().find_map(|e| match &e.record {
            Record::ChunkCompleted {
                start_parent_hash, ..
            } => Some(start_parent_hash),
            _ => None,
        });
        if self
            .last_end_hash
            .as_ref()
            .zip(first_parent)
            .is_some_and(|(a, b)| a != b)
        {
            return self.quarantine();
        }
        Ok(())
    }

    fn accept(&mut self, window: &Journal) -> Result<(), IngestError> {
        let summary = window.summary();
        if summary.completed_scopes != 1
            || summary.provisional_events != 0
            || !summary.invalidated_from.is_empty()
        {
            return Err(reject("incomplete window cannot advance the collector"));
        }
        self.commitments
            .extend(journal::known_block_hashes(window.records())?);
        self.last_end_hash = window.records().iter().rev().find_map(|e| match &e.record {
            Record::ChunkCompleted { end_block_hash, .. } => Some(end_block_hash.clone()),
            _ => None,
        });
        self.tip = digest(
            format!(
                "{}:{}:{}:{}",
                self.tip, self.completed, summary.owner.config_sha256, summary.last_sha256
            )
            .as_bytes(),
        );
        self.events += summary.canonical_events;
        self.completed += 1;
        self.incomplete = false;
        Ok(())
    }

    /// One bounded window per poll. Provider failure leaves the durable cursor
    /// unchanged. On restart every stored window and cross-window link is checked.
    pub fn poll(
        &mut self,
        quorum: &QuorumRpc,
        observed_at: u64,
    ) -> Result<PollResult, IngestError> {
        if !self.control.records().is_empty() {
            return Err(reject("collection is quarantined"));
        }
        let config = window_config(&self.plan, self.completed)?;
        let scope = &config.scopes[0];
        // Recheck the previous complete journal, including its finalization anchor,
        // before advancing; boundary linkage connects it to the next window.
        if self.completed > 0 {
            let previous = window_config(&self.plan, self.completed - 1)?;
            let mut window = Journal::open(&self.window_path(self.completed - 1), &previous)?;
            let result =
                ingestion::scan_scope(&previous.scopes[0], quorum, &mut window, observed_at);
            if !window.summary().invalidated_from.is_empty() {
                return self.quarantine().map(|_| unreachable!());
            }
            result?;
        }
        let finalized = quorum.common_finalized()?;
        if observed_at < finalized.timestamp {
            return Err(reject("collector clock predates finalized head"));
        }
        if finalized.number < scope.to_block {
            return Ok(PollResult::Waiting {
                next_to_block: scope.to_block,
                common_finalized: finalized.number,
            });
        }
        if let Some(previous) = &self.last_end_hash {
            if &quorum.block(scope.from_block)?.parent_hash != previous {
                return self.quarantine().map(|_| unreachable!());
            }
        }
        let mut window = Journal::open(&self.window_path(self.completed), &config)?;
        self.incomplete = true;
        let result = ingestion::scan_scope(scope, quorum, &mut window, observed_at);
        self.inspect(&window)?;
        result?;
        let outcome = PollResult::Completed {
            window_index: self.completed,
            from_block: scope.from_block,
            to_block: scope.to_block,
        };
        self.accept(&window)?;
        Ok(outcome)
    }

    pub fn status(&self) -> Result<CollectorStatus, IngestError> {
        if !self.control.records().is_empty() {
            return Err(reject("collection is quarantined"));
        }
        Ok(CollectorStatus {
            schema: "nqc-miner-collector-status-v1",
            run_id: self.plan.run_id.clone(),
            plan_sha256: self
                .plan
                .integrity_hash()
                .map_err(|e| reject(&e.to_string()))?,
            completed_windows: self.completed,
            incomplete_window: self.incomplete,
            next_from_block: window_config(&self.plan, self.completed)
                .ok()
                .map(|c| c.scopes[0].from_block),
            canonical_events_in_completed_windows: self.events,
            collection_sha256: self.tip.clone(),
            integrity_verified: true,
            chain_authenticity_verified: false,
            data_class: DataClass::Historical,
            observer_bridge_enabled: false,
            signing_enabled: false,
            economic_certification: false,
        })
    }
}
