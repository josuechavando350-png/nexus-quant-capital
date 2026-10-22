-- PREPARED CONTRACT ONLY. Not applied to any database.
-- Apply only to a NEW dedicated database and dedicated owner role after review.
-- No CREATE DATABASE/ROLE, connection URL, credential, trigger or external I/O.
BEGIN;

DO $$
BEGIN
    IF current_database() <> 'nqc_miner_v1' THEN
        RAISE EXCEPTION 'Refusing foreign database: expected nqc_miner_v1';
    END IF;
END;
$$;

-- Deliberately no IF NOT EXISTS: an existing installation requires a migration.
CREATE SCHEMA nqc_miner_v1;
REVOKE ALL ON SCHEMA nqc_miner_v1 FROM PUBLIC;
SET LOCAL search_path = nqc_miner_v1, pg_catalog;

CREATE TABLE nqc_miner_v1.runs (
    run_id text PRIMARY KEY CHECK (run_id ~ '^[a-z0-9_-]{1,96}$'),
    namespace text NOT NULL DEFAULT 'nqc_miner_v1' CHECK (namespace = 'nqc_miner_v1'),
    producer text NOT NULL DEFAULT 'nqc-miner' CHECK (producer = 'nqc-miner'),
    data_class text NOT NULL CHECK (data_class IN ('synthetic', 'historical', 'shadow')),
    owner_sha256 text NOT NULL CHECK (owner_sha256 ~ '^[0-9a-f]{64}$'),
    config_sha256 text NOT NULL CHECK (config_sha256 ~ '^[0-9a-f]{64}$'),
    code_commit text NOT NULL CHECK (code_commit ~ '^[0-9a-f]{40}$'),
    cargo_lock_sha256 text NOT NULL CHECK (cargo_lock_sha256 ~ '^[0-9a-f]{64}$'),
    original_owner bytea NOT NULL CHECK (octet_length(original_owner) BETWEEN 1 AND 65536),
    original_config bytea NOT NULL CHECK (octet_length(original_config) BETWEEN 1 AND 1048576),
    created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
    observer_bridge_enabled boolean NOT NULL DEFAULT false CHECK (NOT observer_bridge_enabled),
    signing_enabled boolean NOT NULL DEFAULT false CHECK (NOT signing_enabled),
    telegram_enabled boolean NOT NULL DEFAULT false CHECK (NOT telegram_enabled),
    kms_enabled boolean NOT NULL DEFAULT false CHECK (NOT kms_enabled),
    gas_budget_mxn_centavos bigint NOT NULL DEFAULT 0 CHECK (gas_budget_mxn_centavos = 0),
    UNIQUE (run_id, data_class, owner_sha256)
);

-- Append-only verified journal mirror. The Rust verifier validates hash chains,
-- exact ABI decode, scope coverage and marker order before this transaction.
CREATE TABLE nqc_miner_v1.journal_ledger (
    run_id text NOT NULL,
    data_class text NOT NULL,
    owner_sha256 text NOT NULL,
    sequence numeric(20, 0) NOT NULL CHECK (sequence >= 0 AND sequence <= 18446744073709551615),
    previous_sha256 text NOT NULL CHECK (previous_sha256 ~ '^[0-9a-f]{64}$'),
    envelope_sha256 text NOT NULL CHECK (envelope_sha256 ~ '^[0-9a-f]{64}$'),
    raw_line_sha256 text NOT NULL CHECK (raw_line_sha256 ~ '^[0-9a-f]{64}$'),
    record_kind text NOT NULL CHECK (record_kind IN ('observed', 'chunk_completed', 'scope_completed', 'invalidated')),
    raw_line bytea NOT NULL CHECK (octet_length(raw_line) BETWEEN 1 AND 1048577),
    imported_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
    PRIMARY KEY (run_id, sequence),
    UNIQUE (run_id, data_class, sequence, envelope_sha256),
    FOREIGN KEY (run_id, data_class, owner_sha256)
        REFERENCES nqc_miner_v1.runs (run_id, data_class, owner_sha256)
);

