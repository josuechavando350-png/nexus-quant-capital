# H21 audit — retained execution economics and Titan-only gas

Predecessor: H20 closure `ec7c976e4da4afae4f24ae7ab52fa24fc38e5058`.

H21 imports two authentic original execution/gas artifacts, reconstructs the
original arithmetic offline, joins the existing temporal evidence and preserves
measured/simulated/modeled/paid distinctions. It also implements the user's
2026-10-23 correction: Titan supplies gas, with no operator gas allowance or
fallback. The former MXN 2,000 rule is superseded in the active architecture.
Historical source contracts and audits retain their original bytes and scope.

Implementation and local verification pass: **2/4 (50% of this increment)**.
Remote execution and post-audit are pending. No H20 result certifies this new
producer. Certified components: 0/36.

Development probes found a bytes-vs-JSON comparison error and an unsupported
restore keyword before the recorded regression. They were corrected to compare
canonical bytes directly and to verify the restored journal head explicitly.

## Local validation before publication

Full Omega suite: **589/589**, with no failures, errors, skips or expected failures.
**28 new cases** over H20: 24 execution-intake, two packet-v4 and two policy tests.
The recorded targeted suites pass 24/24 execution and 19/19 packet cases. The
unchanged original gas auditor also passes its separate 19/19 unit cases; these
are not added to Omega's unique test total. Original D15B/D16 inputs remain pinned.

Isolation passes with 158 reviewed Omega files, 531 original files, 106 historical
workflows disabled and the same active workflow bytes/permissions. Local original
Git objects were not provided; the remote job must perform that stronger check.
Authentic H20 v3 replay evidence still passes the new reader with unchanged scope.

An independent Python-stdlib audit (no Omega imports) recomputes the five budgets,
checks all 14 cost categories, original archive/member hashes and both SQLite
databases. Six batches, five dependency edges and all six blocked after root
revocation; restored table bytes match exactly. This local audit is not network
isolation, a new EVM fork or physical Rust transport evidence.

Economic report: `f1749932c05d9c3ad4fa873580a8673ff5bae62413fc17ea8a786a7fe3edd6af`.
Titan policy: `e2c0b1ea247597de667d093385990880a31519b594f68cae31618ba425f87540`.
Independent audit commitment: `b0a631a90f3f76dae651350a1ed752bab8f65ea5c4f0d3d299e3601fe45f9b44`.

- h21-full-tests.json: SHA256 `6c7c79d5569a60d725f9e9685b3e71f08b1658481e6899fe77d41bb5f7a20e1d`.
- h21-original-gas-tests.json: SHA256 `8ba0989ab061f765f50f3cfa6ffb2469294536fc6736393d8159badb11afdfef`.
- h21-isolation.json: SHA256 `be466656c83c52b67c98971a67ecb4874316ed0b4b7eaeab3b95ecd86083219a`.
- h21-independent-local.json: SHA256 `3ee8a3a43580c387da9ed4664e1b0f164804d437d5e5019c3b266d4ae33279d4`.
- h21-h20-backcompat.json: SHA256 `1a14152492e2fa3e8671e4ab091ee1066515db0b3b396dce23b68a7423cb393e`.
