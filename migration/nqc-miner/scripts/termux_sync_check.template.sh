#!/usr/bin/env bash
# Self-contained artificial Miner transport test. No downloads or existing DBs.
set -euo pipefail
umask 077
if [[ $(id -u) == 0 || ${PREFIX:-} != /data/data/com.termux/files/usr || $HOME != /data/data/com.termux/files/home ]]; then
  printf 'REJECTED: use ordinary native Termux, without root.\n' >&2
  exit 2
fi
for executable in initdb pg_ctl psql createdb sha256sum tar mktemp cmp gzip base64 grep python3; do
  command -v "$executable" >/dev/null || { printf "Falta: %s\n" "$executable" >&2; exit 2; }
done
python3 -c 'import sys; assert sys.version_info >= (3, 10)'
[[ $(psql --version) == 'psql (PostgreSQL) 18.6' ]]
for MINER_AMBIENT in ${!PG@} ${!PSQL@}; do unset "$MINER_AMBIENT"; done
export PGCONNECT_TIMEOUT=10 PSQL_PAGER=cat
MINER_TEST_ROOT=$(mktemp -d "$HOME/nqc-miner-sync.XXXXXX")
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
  printf '{"schema":"nqc-miner-sync-contract-check-v1","status":"%s","data_origin":"artificial_historical_admission","production_integration":false,"observer_bridge_enabled":false,"spending_authorized":false}\n' "$result" > "$MINER_TEST_EVIDENCE/result.json"
  python3 - "$MINER_TEST_EVIDENCE" <<'NQC_SYNC_MANIFEST'
