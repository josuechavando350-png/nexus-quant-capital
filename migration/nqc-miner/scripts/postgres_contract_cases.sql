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
