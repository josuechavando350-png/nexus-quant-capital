# Retained time-only diagnostics

H18 joins the authenticated original time-only artifact to the H17 predecessor
states and the same nine WETH/WETH historical cashflows. It preserves H17 as an
unchanged source report. The new report and all upstream reports are recomputed
from their pinned source bytes on admission, query and recovery.

The trust anchor is the reviewed GitHub capture for original nexus-engine run
37740704145, producer 030d95c705a1fce77c3345cada4c8cd698f4a1db, artifact
11533288894. The metadata and nine ZIP members are pinned by byte count and SHA256.
The inner manifest covers eight payload members. Original Python, Solidity and
Foundry configuration hashes match the preserved source tree. The retained
formatted Solidity hash refers to the original build; H18 performs no formatting
or mutation of original source.

Every temporal witness must match the H17 transaction, rank, borrower fingerprint,
preceding block number/hash, winner block number/hash and preceding health factor.
Both original timestamp operators, dRPC and BlastAPI, must agree on all three
anchors. The window must contain consecutive block numbers, strictly increasing
integer timestamps and at most 120 seconds, as required by the original source.
These three windows are each 12 seconds. Original fork execution used **dRPC
only**. Timestamp agreement does not imply independent fork agreement.

The parser requires one passing retained test and exactly one canonical uint256
value per measurement. It checks raw-log health factors, collateral/debt values,
threshold flags and source-conclusion rows. The condition is strictly HF < 1;
HF = 1 is not below the threshold. Rank two increases in HF; no assumption that
time always worsens health or that health varies linearly is permitted.

One retained time-only endpoint is below one; two are not. Six cases remain
unobserved. Endpoint values do not locate the first crossing, establish actual
transaction prestate, identify an oracle/interest cause, replay original intrablock
transactions, or prove prospective discovery, executable liquidation or capture.
All paid costs and profits previously unknown stay null. The new consumer performs
no fresh chain acquisition or temporal fork; source executions are historical.

Evidence storage remains append-only and content-addressed. Queries reject missing
or extra sources, altered upstream reports and revoked batches. Revocation retains
source bytes; simulated revocation is not a demonstrated real chain reorg. The CLI
rejects symlink paths, output inside the repository and existing output files.

Revocation is batch-local. Duplicated source bytes in another active batch do not
automatically inherit that revocation. Cross-batch dependency invalidation and
current-chain canonicality require a separate integration before any reorg or
live-candidate admission claim. H18 grants neither claim.

H18 grants no certification, phase advancement, signing, broadcasting, spending or
deployment authority. Certified components remain 0/36. Its tests are included by
the existing CI intake pattern; no workflow or permission change is needed.
