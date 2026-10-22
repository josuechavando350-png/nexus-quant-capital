-- Candidate collection migration: requires a separate PostgreSQL runtime audit.
-- Additive to postgres.sql + postgres_import.sql. No grants or connections.
BEGIN;
SET LOCAL search_path = pg_catalog;
DO $$ BEGIN
  IF current_database() <> 'nqc_miner_v1' OR NOT EXISTS (
      SELECT FROM pg_namespace WHERE nspname='nqc_miner_v1' AND nspowner=current_user::regrole) THEN
    RAISE EXCEPTION 'Miner collection migration requires its dedicated database and owner';
  END IF;
  IF NOT EXISTS (SELECT FROM nqc_miner_v1.import_identity
                 WHERE singleton AND contract='nqc-miner-postgres-import-v1') THEN
    RAISE EXCEPTION 'Miner journal importer identity missing';
  END IF;
END $$;

CREATE TABLE nqc_miner_v1.collections (
  parent_run_id text PRIMARY KEY REFERENCES nqc_miner_v1.runs(run_id),
  archive_id uuid NOT NULL,
  collection_key text NOT NULL UNIQUE CHECK (collection_key ~ '^[0-9a-f]{64}$'),
  collector_bytes bytea NOT NULL CHECK (octet_length(collector_bytes) BETWEEN 1 AND 65536),
  created_at timestamptz NOT NULL DEFAULT transaction_timestamp()
);
CREATE TABLE nqc_miner_v1.collection_windows (
  parent_run_id text NOT NULL REFERENCES nqc_miner_v1.collections(parent_run_id),
  window_index integer NOT NULL CHECK (window_index BETWEEN 0 AND 63),
  child_run_id text NOT NULL UNIQUE REFERENCES nqc_miner_v1.runs(run_id),
  journal_sha256 text NOT NULL CHECK (journal_sha256 ~ '^[0-9a-f]{64}$'),
  record_count integer NOT NULL CHECK (record_count BETWEEN 1 AND 10000),
  PRIMARY KEY (parent_run_id,window_index)
);
CREATE TABLE nqc_miner_v1.collection_receipts (
  parent_run_id text NOT NULL REFERENCES nqc_miner_v1.collections(parent_run_id),
  receipt_sequence integer NOT NULL CHECK (receipt_sequence BETWEEN 0 AND 9999),
  receipt_sha256 text NOT NULL CHECK (receipt_sha256 ~ '^[0-9a-f]{64}$'),
  snapshot_sha256 text NOT NULL CHECK (snapshot_sha256 ~ '^[0-9a-f]{64}$'),
  request_sha256 text NOT NULL CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
  source_status text NOT NULL CHECK (source_status IN ('verified_historical_snapshot','quarantined')),
  applied_status text NOT NULL CHECK (applied_status IN ('verified','quarantined')),
  original_receipt bytea NOT NULL CHECK (octet_length(original_receipt) BETWEEN 1 AND 65536),
  original_snapshot bytea NOT NULL CHECK (octet_length(original_snapshot) BETWEEN 1 AND 2097152),
  imported_at timestamptz NOT NULL DEFAULT transaction_timestamp(),
  PRIMARY KEY (parent_run_id,receipt_sequence)
);
-- One permanent parent tombstone blocks every linked window, including children
-- whose individual journal still verifies. Original child bytes are untouched.
CREATE TABLE nqc_miner_v1.collection_quarantine (
  parent_run_id text PRIMARY KEY REFERENCES nqc_miner_v1.collections(parent_run_id),
  reason text NOT NULL CHECK (reason IN ('parent_invalidated','control_quarantined',
    'member_quarantined','receipt_conflict','membership_conflict','collection_regressed','collector_conflict')),
  receipt_sha256 text NOT NULL CHECK (receipt_sha256 ~ '^[0-9a-f]{64}$'),
  control_journal_sha256 text NOT NULL CHECK (control_journal_sha256 ~ '^[0-9a-f]{64}$'),
  quarantined_at timestamptz NOT NULL DEFAULT transaction_timestamp()
);

