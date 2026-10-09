# Local historical-source adapter proposal

Status: local proof of implementation, pending independent review and any separate
approval to publish code. No active workflow, network acquisition, credential,
remote mutation, original repository change, or new certification is included.

## Two identities, two roots

`materialize_historical_source.py` is an additive bridge. The independent consumer
retains its own exact commit/tree and repository ID `1411047452`. A separate
short-lived original-history checkout retains source repository ID `1333360261`,
source commit `e259739c9f75fedcd1061d2f78d6b8852e7a3060` and source tree
`c9cc97b31daa96c3c427c6781333a706e988f342`. The new consumer is not represented as a
descendant of any original certificate. Its history must be independent.

The old materializer, profile, recovered source, overlays, locks, reimplementations,
PFT closeouts, original D06 source pin, archived workflows, and complete frozen
core/store/chain are unchanged. The bridge adds no alternate semantics to them.

1. Read a specifically pinned **local-only** Git bundle, verify its entire SHA-256,
   exact ten-ref inventory, pack integrity and complete object graph. Reject
   replaced refs, grafts, shallow history, external alternates and changed refs.
2. In a fresh temporary repository with no hooks/remotes, sparsely materialize only
   `ci/nqc-census`, `ci/nqc-protocol-fork` and `nqc-census`. Client/workflow paths
   are not checked out. Original historical objects remain temporarily in this
   separate Git directory and are never copied into the consumer or output.
3. Retain original PFT tree and ancestor verification, D06 and recertification-base
   ancestry, D06-to-RMC003.2 ancestry, RMC003.2-to-source ancestry, whole
   core/store/chain immutability, PFT protected-path immutability and original
   D06 provider/scope/toolchain immutability. These operate against original
   history, never a fabricated relationship to the new root.
4. Validate the clean new consumer's exact commit/tree, pinned migration manifest,
   pinned isolation verifier, a closed, hash-bound standalone composition, all 637
   original source/workflow mappings and all ten
   original commit/tree references. Independently compare the complete frozen paths
   across source and consumer. Bind this adapter's own bytes to the consumer commit.
5. Run the unchanged historical materializer in a fresh disconnected Linux network
   namespace using the existing historical network-proof function. If namespace
   isolation is unavailable, fail. No live fallback exists. Clear inherited Git,
   Python, token, proxy and SSH environment authority; disable all Git protocols
   and lazy fetch. Reject executable/config-include/redirection Git settings and
   local attributes before any consumer Git command. The original overlay script
   and input profile remain pinned.
6. Preserve the original `MATERIALIZATION.json` unchanged. Emit
   `HISTORICAL-ADAPTER.json` separately, identifying the original source and the new
   consumer. Recheck consumer and historical authority after execution. Publish a
   new output directory only after all checks pass using atomic no-replace rename;
   failures leave no output claim. Bundle paths with any symlink alias are rejected.

The outer receipt explicitly says canonical recertification, certification
transfer, source-package authentication, source-package replay, live fallback and
production authority are false. The old materialization receipt remains a
historical source receipt and is not promoted into new execution authority.

## Evidence transport gap discovered

The migration's original frozen history bundle contains the complete ancestry of
its sole e259739 reference. It does **not** contain D06's original seed commit
`a33a012591cd6625ddb921d995bb1bd95b4a5406`, which is not reachable from that ref.
Therefore it cannot alone support the original D06 frozen-provider checks or all
ten manifest reference checks. The adapter initially failed on that exact absent
object; the frozen bundle was not changed.

A separate complete original-evidence bundle was built from a private local copy
of the original evidence object store, rooting all ten manifest refs. SHA-256:
`4568af03c4850c6aabf09b5b2897ed3d1fc856f439497f866ca92e31b7aaadac`.
It includes original monorepo history and must remain local-only. It is **not a
publication candidate**, and it is not included in this repository or code patch.
Git pack representation can vary by creation environment; this local prototype
intentionally accepts only this exact reviewed bundle, not a caller-selected hash.

