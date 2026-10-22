-- Runs only in the runner's fresh private cluster. All fixtures are synthetic.
SET ROLE nqc_miner_import_writer;
CREATE FUNCTION pg_temp.check_ok(ok boolean, label text) RETURNS void
LANGUAGE plpgsql AS $$ BEGIN
  IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'FAILED: %',label; END IF;
  RAISE NOTICE 'MINER_IMPORT_PASS: %',label;
END $$;
CREATE FUNCTION pg_temp.expect_import(name text, status text, inserted bigint, reason text, label text)
RETURNS jsonb LANGUAGE plpgsql AS $$ DECLARE r jsonb; BEGIN
  SELECT nqc_miner_v1.import_verified_journal(payload) INTO r FROM nqc_miner_v1.test_inputs WHERE test_inputs.name=expect_import.name;
  PERFORM pg_temp.check_ok(r->>'status'=status AND (r->>'inserted')::bigint=inserted
    AND (reason IS NULL OR r->>'reason'=reason),label);
  RETURN r;
END $$;
CREATE FUNCTION pg_temp.reject_query(q text, expected text, label text) RETURNS void
LANGUAGE plpgsql AS $$ DECLARE actual text; BEGIN
  BEGIN EXECUTE q;
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS actual=RETURNED_SQLSTATE;
    IF actual<>expected THEN RAISE; END IF;
    RAISE NOTICE 'MINER_IMPORT_PASS: %',label;
    RETURN;
  END;
  RAISE EXCEPTION 'FAILED (accepted): %',label;
END $$;

SELECT pg_temp.check_ok(current_user='nqc_miner_import_writer' AND NOT (SELECT rolsuper FROM pg_roles WHERE rolname=current_user), 'limited_writer_identity'); -- CASE
SELECT pg_temp.check_ok(NOT has_function_privilege('nqc_miner_import_outsider','nqc_miner_v1.import_verified_journal(jsonb)','EXECUTE'), 'outsider_function_denied'); -- CASE
SELECT pg_temp.check_ok(current_setting('listen_addresses')='' AND current_setting('fsync')='on' AND current_setting('synchronous_commit')='on', 'private_durable_instance'); -- CASE
SELECT pg_temp.expect_import('normal-prefix','imported',2,NULL,'initial_prefix'); -- CASE
SELECT pg_temp.expect_import('normal-prefix','idempotent',0,NULL,'repeat_prefix'); -- CASE
SELECT pg_temp.expect_import('normal-full','imported',1,NULL,'append_extension'); -- CASE
SELECT pg_temp.expect_import('normal-prefix','idempotent',0,NULL,'old_prefix_preserves_tip'); -- CASE
SELECT pg_temp.expect_import('normal-full','idempotent',0,NULL,'repeat_full'); -- CASE
SELECT pg_temp.check_ok((SELECT count(*)=3 FROM nqc_miner_v1.journal_ledger WHERE run_id='pgimp_normal')
  AND (SELECT count(*)=3 FROM nqc_miner_v1.outbox WHERE run_id='pgimp_normal')
  AND NOT EXISTS(SELECT FROM nqc_miner_v1.test_inputs t CROSS JOIN LATERAL jsonb_array_elements(t.payload->'records') x
    JOIN nqc_miner_v1.journal_ledger l ON l.run_id='pgimp_normal' AND l.sequence=(x->>'sequence')::numeric
    JOIN nqc_miner_v1.outbox o ON o.run_id=l.run_id AND o.sequence=l.sequence
    WHERE t.name='normal-full' AND (l.raw_line IS DISTINCT FROM decode(x->>'raw_line_hex','hex')
      OR o.payload IS DISTINCT FROM l.raw_line OR l.raw_line_sha256 IS DISTINCT FROM x->>'raw_line_sha256'))
  AND (SELECT r.original_owner=decode(t.payload->>'original_owner_hex','hex')
    AND r.original_config=decode(t.payload->>'original_config_hex','hex') FROM nqc_miner_v1.runs r
    CROSS JOIN nqc_miner_v1.test_inputs t WHERE r.run_id='pgimp_normal' AND t.name='normal-full'), 'exact_original_bytes'); -- CASE
SELECT pg_temp.expect_import('empty','idempotent',0,NULL,'empty_journal'); -- CASE
SELECT pg_temp.check_ok(EXISTS(SELECT FROM nqc_miner_v1.runs WHERE run_id='pgimp_empty')
  AND NOT EXISTS(SELECT FROM nqc_miner_v1.journal_ledger WHERE run_id='pgimp_empty'), 'empty_has_no_invented_rows'); -- CASE
SELECT pg_temp.reject_query($q$SELECT nqc_miner_v1.import_verified_journal(jsonb_set(payload,'{database_id}','"00000000-0000-4000-8000-000000000001"')) FROM nqc_miner_v1.test_inputs WHERE name='uuid'$q$,'P0001','foreign_database_uuid'); -- CASE
SELECT pg_temp.reject_query($q$SELECT nqc_miner_v1.import_verified_journal(jsonb_set(payload,'{journal_sha256}',to_jsonb(repeat('0',64)))) FROM nqc_miner_v1.test_inputs WHERE name='uuid'$q$,'P0001','corrupt_transport_hash'); -- CASE
SELECT pg_temp.check_ok(NOT EXISTS(SELECT FROM nqc_miner_v1.runs WHERE run_id='pgimp_uuid'), 'rejected_transport_has_no_run'); -- CASE
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT pg_temp.reject_query($q$SELECT nqc_miner_v1.import_verified_journal(payload) FROM nqc_miner_v1.test_inputs WHERE name='uuid'$q$,'P0001','unsupported_isolation'); -- CASE
COMMIT;

