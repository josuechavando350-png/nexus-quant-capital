# Historical oracle observations: complete secondary coverage, Census open

Current evidence: [checkpoint 007](CHECKPOINT_007.md) authenticates terminal
acquisition and all **215,036 blocks / 67 assets / 14,407,412 price coordinates**,
with zero missing blocks and zero price discrepancies. The original worker
finished on 2026-10-10 at 05:30:23 UTC. Do not launch another continuation for
this already completed plan. Funding, routes, costs, capture and independent
Census authority remain open. Numerical notices were discontinued by the user;
`../MILESTONES.md` records that decision. The earlier notes below are historical.

## Historical continuation notes

At this earlier documentation cut, [checkpoint 004](CHECKPOINT_004.md) added 25,000 blocks
and 1,675,000 matched prices. The verified secondary union is 85,170 / 215,036;
129,866 remain missing. It preserves only the new delta, replays the full prefix
and does not satisfy 10/20. Earlier checkpoint counts below are historical.

The offline integration checker in [COVERAGE_GATE.md](COVERAGE_GATE.md) now
replays the original/prior captures, the complete retained continuation prefix,
and the executed-event/full-receipt evidence together. It checks exact block
sets, not just counters. Its current checkpoint-003 result remains partial;
it neither declares a milestone nor changes the active worker.

The user's subsequent instruction continues the work and requests notices at
10/20, 15/20 and 20/20; definitions are in `../MILESTONES.md`. `resume.py` starts
a separate, pinned acquisition only for the 209,866 missing blocks in
`resume-plan.json`. It enforces the expired 60-second Retry-After, one worker,
a minimum 1.1-second interval, batches of at most ten, a device-wide lock,
a 24-hour runtime budget and the original finite RPC-call and disk budgets.
It stops on every transport/RPC error, preserves partial files and writes an
atomic progress checkpoint after each successful batch. No access identity,
endpoint or subscription is changed. This continuation does not relabel the
earlier 429 attempt or its source code.

Run only one worker on the already authorized device; `PRODUCER_COMMIT` must
identify the exact published commit containing these sources. Use a new output
directory. The progress counter means captured valid-shaped responses, not
offline price parity, independent authority or milestone admission:

```bash
python3 resume.py --plan resume-plan.json --assets /absolute/path/assets.json \
  --primary /absolute/path/original/drpc --out /absolute/path/new-continuation \
  --producer-commit "$PRODUCER_COMMIT"
```

Ten continuation tests cover the actual missing-block plan, conservation,
range/endpoint/rate/worker rejection, Retry-After enforcement, simulated request
spacing and a simulated 429 stop with the prior successful batch retained.
These synthetic controller tests are not chain-state or profitability evidence.

### First closed checkpoint

The later checkpoint below supersedes this prefix for coverage counts; do not
add the two checkpoints together.

The sequential worker started at `2026-10-09T23:03:11Z` using published producer
commit `c163b876d3310855f1db45bfc3ab4189b24d865b`. Its first two closed capture
files contain **2,000 additional blocks / 134,000 matched price values**;
there are zero mismatches. Verified secondary coverage becomes **7,170**,
with **207,866** still missing at this checkpoint. The live progress counter
was 2,140 when snapshotted; the 140 observations in the open file are excluded
from verified counts. Later live progress must not be added again to this
prefix when aggregating coverage.

`sequential-checkpoint-001.zip` retains all ten checkpoint files, including raw
RPC bodies, anchors, plan, exact sources, progress snapshot and remote readback.
It has 746,749 bytes, SHA-256
`4b594dbcc1e32ff8569adaa0a2cea3e374648e5c0d3d3331f0ad5f81b7e83633`.
The same verifier runs against the locally extracted original primary chunks
and returns a byte-identical report. Seven real/adversarial continuation tests
pass, including rejection of a foreign producer, wrong block hash, changed
price, missing/duplicate responses and a noncanonical request. Isolation passes.

For continuation verification, extract original `drpc/chunk-*.json` members
from the pinned original oracle archive to `PRIMARY_DIRECTORY`, and the new
checkpoint to a fresh `CHECKPOINT` directory. The verifier authenticates all
4,301 primary chunk byte hashes, reconstructs relevant observation digests and
compares each closed capture against the exact missing-block plan. It pins the
published producer and source bytes; it does not certify the producer itself.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/oracle_recovery/verify_continuation.py \
  --evidence "$CHECKPOINT" --primary "$PRIMARY_DIRECTORY" \
  --out /absolute/path/new-continuation-readback.json
