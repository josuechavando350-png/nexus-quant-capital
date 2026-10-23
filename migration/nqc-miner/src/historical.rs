//! Bounded Aave account/oracle reads at agreed, finalized block hashes.
//! End-of-block health is not executable liquidation eligibility. Provider
//! agreement is not authenticated state, oracle freshness or proxy certification.
use crate::{
    config::{DataClass, MinerConfig, ScanScope},
    digest, discovery,
    ingestion::{BlockHeader, IngestError, QuorumRpc},
    journal::RunIdentity,
    valid_hex,
};
use alloy_primitives::{keccak256, U256};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::BTreeSet;

const ZERO_ADDRESS: &str = "0x0000000000000000000000000000000000000000";
const MAX_BLOCKS: u64 = 64;
const MAX_ASSETS: usize = 4;
const NO_ARG: [&str; 4] = [
    "ADDRESSES_PROVIDER()",
    "getPriceOracle()",
    "BASE_CURRENCY()",
    "BASE_CURRENCY_UNIT()",
];
const ONE_ADDRESS: [&str; 2] = ["getUserAccountData(address)", "getAssetPrice(address)"];

fn reject(message: &str) -> IngestError {
    IngestError::Rejected(message.into())
}

pub fn hex(bytes: &[u8]) -> String {
    let mut result = String::from("0x");
    for byte in bytes {
        use std::fmt::Write;
        write!(&mut result, "{byte:02x}").expect("string write");
    }
    result
}

pub fn calldata(signature: &str, address: Option<&str>) -> Result<String, IngestError> {
    let selector = hex(&keccak256(signature.as_bytes())[..4]);
    if NO_ARG.contains(&signature) && address.is_none() {
        return Ok(selector);
    }
    if ONE_ADDRESS.contains(&signature) {
        if let Some(address) = address.filter(|a| valid_hex(a, 20) && *a != ZERO_ADDRESS) {
            return Ok(format!("{selector}{}{}", "0".repeat(24), &address[2..]));
        }
    }
    Err(reject("unsupported getter or argument"))
}

pub fn call_params(block_hash: &str, to: &str, data: &str) -> Value {
    json!([{"from":ZERO_ADDRESS,"to":to,"data":data,"value":"0x0","gas":"0x1e8480"},
           {"blockHash":block_hash,"requireCanonical":true}])
}