SELECT pg_temp.expect_import('conflict-base','imported',3,NULL,'conflict_seed'); -- CASE
SELECT pg_temp.expect_import('conflict-space','quarantined',0,'journal_conflict','raw_byte_conflict'); -- CASE
SELECT pg_temp.check_ok((SELECT l.raw_line=decode(t.payload->'records'->0->>'raw_line_hex','hex')
    FROM nqc_miner_v1.journal_ledger l CROSS JOIN nqc_miner_v1.test_inputs t
    WHERE l.run_id='pgimp_conflict' AND l.sequence=0 AND t.name='conflict-base')
  AND (SELECT q.incoming_journal_sha256=t.payload->>'journal_sha256' FROM nqc_miner_v1.import_quarantine q
    CROSS JOIN nqc_miner_v1.test_inputs t WHERE q.run_id='pgimp_conflict' AND t.name='conflict-space'), 'conflict_preserves_prior_bytes'); -- CASE
SELECT pg_temp.expect_import('conflict-base','quarantined',0,NULL,'conflict_never_reactivated'); -- CASE
SELECT pg_temp.expect_import('owner-base','imported',3,NULL,'owner_seed'); -- CASE
SELECT pg_temp.expect_import('owner-pretty','quarantined',0,'owner_conflict','original_owner_byte_conflict'); -- CASE
SELECT pg_temp.expect_import('invalidated-base','imported',3,NULL,'invalidation_seed'); -- CASE
SELECT pg_temp.expect_import('invalidated-full','quarantined',1,'journal_invalidated','late_invalidation'); -- CASE
SELECT pg_temp.expect_import('invalidated-base','quarantined',0,NULL,'invalidation_never_reactivated'); -- CASE
SELECT pg_temp.check_ok((SELECT count(*)=4 FROM nqc_miner_v1.journal_ledger WHERE run_id='pgimp_invalidated')
  AND EXISTS(SELECT FROM nqc_miner_v1.outbox WHERE run_id='pgimp_invalidated' AND sequence=3), 'invalidation_evidence_retained'); -- CASE

SELECT pg_temp.expect_import('gap','imported',3,NULL,'gap_seed'); -- CASE
SET ROLE nqc_miner_import_owner;
DELETE FROM nqc_miner_v1.outbox WHERE run_id='pgimp_gap' AND sequence=1;
DELETE FROM nqc_miner_v1.journal_ledger WHERE run_id='pgimp_gap' AND sequence=1;
SET ROLE nqc_miner_import_writer;
SELECT pg_temp.expect_import('gap','quarantined',0,'database_gap','gap_quarantined'); -- CASE
SELECT pg_temp.expect_import('outbox','imported',3,NULL,'outbox_seed'); -- CASE
SET ROLE nqc_miner_import_owner;
DELETE FROM nqc_miner_v1.outbox WHERE run_id='pgimp_outbox' AND sequence=1;
SET ROLE nqc_miner_import_writer;
SELECT pg_temp.expect_import('outbox','quarantined',0,'outbox_conflict','missing_outbox_quarantined'); -- CASE
SELECT pg_temp.expect_import('payload','imported',3,NULL,'payload_seed'); -- CASE
SET ROLE nqc_miner_import_owner;
UPDATE nqc_miner_v1.outbox SET payload=decode('00','hex') WHERE run_id='pgimp_payload' AND sequence=1;
SET ROLE nqc_miner_import_writer;
SELECT pg_temp.expect_import('payload','quarantined',0,'outbox_conflict','changed_outbox_quarantined'); -- CASE

-- Fault injection is confined to this disposable test database, then removed.
SET ROLE nqc_miner_import_owner;
CREATE FUNCTION nqc_miner_v1.test_abort_outbox() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  IF NEW.run_id='pgimp_rollback' THEN RAISE EXCEPTION 'injected outbox failure' USING ERRCODE='PZ001'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER test_abort_outbox BEFORE INSERT ON nqc_miner_v1.outbox
  FOR EACH ROW EXECUTE FUNCTION nqc_miner_v1.test_abort_outbox();
SET ROLE nqc_miner_import_writer;
SELECT pg_temp.reject_query($q$SELECT nqc_miner_v1.import_verified_journal(payload) FROM nqc_miner_v1.test_inputs WHERE name='rollback'$q$,'PZ001','outbox_failure_rejects_transaction'); -- CASE
SELECT pg_temp.check_ok(NOT EXISTS(SELECT FROM nqc_miner_v1.runs WHERE run_id='pgimp_rollback')
  AND NOT EXISTS(SELECT FROM nqc_miner_v1.journal_ledger WHERE run_id='pgimp_rollback')
  AND NOT EXISTS(SELECT FROM nqc_miner_v1.outbox WHERE run_id='pgimp_rollback'), 'failed_outbox_rolls_back_all'); -- CASE
SET ROLE nqc_miner_import_owner;
DROP TRIGGER test_abort_outbox ON nqc_miner_v1.outbox;
DROP FUNCTION nqc_miner_v1.test_abort_outbox();
SET ROLE nqc_miner_import_writer;
SELECT pg_temp.expect_import('rollback','imported',3,NULL,'retry_after_rollback'); -- CASE
SELECT pg_temp.check_ok(NOT EXISTS(SELECT FROM nqc_miner_v1.runs WHERE observer_bridge_enabled OR signing_enabled
  OR telegram_enabled OR kms_enabled OR gas_budget_mxn_centavos<>0)
  AND NOT EXISTS(SELECT FROM nqc_miner_v1.outbox WHERE delivery_enabled OR delivered_at IS NOT NULL), 'operational_controls_disabled'); -- CASE