For a future reviewed CI implementation, prefer a distinct read-only acquisition
step from the original public Git repository for the exact ten required commits,
including their complete ancestry and trees, into an isolated object store. Verify
source repository identity through the official authenticated/read-only metadata
path plus the fixed commit/tree pins. Do not publish the whole historical bundle,
push old refs to the consumer, fetch by a moving branch, or treat a repository name
in local JSON as proof of GitHub origin. The additive `acquire_historical_source.py` now implements this separate read-only
acquisition step with a fixed HTTPS Git URL, exact SHA-to-ref refspecs, no moving
branch, no redirects/proxies for metadata, no token and no credential helper.
It checks current repository identity and all ten commit/tree metadata responses.
The adapter's `--source-object-store` mode independently rechecks exact refs,
complete fsck/object graph, fixed trees, metadata identity, ancestry, protected
paths and source manifest before disconnected materialization. It never accepts a
caller-provided arbitrary bundle digest. Source acquisition is outside the network
namespace and is explicitly distinguished from disconnected materialization.

Direct public acquisition could not run in the current executor because
api.github.com DNS resolution is unavailable. Ten current official API metadata
responses were instead read through the existing GitHub connector for local
verification against the complete pre-existing original object store. That local
integration does not claim that the direct HTTPS/Git transport was executed.

## Running the local proposal

Use the supplied local-only complete bundle outside the consumer checkout. Commit
these adapter files to a separate local proposal checkout first. Supply exact
consumer values read from that checkout; these are local identities, not proof of
a remote run.

```sh
python3 -I -B migration/materialize_historical_source.py \
  --consumer "$PWD" \
  --historical-bundle /external/path/complete-original-evidence-LOCAL-ONLY.bundle \
  --output /external/path/new-effective-source \
  --expected-consumer-commit "$(git rev-parse HEAD)" \
  --expected-consumer-tree "$(git rev-parse HEAD^{tree})"

NQC_ADAPTER_TEST_BUNDLE=/external/path/complete-original-evidence-LOCAL-ONLY.bundle \
NQC_ADAPTER_TEST_INCOMPLETE_BUNDLE=/external/path/original-history-LOCAL-ONLY.bundle \
python3 -B -m unittest discover -s migration -p test_historical_source_adapter.py -v
```

For the operational transport, run acquisition before disconnecting:

```sh
python3 -I -B migration/acquire_historical_source.py --output /external/path/acquisition
python3 -I -B migration/materialize_historical_source.py \
  --consumer "$PWD" \
  --source-object-store /external/path/acquisition/source-object-store \
  --historical-source-metadata /external/path/acquisition/source-metadata.json \
  --output /external/path/effective-source \
  --expected-consumer-commit "$(git rev-parse HEAD)" \
  --expected-consumer-tree "$(git rev-parse HEAD^{tree})"
```

`verify_standalone_composition.py` preserves the original verifier byte-for-byte.
It verifies the frozen 645-file baseline and a finite list of new helpers, the one
reviewed workflow byte hash, and the immutable original ZIP hash/size. The original
verifier sees a complete authenticated baseline projection, never a selectively
reduced NQC tree. An unexpected workflow, deployment file, evidence addition,
changed ZIP, or modified historical verifier fails. The addition manifest is
content binding under the externally reviewed expected consumer commit/tree; it
is not a certificate that can approve itself. The same YAML may be staged only at
its fixed inactive migration path or its one reviewed active path, never both.
The active location remains uncreated pending publication review.

The public integration baseline is commit
`16e352225ba8a6a931834c4edf3d86d9a2924b7d`, tree
`d9b498f784db19aed4436b0f46ceb4e05766cb6c`. Earlier local packaging commits are not
public producer identities. Local proposal commits and test receipts remain
local-only until integrated against that public baseline.

Linux `unshare --user --map-root-user --net`, Git and Python standard library are
required. There is no dependency installation. Output must be a new path outside
the consumer. Original source and full historical bundles must not be added to
this repository. The consumer migration verifier and original source manifest
are exact reviewed version pins; future intentional changes require independent
review and explicit pin revision, not permissive runtime overrides.

