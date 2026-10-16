# Fixed-cohort transport experiment — registered before measurement

Base: PR14, `26bf4105926a57480a0a920091d8dc3f720351a4`. All new files live
here. Old protocol, lens, registry and evidence remain byte-identical.
The public protocol commit must precede the first remote RPC. Source lock is
generated offline; results are appended later, never by changing these rules.

## Question and fixed selection

Does retaining a client connection reduce acquisition latency versus the current
urllib reader, and versus a fresh client using the same Requests implementation?
This is a transport experiment, not a trading, opportunity-discovery or gas test.

Use all 30 accounts from PR14's registry, without ranking or dropping zero-debt
accounts. Root `3b530c3214b58b8ae4adb5dc4aa399b6e2db1994396bb2ce918302cf0a63f8de`.
Revalidate its start boundary and checkpoint. **No historical rescan or catch-up**:
the already selected cohort is adequate for this question. The index still ends
at 89,902,197; disclose each new observation's unindexed tail. Reconcile its
shares against current totalBorrowShares, but do not claim market completeness.

## Controls and order

- `legacy`: unchanged `rpc_batch.network`, new urllib opener per HTTP request.
- `fresh`: new Requests Session/adapter for each HTTP request, then close it.
- `persistent`: lazily create one Session/adapter and retain it across the run.
  No warm-up request. The first view is the first connection attempt; all later
  requests are reuse-eligible, but actual reuse must be checked, not assumed.
- All arms: same authorized demo endpoint, same exact view call (apart from
  JSON-RPC ID), same 30 accounts, same blockHash with requireCanonical=true.
  The fixed constructor lens is called via eth_call only, never deployed.
- Six triads: L/F/P, F/P/L, P/L/F, P/F/L, F/L/P, L/P/F.
  Each mode occupies each position twice. This controls obvious order imbalance,
  not all cache/provider/load effects. Six blocks are not independent market samples.
- Each triad obtains one latest header with the legacy reader. The first also
  authenticates the fixed protocol bytecode and market parameters. Each arm reads
  state then checks the same canonical header using that arm. Require exact raw
  ABI output AND exact derived-state equality across all three. A mismatch stops.
- Record client socket object tags before reading the body; retain references to
  prevent object-ID recycling. This is local socket reuse, potentially to a proxy,
  **not proof that the upstream node reused a backend connection**. Unknown stays null.

## Timing, stopping and evidence

Input time: start of the view request to receipt of the complete raw body, before
JSON/ABI decoding. Includes construction, connection and transfer where applicable.
Verified time: same start to AFTER decoding and successful canonical comparison.
It includes intervening parsing and evidence writes, excludes the final journal
write. Also preserve common-header-to-verification and header-request-to-verification
times; later arms include preceding arms' waiting time. First-triad common-header
times include initial authentication. These are not fair isolated transport
latencies; use per-arm input/verified times for the controlled comparison.

49 methods/49 sequential HTTP requests expected: chain + two source boundaries +
four authentication views + six latest headers + 36 view/canonical requests.
Hard envelope: 512 RPC methods, 900 seconds for the whole run, 20-second POSIX
wall deadline per HTTP request capped by remaining run time, 2 MiB per response,
32 MiB total. At most one extra byte is read to detect overflow. No HTTP concurrency,
redirects, retries (including Retry-After), failover, alternative endpoint, or quota
evasion. Any transport, status, JSON, identity, parity, cap or reorg error stops
the entire reader. A timeout is not permission to reconnect and repeat a request.

Keep environment proxy/no_proxy and CA configuration; TLS verification enabled.
No implicit netrc credentials, client certificates or cookie state. Requirements
versions are checked before capture. Requests uses public HTTPAdapter.send with
prepared requests and explicit merge_environment_settings: Session.send's redirect
bookkeeping can otherwise consume a response body before our cap. Both Requests
arms use identical headers/settings. Legacy stays unchanged; differences between
legacy and Requests alone cannot be attributed solely to pooling.

Store payloads, timestamps, bounded raw replies/error prefixes, status, exception
types, socket tags and chained journal. Do not log exception strings containing
proxy credentials. Preserve bytes returned before an error; bytes withheld in a
library/OS buffer cannot be reconstructed. New transport reads bounded read1 chunks
without decompression. Legacy body-read failures may expose no partial bytes.
Offline replay reconstructs control flow, outputs, parity and metrics. It checks
hash consistency, not independent cryptographic truth of the provider or clocks.

## Analysis fixed in advance

Report all six triads, all negatives/errors, and count of complete triads. Summarize
each arm's input and verified range/median; also show paired legacy/persistent and
fresh/persistent ratios. Split the first persistent view from the five later views;
report actual socket observations. No removing slow outliers or replacing failed
rounds. Compare against the assumed 1,000 ms target, not a purchased SLA. No claim
of general causal effect, profitable capture, production readiness or future SLA.

No route simulation, inclusion, gas/Nitro/DA measurement, signatures, sends,
funding or economic admission. Realized profit and capture probability stay null.

## Primary API references checked 2026-10-16

- https://requests.readthedocs.io/en/latest/user/advanced/ — pooling, stream
  consumption, prepared requests and explicit environment merging.
- https://requests.readthedocs.io/en/latest/api/ — adapter.send and timeout options.
- https://requests.readthedocs.io/en/latest/_modules/requests/sessions/ — redirect
  bookkeeping and environment behavior; also inspected installed 2.32.5 source.
- https://urllib3.readthedocs.io/en/2.5.0/reference/urllib3.util.html — retry controls.
- https://urllib3.readthedocs.io/en/stable/reference/urllib3.response.html —
  connection and bounded undecoded reads; installed read1 tested locally.
- https://docs.python.org/3/library/signal.html — setitimer, POSIX/main-thread limits.

Offline prerequisites: real loopback HTTP tests for socket reuse, new connections,
redirect/error/disconnect no-retry, timeout, truncation, encoding and size bounds;
proxy/CA/netrc configuration tests; synthetic replay with all 49 RPC failure
boundaries, JSON failure, wrong chain, source reorg, parity divergence, corruption,
budget and source-hash tests. Loopback fixtures never query blockchain RPC.
