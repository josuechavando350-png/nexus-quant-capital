#!/usr/bin/env bash
# Proposed migration helper. Called only inside a new network + private mount namespace.
set -euo pipefail
test "$#" = 7
root="$1"
repo="$2"
parent_network="$3"
runner_uid="$4"
runner_gid="$5"
parent_mount="$6"
phase="$7"
test "$phase" = build || test "$phase" = replay
# The fixed setpriv boundary precedes this unprivileged shell. Confirm all four
# kernel IDs, groups, capabilities and no-new-privs before Python imports or Git.
/usr/bin/python3 -I -B - "$runner_uid" "$runner_gid" "$root/logs/$phase-privilege-drop.json" <<'PRIVILEGES'
import json, pathlib, sys

def privilege_drop_proof(status, uid, gid):
    if type(uid) is not int or uid <= 0 or type(gid) is not int or gid <= 0:
        raise ValueError('invalid original runner identity')
    fields = {}
    for line in status.splitlines():
        key, separator, value = line.partition(':')
        if separator:
            if key in fields:
                raise ValueError('duplicate process status field')
            fields[key] = value.strip()
    uids = [int(value) for value in fields['Uid'].split()]
    gids = [int(value) for value in fields['Gid'].split()]
    groups = [int(value) for value in fields['Groups'].split()]
    caps = {key: int(fields[key], 16) for key in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb')}
    no_new_privs = int(fields['NoNewPrivs'])
    if uids != [uid] * 4 or gids != [gid] * 4 or groups or any(caps.values()) or no_new_privs != 1:
        raise ValueError('privileges were not completely dropped')
    return {'schema': 'nqc-privilege-drop-v1', 'caller_uid': uid, 'caller_gid': gid,
            'uids': uids, 'gids': gids, 'groups': groups, 'capabilities': caps,
            'no_new_privs': no_new_privs}


proof = privilege_drop_proof(pathlib.Path('/proc/self/status').read_text(), int(sys.argv[1]), int(sys.argv[2]))
with pathlib.Path(sys.argv[3]).open('x') as stream:
    stream.write(json.dumps(proof, sort_keys=True, indent=2) + '\n')
PRIVILEGES
cd "$repo"
test "$(git rev-parse HEAD)" = "$EXPECTED_COMMIT"
test "$(git rev-parse 'HEAD^{tree}')" = "$EXPECTED_TREE"
test -z "$(git status --porcelain=v1 --untracked-files=no)"
/usr/bin/python3 -I -B - "$parent_network" "$root/logs/$phase-network-isolation.json" "$parent_mount" "$phase" <<'PY'
import importlib.util, json, os, pathlib, sys
p = pathlib.Path('ci/nqc-census/run_rmc006_recertification.py')
spec = importlib.util.spec_from_file_location('offline_network', p)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
network = m.network_proof(sys.argv[1])
network['isolation_mode'] = 'sudo-drop'
mount = os.readlink('/proc/self/ns/mnt')
if mount == sys.argv[3]:
    raise ValueError('mount namespace was not isolated')
network['mount_namespace'] = mount
network['parent_mount_namespace'] = sys.argv[3]
network['privilege_drop'] = json.loads(pathlib.Path(sys.argv[2]).with_name(sys.argv[4] + '-privilege-drop.json').read_text())
pathlib.Path(sys.argv[2]).write_text(json.dumps(network, sort_keys=True, indent=2) + '\n')
PY
source="$root/authenticated-original"
archive="$repo/migration/evidence/d06/original-evidence.zip"
if test "$phase" = build; then
python3 -B -m unittest discover -s migration -p test_standalone_d06.py -v \
  2>&1 | tee "$root/logs/standalone-helper-tests.log"

# Authenticity/expiry use actual UTC inside the disconnected gate. No date override.
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

exit 0
fi

# Authenticate the mounted package again immediately before replay, using the
# actual UTC clock and unchanged source verifier. This never writes to source.
python3 -B ci/nqc-census/verify_rmc006_recertification_source.py \
  --archive "$archive" --run-metadata "$root/metadata/run.json" \
  --artifact-metadata "$root/metadata/artifact.json" --commit-metadata "$root/metadata/commit.json" \
  --verify-extracted "$source" --provenance "$root/metadata/source-provenance-mounted-before.json" \
  2>&1 | tee "$root/logs/source-authentication-mounted-before.log"

# Explicit prospective v1 runners preserve computation but require a genuine
# pre-mounted source. Their identities are recorded separately from originals.
python3 -B migration/run_premounted_d06_v1.py \
  --repo "$repo" --source "$source" --out "$root/evidence" \
  --parent-network-namespace "$parent_network" 2>&1 | tee "$root/logs/replay.log"
python3 -B migration/test_premounted_d06_replay_v1.py \
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
