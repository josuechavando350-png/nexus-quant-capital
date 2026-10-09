#!/usr/bin/env bash
# Proposed migration helper. Called only inside a new network + private mount namespace.
set -euo pipefail
test "$#" = 3
root="$1"
repo="$2"
parent_network="$3"
cd "$repo"
test "$(git rev-parse HEAD)" = "$EXPECTED_COMMIT"
test "$(git rev-parse 'HEAD^{tree}')" = "$EXPECTED_TREE"
test -z "$(git status --porcelain=v1 --untracked-files=no)"
python3 -B - "$parent_network" "$root/logs/build-network-isolation.json" <<'PY'
import importlib.util, json, pathlib, sys
p = pathlib.Path('ci/nqc-census/run_rmc006_recertification.py')
spec = importlib.util.spec_from_file_location('offline_network', p)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
pathlib.Path(sys.argv[2]).write_text(json.dumps(m.network_proof(sys.argv[1]), sort_keys=True, indent=2) + '\n')
PY
python3 -B -m unittest discover -s migration -p test_standalone_d06.py -v \
  2>&1 | tee "$root/logs/standalone-helper-tests.log"

# Authenticity/expiry use actual UTC inside the disconnected gate. No date override.
source="$root/authenticated-original"
archive="$repo/migration/evidence/d06/original-evidence.zip"
python3 -B ci/nqc-census/verify_rmc006_recertification_source.py \
  --archive "$archive" --run-metadata "$root/metadata/run.json" \
  --artifact-metadata "$root/metadata/artifact.json" --commit-metadata "$root/metadata/commit.json" \
  --extract-to "$source" --provenance "$root/metadata/source-provenance-before.json" \
  2>&1 | tee "$root/logs/source-authentication-before.log"

if grep -RInE 'private.?key|mnemonic|eth_send|eth_sign|sendRawTransaction|reqwest|hyper|tokio|std::net|unsafe' \
  nqc-census/crates/nqc-census-aave-discovery --include='*.rs' > "$root/logs/authority-boundary.log"; then
  echo 'Forbidden execution/network authority in D06' >&2
  exit 1
fi
cd nqc-census
rustc -V | tee "$root/logs/rustc-version.log" | grep -F 'rustc 1.98.1 '
cargo fmt --all -- --check 2>&1 | tee "$root/logs/fmt.log"
cargo clippy --workspace --all-targets --locked --offline -- -D warnings 2>&1 | tee "$root/logs/clippy.log"
cargo test --locked --offline -p nqc-census-aave-discovery --test aave_discovery -- --list \
  > "$root/logs/d06-tests-listed.log" 2>&1
test "$(grep -c ': test$' "$root/logs/d06-tests-listed.log")" = 21
cargo test --locked --offline -p nqc-census-aave-discovery --test aave_history -- --list \
  > "$root/logs/history-tests-listed.log" 2>&1
test "$(grep -c ': test$' "$root/logs/history-tests-listed.log")" = 11
cargo test --locked --offline -p nqc-census-aave-discovery -- --nocapture 2>&1 | tee "$root/logs/d06-tests.log"
cargo test --workspace --all-targets --locked --offline 2>&1 | tee "$root/logs/workspace-tests.log"
cargo build --workspace --all-targets --locked --offline 2>&1 | tee "$root/logs/workspace-build.log"
cargo build --release --locked --offline -p nqc-census-aave-discovery --bins 2>&1 | tee "$root/logs/d06-release.log"
cargo build --release --locked --offline -p nqc-census-store --bin nqc-census-store-verify \
  2>&1 | tee "$root/logs/store-release.log"
cd "$repo"
export RMC006_SOURCE_ARCHIVE="$archive"
export RMC006_SOURCE_RUN_METADATA="$root/metadata/run.json"
export RMC006_SOURCE_ARTIFACT_METADATA="$root/metadata/artifact.json"
export RMC006_SOURCE_COMMIT_METADATA="$root/metadata/commit.json"
python3 -B -m unittest discover -s ci/nqc-census -p 'test_rmc006_recertification*.py' -v \
  2>&1 | tee "$root/logs/python-authentication-and-runner-tests.log"
! grep -E 'skipped=|\.\.\. skipped ' "$root/logs/python-authentication-and-runner-tests.log"

# Unchanged runner binds closeout to this exact independent producer checkout.
python3 -B ci/nqc-census/run_rmc006_recertification.py \
  --repo "$repo" --source "$source" --out "$root/evidence" \
  --parent-network-namespace "$parent_network" 2>&1 | tee "$root/logs/replay.log"
python3 -B ci/nqc-census/test_rmc006_recertification_replay.py \
  --repo "$repo" --source "$source" --work "$root/evidence/negative-tests" \
  --parent-network-namespace "$parent_network" 2>&1 | tee "$root/logs/replay-negatives.log"
python3 -B ci/nqc-census/verify_rmc006_recertification_source.py \
  --archive "$archive" --run-metadata "$root/metadata/run.json" \
  --artifact-metadata "$root/metadata/artifact.json" --commit-metadata "$root/metadata/commit.json" \
  --verify-extracted "$source" --provenance "$root/metadata/source-provenance-after.json" \
  2>&1 | tee "$root/logs/source-authentication-after.log"
test -z "$(git status --porcelain=v1 --untracked-files=no)"
cp -a "$root/logs" "$root/evidence/code-gates"
cp -a "$root/metadata" "$root/evidence/original-seed"
cp -- "$archive" "$root/evidence/original-seed/source.zip"
mkdir -p "$root/evidence/historical-source/effective-source"
cp -- "$root/materialized/HISTORICAL-ADAPTER.json" "$root/evidence/historical-source/"
cp -- "$root/materialized/network-isolation.json" "$root/evidence/historical-source/"
cp -- "$root/materialized/materializer.log" "$root/evidence/historical-source/"
cp -- "$root/materialized/effective-source/MATERIALIZATION.json" \
  "$root/evidence/historical-source/effective-source/"
cp -- "$root/acquisition/source-metadata.json" "$root/evidence/historical-source/source-metadata.json"
# Never copy the source object store, full original history, or dependency cache.
