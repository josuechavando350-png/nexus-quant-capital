//! Bounded read-only JSON-RPC ingestion with independent endpoint agreement.
//! Agreement is evidence, not a cryptographic proof of RPC truth or independence.
use crate::{
    config::{MinerConfig, ProviderSpec, ScanScope},
    discovery::{self, ContractScope, ProtocolFamily, RpcLog},
    journal::{Journal, JournalError, Record},
    valid_hex,
};
use reqwest::{blocking::Client, header::RETRY_AFTER, StatusCode};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    io::Read,
    sync::Mutex,
    time::{Duration, Instant},
};
use thiserror::Error;

const MAX_RESPONSE: u64 = 16 * 1024 * 1024;
const MAX_RPC_ATTEMPTS: usize = 4;
const MIN_REQUEST_GAP: Duration = Duration::from_millis(125);
const MAX_SERVER_RETRY: Duration = Duration::from_secs(5);
const METHODS: &[&str] = &["eth_chainId", "eth_getBlockByNumber", "eth_getLogs"];

fn retryable_status(status: StatusCode) -> bool {
    matches!(status.as_u16(), 408 | 425 | 429 | 500 | 502 | 503 | 504)
}

fn retry_delay(status: Option<StatusCode>, retry_after: Option<&str>, attempt: usize) -> Duration {
    let base = Duration::from_millis(250u64.saturating_mul(1u64 << attempt.min(3)));
    if status == Some(StatusCode::TOO_MANY_REQUESTS) {
        if let Some(seconds) = retry_after.and_then(|value| value.trim().parse::<u64>().ok()) {
            return base.max(Duration::from_secs(seconds).min(MAX_SERVER_RETRY));
        }
    }
    base.min(MAX_SERVER_RETRY)
}

