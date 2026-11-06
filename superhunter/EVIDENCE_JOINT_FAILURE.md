# SuperHunter — bounded joint loss of forensic evidence (M1)

**Status:** new offline source-code implementation, dependent on PR #53. The input is a previously verified **private** evidence-common-mode package, its ablation, path-audit and triage artifacts, and the original source map. This unit neither finds nor confirms vulnerabilities, and is not a remote testing tool.

## Research question

Single-source ablation can miss evidence dependencies. Suppose observation O has two locally valid references to **different** byte-level bundles; neither bundle loss alone creates a missing evidence slot, but removing both does. This module enumerates all combinations of **distinct `COMPLETE.json` byte hashes** from order one through a specified order of at most three. Alias IDs that refer to identical bundle bytes are treated as **one failure unit**.

For each combination it recomputes the *original triage scoring algorithm* after virtual source removal. It reports, for each candidate, inclusion-minimal bundle-loss sets that newly expose evidence gaps, their source IDs, and the resulting priority loss. All outputs are deterministic, replayable and kept private. No original evidence is modified.

The result reports whether **all nonempty bundle failure subsets** were enumerated; when there are more bundles than the requested order, higher-order dependencies explicitly remain **unexamined**. The algorithm runs on at most eight source IDs and failure order at most three, bounding worst-case enumeration at 92 nonempty scenarios; 32 candidate hypotheses are supported by the existing triage schema.

## Commands

```bash
python3 -m superhunter audit-joint-evidence \
  --common /privado/common --ablation /privado/ablation \
  --path-audit /privado/path --triage /privado/triage \
  --sources /privado/sources.json --max-failure-order 2 \
  --out /privado/joint-nuevo

python3 -m superhunter verify-joint-evidence \
  --bundle /privado/joint-nuevo --common /privado/common \
  --ablation /privado/ablation --path-audit /privado/path \
  --triage /privado/triage --sources /privado/sources.json
```

Both commands verify upstream evidence and compute the result afresh, validating source snapshots, input/manifest hashes, receipts and expected structure. The verifier rejects modified results even if their public manifest hashes have been recalculated. Files containing private evidence must **never** be placed in public GitHub.

## Limits and acceptance

- Different hashes **do not prove independent producers or trustworthy custody**; identical hashes only prove exact local byte equality. Labels, priorities and graph links are **operator-declared**.
- A **minimal evidence-gap set** is not an attack path, critical impact, probability, CVSS score or security certification. This module cannot turn `potential_impact=critical` into a confirmed critical vulnerability.
- No chain transactions, RPC, network connections, target exploration, active testing or automated bounty submission.
- The feature gate requires positive, negative and tamper-resistance tests, CLI replay in separate processes, independent verification of the unchanged predecessor package and the full QA inventory. Keep the work as draft until integration and historical NQC isolation are reviewed.
