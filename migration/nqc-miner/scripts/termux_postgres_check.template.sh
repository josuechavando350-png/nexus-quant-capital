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
__EMBEDDED_SQL__
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
[[ $(grep -c 'MINER_PASS:' "$MINER_TEST_EVIDENCE/cases.log") == __EXPECTED_CASES__ ]]

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
printf 'Schema guards, __EXPECTED_CASES__ SQL checks, 3 writer denials and restart comparison passed.\n'
