# Direct historical oracle observations; acquisition stopped at rate limit

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
