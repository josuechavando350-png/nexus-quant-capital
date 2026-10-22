#!/usr/bin/env bash
# Self-contained synthetic Miner importer test. No downloads or existing DBs.
set -euo pipefail
umask 077
if [[ $(id -u) == 0 || ${PREFIX:-} != /data/data/com.termux/files/usr || $HOME != /data/data/com.termux/files/home ]]; then
  printf 'REJECTED: use ordinary native Termux, without root.\n' >&2
  exit 2
fi
for executable in initdb pg_ctl psql createdb sha256sum tar mktemp cmp gzip base64 grep; do
  command -v "$executable" >/dev/null
done
[[ $(psql --version) == 'psql (PostgreSQL) 18.6' ]]
unset PGHOST PGHOSTADDR PGPORT PGDATABASE PGUSER PGDATA PGSERVICE PGSERVICEFILE PGOPTIONS PGAPPNAME
export PGCONNECT_TIMEOUT=10 PSQL_PAGER=cat
MINER_TEST_ROOT=$(mktemp -d "$HOME/nqc-miner-import.XXXXXX")
MINER_TEST_USER=$(id -un)
MINER_TEST_STARTED=0
MINER_TEST_CHILDREN=()
mkdir "$MINER_TEST_ROOT/evidence" "$MINER_TEST_ROOT/s"
MINER_TEST_EVIDENCE="$MINER_TEST_ROOT/evidence"
export PGPASSFILE="$MINER_TEST_ROOT/no-password-file"
printf 'MINER: prueba en una instancia nueva; puede tardar unos minutos.\nEvidence: %s\n' "$MINER_TEST_EVIDENCE"
finish() {
  local rc=$? result=failed archive destination
  trap - EXIT
  set +e
  if [[ $MINER_TEST_STARTED == 1 ]]; then
    pg_ctl -D "$MINER_TEST_ROOT/data" -m fast -w -t 30 stop >> "$MINER_TEST_EVIDENCE/shutdown.log" 2>&1
    if [[ $? != 0 ]]; then rc=1; fi
  fi
  for child in "${MINER_TEST_CHILDREN[@]}"; do wait "$child" 2>/dev/null; done
  if [[ $rc == 0 ]]; then result=pass; fi
  printf '{"schema":"nqc-miner-import-contract-check-v1","status":"%s","data_class":"synthetic","production_integration":false,"observer_bridge_enabled":false,"spending_authorized":false}\n' "$result" > "$MINER_TEST_EVIDENCE/result.json"
  (cd "$MINER_TEST_EVIDENCE" && sha256sum ./* > ../SHA256SUMS)
  if [[ $? != 0 ]]; then printf 'FAILED: cannot hash evidence\n' >&2; exit 1; fi
  mv "$MINER_TEST_ROOT/SHA256SUMS" "$MINER_TEST_EVIDENCE/SHA256SUMS"
  archive="$MINER_TEST_ROOT/nqc-miner-import-evidence.tar.gz"
  tar -czf "$archive" -C "$MINER_TEST_ROOT" evidence
  if [[ $? != 0 ]]; then printf 'FAILED: cannot package evidence\n' >&2; exit 1; fi
  printf '\nMINER IMPORT: %s\nResults: %s\n' "$result" "$archive"
  if [[ -d /sdcard/Download && -w /sdcard/Download ]]; then
    destination=$(mktemp /sdcard/Download/nqc-miner-import-evidence.XXXXXX.tar.gz)
    if [[ -n $destination ]] && cp -- "$archive" "$destination" && cmp -- "$archive" "$destination"; then
      printf 'ADJUNTA ESTE ARCHIVO AL CHAT: %s\n' "$destination"
      sha256sum "$destination"
    else
      printf 'No se pudo copiar a Descargas; se conserva el archivo Results.\n' >&2
    fi
  fi
  exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
date -u +%FT%TZ > "$MINER_TEST_EVIDENCE/started-at.txt"
psql --version > "$MINER_TEST_EVIDENCE/client-version.txt"
uname -m > "$MINER_TEST_EVIDENCE/architecture.txt"
sha256sum "$0" > "$MINER_TEST_EVIDENCE/runner.sha256"
__EMBEDDED_INPUTS__
(cd "$MINER_TEST_EVIDENCE" && sha256sum -c input.sha256)
initdb -D "$MINER_TEST_ROOT/data" -U "$MINER_TEST_USER" --encoding=UTF8 --locale=C \
  --auth-local=peer --auth-host=reject > "$MINER_TEST_EVIDENCE/initdb.log" 2>&1
cat >> "$MINER_TEST_ROOT/data/postgresql.conf" <<EOF
listen_addresses = ''
unix_socket_directories = '$MINER_TEST_ROOT/s'
unix_socket_permissions = 0700
port = 55433
shared_buffers = '32MB'
max_connections = 10
max_parallel_workers = 0
EOF
cp "$MINER_TEST_ROOT/data/postgresql.conf" "$MINER_TEST_ROOT/data/pg_hba.conf" "$MINER_TEST_EVIDENCE/"
MINER_TEST_STARTED=1
pg_ctl -D "$MINER_TEST_ROOT/data" -l "$MINER_TEST_EVIDENCE/server.log" -w -t 60 start > "$MINER_TEST_EVIDENCE/startup.log" 2>&1
export PGOPTIONS='-c statement_timeout=90000 -c lock_timeout=30000'
MINER_TEST_PSQL=(psql -X -w -h "$MINER_TEST_ROOT/s" -p 55433 -U "$MINER_TEST_USER" -v ON_ERROR_STOP=1 -v VERBOSITY=verbose -P pager=off)
"${MINER_TEST_PSQL[@]}" -d postgres -c 'CREATE ROLE nqc_miner_import_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION; CREATE ROLE nqc_miner_import_writer NOLOGIN NOSUPERUSER; CREATE ROLE nqc_miner_import_outsider NOLOGIN NOSUPERUSER;' > "$MINER_TEST_EVIDENCE/roles.log" 2>&1
createdb -w -h "$MINER_TEST_ROOT/s" -p 55433 -U "$MINER_TEST_USER" --maintenance-db=postgres -O nqc_miner_import_owner nqc_miner_v1 > "$MINER_TEST_EVIDENCE/database.log" 2>&1
"${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -c 'SET ROLE nqc_miner_import_owner' -f "$MINER_TEST_EVIDENCE/postgres.sql" > "$MINER_TEST_EVIDENCE/apply-base.log" 2>&1
if "${MINER_TEST_PSQL[@]}" -d postgres -c 'SET ROLE nqc_miner_import_owner' -f "$MINER_TEST_EVIDENCE/postgres_import.sql" > "$MINER_TEST_EVIDENCE/wrong-database.log" 2>&1; then
  printf 'FAILED: importer accepted foreign database\n' >&2; exit 1
fi
grep -q 'ERROR:  *P0001' "$MINER_TEST_EVIDENCE/wrong-database.log"
"${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -c 'SET ROLE nqc_miner_import_owner' -f "$MINER_TEST_EVIDENCE/postgres_import.sql" > "$MINER_TEST_EVIDENCE/apply-importer.log" 2>&1
if "${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -c 'SET ROLE nqc_miner_import_owner' -f "$MINER_TEST_EVIDENCE/postgres_import.sql" > "$MINER_TEST_EVIDENCE/duplicate-importer.log" 2>&1; then
  printf 'FAILED: importer installation overwritten\n' >&2; exit 1
fi
grep -q 'ERROR:  *42P07' "$MINER_TEST_EVIDENCE/duplicate-importer.log"
"${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -f "$MINER_TEST_EVIDENCE/fixtures.sql" > "$MINER_TEST_EVIDENCE/fixtures.log" 2>&1
printf 'MINER: importacion, duplicados, cuarentena y rollback...\n'
"${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -f "$MINER_TEST_EVIDENCE/cases.sql" > "$MINER_TEST_EVIDENCE/cases.log" 2>&1
[[ $(grep -c 'MINER_IMPORT_PASS:' "$MINER_TEST_EVIDENCE/cases.log") == __EXPECTED_CASES__ ]]
for action in 'UPDATE nqc_miner_v1.journal_ledger SET sequence=sequence' 'DELETE FROM nqc_miner_v1.import_quarantine' 'TRUNCATE nqc_miner_v1.outbox' 'UPDATE nqc_miner_v1.import_identity SET database_id=database_id'; do
  if "${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -c 'SET ROLE nqc_miner_import_writer' -c "$action" >> "$MINER_TEST_EVIDENCE/writer-denials.log" 2>&1; then
    printf 'FAILED: limited writer changed existing evidence\n' >&2; exit 1
  fi
done
[[ $(grep -c 'ERROR:  *42501' "$MINER_TEST_EVIDENCE/writer-denials.log") == 4 ]]
if "${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -c 'SET ROLE nqc_miner_import_outsider' -c "SELECT nqc_miner_v1.import_verified_journal('{}'::jsonb)" > "$MINER_TEST_EVIDENCE/outsider-denial.log" 2>&1; then
  printf 'FAILED: outsider executed importer\n' >&2; exit 1
fi
grep -q 'ERROR:  *42501' "$MINER_TEST_EVIDENCE/outsider-denial.log"

query() { "${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -qAtc "$1"; }
wait_for_query() {
  local attempt
  for ((attempt=0;attempt<100;attempt++)); do
    if [[ $(query "$1") == t ]]; then return 0; fi
    sleep 0.1
  done
  printf 'FAILED: timed out waiting for owned test session\n' >&2
  return 1
}
printf 'MINER: dos importadores concurrentes...\n'
PGAPPNAME=nqc_miner_import_holder "${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -f "$MINER_TEST_EVIDENCE/holder.sql" > "$MINER_TEST_EVIDENCE/holder.log" 2>&1 &
MINER_HOLDER_PID=$!; MINER_TEST_CHILDREN+=("$MINER_HOLDER_PID")
wait_for_query "SELECT EXISTS(SELECT FROM pg_locks l JOIN pg_stat_activity a USING(pid) WHERE a.application_name='nqc_miner_import_holder' AND a.datname='nqc_miner_v1' AND l.locktype='advisory' AND l.granted)"
for index in 1 2; do
  PGAPPNAME="nqc_miner_import_waiter_$index" "${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -qAt -c 'SET ROLE nqc_miner_import_writer' \
    -c "SELECT nqc_miner_v1.import_verified_journal(payload) FROM nqc_miner_v1.test_inputs WHERE name='concurrent'" \
    > "$MINER_TEST_EVIDENCE/concurrent-$index.json" 2> "$MINER_TEST_EVIDENCE/concurrent-$index.stderr" &
  MINER_TEST_CHILDREN+=("$!")
done
wait "$MINER_HOLDER_PID"
wait "${MINER_TEST_CHILDREN[1]}"
wait "${MINER_TEST_CHILDREN[2]}"
grep -q 'MINER_IMPORT_BOTH_WAITERS_BLOCKED' "$MINER_TEST_EVIDENCE/holder.log"
[[ $(cat "$MINER_TEST_EVIDENCE/concurrent-1.json" "$MINER_TEST_EVIDENCE/concurrent-2.json" | grep -c '"status": "imported"') == 1 ]]
[[ $(cat "$MINER_TEST_EVIDENCE/concurrent-1.json" "$MINER_TEST_EVIDENCE/concurrent-2.json" | grep -c '"status": "idempotent"') == 1 ]]
[[ $(query "SELECT (SELECT count(*)=3 FROM nqc_miner_v1.journal_ledger WHERE run_id='pgimp_concurrent') AND (SELECT count(*)=3 FROM nqc_miner_v1.outbox WHERE run_id='pgimp_concurrent') AND NOT EXISTS(SELECT FROM nqc_miner_v1.import_quarantine WHERE run_id='pgimp_concurrent')") == t ]]
printf '{"status":"pass","blocked_importers":2,"committed_records":3,"committed_outbox":3}\n' > "$MINER_TEST_EVIDENCE/concurrency.json"

printf 'MINER: interrupcion de una sesion propia antes del commit...\n'
PGAPPNAME=nqc_miner_import_interrupt "${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -qAt -c 'SET ROLE nqc_miner_import_writer' \
  -c "BEGIN; SELECT nqc_miner_v1.import_verified_journal(payload) FROM nqc_miner_v1.test_inputs WHERE name='interrupt'; SELECT pg_sleep(60); COMMIT;" \
  > "$MINER_TEST_EVIDENCE/interrupted-client.log" 2>&1 &
MINER_INTERRUPT_PID=$!; MINER_TEST_CHILDREN+=("$MINER_INTERRUPT_PID")
wait_for_query "SELECT EXISTS(SELECT FROM pg_stat_activity WHERE application_name='nqc_miner_import_interrupt' AND datname='nqc_miner_v1' AND wait_event='PgSleep')"
query "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name='nqc_miner_import_interrupt' AND datname='nqc_miner_v1' AND wait_event='PgSleep'" > "$MINER_TEST_EVIDENCE/terminate-session.txt"
[[ $(cat "$MINER_TEST_EVIDENCE/terminate-session.txt") == t ]]
if wait "$MINER_INTERRUPT_PID"; then printf 'FAILED: interrupted transaction returned success\n' >&2; exit 1; fi
[[ $(query "SELECT NOT EXISTS(SELECT FROM nqc_miner_v1.runs WHERE run_id='pgimp_interrupt') AND NOT EXISTS(SELECT FROM nqc_miner_v1.journal_ledger WHERE run_id='pgimp_interrupt') AND NOT EXISTS(SELECT FROM nqc_miner_v1.outbox WHERE run_id='pgimp_interrupt')") == t ]]
"${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -qAt -c 'SET ROLE nqc_miner_import_writer' \
  -c "SELECT nqc_miner_v1.import_verified_journal(payload) FROM nqc_miner_v1.test_inputs WHERE name='interrupt'" \
  > "$MINER_TEST_EVIDENCE/interruption-retry.json" 2> "$MINER_TEST_EVIDENCE/interruption-retry.stderr"
grep -q '"status": "imported"' "$MINER_TEST_EVIDENCE/interruption-retry.json"
[[ $(query "SELECT (SELECT count(*)=3 FROM nqc_miner_v1.journal_ledger WHERE run_id='pgimp_interrupt') AND (SELECT count(*)=3 FROM nqc_miner_v1.outbox WHERE run_id='pgimp_interrupt')") == t ]]
printf '{"status":"pass","uncommitted_rows_absent":true,"retry_records":3,"backend_termination_injected":true}\n' > "$MINER_TEST_EVIDENCE/interruption.json"

printf 'MINER: reinicio y comparacion de todos los datos...\n'
query 'SELECT version(); SHOW listen_addresses; SHOW unix_socket_directories; SHOW fsync; SHOW synchronous_commit;' > "$MINER_TEST_EVIDENCE/server-settings.txt"
MINER_SNAPSHOT="SELECT jsonb_build_object('identity',(SELECT jsonb_agg(i) FROM nqc_miner_v1.import_identity i),'runs',(SELECT jsonb_agg(r ORDER BY run_id) FROM nqc_miner_v1.runs r),'ledger',(SELECT jsonb_agg(l ORDER BY run_id,sequence) FROM nqc_miner_v1.journal_ledger l),'outbox',(SELECT jsonb_agg(o ORDER BY run_id,sequence,topic) FROM nqc_miner_v1.outbox o),'quarantine',(SELECT jsonb_agg(q ORDER BY run_id) FROM nqc_miner_v1.import_quarantine q),'registry',(SELECT jsonb_agg(m ORDER BY run_id,mine_id) FROM nqc_miner_v1.mine_registry m),'gates',(SELECT jsonb_agg(g ORDER BY run_id,mine_id,gate_kind,report_sha256) FROM nqc_miner_v1.gate_reports g),'lifecycle',(SELECT jsonb_agg(j ORDER BY run_id,mine_id,lifecycle_version) FROM nqc_miner_v1.lifecycle_journal j))"
query "$MINER_SNAPSHOT" > "$MINER_TEST_EVIDENCE/before-restart.json"
pg_ctl -D "$MINER_TEST_ROOT/data" -m fast -w -t 60 restart >> "$MINER_TEST_EVIDENCE/startup.log" 2>&1
query "$MINER_SNAPSHOT" > "$MINER_TEST_EVIDENCE/after-restart.json"
cmp "$MINER_TEST_EVIDENCE/before-restart.json" "$MINER_TEST_EVIDENCE/after-restart.json"
printf '__EXPECTED_CASES__ SQL assertions, permissions, concurrency, interruption and restart passed.\n'
