-- Artificial fixtures only, in the runner's new private disposable cluster.
SET ROLE nqc_miner_import_writer;
CREATE FUNCTION pg_temp.check_ok(ok boolean,label text) RETURNS void LANGUAGE plpgsql AS $$ BEGIN
  IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'FAILED: %',label; END IF;
  RAISE NOTICE 'MINER_COLLECTION_PASS: %',label;
END $$;
CREATE FUNCTION pg_temp.expect_import(name text,status text,inserted bigint,label text) RETURNS jsonb
LANGUAGE plpgsql AS $$ DECLARE r jsonb; BEGIN
  SELECT nqc_miner_v1.import_verified_collection(payload) INTO r FROM nqc_miner_v1.test_inputs WHERE test_inputs.name=expect_import.name;
  PERFORM pg_temp.check_ok(r->>'status'=status AND (r->>'inserted')::bigint=inserted,label);
  RETURN r;
END $$;
CREATE FUNCTION pg_temp.reject_query(q text,expected text,label text) RETURNS void
LANGUAGE plpgsql AS $$ DECLARE actual text; BEGIN
  BEGIN EXECUTE q;
  EXCEPTION WHEN OTHERS THEN
    GET STACKED DIAGNOSTICS actual=RETURNED_SQLSTATE;
    IF actual<>expected THEN RAISE; END IF;
    RAISE NOTICE 'MINER_COLLECTION_PASS: %',label; RETURN;
  END;
  RAISE EXCEPTION 'FAILED (accepted): %',label;
END $$;

SELECT pg_temp.check_ok(current_user='nqc_miner_import_writer' AND NOT (SELECT rolsuper FROM pg_roles WHERE rolname=current_user),'limited_collection_writer'); -- CASE
SELECT pg_temp.check_ok(current_setting('listen_addresses')='' AND current_setting('fsync')='on' AND current_setting('synchronous_commit')='on','private_durable_instance'); -- CASE
SELECT pg_temp.expect_import('normal-two','imported',4,'initial_two_windows'); -- CASE
SELECT pg_temp.expect_import('normal-two','idempotent',0,'same_receipt_repeat'); -- CASE
SELECT pg_temp.check_ok((SELECT count(*)=4 FROM nqc_miner_v1.eligible_collection_ledger WHERE parent_run_id='pgcoll_normal')
 AND (SELECT count(*)=4 FROM nqc_miner_v1.eligible_collection_outbox WHERE parent_run_id='pgcoll_normal'),'whole_collection_visible'); -- CASE
SELECT pg_temp.expect_import('normal-three','imported',2,'append_third_window'); -- CASE
SELECT pg_temp.expect_import('normal-two','stale',0,'old_receipt_cannot_regress'); -- CASE
SELECT pg_temp.check_ok((SELECT count(*)=6 FROM nqc_miner_v1.eligible_collection_ledger WHERE parent_run_id='pgcoll_normal')
 AND (SELECT count(*)=3 FROM nqc_miner_v1.collection_windows WHERE parent_run_id='pgcoll_normal')
 AND NOT EXISTS(SELECT FROM nqc_miner_v1.test_inputs t CROSS JOIN LATERAL jsonb_array_elements(t.payload->'windows') w
 CROSS JOIN LATERAL jsonb_array_elements(w->'journal'->'records') x
 JOIN nqc_miner_v1.journal_ledger l ON l.run_id=w->'journal'->'owner'->>'run_id' AND l.sequence=(x->>'sequence')::numeric
 WHERE t.name='normal-three' AND l.raw_line IS DISTINCT FROM decode(x->>'raw_line_hex','hex')),'original_window_bytes_preserved'); -- CASE
SELECT pg_temp.reject_query($q$SELECT nqc_miner_v1.import_verified_collection(payload) FROM nqc_miner_v1.test_inputs WHERE name='foreign-archive'$q$,'P0001','foreign_archive_rejected'); -- CASE
SELECT pg_temp.reject_query($q$SELECT nqc_miner_v1.import_verified_collection(jsonb_set(payload,'{database_id}','"00000000-0000-4000-8000-000000000001"')) FROM nqc_miner_v1.test_inputs WHERE name='rollback'$q$,'P0001','foreign_database_rejected'); -- CASE
SELECT pg_temp.reject_query($q$SELECT nqc_miner_v1.import_verified_collection(jsonb_set(payload,'{windows,1,journal,records,0,raw_line_hex}','"00"')) FROM nqc_miner_v1.test_inputs WHERE name='rollback'$q$,'P0001','altered_child_transport_rejected'); -- CASE
SELECT pg_temp.check_ok(NOT EXISTS(SELECT FROM nqc_miner_v1.collections WHERE parent_run_id='pgcoll_rollback')
 AND NOT EXISTS(SELECT FROM nqc_miner_v1.runs WHERE run_id='pgcoll_rollback'),'rejected_bundle_has_no_partial_parent'); -- CASE

SELECT pg_temp.expect_import('normal-revoked','quarantined',1,'parent_revocation_imported'); -- CASE
SELECT pg_temp.check_ok(NOT EXISTS(SELECT FROM nqc_miner_v1.eligible_collection_ledger WHERE parent_run_id='pgcoll_normal')
 AND NOT EXISTS(SELECT FROM nqc_miner_v1.eligible_collection_outbox WHERE parent_run_id='pgcoll_normal'),'all_windows_excluded_by_parent'); -- CASE
SELECT pg_temp.check_ok((SELECT count(*)=6 FROM nqc_miner_v1.journal_ledger l JOIN nqc_miner_v1.collection_windows w ON l.run_id=w.child_run_id WHERE w.parent_run_id='pgcoll_normal')
 AND (SELECT count(*)=3 FROM nqc_miner_v1.collection_windows WHERE parent_run_id='pgcoll_normal'),'child_evidence_not_deleted'); -- CASE
