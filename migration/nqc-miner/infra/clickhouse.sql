-- PREPARED CONTRACT ONLY. No ClickHouse server was started or contacted.
-- Names are fully qualified; apply to a NEW dedicated nqc_miner_v1 database.
CREATE DATABASE nqc_miner_v1;

-- Append-only audit log retains every delivery, including identical retries.
-- Import only immutable journals that the Rust verifier has accepted. A hash is
-- integrity evidence, not independent chain authenticity.
CREATE TABLE nqc_miner_v1.raw_ledger
(
    namespace LowCardinality(String) DEFAULT 'nqc_miner_v1',
    producer LowCardinality(String) DEFAULT 'nqc-miner',
    run_id String,
    data_class LowCardinality(String),
    owner_sha256 FixedString(64),
    config_sha256 FixedString(64),
    code_commit FixedString(40),
    cargo_lock_sha256 FixedString(64),
    sequence UInt64,
    previous_sha256 FixedString(64),
    envelope_sha256 FixedString(64),
    raw_line_sha256 FixedString(64),
    record_kind LowCardinality(String),
    raw_line String,
    imported_at DateTime64(3, 'UTC'),
    CONSTRAINT owned CHECK (namespace = 'nqc_miner_v1' AND producer = 'nqc-miner'),
    CONSTRAINT known_class CHECK (data_class IN ('synthetic', 'historical', 'shadow')),
    CONSTRAINT bounded_run CHECK (match(run_id, '^[a-z0-9_-]{1,96}$')),
    CONSTRAINT known_kind CHECK (record_kind IN ('observed', 'chunk_completed', 'scope_completed', 'invalidated')),
    CONSTRAINT bounded_line CHECK (length(raw_line) BETWEEN 1 AND 1048577)
)
ENGINE = MergeTree
PARTITION BY (data_class, cityHash64(run_id) % 16)
ORDER BY (run_id, data_class, sequence, envelope_sha256, raw_line_sha256);

-- Conflicting contents at a sequence or multiple owners for a run quarantine
-- the entire run. Identical redelivery is allowed and does not change counts.
CREATE VIEW nqc_miner_v1.conflicted_runs AS
SELECT run_id, data_class
FROM
(
    SELECT run_id, data_class, sequence
    FROM nqc_miner_v1.raw_ledger
    GROUP BY run_id, data_class, sequence
    HAVING uniqExact(envelope_sha256) != 1 OR uniqExact(raw_line_sha256) != 1
    UNION ALL
    SELECT run_id, data_class, toUInt64(0) AS sequence
    FROM nqc_miner_v1.raw_ledger
    GROUP BY run_id, data_class
    HAVING uniqExact(owner_sha256) != 1 OR uniqExact(config_sha256) != 1
        OR uniqExact(code_commit) != 1 OR uniqExact(cargo_lock_sha256) != 1
)
GROUP BY run_id, data_class;

CREATE VIEW nqc_miner_v1.verified_envelopes AS
SELECT run_id, data_class, sequence, any(owner_sha256) AS owner_sha256,
       any(envelope_sha256) AS envelope_sha256, any(record_kind) AS record_kind,
       any(raw_line) AS raw_line
FROM nqc_miner_v1.raw_ledger
WHERE (run_id, data_class) NOT IN (SELECT run_id, data_class FROM nqc_miner_v1.conflicted_runs)
GROUP BY run_id, data_class, sequence;

-- Projections are inserted only by the future verified importer. A projector
-- must reject different projection bytes for one envelope_sha256. FINAL is used
-- below because background ReplacingMergeTree merges are not a correctness gate.
CREATE TABLE nqc_miner_v1.event_versions
(
    namespace LowCardinality(String) DEFAULT 'nqc_miner_v1',
    run_id String,
    data_class LowCardinality(String),
    sequence UInt64,
    envelope_sha256 FixedString(64),
    scope_id String,
    chain_id UInt64,
    contract FixedString(42),
    topic0 FixedString(66),
    block_number UInt64,
    block_hash FixedString(66),
    transaction_hash FixedString(66),
    log_index UInt32,
    protocol LowCardinality(String),
    market_id String,
    event_kind LowCardinality(String),
    liquidator Nullable(FixedString(42)),
    block_timestamp UInt64,
    observed_at UInt64,
    decoded_json String,
    -- No amount is converted to float/USD and no realized P&L is inferred here.
    CONSTRAINT owned CHECK (namespace = 'nqc_miner_v1'),
    CONSTRAINT known_class CHECK (data_class IN ('synthetic', 'historical', 'shadow')),
    CONSTRAINT known_event CHECK (event_kind IN ('birth', 'liquidation')),
    CONSTRAINT known_liquidator CHECK ((event_kind = 'birth' AND isNull(liquidator)) OR
        (event_kind = 'liquidation' AND isNotNull(liquidator) AND match(ifNull(liquidator, ''), '^0x[0-9a-f]{40}$'))),
    CONSTRAINT known_protocol CHECK (protocol IN ('morpho-blue', 'aave-v3', 'aave-v3-configurator')),
    CONSTRAINT valid_chain CHECK (chain_id > 0),
    CONSTRAINT no_future_observation CHECK (observed_at >= block_timestamp)
)
ENGINE = ReplacingMergeTree(sequence)
PARTITION BY (data_class, cityHash64(run_id) % 16)
ORDER BY (run_id, data_class, scope_id, chain_id, block_hash, log_index);