import hashlib,sys
from pathlib import Path
root=Path(sys.argv[1])
files=sorted(p for p in root.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
(root/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  ./'+p.relative_to(root).as_posix()+'\n' for p in files))
NQC_SYNC_MANIFEST
  if [[ $? != 0 ]]; then printf 'FAILED: cannot hash evidence\n' >&2; exit 1; fi
  archive="$MINER_TEST_ROOT/nqc-miner-sync-evidence.tar.gz"
  tar -czf "$archive" -C "$MINER_TEST_ROOT" evidence
  if [[ $? != 0 ]]; then printf 'FAILED: cannot package evidence\n' >&2; exit 1; fi
  printf '\nMINER SYNC: %s\nResults: %s\n' "$result" "$archive"
  if [[ -d /sdcard/Download && -w /sdcard/Download ]]; then
    destination=$(mktemp /sdcard/Download/nqc-miner-sync-evidence.XXXXXX.tar.gz)
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
port = 55435
shared_buffers = '32MB'
max_connections = 10
max_parallel_workers = 0
EOF
cp "$MINER_TEST_ROOT/data/postgresql.conf" "$MINER_TEST_ROOT/data/pg_hba.conf" "$MINER_TEST_EVIDENCE/"
MINER_TEST_STARTED=1
pg_ctl -D "$MINER_TEST_ROOT/data" -l "$MINER_TEST_EVIDENCE/server.log" -w -t 60 start > "$MINER_TEST_EVIDENCE/startup.log" 2>&1
export PGOPTIONS='-c statement_timeout=90000 -c lock_timeout=30000'
MINER_TEST_PSQL=(psql -X -w -h "$MINER_TEST_ROOT/s" -p 55435 -U "$MINER_TEST_USER" -v ON_ERROR_STOP=1 -v VERBOSITY=verbose -P pager=off)
"${MINER_TEST_PSQL[@]}" -d postgres -c 'CREATE ROLE nqc_miner_import_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION; CREATE ROLE nqc_miner_import_writer NOLOGIN NOSUPERUSER; CREATE ROLE nqc_miner_import_outsider NOLOGIN NOSUPERUSER;' > "$MINER_TEST_EVIDENCE/roles.log" 2>&1
createdb -w -h "$MINER_TEST_ROOT/s" -p 55435 -U "$MINER_TEST_USER" --maintenance-db=postgres -O nqc_miner_import_owner nqc_miner_v1 > "$MINER_TEST_EVIDENCE/database.log" 2>&1
"${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -c 'SET ROLE nqc_miner_import_owner' -f "$MINER_TEST_EVIDENCE/postgres.sql" > "$MINER_TEST_EVIDENCE/apply-base.log" 2>&1
"${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -c 'SET ROLE nqc_miner_import_owner' -f "$MINER_TEST_EVIDENCE/postgres_import.sql" > "$MINER_TEST_EVIDENCE/apply-importer.log" 2>&1
"${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -c 'SET ROLE nqc_miner_import_owner' -f "$MINER_TEST_EVIDENCE/postgres_collection.sql" > "$MINER_TEST_EVIDENCE/apply-collection.log" 2>&1
"${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -f "$MINER_TEST_EVIDENCE/fixtures.sql" > "$MINER_TEST_EVIDENCE/fixtures.log" 2>&1
printf 'MINER: cliente real, confirmacion, reintentos e interrupciones...\n'
python3 "$MINER_TEST_EVIDENCE/postgres_transport_runtime.py" "$MINER_TEST_ROOT" > "$MINER_TEST_EVIDENCE/runtime.log" 2>&1
[[ $(grep -c 'MINER_SYNC_PASS:' "$MINER_TEST_EVIDENCE/runtime.log") == __EXPECTED_CASES__ ]]
query() { "${MINER_TEST_PSQL[@]}" -d nqc_miner_v1 -qAtc "$1"; }
query 'SELECT version(); SHOW listen_addresses; SHOW unix_socket_directories; SHOW fsync; SHOW synchronous_commit;' > "$MINER_TEST_EVIDENCE/server-settings.txt"
MINER_SNAPSHOT="SELECT jsonb_build_object('collections',(SELECT jsonb_agg(c ORDER BY parent_run_id) FROM nqc_miner_v1.collections c),'windows',(SELECT jsonb_agg(w ORDER BY parent_run_id,window_index) FROM nqc_miner_v1.collection_windows w),'receipts',(SELECT jsonb_agg(r ORDER BY parent_run_id,receipt_sequence) FROM nqc_miner_v1.collection_receipts r),'revocations',(SELECT jsonb_agg(q ORDER BY parent_run_id) FROM nqc_miner_v1.collection_quarantine q),'eligible_ledger',(SELECT jsonb_agg(l ORDER BY parent_run_id,window_index,sequence) FROM nqc_miner_v1.eligible_collection_ledger l),'eligible_outbox',(SELECT jsonb_agg(o ORDER BY parent_run_id,window_index,sequence) FROM nqc_miner_v1.eligible_collection_outbox o),'identity',(SELECT jsonb_agg(i) FROM nqc_miner_v1.import_identity i),'runs',(SELECT jsonb_agg(r ORDER BY run_id) FROM nqc_miner_v1.runs r),'ledger',(SELECT jsonb_agg(l ORDER BY run_id,sequence) FROM nqc_miner_v1.journal_ledger l),'outbox',(SELECT jsonb_agg(o ORDER BY run_id,sequence,topic) FROM nqc_miner_v1.outbox o),'quarantine',(SELECT jsonb_agg(q ORDER BY run_id) FROM nqc_miner_v1.import_quarantine q),'registry',(SELECT jsonb_agg(m ORDER BY run_id,mine_id) FROM nqc_miner_v1.mine_registry m),'gates',(SELECT jsonb_agg(g ORDER BY run_id,mine_id,gate_kind,report_sha256) FROM nqc_miner_v1.gate_reports g),'lifecycle',(SELECT jsonb_agg(j ORDER BY run_id,mine_id,lifecycle_version) FROM nqc_miner_v1.lifecycle_journal j))"
query "$MINER_SNAPSHOT" > "$MINER_TEST_EVIDENCE/before-restart.json"
pg_ctl -D "$MINER_TEST_ROOT/data" -m fast -w -t 60 restart >> "$MINER_TEST_EVIDENCE/startup.log" 2>&1
query "$MINER_SNAPSHOT" > "$MINER_TEST_EVIDENCE/after-restart.json"
cmp "$MINER_TEST_EVIDENCE/before-restart.json" "$MINER_TEST_EVIDENCE/after-restart.json"
printf '__EXPECTED_CASES__ client/database assertions and restart passed.\n'
