//! Offline REVM sandbox with a closed, supplied state witness.
//!
//! Unknown accounts, slots, bytecode and BLOCKHASH values are errors. The sandbox
//! has no network, wallet, signer, commit-to-chain or transaction submission path.
//! A supplied state root is provenance, not a verified MPT proof. These results
//! never certify mainnet state, a protocol adapter, or an untested token behavior.

use crate::discovery::decode_hex;
use revm::primitives::{
    keccak256, AccountInfo, Address, Bytecode, Bytes, ExecutionResult, SpecId, TxKind, B256, U256,
};
use revm::{Database, Evm};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::{fmt, str::FromStr};

pub type SandboxResult<T> = Result<T, SandboxError>;
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SandboxError(pub String);
impl fmt::Display for SandboxError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.0.fmt(f)
    }
}
impl std::error::Error for SandboxError {}
fn error(value: impl Into<String>) -> SandboxError {
    SandboxError(value.into())
}
fn address(value: &str) -> SandboxResult<Address> {
    Address::from_str(value).map_err(|_| error("invalid witness address"))
}
fn hash(value: &str) -> SandboxResult<B256> {
    B256::from_str(value).map_err(|_| error("invalid witness hash"))
}
fn integer(value: &str) -> SandboxResult<U256> {
    U256::from_str(value).map_err(|_| error("invalid uint256 witness integer"))
}
fn bytes(value: &str) -> SandboxResult<Vec<u8>> {
    decode_hex(value).map_err(|e| error(e.to_string()))
}
fn hex(value: &[u8]) -> String {
    let mut out = String::from("0x");
    for b in value {
        use std::fmt::Write;
        write!(&mut out, "{b:02x}").expect("writing to string");
    }
    out
}
fn digest<T: Serialize>(value: &T) -> SandboxResult<String> {
    let bytes = serde_json::to_vec(value).map_err(|e| error(e.to_string()))?;
    Ok(hex(&Sha256::digest(bytes)))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EvmFork {
    Shanghai,
    Cancun,
}
impl EvmFork {
    fn spec(self) -> SpecId {
        match self {
            Self::Shanghai => SpecId::SHANGHAI,
            Self::Cancun => SpecId::CANCUN,
        }
    }
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SnapshotKind {
    SyntheticFixture,
    HistoricalWitness,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WitnessAccount {
    pub address: String,
    /// Nonexistence must itself be explicitly supplied; an omitted account is unknown.
    pub exists: bool,
    pub balance_wei: String,
    pub nonce: u64,
    pub runtime_code: String,
    pub code_hash: String,
    /// Keys and values are uint256 strings. Every read slot must be present, including zero.
    pub storage: BTreeMap<String, String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PinnedSnapshot {
    pub schema_version: u16,
    pub kind: SnapshotKind,
    pub chain_id: u64,
    pub block_number: u64,
    pub block_hash: String,
    pub state_root: String,
    pub timestamp: u64,
    pub fork: EvmFork,
    pub block_gas_limit: u64,
    pub base_fee_wei: String,
    pub beneficiary: String,
    pub prevrandao: String,
    pub excess_blob_gas: Option<u64>,
    pub accounts: Vec<WitnessAccount>,
    pub ancestor_block_hashes: BTreeMap<u64, String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SandboxCall {
    pub caller: String,
    pub to: String,
    pub calldata: String,
    pub value_wei: String,
    pub gas_limit: u64,
    pub gas_price_wei: String,
    pub nonce: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum VmStatus {
    Success,
    Revert,
    Halt,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct VmLog {
    pub address: String,
    pub topics: Vec<String>,
    pub data: String,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AccountDelta {
    pub address: String,
    pub balance_wei: String,
    pub nonce: u64,
    pub code_hash: String,
    pub created: bool,
    pub selfdestructed: bool,
    pub storage: BTreeMap<String, String>,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SandboxOutcome {
    pub status: VmStatus,
    pub reason: String,
    pub output: String,
    pub gas_used: u64,
    pub logs: Vec<VmLog>,
    pub account_deltas: Vec<AccountDelta>,
    pub snapshot_sha256: String,
    pub call_sha256: String,
    pub snapshot_kind: SnapshotKind,
    /// False even for historical witnesses: this module does not verify MPT proofs.
    pub canonical_state_authenticated: bool,
}

#[derive(Clone)]
struct ClosedState {
    accounts: BTreeMap<Address, Option<AccountInfo>>,
    code: BTreeMap<B256, Bytecode>,
    storage: BTreeMap<(Address, U256), U256>,
    block_hashes: BTreeMap<u64, B256>,
}
impl Database for ClosedState {
    type Error = SandboxError;
    fn basic(&mut self, address: Address) -> SandboxResult<Option<AccountInfo>> {
        self.accounts
            .get(&address)
            .cloned()
            .ok_or_else(|| error(format!("missing account witness {address:#x}")))
    }
    fn code_by_hash(&mut self, code_hash: B256) -> SandboxResult<Bytecode> {
        self.code
            .get(&code_hash)
            .cloned()
            .ok_or_else(|| error(format!("missing bytecode witness {code_hash:#x}")))
    }
    fn storage(&mut self, address: Address, index: U256) -> SandboxResult<U256> {
        self.storage
            .get(&(address, index))
            .copied()
            .ok_or_else(|| error(format!("missing storage witness {address:#x}:{index}")))
    }
    fn block_hash(&mut self, number: u64) -> SandboxResult<B256> {
        self.block_hashes
            .get(&number)
            .copied()
            .ok_or_else(|| error(format!("missing ancestor block hash {number}")))
    }
}
impl PinnedSnapshot {
    pub fn sha256(&self) -> SandboxResult<String> {
        digest(self)
    }
    fn closed_state(&self) -> SandboxResult<ClosedState> {
        if self.schema_version != 1
            || self.chain_id == 0
            || self.block_gas_limit == 0
            || self.block_gas_limit > 100_000_000
            || self.accounts.is_empty()
            || self.accounts.len() > 4096
        {
            return Err(error("invalid or excessive snapshot bounds"));
        }
        if hash(&self.block_hash)? == B256::ZERO || hash(&self.state_root)? == B256::ZERO {
            return Err(error("unpinned block or state root"));
        }
        if self.fork == EvmFork::Cancun && self.excess_blob_gas.is_none() {
            return Err(error("Cancun excess blob gas is missing"));
        }
        if self.fork == EvmFork::Shanghai && self.excess_blob_gas.is_some() {
            return Err(error("Shanghai must not include Cancun blob environment"));
        }
        integer(&self.base_fee_wei)?;
        address(&self.beneficiary)?;
        hash(&self.prevrandao)?;
        let mut state = ClosedState {
            accounts: BTreeMap::new(),
            code: BTreeMap::new(),
            storage: BTreeMap::new(),
            block_hashes: BTreeMap::new(),
        };
        let mut slots = 0usize;
        for account in &self.accounts {
            let a = address(&account.address)?;
            let balance = integer(&account.balance_wei)?;
            let code = bytes(&account.runtime_code)?;
            if code.len() > 24_576 {
                return Err(error("runtime exceeds supported Ethereum code size"));
            }
            let code_hash = hash(&account.code_hash)?;
            if code_hash != keccak256(&code) {
                return Err(error("witness code hash mismatch"));
            }
            if !account.exists
                && (!balance.is_zero()
                    || account.nonce != 0
                    || !code.is_empty()
                    || !account.storage.is_empty())
            {
                return Err(error("nonexistent account contains state"));
            }
            let bytecode = Bytecode::new_raw_checked(Bytes::from(code))
                .map_err(|_| error("malformed bytecode envelope"))?;
            if bytecode.is_eof() || bytecode.is_eip7702() {
                return Err(error(
                    "EOF/delegation bytecode is unsupported for the pinned Shanghai/Cancun model",
                ));
            }
            let info = account
                .exists
                .then(|| AccountInfo::new(balance, account.nonce, code_hash, bytecode.clone()));
            if state.accounts.insert(a, info).is_some() {
                return Err(error("duplicate account witness"));
            }
            state.code.insert(code_hash, bytecode);
            for (slot, value) in &account.storage {
                if state
                    .storage
                    .insert((a, integer(slot)?), integer(value)?)
                    .is_some()
                {
                    return Err(error("duplicate normalized slot witness"));
                }
                slots += 1;
                if slots > 65_536 {
                    return Err(error("excessive storage witness"));
                }
            }
        }
        for (number, value) in &self.ancestor_block_hashes {
            if *number >= self.block_number || self.block_number - *number > 256 {
                return Err(error("ancestor hash outside EVM window"));
            }
            let value = hash(value)?;
            if value == B256::ZERO {
                return Err(error("zero ancestor hash"));
            }
            state.block_hashes.insert(*number, value);
        }
        Ok(state)
    }
}

/// Execute a bounded unsigned transaction in an ephemeral Ethereum REVM environment.
/// State changes are returned as evidence and are never committed anywhere.
pub fn simulate(snapshot: &PinnedSnapshot, call: &SandboxCall) -> SandboxResult<SandboxOutcome> {
    let db = snapshot.closed_state()?;
    if call.gas_limit < 21_000
        || call.gas_limit > 30_000_000
        || call.gas_limit > snapshot.block_gas_limit
    {
        return Err(error("sandbox gas bound violated"));
    }
    let caller = address(&call.caller)?;
    let to = address(&call.to)?;
    let calldata = bytes(&call.calldata)?;
    if calldata.len() > 1_048_576 {
        return Err(error("sandbox calldata bound violated"));
    }
    let value = integer(&call.value_wei)?;
    let gas_price = integer(&call.gas_price_wei)?;
    let basefee = integer(&snapshot.base_fee_wei)?;
    let beneficiary = address(&snapshot.beneficiary)?;
    let prevrandao = hash(&snapshot.prevrandao)?;
    let mut evm = Evm::builder()
        .with_db(db)
        .with_spec_id(snapshot.fork.spec())
        .modify_cfg_env(|cfg| cfg.chain_id = snapshot.chain_id)
        .modify_block_env(|block| {
            block.number = U256::from(snapshot.block_number);
            block.timestamp = U256::from(snapshot.timestamp);
            block.gas_limit = U256::from(snapshot.block_gas_limit);
            block.basefee = basefee;
            block.coinbase = beneficiary;
            block.prevrandao = Some(prevrandao);
            block.difficulty = U256::ZERO;
            block.blob_excess_gas_and_price = None;
            if let Some(excess) = snapshot.excess_blob_gas {
                block.set_blob_excess_gas_and_price(excess, false);
            }
        })
        .modify_tx_env(|tx| {
            tx.caller = caller;
            tx.transact_to = TxKind::Call(to);
            tx.data = Bytes::from(calldata);
            tx.value = value;
            tx.gas_limit = call.gas_limit;
            tx.gas_price = gas_price;
            tx.gas_priority_fee = None;
            tx.nonce = Some(call.nonce);
            tx.chain_id = Some(snapshot.chain_id);
        })
        .build();
    let result = evm
        .transact()
        .map_err(|e| error(format!("closed sandbox execution rejected: {e}")))?;
    let output = result
        .result
        .output()
        .map(|b| b.as_ref())
        .unwrap_or_default();
    if output.len() > 1_048_576 {
        return Err(error("sandbox output bound violated"));
    }
    let (status, reason) = match &result.result {
        ExecutionResult::Success { reason, .. } => (VmStatus::Success, format!("{reason:?}")),
        ExecutionResult::Revert { .. } => (VmStatus::Revert, "revert".into()),
        ExecutionResult::Halt { reason, .. } => (VmStatus::Halt, format!("{reason:?}")),
    };
    let logs = result
        .result
        .logs()
        .iter()
        .map(|log| VmLog {
            address: format!("{:#x}", log.address),
            topics: log
                .data
                .topics()
                .iter()
                .map(|t| format!("{t:#x}"))
                .collect(),
            data: hex(&log.data.data),
        })
        .collect();
    let mut deltas: Vec<_> = result
        .state
        .iter()
        .filter(|(_, account)| account.is_touched())
        .map(|(a, account)| AccountDelta {
            address: format!("{a:#x}"),
            balance_wei: account.info.balance.to_string(),
            nonce: account.info.nonce,
            code_hash: format!("{:#x}", account.info.code_hash),
            created: account.is_created(),
            selfdestructed: account.is_selfdestructed(),
            storage: account
                .storage
                .iter()
                .filter(|(_, slot)| slot.is_changed())
                .map(|(slot, value)| (slot.to_string(), value.present_value.to_string()))
                .collect(),
        })
        .collect();
    deltas.sort_by(|a, b| a.address.cmp(&b.address));
    Ok(SandboxOutcome {
        status,
        reason,
        output: hex(output),
        gas_used: result.result.gas_used(),
        logs,
        account_deltas: deltas,
        snapshot_sha256: snapshot.sha256()?,
        call_sha256: digest(call)?,
        snapshot_kind: snapshot.kind,
        canonical_state_authenticated: false,
    })
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DifferentialResult {
    pub matches: bool,
    pub mismatches: Vec<String>,
    pub snapshot_sha256: String,
    pub call_sha256: String,
    pub establishes_adapter_certification: bool,
}
/// Compare an independent adapter prediction to REVM output for this one supplied case.
/// Gas, output, status, logs and state deltas all matter. Passing is not a fuzz/property gate.
pub fn compare_adapter_output(
    reference: &SandboxOutcome,
    prediction: &SandboxOutcome,
) -> SandboxResult<DifferentialResult> {
    if reference.snapshot_sha256 != prediction.snapshot_sha256
        || reference.call_sha256 != prediction.call_sha256
        || reference.snapshot_kind != prediction.snapshot_kind
    {
        return Err(error(
            "differential inputs do not identify the same state and call",
        ));
    }
    let mut mismatches = Vec::new();
    if reference.status != prediction.status {
        mismatches.push("status".into());
    }
    if reference.output != prediction.output {
        mismatches.push("output".into());
    }
    if reference.gas_used != prediction.gas_used {
        mismatches.push("gas_used".into());
    }
    if reference.logs != prediction.logs {
        mismatches.push("logs".into());
    }
    if reference.account_deltas != prediction.account_deltas {
        mismatches.push("state_delta".into());
    }
    Ok(DifferentialResult {
        matches: mismatches.is_empty(),
        mismatches,
        snapshot_sha256: reference.snapshot_sha256.clone(),
        call_sha256: reference.call_sha256.clone(),
        establishes_adapter_certification: false,
    })
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TransferProbe {
    pub token: String,
    pub sender: String,
    pub receiver: String,
    pub amount: String,
    pub sender_before: String,
    pub sender_after: String,
    pub receiver_before: String,
    pub receiver_after: String,
    pub call: SandboxCall,
    pub outcome: SandboxOutcome,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OracleStressEvidence {
    pub snapshot_sha256: String,
    pub liquidity_evidence_sha256: String,
    pub manipulation_cost_microusd: Option<u64>,
    pub maximum_extractable_microusd: Option<u64>,
    pub all_dependency_paths_evaluated: bool,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ToxicityVerdict {
    Unknown,
    Rejected,
    PassForSuppliedCases,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ToxicityReport {
    pub verdict: ToxicityVerdict,
    pub reasons: Vec<String>,
    pub snapshot_sha256: String,
    pub cases: usize,
    pub globally_safe: bool,
}
/// Conservative assessment of supplied balances and results. Missing oracle evidence is unknown.
/// The caller must independently attest balance provenance; this function only checks consistency.
pub fn assess_toxicity(
    snapshot_sha256: &str,
    probes: &[TransferProbe],
    oracle: Option<&OracleStressEvidence>,
) -> SandboxResult<ToxicityReport> {
    if hash(snapshot_sha256)? == B256::ZERO {
        return Err(error("missing toxicity state digest"));
    }
    let mut report = ToxicityReport {
        verdict: ToxicityVerdict::Unknown,
        reasons: Vec::new(),
        snapshot_sha256: snapshot_sha256.into(),
        cases: probes.len(),
        globally_safe: false,
    };
    if probes.is_empty() {
        report.reasons.push("no transfer cases".into());
        return Ok(report);
    }
    let mut seen = std::collections::BTreeSet::new();
    for probe in probes {
        let token = address(&probe.token)?;
        let sender = address(&probe.sender)?;
        let receiver = address(&probe.receiver)?;
        let amount = integer(&probe.amount)?;
        if token == Address::ZERO || sender == receiver || amount.is_zero() {
            return Err(error("invalid transfer probe"));
        }
        if probe.outcome.snapshot_sha256 != snapshot_sha256 {
            return Err(error("mixed-state toxicity probes"));
        }
        let mut expected_calldata = vec![0xa9, 0x05, 0x9c, 0xbb];
        expected_calldata.extend_from_slice(&[0u8; 12]);
        expected_calldata.extend_from_slice(receiver.as_slice());
        expected_calldata.extend_from_slice(&amount.to_be_bytes::<32>());
        if address(&probe.call.to)? != token
            || address(&probe.call.caller)? != sender
            || bytes(&probe.call.calldata)? != expected_calldata
            || !integer(&probe.call.value_wei)?.is_zero()
            || digest(&probe.call)? != probe.outcome.call_sha256
        {
            return Err(error(
                "transfer result is not bound to its token, parties, amount and call",
            ));
        }
        if !seen.insert(probe.outcome.call_sha256.clone()) {
            return Err(error("duplicate transfer case"));
        }
        let a0 = integer(&probe.sender_before)?;
        let a1 = integer(&probe.sender_after)?;
        let b0 = integer(&probe.receiver_before)?;
        let b1 = integer(&probe.receiver_after)?;
        let returned = bytes(&probe.outcome.output)?;
        let return_ok = returned.is_empty()
            || (returned.len() == 32
                && returned[..31].iter().all(|b| *b == 0)
                && returned[31] == 1);
        if probe.outcome.status != VmStatus::Success || !return_ok {
            report.verdict = ToxicityVerdict::Rejected;
            report
                .reasons
                .push("transfer reverted, halted, or returned false/noncanonical data".into());
        } else if a0.checked_sub(a1) != Some(amount) || b1.checked_sub(b0) != Some(amount) {
            report.verdict = ToxicityVerdict::Rejected;
            report
                .reasons
                .push("transfer balance deltas reveal fees, rebases, or restrictions".into());
        }
    }
    if report.verdict == ToxicityVerdict::Rejected {
        return Ok(report);
    }
    let Some(oracle) = oracle else {
        report
            .reasons
            .push("oracle manipulation cost is unknown".into());
        return Ok(report);
    };
    if oracle.snapshot_sha256 != snapshot_sha256 {
        return Err(error("oracle and transfer state differ"));
    }
    if hash(&oracle.liquidity_evidence_sha256)? == B256::ZERO {
        return Err(error("missing oracle liquidity evidence"));
    }
    match (
        oracle.manipulation_cost_microusd,
        oracle.maximum_extractable_microusd,
        oracle.all_dependency_paths_evaluated,
    ) {
        (Some(cost), Some(extractable), true) if cost > extractable => {
            report.verdict = ToxicityVerdict::PassForSuppliedCases;
            report.reasons.push("supplied transfer cases and oracle stress bounds pass; scope is finite and unverified externally".into());
        }
        (Some(_), Some(_), true) => {
            report.verdict = ToxicityVerdict::Rejected;
            report
                .reasons
                .push("oracle manipulation cost does not exceed extractable value".into());
        }
        _ => report
            .reasons
            .push("oracle dependency paths or economic bounds are incomplete".into()),
    }
    Ok(report)
}