## Remaining gates, deliberately not claimed

- Fresh authentication, expiry/availability checking and audited local transport
  of original D06 ZIP/run/artifact metadata remain separate. The unchanged seed
  stays source repo `nexus-engine`, run `36820687233`, artifact `11143129177`, ZIP
  SHA-256 `1cdb46fca52ebf1e0e2094b1c14b19384ecb7beceb50229b967592ab7a0308b4`.
- This adapter does not run Census or PFT Rust/Solidity builds, deterministic D06
  replay, the real-package replay negative matrix, or produce a new closeout.
- Enabling any new NQC-only workflow requires separate review/authorization. The
  old disabled workflow's original-repository assertion and monorepo pnpm job
  cannot be enabled unchanged. Original workflow bytes remain preserved.
- New repository ID, producer commit/tree, workflow/run/attempt/artifact and real
  verification timestamps need their own exact-head successful run, immutable
  output, and independent GitHub metadata read-back. New consumer receipt parsing
  and downstream acceptance, including D14, remain blocked until then.
- Local Git content addressing validates content/ancestry against trusted pins;
  it does not independently prove which hosting account first supplied the bytes.
- This proof does not establish live-market completeness, PFT reclosure,
  profitability, acquisition freshness or production permission.

## New producer trigger and bounded authority

The inactive new workflow uses only `push` on
`refs/heads/nqc/d06-standalone-certification` in repository ID `1411047452`.
It uses `contents: read`, fixed source/seed identities, and no launcher,
`actions: write`, PR event, deployment or live RPC. GitHub event head, workflow
head, checkout commit/tree and fixed branch must agree. Runtime push context
records before/after/created/deleted/forced; forced/deleted pushes fail and after
must equal the producer commit. The original seed's event remains
`workflow_dispatch` and is authenticated by the unchanged original verifier.

This removes dependence on a dispatch tool, but deriving an exact runtime head
is not proof of prior review. The publisher/consumer must independently bind the
approved event/ref/commit/tree and inspect final GitHub run, jobs and immutable
artifact metadata. Workflow outputs remain noncanonical and explicitly state
that reviewed-producer authorization has not been independently verified.
The local full replay does not receive fictitious GitHub event/run/attempt IDs;
the GitHub-bound index stage is exercised only by labelled unit-test fixtures
until a real authorized job exists.

## Explicit ephemeral namespace privilege boundary

Historical materialization and the Rust build retain the reviewed sudo-drop
boundary: fixed system sudo/unshare create a disconnected network and private
mount namespace; setpriv restores the original nonzero runner UID/GID, empties
supplementary groups and all five capability sets, and enables no-new-privs
before any historical Python, Git, Rust or build shell executes. The default
user-namespace materializer remains available without automatic sudo fallback.

The prospective v1 replay boundary deliberately changes the runner method.
`premounted_d06.py` passes a fixed standard-library-only literal as argv to
root-owned `/usr/bin/python3 -I -S -B -c`, after fixed `sudo`, environment clearing
and `unshare --net --mount --propagation private`. No runner-writable helper file
or project module is loaded while privileged. This narrow setup closes inherited
FDs, permits only pipes or /dev/null for stdio, resets cwd to /, and traverses the
fixed authenticated-original path using O_PATH/O_DIRECTORY/O_NOFOLLOW/CLOEXEC.
It rejects a replaced inode/device/owner, aliases and descendant mounts. The -S
flag disables global site/.pth/sitecustomize startup hooks.

The source descriptor is cloned with open_tree; mount_setattr adds RDONLY with
attr_clr=0, preserving existing flags; move_mount attaches the detached mount to
the same pinned directory. Both source and destination are descriptors, so no
privileged mount syscall follows a swapped pathname. Source path identity,
read-only status and a distinct new mount ID are checked before descriptors are
closed. The setup then execs fixed setpriv, dropping UID/GID/groups/capabilities
and enabling no-new-privs before the replay shell. sudo may retain its normal
monitor; no privileged project worker or root shell is used.