SELECT pg_temp.check_ok(EXISTS(SELECT FROM nqc_miner_v1.journal_ledger WHERE run_id='pgcoll_normal' AND record_kind='invalidated')
 AND EXISTS(SELECT FROM nqc_miner_v1.collection_quarantine WHERE parent_run_id='pgcoll_normal' AND reason='parent_invalidated')
 AND EXISTS(SELECT FROM nqc_miner_v1.collection_receipts WHERE parent_run_id='pgcoll_normal' AND receipt_sequence=2 AND applied_status='quarantined'),'revocation_receipt_retained'); -- CASE
SELECT pg_temp.expect_import('normal-two','quarantined',0,'old_bundle_never_reactivates'); -- CASE
SELECT pg_temp.expect_import('normal-revoked','quarantined',0,'repeat_revocation'); -- CASE
SELECT pg_temp.expect_import('revoked-first','quarantined',1,'revocation_before_any_child_import'); -- CASE
SELECT pg_temp.check_ok(NOT EXISTS(SELECT FROM nqc_miner_v1.collection_windows WHERE parent_run_id='pgcoll_revoked_first')
 AND EXISTS(SELECT FROM nqc_miner_v1.collection_quarantine WHERE parent_run_id='pgcoll_revoked_first'),'revocation_needs_no_child_files'); -- CASE

SELECT pg_temp.expect_import('child','imported',4,'child_invalidation_seed'); -- CASE
SELECT pg_temp.check_ok((SELECT nqc_miner_v1.import_verified_journal(payload)->>'status'='quarantined' FROM nqc_miner_v1.test_inputs WHERE name='child-invalidated'),'independent_child_invalidation'); -- CASE
SELECT pg_temp.check_ok(NOT EXISTS(SELECT FROM nqc_miner_v1.eligible_collection_ledger WHERE parent_run_id='pgcoll_child'),'one_invalid_child_blocks_whole_collection'); -- CASE
SELECT pg_temp.expect_import('child','quarantined',0,'child_quarantine_propagates_on_replay'); -- CASE
SELECT pg_temp.expect_import('conflict','imported',4,'receipt_conflict_seed'); -- CASE
SELECT pg_temp.expect_import('conflicting-receipt','quarantined',0,'same_sequence_changed_receipt_quarantined'); -- CASE
SELECT pg_temp.check_ok(NOT EXISTS(SELECT FROM nqc_miner_v1.eligible_collection_ledger WHERE parent_run_id='pgcoll_conflict')
 AND (SELECT count(*)=4 FROM nqc_miner_v1.journal_ledger l JOIN nqc_miner_v1.collection_windows w ON w.child_run_id=l.run_id WHERE w.parent_run_id='pgcoll_conflict'),'conflict_preserves_prior_rows'); -- CASE
SELECT pg_temp.expect_import('conflict','quarantined',0,'conflicting_collection_stays_quarantined'); -- CASE

SET ROLE nqc_miner_import_owner;
CREATE FUNCTION nqc_miner_v1.test_abort_collection_outbox() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
  IF NEW.run_id=(SELECT payload->'windows'->1->'journal'->'owner'->>'run_id' FROM nqc_miner_v1.test_inputs WHERE name='rollback') THEN
    RAISE EXCEPTION 'injected second-window outbox failure' USING ERRCODE='PZ001';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER test_abort_collection_outbox BEFORE INSERT ON nqc_miner_v1.outbox
 FOR EACH ROW EXECUTE FUNCTION nqc_miner_v1.test_abort_collection_outbox();
SET ROLE nqc_miner_import_writer;
SELECT pg_temp.reject_query($q$SELECT nqc_miner_v1.import_verified_collection(payload) FROM nqc_miner_v1.test_inputs WHERE name='rollback'$q$,'PZ001','second_window_failure_rolls_back_transaction'); -- CASE
SELECT pg_temp.check_ok(NOT EXISTS(SELECT FROM nqc_miner_v1.runs WHERE run_id='pgcoll_rollback'
 OR run_id IN(SELECT w->'journal'->'owner'->>'run_id' FROM nqc_miner_v1.test_inputs t CROSS JOIN LATERAL jsonb_array_elements(t.payload->'windows') w WHERE t.name='rollback'))
 AND NOT EXISTS(SELECT FROM nqc_miner_v1.collections WHERE parent_run_id='pgcoll_rollback'),'no_partial_parent_or_first_window'); -- CASE
SET ROLE nqc_miner_import_owner;
DROP TRIGGER test_abort_collection_outbox ON nqc_miner_v1.outbox;
DROP FUNCTION nqc_miner_v1.test_abort_collection_outbox();
SET ROLE nqc_miner_import_writer;
SELECT pg_temp.expect_import('rollback','imported',4,'retry_after_collection_rollback'); -- CASE
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT pg_temp.reject_query($q$SELECT nqc_miner_v1.import_verified_collection(payload) FROM nqc_miner_v1.test_inputs WHERE name='rollback'$q$,'P0001','unsupported_collection_isolation'); -- CASE
COMMIT;
SELECT pg_temp.check_ok(NOT EXISTS(SELECT FROM nqc_miner_v1.runs WHERE observer_bridge_enabled OR signing_enabled OR telegram_enabled OR kms_enabled OR gas_budget_mxn_centavos<>0)
 AND NOT EXISTS(SELECT FROM nqc_miner_v1.outbox WHERE delivery_enabled OR delivered_at IS NOT NULL),'operational_controls_stay_disabled'); -- CASE
