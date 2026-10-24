# H13 — retained CI evidence consumer

This consumer verifies one reviewed capture of H2 run `39859932654`, attempt 1,
producer `e21d528dabd83d7f14e7f236b9e6d4e3fc1706f7`. It does not authenticate
arbitrary caller-provided JSON or convert a historical run into a new-head run.

The capture was independently retrieved through the connected GitHub API at
`2026-10-22T22:25:54.894Z`: run, jobs, artifact inventory, commit and both job
logs. The workflow comes from the producer Git object. The ZIP preserves all
seven UTF-8 payloads, without summarizing or rewriting runner identities.
Its pinned SHA-256 and each member hash bind the reviewed capture. The consumer
also verifies the producer commit/tree and workflow against real Git objects.

The trust boundary is explicit: the reviewed pin depends on the original
authenticated retrieval. A local hash does not prove remote origin by itself.
Offline verification checks this retained snapshot and does not query GitHub,
reexecute H2, reauthenticate D06, or establish current market observations.

The consumer fails closed on altered pins/archives, duplicate or unknown ZIP
members, traversal, symlinks, special files, oversized expansion, duplicate JSON
keys, wrong repository/branch/commit/tree/run/attempt/workflow, missing or failed
jobs/steps, invalid timings, incomplete inventories, changed evidence digests,
nonzero commands, partial tests, failed fork consensus, incomplete replay pairs,
network-isolation failures, or economic/certification authority.

The package contains 29 fork and 25 replay JSON commitments. Semantic checks
reconcile 41 runner tests per job, 56 PFT Rust tests, 528 Census Rust tests,
14 Solidity tests, four fork executions and 16 replay steps. Output digests
printed by commands are retained inside the pinned raw logs; those digests are
not independently reconstructed from GitHub's timestamped stdout rendering.

The capture ZIP is 98297 bytes, stored in Git. It is **not** a GitHub Actions
artifact: the captured API inventory has zero artifacts, `artifact_id` remains
null and `artifact_authenticated` is false. Canonical recertification, Census
closure, certified-component count and economic authorities remain unchanged.
This consumer closes reproducibility of H2's post-run log audit only. A new
authenticated runtime artifact and the remaining component gates are still due.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 omega/ci_evidence.py
PYTHONDONTWRITEBYTECODE=1 python3 omega/ci_evidence.py --expected-producer e21d528dabd83d7f14e7f236b9e6d4e3fc1706f7 --report /tmp/omega-h2-capture-report.json
```

`--report` is exclusive-create and never overwrites an existing file. The
consumer reports its own source hash separately from the physical producer.
Any other `--expected-producer` fails; subsequent documentation or consumer
commits cannot borrow this old execution as their own runtime certificate.

The existing H2 workflow definition, permissions, triggers, historical disabled
workflows and runner sizes are unchanged. Its Python entry point now runs this
consumer and its adversarial tests before the physical gates. No artifact
uploads, new service, subscription, secret or signing permission are added.

The workflow retains its existing five-path trigger filter. H13 was tested
remotely because this change updates `h2_actions.py` and `isolation.py`;
future edits limited to the consumer/capture files alone do not trigger it.
Run the affected offline tests and isolation on every such edit. Extending the
workflow filter belongs to the next reviewed workflow migration; no automatic
coverage of those future edits is claimed here.
