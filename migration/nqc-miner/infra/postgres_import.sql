-- Candidate importer migration. Runtime audit is pending; no deployment implied.
-- Install once as the dedicated schema owner, after postgres.sql, in a NEW
-- reviewed Miner instance. No role grants, connection settings or external I/O.
BEGIN;
SET LOCAL search_path = pg_catalog;
DO $$ BEGIN
  IF current_database() <> 'nqc_miner_v1' OR NOT EXISTS (
      SELECT FROM pg_namespace WHERE nspname = 'nqc_miner_v1'
      AND nspowner = current_user::regrole) THEN
    RAISE EXCEPTION 'Miner importer requires its dedicated database and schema owner';
  END IF;
END $$;

CREATE TABLE nqc_miner_v1.import_identity (
  singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
  database_id uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  contract text NOT NULL DEFAULT 'nqc-miner-postgres-import-v1'
    CHECK (contract = 'nqc-miner-postgres-import-v1')
);
INSERT INTO nqc_miner_v1.import_identity(singleton) VALUES (true);

-- Permanent, append-only revocation. Readers must anti-join this table.
-- Deleting the row to reactivate a run is not an authorized recovery action.
CREATE TABLE nqc_miner_v1.import_quarantine (
  run_id text PRIMARY KEY REFERENCES nqc_miner_v1.runs(run_id),
  reason text NOT NULL CHECK (reason IN
    ('owner_conflict', 'journal_conflict', 'database_gap', 'outbox_conflict', 'journal_invalidated')),
  incoming_owner_sha256 text NOT NULL CHECK (incoming_owner_sha256 ~ '^[0-9a-f]{64}$'),
  incoming_journal_sha256 text NOT NULL CHECK (incoming_journal_sha256 ~ '^[0-9a-f]{64}$'),
  quarantined_at timestamptz NOT NULL DEFAULT transaction_timestamp()
);

CREATE FUNCTION nqc_miner_v1.import_verified_journal(p jsonb) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY INVOKER SET search_path = pg_catalog AS $miner$
DECLARE
  own jsonb; cfg jsonb; item jsonb; parsed jsonb;
  rid text; klass text; oh text; jh text; previous text := repeat('0',64);
  raw bytea; original_owner bytea; original_config bytea; all_raw bytea := ''::bytea;
  rows_count integer := 0; db_count bigint; added bigint := 0; issue text;
  prior nqc_miner_v1.runs%ROWTYPE;
