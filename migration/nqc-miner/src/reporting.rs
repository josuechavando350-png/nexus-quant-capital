//! Research summaries reconstructed solely from this Miner's verified journal.
use crate::{
    analytics::{
        self, ChainEventId, CoverageReport, EvidenceClass, LiquidationObservation,
        SaturationCalibration, SaturationInput, SaturationReport, ScanManifest, ScanRange,
        WatchInterval,
    },
    config::{DataClass, MinerConfig},
    discovery::{BirthSignal, DecodedEvent},
    journal::{self, Record, RunIdentity},
};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, path::Path};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScopeCompletion {
    pub scope_id: String,
    pub chain_id: u64,
    pub from_block: u64,
    pub to_block: u64,
    pub completed_through: Option<u64>,
    pub complete: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MinerReport {
    pub schema: String,
    pub owner: RunIdentity,
    pub scope_completion: Vec<ScopeCompletion>,
    pub birth_candidates: Vec<BirthSignal>,
    pub saturations: Vec<SaturationReport>,
    /// Null until every configured range is complete and canonical.
    pub coverage: Option<CoverageReport>,
    pub coverage_unavailable_reason: Option<String>,
    pub observed_liquidations: usize,
    pub measured_realized_profit: Option<i64>,
    pub money_unit: String,
    pub source_authentication: String,
    pub activation_permitted: bool,
}

pub fn evidence_class(class: DataClass) -> EvidenceClass {
    match class {
        DataClass::Synthetic => EvidenceClass::Fixture,
        DataClass::Historical => EvidenceClass::Historical,
        DataClass::Shadow => EvidenceClass::Shadow,
    }
}

/// These thresholds have no empirical authority. Uncalibrated is mandatory here.
pub fn uncalibrated_thresholds(class: EvidenceClass) -> SaturationCalibration {
    SaturationCalibration {
        calibration_id: "unconfigured-no-economic-admission".into(),
        evidence_class: class,
        calibrated: false,
        minimum_events: 10,
        minimum_delay_observations: 10,
        minimum_tip_observations: 10,
        virgin_unique_max: 1,
        virgin_median_delay_min_blocks: 3,
        virgin_tip_share_max: 0.2,
        dead_unique_min: 5,
        dead_median_delay_max_blocks: 0,
        dead_tip_share_min: 0.9,
    }
}

pub fn report(
    config: &MinerConfig,
    state: &Path,
    watches: &[WatchInterval],
) -> Result<MinerReport, Box<dyn std::error::Error>> {
    config.validate()?;
    let (owner, records) = journal::read_verified(state)?;
    if owner != RunIdentity::from_config(config)? {
        return Err("report configuration does not own this evidence".into());
    }
    let class = evidence_class(config.data_class);
    let mut invalid: BTreeMap<u64, u64> = BTreeMap::new();
    for record in &records {
        if let Record::Invalidated {
            chain_id,
            from_block,
            ..
        } = &record.record
        {
            invalid
                .entry(*chain_id)
                .and_modify(|v| *v = (*v).min(*from_block))
                .or_insert(*from_block);
        }
    }
    let mut completion = Vec::new();
    let mut ranges = Vec::new();
    for scope in &config.scopes {
        let mut chunks = records
            .iter()
            .filter_map(|record| match &record.record {
                Record::ChunkCompleted {
                    scope_id,
                    chain_id,
                    from_block,
                    to_block,
                    end_block_hash,
                    ..
                } if scope_id == &scope.id && *chain_id == scope.chain_id => {
                    Some((*from_block, *to_block, end_block_hash))
                }
                _ => None,
            })
            .collect::<Vec<_>>();
        chunks.sort_by_key(|c| c.0);
        let mut next = scope.from_block;
        let mut through = None;
        let mut hash = None;
        for (from, to, last_hash) in chunks {
            if from != next || to < from || to > scope.to_block {
                return Err("noncontiguous report checkpoint".into());
            }
            if invalid
                .get(&scope.chain_id)
                .is_some_and(|start| to >= *start)
            {
                break;
            }
            through = Some(to);
            hash = Some(last_hash.clone());
            next = to.checked_add(1).ok_or("checkpoint overflow")?;
        }
        let certified_completion=records.iter().any(|entry|matches!(&entry.record,Record::ScopeCompleted{scope_id,chain_id,..}if scope_id==&scope.id && *chain_id==scope.chain_id));
        let complete = through == Some(scope.to_block) && certified_completion;
        if complete {
            for topic in &scope.event_topics {
                ranges.push(ScanRange {
                    chain_id: scope.chain_id,
                    contract: scope.contract.clone(),
                    topic0: topic.clone(),
                    first_block: scope.from_block,
                    last_block: scope.to_block,
                    last_block_hash: hash.clone().ok_or("missing checkpoint hash")?,
                    complete: true,
                    finalized: true,
                });
            }
        }
        completion.push(ScopeCompletion {
            scope_id: scope.id.clone(),
            chain_id: scope.chain_id,
            from_block: scope.from_block,
            to_block: scope.to_block,
            completed_through: through,
            complete,
        });
    }
    let mut events = Vec::new();
    let mut births = Vec::new();
    let mut by_mine: BTreeMap<(String, u64, String), Vec<LiquidationObservation>> = BTreeMap::new();
    for record in &records {
        if let Record::Observed {
            scope_id,
            log,
            decoded,
            block_timestamp,
            ..
        } = &record.record
        {
            if invalid
                .get(&log.chain_id)
                .is_some_and(|start| log.block_number >= *start)
            {
                continue;
            }
            if !journal::event_committed(scope_id, log.block_number, &records) {
                continue;
            }
            match decoded.as_ref() {
                DecodedEvent::Birth(value) => births.push(value.clone()),
                DecodedEvent::Liquidation(value) => {
                    let observation = LiquidationObservation {
                        event_id: ChainEventId {
                            chain_id: log.chain_id,
                            block_hash: log.block_hash.clone(),
                            transaction_hash: log.transaction_hash.clone(),
                            log_index: log.log_index,
                        },
                        mine_id: value.market_id.clone(),
                        block_number: log.block_number,
                        block_timestamp: *block_timestamp,
                        contract: log.address.clone(),
                        topic0: log.topics[0].clone(),
                        liquidator: value.liquidator.clone(),
                        first_eligible_block: None,
                        gross_bonus_microusd: None,
                        builder_tip_microusd: None,
                        canonical: true,
                        finalized: true,
                        evidence_class: class,
                    };
                    by_mine
                        .entry((scope_id.clone(), log.chain_id, value.market_id.clone()))
                        .or_default()
                        .push(observation.clone());
                    events.push(observation);
                }
            }
        }
    }
    let mut saturations = Vec::new();
    for ((scope_id, chain_id, mine_id), events) in by_mine {
        let scope = config
            .scopes
            .iter()
            .find(|s| s.id == scope_id)
            .ok_or("record scope absent from configuration")?;
        let scan_complete = completion
            .iter()
            .find(|s| s.scope_id == scope_id)
            .ok_or("missing completion")?
            .complete;
        saturations.push(analytics::saturation(
            &SaturationInput {
                mine_id,
                chain_id,
                first_block: scope.from_block,
                last_block: scope.to_block,
                scan_complete,
                evidence_class: class,
                events,
            },
            &uncalibrated_thresholds(class),
        )?);
    }
    let all_complete = completion.iter().all(|s| s.complete);
    let coverage = if all_complete {
        Some(analytics::coverage(
            &ScanManifest {
                scan_id: config.run_id.clone(),
                evidence_class: class,
                ranges,
            },
            &events,
            watches,
        )?)
    } else {
        None
    };
    Ok(MinerReport {
        schema: "nqc-miner-report-v1".into(),
        owner,
        scope_completion: completion,
        birth_candidates: births,
        saturations,
        coverage,
        coverage_unavailable_reason: if all_complete {
            None
        } else {
            Some("configured scan has incomplete or invalidated ranges".into())
        },
        observed_liquidations: events.len(),
        measured_realized_profit: None,
        money_unit: "USD millionths (no realized ledger imported)".into(),
        source_authentication: "provider agreement and local integrity; no independent chain proof"
            .into(),
        activation_permitted: false,
    })
}

/// Textfile metrics: safe to scrape without exposing RPC URLs, borrower IDs or keys.
pub fn prometheus(report: &MinerReport) -> String {
    let complete = report
        .scope_completion
        .iter()
        .filter(|s| s.complete)
        .count();
    format!("# HELP nqc_miner_scopes_total Configured contract and block scopes\n# TYPE nqc_miner_scopes_total gauge\nnqc_miner_scopes_total {}\n\
# HELP nqc_miner_scopes_complete Complete finalized scopes\n# TYPE nqc_miner_scopes_complete gauge\nnqc_miner_scopes_complete {}\n\
# HELP nqc_miner_birth_candidates Observed candidates without safety certification\n# TYPE nqc_miner_birth_candidates gauge\nnqc_miner_birth_candidates {}\n\
# HELP nqc_miner_liquidations Observed finalized liquidation logs\n# TYPE nqc_miner_liquidations gauge\nnqc_miner_liquidations {}\n\
# HELP nqc_miner_execution_enabled Execution capability in this build\n# TYPE nqc_miner_execution_enabled gauge\nnqc_miner_execution_enabled 0\n", report.scope_completion.len(),complete,report.birth_candidates.len(),report.observed_liquidations)
}