/// A small getter-only request surface. State overrides and unpinned calls fail.
pub fn validate_call_params(params: &Value) -> Result<(), IngestError> {
    let params = params
        .as_array()
        .filter(|p| p.len() == 2)
        .ok_or_else(|| reject("exactly two pinned call parameters required"))?;
    let tx = params[0]
        .as_object()
        .filter(|p| p.len() == 5)
        .ok_or_else(|| reject("fixed getter call object required"))?;
    let anchor = params[1]
        .as_object()
        .filter(|p| p.len() == 2)
        .ok_or_else(|| reject("hash-pinned block required"))?;
    let to = tx
        .get("to")
        .and_then(Value::as_str)
        .ok_or_else(|| reject("getter address missing"))?;
    let data = tx
        .get("data")
        .and_then(Value::as_str)
        .ok_or_else(|| reject("getter calldata missing"))?;
    let hash = anchor
        .get("blockHash")
        .and_then(Value::as_str)
        .ok_or_else(|| reject("block hash missing"))?;
    if !valid_hex(to, 20)
        || to == ZERO_ADDRESS
        || !valid_hex(hash, 32)
        || hash[2..].bytes().all(|b| b == b'0')
        || anchor.get("requireCanonical") != Some(&json!(true))
        || tx.get("from") != Some(&json!(ZERO_ADDRESS))
        || tx.get("value") != Some(&json!("0x0"))
        || tx.get("gas") != Some(&json!("0x1e8480"))
    {
        return Err(reject("unsafe or unpinned historical getter"));
    }
    let no_arg = NO_ARG
        .iter()
        .any(|s| calldata(s, None).is_ok_and(|v| v == data));
    let one_arg = data.len() == 74
        && valid_hex(data, 36)
        && data[10..34].bytes().all(|b| b == b'0')
        && ONE_ADDRESS
            .iter()
            .any(|s| calldata(s, Some(&format!("0x{}", &data[34..]))).is_ok_and(|v| v == data));
    if !no_arg && !one_arg {
        return Err(reject("getter selector or ABI argument not allowed"));
    }
    Ok(())
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct AaveReadPlan {
    pub schema_version: u16,
    pub scope_id: String,
    pub borrower: String,
    pub assets: Vec<String>,
    pub from_block: u64,
    pub to_block: u64,
    /// Expected canonical event block, after the sampled end-of-block states.
    pub event_block: u64,
    pub event_block_hash: String,
}

impl AaveReadPlan {
    pub fn validate<'a>(&self, config: &'a MinerConfig) -> Result<&'a ScanScope, IngestError> {
        config.validate().map_err(|e| reject(&e.to_string()))?;
        let scope = config
            .scopes
            .iter()
            .find(|s| s.id == self.scope_id)
            .ok_or_else(|| reject("plan scope not configured"))?;
        if self.schema_version != 1
            || scope.protocol != "aave-v3"
            || config.data_class == DataClass::Shadow
            || !valid_hex(&self.borrower, 20)
            || self.borrower == ZERO_ADDRESS
            || self.assets.is_empty()
            || self.assets.len() > MAX_ASSETS
            || self
                .assets
                .iter()
                .any(|a| !valid_hex(a, 20) || a == ZERO_ADDRESS)
            || self.assets.iter().collect::<BTreeSet<_>>().len() != self.assets.len()
            || self.from_block > self.to_block
            || self.to_block - self.from_block >= MAX_BLOCKS
            || self.from_block < scope.from_block
            || self.event_block > scope.to_block
            || self.to_block.checked_add(1) != Some(self.event_block)
            || !valid_hex(&self.event_block_hash, 32)
            || self.event_block_hash[2..].bytes().all(|b| b == b'0')
        {
            return Err(reject(
                "invalid, unbounded, out-of-scope or post-event read plan",
            ));
        }
        Ok(scope)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ProviderReply {
    pub provider_id: String,
    pub result: String,
}
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct CallEvidence {
    pub params: Value,
    pub replies: Vec<ProviderReply>,
}

fn words(call: &CallEvidence, count: usize) -> Result<Vec<U256>, IngestError> {
    let result = call
        .replies
        .first()
        .ok_or_else(|| reject("missing call agreement"))?;
    let data = discovery::decode_hex(&result.result).map_err(|_| reject("bad ABI result"))?;
    if data.len() != count * 32 {
        return Err(reject("getter return ABI length mismatch"));
    }
    Ok(data.chunks_exact(32).map(U256::from_be_slice).collect())
}
fn returned_address(call: &CallEvidence, allow_zero: bool) -> Result<String, IngestError> {
    let value = words(call, 1)?[0].to_be_bytes::<32>();
    if value[..12].iter().any(|b| *b != 0) || !allow_zero && value[12..].iter().all(|b| *b == 0) {
        return Err(reject("noncanonical or zero returned address"));
    }
    Ok(hex(&value[12..]))
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct AccountState {
    pub total_collateral_base: String,
    pub total_debt_base: String,
    pub available_borrows_base: String,
    pub liquidation_threshold_bps: String,
    pub ltv_bps: String,
    pub health_factor_wad: String,
    pub health_factor_below_one_with_debt: bool,
}
#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct OraclePrice {
    pub asset: String,
    pub price_base: String,
}
#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct AaveStateSample {
    pub block: BlockHeader,
    pub addresses_provider: String,
    pub oracle: String,
    pub base_currency: String,
    pub base_currency_unit: String,
    pub base_currency_is_usd_by_interface: bool,
    pub account: AccountState,
    pub prices: Vec<OraclePrice>,
    pub calls: Vec<CallEvidence>,
}
#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct BreachEpisode {
    pub first_sampled_block: u64,
    pub last_sampled_block: u64,
    pub left_censored: bool,
    pub right_censored: bool,
}
#[derive(Debug, Serialize)]
pub struct AaveStateReport {
    pub schema: String,
    pub owner: RunIdentity,
    pub plan: AaveReadPlan,
    pub plan_sha256: String,
    pub providers: Vec<String>,
    pub finalized_anchor: BlockHeader,
    pub event_anchor: BlockHeader,
    pub samples: Vec<AaveStateSample>,
    pub breach_episodes: Vec<BreachEpisode>,
    pub state_timing: String,
    pub oracle_configuration_changed: bool,
    pub provider_agreement_is_not_state_authentication: bool,
    pub source_journal_binding_verified: bool,
    pub executable_eligibility_verified: bool,
    pub first_eligible_block: Option<u64>,
    pub liquidation_delay_blocks: Option<u64>,
    pub prices_freshness_verified: bool,
    pub economic_certification: bool,
    pub activation_allowed: bool,
}

