//! Preparatory lifecycle controls. This module cannot authorize, sign, or send a transaction.
//!
//! Evidence references and canonical snapshots are supplied by a caller; they are not signatures
//! or on-chain proofs. Hash/scope/time validation proves internal consistency, not source honesty.

use serde::{Deserialize, Serialize};
use sha2::{Digest as ShaDigest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

pub const MAX_OWN_GAS_CENTAVOS: u64 = 200_000;
pub const MAX_TOP_UP_CENTAVOS: u64 = 50_000;
pub const NO_CAPTURE_STOP_CENTAVOS: u64 = 100_000;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ControlError {
    InvalidInput(&'static str),
    WrongScope,
    MissingCanonicalBlock,
    UnfinalizedBlock,
    ReorganizedBlock,
    ExpiredEvidence,
    FutureEvidence,
    ClockRegression,
    WrongGate,
    GateRejected(&'static str),
    WrongState,
    OperationalBridgeDisabled,
    ReplayMismatch,
    ArithmeticOverflow,
    DuplicateReceipt,
    BudgetHalted,
    BudgetLimit,
}

impl fmt::Display for ControlError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{self:?}")
    }
}
impl std::error::Error for ControlError {}

type Result<T> = std::result::Result<T, ControlError>;

/// A nonzero 256-bit artifact/code/block digest. Serialized as lowercase hexadecimal.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[serde(try_from = "String", into = "String")]
pub struct EvidenceHash([u8; 32]);

impl EvidenceHash {
    pub fn new(bytes: [u8; 32]) -> Result<Self> {
        if bytes == [0; 32] {
            return Err(ControlError::InvalidInput("zero digest"));
        }
        Ok(Self(bytes))
    }
    pub fn from_hex(value: &str) -> Result<Self> {
        let value = value.strip_prefix("0x").unwrap_or(value);
        if value.len() != 64 || !value.is_ascii() {
            return Err(ControlError::InvalidInput(
                "digest must contain 64 hex digits",
            ));
        }
        let mut bytes = [0_u8; 32];
        for (i, byte) in bytes.iter_mut().enumerate() {
            *byte = u8::from_str_radix(&value[i * 2..i * 2 + 2], 16)
                .map_err(|_| ControlError::InvalidInput("invalid hex digest"))?;
        }
        Self::new(bytes)
    }
    pub fn to_hex(self) -> String {
        self.0.iter().map(|b| format!("{b:02x}")).collect()
    }
    pub fn sha256(bytes: &[u8]) -> Self {
        Self(Sha256::digest(bytes).into())
    }
}
impl TryFrom<String> for EvidenceHash {
    type Error = ControlError;
    fn try_from(value: String) -> Result<Self> {
        Self::from_hex(&value)
    }
}
impl From<EvidenceHash> for String {
    fn from(value: EvidenceHash) -> Self {
        value.to_hex()
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct MineIdentity {
    mine_id: String,
    chain_id: u64,
    source_hash: EvidenceHash,
    adapter_hash: EvidenceHash,
}
impl MineIdentity {
    pub fn new(
        mine_id: impl Into<String>,
        chain_id: u64,
        source_hash: EvidenceHash,
        adapter_hash: EvidenceHash,
    ) -> Result<Self> {
        let value = Self {
            mine_id: mine_id.into(),
            chain_id,
            source_hash,
            adapter_hash,
        };
        value.validate()?;
        Ok(value)
    }
    fn validate(&self) -> Result<()> {
        if self.chain_id == 0
            || self.mine_id.is_empty()
            || self.mine_id.len() > 128
            || !self
                .mine_id
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"-_:./".contains(&b))
        {
            return Err(ControlError::InvalidInput(
                "invalid mine identifier or chain",
            ));
        }
        Ok(())
    }
    pub fn mine_id(&self) -> &str {
        &self.mine_id
    }
    pub fn chain_id(&self) -> u64 {
        self.chain_id
    }
    pub fn source_hash(&self) -> EvidenceHash {
        self.source_hash
    }
    pub fn adapter_hash(&self) -> EvidenceHash {
        self.adapter_hash
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct CanonicalBlock {
    number: u64,
    hash: EvidenceHash,
}
impl CanonicalBlock {
    pub fn new(number: u64, hash: EvidenceHash) -> Self {
        Self { number, hash }
    }
    pub fn number(&self) -> u64 {
        self.number
    }
    pub fn hash(&self) -> EvidenceHash {
        self.hash
    }
}

/// Caller-supplied finalized canonical hash map. This type does not query a chain.
/// Serialized transition contexts retain the claimed history, not proof of finality.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "CanonicalViewData", into = "CanonicalViewData")]
pub struct CanonicalView {
    chain_id: u64,
    finalized_head: u64,
    blocks: BTreeMap<u64, EvidenceHash>,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct CanonicalViewData {
    chain_id: u64,
    finalized_head: u64,
    blocks: Vec<CanonicalBlock>,
}

impl TryFrom<CanonicalViewData> for CanonicalView {
    type Error = ControlError;

    fn try_from(value: CanonicalViewData) -> Result<Self> {
        let mut blocks = BTreeMap::new();
        for block in value.blocks {
            if blocks.insert(block.number, block.hash).is_some() {
                return Err(ControlError::InvalidInput(
                    "duplicate block in canonical context",
                ));
            }
        }
        Self::new(value.chain_id, value.finalized_head, blocks)
    }
}

impl From<CanonicalView> for CanonicalViewData {
    fn from(value: CanonicalView) -> Self {
        Self {
            chain_id: value.chain_id,
            finalized_head: value.finalized_head,
            blocks: value
                .blocks
                .into_iter()
                .map(|(number, hash)| CanonicalBlock::new(number, hash))
                .collect(),
        }
    }
}

impl CanonicalView {
    pub fn new(
        chain_id: u64,
        finalized_head: u64,
        blocks: BTreeMap<u64, EvidenceHash>,
    ) -> Result<Self> {
        if chain_id == 0
            || !blocks.contains_key(&finalized_head)
            || blocks.keys().any(|b| *b > finalized_head)
        {
            return Err(ControlError::InvalidInput(
                "invalid finalized canonical snapshot",
            ));
        }
        Ok(Self {
            chain_id,
            finalized_head,
            blocks,
        })
    }
    fn check(&self, chain_id: u64, block: CanonicalBlock) -> Result<()> {
        if self.chain_id != chain_id {
            return Err(ControlError::WrongScope);
        }
        if block.number > self.finalized_head {
            return Err(ControlError::UnfinalizedBlock);
        }
        match self.blocks.get(&block.number) {
            None => Err(ControlError::MissingCanonicalBlock),
            Some(hash) if *hash != block.hash => Err(ControlError::ReorganizedBlock),
            Some(_) => Ok(()),
        }
    }

    /// Save exactly the evidence blocks used by this transition plus its finalized head.
    fn context_for(&self, blocks: impl Iterator<Item = CanonicalBlock>) -> Result<Self> {
        let head_hash = *self
            .blocks
            .get(&self.finalized_head)
            .ok_or(ControlError::MissingCanonicalBlock)?;
        let mut retained = BTreeMap::from([(self.finalized_head, head_hash)]);
        for block in blocks {
            self.check(self.chain_id, block)?;
            retained.insert(block.number, block.hash);
        }
        Self::new(self.chain_id, self.finalized_head, retained)
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct EvidenceScope {
    identity: MineIdentity,
    canonical_block: CanonicalBlock,
    observed_at: u64,
    produced_at: u64,
    expires_at: u64,
}
impl EvidenceScope {
    pub fn new(
        identity: MineIdentity,
        canonical_block: CanonicalBlock,
        observed_at: u64,
        produced_at: u64,
        expires_at: u64,
    ) -> Result<Self> {
        let value = Self {
            identity,
            canonical_block,
            observed_at,
            produced_at,
            expires_at,
        };
        value.validate_shape()?;
        Ok(value)
    }
    fn validate_shape(&self) -> Result<()> {
        self.identity.validate()?;
        if self.observed_at > self.produced_at || self.produced_at >= self.expires_at {
            return Err(ControlError::InvalidInput("evidence time interval"));
        }
        Ok(())
    }
    pub fn validate(
        &self,
        expected: &MineIdentity,
        now: u64,
        canonical: &CanonicalView,
    ) -> Result<()> {
        self.validate_shape()?;
        if &self.identity != expected {
            return Err(ControlError::WrongScope);
        }
        if now < self.produced_at {
            return Err(ControlError::FutureEvidence);
        }
        if now >= self.expires_at {
            return Err(ControlError::ExpiredEvidence);
        }
        canonical.check(self.identity.chain_id, self.canonical_block)
    }
    pub fn identity(&self) -> &MineIdentity {
        &self.identity
    }
    pub fn canonical_block(&self) -> CanonicalBlock {
        self.canonical_block
    }
    pub fn expires_at(&self) -> u64 {
        self.expires_at
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CheckStatus {
    Pass,
    Fail,
    Unknown,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AdapterTestKind {
    Differential,
    Properties,
    Fuzzing,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct AdapterTestEvidence {
    kind: AdapterTestKind,
    scope: EvidenceScope,
    status: CheckStatus,
    artifact_hash: EvidenceHash,
    runner_hash: EvidenceHash,
    cases: u64,
}
impl AdapterTestEvidence {
    pub fn new(
        kind: AdapterTestKind,
        scope: EvidenceScope,
        status: CheckStatus,
        artifact_hash: EvidenceHash,
        runner_hash: EvidenceHash,
        cases: u64,
    ) -> Result<Self> {
        scope.validate_shape()?;
        if cases == 0 {
            return Err(ControlError::InvalidInput("adapter test has no cases"));
        }
        Ok(Self {
            kind,
            scope,
            status,
            artifact_hash,
            runner_hash,
            cases,
        })
    }
}

/// Distinct reports for all three test families, scoped to the same code and block.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct AdapterCertification {
    tests: [AdapterTestEvidence; 3],
}
impl AdapterCertification {
    pub fn new(tests: [AdapterTestEvidence; 3]) -> Result<Self> {
        let value = Self { tests };
        value.validate_shape()?;
        Ok(value)
    }
    fn validate_shape(&self) -> Result<()> {
        let mut kinds = BTreeSet::new();
        let mut reports = BTreeSet::new();
        let first = &self.tests[0].scope;
        for test in &self.tests {
            test.scope.validate_shape()?;
            if test.status != CheckStatus::Pass || test.cases == 0 {
                return Err(ControlError::GateRejected("adapter test not passed"));
            }
            if test.scope.identity != first.identity
                || test.scope.canonical_block != first.canonical_block
            {
                return Err(ControlError::WrongScope);
            }
            if !kinds.insert(test.kind) || !reports.insert(test.artifact_hash) {
                return Err(ControlError::GateRejected(
                    "three distinct test kinds and report hashes required",
                ));
            }
        }
        Ok(())
    }
    fn validate(&self, identity: &MineIdentity, now: u64, canonical: &CanonicalView) -> Result<()> {
        self.validate_shape()?;
        for test in &self.tests {
            test.scope.validate(identity, now, canonical)?;
        }
        Ok(())
    }
    pub fn tests(&self) -> &[AdapterTestEvidence; 3] {
        &self.tests
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum MineState {
    Detected,
    Classified,
    Valued,
    WindTunnel,
    Shadow,
    Proposed,
    Active,
    Watched,
    Retired,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum GateKind {
    Toxicity,
    Adapter,
    Valuation,
    WindTunnel,
    Shadow,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct AdmissionPolicy {
    minimum_expected_net_centavos: i64,
    minimum_priority_score_micros: u64,
    minimum_scenarios: u32,
    minimum_shadow_seconds: u64,
    minimum_shadow_observations: u64,
}
impl Default for AdmissionPolicy {
    fn default() -> Self {
        Self {
            minimum_expected_net_centavos: 0,
            minimum_priority_score_micros: 1,
            minimum_scenarios: 1_000,
            minimum_shadow_seconds: 86_400,
            minimum_shadow_observations: 10,
        }
    }
}
impl AdmissionPolicy {
    pub fn new(
        minimum_expected_net_centavos: i64,
        minimum_priority_score_micros: u64,
        minimum_scenarios: u32,
        minimum_shadow_seconds: u64,
        minimum_shadow_observations: u64,
    ) -> Result<Self> {
        let value = Self {
            minimum_expected_net_centavos,
            minimum_priority_score_micros,
            minimum_scenarios,
            minimum_shadow_seconds,
            minimum_shadow_observations,
        };
        value.validate()?;
        Ok(value)
    }
    fn validate(&self) -> Result<()> {
        if self.minimum_expected_net_centavos < 0
            || self.minimum_priority_score_micros == 0
            || self.minimum_scenarios == 0
            || self.minimum_shadow_seconds == 0
            || self.minimum_shadow_observations == 0
        {
            return Err(ControlError::InvalidInput(
                "admission thresholds must be positive (minimum profit may be zero)",
            ));
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EvidenceBasis {
    Synthetic,
    Historical,
    RealtimeShadow,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum GateReport {
    Toxicity {
        transfer: CheckStatus,
        oracle: CheckStatus,
    },
    Adapter {
        certification: Box<AdapterCertification>,
    },
    Valuation {
        expected_net_centavos: i64,
        priority_score_micros: u64,
        scenarios: u32,
    },
    WindTunnel {
        net_centavos: i64,
        episodes: u64,
    },
    Shadow {
        net_centavos: i64,
        starts_at: u64,
        ends_at: u64,
        observations: u64,
    },
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct GateEvidence {
    scope: EvidenceScope,
    artifact_hash: EvidenceHash,
    basis: EvidenceBasis,
    report: GateReport,
}
impl GateEvidence {
    pub fn new(
        scope: EvidenceScope,
        artifact_hash: EvidenceHash,
        basis: EvidenceBasis,
        report: GateReport,
    ) -> Result<Self> {
        scope.validate_shape()?;
        if let GateReport::Adapter { certification } = &report {
            certification.validate_shape()?;
            if certification.tests.iter().any(|test| {
                test.scope.identity != scope.identity
                    || test.scope.canonical_block != scope.canonical_block
            }) {
                return Err(ControlError::WrongScope);
            }
        }
        if let GateReport::Shadow {
            starts_at, ends_at, ..
        } = &report
        {
            if starts_at >= ends_at || *ends_at > scope.observed_at {
                return Err(ControlError::InvalidInput("shadow observation interval"));
            }
        }
        Ok(Self {
            scope,
            artifact_hash,
            basis,
            report,
        })
    }
    pub fn kind(&self) -> GateKind {
        match self.report {
            GateReport::Toxicity { .. } => GateKind::Toxicity,
            GateReport::Adapter { .. } => GateKind::Adapter,
            GateReport::Valuation { .. } => GateKind::Valuation,
            GateReport::WindTunnel { .. } => GateKind::WindTunnel,
            GateReport::Shadow { .. } => GateKind::Shadow,
        }
    }
    pub fn artifact_hash(&self) -> EvidenceHash {
        self.artifact_hash
    }
    pub fn scope(&self) -> &EvidenceScope {
        &self.scope
    }
    fn validate(
        &self,
        identity: &MineIdentity,
        policy: &AdmissionPolicy,
        now: u64,
        canonical: &CanonicalView,
    ) -> Result<()> {
        self.scope.validate(identity, now, canonical)?;
        if self.basis == EvidenceBasis::Synthetic {
            return Err(ControlError::GateRejected(
                "synthetic evidence cannot advance an operational proposal",
            ));
        }
        match &self.report {
            GateReport::Toxicity { transfer, oracle } => {
                if *transfer != CheckStatus::Pass || *oracle != CheckStatus::Pass {
                    return Err(ControlError::GateRejected("toxicity is unknown or failed"));
                }
            }
            GateReport::Adapter { certification } => {
                certification.validate(identity, now, canonical)?;
                if certification
                    .tests
                    .iter()
                    .any(|test| test.scope.canonical_block != self.scope.canonical_block)
                {
                    return Err(ControlError::WrongScope);
                }
            }
            GateReport::Valuation {
                expected_net_centavos,
                priority_score_micros,
                scenarios,
            } => {
                if *expected_net_centavos <= policy.minimum_expected_net_centavos
                    || *priority_score_micros < policy.minimum_priority_score_micros
                    || *scenarios < policy.minimum_scenarios
                {
                    return Err(ControlError::GateRejected(
                        "valuation is below admission thresholds",
                    ));
                }
            }
            GateReport::WindTunnel {
                net_centavos,
                episodes,
            } => {
                if *net_centavos <= 0 || *episodes == 0 || self.basis != EvidenceBasis::Historical {
                    return Err(ControlError::GateRejected(
                        "positive historical tunnel evidence required",
                    ));
                }
            }
            GateReport::Shadow {
                net_centavos,
                starts_at,
                ends_at,
                observations,
            } => {
                if *starts_at >= *ends_at
                    || *ends_at > self.scope.observed_at
                    || ends_at - starts_at < policy.minimum_shadow_seconds
                    || *observations < policy.minimum_shadow_observations
                    || *net_centavos <= 0
                    || self.basis != EvidenceBasis::RealtimeShadow
                {
                    return Err(ControlError::GateRejected(
                        "positive, sufficiently observed real-time shadow evidence required",
                    ));
                }
            }
        }
        Ok(())
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "action", rename_all = "snake_case")]
pub enum JournalAction {
    Created {
        identity: MineIdentity,
        policy: AdmissionPolicy,
    },
    Advanced {
        evidence: GateEvidence,
        /// Claimed canonical context at the journal entry's injected timestamp.
        canonical_context: CanonicalView,
    },
    Retired {
        reason: String,
    },
    Reactivated {
        identity: MineIdentity,
        reason: String,
    },
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct JournalEntry {
    sequence: u64,
    timestamp: u64,
    from: Option<MineState>,
    to: MineState,
    action: JournalAction,
    previous_hash: Option<EvidenceHash>,
    entry_hash: EvidenceHash,
}
impl JournalEntry {
    pub fn sequence(&self) -> u64 {
        self.sequence
    }
    pub fn timestamp(&self) -> u64 {
        self.timestamp
    }
    pub fn action(&self) -> &JournalAction {
        &self.action
    }
    pub fn entry_hash(&self) -> EvidenceHash {
        self.entry_hash
    }
}

/// No Deserialize implementation: state can only be rebuilt through checked journal replay.
#[derive(Clone, Debug)]
pub struct MineLifecycle {
    identity: MineIdentity,
    policy: AdmissionPolicy,
    state: MineState,
    accepted_evidence: Vec<GateEvidence>,
    journal: Vec<JournalEntry>,
}
impl MineLifecycle {
    pub fn new(identity: MineIdentity, policy: AdmissionPolicy, now: u64) -> Result<Self> {
        identity.validate()?;
        policy.validate()?;
        let mut value = Self {
            identity: identity.clone(),
            policy: policy.clone(),
            state: MineState::Detected,
            accepted_evidence: Vec::new(),
            journal: Vec::new(),
        };
        value.append(
            None,
            MineState::Detected,
            now,
            JournalAction::Created { identity, policy },
        )?;
        Ok(value)
    }
    pub fn state(&self) -> MineState {
        self.state
    }
    pub fn identity(&self) -> &MineIdentity {
        &self.identity
    }
    pub fn journal(&self) -> &[JournalEntry] {
        &self.journal
    }
    fn check_time(&self, now: u64) -> Result<()> {
        if self.journal.last().is_some_and(|e| now < e.timestamp) {
            return Err(ControlError::ClockRegression);
        }
        Ok(())
    }
    fn append(
        &mut self,
        from: Option<MineState>,
        to: MineState,
        timestamp: u64,
        action: JournalAction,
    ) -> Result<()> {
        let sequence =
            u64::try_from(self.journal.len()).map_err(|_| ControlError::ArithmeticOverflow)?;
        let previous_hash = self.journal.last().map(|e| e.entry_hash);
        let payload = serde_json::to_vec(&(sequence, timestamp, from, to, &action, previous_hash))
            .map_err(|_| ControlError::InvalidInput("journal serialization"))?;
        let entry_hash = EvidenceHash::sha256(&payload);
        self.journal.push(JournalEntry {
            sequence,
            timestamp,
            from,
            to,
            action,
            previous_hash,
            entry_hash,
        });
        self.state = to;
        Ok(())
    }
    pub fn validate_current_evidence(&self, now: u64, canonical: &CanonicalView) -> Result<()> {
        self.check_time(now)?;
        for evidence in &self.accepted_evidence {
            evidence.validate(&self.identity, &self.policy, now, canonical)?;
        }
        Ok(())
    }
    pub fn advance(
        &mut self,
        evidence: GateEvidence,
        now: u64,
        canonical: &CanonicalView,
    ) -> Result<MineState> {
        self.check_time(now)?;
        let (gate, target) = match self.state {
            MineState::Detected => (GateKind::Toxicity, MineState::Classified),
            MineState::Classified => (GateKind::Adapter, MineState::Valued),
            MineState::Valued => (GateKind::Valuation, MineState::WindTunnel),
            MineState::WindTunnel => (GateKind::WindTunnel, MineState::Shadow),
            MineState::Shadow => (GateKind::Shadow, MineState::Proposed),
            MineState::Proposed | MineState::Active | MineState::Watched => {
                return Err(ControlError::OperationalBridgeDisabled)
            }
            MineState::Retired => return Err(ControlError::WrongState),
        };
        if evidence.kind() != gate {
            return Err(ControlError::WrongGate);
        }
        self.validate_current_evidence(now, canonical)?;
        evidence.validate(&self.identity, &self.policy, now, canonical)?;
        if let GateReport::Shadow { starts_at, .. } = &evidence.report {
            if self
                .journal
                .last()
                .is_some_and(|entry| *starts_at < entry.timestamp)
            {
                return Err(ControlError::GateRejected(
                    "shadow observations predate shadow admission",
                ));
            }
        }
        if self
            .accepted_evidence
            .iter()
            .any(|old| old.artifact_hash == evidence.artifact_hash)
        {
            return Err(ControlError::GateRejected(
                "distinct gate artifact required",
            ));
        }
        let canonical_context = canonical.context_for(
            self.accepted_evidence
                .iter()
                .chain(std::iter::once(&evidence))
                .map(|accepted| accepted.scope.canonical_block),
        )?;
        self.append(
            Some(self.state),
            target,
            now,
            JournalAction::Advanced {
                evidence: evidence.clone(),
                canonical_context,
            },
        )?;
        self.accepted_evidence.push(evidence);
        Ok(target)
    }
    pub fn retire(&mut self, reason: impl Into<String>, now: u64) -> Result<()> {
        self.check_time(now)?;
        if self.state == MineState::Retired {
            return Err(ControlError::WrongState);
        }
        let reason = checked_reason(reason.into())?;
        self.append(
            Some(self.state),
            MineState::Retired,
            now,
            JournalAction::Retired { reason },
        )?;
        self.accepted_evidence.clear();
        Ok(())
    }
    /// Restart admission from Detected; historical approval/evidence is never inherited.
    pub fn reactivate(
        &mut self,
        identity: MineIdentity,
        reason: impl Into<String>,
        now: u64,
    ) -> Result<()> {
        self.check_time(now)?;
        identity.validate()?;
        if self.state != MineState::Retired {
            return Err(ControlError::WrongState);
        }
        if identity.mine_id != self.identity.mine_id || identity.chain_id != self.identity.chain_id
        {
            return Err(ControlError::WrongScope);
        }
        let reason = checked_reason(reason.into())?;
        self.append(
            Some(self.state),
            MineState::Detected,
            now,
            JournalAction::Reactivated {
                identity: identity.clone(),
                reason,
            },
        )?;
        self.identity = identity;
        self.accepted_evidence.clear();
        Ok(())
    }
    pub fn proposal(&self, now: u64, canonical: &CanonicalView) -> Result<ProposalArtifact> {
        if self.state != MineState::Proposed {
            return Err(ControlError::WrongState);
        }
        self.validate_current_evidence(now, canonical)?;
        Ok(ProposalArtifact {
            schema_version: 1,
            identity: self.identity.clone(),
            prepared_at: now,
            journal_tip: self
                .journal
                .last()
                .ok_or(ControlError::WrongState)?
                .entry_hash,
            evidence_artifacts: self
                .accepted_evidence
                .iter()
                .map(|e| e.artifact_hash)
                .collect(),
            operational_bridge: "disabled".to_owned(),
            evidence_authenticity: "external_verification_required".to_owned(),
            external_approval_required: true,
        })
    }
    /// A reference is metadata only. This build contains no transition to Active.
    pub fn request_activation(&mut self, _approval: &ExternalApprovalReference) -> Result<()> {
        Err(ControlError::OperationalBridgeDisabled)
    }
    /// Rebuild each transition against its recorded historical context and timestamp,
    /// then validate only the still-accepted evidence against the current canonical view.
    /// Historical contexts are integrity-bound caller claims, not authenticated chain proofs.
    pub fn replay(entries: &[JournalEntry], canonical: &CanonicalView, now: u64) -> Result<Self> {
        let first = entries.first().ok_or(ControlError::ReplayMismatch)?;
        let JournalAction::Created { identity, policy } = &first.action else {
            return Err(ControlError::ReplayMismatch);
        };
        let mut value = Self::new(identity.clone(), policy.clone(), first.timestamp)?;
        if value.journal.first() != Some(first) {
            return Err(ControlError::ReplayMismatch);
        }
        for entry in &entries[1..] {
            match &entry.action {
                JournalAction::Created { .. } => return Err(ControlError::ReplayMismatch),
                JournalAction::Advanced {
                    evidence,
                    canonical_context,
                } => {
                    value.advance(evidence.clone(), entry.timestamp, canonical_context)?;
                }
                JournalAction::Retired { reason } => {
                    value.retire(reason.clone(), entry.timestamp)?
                }
                JournalAction::Reactivated { identity, reason } => {
                    value.reactivate(identity.clone(), reason.clone(), entry.timestamp)?
                }
            }
            if value.journal.last() != Some(entry) {
                return Err(ControlError::ReplayMismatch);
            }
        }
        value.validate_current_evidence(now, canonical)?;
        Ok(value)
    }
}
fn checked_reason(value: String) -> Result<String> {
    if value.trim().is_empty() || value.len() > 1024 || value.chars().any(|c| c.is_control()) {
        return Err(ControlError::InvalidInput(
            "a bounded retirement/restart reason is required",
        ));
    }
    Ok(value)
}

/// An opaque external decision locator, never a locally trusted approval boolean.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct ExternalApprovalReference(String);
impl ExternalApprovalReference {
    pub fn new(value: impl Into<String>) -> Result<Self> {
        let value = value.into();
        if value.len() < 16
            || value.len() > 512
            || value.chars().any(|c| c.is_whitespace() || c.is_control())
        {
            return Err(ControlError::InvalidInput(
                "opaque external approval reference",
            ));
        }
        Ok(Self(value))
    }
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct ProposalArtifact {
    schema_version: u32,
    identity: MineIdentity,
    prepared_at: u64,
    journal_tip: EvidenceHash,
    evidence_artifacts: Vec<EvidenceHash>,
    operational_bridge: String,
    evidence_authenticity: String,
    external_approval_required: bool,
}

/// Planning/accounting ceilings only; even a nonzero policy does not authorize spending.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Default)]
pub struct BudgetPolicy {
    total_gas_centavos: u64,
    top_up_centavos: u64,
}
impl BudgetPolicy {
    pub fn new(total_gas_centavos: u64, top_up_centavos: u64) -> Result<Self> {
        if total_gas_centavos > MAX_OWN_GAS_CENTAVOS
            || top_up_centavos > MAX_TOP_UP_CENTAVOS
            || top_up_centavos > total_gas_centavos
            || (total_gas_centavos == 0) != (top_up_centavos == 0)
        {
            return Err(ControlError::BudgetLimit);
        }
        Ok(Self {
            total_gas_centavos,
            top_up_centavos,
        })
    }
    pub fn total_gas_centavos(&self) -> u64 {
        self.total_gas_centavos
    }
    pub fn top_up_centavos(&self) -> u64 {
        self.top_up_centavos
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum BudgetHalt {
    NoBudget,
    TopUpLimitBreached,
    BudgetExhausted,
    NoRealizedCapture,
    ReorganizedAccountingEvidence,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum PaperResultKind {
    Simulated,
    Shadow,
}

/// A reference to externally verified accounting evidence, not a transaction sender.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct RealizedReceipt {
    chain_id: u64,
    transaction_hash: EvidenceHash,
    canonical_block: CanonicalBlock,
    evidence_hash: EvidenceHash,
}
impl RealizedReceipt {
    pub fn new(
        chain_id: u64,
        transaction_hash: EvidenceHash,
        canonical_block: CanonicalBlock,
        evidence_hash: EvidenceHash,
    ) -> Result<Self> {
        if chain_id == 0 {
            return Err(ControlError::InvalidInput("receipt chain"));
        }
        Ok(Self {
            chain_id,
            transaction_hash,
            canonical_block,
            evidence_hash,
        })
    }
    pub fn evidence_hash(&self) -> EvidenceHash {
        self.evidence_hash
    }
    pub fn transaction_hash(&self) -> EvidenceHash {
        self.transaction_hash
    }
    fn key(&self) -> (u64, EvidenceHash) {
        (self.chain_id, self.transaction_hash)
    }
    fn validate(&self, canonical: &CanonicalView) -> Result<()> {
        canonical.check(self.chain_id, self.canonical_block)
    }
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
#[serde(tag = "entry_type", rename_all = "snake_case")]
pub enum AccountingRecord {
    Gas {
        centavos: u64,
        receipt: RealizedReceipt,
    },
    Capture {
        net_centavos: u64,
        receipt: RealizedReceipt,
    },
    TopUp {
        centavos: u64,
        receipt: RealizedReceipt,
    },
    Paper {
        kind: PaperResultKind,
        net_centavos: i64,
    },
}
#[derive(Clone, Debug)]
pub struct BudgetLedger {
    policy: BudgetPolicy,
    gas_consumed_centavos: u64,
    observed_top_ups_centavos: u64,
    realized_capture_count: u64,
    realized_net_centavos: u64,
    simulated_net_centavos: i128,
    shadow_net_centavos: i128,
    halt: Option<BudgetHalt>,
    gas_receipts: BTreeSet<(u64, EvidenceHash)>,
    capture_receipts: BTreeSet<(u64, EvidenceHash)>,
    top_up_receipts: BTreeSet<(u64, EvidenceHash)>,
    accounting_records: Vec<AccountingRecord>,
}
impl Default for BudgetLedger {
    fn default() -> Self {
        Self::new(BudgetPolicy::default())
    }
}
impl BudgetLedger {
    pub fn new(policy: BudgetPolicy) -> Self {
        Self {
            policy,
            gas_consumed_centavos: 0,
            observed_top_ups_centavos: 0,
            realized_capture_count: 0,
            realized_net_centavos: 0,
            simulated_net_centavos: 0,
            shadow_net_centavos: 0,
            halt: if policy.total_gas_centavos == 0 {
                Some(BudgetHalt::NoBudget)
            } else {
                None
            },
            gas_receipts: BTreeSet::new(),
            capture_receipts: BTreeSet::new(),
            top_up_receipts: BTreeSet::new(),
            accounting_records: Vec::new(),
        }
    }
    pub fn accounting_records(&self) -> &[AccountingRecord] {
        &self.accounting_records
    }
    /// Recheck receipts from this chain against refreshed canonical evidence; latch on any loss.
    pub fn audit_canonical(&mut self, canonical: &CanonicalView) -> Result<()> {
        for record in &self.accounting_records {
            let receipt = match record {
                AccountingRecord::Gas { receipt, .. }
                | AccountingRecord::Capture { receipt, .. }
                | AccountingRecord::TopUp { receipt, .. } => receipt,
                AccountingRecord::Paper { .. } => continue,
            };
            if receipt.chain_id == canonical.chain_id {
                if let Err(error) = receipt.validate(canonical) {
                    self.halt = Some(BudgetHalt::ReorganizedAccountingEvidence);
                    return Err(error);
                }
            }
        }
        Ok(())
    }
    pub fn gas_consumed_centavos(&self) -> u64 {
        self.gas_consumed_centavos
    }
    pub fn realized_capture_count(&self) -> u64 {
        self.realized_capture_count
    }
    pub fn realized_net_centavos(&self) -> u64 {
        self.realized_net_centavos
    }
    pub fn simulated_net_centavos(&self) -> i128 {
        self.simulated_net_centavos
    }
    pub fn shadow_net_centavos(&self) -> i128 {
        self.shadow_net_centavos
    }
    pub fn halt_reason(&self) -> Option<BudgetHalt> {
        self.halt
    }
    pub fn spending_enabled(&self) -> bool {
        false
    }
    pub fn request_spend(
        &self,
        _centavos: u64,
        _approval: &ExternalApprovalReference,
    ) -> Result<()> {
        Err(ControlError::OperationalBridgeDisabled)
    }
    /// A numerical precheck, never authorization. Actual funding is absent from this build.
    pub fn assess_top_up(&self, centavos: u64) -> Result<()> {
        if self.halt.is_some() {
            return Err(ControlError::BudgetHalted);
        }
        if centavos == 0
            || centavos > self.policy.top_up_centavos
            || self
                .observed_top_ups_centavos
                .checked_add(centavos)
                .ok_or(ControlError::ArithmeticOverflow)?
                > self.policy.total_gas_centavos
        {
            return Err(ControlError::BudgetLimit);
        }
        Ok(())
    }
    pub fn record_paper_result(&mut self, kind: PaperResultKind, net_centavos: i64) -> Result<()> {
        let target = match kind {
            PaperResultKind::Simulated => &mut self.simulated_net_centavos,
            PaperResultKind::Shadow => &mut self.shadow_net_centavos,
        };
        *target = target
            .checked_add(i128::from(net_centavos))
            .ok_or(ControlError::ArithmeticOverflow)?;
        self.accounting_records
            .push(AccountingRecord::Paper { kind, net_centavos });
        Ok(())
    }
    /// Keep observed overspending visible and latch the breach; never discard it as a failed request.
    pub fn record_realized_gas(
        &mut self,
        centavos: u64,
        receipt: &RealizedReceipt,
        canonical: &CanonicalView,
    ) -> Result<()> {
        receipt.validate(canonical)?;
        if centavos == 0 {
            return Err(ControlError::InvalidInput("zero gas accounting entry"));
        }
        if self.gas_receipts.contains(&receipt.key()) {
            return Err(ControlError::DuplicateReceipt);
        }
        let next = self
            .gas_consumed_centavos
            .checked_add(centavos)
            .ok_or(ControlError::ArithmeticOverflow)?;
        self.gas_receipts.insert(receipt.key());
        self.gas_consumed_centavos = next;
        self.accounting_records.push(AccountingRecord::Gas {
            centavos,
            receipt: receipt.clone(),
        });
        self.refresh_halt();
        Ok(())
    }
    pub fn record_realized_capture(
        &mut self,
        net_centavos: u64,
        receipt: &RealizedReceipt,
        canonical: &CanonicalView,
    ) -> Result<()> {
        receipt.validate(canonical)?;
        if net_centavos == 0 {
            return Err(ControlError::InvalidInput(
                "realized net capture must be positive",
            ));
        }
        if self.capture_receipts.contains(&receipt.key()) {
            return Err(ControlError::DuplicateReceipt);
        }
        let next_net = self
            .realized_net_centavos
            .checked_add(net_centavos)
            .ok_or(ControlError::ArithmeticOverflow)?;
        let next_count = self
            .realized_capture_count
            .checked_add(1)
            .ok_or(ControlError::ArithmeticOverflow)?;
        self.capture_receipts.insert(receipt.key());
        self.realized_net_centavos = next_net;
        self.realized_capture_count = next_count;
        self.accounting_records.push(AccountingRecord::Capture {
            net_centavos,
            receipt: receipt.clone(),
        });
        // A later capture never clears a review-required stop already reached.
        self.refresh_halt();
        Ok(())
    }
    pub fn record_observed_top_up(
        &mut self,
        centavos: u64,
        receipt: &RealizedReceipt,
        canonical: &CanonicalView,
    ) -> Result<()> {
        receipt.validate(canonical)?;
        if centavos == 0 {
            return Err(ControlError::InvalidInput("zero top-up accounting entry"));
        }
        if self.top_up_receipts.contains(&receipt.key()) {
            return Err(ControlError::DuplicateReceipt);
        }
        let next = self
            .observed_top_ups_centavos
            .checked_add(centavos)
            .ok_or(ControlError::ArithmeticOverflow)?;
        self.top_up_receipts.insert(receipt.key());
        self.observed_top_ups_centavos = next;
        self.accounting_records.push(AccountingRecord::TopUp {
            centavos,
            receipt: receipt.clone(),
        });
        if self.halt.is_none()
            && (centavos > self.policy.top_up_centavos || next > self.policy.total_gas_centavos)
        {
            self.halt = Some(BudgetHalt::TopUpLimitBreached);
        }
        Ok(())
    }
    fn refresh_halt(&mut self) {
        if self.halt.is_some() {
            return;
        }
        self.halt = if self.gas_consumed_centavos >= self.policy.total_gas_centavos {
            Some(BudgetHalt::BudgetExhausted)
        } else if self.gas_consumed_centavos >= NO_CAPTURE_STOP_CENTAVOS
            && self.realized_capture_count == 0
        {
            Some(BudgetHalt::NoRealizedCapture)
        } else {
            None
        };
    }
}
