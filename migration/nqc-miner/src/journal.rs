//! Append-only, hash-chained local evidence. Hashes prove integrity, not authenticity.
//! A Miner ownership marker and an exclusive lock prevent cross-run data mixing.
use crate::{
    config::{DataClass, MinerConfig, NAMESPACE, PRODUCER},
    digest,
    discovery::{DecodedEvent, RpcLog},
    valid_hex, valid_identifier,
};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File, OpenOptions},
    io::{BufRead, BufReader, Read, Write},
    path::Path,
};
use thiserror::Error;

const MARKER: &str = "owner.json";
const JOURNAL: &str = "events.jsonl";
const CONFIG: &str = "config.json";
const MAX_LINE: usize = 1_048_576;
const ZERO_HASH: &str = "0000000000000000000000000000000000000000000000000000000000000000";

#[derive(Debug, Error)]
pub enum JournalError {
    #[error("Miner journal IO: {0}")]
    Io(#[from] std::io::Error),
    #[error("Miner journal JSON: {0}")]
    Json(#[from] serde_json::Error),
    #[error("Miner journal rejected: {0}")]
    Rejected(String),
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RunIdentity {
    pub schema: String,
    pub namespace: String,
    pub producer: String,
    pub run_id: String,
    pub data_class: DataClass,
    pub config_sha256: String,
    pub code_commit: String,
    pub cargo_lock_sha256: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub build_identity_sha256: Option<String>,
}

impl RunIdentity {
    pub fn from_config(config: &MinerConfig) -> Result<Self, JournalError> {
        let config_sha256 = config
            .integrity_hash()
            .map_err(|e| JournalError::Rejected(e.to_string()))?;
        Ok(Self {
            schema: if config.schema_version == 1 {
                "nqc-miner-owner-v1"
            } else {
                "nqc-miner-owner-v2"
            }
            .into(),
            namespace: NAMESPACE.into(),
            producer: PRODUCER.into(),
            run_id: config.run_id.clone(),
            data_class: config.data_class,
            config_sha256,
            code_commit: config.code_commit.clone(),
            cargo_lock_sha256: config.cargo_lock_sha256.clone(),
            build_identity_sha256: config.build_identity_sha256.clone(),
        })
    }
    fn validate(&self) -> Result<(), JournalError> {
        let version_valid = match (self.schema.as_str(), self.build_identity_sha256.as_deref()) {
            ("nqc-miner-owner-v1", None) => true,
            ("nqc-miner-owner-v2", Some(value)) => crate::config::valid_sha256(value),
            _ => false,
        };
        if !version_valid
            || self.namespace != NAMESPACE
            || self.producer != PRODUCER
            || !valid_identifier(&self.run_id)
            || !crate::config::valid_sha256(&self.config_sha256)
            || !crate::config::valid_sha256(&self.cargo_lock_sha256)
            || self.code_commit.len() != 40
            || !self
                .code_commit
                .bytes()
                .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
        {
            return Err(JournalError::Rejected("foreign or invalid owner".into()));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Record {
    Observed {
        scope_id: String,
        log: RpcLog,
        decoded: Box<DecodedEvent>,
        block_timestamp: u64,
        observed_at: u64,
        providers: Vec<String>,
    },
    ChunkCompleted {
        scope_id: String,
        chain_id: u64,
        from_block: u64,
        to_block: u64,
        start_block_hash: String,
        start_parent_hash: String,
        end_block_hash: String,
        observed_at: u64,
        providers: Vec<String>,
        event_count: u64,
        logs_sha256: String,
    },
    ScopeCompleted {
        scope_id: String,
        chain_id: u64,
        from_block: u64,
        to_block: u64,
        finalized_anchor_number: u64,
        finalized_anchor_hash: String,
        observed_at: u64,
        providers: Vec<String>,
    },
    Invalidated {
        chain_id: u64,
        from_block: u64,
        reason: String,
    },
}

fn valid_providers(providers: &[String]) -> bool {
    (2..=4).contains(&providers.len())
        && providers.iter().all(|p| valid_identifier(p))
        && providers.iter().collect::<BTreeSet<_>>().len() == providers.len()
}

impl Record {
    fn block_commitments(&self) -> Vec<(u64, u64, &str)> {
        match self {
            Self::Observed { log, .. } => {
                vec![(log.chain_id, log.block_number, &log.block_hash)]
            }
            Self::ChunkCompleted {
                chain_id,
                from_block,
                to_block,
                start_block_hash,
                start_parent_hash,
                end_block_hash,
                ..
            } => {
                let mut hashes = vec![
                    (*chain_id, *from_block, start_block_hash.as_str()),
                    (*chain_id, *to_block, end_block_hash.as_str()),
                ];
                if let Some(parent) = from_block.checked_sub(1) {
                    hashes.push((*chain_id, parent, start_parent_hash.as_str()));
                }
                hashes
            }
            Self::ScopeCompleted {
                chain_id,
                finalized_anchor_number,
                finalized_anchor_hash,
                ..
            } => vec![(*chain_id, *finalized_anchor_number, finalized_anchor_hash)],
            Self::Invalidated { .. } => Vec::new(),
        }
    }

    fn validate(&self, config: &MinerConfig) -> Result<(), JournalError> {
        let valid = match self {
            Self::Observed {
                scope_id,
                log,
                decoded,
                block_timestamp,
                observed_at,
                providers,
            } => {
                let scope = config
                    .scopes
                    .iter()
                    .find(|s| s.id == *scope_id)
                    .ok_or_else(|| JournalError::Rejected("foreign scope in event".into()))?;
                let family = crate::ingestion::family(&scope.protocol)
                    .map_err(|e| JournalError::Rejected(e.to_string()))?;
                let decoded_again = crate::discovery::decode_log(
                    &crate::discovery::ContractScope {
                        chain_id: scope.chain_id,
                        address: scope.contract.clone(),
                        family,
                        from_block: scope.from_block,
                        to_block: scope.to_block,
                    },
                    log,
                )
                .map_err(|e| JournalError::Rejected(e.to_string()))?;
                valid_identifier(scope_id)
                    && log.chain_id > 0
                    && !log.removed
                    && valid_hex(&log.address, 20)
                    && valid_hex(&log.block_hash, 32)
                    && valid_hex(&log.transaction_hash, 32)
                    && *block_timestamp > 0
                    && *observed_at >= *block_timestamp
                    && valid_providers(providers)
                    && scope.providers.iter().map(|p| &p.id).eq(providers.iter())
                    && scope.event_topics.contains(&log.topics[0])
                    && decoded.as_ref() == &decoded_again
            }
            Self::ChunkCompleted {
                scope_id,
                chain_id,
                from_block,
                to_block,
                start_block_hash,
                start_parent_hash,
                end_block_hash,
                observed_at,
                providers,
                logs_sha256,
                ..
            } => {
                let scope = config
                    .scopes
                    .iter()
                    .find(|s| s.id == *scope_id)
                    .ok_or_else(|| JournalError::Rejected("foreign scope in chunk".into()))?;
                valid_identifier(scope_id)
                    && *chain_id > 0
                    && from_block <= to_block
                    && valid_hex(start_block_hash, 32)
                    && valid_hex(end_block_hash, 32)
                    && valid_hex(start_parent_hash, 32)
                    && *chain_id == scope.chain_id
                    && *from_block >= scope.from_block
                    && *to_block <= scope.to_block
                    && (*from_block - scope.from_block) % scope.chunk_blocks == 0
                    && *to_block
                        == from_block
                            .saturating_add(scope.chunk_blocks - 1)
                            .min(scope.to_block)
                    && scope.providers.iter().map(|p| &p.id).eq(providers.iter())
                    && *observed_at > 0
                    && valid_providers(providers)
                    && crate::config::valid_sha256(logs_sha256)
            }
            Self::ScopeCompleted {
                scope_id,
                chain_id,
                from_block,
                to_block,
                finalized_anchor_number,
                finalized_anchor_hash,
                observed_at,
                providers,
            } => {
                let scope = config
                    .scopes
                    .iter()
                    .find(|s| s.id == *scope_id)
                    .ok_or_else(|| JournalError::Rejected("foreign scope completion".into()))?;
                *chain_id == scope.chain_id
                    && *from_block == scope.from_block
                    && *to_block == scope.to_block
                    && finalized_anchor_number >= to_block
                    && valid_hex(finalized_anchor_hash, 32)
                    && *observed_at > 0
                    && valid_providers(providers)
                    && scope.providers.iter().map(|p| &p.id).eq(providers.iter())
            }
            Self::Invalidated {
                chain_id, reason, ..
            } => {
                *chain_id > 0
                    && config.scopes.iter().any(|s| s.chain_id == *chain_id)
                    && !reason.is_empty()
                    && reason.len() <= 256
            }
        };
        if valid {
            Ok(())
        } else {
            Err(JournalError::Rejected("invalid evidence record".into()))
        }
    }

    fn event_key_and_digest(&self) -> Result<Option<(String, String)>, JournalError> {
        match self {
            Self::Observed {
                log,
                decoded,
                block_timestamp,
                ..
            } => Ok(Some((
                format!("{}:{}:{}", log.chain_id, log.block_hash, log.log_index),
                digest(&serde_json::to_vec(&(log, decoded, block_timestamp))?),
            ))),
            _ => Ok(None),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Envelope {
    pub sequence: u64,
    pub owner_sha256: String,
    pub previous_sha256: String,
    pub record: Record,
    pub sha256: String,
}

fn envelope_digest(
    sequence: u64,
    owner: &str,
    previous: &str,
    record: &Record,
) -> Result<String, JournalError> {
    Ok(digest(&serde_json::to_vec(&(
        sequence, owner, previous, record,
    ))?))
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JournalSummary {
    pub owner: RunIdentity,
    pub records: u64,
    pub canonical_events: u64,
    pub invalidated_events: u64,
    pub provisional_events: u64,
    pub completed_chunks: u64,
    pub completed_scopes: u64,
    pub invalidated_from: BTreeMap<u64, u64>,
    pub last_sha256: String,
    pub integrity_verified: bool,
    pub authenticity_verified: bool,
}

// The kernel releases this lock even on SIGKILL. Never unlink its inode: doing
// so could let two writers lock different files with the same pathname.
struct LockGuard {
    _file: File,
}
const LOCK_MAGIC: &[u8] = b"nqc-miner-kernel-lock-v1\n";

pub(crate) fn reject_symlink(path: &Path) -> Result<(), JournalError> {
    // Do not follow even an ancestor symlink into another workspace/state directory.
    for component in path.ancestors() {
        if component.as_os_str().is_empty() {
            continue;
        }
        match fs::symlink_metadata(component) {
            Ok(metadata) if metadata.file_type().is_symlink() => {
                return Err(JournalError::Rejected("symlink in state path".into()))
            }
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(error.into()),
        }
    }
    Ok(())
}

fn acquire_lock(path: &Path) -> Result<LockGuard, JournalError> {
    let lock_path = path.join("writer.lock");
    reject_symlink(&lock_path)?;
    let (mut lock, created) = match OpenOptions::new()
        .read(true)
        .write(true)
        .create_new(true)
        .open(&lock_path)
    {
        Ok(file) => (file, true),
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => (
            OpenOptions::new().read(true).write(true).open(&lock_path)?,
            false,
        ),
        Err(error) => return Err(error.into()),
    };
    lock.try_lock().map_err(|_| {
        JournalError::Rejected("state is locked or filesystem locking is unsupported".into())
    })?;
    if created {
        lock.write_all(LOCK_MAGIC)?;
        lock.sync_all()?;
        File::open(path)?.sync_all()?;
    } else {
        let mut bytes = Vec::new();
        (&mut lock).take(128).read_to_end(&mut bytes)?;
        if bytes != LOCK_MAGIC {
            return Err(JournalError::Rejected("legacy, incomplete or foreign lock; requires manual inspection, never automatic removal".into()));
        }
    }
    Ok(LockGuard { _file: lock })
}

pub struct Journal {
    owner: RunIdentity,
    config: MinerConfig,
    owner_hash: String,
    file: File,
    envelopes: Vec<Envelope>,
    seen: BTreeMap<String, String>,
    poisoned: bool,
    _lock: LockGuard,
}

impl Journal {
    pub fn open(path: &Path, config: &MinerConfig) -> Result<Self, JournalError> {
        let expected = RunIdentity::from_config(config)?;
        reject_symlink(path)?;
        if !path.exists() {
            // Parent must already exist; never create an arbitrary tree.
            fs::create_dir(path)?;
            let mut marker = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(path.join(MARKER))?;
            marker.write_all(&serde_json::to_vec_pretty(&expected)?)?;
            marker.sync_all()?;
            let mut manifest = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(path.join(CONFIG))?;
            manifest.write_all(&serde_json::to_vec_pretty(config)?)?;
            manifest.sync_all()?;
            File::open(path)?.sync_all()?;
        }
        reject_symlink(&path.join(MARKER))?;
        let owner: RunIdentity = serde_json::from_slice(&fs::read(path.join(MARKER))?)?;
        owner.validate()?;
        if owner != expected {
            return Err(JournalError::Rejected(
                "state directory belongs to a different run, class, configuration or code revision"
                    .into(),
            ));
        }
        let lock = acquire_lock(path)?;
        let stored_config = read_config(path, &owner)?;
        if &stored_config != config {
            return Err(JournalError::Rejected(
                "configuration manifest changed".into(),
            ));
        }
        reject_symlink(&path.join(JOURNAL))?;
        let envelopes = read_envelopes(path, &owner, config)?;
        let owner_hash = digest(&serde_json::to_vec(&owner)?);
        let mut seen = BTreeMap::new();
        for envelope in &envelopes {
            if let Some((key, value)) = envelope.record.event_key_and_digest()? {
                seen.insert(key, value);
            }
        }
        let file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(path.join(JOURNAL))?;
        File::open(path)?.sync_all()?;
        Ok(Self {
            owner,
            config: config.clone(),
            owner_hash,
            file,
            envelopes,
            seen,
            poisoned: false,
            _lock: lock,
        })
    }

    pub fn records(&self) -> &[Envelope] {
        &self.envelopes
    }
    pub fn owner(&self) -> &RunIdentity {
        &self.owner
    }
    pub fn config(&self) -> &MinerConfig {
        &self.config
    }

    /// Returns false for an identical event replay. Conflicting bytes are errors.
    pub fn append(&mut self, record: Record) -> Result<bool, JournalError> {
        if self.poisoned {
            return Err(JournalError::Rejected(
                "journal writer is poisoned after a failed durable write".into(),
            ));
        }
        record.validate(&self.config)?;
        validate_block_commitments(&record, &self.envelopes)?;
        let event_key = record.event_key_and_digest()?;
        if let Some((key, value)) = &event_key {
            if let Some(existing) = self.seen.get(key) {
                if existing == value {
                    return Ok(false);
                }
                return Err(JournalError::Rejected(
                    "same event identity has conflicting contents".into(),
                ));
            }
        }
        let invalidations = invalidations(&self.envelopes);
        let affected = match &record {
            Record::Observed { log, .. } => invalidations
                .get(&log.chain_id)
                .is_some_and(|start| log.block_number >= *start),
            Record::ChunkCompleted {
                chain_id, to_block, ..
            } => invalidations
                .get(chain_id)
                .is_some_and(|start| to_block >= start),
            Record::ScopeCompleted {
                chain_id, to_block, ..
            } => invalidations
                .get(chain_id)
                .is_some_and(|start| to_block >= start),
            _ => false,
        };
        if affected {
            return Err(JournalError::Rejected(
                "invalidated range requires a new run; old evidence is preserved".into(),
            ));
        }
        if let Record::ScopeCompleted { scope_id, .. } = &record {
            if self
                .envelopes
                .iter()
                .any(|e| matches!(&e.record,Record::ScopeCompleted{scope_id:id,..} if id==scope_id))
            {
                return Ok(false);
            }
        }
        validate_sequence(&record, &self.envelopes, &self.config)?;
        let sequence = u64::try_from(self.envelopes.len())
            .map_err(|_| JournalError::Rejected("sequence overflow".into()))?;
        let previous_sha256 = self
            .envelopes
            .last()
            .map_or(ZERO_HASH, |item| &item.sha256)
            .to_owned();
        let sha256 = envelope_digest(sequence, &self.owner_hash, &previous_sha256, &record)?;
        let envelope = Envelope {
            sequence,
            owner_sha256: self.owner_hash.clone(),
            previous_sha256,
            record,
            sha256,
        };
        let mut bytes = serde_json::to_vec(&envelope)?;
        if bytes.len() > MAX_LINE {
            return Err(JournalError::Rejected("record too large".into()));
        }
        bytes.push(b'\n');
        if let Err(error) = self
            .file
            .write_all(&bytes)
            .and_then(|()| self.file.sync_all())
        {
            self.poisoned = true;
            return Err(error.into());
        }
        if let Some((key, value)) = event_key {
            self.seen.insert(key, value);
        }
        self.envelopes.push(envelope);
        Ok(true)
    }

    pub fn summary(&self) -> JournalSummary {
        summarize(&self.owner, &self.envelopes)
    }
}

fn read_config(path: &Path, owner: &RunIdentity) -> Result<MinerConfig, JournalError> {
    reject_symlink(&path.join(CONFIG))?;
    let config =
        MinerConfig::load(&path.join(CONFIG)).map_err(|e| JournalError::Rejected(e.to_string()))?;
    if RunIdentity::from_config(&config)? != *owner {
        return Err(JournalError::Rejected(
            "stored manifest does not match owner identity".into(),
        ));
    }
    Ok(config)
}

fn read_envelopes(
    path: &Path,
    owner: &RunIdentity,
    config: &MinerConfig,
) -> Result<Vec<Envelope>, JournalError> {
    let journal_path = path.join(JOURNAL);
    reject_symlink(&journal_path)?;
    if !journal_path.exists() {
        return Ok(Vec::new());
    }
    let file = File::open(journal_path)?;
    if file.metadata()?.len() > 512 * 1024 * 1024 {
        return Err(JournalError::Rejected(
            "local journal exceeds bounded 512 MiB segment; rotate to a new run".into(),
        ));
    }
    let mut reader = BufReader::new(file);
    let owner_hash = digest(&serde_json::to_vec(owner)?);
    let mut result: Vec<Envelope> = Vec::new();
    let mut events = BTreeMap::new();
    loop {
        let mut line = Vec::new();
        let read = reader.read_until(b'\n', &mut line)?;
        if read == 0 {
            break;
        }
        if line.len() > MAX_LINE + 1 || line.last() != Some(&b'\n') {
            return Err(JournalError::Rejected(
                "oversize or torn final record; evidence is not silently truncated".into(),
            ));
        }
        let envelope: Envelope = serde_json::from_slice(&line)?;
        envelope.record.validate(config)?;
        validate_sequence(&envelope.record, &result, config)?;
        let previous = result.last().map_or(ZERO_HASH, |item| &item.sha256);
        if envelope.sequence != result.len() as u64
            || envelope.owner_sha256 != owner_hash
            || envelope.previous_sha256 != previous
            || envelope.sha256
                != envelope_digest(envelope.sequence, &owner_hash, previous, &envelope.record)?
        {
            return Err(JournalError::Rejected(
                "hash chain, identity or sequence mismatch".into(),
            ));
        }
        if let Some((key, hash)) = envelope.record.event_key_and_digest()? {
            if events.insert(key, hash).is_some() {
                return Err(JournalError::Rejected(
                    "duplicate canonical event in durable journal".into(),
                ));
            }
        }
        result.push(envelope);
    }
    Ok(result)
}

fn validate_sequence(
    record: &Record,
    prior: &[Envelope],
    config: &MinerConfig,
) -> Result<(), JournalError> {
    let reject = |message: &str| JournalError::Rejected(message.into());
    validate_block_commitments(record, prior)?;
    match record {
        Record::Observed { scope_id, log, .. } => {
            for previous in prior {
                match &previous.record {
                    Record::Observed { log: old, .. }
                        if old.chain_id == log.chain_id
                            && old.block_number == log.block_number
                            && old.block_hash != log.block_hash =>
                    {
                        return Err(reject("conflicting canonical block hashes"))
                    }
                    Record::ChunkCompleted {
                        scope_id: old,
                        from_block,
                        to_block,
                        ..
                    } if old == scope_id
                        && (*from_block..=*to_block).contains(&log.block_number) =>
                    {
                        return Err(reject("cannot append a new event into a completed chunk"))
                    }
                    Record::Invalidated {
                        chain_id,
                        from_block,
                        ..
                    } if *chain_id == log.chain_id && log.block_number >= *from_block => {
                        return Err(reject("event follows canonical invalidation"))
                    }
                    _ => {}
                }
            }
        }
        Record::ChunkCompleted {
            scope_id,
            chain_id,
            from_block,
            to_block,
            start_parent_hash,
            event_count,
            logs_sha256,
            ..
        } => {
            let scope = config
                .scopes
                .iter()
                .find(|s| s.id == *scope_id)
                .ok_or_else(|| reject("missing scope"))?;
            let previous = prior.iter().rev().find_map(|entry| match &entry.record {
                Record::ChunkCompleted {
                    scope_id: old,
                    to_block,
                    end_block_hash,
                    ..
                } if old == scope_id => Some((*to_block, end_block_hash)),
                _ => None,
            });
            if let Some((end, hash)) = previous {
                if end.checked_add(1) != Some(*from_block) || hash != start_parent_hash {
                    return Err(reject("noncontiguous chunk ancestry"));
                }
            } else if *from_block != scope.from_block {
                return Err(reject("first chunk skips configured start"));
            }
            if invalidations(prior)
                .get(chain_id)
                .is_some_and(|start| to_block >= start)
            {
                return Err(reject("chunk follows canonical invalidation"));
            }
            let mut logs = prior
                .iter()
                .filter_map(|entry| match &entry.record {
                    Record::Observed {
                        scope_id: old, log, ..
                    } if old == scope_id
                        && (*from_block..=*to_block).contains(&log.block_number) =>
                    {
                        Some(log.clone())
                    }
                    _ => None,
                })
                .collect::<Vec<_>>();
            logs.sort_by_key(|log| (log.block_number, log.log_index));
            if logs.len() as u64 != *event_count
                || digest(&serde_json::to_vec(&logs)?) != *logs_sha256
            {
                return Err(reject(
                    "completed chunk does not reconcile with durable raw logs",
                ));
            }
        }
        Record::ScopeCompleted {
            scope_id,
            chain_id,
            to_block,
            finalized_anchor_number,
            finalized_anchor_hash,
            ..
        } => {
            if invalidations(prior)
                .get(chain_id)
                .is_some_and(|start| to_block >= start)
            {
                return Err(reject("scope follows canonical invalidation"));
            }
            if prior
                .iter()
                .any(|e| matches!(&e.record,Record::ScopeCompleted{scope_id:id,..}if id==scope_id))
            {
                return Err(reject("duplicate scope completion"));
            }
            let last = prior.iter().rev().find_map(|e| match &e.record {
                Record::ChunkCompleted {
                    scope_id: id,
                    to_block,
                    end_block_hash,
                    ..
                } if id == scope_id => Some((*to_block, end_block_hash)),
                _ => None,
            });
            match last {
                Some((height, hash))
                    if height == *to_block
                        && (finalized_anchor_number != to_block
                            || finalized_anchor_hash == hash) => {}
                _ => {
                    return Err(reject(
                        "scope completed before its exact finalized interval",
                    ))
                }
            }
        }
        Record::Invalidated { .. } => {}
    }
    Ok(())
}

/// Every persisted block identity, across all scopes and provisional records.
/// This is a consistency index, not cryptographic verification of chain history.
pub fn known_block_hashes(
    records: &[Envelope],
) -> Result<BTreeMap<(u64, u64), String>, JournalError> {
    let mut hashes = BTreeMap::new();
    for entry in records {
        for (chain, height, hash) in entry.record.block_commitments() {
            if hashes
                .insert((chain, height), hash.to_owned())
                .is_some_and(|previous| previous != hash)
            {
                return Err(JournalError::Rejected(
                    "conflicting block commitments across scopes".into(),
                ));
            }
        }
    }
    Ok(hashes)
}

fn validate_block_commitments(record: &Record, prior: &[Envelope]) -> Result<(), JournalError> {
    let mut hashes = known_block_hashes(prior)?;
    for (chain, height, hash) in record.block_commitments() {
        if hashes
            .insert((chain, height), hash.to_owned())
            .is_some_and(|previous| previous != hash)
        {
            return Err(JournalError::Rejected(
                "conflicting block commitments across scopes".into(),
            ));
        }
    }
    Ok(())
}

pub fn event_committed(scope_id: &str, block: u64, records: &[Envelope]) -> bool {
    records.iter().any(|entry| {
        matches!(&entry.record, Record::ChunkCompleted {scope_id:id,from_block,to_block,..}
        if id==scope_id && (*from_block..=*to_block).contains(&block))
    })
}

fn invalidations(records: &[Envelope]) -> BTreeMap<u64, u64> {
    let mut map: BTreeMap<u64, u64> = BTreeMap::new();
    for envelope in records {
        if let Record::Invalidated {
            chain_id,
            from_block,
            ..
        } = envelope.record
        {
            map.entry(chain_id)
                .and_modify(|start| *start = (*start).min(from_block))
                .or_insert(from_block);
        }
    }
    map
}

fn summarize(owner: &RunIdentity, records: &[Envelope]) -> JournalSummary {
    let invalidated_from = invalidations(records);
    let mut canonical_events = 0;
    let mut invalidated_events = 0;
    let mut provisional_events = 0;
    let mut completed_chunks = 0;
    let mut completed_scopes = 0;
    for envelope in records {
        match &envelope.record {
            Record::Observed { scope_id, log, .. } => {
                if invalidated_from
                    .get(&log.chain_id)
                    .is_some_and(|start| log.block_number >= *start)
                {
                    invalidated_events += 1;
                } else if !event_committed(scope_id, log.block_number, records) {
                    provisional_events += 1;
                } else {
                    canonical_events += 1;
                }
            }
            Record::ChunkCompleted {
                chain_id, to_block, ..
            } => {
                if invalidated_from
                    .get(chain_id)
                    .is_none_or(|start| to_block < start)
                {
                    completed_chunks += 1;
                }
            }
            Record::ScopeCompleted {
                chain_id, to_block, ..
            } => {
                if invalidated_from
                    .get(chain_id)
                    .is_none_or(|start| to_block < start)
                {
                    completed_scopes += 1;
                }
            }
            _ => {}
        }
    }
    JournalSummary {
        owner: owner.clone(),
        records: records.len() as u64,
        canonical_events,
        invalidated_events,
        provisional_events,
        completed_chunks,
        completed_scopes,
        invalidated_from,
        last_sha256: records.last().map_or(ZERO_HASH, |item| &item.sha256).into(),
        integrity_verified: true,
        authenticity_verified: false,
    }
}

/// Verification acquires the same lock as a writer: no racing partial reads.
pub fn verify(path: &Path) -> Result<JournalSummary, JournalError> {
    reject_symlink(path)?;
    reject_symlink(&path.join(MARKER))?;
    let owner: RunIdentity = serde_json::from_slice(&fs::read(path.join(MARKER))?)?;
    owner.validate()?;
    let _lock = acquire_lock(path)?;
    let config = read_config(path, &owner)?;
    Ok(summarize(&owner, &read_envelopes(path, &owner, &config)?))
}

pub fn read_verified(path: &Path) -> Result<(RunIdentity, Vec<Envelope>), JournalError> {
    reject_symlink(path)?;
    reject_symlink(&path.join(MARKER))?;
    let owner: RunIdentity = serde_json::from_slice(&fs::read(path.join(MARKER))?)?;
    owner.validate()?;
    let _lock = acquire_lock(path)?;
    let config = read_config(path, &owner)?;
    let records = read_envelopes(path, &owner, &config)?;
    Ok((owner, records))
}
