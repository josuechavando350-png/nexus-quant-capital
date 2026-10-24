# H23 — direct payment observation, local intake checkpoint

Source base: H22 producer `811c549b3561dcdd0719993a2a12852068f5920b`.
The H22 physical run does not validate H23 code or evidence.

Public read-only Routescan acquisition recovered the first historical winner's
57 indexed operations across three pages, matching transaction metadata and the
same provider's separate positive internal-transfer representation. All five raw
response bodies and their exact request URLs are retained in the capture. No
account, API key, paid subscription, Blockscout session or permission was added.

Capture SHA256: `b139de8b1dd63d1c87c629b6dbab4f4239c7a03b7a2d69082cffff61d6c43f12`.
Report commitment: `42cc6a948cad0bd4677e69a676b6b1fb41807b710b68b2451c2feeaa17aabbd7`.

Observed direct transfer to the historical block fee recipient:
**95915734379292898 wei**, approximately 99.75% of the observed gross WETH delta.
This is not a claim of total builder compensation, verified builder identity,
Titan funding, exclusive liquidation cost attribution or realized NQC profit.
The distinct 9975 wei root value and the residual's different recipient are
explicitly retained. See `DIRECT_PAYMENT_CONTRACT.md` for exact arithmetic and
remaining evidence limits.

Development probes first rejected a bytes-vs-JSON comparison and then an assumed
exact count label on the last cursor page. The byte comparison was corrected;
pagination now verifies the captured final `lowerBound` label against the earlier
exact count, all 57 unique indices and a terminal cursor. These failed probes are
not counted as passed tests or used to weaken the evidence scope.

## Local verification

**638/638 unique Omega tests pass**, including 16 new direct-payment cases, with
zero failures, errors, skips or expected failures (402.651 seconds). The targeted
16/16 suite also passes. Cases reject pagination truncation, missing/duplicate
indices, cursor changes, cross-chain/block drift, failed calls, inconsistent
amounts, gas/native-value disagreement and resealed profit or Titan claims.

Isolation passes with 170 reviewed Omega files, 531 original files and 106 disabled
historical workflows; the one active workflow is unchanged. Original Git objects
were not supplied locally (`original_objects_checked=false`). No Rust/Solidity
implementation was changed or rerun for H23.

An independent stdlib-only check (no Omega imports) validates every retained raw
response hash, all operation indices, block identities, native split, exact payment
ratio, separate root value, gas and unknown-profit fields. It passes.

| Local result | SHA256 |
|---|---|
| Full regression | `6fe25462324395e33865503758d94f8b56dfccd580e2bb2c36b51f859db773ff` |
| Targeted direct-payment suite | `0bbd0cf0b9e9a93d43645ec1f7b980c61ae297342ef44dfcb6e4e87be6bcae01` |
| Isolation | `0b9f54179341cfb8943453deba88e1d308dd37d9f668f714f1e835fde0f11dd7` |
| Independent arithmetic | `fee308b24f5226504d1e651df36010acb387a4ee741c49d13e643f945fbaf82d` |

These local result files are session outputs; their hashes do not claim durable
remote CI artifacts. Source, tests, raw capture and reproducible report are kept
with this draft. No eighth dependent store batch, new runtime proof or H23 remote
validation is claimed. Product certification remains 0/36, complete paid costs
0/127, and execution-specific Titan coverage zero.