PYTHONDONTWRITEBYTECODE=1 NQC_ORACLE_CHECKPOINT="$CHECKPOINT" \
  NQC_ORACLE_PRIMARY_DIRECTORY="$PRIMARY_DIRECTORY" \
  python3 -m unittest discover -s migration/census_v2/oracle_recovery \
  -p test_continuation.py -v
```

For later live snapshots, copy `progress.json` once and only its already closed
capture files plus anchors/plan/sources into a fresh directory, checking every
listed file digest before verification. An open file is excluded. Preserve
the entire fixed snapshot and its readback; publish new immutable files with
an expected-head lease. Do not restart or interrupt the active worker merely
to snapshot it. The worker's directory is
`/tmp/nqc-census-v2-oracle-20261009/sequential-v1` on the authorized device.
The hourly continuation task follows `../MILESTONES.md`. No milestone has yet
been reached, and the acquisition remains incomplete until verified otherwise.

### Second closed checkpoint — 2026-10-10 00:22:43Z

The same active worker was snapshotted without interruption. **43,000 blocks /
2,881,000 prices** match the original dRPC vectors, with zero discrepancies.
There are 43 closed files; the 220 observations still in an open file at that
snapshot are excluded. Verified secondary union is now **48,170 / 215,036**;
**166,866** remain missing. This includes the previous 2,000-block prefix and
adds 41,000 blocks beyond it. It does not satisfy the 10/20 milestone.

Both remote and local runs of the unchanged verifier produce byte-identical
readback JSON. `evidence/continuation-checkpoint-002.json` retains that result;
the validation record binds archive hash and size. All source, anchor and first
checkpoint capture bytes are unchanged. The seven prior adversarial checks and
two second-checkpoint checks pass. An initial additional test failed because
the local temporary disk was full; its log is preserved. The successful test
checks the already-extracted bytes against every archive member instead of
creating another full temporary copy, then repeats all price comparisons.

The exact 50-member ZIP has **15,143,401 bytes**, SHA-256
`913b4c530d53207e450ff72e21ad0a0b420af0b80574faee329c161f3daca18c`.
It is retained in two ordered binary parts because base64 upload of the whole
ZIP exceeded the connector's 16 MiB request limit. Concatenation reproduces the
original ZIP exactly; individual sizes/hashes are in
`sequential-checkpoint-002.parts.json`. The first local transfer was rejected
on digest mismatch; the missing transport line was recovered and the full ZIP
matched before any local validation or publication. Captured data was not edited.

```bash
cat migration/census_v2/oracle_recovery/sequential-checkpoint-002.zip.part-001 \
    migration/census_v2/oracle_recovery/sequential-checkpoint-002.zip.part-002 \
    > /tmp/sequential-checkpoint-002.zip