BEGIN
  IF current_database() <> 'nqc_miner_v1' OR current_setting('transaction_isolation') <> 'read committed' THEN
    RAISE EXCEPTION 'Miner import requires dedicated database and READ COMMITTED';
  END IF;
  IF jsonb_typeof(p) IS DISTINCT FROM 'object' OR p->>'schema' IS DISTINCT FROM 'nqc-miner-postgres-import-v1'
      OR jsonb_typeof(p->'records') IS DISTINCT FROM 'array' OR octet_length(p::text) > 33554432 THEN
    RAISE EXCEPTION 'Invalid or oversized Miner import request';
  END IF;
  IF NOT EXISTS (SELECT FROM nqc_miner_v1.import_identity
      WHERE singleton AND database_id::text = p->>'database_id' AND contract = p->>'schema') THEN
    RAISE EXCEPTION 'Miner database UUID mismatch';
  END IF;
  own := p->'owner'; rid := own->>'run_id'; klass := own->>'data_class';
  oh := p->>'owner_sha256'; jh := p->>'journal_sha256';
  IF jsonb_typeof(own) IS DISTINCT FROM 'object' OR own->>'schema' IS DISTINCT FROM 'nqc-miner-owner-v2'
      OR own->>'namespace' IS DISTINCT FROM 'nqc_miner_v1' OR own->>'producer' IS DISTINCT FROM 'nqc-miner'
      OR (rid ~ '^[a-z0-9_-]{1,96}$') IS DISTINCT FROM true
      OR (klass IN ('synthetic','historical','shadow')) IS DISTINCT FROM true
      OR (own->>'build_identity_sha256' ~ '^[0-9a-f]{64}$') IS DISTINCT FROM true
      OR (oh ~ '^[0-9a-f]{64}$') IS DISTINCT FROM true
      OR (jh ~ '^[0-9a-f]{64}$') IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'Foreign or invalid Miner owner';
  END IF;
  original_owner := decode(p->>'original_owner_hex', 'hex');
  original_config := decode(p->>'original_config_hex', 'hex');
  cfg := convert_from(original_config, 'UTF8')::jsonb;
  IF (octet_length(original_owner) BETWEEN 1 AND 65536) IS DISTINCT FROM true
      OR (octet_length(original_config) BETWEEN 1 AND 1048576) IS DISTINCT FROM true
      OR convert_from(original_owner, 'UTF8')::jsonb IS DISTINCT FROM own
      OR convert_from(decode(p->>'canonical_owner_hex','hex'),'UTF8')::jsonb IS DISTINCT FROM own
      OR encode(sha256(decode(p->>'canonical_owner_hex','hex')),'hex') IS DISTINCT FROM oh
      OR cfg->>'namespace' IS DISTINCT FROM 'nqc_miner_v1' OR cfg->>'producer' IS DISTINCT FROM 'nqc-miner'
      OR cfg->>'run_id' IS DISTINCT FROM rid OR cfg->>'data_class' IS DISTINCT FROM klass
      OR cfg->>'code_commit' IS DISTINCT FROM own->>'code_commit'
      OR cfg->>'cargo_lock_sha256' IS DISTINCT FROM own->>'cargo_lock_sha256'
      OR cfg->>'build_identity_sha256' IS DISTINCT FROM own->>'build_identity_sha256'
      OR cfg->'observer_bridge_enabled' IS DISTINCT FROM 'false'::jsonb
      OR cfg->'signing_enabled' IS DISTINCT FROM 'false'::jsonb
      OR cfg->'gas_budget_mxn_centavos' IS DISTINCT FROM '0'::jsonb THEN
    RAISE EXCEPTION 'Miner original bytes or controls do not match owner';
  END IF;
  -- Verify transport and order again. Rust remains the ABI/hash-chain authority;
  -- a caller able to INSERT directly is trusted and cannot self-certify markets.
  FOR item IN SELECT value FROM jsonb_array_elements(p->'records') LOOP
    raw := decode(item->>'raw_line_hex', 'hex');
    IF (octet_length(raw) BETWEEN 1 AND 1048577) IS DISTINCT FROM true
        OR get_byte(raw,octet_length(raw)-1) IS DISTINCT FROM 10 THEN
      RAISE EXCEPTION 'Invalid Miner line size/newline';
    END IF;
    parsed := convert_from(raw,'UTF8')::jsonb;
    IF item->'sequence' IS DISTINCT FROM to_jsonb(rows_count)
        OR parsed->'sequence' IS DISTINCT FROM item->'sequence'
        OR parsed->>'owner_sha256' IS DISTINCT FROM oh
        OR item->>'previous_sha256' IS DISTINCT FROM previous
        OR parsed->>'previous_sha256' IS DISTINCT FROM previous
        OR (item->>'envelope_sha256' ~ '^[0-9a-f]{64}$') IS DISTINCT FROM true
        OR parsed->>'sha256' IS DISTINCT FROM item->>'envelope_sha256'
        OR parsed->'record'->>'kind' IS DISTINCT FROM item->>'record_kind'
        OR (item->>'record_kind' IN ('observed','chunk_completed','scope_completed','invalidated')) IS DISTINCT FROM true
        OR encode(sha256(raw),'hex') IS DISTINCT FROM item->>'raw_line_sha256' THEN
      RAISE EXCEPTION 'Miner transported record does not match verified metadata';
    END IF;
    rows_count := rows_count + 1;
    all_raw := all_raw || raw;
    IF rows_count > 10000 OR octet_length(all_raw) > 4194304 THEN
      RAISE EXCEPTION 'Miner import bounds exceeded';
    END IF;
    previous := item->>'envelope_sha256';
  END LOOP;
  IF encode(sha256(all_raw),'hex') IS DISTINCT FROM jh THEN
    RAISE EXCEPTION 'Miner journal transport hash mismatch';
  END IF;

  -- One transaction lock per run, including first insertion; hash collisions
  -- only serialize unrelated Miner runs. Reads occur after lock acquisition.
  PERFORM pg_advisory_xact_lock(hashtext('nqc_miner_v1.import.v1'), hashtext(rid));
  SELECT * INTO prior FROM nqc_miner_v1.runs WHERE run_id = rid;
  IF FOUND THEN
    IF (prior.namespace, prior.producer, prior.data_class, prior.owner_sha256,
        prior.config_sha256, prior.code_commit, prior.cargo_lock_sha256,
        prior.original_owner, prior.original_config) IS DISTINCT FROM
       ('nqc_miner_v1'::text,'nqc-miner'::text,klass,oh,own->>'config_sha256',
        own->>'code_commit',own->>'cargo_lock_sha256',original_owner,original_config) THEN
      issue := 'owner_conflict';
    END IF;
  ELSE
    INSERT INTO nqc_miner_v1.runs(run_id,data_class,owner_sha256,config_sha256,
        code_commit,cargo_lock_sha256,original_owner,original_config)
    VALUES(rid,klass,oh,own->>'config_sha256',own->>'code_commit',own->>'cargo_lock_sha256',
        original_owner,original_config);
  END IF;
  IF EXISTS (SELECT FROM nqc_miner_v1.import_quarantine WHERE run_id = rid) THEN
    RETURN jsonb_build_object('status','quarantined','run_id',rid,'inserted',0,'journal_sha256',jh);
  END IF;
  SELECT count(*) INTO db_count FROM nqc_miner_v1.journal_ledger WHERE run_id = rid;
  IF issue IS NULL AND (SELECT coalesce(max(sequence),-1) <> db_count - 1
      FROM nqc_miner_v1.journal_ledger WHERE run_id = rid) THEN
    issue := 'database_gap';
  END IF;
  IF issue IS NULL AND (db_count <> (SELECT count(*) FROM nqc_miner_v1.outbox WHERE run_id = rid)
      OR EXISTS (SELECT FROM nqc_miner_v1.journal_ledger l LEFT JOIN nqc_miner_v1.outbox o
          ON o.run_id=l.run_id AND o.sequence=l.sequence
          WHERE l.run_id=rid AND (o.run_id IS NULL
            OR (o.data_class,o.envelope_sha256,o.topic,o.message_key,o.payload,o.delivery_enabled,o.delivered_at)
              IS DISTINCT FROM (klass,l.envelope_sha256,'nqc_miner_v1.'||klass||'.ledger.v1',
                'nqc_miner_v1/'||klass||'/'||rid,l.raw_line,false,NULL::timestamptz)))) THEN
    issue := 'outbox_conflict';
  END IF;
  IF issue IS NULL AND EXISTS (
      SELECT FROM jsonb_array_elements(p->'records') x
      JOIN nqc_miner_v1.journal_ledger l ON l.run_id=rid AND l.sequence=(x->>'sequence')::numeric
      WHERE (l.data_class,l.owner_sha256,l.previous_sha256,l.envelope_sha256,l.raw_line_sha256,l.record_kind,l.raw_line)
        IS DISTINCT FROM (klass,oh,x->>'previous_sha256',x->>'envelope_sha256',x->>'raw_line_sha256',
          x->>'record_kind',decode(x->>'raw_line_hex','hex'))) THEN
    issue := 'journal_conflict';
  END IF;
  IF issue IS NOT NULL THEN
    INSERT INTO nqc_miner_v1.import_quarantine(run_id,reason,incoming_owner_sha256,incoming_journal_sha256)
    VALUES(rid,issue,oh,jh);
    -- Return, do not raise: the caller must COMMIT this durable quarantine.
    RETURN jsonb_build_object('status','quarantined','reason',issue,'run_id',rid,'inserted',0,'journal_sha256',jh);
  END IF;
  INSERT INTO nqc_miner_v1.journal_ledger(run_id,data_class,owner_sha256,sequence,previous_sha256,
      envelope_sha256,raw_line_sha256,record_kind,raw_line)
  SELECT rid,klass,oh,(x->>'sequence')::numeric,x->>'previous_sha256',x->>'envelope_sha256',
      x->>'raw_line_sha256',x->>'record_kind',decode(x->>'raw_line_hex','hex')
    FROM jsonb_array_elements(p->'records') x WHERE (x->>'sequence')::numeric >= db_count;
  GET DIAGNOSTICS added = ROW_COUNT;
  INSERT INTO nqc_miner_v1.outbox(run_id,data_class,sequence,envelope_sha256,topic,message_key,payload)
  SELECT rid,klass,(x->>'sequence')::numeric,x->>'envelope_sha256',
      'nqc_miner_v1.'||klass||'.ledger.v1','nqc_miner_v1/'||klass||'/'||rid,decode(x->>'raw_line_hex','hex')
    FROM jsonb_array_elements(p->'records') x WHERE (x->>'sequence')::numeric >= db_count;
  IF EXISTS (SELECT FROM jsonb_array_elements(p->'records') x WHERE x->>'record_kind'='invalidated') THEN
    INSERT INTO nqc_miner_v1.import_quarantine(run_id,reason,incoming_owner_sha256,incoming_journal_sha256)
    VALUES(rid,'journal_invalidated',oh,jh);
    RETURN jsonb_build_object('status','quarantined','reason','journal_invalidated',
        'run_id',rid,'inserted',added,'journal_sha256',jh);
  END IF;
  RETURN jsonb_build_object('status',CASE WHEN added=0 THEN 'idempotent' ELSE 'imported' END,
      'run_id',rid,'inserted',added,'stored_records',db_count+added,'journal_sha256',jh);
END
$miner$;

REVOKE ALL ON nqc_miner_v1.import_identity,nqc_miner_v1.import_quarantine FROM PUBLIC;
REVOKE ALL ON FUNCTION nqc_miner_v1.import_verified_journal(jsonb) FROM PUBLIC;
COMMIT;
-- Read this UUID for --database-id. Never infer ownership from the DB name alone.
SELECT database_id FROM nqc_miner_v1.import_identity WHERE singleton;
