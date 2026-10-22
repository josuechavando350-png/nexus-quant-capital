//! Deterministic, read-only Miner analytics. These models never authorize execution.
//!
//! Observation provenance and finality are inputs verified by the ingestion boundary.
//! None of the estimators can establish data completeness or realized profit by itself.

use rand::{Rng, SeedableRng};
use rand_chacha::ChaCha8Rng;
use rand_distr::{Beta, Distribution};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AnalyticsError {
    pub code: &'static str,
    pub message: String,
}

impl fmt::Display for AnalyticsError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.code, self.message)
    }
}
impl std::error::Error for AnalyticsError {}

pub type Result<T> = std::result::Result<T, AnalyticsError>;

fn fail(code: &'static str, message: impl Into<String>) -> AnalyticsError {
    AnalyticsError {
        code,
        message: message.into(),
    }
}
fn require(ok: bool, code: &'static str, message: &str) -> Result<()> {
    if ok {
        Ok(())
    } else {
        Err(fail(code, message))
    }
}
fn nonempty(s: &str) -> bool {
    !s.is_empty() && s.trim() == s && s.len() <= 256 && s.chars().all(|c| !c.is_control())
}
fn hex(s: &str, bytes: usize) -> bool {
    s.len() == 2 + 2 * bytes
        && s.starts_with("0x")
        && s[2..]
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
fn fraction(x: f64) -> bool {
    x.is_finite() && (0.0..=1.0).contains(&x)
}

/// Data classes are deliberately not interchangeable. Every result retains its class.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EvidenceClass {
    Fixture,
    Historical,
    Shadow,
    Realized,
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ChainEventId {
    pub chain_id: u64,
    pub block_hash: String,
    pub transaction_hash: String,
    pub log_index: u32,
}
impl ChainEventId {
    pub fn validate(&self) -> Result<()> {
        require(
            self.chain_id > 0 && hex(&self.block_hash, 32) && hex(&self.transaction_hash, 32),
            "invalid_event_id",
            "invalid chain or canonical lowercase hash",
        )
    }
    fn logical_key(&self) -> (u64, String, u32) {
        (self.chain_id, self.transaction_hash.clone(), self.log_index)
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LiquidationObservation {
    pub event_id: ChainEventId,
    pub mine_id: String,
    pub block_number: u64,
    pub block_timestamp: u64,
    pub contract: String,
    pub topic0: String,
    pub liquidator: String,
    pub first_eligible_block: Option<u64>,
    pub gross_bonus_microusd: Option<u64>,
    /// Direct builder payments only. Do not also include these in gas costs.
    pub builder_tip_microusd: Option<u64>,
    pub canonical: bool,
    pub finalized: bool,
    pub evidence_class: EvidenceClass,
}
impl LiquidationObservation {
    pub fn validate(&self) -> Result<()> {
        self.event_id.validate()?;
        require(
            nonempty(&self.mine_id)
                && hex(&self.contract, 20)
                && hex(&self.topic0, 32)
                && hex(&self.liquidator, 20),
            "invalid_liquidation",
            "invalid mine, contract, event signature or liquidator",
        )?;
        require(
            self.first_eligible_block
                .is_none_or(|b| b <= self.block_number),
            "future_eligibility",
            "eligibility cannot follow the liquidation block",
        )
    }
}

#[derive(Default)]
struct CanonicalEvents<'a> {
    events: Vec<&'a LiquidationObservation>,
    duplicates: usize,
    noncanonical: usize,
    unfinalized: usize,
}

fn canonical_events(
    events: &[LiquidationObservation],
    class: EvidenceClass,
) -> Result<CanonicalEvents<'_>> {
    let mut result = CanonicalEvents::default();
    let mut seen: BTreeMap<(u64, String, u32), &LiquidationObservation> = BTreeMap::new();
    let mut blocks = BTreeMap::new();
    let mut transactions = BTreeMap::new();
    let mut log_positions = BTreeMap::new();
    for event in events {
        event.validate()?;
        require(
            event.evidence_class == class,
            "mixed_evidence",
            "mixed provenance classes are not allowed",
        )?;
        if !event.canonical {
            result.noncanonical += 1;
            continue;
        }
        if !event.finalized {
            result.unfinalized += 1;
            continue;
        }
        let block = (event.event_id.block_hash.as_str(), event.block_timestamp);
        if let Some(previous) = blocks.insert((event.event_id.chain_id, event.block_number), block)
        {
            require(
                previous == block,
                "conflicting_block",
                "one canonical height has conflicting hashes or timestamps",
            )?;
        }
        let location = (event.block_number, event.event_id.block_hash.as_str());
        if let Some(previous) = transactions.insert(
            (
                event.event_id.chain_id,
                event.event_id.transaction_hash.as_str(),
            ),
            location,
        ) {
            require(
                previous == location,
                "conflicting_transaction",
                "one transaction appears in multiple canonical blocks",
            )?;
        }
        // EVM logIndex is block-global, not transaction-relative. Distinct
        // transaction hashes cannot legitimize two receipts at one position.
        if let Some(previous) = log_positions.insert(
            (
                event.event_id.chain_id,
                event.block_number,
                event.event_id.log_index,
            ),
            event.event_id.transaction_hash.as_str(),
        ) {
            require(
                previous == event.event_id.transaction_hash,
                "conflicting_log_index",
                "one canonical block log position has conflicting transaction hashes",
            )?;
        }
        if let Some(prior) = seen.get(&event.event_id.logical_key()) {
            require(
                *prior == event,
                "conflicting_event",
                "conflicting canonical events require reconciliation",
            )?;
            result.duplicates += 1;
        } else {
            seen.insert(event.event_id.logical_key(), event);
        }
    }
    result.events = seen.into_values().collect();
    result
        .events
        .sort_by_key(|e| (e.event_id.chain_id, e.block_number, e.event_id.log_index));
    Ok(result)
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SaturationInput {
    pub mine_id: String,
    pub chain_id: u64,
    pub first_block: u64,
    pub last_block: u64,
    pub scan_complete: bool,
    pub evidence_class: EvidenceClass,
    pub events: Vec<LiquidationObservation>,
}

/// Thresholds must be supplied by a versioned Census calibration, never inferred
/// from a single market's absence of observations.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SaturationCalibration {
    pub calibration_id: String,
    pub evidence_class: EvidenceClass,
    pub calibrated: bool,
    pub minimum_events: usize,
    pub minimum_delay_observations: usize,
    pub minimum_tip_observations: usize,
    pub virgin_unique_max: usize,
    pub virgin_median_delay_min_blocks: u64,
    pub virgin_tip_share_max: f64,
    pub dead_unique_min: usize,
    pub dead_median_delay_max_blocks: u64,
    pub dead_tip_share_min: f64,
}
impl SaturationCalibration {
    pub fn validate(&self) -> Result<()> {
        require(
            nonempty(&self.calibration_id)
                && self.minimum_events > 0
                && self.minimum_delay_observations > 0
                && self.minimum_tip_observations > 0,
            "invalid_calibration",
            "calibration identity and positive sample minimums are required",
        )?;
        require(
            self.virgin_unique_max < self.dead_unique_min
                && self.virgin_median_delay_min_blocks > self.dead_median_delay_max_blocks
                && fraction(self.virgin_tip_share_max)
                && fraction(self.dead_tip_share_min)
                && self.virgin_tip_share_max < self.dead_tip_share_min,
            "invalid_calibration",
            "overlapping or invalid saturation thresholds",
        )
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SaturationState {
    IncompleteScan,
    InsufficientData,
    Uncalibrated,
    Virgin,
    Disputed,
    Dead,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SaturationReport {
    pub mine_id: String,
    pub chain_id: u64,
    pub first_block: u64,
    pub last_block: u64,
    pub evidence_class: EvidenceClass,
    pub calibration_id: String,
    pub state: SaturationState,
    pub liquidations: usize,
    pub unique_liquidators: usize,
    pub median_delay_blocks: Option<f64>,
    pub delay_observations: usize,
    pub mean_builder_tip_share: Option<f64>,
    pub tip_observations: usize,
    pub deduplicated: usize,
    pub excluded_noncanonical: usize,
    pub excluded_unfinalized: usize,
}

pub fn saturation(
    input: &SaturationInput,
    calibration: &SaturationCalibration,
) -> Result<SaturationReport> {
    calibration.validate()?;
    require(
        input.chain_id > 0 && nonempty(&input.mine_id) && input.first_block <= input.last_block,
        "invalid_window",
        "invalid saturation window",
    )?;
    require(
        calibration.evidence_class == input.evidence_class,
        "mixed_calibration",
        "calibration and data classes differ",
    )?;
    for e in &input.events {
        require(
            e.mine_id == input.mine_id
                && e.event_id.chain_id == input.chain_id
                && (input.first_block..=input.last_block).contains(&e.block_number),
            "outside_window",
            "saturation event lies outside the declared mine window",
        )?;
    }
    let canonical = canonical_events(&input.events, input.evidence_class)?;
    let unique: BTreeSet<_> = canonical.events.iter().map(|e| &e.liquidator).collect();
    let mut delays: Vec<f64> = canonical
        .events
        .iter()
        .filter_map(|e| e.first_eligible_block.map(|b| (e.block_number - b) as f64))
        .collect();
    delays.sort_by(f64::total_cmp);
    let tips: Vec<f64> = canonical
        .events
        .iter()
        .filter_map(|e| match (e.gross_bonus_microusd, e.builder_tip_microusd) {
            (Some(b), Some(t)) if b > 0 => Some(t as f64 / b as f64),
            _ => None,
        })
        .collect();
    let delay = if delays.is_empty() {
        None
    } else {
        Some(quantile_sorted(&delays, 0.5))
    };
    let tip = if tips.is_empty() {
        None
    } else {
        Some(tips.iter().sum::<f64>() / tips.len() as f64)
    };
    let state = if !input.scan_complete || canonical.unfinalized > 0 {
        SaturationState::IncompleteScan
    } else if canonical.events.len() < calibration.minimum_events
        || delays.len() < calibration.minimum_delay_observations
        || tips.len() < calibration.minimum_tip_observations
    {
        SaturationState::InsufficientData
    } else if !calibration.calibrated {
        SaturationState::Uncalibrated
    } else if unique.len() <= calibration.virgin_unique_max
        && delay.is_some_and(|d| d >= calibration.virgin_median_delay_min_blocks as f64)
        && tip.is_some_and(|t| t <= calibration.virgin_tip_share_max)
    {
        SaturationState::Virgin
    } else if unique.len() >= calibration.dead_unique_min
        && delay.is_some_and(|d| d <= calibration.dead_median_delay_max_blocks as f64)
        && tip.is_some_and(|t| t >= calibration.dead_tip_share_min)
    {
        SaturationState::Dead
    } else {
        SaturationState::Disputed
    };
    Ok(SaturationReport {
        mine_id: input.mine_id.clone(),
        chain_id: input.chain_id,
        first_block: input.first_block,
        last_block: input.last_block,
        evidence_class: input.evidence_class,
        calibration_id: calibration.calibration_id.clone(),
        state,
        liquidations: canonical.events.len(),
        unique_liquidators: unique.len(),
        median_delay_blocks: delay,
        delay_observations: delays.len(),
        mean_builder_tip_share: tip,
        tip_observations: tips.len(),
        deduplicated: canonical.duplicates,
        excluded_noncanonical: canonical.noncanonical,
        excluded_unfinalized: canonical.unfinalized,
    })
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ScanRange {
    pub chain_id: u64,
    pub contract: String,
    pub topic0: String,
    pub first_block: u64,
    pub last_block: u64,
    pub last_block_hash: String,
    pub complete: bool,
    pub finalized: bool,
}
impl ScanRange {
    fn matches(&self, event: &LiquidationObservation) -> bool {
        self.chain_id == event.event_id.chain_id
            && self.contract == event.contract
            && self.topic0 == event.topic0
            && (self.first_block..=self.last_block).contains(&event.block_number)
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ScanManifest {
    pub scan_id: String,
    pub evidence_class: EvidenceClass,
    pub ranges: Vec<ScanRange>,
}
impl ScanManifest {
    pub fn validate(&self) -> Result<()> {
        require(
            nonempty(&self.scan_id) && !self.ranges.is_empty() && self.ranges.len() <= 100_000,
            "invalid_scan",
            "a bounded, explicit scan scope is required",
        )?;
        let mut ranges = self.ranges.iter().collect::<Vec<_>>();
        ranges.sort_by_key(|r| (r.chain_id, &r.contract, &r.topic0, r.first_block));
        for r in &ranges {
            require(
                r.chain_id > 0
                    && hex(&r.contract, 20)
                    && hex(&r.topic0, 32)
                    && hex(&r.last_block_hash, 32)
                    && r.first_block <= r.last_block,
                "invalid_scan",
                "invalid scan range identity or bounds",
            )?;
        }
        for pair in ranges.windows(2) {
            let (a, b) = (pair[0], pair[1]);
            require(
                a.chain_id != b.chain_id
                    || a.contract != b.contract
                    || a.topic0 != b.topic0
                    || a.last_block < b.first_block,
                "overlapping_scan",
                "scan ranges overlap",
            )?;
        }
        Ok(())
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WatchInterval {
    pub mine_id: String,
    pub chain_id: u64,
    pub contract: String,
    pub topic0: String,
    /// First block watched prospectively; registration must precede this block.
    pub first_block: u64,
    pub last_block: Option<u64>,
    pub registered_at_block: u64,
    pub evidence_class: EvidenceClass,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CoverageStatus {
    Complete,
    IncompleteScan,
    NoLiquidations,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BlindspotReason {
    UnregisteredScope,
    DiscoveredLater,
    OutsideWatchInterval,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Blindspot {
    pub event_id: ChainEventId,
    pub mine_id: String,
    pub reason: BlindspotReason,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CoverageReport {
    pub manifest: ScanManifest,
    pub status: CoverageStatus,
    pub total_finalized_liquidations: usize,
    pub watched_when_liquidated: usize,
    /// Undefined for incomplete scans and zero denominators. This is not global coverage.
    pub fraction: Option<f64>,
    pub blindspots: Vec<Blindspot>,
    pub deduplicated: usize,
    pub excluded_noncanonical: usize,
    pub excluded_unfinalized: usize,
}

pub fn coverage(
    manifest: &ScanManifest,
    events: &[LiquidationObservation],
    watches: &[WatchInterval],
) -> Result<CoverageReport> {
    manifest.validate()?;
    for w in watches {
        require(
            nonempty(&w.mine_id)
                && w.chain_id > 0
                && hex(&w.contract, 20)
                && hex(&w.topic0, 32)
                && w.registered_at_block < w.first_block
                && w.last_block.is_none_or(|b| b >= w.first_block),
            "invalid_watch",
            "watch intervals require a prospective start after registration",
        )?;
        require(
            w.evidence_class == manifest.evidence_class,
            "mixed_evidence",
            "watch and scan provenance differ",
        )?;
    }
    for event in events {
        let range = manifest.ranges.iter().find(|r| r.matches(event));
        require(
            range.is_some(),
            "outside_scan",
            "event is outside the declared contract/topic/block scope",
        )?;
        if let Some(r) = range {
            require(
                !event.canonical
                    || event.block_number != r.last_block
                    || event.event_id.block_hash == r.last_block_hash,
                "scan_hash_mismatch",
                "canonical event contradicts the scan end hash",
            )?;
        }
    }
    let canonical = canonical_events(events, manifest.evidence_class)?;
    let complete =
        manifest.ranges.iter().all(|r| r.complete && r.finalized) && canonical.unfinalized == 0;
    let mut watched = 0;
    let mut blindspots = Vec::new();
    for e in &canonical.events {
        let matching: Vec<_> = watches
            .iter()
            .filter(|w| {
                w.mine_id == e.mine_id
                    && w.chain_id == e.event_id.chain_id
                    && w.contract == e.contract
                    && w.topic0 == e.topic0
            })
            .collect();
        if matching.iter().any(|w| {
            w.registered_at_block < e.block_number
                && w.first_block <= e.block_number
                && w.last_block.is_none_or(|b| b >= e.block_number)
        }) {
            watched += 1;
        } else {
            let reason = if matching.is_empty() {
                BlindspotReason::UnregisteredScope
            } else if matching.iter().all(|w| w.first_block > e.block_number) {
                BlindspotReason::DiscoveredLater
            } else {
                BlindspotReason::OutsideWatchInterval
            };
            blindspots.push(Blindspot {
                event_id: e.event_id.clone(),
                mine_id: e.mine_id.clone(),
                reason,
            });
        }
    }
    let count = canonical.events.len();
    let status = if !complete {
        CoverageStatus::IncompleteScan
    } else if count == 0 {
        CoverageStatus::NoLiquidations
    } else {
        CoverageStatus::Complete
    };
    Ok(CoverageReport {
        manifest: manifest.clone(),
        status,
        total_finalized_liquidations: count,
        watched_when_liquidated: watched,
        fraction: if complete && count > 0 {
            Some(watched as f64 / count as f64)
        } else {
            None
        },
        blindspots,
        deduplicated: canonical.duplicates,
        excluded_noncanonical: canonical.noncanonical,
        excluded_unfinalized: canonical.unfinalized,
    })
}

/// All monetary observations use one explicitly named numeraire (USD millionths).
/// Costs describe the modeled strategy at its assumed participation, not all rivals.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DailyEconomics {
    pub day_start_unix: u64,
    pub evidence_class: EvidenceClass,
    pub gross_available_bonus_microusd: u64,
    pub successful_attempt_gas_microusd: u64,
    pub failed_attempt_gas_microusd: u64,
    /// Financing, route slippage and other costs excluding builder payments and gas.
    pub other_execution_cost_microusd: u64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ValuationConfig {
    pub input_class: EvidenceClass,
    pub horizon_days: usize,
    pub scenarios: usize,
    pub bootstrap_block_days: usize,
    pub minimum_history_days: usize,
    pub capture_share: f64,
    /// Additional direct builder share; priority fees already in gas are excluded.
    pub builder_share: f64,
    pub daily_operating_cost_microusd: u64,
    pub adapter_hours: f64,
    pub adapter_hourly_rate_microusd: u64,
    pub setup_compute_cost_microusd: u64,
    pub seed: u64,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ValuationDistribution {
    pub algorithm: String,
    pub input_class: EvidenceClass,
    pub output_is_simulation: bool,
    pub seed: u64,
    pub history_days: usize,
    pub horizon_days: usize,
    pub bootstrap_block_days: usize,
    pub assumed_capture_share: f64,
    pub assumed_builder_share: f64,
    pub scenarios_net_microusd: Vec<f64>,
    pub expected_net_microusd: f64,
    pub p05_net_microusd: f64,
    pub p50_net_microusd: f64,
    pub p95_net_microusd: f64,
    pub lower_tail_mean_5pct_microusd: f64,
    pub probability_net_positive: f64,
    pub effort_cost_microusd: f64,
    /// E[monthly operating net] / (adapter hours * hourly rate + setup compute).
    pub priority_score: f64,
}

fn quantile_sorted(values: &[f64], q: f64) -> f64 {
    let index = q * (values.len() - 1) as f64;
    let lower = index.floor() as usize;
    let upper = index.ceil() as usize;
    values[lower] + (values[upper] - values[lower]) * (index - lower as f64)
}

/// Circular moving-block bootstrap of observed daily economics. This is an
/// explicitly conditional statistical estimate, not an EVM liquidation simulator.
/// Contiguous blocks retain within-block correlations in bonuses and all costs.
pub fn value_month(
    history: &[DailyEconomics],
    cfg: &ValuationConfig,
) -> Result<ValuationDistribution> {
    require(
        cfg.minimum_history_days > 0
            && history.len() >= cfg.minimum_history_days
            && history.len() <= 36_600,
        "insufficient_history",
        "invalid or insufficient daily history",
    )?;
    require(
        (1..=366).contains(&cfg.horizon_days)
            && (1..=100_000).contains(&cfg.scenarios)
            && cfg.scenarios.saturating_mul(cfg.horizon_days) <= 5_000_000
            && cfg.bootstrap_block_days > 0
            && cfg.bootstrap_block_days <= history.len(),
        "invalid_simulation_size",
        "invalid or excessive simulation size",
    )?;
    require(
        fraction(cfg.capture_share)
            && fraction(cfg.builder_share)
            && cfg.adapter_hours.is_finite()
            && cfg.adapter_hours >= 0.0,
        "invalid_assumption",
        "shares and effort must be finite and in range",
    )?;
    const MAX_EXACT: u64 = 1_u64 << 53;
    require(
        cfg.daily_operating_cost_microusd <= MAX_EXACT
            && cfg.adapter_hourly_rate_microusd <= MAX_EXACT
            && cfg.setup_compute_cost_microusd <= MAX_EXACT,
        "amount_too_large",
        "amount exceeds exact integer range of the statistical model",
    )?;
    let effort = cfg.adapter_hours * cfg.adapter_hourly_rate_microusd as f64
        + cfg.setup_compute_cost_microusd as f64;
    require(
        effort.is_finite() && effort > 0.0,
        "zero_effort_cost",
        "priority denominator must be a positive cost in USD millionths",
    )?;
    let mut daily_net = Vec::with_capacity(history.len());
    for (index, day) in history.iter().enumerate() {
        require(
            day.evidence_class == cfg.input_class,
            "mixed_evidence",
            "valuation history mixes evidence classes",
        )?;
        require(
            day.day_start_unix % 86_400 == 0,
            "invalid_day",
            "history dates must be UTC day boundaries",
        )?;
        if index > 0 {
            require(
                history[index - 1].day_start_unix.checked_add(86_400) == Some(day.day_start_unix),
                "noncontiguous_history",
                "history must be unique, chronological and contiguous; unknown days are not zeros",
            )?;
        }
        require(
            [
                day.gross_available_bonus_microusd,
                day.successful_attempt_gas_microusd,
                day.failed_attempt_gas_microusd,
                day.other_execution_cost_microusd,
            ]
            .iter()
            .all(|v| *v <= MAX_EXACT),
            "amount_too_large",
            "daily amount exceeds exact statistical input range",
        )?;
        let net = day.gross_available_bonus_microusd as f64
            * cfg.capture_share
            * (1.0 - cfg.builder_share)
            - day.successful_attempt_gas_microusd as f64
            - day.failed_attempt_gas_microusd as f64
            - day.other_execution_cost_microusd as f64
            - cfg.daily_operating_cost_microusd as f64;
        require(net.is_finite(), "nonfinite_net", "nonfinite daily result")?;
        daily_net.push(net);
    }
    let mut rng = ChaCha8Rng::seed_from_u64(cfg.seed);
    let mut samples = Vec::with_capacity(cfg.scenarios);
    for _ in 0..cfg.scenarios {
        let mut net = 0.0;
        let mut remaining = cfg.horizon_days;
        while remaining > 0 {
            let start = rng.gen_range(0..history.len());
            let block_days = cfg.bootstrap_block_days.min(remaining);
            for day in 0..block_days {
                net += daily_net[(start + day) % history.len()];
            }
            remaining -= block_days;
        }
        require(
            net.is_finite(),
            "nonfinite_net",
            "nonfinite scenario result",
        )?;
        samples.push(net);
    }
    let mut sorted = samples.clone();
    sorted.sort_by(f64::total_cmp);
    let expected = samples.iter().sum::<f64>() / samples.len() as f64;
    let tail_count = ((sorted.len() as f64 * 0.05).ceil() as usize).max(1);
    let score = expected / effort;
    require(
        score.is_finite(),
        "nonfinite_score",
        "priority score exceeds the finite statistical range",
    )?;
    Ok(ValuationDistribution {
        algorithm: "circular_daily_economics_block_bootstrap_v1_chacha8".into(),
        input_class: cfg.input_class,
        output_is_simulation: true,
        seed: cfg.seed,
        history_days: history.len(),
        horizon_days: cfg.horizon_days,
        bootstrap_block_days: cfg.bootstrap_block_days,
        assumed_capture_share: cfg.capture_share,
        assumed_builder_share: cfg.builder_share,
        expected_net_microusd: expected,
        p05_net_microusd: quantile_sorted(&sorted, 0.05),
        p50_net_microusd: quantile_sorted(&sorted, 0.50),
        p95_net_microusd: quantile_sorted(&sorted, 0.95),
        lower_tail_mean_5pct_microusd: sorted[..tail_count].iter().sum::<f64>() / tail_count as f64,
        probability_net_positive: samples.iter().filter(|x| **x > 0.0).count() as f64
            / samples.len() as f64,
        effort_cost_microusd: effort,
        priority_score: score,
        scenarios_net_microusd: samples,
    })
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RivalConfig {
    pub chain_id: u64,
    pub mine_id: String,
    pub evidence_class: EvidenceClass,
    /// Per-observation changepoint probability, not a per-block probability.
    pub hazard: f64,
    pub prior_alpha: f64,
    pub prior_beta: f64,
    pub alarm_probability: f64,
    pub minimum_samples: usize,
    pub max_hypotheses: usize,
}
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CompetitionSample {
    pub sample_id: String,
    pub chain_id: u64,
    pub mine_id: String,
    pub block_number: u64,
    pub block_hash: String,
    pub canonical: bool,
    pub finalized: bool,
    pub evidence_class: EvidenceClass,
    /// Derived by a separately versioned, complete saturation measurement.
    pub elevated_competition: bool,
    pub liquidators: Vec<String>,
}
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RivalSignal {
    pub sample_id: String,
    pub chain_id: u64,
    pub mine_id: String,
    pub evidence_class: EvidenceClass,
    pub sample_count: usize,
    pub changepoint_probability: f64,
    pub probability_discarded_by_pruning: f64,
    pub new_liquidators: Vec<String>,
    pub regime_alarm: bool,
    pub request_revaluation: bool,
}
#[derive(Clone, Debug)]
struct RunHypothesis {
    length: u64,
    alpha: f64,
    beta: f64,
    probability: f64,
}

/// Beta-Bernoulli Bayesian run-length mixture. A change occurs before the new
/// observation, whose likelihood under the reset state uses the prior predictive.
/// Pruning bounds memory; discarded mass is exposed in every result.
#[derive(Clone, Debug)]
pub struct RivalMonitor {
    config: RivalConfig,
    hypotheses: Vec<RunHypothesis>,
    liquidators: BTreeSet<String>,
    sample_count: usize,
    sample_ids: BTreeSet<String>,
    block_hashes: BTreeSet<String>,
    last: Option<(CompetitionSample, RivalSignal)>,
}
impl RivalMonitor {
    pub fn new(config: RivalConfig) -> Result<Self> {
        require(
            config.chain_id > 0 && nonempty(&config.mine_id),
            "invalid_rival_config",
            "invalid mine identity",
        )?;
        require(
            config.hazard.is_finite()
                && config.hazard > 0.0
                && config.hazard < 1.0
                && config.alarm_probability.is_finite()
                && config.alarm_probability > 0.0
                && config.alarm_probability <= 1.0
                && config.prior_alpha.is_finite()
                && (0.000_001..=1_000_000.0).contains(&config.prior_alpha)
                && config.prior_beta.is_finite()
                && (0.000_001..=1_000_000.0).contains(&config.prior_beta)
                && config.minimum_samples >= 2
                && (2..=512).contains(&config.max_hypotheses),
            "invalid_rival_config",
            "invalid Bayesian parameters or limits",
        )?;
        Ok(Self {
            config,
            hypotheses: Vec::new(),
            liquidators: BTreeSet::new(),
            sample_count: 0,
            sample_ids: BTreeSet::new(),
            block_hashes: BTreeSet::new(),
            last: None,
        })
    }
    /// Any canonicality break invalidates the model. Rebuild from the canonical journal.
    pub fn reset_after_reorg(&mut self) {
        self.hypotheses.clear();
        self.liquidators.clear();
        self.sample_count = 0;
        self.last = None;
        self.sample_ids.clear();
        self.block_hashes.clear();
    }
    pub fn update(&mut self, sample: &CompetitionSample) -> Result<RivalSignal> {
        require(
            sample.chain_id == self.config.chain_id
                && sample.mine_id == self.config.mine_id
                && sample.evidence_class == self.config.evidence_class,
            "mixed_rival_scope",
            "rival sample scope or provenance differs",
        )?;
        require(
            nonempty(&sample.sample_id)
                && hex(&sample.block_hash, 32)
                && sample.canonical
                && sample.finalized,
            "unconfirmed_sample",
            "rival samples must be identified, canonical and finalized",
        )?;
        require(
            sample.liquidators.iter().all(|a| hex(a, 20)),
            "invalid_liquidator",
            "invalid liquidator address",
        )?;
        if let Some((prior, signal)) = &self.last {
            if prior == sample {
                return Ok(signal.clone());
            }
            require(
                sample.sample_id != prior.sample_id && sample.block_number > prior.block_number,
                "nonmonotonic_sample",
                "duplicate, conflicting or out-of-order rival sample",
            )?;
        }
        require(
            !self.sample_ids.contains(&sample.sample_id)
                && !self.block_hashes.contains(&sample.block_hash),
            "reused_sample_identity",
            "sample identity or block hash was already processed",
        )?;
        require(
            self.sample_count < 100_000,
            "rival_capacity",
            "bounded rival history requires archival before this limit",
        )?;
        let addresses: BTreeSet<_> = sample.liquidators.iter().cloned().collect();
        let new: Vec<_> = if self.sample_count == 0 {
            Vec::new()
        } else {
            addresses.difference(&self.liquidators).cloned().collect()
        };
        require(
            self.liquidators.union(&addresses).count() <= 100_000,
            "rival_capacity",
            "rival history requires archival and replay before this limit",
        )?;
        let x = if sample.elevated_competition {
            1.0
        } else {
            0.0
        };
        let mut next = Vec::with_capacity(self.hypotheses.len() + 1);
        if self.hypotheses.is_empty() {
            next.push(RunHypothesis {
                length: 1,
                alpha: self.config.prior_alpha + x,
                beta: self.config.prior_beta + 1.0 - x,
                probability: 1.0,
            });
        } else {
            let prior_p = if x == 1.0 {
                self.config.prior_alpha
            } else {
                self.config.prior_beta
            } / (self.config.prior_alpha + self.config.prior_beta);
            next.push(RunHypothesis {
                length: 1,
                alpha: self.config.prior_alpha + x,
                beta: self.config.prior_beta + 1.0 - x,
                probability: self.config.hazard * prior_p,
            });
            for h in &self.hypotheses {
                let p = if x == 1.0 { h.alpha } else { h.beta } / (h.alpha + h.beta);
                next.push(RunHypothesis {
                    length: h
                        .length
                        .checked_add(1)
                        .ok_or_else(|| fail("counter_overflow", "rival run length"))?,
                    alpha: h.alpha + x,
                    beta: h.beta + 1.0 - x,
                    probability: h.probability * (1.0 - self.config.hazard) * p,
                });
            }
        }
        let normalization: f64 = next.iter().map(|h| h.probability).sum();
        require(
            normalization.is_finite() && normalization > 0.0,
            "invalid_posterior",
            "Bayesian posterior underflow or nonfinite value",
        )?;
        for h in &mut next {
            h.probability /= normalization;
        }
        let probability = if self.sample_count == 0 {
            0.0
        } else {
            next[0].probability
        };
        next.sort_by(|a, b| {
            b.probability
                .total_cmp(&a.probability)
                .then(a.length.cmp(&b.length))
        });
        let discarded: f64 = next
            .iter()
            .skip(self.config.max_hypotheses)
            .map(|h| h.probability)
            .sum();
        next.truncate(self.config.max_hypotheses);
        let retained: f64 = next.iter().map(|h| h.probability).sum();
        for h in &mut next {
            h.probability /= retained;
        }
        let count = self
            .sample_count
            .checked_add(1)
            .ok_or_else(|| fail("counter_overflow", "rival sample count"))?;
        let alarm = count >= self.config.minimum_samples
            && sample.elevated_competition
            && probability >= self.config.alarm_probability;
        let signal = RivalSignal {
            sample_id: sample.sample_id.clone(),
            chain_id: sample.chain_id,
            mine_id: sample.mine_id.clone(),
            evidence_class: sample.evidence_class,
            sample_count: count,
            changepoint_probability: probability,
            probability_discarded_by_pruning: discarded,
            request_revaluation: alarm || !new.is_empty(),
            new_liquidators: new,
            regime_alarm: alarm,
        };
        self.hypotheses = next;
        self.sample_count = count;
        self.liquidators.extend(addresses);
        self.sample_ids.insert(sample.sample_id.clone());
        self.block_hashes.insert(sample.block_hash.clone());
        self.last = Some((sample.clone(), signal.clone()));
        Ok(signal)
    }
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResearchArm {
    pub mine_id: String,
    pub request_cost_units: u64,
    pub eligible: bool,
    pub prior_alpha: f64,
    pub prior_beta: f64,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResearchBudget {
    pub total_units: u64,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RealizedOutcome {
    pub outcome_id: String,
    pub mine_id: String,
    pub settlement_event: ChainEventId,
    pub evidence_class: EvidenceClass,
    pub canonical: bool,
    pub finalized: bool,
    pub net_microusd: i64,
    /// Content hash or receipt-proof identity verified outside this estimator.
    pub verification_reference: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RecordOutcome {
    Applied,
    AlreadyApplied,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ArmPosterior {
    pub mine_id: String,
    pub alpha: f64,
    pub beta: f64,
    pub realized_observations: usize,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResearchAllocation {
    pub mine_id: String,
    pub units: u64,
    pub sampled_profit_probability: f64,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AllocationPlan {
    pub algorithm: String,
    pub seed: u64,
    pub budget_units: u64,
    pub total_units: u64,
    pub unallocated_units: u64,
    pub allocations: Vec<ResearchAllocation>,
    pub authorizes_spending: bool,
}

/// Pure allocation of research quanta. No wallets, execution budgets, signing or
/// outbound actions. A caller must separately enforce a real resource reservation.
#[derive(Clone, Debug)]
pub struct ThompsonBandit {
    arms: BTreeMap<String, ResearchArm>,
    outcomes: BTreeMap<(u64, String, u32), RealizedOutcome>,
    outcome_ids: BTreeMap<String, (u64, String, u32)>,
}
impl ThompsonBandit {
    pub fn new(arms: Vec<ResearchArm>) -> Result<Self> {
        require(
            !arms.is_empty() && arms.len() <= 100_000,
            "invalid_arms",
            "one to 100000 unique research arms are required",
        )?;
        let mut map = BTreeMap::new();
        for arm in arms {
            require(
                nonempty(&arm.mine_id)
                    && arm.request_cost_units > 0
                    && arm.prior_alpha.is_finite()
                    && (0.000_001..=1_000_000.0).contains(&arm.prior_alpha)
                    && arm.prior_beta.is_finite()
                    && (0.000_001..=1_000_000.0).contains(&arm.prior_beta),
                "invalid_arm",
                "invalid arm identity, cost or Beta prior",
            )?;
            require(
                !map.contains_key(&arm.mine_id),
                "duplicate_arm",
                "arm IDs must be unique",
            )?;
            map.insert(arm.mine_id.clone(), arm);
        }
        Ok(Self {
            arms: map,
            outcomes: BTreeMap::new(),
            outcome_ids: BTreeMap::new(),
        })
    }
    pub fn record_realized(&mut self, outcome: RealizedOutcome) -> Result<RecordOutcome> {
        outcome.settlement_event.validate()?;
        require(
            nonempty(&outcome.outcome_id)
                && nonempty(&outcome.verification_reference)
                && self.arms.contains_key(&outcome.mine_id),
            "invalid_outcome",
            "unknown mine or missing evidence identity",
        )?;
        require(
            outcome.evidence_class == EvidenceClass::Realized
                && outcome.canonical
                && outcome.finalized,
            "not_realized",
            "only canonical, finalized, realized net outcomes update the bandit",
        )?;
        let key = outcome.settlement_event.logical_key();
        if let Some(previous) = self.outcomes.get(&key) {
            require(
                previous == &outcome,
                "conflicting_outcome",
                "settlement event has conflicting outcomes",
            )?;
            return Ok(RecordOutcome::AlreadyApplied);
        }
        require(
            !self.outcome_ids.contains_key(&outcome.outcome_id),
            "reused_outcome_id",
            "outcome ID was already used",
        )?;
        require(
            self.outcomes.len() < 1_000_000,
            "outcome_capacity",
            "bounded outcome history requires archival before this limit",
        )?;
        self.outcome_ids
            .insert(outcome.outcome_id.clone(), key.clone());
        self.outcomes.insert(key, outcome);
        Ok(RecordOutcome::Applied)
    }
    /// Finality can fail. Removing the orphaned block restores the exact prior
    /// contribution because posteriors are derived from retained settlement facts.
    pub fn retract_block(&mut self, chain_id: u64, block_hash: &str) -> Result<usize> {
        require(
            chain_id > 0 && hex(block_hash, 32),
            "invalid_reorg",
            "invalid reorg identity",
        )?;
        let remove: Vec<_> = self
            .outcomes
            .iter()
            .filter(|(_, o)| {
                o.settlement_event.chain_id == chain_id
                    && o.settlement_event.block_hash == block_hash
            })
            .map(|(key, o)| (key.clone(), o.outcome_id.clone()))
            .collect();
        for (key, id) in &remove {
            self.outcomes.remove(key);
            self.outcome_ids.remove(id);
        }
        Ok(remove.len())
    }
    pub fn posteriors(&self) -> Vec<ArmPosterior> {
        let mut result: BTreeMap<_, _> = self
            .arms
            .iter()
            .map(|(id, arm)| {
                (
                    id.clone(),
                    ArmPosterior {
                        mine_id: id.clone(),
                        alpha: arm.prior_alpha,
                        beta: arm.prior_beta,
                        realized_observations: 0,
                    },
                )
            })
            .collect();
        for outcome in self.outcomes.values() {
            if let Some(arm) = result.get_mut(&outcome.mine_id) {
                if outcome.net_microusd > 0 {
                    arm.alpha += 1.0;
                } else {
                    arm.beta += 1.0;
                }
                arm.realized_observations += 1;
            }
        }
        result.into_values().collect()
    }
    /// One indivisible research request per eligible mine per cycle, ordered by
    /// independent Thompson samples. Unaffordable requests are skipped, never split.
    pub fn allocate(&self, budget: ResearchBudget, seed: u64) -> Result<AllocationPlan> {
        let mut rng = ChaCha8Rng::seed_from_u64(seed);
        let mut candidates = Vec::new();
        for posterior in self.posteriors() {
            let arm = &self.arms[&posterior.mine_id];
            if !arm.eligible || arm.request_cost_units > budget.total_units {
                continue;
            }
            let beta = Beta::new(posterior.alpha, posterior.beta)
                .map_err(|_| fail("invalid_posterior", "invalid Beta posterior"))?;
            let probability = beta.sample(&mut rng);
            require(
                fraction(probability),
                "invalid_sample",
                "invalid Thompson sample",
            )?;
            candidates.push(ResearchAllocation {
                mine_id: arm.mine_id.clone(),
                units: arm.request_cost_units,
                sampled_profit_probability: probability,
            });
        }
        candidates.sort_by(|a, b| {
            b.sampled_profit_probability
                .total_cmp(&a.sampled_profit_probability)
                .then(a.mine_id.cmp(&b.mine_id))
        });
        let mut remaining = budget.total_units;
        let mut allocations = Vec::new();
        for item in candidates {
            if item.units <= remaining {
                remaining -= item.units;
                allocations.push(item);
            }
        }
        Ok(AllocationPlan {
            algorithm: "beta_bernoulli_research_quanta_thompson_v1_chacha8".into(),
            seed,
            budget_units: budget.total_units,
            total_units: budget.total_units - remaining,
            unallocated_units: remaining,
            allocations,
            authorizes_spending: false,
        })
    }
}
