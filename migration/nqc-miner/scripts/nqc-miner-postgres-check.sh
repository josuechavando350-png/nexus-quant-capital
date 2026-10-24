#!/usr/bin/env bash
# Generated self-contained PostgreSQL 18 contract test. Synthetic fixtures only.
# No network downloads, existing databases, Observer directories or credentials.
set -euo pipefail
umask 077
if [[ $(id -u) == 0 ]]; then
  printf 'REJECTED: run in ordinary Termux, not as root.\n' >&2
  exit 2
fi
if [[ ${PREFIX:-} != /data/data/com.termux/files/usr || $HOME != /data/data/com.termux/files/home ]]; then
  printf 'REJECTED: expected the native Termux environment reviewed for this test.\n' >&2
  exit 2
fi
for executable in initdb pg_ctl psql createdb sha256sum tar mktemp cmp; do
  command -v "$executable" >/dev/null
done
[[ $(psql --version) == 'psql (PostgreSQL) 18.'* ]]
unset PGHOST PGHOSTADDR PGPORT PGDATABASE PGUSER PGDATA PGSERVICE PGSERVICEFILE PGOPTIONS
export PGCONNECT_TIMEOUT=10 PSQL_PAGER=cat
MINER_TEST_ROOT=$(mktemp -d "$HOME/nqc-miner-check.XXXXXX")
MINER_TEST_USER=$(id -un)
MINER_TEST_STARTED=0
mkdir "$MINER_TEST_ROOT/evidence" "$MINER_TEST_ROOT/s"
MINER_TEST_EVIDENCE="$MINER_TEST_ROOT/evidence"
printf 'Evidence directory: %s\n' "$MINER_TEST_EVIDENCE"
finish() {
  local rc=$?
  trap - EXIT
  if [[ $MINER_TEST_STARTED == 1 ]]; then
    if ! pg_ctl -D "$MINER_TEST_ROOT/data" -m fast -w -t 30 stop >> "$MINER_TEST_EVIDENCE/shutdown.log" 2>&1; then
      rc=1
    fi
  fi
  local result=failed
  if [[ $rc == 0 ]]; then result=pass; fi
  printf '{"schema":"nqc-miner-postgres-contract-check-v1","status":"%s","data_class":"synthetic","production_integration":false,"observer_bridge_enabled":false,"spending_authorized":false}\n' "$result" > "$MINER_TEST_EVIDENCE/result.json"
  (cd "$MINER_TEST_EVIDENCE" && sha256sum ./* > ../SHA256SUMS)
  mv "$MINER_TEST_ROOT/SHA256SUMS" "$MINER_TEST_EVIDENCE/SHA256SUMS"
  tar -czf "$MINER_TEST_ROOT/nqc-miner-postgres-evidence.tar.gz" -C "$MINER_TEST_ROOT" evidence
  printf '\nMINER POSTGRES: %s\nResults: %s\n' "$result" "$MINER_TEST_ROOT/nqc-miner-postgres-evidence.tar.gz"
  exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
date -u +%FT%TZ > "$MINER_TEST_EVIDENCE/started-at.txt"
psql --version > "$MINER_TEST_EVIDENCE/client-version.txt"
uname -m > "$MINER_TEST_EVIDENCE/architecture.txt"
sha256sum "$0" > "$MINER_TEST_EVIDENCE/runner.sha256"
cat > "$MINER_TEST_EVIDENCE/postgres.sql" <<'NQC_MINER_EMBEDDED_SQL_0'
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
NQC_MINER_EMBEDDED_SQL_0
cat > "$MINER_TEST_EVIDENCE/cases.sql" <<'NQC_MINER_EMBEDDED_SQL_1'
-- Synthetic SQL fixtures only. These are NOT verified Miner journals.
-- Run solely in the new disposable cluster created by the Termux runner.
SET ROLE nqc_miner_test_owner;
SET search_path = nqc_miner_v1, pg_catalog;

CREATE FUNCTION pg_temp.check_ok(ok boolean, label text) RETURNS void
LANGUAGE plpgsql AS $$ BEGIN
  IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'FAILED: %', label; END IF;
  RAISE NOTICE 'MINER_PASS: %', label;
END $$;

CREATE FUNCTION pg_temp.reject_sql(q text, expected_state text, label text)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE actual_state text;
BEGIN
  BEGIN
    EXECUTE q;
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS actual_state = RETURNED_SQLSTATE;
    IF actual_state <> expected_state THEN RAISE; END IF;
    RAISE NOTICE 'MINER_PASS: %', label;
    RETURN;
  END;
  RAISE EXCEPTION 'FAILED (statement accepted): %', label;
END $$;

SELECT pg_temp.check_ok(current_database() = 'nqc_miner_v1', 'dedicated_database');
SELECT pg_temp.check_ok(current_setting('listen_addresses') = '', 'no_tcp_listener');
SELECT pg_temp.check_ok(current_setting('fsync') = 'on' AND current_setting('synchronous_commit') = 'on', 'durable_commit_settings');
SELECT pg_temp.check_ok((SELECT count(*) = 6 AND bool_and(tableowner = 'nqc_miner_test_owner')
  FROM pg_tables WHERE schemaname = 'nqc_miner_v1'), 'six_tables_owned_by_dedicated_role');
SELECT pg_temp.check_ok(NOT has_schema_privilege('nqc_miner_test_outsider', 'nqc_miner_v1', 'USAGE'), 'outsider_schema_denied');
SELECT pg_temp.check_ok((SELECT bool_and(NOT has_table_privilege('nqc_miner_test_outsider',
  format('%I.%I', schemaname, tablename), 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE'))
  FROM pg_tables WHERE schemaname = 'nqc_miner_v1'), 'outsider_table_access_denied');

INSERT INTO runs(run_id,data_class,owner_sha256,config_sha256,code_commit,cargo_lock_sha256,original_owner,original_config)
VALUES ('pg_contract_synthetic','synthetic',repeat('1',64),repeat('2',64),repeat('3',40),repeat('4',64),
  convert_to('SYNTHETIC SQL FIXTURE ONLY','UTF8'),convert_to('NOT A MINER CONFIG','UTF8'));

SELECT pg_temp.reject_sql($q$UPDATE runs SET observer_bridge_enabled=true$q$, '23514', 'bridge_disabled');
SELECT pg_temp.reject_sql($q$UPDATE runs SET signing_enabled=true$q$, '23514', 'signing_disabled');
SELECT pg_temp.reject_sql($q$UPDATE runs SET telegram_enabled=true$q$, '23514', 'notifications_disabled');
SELECT pg_temp.reject_sql($q$UPDATE runs SET kms_enabled=true$q$, '23514', 'kms_disabled');
SELECT pg_temp.reject_sql($q$UPDATE runs SET gas_budget_mxn_centavos=1$q$, '23514', 'spending_disabled');
SELECT pg_temp.reject_sql($q$UPDATE runs SET data_class='unclassified'$q$, '23514', 'unknown_class_rejected');

BEGIN;
INSERT INTO journal_ledger(run_id,data_class,owner_sha256,sequence,previous_sha256,envelope_sha256,raw_line_sha256,record_kind,raw_line)
VALUES ('pg_contract_synthetic','synthetic',repeat('1',64),0,repeat('0',64),repeat('5',64),repeat('6',64),'observed',decode('000aff80','hex'));
INSERT INTO outbox(run_id,data_class,sequence,envelope_sha256,topic,message_key,payload)
VALUES ('pg_contract_synthetic','synthetic',0,repeat('5',64),'nqc_miner_v1.synthetic.ledger.v1',
  'nqc_miner_v1/synthetic/pg_contract_synthetic',decode('000aff80','hex'));
COMMIT;
SELECT pg_temp.check_ok((SELECT count(*)=1 FROM journal_ledger) AND (SELECT count(*)=1 FROM outbox), 'ledger_outbox_commit');
SELECT pg_temp.check_ok((SELECT encode(raw_line,'hex')='000aff80' FROM journal_ledger)
  AND (SELECT encode(payload,'hex')='000aff80' FROM outbox), 'exact_binary_bytes');
SELECT pg_temp.reject_sql($q$INSERT INTO journal_ledger SELECT * FROM journal_ledger$q$, '23505', 'duplicate_ledger_rejected');
SELECT pg_temp.reject_sql($q$INSERT INTO outbox SELECT * FROM outbox$q$, '23505', 'duplicate_outbox_rejected');
SELECT pg_temp.reject_sql($q$UPDATE journal_ledger SET owner_sha256=repeat('9',64)$q$, '23503', 'foreign_owner_rejected');
SELECT pg_temp.reject_sql($q$UPDATE journal_ledger SET sequence=-1$q$, '23514', 'negative_sequence_rejected');
SELECT pg_temp.reject_sql($q$UPDATE journal_ledger SET sequence=18446744073709551616$q$, '23514', 'sequence_overflow_rejected');
SELECT pg_temp.reject_sql($q$UPDATE outbox SET envelope_sha256=repeat('8',64)$q$, '23503', 'outbox_foreign_envelope_rejected');
SELECT pg_temp.reject_sql($q$UPDATE outbox SET topic='nqc_miner_v1.historical.ledger.v1'$q$, '23514', 'cross_class_topic_rejected');
SELECT pg_temp.reject_sql($q$UPDATE outbox SET message_key='foreign/key'$q$, '23514', 'foreign_message_key_rejected');
SELECT pg_temp.reject_sql($q$UPDATE outbox SET delivery_enabled=true$q$, '23514', 'relay_disabled');
SELECT pg_temp.reject_sql($q$UPDATE outbox SET delivered_at=now()$q$, '23514', 'delivery_ack_disabled');

-- A failure after the ledger INSERT must roll that INSERT back too.
DO $$ DECLARE inserted boolean := false; BEGIN
  BEGIN
    INSERT INTO journal_ledger(run_id,data_class,owner_sha256,sequence,previous_sha256,envelope_sha256,raw_line_sha256,record_kind,raw_line)
    VALUES ('pg_contract_synthetic','synthetic',repeat('1',64),1,repeat('5',64),repeat('7',64),repeat('8',64),'observed',decode('aa','hex'));
    inserted := true;
    INSERT INTO outbox(run_id,data_class,sequence,envelope_sha256,topic,message_key,payload)
    VALUES ('pg_contract_synthetic','synthetic',1,repeat('7',64),'wrong-topic','wrong-key',decode('aa','hex'));
    RAISE EXCEPTION 'invalid outbox unexpectedly accepted';
  EXCEPTION WHEN check_violation THEN
    IF NOT inserted THEN RAISE; END IF;
  END;
END $$;
SELECT pg_temp.check_ok(NOT EXISTS(SELECT FROM journal_ledger WHERE sequence=1)
  AND NOT EXISTS(SELECT FROM outbox WHERE sequence=1), 'failed_outbox_rolls_back_ledger');

BEGIN;
INSERT INTO journal_ledger(run_id,data_class,owner_sha256,sequence,previous_sha256,envelope_sha256,raw_line_sha256,record_kind,raw_line)
VALUES ('pg_contract_synthetic','synthetic',repeat('1',64),2,repeat('5',64),repeat('7',64),repeat('8',64),'observed',decode('bb','hex'));
INSERT INTO outbox(run_id,data_class,sequence,envelope_sha256,topic,message_key,payload)
VALUES ('pg_contract_synthetic','synthetic',2,repeat('7',64),'nqc_miner_v1.synthetic.ledger.v1',
  'nqc_miner_v1/synthetic/pg_contract_synthetic',decode('bb','hex'));
ROLLBACK;
SELECT pg_temp.check_ok(NOT EXISTS(SELECT FROM journal_ledger WHERE sequence=2)
  AND NOT EXISTS(SELECT FROM outbox WHERE sequence=2), 'explicit_transaction_rollback');

INSERT INTO mine_registry(mine_id,run_id,data_class,owner_sha256,chain_id,contract,scope_id,protocol,registered_at_block)
VALUES ('synthetic-mine','pg_contract_synthetic','synthetic',repeat('1',64),1,'0x'||repeat('1',40),'synthetic','aave-v3',0);
SELECT pg_temp.reject_sql($q$UPDATE mine_registry SET lifecycle_state='active'$q$, '23514', 'active_state_unavailable');
SELECT pg_temp.reject_sql($q$UPDATE mine_registry SET lifecycle_state='watched'$q$, '23514', 'watched_state_unavailable');
SELECT pg_temp.reject_sql($q$UPDATE mine_registry SET data_class='historical'$q$, '23503', 'cross_class_registry_rejected');

GRANT USAGE ON SCHEMA nqc_miner_v1 TO nqc_miner_test_writer;
GRANT SELECT,INSERT ON journal_ledger,outbox TO nqc_miner_test_writer;
SELECT pg_temp.check_ok(has_table_privilege('nqc_miner_test_writer','journal_ledger','SELECT')
  AND has_table_privilege('nqc_miner_test_writer','journal_ledger','INSERT')
  AND NOT has_table_privilege('nqc_miner_test_writer','journal_ledger','UPDATE,DELETE,TRUNCATE')
  AND NOT has_table_privilege('nqc_miner_test_writer','outbox','UPDATE,DELETE,TRUNCATE')
  AND NOT has_schema_privilege('nqc_miner_test_writer','nqc_miner_v1','CREATE'), 'writer_privileges_append_only');
NQC_MINER_EMBEDDED_SQL_1
cat > "$MINER_TEST_EVIDENCE/input.sha256" <<'NQC_MINER_INPUT_HASHES'
5307880cd7f274f5f0ac4eb222e19ca34fb0e0a9abd59a2970be50611a259f21  postgres.sql
e0d321b30d43e1199bba3bd439087e1d404d876307edff70959de4a03ae86fff  cases.sql
NQC_MINER_INPUT_HASHES

(cd "$MINER_TEST_EVIDENCE" && sha256sum -c input.sha256)
initdb -D "$MINER_TEST_ROOT/data" -U "$MINER_TEST_USER" --encoding=UTF8 --locale=C \
  --auth-local=peer --auth-host=reject > "$MINER_TEST_EVIDENCE/initdb.log" 2>&1
cat >> "$MINER_TEST_ROOT/data/postgresql.conf" <<EOF
listen_addresses = ''
unix_socket_directories = '$MINER_TEST_ROOT/s'
unix_socket_permissions = 0700
port = 55432
shared_buffers = '32MB'
max_connections = 10
max_parallel_workers = 0
EOF
cp "$MINER_TEST_ROOT/data/postgresql.conf" "$MINER_TEST_ROOT/data/pg_hba.conf" "$MINER_TEST_EVIDENCE/"
# Set before startup: even a timeout triggers shutdown of this new cluster only.
MINER_TEST_STARTED=1
pg_ctl -D "$MINER_TEST_ROOT/data" -l "$MINER_TEST_EVIDENCE/server.log" -w -t 60 start > "$MINER_TEST_EVIDENCE/startup.log" 2>&1
MINER_TEST_PSQL=(psql -X -w -h "$MINER_TEST_ROOT/s" -p 55432 -U "$MINER_TEST_USER" -v ON_ERROR_STOP=1 -v VERBOSITY=verbose -P pager=off)
"${MINER_TEST_PSQL[@]}" -d postgres -c 'CREATE ROLE nqc_miner_test_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION; CREATE ROLE nqc_miner_test_outsider NOLOGIN NOSUPERUSER; CREATE ROLE nqc_miner_test_writer NOLOGIN NOSUPERUSER;' > "$MINER_TEST_EVIDENCE/roles.log" 2>&1
createdb -w -h "$MINER_TEST_ROOT/s" -p 55432 -U "$MINER_TEST_USER" --maintenance-db=postgres -O nqc_miner_test_owner nqc_miner_v1 > "$MINER_TEST_EVIDENCE/database.log" 2>&1

if "${MINER_TEST_PSQL[@]}" -d postgres -c 'SET ROLE nqc_miner_test_owner' -f "$MINER_TEST_EVIDENCE/postgres.sql" > "$MINER_TEST_EVIDENCE/wrong-database.log" 2>&1; then
  printf 'FAILED: foreign database accepted\n' >&2; exit 1
fi
grep -q 'Refusing foreign database: expected nqc_miner_v1' "$MINER_TEST_EVIDENCE/wrong-database.log"
[[ $("${MINER_TEST_PSQL[@]}" -d postgres -Atqc "SELECT count(*) FROM pg_namespace WHERE nspname='nqc_miner_v1'") == 0 ]]
"${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -c 'SET ROLE nqc_miner_test_owner' -f "$MINER_TEST_EVIDENCE/postgres.sql" > "$MINER_TEST_EVIDENCE/apply-schema.log" 2>&1
if "${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -c 'SET ROLE nqc_miner_test_owner' -f "$MINER_TEST_EVIDENCE/postgres.sql" > "$MINER_TEST_EVIDENCE/duplicate-schema.log" 2>&1; then
  printf 'FAILED: existing schema silently adopted\n' >&2; exit 1
fi
grep -q '42P06' "$MINER_TEST_EVIDENCE/duplicate-schema.log"
"${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -f "$MINER_TEST_EVIDENCE/cases.sql" > "$MINER_TEST_EVIDENCE/cases.log" 2>&1
[[ $(grep -c 'MINER_PASS:' "$MINER_TEST_EVIDENCE/cases.log") == 30 ]]

# Exercise actual denied statements under the limited role, not only ACL queries.
for action in 'UPDATE nqc_miner_v1.journal_ledger SET sequence=sequence' 'DELETE FROM nqc_miner_v1.outbox' 'TRUNCATE nqc_miner_v1.journal_ledger'; do
  if "${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -c 'SET ROLE nqc_miner_test_writer' -c "$action" >> "$MINER_TEST_EVIDENCE/writer-denials.log" 2>&1; then
    printf 'FAILED: limited writer modified existing evidence\n' >&2; exit 1
  fi
done
[[ $(grep -c 'ERROR:  *42501' "$MINER_TEST_EVIDENCE/writer-denials.log") == 3 ]]
"${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -Atqc 'SELECT version(); SHOW listen_addresses; SHOW unix_socket_directories; SHOW fsync; SHOW synchronous_commit;' > "$MINER_TEST_EVIDENCE/server-settings.txt"
MINER_TEST_SNAPSHOT="SELECT jsonb_build_object('runs',(SELECT jsonb_agg(r ORDER BY run_id) FROM nqc_miner_v1.runs r),'ledger',(SELECT jsonb_agg(j ORDER BY run_id,sequence) FROM nqc_miner_v1.journal_ledger j),'outbox',(SELECT jsonb_agg(o ORDER BY run_id,sequence,topic) FROM nqc_miner_v1.outbox o),'registry',(SELECT jsonb_agg(m ORDER BY run_id,mine_id) FROM nqc_miner_v1.mine_registry m))"
"${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -Atqc "$MINER_TEST_SNAPSHOT" > "$MINER_TEST_EVIDENCE/before-restart.json"
pg_ctl -D "$MINER_TEST_ROOT/data" -m fast -w -t 60 restart >> "$MINER_TEST_EVIDENCE/startup.log" 2>&1
"${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -Atqc "$MINER_TEST_SNAPSHOT" > "$MINER_TEST_EVIDENCE/after-restart.json"
cmp "$MINER_TEST_EVIDENCE/before-restart.json" "$MINER_TEST_EVIDENCE/after-restart.json"
printf 'Schema guards, 30 SQL checks, 3 writer denials and restart comparison passed.\n'