-- Duplicate delivery is a no-op ONLY after comparing all original bytes and
-- hashes against the existing row. Different content for an existing key is an
-- integrity error that quarantines the run. Never unconditional DO NOTHING.
CREATE TABLE nqc_miner_v1.mine_registry (
    mine_id text NOT NULL CHECK (mine_id ~ '^[A-Za-z0-9_:./-]{1,128}$'),
    run_id text NOT NULL,
    data_class text NOT NULL,
    owner_sha256 text NOT NULL,
    chain_id numeric(20, 0) NOT NULL CHECK (chain_id > 0 AND chain_id <= 18446744073709551615),
    contract text NOT NULL CHECK (contract ~ '^0x[0-9a-f]{40}$'),
    scope_id text NOT NULL CHECK (length(scope_id) BETWEEN 1 AND 96),
    protocol text NOT NULL CHECK (protocol IN ('morpho-blue', 'aave-v3', 'aave-v3-configurator')),
    adapter_sha256 text CHECK (adapter_sha256 ~ '^[0-9a-f]{64}$'),
    lifecycle_state text NOT NULL DEFAULT 'detected' CHECK (lifecycle_state IN
        ('detected', 'classified', 'valued', 'wind_tunnel', 'shadow', 'proposed', 'retired')),
    registered_at_block numeric(20, 0) NOT NULL CHECK (registered_at_block >= 0),
    lifecycle_version bigint NOT NULL DEFAULT 0 CHECK (lifecycle_version >= 0),
    PRIMARY KEY (run_id, mine_id),
    FOREIGN KEY (run_id, data_class, owner_sha256)
        REFERENCES nqc_miner_v1.runs (run_id, data_class, owner_sha256)
);

-- active/watched intentionally have no representation in this research schema.
-- Rust controls remain the transition authority; a DB write is not a gate pass.
CREATE TABLE nqc_miner_v1.gate_reports (
    run_id text NOT NULL,
    mine_id text NOT NULL,
    gate_kind text NOT NULL CHECK (gate_kind IN ('toxicity', 'adapter', 'valuation', 'wind_tunnel', 'shadow')),
    report_sha256 text NOT NULL CHECK (report_sha256 ~ '^[0-9a-f]{64}$'),
    report_bytes bytea NOT NULL CHECK (octet_length(report_bytes) BETWEEN 1 AND 1048576),
    passed boolean NOT NULL,
    evaluated_at timestamptz NOT NULL,
    PRIMARY KEY (run_id, mine_id, gate_kind, report_sha256),
    FOREIGN KEY (run_id, mine_id) REFERENCES nqc_miner_v1.mine_registry (run_id, mine_id)
);

CREATE TABLE nqc_miner_v1.lifecycle_journal (
    run_id text NOT NULL,
    mine_id text NOT NULL,
    lifecycle_version bigint NOT NULL CHECK (lifecycle_version > 0),
    from_state text NOT NULL CHECK (from_state IN ('detected', 'classified', 'valued', 'wind_tunnel', 'shadow', 'proposed', 'retired')),
    to_state text NOT NULL CHECK (to_state IN ('detected', 'classified', 'valued', 'wind_tunnel', 'shadow', 'proposed', 'retired')),
    decision_sha256 text NOT NULL CHECK (decision_sha256 ~ '^[0-9a-f]{64}$'),
    decision_bytes bytea NOT NULL CHECK (octet_length(decision_bytes) BETWEEN 1 AND 1048576),
    decided_at timestamptz NOT NULL,
    PRIMARY KEY (run_id, mine_id, lifecycle_version),
    FOREIGN KEY (run_id, mine_id) REFERENCES nqc_miner_v1.mine_registry (run_id, mine_id)
);

-- Insert the ledger row and this outbox row in ONE transaction. A future relay
-- may acknowledge only the exact bytes/hash. No relay is implemented or enabled.
CREATE TABLE nqc_miner_v1.outbox (
    run_id text NOT NULL,
    data_class text NOT NULL,
    sequence numeric(20, 0) NOT NULL,
    envelope_sha256 text NOT NULL,
    topic text NOT NULL,
    message_key text NOT NULL,
    payload bytea NOT NULL CHECK (octet_length(payload) BETWEEN 1 AND 1048577),
    created_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
    delivery_enabled boolean NOT NULL DEFAULT false CHECK (NOT delivery_enabled),
    delivered_at timestamptz CHECK (delivered_at IS NULL),
    PRIMARY KEY (run_id, sequence, topic),
    CHECK (topic = 'nqc_miner_v1.' || data_class || '.ledger.v1'),
    CHECK (message_key = 'nqc_miner_v1/' || data_class || '/' || run_id),
    FOREIGN KEY (run_id, data_class, sequence, envelope_sha256)
        REFERENCES nqc_miner_v1.journal_ledger (run_id, data_class, sequence, envelope_sha256)
);

REVOKE ALL ON ALL TABLES IN SCHEMA nqc_miner_v1 FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA nqc_miner_v1 REVOKE ALL ON TABLES FROM PUBLIC;
-- Dedicated runtime roles/privileges are a deployment gate. Ingestion roles must
-- have SELECT/INSERT only on ledger/outbox, never UPDATE/DELETE/TRUNCATE/DDL.
COMMIT;