#[derive(Debug, Error)]
pub enum IngestError {
    #[error("read-only RPC rejected: {0}")]
    Rejected(String),
    #[error("read-only RPC provider {0} failed (endpoint details redacted)")]
    Provider(String),
    #[error("RPC providers disagree: {0}")]
    Disagreement(String),
    #[error("journal: {0}")]
    Journal(#[from] JournalError),
}

pub trait ReadRpc {
    fn id(&self) -> &str;
    fn call(&self, method: &str, params: Value) -> Result<Value, IngestError>;
}

pub struct HttpRpc {
    id: String,
    endpoint: reqwest::Url,
    client: Client,
    last_request: Mutex<Option<Instant>>,
}

impl HttpRpc {
    pub fn from_env(spec: &ProviderSpec) -> Result<Self, IngestError> {
        if !spec.url_env.starts_with("NQC_MINER_RPC_") {
            return Err(IngestError::Rejected("foreign credential namespace".into()));
        }
        let value = std::env::var(&spec.url_env).map_err(|_| {
            IngestError::Rejected(format!("missing environment variable {}", spec.url_env))
        })?;
        Self::new(&spec.id, &value)
    }
    pub fn new(id: &str, url: &str) -> Result<Self, IngestError> {
        if !crate::valid_identifier(id) {
            return Err(IngestError::Rejected("invalid provider id".into()));
        }
        let endpoint = reqwest::Url::parse(url)
            .map_err(|_| IngestError::Rejected("invalid RPC URL (redacted)".into()))?;
        let local = matches!(
            endpoint.host_str(),
            Some("127.0.0.1" | "localhost" | "[::1]" | "::1")
        );
        if !(endpoint.scheme() == "https" || local && endpoint.scheme() == "http")
            || !endpoint.username().is_empty()
            || endpoint.password().is_some()
            || endpoint.fragment().is_some()
            || endpoint.host_str().is_none()
        {
            return Err(IngestError::Rejected(
                "RPC requires HTTPS without userinfo, or a loopback HTTP test server".into(),
            ));
        }
        let client = Client::builder()
            .timeout(Duration::from_secs(15))
            .connect_timeout(Duration::from_secs(5))
            .redirect(reqwest::redirect::Policy::none())
            .user_agent("nqc-miner/0.1 read-only")
            .build()
            .map_err(|_| IngestError::Provider(id.into()))?;
        Ok(Self {
            id: id.into(),
            endpoint,
            client,
            last_request: Mutex::new(None),
        })
    }
    fn host(&self) -> String {
        self.endpoint.host_str().unwrap_or_default().to_owned()
    }
    fn pace(&self) -> Result<(), IngestError> {
        let mut last = self
            .last_request
            .lock()
            .map_err(|_| IngestError::Provider(self.id.clone()))?;
        if let Some(previous) = last.as_ref() {
            let elapsed = previous.elapsed();
            if elapsed < MIN_REQUEST_GAP {
                std::thread::sleep(MIN_REQUEST_GAP - elapsed);
            }
        }
        *last = Some(Instant::now());
        Ok(())
    }
}

impl ReadRpc for HttpRpc {
    fn id(&self) -> &str {
        &self.id
    }
    fn call(&self, method: &str, params: Value) -> Result<Value, IngestError> {
        if !METHODS.contains(&method) {
            return Err(IngestError::Rejected(
                "method is not in the read-only allowlist".into(),
            ));
        }
        let body = json!({"jsonrpc":"2.0", "id":1, "method":method, "params":params});
        // A failed chunk never advances its cursor. Requests are paced and retries stay bounded.
        for attempt in 0..MAX_RPC_ATTEMPTS {
            self.pace()?;
            let response = self.client.post(self.endpoint.clone()).json(&body).send();
            let mut delay = retry_delay(None, None, attempt);
            if let Ok(response) = response {
                let status = response.status();
                let retry_after = response
                    .headers()
                    .get(RETRY_AFTER)
                    .and_then(|value| value.to_str().ok())
                    .map(str::to_owned);
                if status.is_success() {
                    let mut bytes = Vec::new();
                    if response
                        .take(MAX_RESPONSE + 1)
                        .read_to_end(&mut bytes)
                        .is_ok()
                        && bytes.len() as u64 <= MAX_RESPONSE
                    {
                        if let Ok(value) = serde_json::from_slice::<Value>(&bytes) {
                            if value.get("jsonrpc") == Some(&json!("2.0"))
                                && value.get("id") == Some(&json!(1))
                                && value.get("error").is_none()
                            {
                                if let Some(result) = value.get("result") {
                                    return Ok(result.clone());
                                }
                            }
                        }
                    }
                } else if retryable_status(status) {
                    delay = retry_delay(Some(status), retry_after.as_deref(), attempt);
                } else {
                    return Err(IngestError::Provider(self.id.clone()));
                }
            }
            if attempt + 1 < MAX_RPC_ATTEMPTS {
                std::thread::sleep(delay);
            }
        }
        Err(IngestError::Provider(self.id.clone()))
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BlockHeader {
    pub number: u64,
    pub hash: String,
    pub parent_hash: String,
    pub timestamp: u64,
}

pub fn quantity(value: &Value) -> Result<u64, IngestError> {
    let value = value
        .as_str()
        .ok_or_else(|| IngestError::Rejected("RPC quantity must be hex text".into()))?;
    let digits = value
        .strip_prefix("0x")
        .ok_or_else(|| IngestError::Rejected("RPC quantity prefix".into()))?;
    if digits.is_empty() || digits.len() > 16 || digits.len() > 1 && digits.starts_with('0') {
        return Err(IngestError::Rejected(
            "noncanonical or overflowing RPC quantity".into(),
        ));
    }
    u64::from_str_radix(digits, 16)
        .map_err(|_| IngestError::Rejected("invalid RPC quantity".into()))
}

fn field<'a>(value: &'a Value, key: &str) -> Result<&'a Value, IngestError> {
    value
        .get(key)
        .ok_or_else(|| IngestError::Rejected(format!("RPC missing {key}")))
}
fn hex_field(value: &Value, key: &str, bytes: usize) -> Result<String, IngestError> {
    let result = field(value, key)?
        .as_str()
        .ok_or_else(|| IngestError::Rejected(format!("RPC invalid {key}")))?
        .to_ascii_lowercase();
    if !valid_hex(&result, bytes) || (bytes == 32 && result[2..].bytes().all(|v| v == b'0')) {
        return Err(IngestError::Rejected(format!("RPC invalid {key}")));
    }
    Ok(result)
}
fn parse_header(value: &Value) -> Result<BlockHeader, IngestError> {
    Ok(BlockHeader {
        number: quantity(field(value, "number")?)?,
        hash: hex_field(value, "hash", 32)?,
        parent_hash: hex_field(value, "parentHash", 32)?,
        timestamp: quantity(field(value, "timestamp")?)?,
    })
}

pub fn parse_log(value: &Value, chain_id: u64) -> Result<RpcLog, IngestError> {
    let topics = field(value, "topics")?
        .as_array()
        .ok_or_else(|| IngestError::Rejected("RPC topic array".into()))?;
    if topics.is_empty() || topics.len() > 4 {
        return Err(IngestError::Rejected("RPC topic count".into()));
    }
    let topics = topics
        .iter()
        .map(|v| {
            let topic = v.as_str().unwrap_or_default().to_ascii_lowercase();
            if valid_hex(&topic, 32) {
                Ok(topic)
            } else {
                Err(IngestError::Rejected("RPC invalid topic".into()))
            }
        })
        .collect::<Result<Vec<_>, _>>()?;
    let data = field(value, "data")?
        .as_str()
        .ok_or_else(|| IngestError::Rejected("RPC data encoding".into()))?
        .to_ascii_lowercase();
    discovery::decode_hex(&data).map_err(|e| IngestError::Rejected(e.to_string()))?;
    Ok(RpcLog {
        chain_id,
        address: hex_field(value, "address", 20)?,
        block_number: quantity(field(value, "blockNumber")?)?,
        block_hash: hex_field(value, "blockHash", 32)?,
        transaction_hash: hex_field(value, "transactionHash", 32)?,
        log_index: u32::try_from(quantity(field(value, "logIndex")?)?)
            .map_err(|_| IngestError::Rejected("log index overflow".into()))?,
        topics,
        data,
        removed: field(value, "removed")?
            .as_bool()
            .ok_or_else(|| IngestError::Rejected("removed must be boolean".into()))?,
    })
}

pub fn family(protocol: &str) -> Result<ProtocolFamily, IngestError> {
    match protocol {
        "morpho-blue" => Ok(ProtocolFamily::MorphoBlue),
        "aave-v3" => Ok(ProtocolFamily::AaveV3Pool),
        "aave-v3-configurator" => Ok(ProtocolFamily::AaveV3Configurator),
        _ => Err(IngestError::Rejected("unsupported protocol family".into())),
    }
}

pub struct QuorumRpc {
    chain_id: u64,
    providers: Vec<Box<dyn ReadRpc>>,
}

impl QuorumRpc {
    pub fn new(chain_id: u64, providers: Vec<Box<dyn ReadRpc>>) -> Result<Self, IngestError> {
        if chain_id == 0
            || !(2..=4).contains(&providers.len())
            || providers
                .iter()
                .map(|p| p.id())
                .collect::<BTreeSet<_>>()
                .len()
                != providers.len()
        {
            return Err(IngestError::Rejected(
                "at least two distinct providers and an explicit chain required".into(),
            ));
        }
        for provider in &providers {
            if !crate::valid_identifier(provider.id())
                || quantity(&provider.call("eth_chainId", json!([]))?)? != chain_id
            {
                return Err(IngestError::Disagreement("chain identity".into()));
            }
        }
        Ok(Self {
            chain_id,
            providers,
        })
    }
    pub fn from_scope(scope: &ScanScope) -> Result<Self, IngestError> {
        let mut providers: Vec<Box<dyn ReadRpc>> = Vec::new();
        let mut hosts = BTreeSet::new();
        for spec in &scope.providers {
            let rpc = HttpRpc::from_env(spec)?;
            if !hosts.insert(rpc.host()) {
                return Err(IngestError::Rejected("RPC endpoints must use distinct hosts; upstream independence still requires review".into()));
            }
            providers.push(Box::new(rpc));
        }
        Self::new(scope.chain_id, providers)
    }
    pub fn provider_ids(&self) -> Vec<String> {
        self.providers.iter().map(|p| p.id().to_owned()).collect()
    }