sha256sum /tmp/sequential-checkpoint-002.zip
```

Extract to a fresh directory and use the earlier verification command. For the
new tests, set `NQC_ORACLE_CHECKPOINT_TWO` to that directory and
`NQC_ORACLE_PRIMARY_DIRECTORY` to the original primary chunks, then run
`python3 -m unittest discover -s migration/census_v2/oracle_recovery -p test_checkpoint_two.py -v`.
No new collector, RPC requests, spending or permissions were introduced by
this checkpoint. Later capture progress does not increase these verified counts.

### Third closed checkpoint (delta) — 2026-10-10 00:44:28Z

The existing worker remained healthy under the same PID and lock. This immutable
delta retains only the 12 newly closed files after checkpoint 002: **12,000
additional blocks / 804,000 matched prices**, with zero discrepancies. The
verified continuation prefix is therefore 55,000 blocks and the secondary union
is **60,170 / 215,036**; **154,866** remain missing. The 20 observations in the
open file at snapshot time are excluded. This still does not satisfy 10/20.

`sequential-checkpoint-003-delta.zip` has **4,269,496 bytes**, 22 members and
SHA-256 `6b5691d546ee3eb4aa291a7f32ef52689826021fb791136b67fa84c8e6fbd0c0`.
It includes the exact base readback and base-archive manifest but does not repeat
the first 43 capture files. The delta verifier pins both base hashes, requires the
current progress commitments to have that exact prefix, and begins counting at
offset 43,000. It rejects a substituted base before using any prices. All 12,000
new block vectors were compared to the original dRPC chunks on the authorized
device; the retained readback has SHA-256
`c4d657efa39cdc6620e9862a708fe2fb40fdc9f5c01c9fe2dcd11892d7722253`.
Three archive, prefix-conservation and adversarial tests pass.

To reproduce, extract the delta archive and checkpoint 002 to separate fresh
directories, then provide the original dRPC chunks:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/oracle_recovery/verify_checkpoint_delta.py \
  --evidence "$DELTA" --primary "$PRIMARY_DIRECTORY" \
  --base-readback "$DELTA/base-readback.json" --out /absolute/path/delta-readback.json
PYTHONDONTWRITEBYTECODE=1 NQC_ORACLE_CHECKPOINT_THREE="$DELTA" \
  NQC_ORACLE_PRIMARY_DIRECTORY="$PRIMARY_DIRECTORY" \
  python3 -m unittest discover -s migration/census_v2/oracle_recovery \
  -p test_checkpoint_delta.py -v
```

No request was made to create this checkpoint, and the live worker was neither
restarted nor interrupted. Later progress must not be added to this closed delta
until another immutable snapshot has been verified.

## Earlier captured evidence

Census remains open. This increment verifies 139,360 new price observations
(67 assets at 2,080 blocks) against the immutable original dRPC chunks.
There are zero price mismatches. Only **520 blocks add coverage** beyond the
4,650 previously retained Nodies blocks: the union is **5,170 / 215,036**, with
**209,866 blocks still missing**. Overlapping observations are not counted twice.

The first 1,000-block pilot completed in 103 HTTP requests, including Ethereum
chain and both window anchors. The remaining-window attempt obtained 1,080
blocks, then stopped on Nodies HTTP 429 at `2026-10-09T22:44:14.597626Z`.
Its response says the public endpoint rate limit was exceeded and includes
`Retry-After: 60`. No automatic retry, alternative endpoint, private account or
subscription was used. Already in-flight responses are preserved through
`22:44:15.378879Z`; queued work made no further requests. The failed acquisition
stays `INCOMPLETE`. Any later continuation must respect the provider's current
limits and preserve this failure; it is not part of this result.

The partial collector summary counts 950 blocks in nonfailed files. The offline
reader additionally recovers 130 successful blocks preceding the 429 in the
failed file, giving 1,080 for that attempt. The failed ten-call batch contributes
zero observations. All 112 attempted HTTP requests and 1,093 logical calls,
including anchors, reconcile. Empty queued capture files remain in the archive.

## What is authenticated

Requests call the existing Aave oracle `getAssetsPrices(address[])` through
read-only `eth_call`, using each block's hash with `requireCanonical: true`.
All 67 addresses and their order are rederived from the original D08 member,
SHA-256 `c64719793eed5fd5b09eb725f18b811746b1a50e101bfa00b9569be65282d19e`.
Every primary observation digest is reconstructed from the original oracle ZIP.
The 4,301 exact primary chunk hashes commit to
`1c359a46f8e0b5fbeb39df593ce0e98f581909d057a09819635602ae2a76f906`.
Interior hashes derive from the next retained block's parent; both endpoint
hashes are checked against new headers. This does not reconstruct every header
or authenticate the original primary RPC transport.

Exact JSON request/response body bytes are preserved losslessly as UTF-8 strings
with byte hashes, HTTP status/headers and current send/receive times. Gzip and
archive hashes bind the captured inventory, including failures. The consumer
rejects missing or duplicate responses, changed prices, noncanonical or changed
block requests, changed calldata, invalid ABI shapes, duplicate observations,
body corruption and impossible chronology.

Current acquisition time is not historical decision time. A public endpoint
label does not establish independent underlying nodes. Block-state prices are
not transaction prestate, executable conversion quotes, gas funding or P&L.
No historical timestamp or MXN 2,000 authorization is backdated.

## Preflight findings preserved