fn sample(
    q: &QuorumRpc,
    scope: &ScanScope,
    plan: &AaveReadPlan,
    block: BlockHeader,
) -> Result<AaveStateSample, IngestError> {
    let mut calls = Vec::new();
    let mut get =
        |to: &str, signature: &str, argument: Option<&str>| -> Result<CallEvidence, IngestError> {
            let call = q.pinned_call(&block.hash, to, &calldata(signature, argument)?)?;
            calls.push(call.clone());
            Ok(call)
        };
    let provider = returned_address(&get(&scope.contract, "ADDRESSES_PROVIDER()", None)?, false)?;
    let oracle = returned_address(&get(&provider, "getPriceOracle()", None)?, false)?;
    let base = returned_address(&get(&oracle, "BASE_CURRENCY()", None)?, true)?;
    let unit = words(&get(&oracle, "BASE_CURRENCY_UNIT()", None)?, 1)?[0];
    if unit == U256::ZERO {
        return Err(reject("zero oracle unit"));
    }
    let a = words(
        &get(
            &scope.contract,
            "getUserAccountData(address)",
            Some(&plan.borrower),
        )?,
        6,
    )?;
    if a[3] > U256::from(10000) || a[4] > U256::from(10000) {
        return Err(reject("account basis points exceed 10000"));
    }
    let account = AccountState {
        total_collateral_base: a[0].to_string(),
        total_debt_base: a[1].to_string(),
        available_borrows_base: a[2].to_string(),
        liquidation_threshold_bps: a[3].to_string(),
        ltv_bps: a[4].to_string(),
        health_factor_wad: a[5].to_string(),
        health_factor_below_one_with_debt: a[1] != U256::ZERO
            && a[5] < U256::from(1_000_000_000_000_000_000u64),
    };
    let mut prices = Vec::new();
    for asset in &plan.assets {
        let price = words(&get(&oracle, "getAssetPrice(address)", Some(asset))?, 1)?[0];
        if price == U256::ZERO {
            return Err(reject("zero oracle price is not an economic observation"));
        }
        prices.push(OraclePrice {
            asset: asset.clone(),
            price_base: price.to_string(),
        });
    }
    if q.block(block.number)? != block {
        return Err(IngestError::Disagreement(
            "block changed during historical reads".into(),
        ));
    }
    Ok(AaveStateSample {
        block,
        addresses_provider: provider,
        oracle,
        base_currency_is_usd_by_interface: base == ZERO_ADDRESS,
        base_currency: base,
        base_currency_unit: unit.to_string(),
        account,
        prices,
        calls,
    })
}

pub fn read_aave(
    config: &MinerConfig,
    plan: &AaveReadPlan,
    q: &QuorumRpc,
) -> Result<AaveStateReport, IngestError> {
    let scope = plan.validate(config)?;
    if q.chain_id() != scope.chain_id
        || q.provider_ids()
            != scope
                .providers
                .iter()
                .map(|p| p.id.clone())
                .collect::<Vec<_>>()
    {
        return Err(reject("historical reader provider/chain mismatch"));
    }
    let anchor = q.common_finalized()?;
    if anchor.number < plan.event_block {
        return Err(reject("event anchor is not finalized"));
    }
    let event = q.block(plan.event_block)?;
    if event.hash != plan.event_block_hash {
        return Err(IngestError::Disagreement("event block identity".into()));
    }
    let mut samples: Vec<AaveStateSample> = Vec::new();
    for number in plan.from_block..=plan.to_block {
        let block = q.block(number)?;
        if samples.last().is_some_and(|s| {
            block.parent_hash != s.block.hash || block.timestamp < s.block.timestamp
        }) {
            return Err(IngestError::Disagreement(
                "historical state block continuity".into(),
            ));
        }
        samples.push(sample(q, scope, plan, block)?);
    }
    let last = samples.last().expect("validated nonempty interval");
    if event.parent_hash != last.block.hash || event.timestamp < last.block.timestamp {
        return Err(IngestError::Disagreement(
            "event parent does not close state interval".into(),
        ));
    }
    // Recheck every sampled block, not just range endpoints, before publishing.
    for s in &samples {
        if q.block(s.block.number)? != s.block {
            return Err(IngestError::Disagreement("historical sample reorg".into()));
        }
    }
    if q.block(event.number)? != event || q.block(anchor.number)? != anchor {
        return Err(IngestError::Disagreement(
            "historical finality/event anchor changed".into(),
        ));
    }
    let mut episodes: Vec<BreachEpisode> = Vec::new();
    for (i, s) in samples.iter().enumerate() {
        if !s.account.health_factor_below_one_with_debt {
            continue;
        }
        if i > 0 && samples[i - 1].account.health_factor_below_one_with_debt {
            let episode = episodes.last_mut().expect("previous breached sample");
            episode.last_sampled_block = s.block.number;
            episode.right_censored = i + 1 == samples.len();
        } else {
            episodes.push(BreachEpisode {
                first_sampled_block: s.block.number,
                last_sampled_block: s.block.number,
                left_censored: i == 0,
                right_censored: i + 1 == samples.len(),
            });
        }
    }
    let oracle_configuration_changed = samples.windows(2).any(|s| {
        s[0].oracle != s[1].oracle
            || s[0].addresses_provider != s[1].addresses_provider
            || s[0].base_currency != s[1].base_currency
            || s[0].base_currency_unit != s[1].base_currency_unit
    });
    Ok(AaveStateReport {
        schema: "nqc-miner-aave-state-v1".into(),
        owner: RunIdentity::from_config(config).map_err(|e| reject(&e.to_string()))?,
        plan: plan.clone(),
        plan_sha256: digest(&serde_json::to_vec(plan).map_err(|_| reject("plan serialization"))?),
        providers: q.provider_ids(),
        finalized_anchor: anchor,
        event_anchor: event,
        samples,
        breach_episodes: episodes,
        state_timing: "end_of_block_before_event_block; no intra-block reconstruction".into(),
        oracle_configuration_changed,
        provider_agreement_is_not_state_authentication: true,
        source_journal_binding_verified: false,
        executable_eligibility_verified: false,
        first_eligible_block: None,
        liquidation_delay_blocks: None,
        prices_freshness_verified: false,
        economic_certification: false,
        activation_allowed: false,
    })
}
