//! Bounded-memory read-back of every canonical historical capital source.
//! The existing decoder validates each readable/canonical record. Cross-row
//! uniqueness, common provenance and anchor are preserved across the stream.
//! Aave selection is a derived view, never a replacement for the full universe.
use nqc_census_capital::{
    adapters::AAVE_V3_PROVIDER_NAMESPACE, artifacts::parse_capital_sources_artifact, CapitalAsset,
    CapitalClass, CapitalProviderKind, CapitalSource, RepaymentSemantics,
};
use nqc_census_chain::json::Json;
use nqc_census_core::{Address, StateAnchor};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeSet,
    error::Error,
    io::{BufRead, Read},
};

const MAX_LINE_BYTES: u64 = 65_536;
const MAX_SELECTED_ROWS: u64 = 67;

pub struct Expected<'a> {
    pub sha256: &'a str,
    pub bytes: u64,
    pub rows: u64,
    pub code_commit: &'a str,
    pub code_tree: &'a str,
    pub anchor: &'a StateAnchor,
    pub pool: Address,
}

#[derive(Debug)]
pub struct Scan {
    pub bytes: u64,
    pub rows: u64,
    pub selected_rows: u64,
    pub selected_blocked: u64,
    pub selected_bytes: Vec<u8>,
    pub sha256: String,
    pub selected_sha256: String,
}

/// Necessary (not sufficient) provider predicate used by the unchanged
/// evaluate_protocol_native_flash_promotion. Debt-asset matching is deferred
/// to that function for each actual candidate. Every excluded source fails at
/// least one of its non-candidate-specific necessary conditions.
pub fn relevant(source: &CapitalSource, expected: &Expected<'_>) -> bool {
    source.class() == CapitalClass::ProtocolNativeFlashLoan
        && source.provider_namespace() == AAVE_V3_PROVIDER_NAMESPACE
        && source.provider_kind() == CapitalProviderKind::ProtocolContract
        && source.source_contract() == Some(expected.pool)
        && matches!(source.asset(), CapitalAsset::Token(_))
        && source.asset() == source.repayment_asset()
        && matches!(
            source.repayment(),
            RepaymentSemantics::AtomicSameTransaction
        )
        && source.anchor() == expected.anchor
}

pub fn scan(mut reader: impl BufRead, expected: &Expected<'_>) -> Result<Scan, Box<dyn Error>> {
    let mut ids = BTreeSet::new();
    let mut keys = BTreeSet::new();
    let mut hasher = Sha256::new();
    let mut result = Scan {
        bytes: 0,
        rows: 0,
        selected_rows: 0,
        selected_blocked: 0,
        selected_bytes: Vec::new(),
        sha256: String::new(),
        selected_sha256: String::new(),
    };
    loop {
        let mut line = Vec::new();
        let size = (&mut reader)
            .take(MAX_LINE_BYTES + 1)
            .read_until(b'\n', &mut line)?;
        if size == 0 {
            break;
        }
        if size as u64 > MAX_LINE_BYTES || line.last() != Some(&b'\n') || size == 1 {
            return Err("oversized, blank or unterminated capital record".into());
        }
        result.bytes = result
            .bytes
            .checked_add(size as u64)
            .ok_or("byte count overflow")?;
        result.rows = result.rows.checked_add(1).ok_or("row count overflow")?;
        if result.bytes > expected.bytes || result.rows > expected.rows {
            return Err("capital population exceeds exact pin".into());
        }
        hasher.update(&line);
        // Existing parser enforces exact canonical JSON, IDs, source encoding,
        // readable-field consistency and generated-at/anchor agreement.
        let decoded = parse_capital_sources_artifact(&line)?;
        if decoded.len() != 1 {
            return Err("capital row did not decode exactly once".into());
        }
        let source = &decoded[0];
        let row = Json::parse(&line)?;
        if row.str_field("code_commit")? != expected.code_commit
            || row.str_field("code_tree")? != expected.code_tree
            || source.anchor() != expected.anchor
        {
            return Err("capital stream mixes provenance or anchor".into());
        }
        if !ids.insert(source.id()) || !keys.insert(source.key_id()) {
            return Err("capital stream repeats source identity or key".into());
        }
        if relevant(source, expected) {
            result.selected_rows += 1;
            if result.selected_rows > MAX_SELECTED_ROWS {
                return Err("derived Aave view exceeds pinned 67-reserve scope".into());
            }
            result.selected_blocked += u64::from(!source.execution_eligible());
            result.selected_bytes.extend_from_slice(&line);
        }
    }
    result.sha256 = format!("{:x}", hasher.finalize());
    if result.bytes != expected.bytes
        || result.rows != expected.rows
        || result.sha256 != expected.sha256
    {
        return Err("full capital stream size/count/hash mismatch".into());
    }
    result.selected_sha256 = format!("{:x}", Sha256::digest(&result.selected_bytes));
    Ok(result)
}