    pub fn block(&self, height: u64) -> Result<BlockHeader, IngestError> {
        let mut accepted: Option<BlockHeader> = None;
        for provider in &self.providers {
            let header = parse_header(&provider.call(
                "eth_getBlockByNumber",
                json!([format!("0x{height:x}"), false]),
            )?)?;
            if header.number != height || accepted.as_ref().is_some_and(|prev| prev != &header) {
                return Err(IngestError::Disagreement(format!("block {height}")));
            }
            accepted = Some(header);
        }
        accepted.ok_or_else(|| IngestError::Rejected("empty quorum".into()))
    }

    pub fn common_finalized(&self) -> Result<BlockHeader, IngestError> {
        let mut min = u64::MAX;
        for provider in &self.providers {
            let header =
                parse_header(&provider.call("eth_getBlockByNumber", json!(["finalized", false]))?)?;
            min = min.min(header.number);
        }
        self.block(min)
    }

    pub fn logs(&self, scope: &ScanScope, from: u64, to: u64) -> Result<Vec<RpcLog>, IngestError> {
        if self.chain_id != scope.chain_id
            || from > to
            || from < scope.from_block
            || to > scope.to_block
        {
            return Err(IngestError::Rejected(
                "log request outside configured scope".into(),
            ));
        }
        let query = json!([{"address":scope.contract, "fromBlock":format!("0x{from:x}"),
            "toBlock":format!("0x{to:x}"), "topics":[scope.event_topics]}]);
        let mut accepted: Option<Vec<RpcLog>> = None;
        for provider in &self.providers {
            let response = provider.call("eth_getLogs", query.clone())?;
            let list = response
                .as_array()
                .ok_or_else(|| IngestError::Rejected("RPC logs is not an array".into()))?;
            if list.len() > 100_000 {
                return Err(IngestError::Rejected(
                    "RPC log response exceeds bounded chunk".into(),
                ));
            }
            let mut logs = list
                .iter()
                .map(|item| parse_log(item, scope.chain_id))
                .collect::<Result<Vec<_>, _>>()?;
            logs.sort_by_key(|log| (log.block_number, log.log_index));
            let mut keys = BTreeSet::new();
            for log in &logs {
                if log.address != scope.contract
                    || log.removed
                    || log.block_number < from
                    || log.block_number > to
                    || !scope.event_topics.contains(&log.topics[0])
                    || !keys.insert((log.block_number, log.log_index))
                {
                    return Err(IngestError::Rejected(
                        "out-of-scope, removed, or duplicate RPC log".into(),
                    ));
                }
            }
            if accepted.as_ref().is_some_and(|value| value != &logs) {
                return Err(IngestError::Disagreement(format!("log set {from}..{to}")));
            }
            accepted = Some(logs);
        }
        accepted.ok_or_else(|| IngestError::Rejected("empty quorum".into()))
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScanReport {
    pub scope_id: String,
    pub chain_id: u64,
    pub from_block: u64,
    pub to_block: u64,
    pub finalized_anchor: BlockHeader,
    pub new_events: u64,
    pub new_chunks: u64,
    pub resumed_after: Option<u64>,
    pub complete: bool,
    pub provider_agreement_is_not_source_authentication: bool,
}

fn quarantine_chain(journal: &mut Journal, chain_id: u64, reason: &str) -> Result<(), IngestError> {
    let from_block = journal
        .config()
        .scopes
        .iter()
        .filter(|scope| scope.chain_id == chain_id)
        .map(|scope| scope.from_block)
        .min()
        .ok_or_else(|| IngestError::Rejected("chain not owned by this run".into()))?;
    journal.append(Record::Invalidated {
        chain_id,
        from_block,
        reason: reason.into(),
    })?;
    Ok(())
}

fn revalidate_chain(quorum: &QuorumRpc, journal: &mut Journal) -> Result<(), IngestError> {
    let hashes = crate::journal::known_block_hashes(journal.records())?;
    for ((chain, height), hash) in hashes {
        if chain == quorum.chain_id && quorum.block(height)?.hash != hash {
            quarantine_chain(
                journal,
                chain,
                "persisted chain identity changed; all same-chain scopes quarantined",
            )?;
            return Err(IngestError::Disagreement(
                "persisted canonical checkpoint changed across scopes".into(),
            ));
        }
    }
    Ok(())
}

/// One finite scan. Completion is durable only after all decoded events are synced.
pub fn scan_scope(
    scope: &ScanScope,
    quorum: &QuorumRpc,
    journal: &mut Journal,
    observed_at: u64,
) -> Result<ScanReport, IngestError> {
    scope
        .validate()
        .map_err(|e| IngestError::Rejected(e.to_string()))?;
    if !journal.config().scopes.contains(scope)
        || journal.owner().data_class == crate::config::DataClass::Synthetic
        || quorum.chain_id != scope.chain_id
        || !scope
            .providers
            .iter()
            .map(|p| &p.id)
            .eq(quorum.provider_ids().iter())
    {
        return Err(IngestError::Rejected(
            "scope, providers or data class differ from the journal manifest".into(),
        ));
    }
    let protocol = family(&scope.protocol)?;
    let supported = discovery::event_topics(protocol);
    if scope
        .event_topics
        .iter()
        .any(|topic| !supported.contains(topic))
    {
        return Err(IngestError::Rejected(
            "topic has no registered decoder".into(),
        ));
    }
    if journal
        .summary()
        .invalidated_from
        .contains_key(&scope.chain_id)
    {
        return Err(IngestError::Rejected(
            "invalidated run requires a new evidence directory".into(),
        ));
    }
    let finalized = quorum.common_finalized()?;
    if scope.to_block > finalized.number || observed_at < finalized.timestamp {
        return Err(IngestError::Rejected(
            "range is not finalized or observation clock predates chain anchor".into(),
        ));
    }
    revalidate_chain(quorum, journal)?;
    let mut checkpoints = journal
        .records()
        .iter()
        .filter_map(|entry| match &entry.record {
            Record::ChunkCompleted {
                scope_id,
                chain_id,
                from_block,
                to_block,
                end_block_hash,
                ..
            } if scope_id == &scope.id && *chain_id == scope.chain_id => {
                Some((*from_block, *to_block, end_block_hash.clone()))
            }
            _ => None,
        })
        .collect::<Vec<_>>();
    checkpoints.sort_by_key(|item| item.0);
    let mut next = scope.from_block;
    let mut resumed_after = None;
    let mut previous_end_hash = None;
    for (from, to, end_hash) in checkpoints {
        if from != next || to < from || to > scope.to_block {
            return Err(IngestError::Rejected(
                "non-contiguous durable cursor".into(),
            ));
        }
        let header = quorum.block(to)?;
        if header.hash != end_hash {
            quarantine_chain(
                journal,
                scope.chain_id,
                "finalized checkpoint changed; all same-chain scopes quarantined",
            )?;
            return Err(IngestError::Disagreement(
                "persisted canonical checkpoint changed".into(),
            ));
        }
        resumed_after = Some(to);
        previous_end_hash = Some(end_hash);
        next = to
            .checked_add(1)
            .ok_or_else(|| IngestError::Rejected("cursor overflow".into()))?;
    }
    let mut report = ScanReport {
        scope_id: scope.id.clone(),
        chain_id: scope.chain_id,
        from_block: scope.from_block,
        to_block: scope.to_block,
        finalized_anchor: finalized,
        new_events: 0,
        new_chunks: 0,
        resumed_after,
        complete: false,
        provider_agreement_is_not_source_authentication: true,
    };
    while next <= scope.to_block {
        let end = next
            .saturating_add(scope.chunk_blocks - 1)
            .min(scope.to_block);
        let first = quorum.block(next)?;
        if previous_end_hash
            .as_ref()
            .is_some_and(|hash| hash != &first.parent_hash)
        {
            quarantine_chain(
                journal,
                scope.chain_id,
                "chunk ancestry changed; all same-chain scopes quarantined",
            )?;
            return Err(IngestError::Disagreement("chunk ancestry".into()));
        }
        let last = if next == end {
            first.clone()
        } else {
            quorum.block(end)?
        };
        let logs = quorum.logs(scope, next, end)?;
        let decoder_scope = ContractScope {
            chain_id: scope.chain_id,
            address: scope.contract.clone(),
            family: protocol,
            from_block: next,
            to_block: end,
        };
        let mut headers = BTreeMap::from([(next, first.clone()), (end, last.clone())]);
        let mut records = Vec::new();
        for log in &logs {
            let header = if let Some(value) = headers.get(&log.block_number) {
                value.clone()
            } else {
                let header = quorum.block(log.block_number)?;
                headers.insert(log.block_number, header.clone());
                header
            };
            if header.hash != log.block_hash || header.timestamp > observed_at {
                return Err(IngestError::Disagreement("log block hash/time".into()));
            }
            let decoded = discovery::decode_log(&decoder_scope, log)
                .map_err(|e| IngestError::Rejected(e.to_string()))?;
            records.push(Record::Observed {
                scope_id: scope.id.clone(),
                log: log.clone(),
                decoded: Box::new(decoded),
                block_timestamp: header.timestamp,
                observed_at,
                providers: quorum.provider_ids(),
            });
        }
        if quorum.block(next)? != first || quorum.block(end)? != last {
            return Err(IngestError::Disagreement(
                "block changed while scanning".into(),
            ));
        }
        for record in records {
            report.new_events += u64::from(journal.append(record)?);
        }
        let encoded = serde_json::to_vec(&logs)
            .map_err(|_| IngestError::Rejected("log serialization".into()))?;
        journal.append(Record::ChunkCompleted {
            scope_id: scope.id.clone(),
            chain_id: scope.chain_id,
            from_block: next,
            to_block: end,
            start_block_hash: first.hash,
            start_parent_hash: first.parent_hash,
            end_block_hash: last.hash.clone(),
            observed_at,
            providers: quorum.provider_ids(),
            event_count: logs.len() as u64,
            logs_sha256: crate::digest(&encoded),
        })?;
        report.new_chunks += 1;
        previous_end_hash = Some(last.hash);
        next = end
            .checked_add(1)
            .ok_or_else(|| IngestError::Rejected("cursor overflow".into()))?;
    }
    revalidate_chain(quorum, journal)?;
    if quorum.block(report.finalized_anchor.number)? != report.finalized_anchor {
        quarantine_chain(
            journal,
            scope.chain_id,
            "finalized anchor changed during scan; all same-chain scopes quarantined",
        )?;
        return Err(IngestError::Disagreement("finalized anchor changed".into()));
    }
    journal.append(Record::ScopeCompleted {
        scope_id: scope.id.clone(),
        chain_id: scope.chain_id,
        from_block: scope.from_block,
        to_block: scope.to_block,
        finalized_anchor_number: report.finalized_anchor.number,
        finalized_anchor_hash: report.finalized_anchor.hash.clone(),
        observed_at,
        providers: quorum.provider_ids(),
    })?;
    report.complete = true;
    Ok(report)
}

pub fn validate_runtime(config: &MinerConfig) -> Result<(), IngestError> {
    config
        .validate()
        .map_err(|e| IngestError::Rejected(e.to_string()))?;
    if config.data_class == crate::config::DataClass::Synthetic {
        return Err(IngestError::Rejected(
            "synthetic runs cannot call live RPC".into(),
        ));
    }
    Ok(())
}
