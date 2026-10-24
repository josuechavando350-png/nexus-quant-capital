# H14 — reviewed bounded artifact migration

This extends the one already authorized branch-scoped Omega workflow. The 106
legacy workflows remain disabled. Repository, branch, read-only GitHub token
permissions, standard Ubuntu runners, two physical stages, 60-minute job bounds
and exact checkout pin are unchanged.

New trigger coverage: `omega/*.py`, `omega/evidence/**`, the reviewed workflow
template and active workflow. Documentation-only changes do not rerun the jobs.
The template and active definition are byte-identical and bound by the new
`isolation.py` SHA-256. Old H13 retained evidence continues to verify the OLD
workflow bytes from its OLD producer; its identity is not rewritten.

Each successful job now also runs the retained historical intake, local durable
store, pipeline and artifact-consumer test suites, then executes and independently
verifies the real 139-event/127-receipt pipeline. Original physical fork/replay
gates remain mandatory. A failure prevents artifact publication.

After the physical gate, the runner assembles one `runtime.json` of at most
1 MiB: explicit producer identity, exact code/workflow hashes, committed evidence
records, targeted test reports, local pipeline result and physical-stage result.
It does not serialize environment variables, credentials, whole directories,
private keys, arbitrary logs or caches. Output is outside the checkout.

Upload action: `actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02`.
Its exact `action.yml` was reviewed through GitHub. Path is the single explicit
runtime file; hidden files false, overwrite false, missing file error, compression
6, retention **one day**. Unique names include stage, exact commit and run attempt.
At most two bounded artifacts are created per successful run. No billing plan,
permissions, subscriptions or repository settings are changed. Storage is bounded;
this document makes no unconditional claim about an account's billing allowance.

`runtime_artifact.py` verifies downloaded ZIP bytes against a separately
retrieved GitHub run/commit/jobs/artifact capture. It requires an expected producer
and an **out-of-band expected capture digest**. The digest is an external trust
input; arbitrary caller-supplied JSON does not authenticate itself. Offline output
states `RUNTIME_ARTIFACT_MATCHES_EXTERNAL_CAPTURE`, never that a new API query
occurred. The post-audit records the independent retrieval and exact artifact IDs.

Both jobs, upload steps, artifact sizes/digests, repository/branch/run/attempt,
Git commit/tree, code bytes, record commitments, tests, unchanged source isolation,
fork consensus/replay result and authority boundaries are checked. These are
runtime artifacts of NQC, but they are **not a canonical PFT/Census closeout**.
Original phase criteria and per-component certification remain unsatisfied.

Primary references reviewed: the exact action.yml above and
https://docs.github.com/en/rest/actions/artifacts?apiVersion=2022-11-28 .

H22 runtime v5 keeps this existing workflow unchanged. Replay requires the new
`inclusion-fees` proof alongside the v2 Rust transport, v3 dependency and v4
economics proofs. It binds the inclusion reader's producer bytes, the retained
capture, the seven-batch SQLite recovery and the current Titan-only gas policy.
All four proofs must use the physical replay's isolated network namespace. The
new record must match the economic record's source commitment and policy.
Prior versions remain accepted only with their own record/code inventories;
in particular, v4 evidence cannot satisfy the v5 inclusion requirement.