CREATE FUNCTION nqc_miner_v1.import_verified_collection(p jsonb) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path=pg_catalog AS $collection$
DECLARE
  v_receipt jsonb; v_snapshot jsonb; v_control jsonb; v_journal jsonb; v_window jsonb; v_result jsonb;
  v_receipt_raw bytea; v_snapshot_raw bytea; v_marker bytea; v_raw bytea;
  v_parent text; v_key text; v_digest text; v_issue text; v_name text; v_prefix text; v_lock text;
  v_child text; v_revoked boolean; v_repeated boolean := false;
  v_index integer := 0; v_sequence integer; v_head integer; v_records integer := 0;
  v_bytes bigint := 0; v_added bigint := 0;
  v_existing nqc_miner_v1.collections%ROWTYPE;
  v_prior nqc_miner_v1.collection_receipts%ROWTYPE;
BEGIN
  IF current_database() <> 'nqc_miner_v1' OR current_setting('transaction_isolation') <> 'read committed'
      OR jsonb_typeof(p) IS DISTINCT FROM 'object' OR p->>'schema' IS DISTINCT FROM 'nqc-miner-postgres-collection-v1'
      OR octet_length(p::text)>33554432 OR jsonb_typeof(p->'windows') IS DISTINCT FROM 'array'
      OR jsonb_array_length(p->'windows')>64
      OR NOT EXISTS (SELECT FROM nqc_miner_v1.import_identity WHERE singleton AND database_id::text=p->>'database_id')
      OR (p->>'archive_id' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS DISTINCT FROM true
      OR p->>'archive_id'='00000000-0000-0000-0000-000000000000' THEN
    RAISE EXCEPTION 'Invalid collection environment, identity or bounds';
  END IF;
  v_control := p->'control'; v_parent := v_control->'owner'->>'run_id';
  IF (v_parent ~ '^[a-z0-9_-]{1,96}$') IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'Invalid collection parent';
  END IF;
  v_key := encode(sha256(convert_to('["nqc_miner_v1","historical","'||v_parent||'"]','UTF8')),'hex');
  v_digest := encode(sha256(convert_to(p::text,'UTF8')),'hex');
  v_receipt_raw := decode(p->>'receipt_hex','hex');
  v_snapshot_raw := decode(p->>'snapshot_hex','hex');
  v_marker := decode(p->>'collector_hex','hex');
  IF (octet_length(v_receipt_raw) BETWEEN 1 AND 65536) IS DISTINCT FROM true
      OR (octet_length(v_snapshot_raw) BETWEEN 1 AND 2097152) IS DISTINCT FROM true
      OR (octet_length(v_marker) BETWEEN 1 AND 65536) IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'Invalid collection evidence size';
  END IF;
  v_receipt := convert_from(v_receipt_raw,'UTF8')::jsonb;
  v_snapshot := convert_from(v_snapshot_raw,'UTF8')::jsonb;
  v_sequence := (v_receipt->>'sequence')::integer;
  v_revoked := v_receipt->>'status'='quarantined';
  IF v_receipt->>'schema' IS DISTINCT FROM 'nqc-miner-archive-receipt-v2'
      OR v_receipt->>'archive_id' IS DISTINCT FROM p->>'archive_id'
      OR (v_sequence BETWEEN 0 AND 9999) IS DISTINCT FROM true
      OR v_receipt->'sequence' IS DISTINCT FROM to_jsonb(v_sequence)
      OR v_receipt->>'collection_key' IS DISTINCT FROM v_key
      OR (v_receipt->>'previous_sha256' ~ '^[0-9a-f]{64}$') IS DISTINCT FROM true
      OR convert_from(decode(p->>'receipt_fields_hex','hex'),'UTF8')::jsonb IS DISTINCT FROM v_receipt-'sha256'
      OR encode(sha256(decode(p->>'receipt_fields_hex','hex')),'hex') IS DISTINCT FROM v_receipt->>'sha256'
      OR encode(sha256(v_snapshot_raw),'hex') IS DISTINCT FROM v_receipt->>'snapshot_sha256'
      OR v_snapshot->>'schema' IS DISTINCT FROM 'nqc-miner-collection-snapshot-v1'
      OR v_snapshot->>'collection_key' IS DISTINCT FROM v_key
      OR v_snapshot->'owner' IS DISTINCT FROM v_control->'owner'
      OR v_snapshot->>'status' IS DISTINCT FROM v_receipt->>'status'
      OR (v_receipt->>'status' IN ('verified_historical_snapshot','quarantined')) IS DISTINCT FROM true
      OR convert_from(v_marker,'UTF8')::jsonb IS DISTINCT FROM jsonb_build_object(
          'schema','nqc-miner-collector-v1','plan_sha256',v_control->'owner'->>'config_sha256')
      OR v_snapshot->'observer_bridge_enabled' IS DISTINCT FROM 'false'::jsonb
      OR v_snapshot->'remote_upload_enabled' IS DISTINCT FROM 'false'::jsonb
      OR v_snapshot->'authenticity_verified' IS DISTINCT FROM 'false'::jsonb
      OR v_snapshot->'economic_certification' IS DISTINCT FROM 'false'::jsonb
      OR jsonb_typeof(v_snapshot->'source_files') IS DISTINCT FROM 'object'
      OR (SELECT count(*) FROM jsonb_object_keys(v_snapshot->'source_files')) <> 4+3*jsonb_array_length(p->'windows')
      OR (v_revoked AND jsonb_array_length(p->'windows')<>0)
      OR (NOT v_revoked AND jsonb_array_length(p->'windows')=0) THEN
    RAISE EXCEPTION 'Collection receipt, snapshot or marker mismatch';
  END IF;
  -- Validate all member bindings before acquiring locks or making any writes.
  FOR v_index IN -1..jsonb_array_length(p->'windows')-1 LOOP
    IF v_index=-1 THEN
      v_journal := v_control; v_prefix := '';
    ELSE
      v_window := p->'windows'->v_index; v_journal := v_window->'journal';
      v_prefix := 'window-'||lpad(v_index::text,20,'0')||'/';
      v_child := 'window-'||encode(sha256(convert_to((v_control->'owner'->>'config_sha256')||':'||v_index::text,'UTF8')),'hex');
      IF v_window->'index' IS DISTINCT FROM to_jsonb(v_index)
          OR v_journal->'owner'->>'run_id' IS DISTINCT FROM v_child THEN
        RAISE EXCEPTION 'Foreign or noncontiguous collection window';
      END IF;
    END IF;
    IF v_journal->>'schema' IS DISTINCT FROM 'nqc-miner-postgres-import-v1'
        OR v_journal->>'database_id' IS DISTINCT FROM p->>'database_id'
        OR v_journal->'owner'->>'data_class' IS DISTINCT FROM 'historical'
        OR jsonb_typeof(v_journal->'records') IS DISTINCT FROM 'array'
        OR (v_index>=0 AND jsonb_array_length(v_journal->'records')=0) THEN
      RAISE EXCEPTION 'Foreign collection journal';
    END IF;
    v_records := v_records + jsonb_array_length(v_journal->'records');
    FOR v_name,v_raw IN SELECT x.name,x.bytes FROM (VALUES
        ('owner.json',decode(v_journal->>'original_owner_hex','hex')),
        ('config.json',decode(v_journal->>'original_config_hex','hex')),
        ('events.jsonl',(SELECT coalesce(string_agg(decode(r.value->>'raw_line_hex','hex'),''::bytea ORDER BY r.ordinality),''::bytea)
                         FROM jsonb_array_elements(v_journal->'records') WITH ORDINALITY r(value,ordinality)))
        ) x(name,bytes) LOOP
      IF v_snapshot->'source_files'->(v_prefix||v_name) IS DISTINCT FROM
          jsonb_build_object('bytes',octet_length(v_raw),'sha256',encode(sha256(v_raw),'hex')) THEN
        RAISE EXCEPTION 'Collection source bytes differ from sealed snapshot';
      END IF;
      IF v_name='events.jsonl' THEN v_bytes := v_bytes+octet_length(v_raw); END IF;
    END LOOP;
  END LOOP;
  IF v_records>10000 OR v_bytes>4194304
      OR v_snapshot->'source_files'->'collector.json' IS DISTINCT FROM
        jsonb_build_object('bytes',octet_length(v_marker),'sha256',encode(sha256(v_marker),'hex'))
      OR (NOT v_revoked AND jsonb_array_length(v_control->'records')<>0)
      OR (v_revoked AND (jsonb_array_length(v_control->'records')=0 OR EXISTS (
          SELECT FROM jsonb_array_elements(v_control->'records') x WHERE x->>'record_kind'<>'invalidated'))) THEN
    RAISE EXCEPTION 'Invalid collection control or aggregate bounds';
  END IF;

  PERFORM pg_advisory_xact_lock(hashtext('nqc_miner_v1.collection.v1'),hashtext(v_parent));
  -- Same run locks as the individual importer, ordered by actual lock key.
  FOR v_lock IN SELECT rid FROM (
      SELECT v_parent AS rid UNION SELECT x->'journal'->'owner'->>'run_id' FROM jsonb_array_elements(p->'windows') x
      UNION SELECT w.child_run_id FROM nqc_miner_v1.collection_windows w WHERE w.parent_run_id=v_parent
      ) locks ORDER BY hashtext(rid),rid LOOP
    PERFORM pg_advisory_xact_lock(hashtext('nqc_miner_v1.import.v1'),hashtext(v_lock));
  END LOOP;
  SELECT * INTO v_existing FROM nqc_miner_v1.collections c WHERE c.parent_run_id=v_parent;
  IF FOUND THEN
    IF v_existing.archive_id::text <> p->>'archive_id' THEN
      RAISE EXCEPTION 'Collection belongs to a different archive UUID';
    END IF;
    IF EXISTS (SELECT FROM nqc_miner_v1.collection_quarantine q WHERE q.parent_run_id=v_parent) THEN
      RETURN jsonb_build_object('status','quarantined','parent_run_id',v_parent,'inserted',0);
    END IF;
    IF v_existing.collector_bytes <> v_marker OR v_existing.collection_key<>v_key THEN v_issue:='collector_conflict'; END IF;
    SELECT * INTO v_prior FROM nqc_miner_v1.collection_receipts r
      WHERE r.parent_run_id=v_parent AND r.receipt_sequence=v_sequence;
    IF FOUND THEN
      v_repeated := true;
      IF v_prior.request_sha256<>v_digest THEN v_issue:='receipt_conflict'; END IF;
    END IF;
    SELECT max(r.receipt_sequence) INTO v_head FROM nqc_miner_v1.collection_receipts r WHERE r.parent_run_id=v_parent;
    IF v_issue IS NULL AND v_sequence<v_head AND NOT v_revoked THEN
      RETURN jsonb_build_object('status','stale','parent_run_id',v_parent,'inserted',0);
    END IF;
    IF NOT v_revoked AND jsonb_array_length(p->'windows') <
        (SELECT count(*) FROM nqc_miner_v1.collection_windows w WHERE w.parent_run_id=v_parent) THEN
      v_issue := coalesce(v_issue,'collection_regressed');
    END IF;
  END IF;
  IF v_issue IS NULL THEN
    v_result := nqc_miner_v1.import_verified_journal(v_control);
    v_added := v_added+(v_result->>'inserted')::bigint;
    IF v_existing.parent_run_id IS NULL THEN
      INSERT INTO nqc_miner_v1.collections(parent_run_id,archive_id,collection_key,collector_bytes)
        VALUES(v_parent,(p->>'archive_id')::uuid,v_key,v_marker);
    END IF;
    IF v_revoked THEN v_issue:='parent_invalidated';
    ELSIF v_result->>'status'='quarantined' THEN v_issue:='control_quarantined';
    ELSE
      FOR v_window IN SELECT value FROM jsonb_array_elements(p->'windows') LOOP
        v_journal:=v_window->'journal'; v_index:=(v_window->>'index')::integer;
        v_child:=v_journal->'owner'->>'run_id';
        v_result:=nqc_miner_v1.import_verified_journal(v_journal);
        v_added:=v_added+(v_result->>'inserted')::bigint;
        IF v_result->>'status'='quarantined' THEN v_issue:=coalesce(v_issue,'member_quarantined'); END IF;
        IF EXISTS (SELECT FROM nqc_miner_v1.collection_windows w WHERE w.parent_run_id=v_parent AND w.window_index=v_index) THEN
          IF NOT EXISTS (SELECT FROM nqc_miner_v1.collection_windows w WHERE w.parent_run_id=v_parent AND w.window_index=v_index
              AND w.child_run_id=v_child AND w.journal_sha256=v_journal->>'journal_sha256'
              AND w.record_count=jsonb_array_length(v_journal->'records')) THEN
            v_issue:=coalesce(v_issue,'membership_conflict');
          END IF;
        ELSE
          INSERT INTO nqc_miner_v1.collection_windows(parent_run_id,window_index,child_run_id,journal_sha256,record_count)
            VALUES(v_parent,v_index,v_child,v_journal->>'journal_sha256',jsonb_array_length(v_journal->'records'));
        END IF;
      END LOOP;
    END IF;
  END IF;
  IF v_issue IS NOT NULL THEN
    INSERT INTO nqc_miner_v1.collection_quarantine(parent_run_id,reason,receipt_sha256,control_journal_sha256)
      VALUES(v_parent,v_issue,v_receipt->>'sha256',v_control->>'journal_sha256');
  END IF;
  IF NOT v_repeated THEN
    INSERT INTO nqc_miner_v1.collection_receipts(parent_run_id,receipt_sequence,receipt_sha256,snapshot_sha256,
        request_sha256,source_status,applied_status,original_receipt,original_snapshot)
      VALUES(v_parent,v_sequence,v_receipt->>'sha256',v_receipt->>'snapshot_sha256',v_digest,v_receipt->>'status',
             CASE WHEN v_issue IS NULL THEN 'verified' ELSE 'quarantined' END,v_receipt_raw,v_snapshot_raw);
  END IF;
  RETURN jsonb_build_object('status',CASE WHEN v_issue IS NOT NULL THEN 'quarantined'
          WHEN v_repeated AND v_added=0 THEN 'idempotent' ELSE 'imported' END,
          'parent_run_id',v_parent,'inserted',v_added,'reason',v_issue,'receipt_sequence',v_sequence);
END
$collection$;

-- Mandatory collection read boundary. Raw tables are retained audit evidence.
-- A parent revocation removes ALL its windows from these views atomically.
CREATE VIEW nqc_miner_v1.eligible_collection_ledger WITH (security_invoker=true,security_barrier=true) AS
SELECT w.parent_run_id,w.window_index,l.* FROM nqc_miner_v1.collection_windows w
JOIN nqc_miner_v1.journal_ledger l ON l.run_id=w.child_run_id
WHERE NOT EXISTS (SELECT FROM nqc_miner_v1.collection_quarantine q WHERE q.parent_run_id=w.parent_run_id)
  AND NOT EXISTS (SELECT FROM nqc_miner_v1.import_quarantine q WHERE q.run_id=w.parent_run_id)
  AND NOT EXISTS (SELECT FROM nqc_miner_v1.collection_windows siblings
                  JOIN nqc_miner_v1.import_quarantine q ON q.run_id=siblings.child_run_id
                  WHERE siblings.parent_run_id=w.parent_run_id)
  AND EXISTS (SELECT FROM nqc_miner_v1.collection_receipts r WHERE r.parent_run_id=w.parent_run_id AND r.applied_status='verified');
CREATE VIEW nqc_miner_v1.eligible_collection_outbox WITH (security_invoker=true,security_barrier=true) AS
SELECT l.parent_run_id,l.window_index,o.* FROM nqc_miner_v1.eligible_collection_ledger l
JOIN nqc_miner_v1.outbox o ON o.run_id=l.run_id AND o.sequence=l.sequence
  AND o.envelope_sha256=l.envelope_sha256 AND o.payload=l.raw_line;
REVOKE ALL ON nqc_miner_v1.collections,nqc_miner_v1.collection_windows,nqc_miner_v1.collection_receipts,
  nqc_miner_v1.collection_quarantine,nqc_miner_v1.eligible_collection_ledger,nqc_miner_v1.eligible_collection_outbox FROM PUBLIC;
REVOKE ALL ON FUNCTION nqc_miner_v1.import_verified_collection(jsonb) FROM PUBLIC;
COMMIT;
