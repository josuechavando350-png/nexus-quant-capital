# H21 audit — retained execution economics and Titan-only gas

Predecessor: H20 closure `ec7c976e4da4afae4f24ae7ab52fa24fc38e5058`.

H21 imports two authentic original execution/gas artifacts, reconstructs the
original arithmetic offline, joins the existing temporal evidence and preserves
measured/simulated/modeled/paid distinctions. It also implements the user's
2026-10-23 correction: Titan supplies gas, with no operator gas allowance or
fallback. The former MXN 2,000 rule is superseded in the active architecture.
Historical source contracts and audits retain their original bytes and scope.

Pre-publication checkpoint: **2/4 (50%)**, with remote execution and post-audit
then pending. The final outcome below closes both remaining gates. No H20 result
substitutes for this producer. Certified components: 0/36.

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

## Final exact-producer outcome

Run **40027689852**, producer `668ddb5f26225e9f9f545b1c1e07740c01d783c8`, tree
`4e8750f01620e08d10d1cb5d462af2bc28932abf`, completed successfully at 2026-10-23T22:01:52Z.
Closure changes after this producer are Markdown only.

| Stage | Job | Artifact | ZIP SHA256 | External capture SHA256 |
|---|---|---|---|---|
| forks | 120667894830 | 12533518264 | `c4ccbb34521496987ab2d9dde5360cb018c2c48697db690945651eff7332eea5` | `b6a698eee265f506dc905e418252f1d50c6866800d8216f50ae4978868638be2` |
| replay | 120667894707 | 12535070907 | `59a2c1930a50ddd8a046ac60c41cab5d06097a6700e0b68bdd71372f8e059599` | `bab77a94e1fc0054fabc63ca52dc7ff1bb0da86cb7fb6787ecce9faad7c59e55` |

Both jobs and all their steps pass. Independent API captures, artifact bytes and
full logs agree on 43 evidence records per job and all selected test-source hashes.
Each job passes 171 intake, 43 runner, 38 capture, 33 store, 10 pipeline and 19 packet
tests: 314 executions, not additional unique cases. Physical checks pass 56 PFT
Rust, 528 Census Rust, 14 Solidity tests, four historical fork executions and 16
verified disconnected replay steps. Original-source Git-object checks pass before
and after execution, with unchanged source/store roots and workflow bytes.

The new economics report is recomputed inside the disconnected worker. The log
report exactly matches the v4 packet. Independent arithmetic confirms the five
gas budgets, 14 cost categories, one retained diagnostic and eight unobserved rows.
All paid costs and execution-specific Titan coverage remain unknown. The active
policy binds Titan as payer with zero operator allowance and no own-gas fallback.
Six dependent batches remain blocked after ancestor revocation and SQLite restore;
forensic bytes are retained. H21 makes no claim of a new liquidation EVM execution,
a request to Titan, or physical Rust transport of its new economics batch.

H19/H20's separate Rust probes also pass with their original 28- and 29-artifact
inventories and zero certified ranges. Old runtime packets retain their old scope.

- forks post-audit commitment: `b878d1fff2ecd211258b53f4146a78852b10fd4d324c5e42d895390fb751c53b`; log SHA256: `d1295932baf0d5a4ed0800784e922dab6820de9f17ca826dbac93da62a89cfaa`.
- replay post-audit commitment: `3b28670664f06b702c13f323bf2ed18c1da3c3734f8dfea890bab614ddca7dae`; log SHA256: `de6a04d1d9d9a7c60e853e8b7164baf166e9bae0d72d3be75b60df5055a8b1aa`.
- Economic replay commitment: `a024c1b0b6675a5bd0e56c509b230e96e0e3c514aa0776a6e315397c4738ff5b`.

H21 engineering closure: **4/4 (100% of this increment)**. Final local regression
remains **589/589 unique Omega tests**, 28 new, plus 19 separate original-auditor
cases. No failures or omissions in these recorded suites. Product certification
remains **0/36**, Census **0/9**, temporal sample coverage **3/9**, complete paid-cost
rows **0/127**, and Titan-covered executions **0**. The policy is implemented;
coverage for a concrete future bundle still requires its own evidence. Complete
market/cost evidence, real canonical reorgs and inter-host recovery remain open.
No supported overall product-completion percentage is asserted.
