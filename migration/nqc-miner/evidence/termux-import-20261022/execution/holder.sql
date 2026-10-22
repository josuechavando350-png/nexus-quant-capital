-- The parent waits for this transaction's granted lock before starting clients.
-- Release only after both real importer sessions are blocked on advisory locks.
DO $$ DECLARE attempt integer; BEGIN
  PERFORM pg_advisory_xact_lock(hashtext('nqc_miner_v1.import.v1'),hashtext('pgimp_concurrent'));
  FOR attempt IN 1..400 LOOP
    PERFORM pg_stat_clear_snapshot();
    IF (SELECT count(*)=2 FROM pg_stat_activity
        WHERE application_name IN ('nqc_miner_import_waiter_1','nqc_miner_import_waiter_2')
          AND datname='nqc_miner_v1' AND wait_event_type='Lock' AND wait_event='advisory') THEN
      RAISE NOTICE 'MINER_IMPORT_BOTH_WAITERS_BLOCKED';
      RETURN;
    END IF;
    PERFORM pg_sleep(0.05);
  END LOOP;
  RAISE EXCEPTION 'Both importers did not block before the deadline';
END $$;
