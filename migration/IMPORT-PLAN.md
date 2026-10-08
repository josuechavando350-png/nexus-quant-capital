# NQC-only repository import

## Destination and approved isolation boundary

- Destination: `josuechavando350-png/nexus-quant-capital`, public repository ID `1411047452`.
- Source: `josuechavando350-png/nexus-engine`, repository ID `1333360261`, commit `e259739c9f75fedcd1061d2f78d6b8852e7a3060`, tree `c9cc97b31daa96c3c427c6781333a706e988f342`.
- Publish an independent root containing only NQC and migration documentation. Original commit ancestry is not transplanted. Original history stays unchanged at its original repository, with an independently verified local-only Git bundle as additional preservation.
- Include 531 original NQC files and 106 historical NQC workflows as `.yml.disabled` files. Only six test files differ from source; their filesystem lookups point to disabled workflows without weakening assertions.
- No active Actions workflow, launcher, deployment, client app, TypeScript workspace, unrelated runtime, Vercel configuration, token, repository permission change or new subscription is part of this import.
- Three preserved historical NQC boundary documents mention an excluded client by name. They contain no client implementation, data, settings or credentials.

## Immutable source/evidence map

`source-manifest.json` records every source path, Git blob, SHA-256, mode,
destination and transformation, plus the exact original PFT/Census commit/tree
references. Original PFT protected paths remain byte-identical. Source repository,
run, artifact, workflow and certificate identities must not be renamed.

D06 original evidence remains pinned to:

- Original repository `josuechavando350-png/nexus-engine`, ID `1333360261`.
- Commit `a33a012591cd6625ddb921d995bb1bd95b4a5406`; tree `eda36fdc07e82ccdcc9666799fa8fe21aacc7f1d`.
- Workflow `NQC RMC-006 Aave Discovery`, ID `369620615`.
- Run `36820687233`, attempt `1`; artifact `11143129177`.
- ZIP SHA-256 `1cdb46fca52ebf1e0e2094b1c14b19384ecb7beceb50229b967592ab7a0308b4`.
- Store root `e3d2b0739d3e5affea6b337540cf3cb9b2caaedd438656d2759105d39dacba03`.
- Original observation block `26095351`; hash `0x0d7a15fbb72e69696a33c65bc20902fe08e5630862ada64b065a97405c70c781`.

The original ZIP and historical full-repository Git bundle are not included in
the publishable payload. Public source preservation is reference-based, with
local evidence copies held separately. Artifact retention/availability must be
checked before any new canonical run; rehosting an authenticated ZIP requires its
own reviewed publication and must preserve original provenance.

## Safe transfer checklist

1. Read back destination owner, ID, visibility and empty/default-branch state.
2. Verify the existing GitHub App includes only the newly approved repository in addition to its previous selection. Do not change permissions or any other integration as part of transfer.
3. Review the frozen all-file manifest and independent safety report. Keep local evidence, original bundles, build targets and caches outside the publishable tree.
4. Create an independent initial commit in the new repository. The exposed GitHub Contents API can seed an empty repository; then Git Data blob/tree/commit APIs can import the reviewed files. Per-file API import creates new commit identity; do not claim it preserves the local packaging commit SHA.
5. Build a complete tree from scratch, with no inherited tree or cross-repository parent. Validate returned Git tree against the local reviewed tree before changing a branch ref. Avoid an intermediate partial tree as the final reported result.
6. Update only the new repository's reviewed branch using the known expected parent. No mirror push, tags, old branches, PRs/comments on the source repository or force push.
7. Read back the exact new commit/tree, recursively verify every path/mode/blob, confirm no active workflow and no unexpected files, then report the new producer SHA. An import does not establish canonical CI authority.

If an authenticated normal Git push route is later available, a reviewed clean
single-ref bundle can be pushed to the named new repository. Do not retrieve
connector credentials, guess proxy endpoints, use GitHub Import or push `--mirror`.

## Why existing certification cannot just move

The legacy D06 workflow requires ancestor checks and old source objects in the
same checkout, runs monorepo pnpm gates, asserts the old `GITHUB_REPOSITORY`, and
downloads artifacts from that repository. None of these assumptions establishes
authority for this new independent root. Its file remains inert and unchanged.

`ci/nqc-census/materialize_effective_source.py` verifies the original certified
PFT commit/tree, ancestry and protected paths before materializing original Git
objects. It is preserved unchanged, and remains blocked in this independent root.
Never delete or bypass its ancestry gate. Other legacy producers similarly bind
their original source repository or source-catalog Git blobs.

## Minimal truthful recertification adaptation, separately reviewed

1. Authenticate the immutable original seed and source commit metadata at the
   original repository. Preserve all original IDs/hashes/timing. Verify actual
   cross-repository artifact access before relying on the new job token; its
   permissions must not be assumed to reach old artifacts.
2. Obtain original objects read-only into a distinct evidence object store. Run
   original ancestry/authority checks there, and bind exact required subtrees to
   this repository using source Git blob identities and content hashes. Do not
   claim the new root is descended from the old certification commit.
3. Review an explicit standalone/source-object-store adapter. Include negative
   tests for changed source object, substituted repository, missing parent,
   altered protected bytes, source artifact mismatch and relabelled certificate.
4. Use an NQC-only validation job. Keep recovered PFT source immutable, apply its
   pinned overlays in a separate build copy, and run applicable Census/PFT gates.
5. Bind the new producer repository ID `1411047452`, exact new commit/tree, new
   workflow identity/run/attempt/artifact and actual verification timestamps in a
   separate new authority record. The old observation timestamp stays unchanged.
6. Replay only the verified original seed in the enforced disconnected namespace,
   preserve source bytes, verify deterministic closeout and run the real-package
   negative matrix. No live acquisition, signing, broadcasting or spending.
7. Only a successful exact-head new run, independently read-back final metadata,
   authenticated artifact and downstream consumer validation can establish new
   canonical authority. D14 and other downstream gates stay blocked until then.

## Validation scope

See `VALIDATION.md`. Import identity, offline code tests and historical evidence
checks have separate meanings. Original PASS labels remain historical. Do not
call this repository recertified or all tests green when aggregate discovery has
documented harness/input failures.