`run_premounted_d06_v1.py` and `test_premounted_d06_replay_v1.py` are explicit new
prospective adapters. The original runner and negative-driver bytes remain
unchanged. Whole-file regression comparisons require every original computation
to stay identical except the documented mount-boundary and identity-receipt
changes. Both adapters require an exact private read-only mount with no child
mounts, the recorded new mount ID, and a real EROFS response to an anonymous O_TMPFILE|O_EXCL write-open on the
owner-writable source directory. The original extractor preserves directories as
0700 and evidence files as 0444; opening an existing evidence file for write can
return EACCES before mount writability is tested. EACCES is never accepted as a
read-only proof. Unsupported operations and other errors fail closed with numeric
and symbolic errno diagnostics. The v2 source-proof receipt identifies the new
probe precisely: no named file is created, no existing evidence is written or
truncated, and O_EXCL makes an anonymous inode nonlinkable. A correct read-only
mount rejects creation with EROFS; unexpected success immediately closes the
unnamed inode without writing, then fails. Original bytes, modes, membership and
directory timestamps are unchanged. The privileged setup and capability-drop
boundary are unchanged by this probe correction.

The unchanged original source authenticator runs before extraction/build,
immediately before replay in the mounted namespace, and after the negative
matrix. All replay bytes, source hashes, Rust gates and 22 real negative cases
remain required. Receipts bind original, prospective adapter, boundary-module
and privileged-literal hashes and explicitly deny unchanged-original-runner
identity or inherited certification. The index requires matching nonzero caller
identities and zero capabilities for materializer, build and replay stages.

This is not a filesystem jail. The runner retains its ordinary filesystem rights;
same-UID host processes and filesystem Unix sockets are outside this boundary.
Network proof establishes a fresh namespace, down loopback, no addresses/routes
and unreachable IPv4/IPv6 probes. All mounts exist only in the private namespace;
no host sysctl, AppArmor, credentials, permissions or network settings change.
Every setup descriptor is closed. Namespaces expire after their final process or
reference exits; the 240-minute job bound and hosted-runner cleanup remain the
outer limit for abnormal descendants. No stronger daemon-free teardown is
claimed. A separate authorized exact-head Actions execution and independent
GitHub artifact read-back are required before any operational result is accepted.

The hosted diagnostic established Ubuntu image 20261004.327.1, kernel
6.17.0-1022-azure, util-linux 2.39.3-9ubuntu6.6. The new boundary does not depend on
version-specific user-ID mapping flags. Its fd-based mount API requires Linux
5.12+ and libc wrappers (glibc 2.36+); absence fails closed without fallback.


## Independent negative-fixture permissions

The immutable authenticated source remains 0700 directories and 0444 regular
files. All nine copied-store negative fixtures are freshly copied, exhaustively
checked for matching named bytes/modes/ownership and distinct inode identities,
and rejected if any symlink, special file, hardlink, overlap or stale destination
is found. Deletion cases use their copied 0700 directories without relaxing any
permission. Report/provider JSONs continue to be newly created fixture files.

Only the selected corrupted-checkpoint or corrupted-chunk copied file temporarily
receives owner-write, through an already-open descriptor verified against its
immutable counterpart. The write descriptor must match the same inode before
truncation or writing. The original 0444 mode is restored in a finally path,
including write failures. Source descriptors are never chmodded or written; no
recursive chmod or broadly writable store exists. Fresh-copy verification,
preparation errors and write errors fail the harness rather than counting as
semantic rejections. Source hashes, modes, ownership, link counts, inode identity
and named membership are rechecked after all cases.

The exact fixture-copy and two mutation transformations are now explicitly
allowed by the whole-file comparison regression. All22 case selections, binary
invocations, failure/no-output expectations and post-rejection unchanged-store
assertions remain identical to the original driver. This changes prospective
fixture mechanics, not replay decisions or immutable original source files.
