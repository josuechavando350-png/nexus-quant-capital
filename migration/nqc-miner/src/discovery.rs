//! Deterministic discovery primitives. These produce candidates, never trading authority.
//!
//! Every log is checked against an explicit contract/chain/block scope. ABI recognition,
//! bytecode similarity and graph associations are not protocol or identity certificates.

use alloy_primitives::{keccak256, Address, B256, U256};
use alloy_sol_types::{sol, SolEvent, SolValue};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use std::str::FromStr;

pub type DiscoveryResult<T> = Result<T, DiscoveryError>;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DiscoveryError(pub String);
impl fmt::Display for DiscoveryError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.0.fmt(f)
    }
}
impl std::error::Error for DiscoveryError {}
fn error(message: impl Into<String>) -> DiscoveryError {
    DiscoveryError(message.into())
}

pub mod abi {
    use super::*;
    sol! {
        struct MarketParams {
            address loanToken;
            address collateralToken;
            address oracle;
            address irm;
            uint256 lltv;
        }
        event CreateMarket(bytes32 indexed id, MarketParams marketParams);
        event Liquidate(bytes32 indexed id, address indexed caller, address indexed borrower,
            uint256 repaidAssets, uint256 repaidShares, uint256 seizedAssets,
            uint256 badDebtAssets, uint256 badDebtShares);
        event ReserveInitialized(address indexed asset, address indexed aToken,
            address stableDebtToken, address variableDebtToken, address interestRateStrategyAddress);
        event LiquidationCall(address indexed collateralAsset, address indexed debtAsset,
            address indexed user, uint256 debtToCover, uint256 liquidatedCollateralAmount,
            address liquidator, bool receiveAToken);
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProtocolFamily {
    MorphoBlue,
    AaveV3Pool,
    AaveV3Configurator,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ContractScope {
    pub chain_id: u64,
    pub address: String,
    pub family: ProtocolFamily,
    pub from_block: u64,
    pub to_block: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RpcLog {
    pub chain_id: u64,
    pub address: String,
    pub block_number: u64,
    pub block_hash: String,
    pub transaction_hash: String,
    pub log_index: u32,
    pub topics: Vec<String>,
    pub data: String,
    pub removed: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LogIdentity {
    pub chain_id: u64,
    pub contract: String,
    pub block_number: u64,
    pub block_hash: String,
    pub transaction_hash: String,
    pub log_index: u32,
}
impl LogIdentity {
    pub fn event_id(&self) -> String {
        format!(
            "{}:{}:{}:{}",
            self.chain_id, self.block_hash, self.transaction_hash, self.log_index
        )
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BirthSignal {
    pub identity: LogIdentity,
    pub family: ProtocolFamily,
    pub market_id: String,
    pub loan_token: Option<String>,
    pub collateral_token: Option<String>,
    pub oracle: Option<String>,
    pub interest_rate_model: Option<String>,
    pub lltv_wad: Option<String>,
    pub related_tokens: Vec<String>,
    /// Always false: log decoding cannot certify bytecode, proxies, arithmetic or safety.
    pub protocol_certified: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LiquidationSignal {
    pub identity: LogIdentity,
    pub family: ProtocolFamily,
    pub market_id: String,
    pub liquidator: String,
    pub borrower: String,
    pub debt_token: Option<String>,
    pub collateral_token: Option<String>,
    /// Decimal integer strings, in native token base units, never dollars.
    pub repaid_assets: String,
    pub seized_assets: String,
    pub bad_debt_assets: Option<String>,
    pub receive_a_token: Option<bool>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "kind", content = "payload", rename_all = "snake_case")]
pub enum DecodedEvent {
    Birth(BirthSignal),
    Liquidation(LiquidationSignal),
}

pub fn event_topics(family: ProtocolFamily) -> Vec<String> {
    match family {
        ProtocolFamily::MorphoBlue => vec![
            format!("{:#x}", abi::CreateMarket::SIGNATURE_HASH),
            format!("{:#x}", abi::Liquidate::SIGNATURE_HASH),
        ],
        ProtocolFamily::AaveV3Pool => vec![format!("{:#x}", abi::LiquidationCall::SIGNATURE_HASH)],
        ProtocolFamily::AaveV3Configurator => {
            vec![format!("{:#x}", abi::ReserveInitialized::SIGNATURE_HASH)]
        }
    }
}

fn hash(value: &str) -> DiscoveryResult<B256> {
    let parsed = B256::from_str(value).map_err(|_| error("invalid 32-byte hash"))?;
    if parsed == B256::ZERO {
        return Err(error("zero hash is not pinned evidence"));
    }
    Ok(parsed)
}
fn address(value: &str) -> DiscoveryResult<Address> {
    Address::from_str(value).map_err(|_| error("invalid address"))
}
pub fn decode_hex(value: &str) -> DiscoveryResult<Vec<u8>> {
    let value = value
        .strip_prefix("0x")
        .ok_or_else(|| error("hex requires 0x prefix"))?;
    if value.len() % 2 != 0 || value.len() > 2_097_152 {
        return Err(error("invalid hex length"));
    }
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let digit = |b: u8| {
                (b as char)
                    .to_digit(16)
                    .ok_or_else(|| error("invalid hex digit"))
            };
            Ok((digit(pair[0])? * 16 + digit(pair[1])?) as u8)
        })
        .collect()
}

fn canonical_event<E: SolEvent>(event: E, topics: &[B256], data: &[u8]) -> DiscoveryResult<E> {
    // Codec validation alone accepts some padded addresses/bools. Require exact round-trip.
    let encoded = event.encode_log_data();
    if encoded.topics() != topics || encoded.data.as_ref() != data {
        return Err(error("noncanonical ABI scalar encoding"));
    }
    Ok(event)
}

/// Decode only the four supported ABI events, rejecting removals and ambiguous encodings.
/// A matched scope authenticates neither the RPC provider nor a deployment's current code.
pub fn decode_log(scope: &ContractScope, log: &RpcLog) -> DiscoveryResult<DecodedEvent> {
    if scope.chain_id == 0 || scope.from_block > scope.to_block {
        return Err(error("invalid scope"));
    }
    let contract = address(&scope.address)?;
    if contract == Address::ZERO
        || log.chain_id != scope.chain_id
        || address(&log.address)? != contract
        || !(scope.from_block..=scope.to_block).contains(&log.block_number)
    {
        return Err(error(
            "log is outside the declared contract/chain/block scope",
        ));
    }
    if log.removed {
        return Err(error("removed log requires rollback, never discovery"));
    }
    let block_hash = hash(&log.block_hash)?;
    let transaction_hash = hash(&log.transaction_hash)?;
    if log.topics.is_empty() || log.topics.len() > 4 {
        return Err(error("invalid topic count"));
    }
    let topics: Vec<B256> = log
        .topics
        .iter()
        .map(|s| B256::from_str(s).map_err(|_| error("invalid topic")))
        .collect::<DiscoveryResult<_>>()?;
    let data = decode_hex(&log.data)?;
    let id = LogIdentity {
        chain_id: log.chain_id,
        contract: format!("{contract:#x}"),
        block_number: log.block_number,
        block_hash: format!("{block_hash:#x}"),
        transaction_hash: format!("{transaction_hash:#x}"),
        log_index: log.log_index,
    };
    let shape = |n: usize, bytes: usize| -> DiscoveryResult<()> {
        if topics.len() != n || data.len() != bytes {
            Err(error("noncanonical ABI topic/data length"))
        } else {
            Ok(())
        }
    };
    if scope.family == ProtocolFamily::MorphoBlue && topics[0] == abi::CreateMarket::SIGNATURE_HASH
    {
        shape(2, 160)?;
        let event = canonical_event(
            abi::CreateMarket::decode_raw_log_validate(topics.iter().copied(), &data)
                .map_err(|_| error("malformed CreateMarket"))?,
            &topics,
            &data,
        )?;
        if keccak256(event.marketParams.abi_encode()) != event.id {
            return Err(error("Morpho market id does not hash to its parameters"));
        }
        return Ok(DecodedEvent::Birth(BirthSignal {
            identity: id,
            family: scope.family,
            market_id: format!("{:#x}", event.id),
            loan_token: Some(format!("{:#x}", event.marketParams.loanToken)),
            collateral_token: Some(format!("{:#x}", event.marketParams.collateralToken)),
            oracle: Some(format!("{:#x}", event.marketParams.oracle)),
            interest_rate_model: Some(format!("{:#x}", event.marketParams.irm)),
            lltv_wad: Some(event.marketParams.lltv.to_string()),
            related_tokens: vec![],
            protocol_certified: false,
        }));
    }
    if scope.family == ProtocolFamily::MorphoBlue && topics[0] == abi::Liquidate::SIGNATURE_HASH {
        shape(4, 160)?;
        let event = canonical_event(
            abi::Liquidate::decode_raw_log_validate(topics.iter().copied(), &data)
                .map_err(|_| error("malformed Liquidate"))?,
            &topics,
            &data,
        )?;
        return Ok(DecodedEvent::Liquidation(LiquidationSignal {
            identity: id,
            family: scope.family,
            market_id: format!("{:#x}", event.id),
            liquidator: format!("{:#x}", event.caller),
            borrower: format!("{:#x}", event.borrower),
            debt_token: None,
            collateral_token: None,
            repaid_assets: event.repaidAssets.to_string(),
            seized_assets: event.seizedAssets.to_string(),
            bad_debt_assets: Some(event.badDebtAssets.to_string()),
            receive_a_token: None,
        }));
    }
    if scope.family == ProtocolFamily::AaveV3Pool
        && topics[0] == abi::LiquidationCall::SIGNATURE_HASH
    {
        shape(4, 128)?;
        let event = canonical_event(
            abi::LiquidationCall::decode_raw_log_validate(topics.iter().copied(), &data)
                .map_err(|_| error("malformed LiquidationCall"))?,
            &topics,
            &data,
        )?;
        return Ok(DecodedEvent::Liquidation(LiquidationSignal {
            identity: id,
            family: scope.family,
            // Pool plus debt/collateral pair: one reserve address cannot identify an Aave liquidation market.
            market_id: format!(
                "{contract:#x}:{:#x}:{:#x}",
                event.collateralAsset, event.debtAsset
            ),
            liquidator: format!("{:#x}", event.liquidator),
            borrower: format!("{:#x}", event.user),
            debt_token: Some(format!("{:#x}", event.debtAsset)),
            collateral_token: Some(format!("{:#x}", event.collateralAsset)),
            repaid_assets: event.debtToCover.to_string(),
            seized_assets: event.liquidatedCollateralAmount.to_string(),
            bad_debt_assets: None,
            receive_a_token: Some(event.receiveAToken),
        }));
    }
    if scope.family == ProtocolFamily::AaveV3Configurator
        && topics[0] == abi::ReserveInitialized::SIGNATURE_HASH
    {
        shape(3, 96)?;
        let event = canonical_event(
            abi::ReserveInitialized::decode_raw_log_validate(topics.iter().copied(), &data)
                .map_err(|_| error("malformed ReserveInitialized"))?,
            &topics,
            &data,
        )?;
        return Ok(DecodedEvent::Birth(BirthSignal {
            identity: id,
            family: scope.family,
            market_id: format!("{contract:#x}:{:#x}", event.asset),
            loan_token: Some(format!("{:#x}", event.asset)),
            collateral_token: None,
            oracle: None,
            interest_rate_model: Some(format!("{:#x}", event.interestRateStrategyAddress)),
            lltv_wad: None,
            related_tokens: vec![
                format!("{:#x}", event.aToken),
                format!("{:#x}", event.stableDebtToken),
                format!("{:#x}", event.variableDebtToken),
            ],
            protocol_certified: false,
        }));
    }
    Err(error("unsupported event for declared protocol family"))
}

/// Evidence required to relate an ABI candidate to inspected runtime/proxy code at one block.
/// This checks supplied bindings only; trust in evidence acquisition remains external.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CodeBinding {
    pub chain_id: u64,
    pub contract: String,
    pub block_hash: String,
    pub runtime_code_hash: String,
    pub expected_runtime_code_hash: String,
    pub proxy_implementation: Option<String>,
    pub implementation_code_hash: Option<String>,
    pub expected_implementation_code_hash: Option<String>,
}
impl CodeBinding {
    pub fn verify_supplied_hashes(&self) -> DiscoveryResult<()> {
        if self.chain_id == 0 || address(&self.contract)? == Address::ZERO {
            return Err(error("invalid code identity"));
        }
        hash(&self.block_hash)?;
        if hash(&self.runtime_code_hash)? != hash(&self.expected_runtime_code_hash)? {
            return Err(error("runtime hash mismatch"));
        }
        match (
            &self.proxy_implementation,
            &self.implementation_code_hash,
            &self.expected_implementation_code_hash,
        ) {
            (None, None, None) => Ok(()),
            (Some(implementation), Some(observed), Some(expected))
                if address(implementation)? != Address::ZERO
                    && hash(observed)? == hash(expected)? =>
            {
                Ok(())
            }
            _ => Err(error("proxy implementation identity missing or changed")),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BytecodeFingerprint {
    pub algorithm: String,
    pub runtime_keccak256: String,
    pub selectors: BTreeSet<String>,
    /// Linear selector extraction stopped at an incomplete PUSH operand.
    /// This may be unreachable metadata and says nothing about runtime validity.
    pub selector_scan_truncated: bool,
    pub minhash: Vec<u64>,
    pub shingle_width: usize,
    pub byte_length: usize,
}

/// PUSH4 operands are candidates, not guaranteed dispatch selectors. PUSH data is skipped.
/// Incomplete PUSH tails stop selector extraction but remain in both byte hashes.
pub fn bytecode_fingerprint(
    code: &[u8],
    shingle_width: usize,
    permutations: usize,
) -> DiscoveryResult<BytecodeFingerprint> {
    if code.is_empty()
        || code.len() > 1_048_576
        || code.len().saturating_mul(permutations) > 8_388_608
        || shingle_width == 0
        || shingle_width > code.len()
        || !(8..=256).contains(&permutations)
    {
        return Err(error("invalid fingerprint bounds"));
    }
    let mut selectors = BTreeSet::new();
    let mut selector_scan_truncated = false;
    let mut pc = 0usize;
    while pc < code.len() {
        let op = code[pc];
        let immediate = if (0x60..=0x7f).contains(&op) {
            (op - 0x5f) as usize
        } else {
            0
        };
        if pc + 1 + immediate > code.len() {
            selector_scan_truncated = true;
            break;
        }
        if op == 0x63 {
            selectors.insert(format!(
                "0x{:02x}{:02x}{:02x}{:02x}",
                code[pc + 1],
                code[pc + 2],
                code[pc + 3],
                code[pc + 4]
            ));
        }
        pc += 1 + immediate;
    }
    let mut minhash = vec![u64::MAX; permutations];
    // Independent seeded SHA-256 permutations: stable across architectures/runtimes.
    // Raw-byte shingles deliberately retain immutables/metadata; no semantic equivalence claim.
    for shingle in code.windows(shingle_width) {
        for (i, minimum) in minhash.iter_mut().enumerate() {
            let mut digest = Sha256::new();
            digest.update(b"nqc-miner-bytecode-minhash-v1");
            digest.update((i as u64).to_be_bytes());
            digest.update(shingle);
            let result = digest.finalize();
            let value =
                u64::from_be_bytes(result[..8].try_into().expect("eight-byte digest prefix"));
            *minimum = (*minimum).min(value);
        }
    }
    Ok(BytecodeFingerprint {
        algorithm: "sha256-minhash-v1".into(),
        runtime_keccak256: format!("{:#x}", keccak256(code)),
        selectors,
        selector_scan_truncated,
        minhash,
        shingle_width,
        byte_length: code.len(),
    })
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ForkSimilarity {
    pub exact_runtime_match: bool,
    pub bytecode_jaccard_estimate: f64,
    pub selector_jaccard: Option<f64>,
    pub semantic_equivalence_certified: bool,
}
pub fn compare_fingerprints(
    a: &BytecodeFingerprint,
    b: &BytecodeFingerprint,
) -> DiscoveryResult<ForkSimilarity> {
    if a.algorithm != "sha256-minhash-v1"
        || a.algorithm != b.algorithm
        || a.shingle_width != b.shingle_width
        || a.minhash.len() != b.minhash.len()
        || !(8..=256).contains(&a.minhash.len())
        || a.byte_length == 0
        || b.byte_length == 0
    {
        return Err(error("incompatible or empty fingerprint"));
    }
    hash(&a.runtime_keccak256)?;
    hash(&b.runtime_keccak256)?;
    let union = a.selectors.union(&b.selectors).count();
    Ok(ForkSimilarity {
        exact_runtime_match: a.runtime_keccak256 == b.runtime_keccak256,
        bytecode_jaccard_estimate: a
            .minhash
            .iter()
            .zip(&b.minhash)
            .filter(|(x, y)| x == y)
            .count() as f64
            / a.minhash.len() as f64,
        selector_jaccard: (union > 0)
            .then(|| a.selectors.intersection(&b.selectors).count() as f64 / union as f64),
        semantic_equivalence_certified: false,
    })
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TimelockStatus {
    Queued,
    Cancelled,
    Executed,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TimelockOperation {
    pub chain_id: u64,
    pub contract: String,
    pub operation_id: String,
    pub queued_at: u64,
    pub earliest_execution_timestamp: u64,
    pub predecessor: Option<String>,
    pub payload_hash: String,
    pub status: TimelockStatus,
    pub actual_execution: Option<(u64, u64, String)>,
}
#[derive(Debug, Clone, Default)]
pub struct TimelockBook {
    operations: BTreeMap<String, TimelockOperation>,
}
impl TimelockBook {
    fn key(chain: u64, contract: &str, id: &str) -> DiscoveryResult<String> {
        if chain == 0 {
            return Err(error("invalid timelock chain"));
        }
        Ok(format!(
            "{chain}:{:#x}:{:#x}",
            address(contract)?,
            hash(id)?
        ))
    }
    pub fn queue(&mut self, operation: TimelockOperation) -> DiscoveryResult<()> {
        if operation.queued_at > operation.earliest_execution_timestamp
            || operation.status != TimelockStatus::Queued
            || operation.actual_execution.is_some()
        {
            return Err(error("invalid newly queued timelock operation"));
        }
        hash(&operation.payload_hash)?;
        if let Some(predecessor) = &operation.predecessor {
            hash(predecessor)?;
        }
        let key = Self::key(
            operation.chain_id,
            &operation.contract,
            &operation.operation_id,
        )?;
        if self.operations.contains_key(&key) {
            return Err(error(
                "operation id already present; cancellations require a new evidence cycle",
            ));
        }
        self.operations.insert(key, operation);
        Ok(())
    }
    pub fn cancel(&mut self, chain: u64, contract: &str, id: &str) -> DiscoveryResult<()> {
        let key = Self::key(chain, contract, id)?;
        let operation = self
            .operations
            .get_mut(&key)
            .ok_or_else(|| error("unknown operation"))?;
        if operation.status != TimelockStatus::Queued {
            return Err(error("only queued operations may cancel"));
        }
        operation.status = TimelockStatus::Cancelled;
        Ok(())
    }
    /// Eligibility is an earliest timestamp, never a predicted exact execution block.
    pub fn eligible(&self, now: u64) -> Vec<&TimelockOperation> {
        self.operations
            .values()
            .filter(|operation| {
                operation.status == TimelockStatus::Queued
                    && operation.earliest_execution_timestamp <= now
                    && operation.predecessor.as_ref().is_none_or(|p| {
                        Self::key(operation.chain_id, &operation.contract, p)
                            .ok()
                            .and_then(|k| self.operations.get(&k))
                            .is_some_and(|p| {
                                p.status == TimelockStatus::Executed
                                    && p.actual_execution
                                        .as_ref()
                                        .is_some_and(|(time, _, _)| *time <= now)
                            })
                    })
            })
            .collect()
    }
    pub fn mark_executed(
        &mut self,
        chain: u64,
        contract: &str,
        id: &str,
        timestamp: u64,
        block: u64,
        block_hash: &str,
    ) -> DiscoveryResult<()> {
        let key = Self::key(chain, contract, id)?;
        hash(block_hash)?;
        if !self.eligible(timestamp).iter().any(|op| {
            Self::key(op.chain_id, &op.contract, &op.operation_id)
                .ok()
                .as_ref()
                == Some(&key)
        }) {
            return Err(error(
                "operation is not eligible or predecessor is not executed",
            ));
        }
        let op = self
            .operations
            .get_mut(&key)
            .ok_or_else(|| error("unknown operation"))?;
        op.status = TimelockStatus::Executed;
        op.actual_execution = Some((timestamp, block, block_hash.to_ascii_lowercase()));
        Ok(())
    }
    pub fn operation(
        &self,
        chain: u64,
        contract: &str,
        id: &str,
    ) -> DiscoveryResult<&TimelockOperation> {
        self.operations
            .get(&Self::key(chain, contract, id)?)
            .ok_or_else(|| error("unknown operation"))
    }
}

pub const WAD: u128 = 1_000_000_000_000_000_000;
fn checked_mul(x: U256, y: U256) -> DiscoveryResult<U256> {
    x.checked_mul(y)
        .ok_or_else(|| error("Solidity uint256 multiplication overflow"))
}
fn checked_add(x: U256, y: U256) -> DiscoveryResult<U256> {
    x.checked_add(y)
        .ok_or_else(|| error("Solidity uint256 addition overflow"))
}
/// Exact integer evaluation of Morpho Blue MathLib.wTaylorCompounded for the supplied rate.
/// The *protocol's formula* is a Taylor approximation; this does not approximate its rounding.
pub fn morpho_taylor_compounded(
    rate_wad_per_second: U256,
    elapsed_seconds: u64,
) -> DiscoveryResult<U256> {
    let first = checked_mul(rate_wad_per_second, U256::from(elapsed_seconds))?;
    let second = checked_mul(first, first)? / U256::from(2 * WAD);
    let third = checked_mul(second, first)? / U256::from(3 * WAD);
    checked_add(checked_add(first, second)?, third)
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MorphoInterestSnapshot {
    pub chain_id: u64,
    pub market_id: String,
    pub block_hash: String,
    pub timestamp: u64,
    pub total_borrow_assets: u128,
    pub total_borrow_shares: u128,
    pub borrower_shares: u128,
    pub rate_wad_per_second: String,
    pub maximum_healthy_debt_assets: u128,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct InterestProjection {
    pub timestamp: u64,
    pub debt_assets: String,
    pub liquidatable_under_fixed_assumptions: bool,
    pub assumptions: Vec<String>,
}
impl MorphoInterestSnapshot {
    pub fn project(&self, at: u64) -> DiscoveryResult<InterestProjection> {
        if self.chain_id == 0
            || at < self.timestamp
            || self.borrower_shares > self.total_borrow_shares
        {
            return Err(error("invalid interest snapshot"));
        }
        hash(&self.market_id)?;
        hash(&self.block_hash)?;
        let rate =
            U256::from_str(&self.rate_wad_per_second).map_err(|_| error("invalid rate integer"))?;
        let growth = morpho_taylor_compounded(rate, at - self.timestamp)?;
        let interest = checked_mul(U256::from(self.total_borrow_assets), growth)? / U256::from(WAD);
        let total = checked_add(U256::from(self.total_borrow_assets), interest)?;
        if total > U256::from(u128::MAX) {
            return Err(error("Morpho uint128 totalBorrowAssets overflow"));
        }
        let denominator = checked_add(
            U256::from(self.total_borrow_shares),
            U256::from(1_000_000u64),
        )?;
        let numerator = checked_mul(
            U256::from(self.borrower_shares),
            checked_add(total, U256::from(1u8))?,
        )?;
        // SharesMathLib.toAssetsUp: preserve checked x*y + (d-1), then division.
        let debt = checked_add(numerator, denominator - U256::from(1u8))? / denominator;
        Ok(InterestProjection {
            timestamp: at,
            debt_assets: debt.to_string(),
            liquidatable_under_fixed_assumptions: debt
                > U256::from(self.maximum_healthy_debt_assets),
            assumptions: vec![
                "borrow rate held constant for one accrual interval".into(),
                "no deposits, borrows, repayments, liquidations, or intermediate accruals".into(),
                "oracle, collateral and LLTV held constant".into(),
            ],
        })
    }
    pub fn first_crossing(&self, horizon: u64) -> DiscoveryResult<Option<InterestProjection>> {
        if horizon < self.timestamp {
            return Err(error("horizon precedes snapshot"));
        }
        if self
            .project(self.timestamp)?
            .liquidatable_under_fixed_assumptions
        {
            return self.project(self.timestamp).map(Some);
        }
        if !self.project(horizon)?.liquidatable_under_fixed_assumptions {
            return Ok(None);
        }
        let mut lo = self.timestamp;
        let mut hi = horizon;
        while hi - lo > 1 {
            let mid = lo + (hi - lo) / 2;
            if self.project(mid)?.liquidatable_under_fixed_assumptions {
                hi = mid
            } else {
                lo = mid
            }
        }
        self.project(hi).map(Some)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AddressNode {
    pub chain_id: u64,
    pub address: String,
}
impl AddressNode {
    fn normalized(&self) -> DiscoveryResult<Self> {
        if self.chain_id == 0 {
            return Err(error("invalid graph chain"));
        }
        Ok(Self {
            chain_id: self.chain_id,
            address: format!("{:#x}", address(&self.address)?),
        })
    }
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AssociationReason {
    CommonFunding,
    CommonDeployer,
    OperationPattern,
    ExplicitBridgeEvidence,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AssociationEdge {
    pub a: AddressNode,
    pub b: AddressNode,
    pub reason: AssociationReason,
    pub confidence_bps: u16,
    pub evidence_hash: String,
    pub observed_at: u64,
}
#[derive(Debug, Clone, Default)]
pub struct EvidenceGraph {
    edges: Vec<AssociationEdge>,
    evidence: BTreeSet<String>,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AssociationCluster {
    pub nodes: Vec<AddressNode>,
    pub evidence_hashes: Vec<String>,
    pub identity_proven: bool,
}
impl EvidenceGraph {
    pub fn add(&mut self, mut edge: AssociationEdge) -> DiscoveryResult<()> {
        edge.a = edge.a.normalized()?;
        edge.b = edge.b.normalized()?;
        if edge.a == edge.b || edge.confidence_bps == 0 || edge.confidence_bps >= 10_000 {
            return Err(error(
                "heuristic association must have confidence between 1 and 9999 bps",
            ));
        }
        let evidence = format!("{:#x}", hash(&edge.evidence_hash)?);
        if !self.evidence.insert(evidence.clone()) {
            return Err(error("duplicate association evidence"));
        }
        edge.evidence_hash = evidence;
        self.edges.push(edge);
        Ok(())
    }
    /// Connected candidates at an as-of time. Confidence is not multiplied into identity truth.
    pub fn cluster(
        &self,
        start: &AddressNode,
        minimum_confidence_bps: u16,
        as_of: u64,
    ) -> DiscoveryResult<AssociationCluster> {
        if minimum_confidence_bps == 0 || minimum_confidence_bps > 10_000 {
            return Err(error("invalid graph threshold"));
        }
        let mut nodes = BTreeSet::from([start.normalized()?]);
        let mut evidence = BTreeSet::new();
        loop {
            let old = nodes.len();
            for edge in &self.edges {
                if edge.observed_at > as_of || edge.confidence_bps < minimum_confidence_bps {
                    continue;
                }
                if nodes.contains(&edge.a) || nodes.contains(&edge.b) {
                    nodes.insert(edge.a.clone());
                    nodes.insert(edge.b.clone());
                    evidence.insert(edge.evidence_hash.clone());
                }
            }
            if nodes.len() == old {
                break;
            }
        }
        Ok(AssociationCluster {
            nodes: nodes.into_iter().collect(),
            evidence_hashes: evidence.into_iter().collect(),
            identity_proven: false,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IncentiveCampaign {
    pub campaign_id: String,
    pub chain_id: u64,
    pub market_id: String,
    pub starts_at: u64,
    pub ends_at: u64,
    pub observed_at: u64,
    pub source_hash: String,
    pub cancelled: bool,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LeverageSample {
    pub timestamp: u64,
    pub supplied_value_microusd: u64,
    pub borrowed_value_microusd: u64,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IncentiveEndSignal {
    pub campaign_id: String,
    pub ends_at: u64,
    pub seconds_until_end: u64,
    pub borrow_to_supply_bps: Option<u64>,
    pub implies_liquidation: bool,
}
impl IncentiveCampaign {
    pub fn end_signal(
        &self,
        now: u64,
        lookahead: u64,
        samples: &[LeverageSample],
    ) -> DiscoveryResult<Option<IncentiveEndSignal>> {
        if self.campaign_id.is_empty()
            || self.chain_id == 0
            || self.market_id.is_empty()
            || self.starts_at >= self.ends_at
            || self.observed_at > now
        {
            return Err(error("invalid or future campaign evidence"));
        }
        hash(&self.source_hash)?;
        if self.cancelled || now > self.ends_at || self.ends_at - now > lookahead {
            return Ok(None);
        }
        let last = samples
            .iter()
            .filter(|s| s.timestamp <= now)
            .max_by_key(|s| s.timestamp);
        let borrow_to_supply_bps = match last {
            None => None,
            Some(s) if s.supplied_value_microusd == 0 => None,
            Some(s) => {
                let numerator = (s.borrowed_value_microusd as u128) * 10_000;
                Some(
                    u64::try_from(numerator / (s.supplied_value_microusd as u128))
                        .map_err(|_| error("leverage ratio overflow"))?,
                )
            }
        };
        Ok(Some(IncentiveEndSignal {
            campaign_id: self.campaign_id.clone(),
            ends_at: self.ends_at,
            seconds_until_end: self.ends_at - now,
            borrow_to_supply_bps,
            implies_liquidation: false,
        }))
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Maturity {
    pub chain_id: u64,
    pub market_id: String,
    pub maturity_timestamp: u64,
    pub source_hash: String,
    pub observed_at: u64,
}
pub fn approaching_maturities(
    items: &[Maturity],
    now: u64,
    horizon_seconds: u64,
) -> DiscoveryResult<Vec<Maturity>> {
    let end = now
        .checked_add(horizon_seconds)
        .ok_or_else(|| error("maturity horizon overflow"))?;
    let mut result = Vec::new();
    let mut ids = BTreeSet::new();
    for item in items {
        if item.chain_id == 0 || item.market_id.is_empty() {
            return Err(error("invalid maturity"));
        }
        hash(&item.source_hash)?;
        if item.observed_at <= now && (now..=end).contains(&item.maturity_timestamp) {
            if !ids.insert((
                item.chain_id,
                item.market_id.clone(),
                item.maturity_timestamp,
            )) {
                return Err(error("duplicate maturity evidence"));
            }
            result.push(item.clone());
        }
    }
    result.sort_by_key(|item| {
        (
            item.maturity_timestamp,
            item.chain_id,
            item.market_id.clone(),
        )
    });
    Ok(result)
}
