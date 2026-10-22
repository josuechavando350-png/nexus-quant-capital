//! Deliberately separate identifiers and credentials for the Miner process.
use serde::{Deserialize, Serialize};
use std::{collections::BTreeSet, path::Path};
use thiserror::Error;

use crate::{valid_hex, valid_identifier};

pub const NAMESPACE: &str = "nqc_miner_v1";
pub const PRODUCER: &str = "nqc-miner";
pub const MAX_SCAN_BLOCKS: u64 = 20_000;

#[derive(Debug, Error)]
pub enum ConfigError {
    #[error("invalid Miner configuration: {0}")]
    Invalid(String),
    #[error("configuration IO: {0}")]
    Io(#[from] std::io::Error),
    #[error("configuration JSON: {0}")]
    Json(#[from] serde_json::Error),
}

/// Research evidence cannot be reclassified as a realized cash-flow record.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DataClass {
    Synthetic,
    Historical,
    Shadow,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ProviderSpec {
    pub id: String,
    /// Only the name is stored. The credential-bearing URL is never serialized.
    pub url_env: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ScanScope {
    pub id: String,
    pub chain_id: u64,
    pub protocol: String,
    pub contract: String,
    pub event_topics: Vec<String>,
    pub from_block: u64,
    pub to_block: u64,
    pub chunk_blocks: u64,
    pub providers: Vec<ProviderSpec>,
    /// A source reference for the address/ABI; not a semantic certification.
    pub deployment_source: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MinerConfig {
    pub schema_version: u16,
    pub namespace: String,
    pub producer: String,
    pub run_id: String,
    pub data_class: DataClass,
    /// Immutable code commit used by this run. Not inferred from a mutable branch.
    pub code_commit: String,
    pub cargo_lock_sha256: String,
    pub observer_bridge_enabled: bool,
    pub signing_enabled: bool,
    pub gas_budget_mxn_centavos: u64,
    pub scopes: Vec<ScanScope>,
}

fn require(test: bool, message: &str) -> Result<(), ConfigError> {
    if test {
        Ok(())
    } else {
        Err(ConfigError::Invalid(message.into()))
    }
}

pub fn valid_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
}

impl ScanScope {
    pub fn validate(&self) -> Result<(), ConfigError> {
        require(valid_identifier(&self.id), "scope id")?;
        require(self.chain_id != 0, "chain id is zero")?;
        require(
            matches!(
                self.protocol.as_str(),
                "morpho-blue" | "aave-v3" | "aave-v3-configurator"
            ),
            "unsupported protocol decoder",
        )?;
        require(
            valid_hex(&self.contract, 20),
            "contract must be a lowercase address",
        )?;
        require(
            !self.event_topics.is_empty() && self.event_topics.len() <= 8,
            "one to eight explicit event topics required",
        )?;
        let mut topics = BTreeSet::new();
        for topic in &self.event_topics {
            require(
                valid_hex(topic, 32) && topics.insert(topic),
                "invalid or duplicate event topic",
            )?;
        }
        let span = self
            .to_block
            .checked_sub(self.from_block)
            .and_then(|v| v.checked_add(1));
        require(
            span.is_some_and(|v| v <= MAX_SCAN_BLOCKS),
            "scan range must be ordered, inclusive, and at most 20000 blocks",
        )?;
        require(
            (1..=500).contains(&self.chunk_blocks),
            "chunk size must be 1..500",
        )?;
        require(
            (2..=4).contains(&self.providers.len()),
            "two to four agreeing read providers required",
        )?;
        let mut ids = BTreeSet::new();
        let mut envs = BTreeSet::new();
        for provider in &self.providers {
            require(
                valid_identifier(&provider.id) && ids.insert(&provider.id),
                "invalid/duplicate provider id",
            )?;
            require(
                provider.url_env.starts_with("NQC_MINER_RPC_")
                    && provider.url_env.len() > "NQC_MINER_RPC_".len()
                    && provider
                        .url_env
                        .bytes()
                        .all(|c| c.is_ascii_uppercase() || c.is_ascii_digit() || c == b'_')
                    && envs.insert(&provider.url_env),
                "RPC environment names must be distinct and owned by Miner",
            )?;
        }
        require(
            self.deployment_source.starts_with("https://") && self.deployment_source.len() < 1024,
            "HTTPS deployment source required",
        )
    }
}

impl MinerConfig {
    pub fn load(path: &Path) -> Result<Self, ConfigError> {
        let bytes = std::fs::read(path)?;
        require(bytes.len() <= 1_048_576, "configuration too large")?;
        let config: Self = serde_json::from_slice(&bytes)?;
        config.validate()?;
        Ok(config)
    }

    pub fn validate(&self) -> Result<(), ConfigError> {
        require(
            self.schema_version == 1 && self.namespace == NAMESPACE && self.producer == PRODUCER,
            "foreign schema/producer/namespace",
        )?;
        require(valid_identifier(&self.run_id), "run id")?;
        require(
            self.code_commit.len() == 40
                && self
                    .code_commit
                    .bytes()
                    .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
                && self.code_commit.bytes().any(|c| c != b'0'),
            "immutable code commit required",
        )?;
        require(
            valid_sha256(&self.cargo_lock_sha256),
            "Cargo.lock SHA256 required",
        )?;
        require(
            !self.observer_bridge_enabled
                && !self.signing_enabled
                && self.gas_budget_mxn_centavos == 0,
            "this Miner build is isolated and cannot authorize money or the observer bridge",
        )?;
        require(
            !self.scopes.is_empty() && self.scopes.len() <= 32,
            "one to 32 explicit scopes required",
        )?;
        let mut ids = BTreeSet::new();
        for scope in &self.scopes {
            require(ids.insert(&scope.id), "duplicate scope id")?;
            scope.validate()?;
        }
        // Overlapping copies could inflate scope denominators or hide divergent settings.
        for (i, a) in self.scopes.iter().enumerate() {
            for b in self.scopes.iter().skip(i + 1) {
                if a.chain_id == b.chain_id
                    && a.contract == b.contract
                    && a.from_block <= b.to_block
                    && b.from_block <= a.to_block
                    && a.event_topics.iter().any(|t| b.event_topics.contains(t))
                {
                    return Err(ConfigError::Invalid(
                        "overlapping contract/topic scan scopes".into(),
                    ));
                }
            }
        }
        Ok(())
    }

    pub fn integrity_hash(&self) -> Result<String, ConfigError> {
        self.validate()?;
        Ok(crate::digest(&serde_json::to_vec(self)?))
    }
}
