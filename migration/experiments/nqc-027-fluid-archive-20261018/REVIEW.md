# NQC027: separately reviewed historical read acquisition

Date: 2026-10-18. Repository exclusively josuechavando350-png/nexus-quant-capital.
Immutable base: 16e352225ba8a6a931834c4edf3d86d9a2924b7d.
Branch: research/nqc-027-fluid-archive-20261018. No main/legacy modifications.

## Purpose and current evidence

NQC026 prepared but did not execute a parent-state Fluid quote. Local HTTP failed
DNS; Blockscout and Desktop Commander quotas must not be retried or bypassed.
This uses the existing PUBLIC NQC repository's standard ubuntu-24.04 runner and
a different public unauthenticated node: https://ethereum-rpc.publicnode.com .
This is a new bounded archival-data acquisition, not a repeated synthetic EVM run.
No builder contact, accounts, paid endpoints, secrets or permission expansion.
GitHub documents free standard-runner compute for public repositories, and logs
are outside artifact-storage allowance. No caches or artifact uploads are used.
References: https://docs.github.com/en/billing/concepts/product-billing/github-actions
and https://ethereum.publicnode.com/ . PublicNode archive availability at this
height is unproven until an actual response is received. No guarantee is claimed.

## Review before activation

The frozen Python collector and tests were inspected and run offline: 14/14 tests
passed; four selectors checked against the existing NQC026 Keccak implementation.
Tests made ZERO network calls and establish collector behavior, not opportunities.
Files (UTF-8) and SHA-256:
- source/collect_fluid.py: 366f7485e9a65c8358ddf1bd69524440b892a37beb241d0db1576587673e14b2
- tests/test_collect_fluid.py: 74c74f0926a151a4651127045159d113714c950dc9bf55367db30b76732aa80c
Frozen gzip transport: 5980 bytes; SHA-256
7499ee8558be719b872cb3d36d86196105016c44e012e8e75924e0e26b93d738.
The workflow unpacks exactly those two files OUTSIDE the source checkout and
checks their hashes before execution. Plain source is retained in the local
NQC027 delivery; compression is transport, not a new source of authority.

## Acquisition boundary

At most 12 sequential RPC requests, each timeout 20 seconds and response cap 4 MiB;
total successful response cap 16 MiB. No retries, other hosts, redirects, latest
fallback, state overrides, signatures or eth_send methods. Every request must be
exactly in the frozen allowlist. Any transport/RPC rejection stops the sequence.
The only expected error is Fluid's documented swap quote custom error.
Methods: eth_chainId, eth_getBlockByHash, eth_getCode, eth_call,
eth_getTransactionReceipt, eth_getTransactionByHash, eth_getProof and
ONE debug_traceTransaction with prestateTracer (read only). Unsupported tracing
or proof access is recorded, not worked around. No new key/session is created.

Parent block 26190954, hash
0xf57a30121eac97b983cad86fcb3107787a9d400ca4d69d5a96a4b1b618ac65dc.
Target block 26190955, index 1, transaction
0x46300e9614c547118ecdd524bc7218208088cc4ae9e5bd534e62055d38f9925b.
Pool 0xdd72157a021804141817d46d9852a97addfb9f59.
The quote amount 24343983926960874121 ezETH is taken retrospectively from B;
this is not a prospectively selected candidate. Parent-end state is NOT pre-tx1.
Quote completion is NOT token settlement, replay, inclusion or financing evidence.
Proof bytes require independent verification. Historical runtime/source parity
and original/NQC EVM replay remain unperformed by this collector.

## Workflow gate and producer identity

Only the exact branch and new workflow-path push activate the workflow; no cron,
manual dispatcher, PR trigger or other repository is permitted. Attempt must be 1.
Only permissions: {}. No secrets, actions dependencies or nonstandard runners.
Before RPC: fetch the public NQC base and producer, check exact GITHUB_SHA, verify
base isolation and its 9 tests, verify base-to-producer diff contains only the
new REVIEW and workflow, verify runtime hashes, rerun the 14 collector tests.
The global legacy isolation verifier rejects any active .github tree; it is NOT
claimed to pass on the new producer. It runs on the untouched pre-workflow base.
A separate explicit two-file addition check covers this reviewed producer.
Original external Git objects and Rust/Solidity suites are NOT checked here.

The current environment lacks the full base checkout, so base isolation was not
run locally before this review. It is a mandatory pre-network gate on the runner.
No RPC acquisition result exists at review time. The new producer commit and run
will be read back from GitHub; do not reuse a previous experiment's identity.

## Output and stop conditions

Preserve raw HTTP response bytes, exact request IDs/block hashes, times, hashes,
errors and a compressed export in logs. Export availability is not itself an
independent state proof. All commercial flags stay false. If acquisition fails,
report BLOCKED without manufacturing a quote or counting tests as market success.
No remote mutation is performed by the job. Only the director publishes reviewed
research files; main and every original file/mode must remain unchanged.