CREATE TABLE nqc_miner_v1.scope_completions
(
    namespace LowCardinality(String) DEFAULT 'nqc_miner_v1',
    run_id String,
    data_class LowCardinality(String),
    sequence UInt64,
    envelope_sha256 FixedString(64),
    scope_id String,
    chain_id UInt64,
    from_block UInt64,
    to_block UInt64,
    finalized_anchor_number UInt64,
    finalized_anchor_hash FixedString(66),
    observed_at UInt64,
    providers Array(String),
    CONSTRAINT owned CHECK (namespace = 'nqc_miner_v1'),
    CONSTRAINT known_class CHECK (data_class IN ('synthetic', 'historical', 'shadow')),
    CONSTRAINT valid_range CHECK (chain_id > 0 AND from_block <= to_block AND finalized_anchor_number >= to_block),
    CONSTRAINT provider_agreement CHECK (length(arrayDistinct(providers)) >= 2)
)
ENGINE = ReplacingMergeTree(sequence)
PARTITION BY (data_class, cityHash64(run_id) % 16)
ORDER BY (run_id, data_class, scope_id, chain_id);

-- A publication barrier is written LAST after full immutable snapshot import,
-- exact raw verification and projection checks. A new raw sequence immediately
-- makes an older barrier ineligible, including during partial multi-table writes.
CREATE TABLE nqc_miner_v1.run_publications
(
    namespace LowCardinality(String) DEFAULT 'nqc_miner_v1',
    run_id String,
    data_class LowCardinality(String),
    owner_sha256 FixedString(64),
    record_count UInt64,
    last_sequence UInt64,
    last_envelope_sha256 FixedString(64),
    source_journal_sha256 FixedString(64),
    verifier_sha256 FixedString(64),
    verification_summary_sha256 FixedString(64),
    published_at DateTime64(3, 'UTC'),
    CONSTRAINT owned CHECK (namespace = 'nqc_miner_v1'),
    CONSTRAINT known_class CHECK (data_class IN ('synthetic', 'historical', 'shadow')),
    CONSTRAINT bounded_snapshot CHECK (record_count BETWEEN 1 AND 1000000 AND last_sequence = record_count - 1)
)
ENGINE = ReplacingMergeTree(last_sequence)
PARTITION BY (data_class, cityHash64(run_id) % 16)
ORDER BY (run_id, data_class);

CREATE VIEW nqc_miner_v1.projection_gaps AS
SELECT r.run_id, r.data_class
FROM nqc_miner_v1.verified_envelopes AS r
WHERE (r.record_kind = 'observed' AND (r.run_id, r.data_class, r.sequence, r.envelope_sha256) NOT IN
       (SELECT run_id, data_class, sequence, envelope_sha256 FROM nqc_miner_v1.event_versions FINAL))
   OR (r.record_kind = 'scope_completed' AND (r.run_id, r.data_class, r.sequence, r.envelope_sha256) NOT IN
       (SELECT run_id, data_class, sequence, envelope_sha256 FROM nqc_miner_v1.scope_completions FINAL))
GROUP BY r.run_id, r.data_class;

CREATE VIEW nqc_miner_v1.published_runs AS
SELECT p.run_id, p.data_class, p.owner_sha256, p.record_count,
       p.last_sequence, p.last_envelope_sha256, p.source_journal_sha256
FROM (SELECT * FROM nqc_miner_v1.run_publications FINAL) AS p
INNER JOIN
(
    SELECT run_id, data_class, any(owner_sha256) AS owner_sha256,
           count() AS records, min(sequence) AS first_sequence, max(sequence) AS last_sequence,
           argMax(envelope_sha256, sequence) AS last_envelope_sha256,
           countIf(record_kind = 'observed') AS observed_records,
           countIf(record_kind = 'scope_completed') AS completed_records
    FROM nqc_miner_v1.verified_envelopes
    GROUP BY run_id, data_class
) AS r ON p.run_id = r.run_id AND p.data_class = r.data_class
LEFT JOIN
(
    SELECT run_id, data_class, count() AS projected_events
    FROM nqc_miner_v1.event_versions FINAL GROUP BY run_id, data_class
) AS e ON p.run_id = e.run_id AND p.data_class = e.data_class
LEFT JOIN
(
    SELECT run_id, data_class, count() AS projected_scopes
    FROM nqc_miner_v1.scope_completions FINAL GROUP BY run_id, data_class
) AS s ON p.run_id = s.run_id AND p.data_class = s.data_class
WHERE r.owner_sha256 = p.owner_sha256 AND r.records = p.record_count
    AND r.first_sequence = 0 AND r.last_sequence = p.last_sequence
    AND r.last_envelope_sha256 = p.last_envelope_sha256
    AND r.observed_records = ifNull(e.projected_events, 0)
    AND r.completed_records = ifNull(s.projected_scopes, 0)
    AND (p.run_id, p.data_class) NOT IN
        (SELECT run_id, data_class FROM nqc_miner_v1.projection_gaps);