The original helper source compiles byte-identically with Solidity 0.8.24,
optimizer 200, Shanghai, without via-IR. The compiler binary was checked against
the official [release manifest](https://github.com/argotorg/solc-bin/blob/gh-pages/linux-amd64/list.json):
SHA-256 `fb03a29a517452b9f12bcf459ef37d0a543765bb3bbc911e70a87d6a37c30d5f`.
Compiler input/output, original source/initcode and the release pin are retained.
Only exact full-byte equality is used; the diagnostic CBOR-stripping comparison
is not an admission criterion.

At the first block, the helper and direct call return identical 67 prices,
timestamp and parent hash. The helper's simulated basefee is **0**, while the
actual header records **38,880,936 wei/gas**. The first preflight assertion that
these fields should match failed. Their actual responses remain preserved.
The original price chunk schema already excludes basefee, so this discrepancy
does not invalidate that schema or become a gas quote. Direct price calls avoid
using the helper's basefee. No historical economic record is rewritten.

An initial batch of 20 was rejected with an explicit maximum of 10 and an
instruction to split the batch. The accepted pilot and collector use at most
10. The larger attempt used eight workers and at most eight HTTP requests per
second; the provider subsequently rate-limited it. These settings are recorded
as the failed attempt's settings, not as a proven permissible sustained rate.

## Reproduction

Two archives are stored in this repository:

| Archive | Bytes / members | SHA-256 |
| --- | --- | --- |
| `oracle-pilot-evidence.zip` | 413,568 / 37 | `eef4643d627d3d27b6fd0acaa54afb94dbfdf794bf5b91832acb2b930e53dc35` |
| `oracle-rate-limited-evidence.zip` | 490,206 / 220 | `efe884429fdc43af0231406ab951acb23a864ee21812849fa49b0ab323a03318` |

Extract each ZIP into its own fresh directory outside the repository. Set
`PILOT` to the first root's `pilot` directory and `PARTIAL` to the second root's
`remaining` directory. The consumer checks every extracted member byte against
the pinned ZIP before use. `PRIMARY` is the previously recovered
`original-oracle-evidence.zip`; `D08` is original artifact `11237887761.zip`.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 migration/census_v2/oracle_recovery/reconcile.py \
  --primary-archive "$PRIMARY" --d08 "$D08" \
  --acquisition "$PILOT" --acquisition "$PARTIAL" \
  --out /absolute/path/new-oracle-readback.json
PYTHONDONTWRITEBYTECODE=1 NQC_ORACLE_PRIMARY_ARCHIVE="$PRIMARY" \
  NQC_ORACLE_D08="$D08" NQC_ORACLE_PILOT="$PILOT" NQC_ORACLE_PARTIAL="$PARTIAL" \
  python3 -m unittest discover -s migration/census_v2/oracle_recovery \
  -p test_reconcile.py -v
```

Fifteen real-data/adversarial tests pass, zero skips. Two final readbacks match
byte-for-byte. The original isolation checks pass. Rust was unchanged and was
not rerun. This consumer is not an independent certifying authority.

## Other material blockers checked

Fresh API metadata for physical archives 11532297952, 11533288894, 11534051574
and 11533854519 still matches the original pins and reports them unexpired.
The normal download connector returned file references, but all four downloads
returned HTTP 403. No bytes were recovered or alternative access attempted.
`physical-archive-blockers.json` preserves that distinction; existing job-log
evidence remains the only recovered physical execution evidence for those runs.

Completion still requires full declared market/censored coverage, original or
prospective decision-time evidence, admissible financing and native gas, token
compatibility and monetizable routes, complete costs and capture treatment, and
an independent review of the exact new producer/consumer commits. Negative or
insufficient-evidence findings remain valid classifications; they are not proof
of commercial impossibility or permission to mark Census certified.
# Latest verified continuation checkpoint

The fifth closed checkpoint adds 59,000 blocks / 3,953,000 matching prices to
the prior 80,000-block continuation prefix. Exact two-operator union:
**144,170 / 215,036 blocks**, with 70,866 missing. The 920 observations in the
open file are excluded. See `CHECKPOINT_005.md` for exact source commitments,
durable binary parts and offline reproduction. Historical coverage is incomplete.