-- Read invalidations straight from verified original bytes, never from a lagging
-- projection. Any newly received invalidation also blocks the old publication.
CREATE VIEW nqc_miner_v1.invalidation_cutoffs AS
SELECT run_id, data_class, JSONExtractUInt(raw_line, 'record', 'chain_id') AS chain_id,
       min(JSONExtractUInt(raw_line, 'record', 'from_block')) AS from_block
FROM nqc_miner_v1.verified_envelopes
WHERE record_kind = 'invalidated'
GROUP BY run_id, data_class, chain_id;

CREATE VIEW nqc_miner_v1.completed_scopes AS
SELECT s.*
FROM (SELECT * FROM nqc_miner_v1.scope_completions FINAL) AS s
INNER JOIN nqc_miner_v1.published_runs AS p
    ON s.run_id = p.run_id AND s.data_class = p.data_class
INNER JOIN nqc_miner_v1.verified_envelopes AS r
    ON s.run_id = r.run_id AND s.data_class = r.data_class
    AND s.sequence = r.sequence AND s.envelope_sha256 = r.envelope_sha256
WHERE r.record_kind = 'scope_completed'
    -- Invalidate the whole coverage claim if any part of its range is affected.
    AND (s.run_id, s.data_class, s.scope_id, s.chain_id) NOT IN
    (
        SELECT t.run_id, t.data_class, t.scope_id, t.chain_id
        FROM (SELECT * FROM nqc_miner_v1.scope_completions FINAL) AS t
        INNER JOIN nqc_miner_v1.invalidation_cutoffs AS i
            ON t.run_id = i.run_id AND t.data_class = i.data_class AND t.chain_id = i.chain_id
        WHERE t.to_block >= i.from_block
    );

CREATE VIEW nqc_miner_v1.finalized_events AS
SELECT e.*
FROM (SELECT * FROM nqc_miner_v1.event_versions FINAL) AS e
INNER JOIN nqc_miner_v1.verified_envelopes AS r
    ON e.run_id = r.run_id AND e.data_class = r.data_class
    AND e.sequence = r.sequence AND e.envelope_sha256 = r.envelope_sha256
INNER JOIN nqc_miner_v1.completed_scopes AS s
    ON e.run_id = s.run_id AND e.data_class = s.data_class
    AND e.scope_id = s.scope_id AND e.chain_id = s.chain_id
WHERE r.record_kind = 'observed' AND e.block_number BETWEEN s.from_block AND s.to_block;

-- Dynamic view, never an additive insert-trigger aggregate. A late invalidation
-- removes affected scope rows at query time. Replaying deliveries cannot inflate
-- uniqExact. All grouping dimensions remain explicit; no global coverage claim.
CREATE VIEW nqc_miner_v1.saturation_scoped AS
SELECT run_id, data_class, scope_id, chain_id, contract, topic0, protocol, market_id,
       uniqExactIf(tuple(block_hash, log_index), event_kind = 'liquidation') AS liquidation_events,
       uniqExactIf(transaction_hash, event_kind = 'liquidation') AS liquidation_transactions,
       uniqExactIf(liquidator, event_kind = 'liquidation') AS unique_liquidator_addresses,
       min(block_number) AS first_observed_event_block,
       max(block_number) AS last_observed_event_block,
       CAST(NULL, 'Nullable(Float64)') AS median_capture_delay_seconds,
       CAST(NULL, 'Nullable(Float64)') AS median_priority_fee_wei,
       'uncalibrated' AS saturation_classification
FROM nqc_miner_v1.finalized_events
GROUP BY run_id, data_class, scope_id, chain_id, contract, topic0, protocol, market_id;

-- Zero-event completed scopes remain visible here. Saturation rows alone must
-- never be used to fabricate a denominator or classify a zero-event mine virgin.
CREATE VIEW nqc_miner_v1.coverage_ranges AS
SELECT run_id, data_class, scope_id, chain_id, from_block, to_block,
       finalized_anchor_number, finalized_anchor_hash, providers
FROM nqc_miner_v1.completed_scopes;
