# NQC V2 — isolated recovery of NQC-only research from nexus-engine
Status: IN PROGRESS, no certification of migrated producer. Last verified source snapshot: `josuechavando350-png/nexus-engine@21e7df356600d411a5bd5371fa2a0d7292944703` (Git tree `6842333ac78db36ddd11ee7dd2e926fd05e771d9`). Destination parent: `josuechavando350-png/nexus-quant-capital@b737723e0e429a40d993cf2433bc4d92c6316829` (PR #3).

Purpose: preserve later NQC-specific source code and historical workflow evidence absent from the dedicated NQC repository. Files under `source/` preserve original paths underneath this inert migration directory, and have not been admitted as the runtime producer. Existing imported/certified source files, `main`, live workflows and client apps are not altered. Source Git blob SHA must match destination Git blob SHA for each recovered file; do not re-sign, rename or transfer a historical certificate.

Workflow definitions must be preserved as `.yml.disabled` outside `.github/workflows`. No authorized LIVE transactions, wallets, gas spending, sponsor deposits, deployment, CI activation, code publication outside the already public repositories, or financial contracts.

Economic status: authenticated historical competitor settlements and local EVM evidence are not NQC receipts. NQC-owned realized P&L remains USD 0; EntryPoint Robinhood code parity, L2 expiry, complete UserOperation gas, external non-recourse underwriting, prospectivity and competition remain open. Do not apply a CI PASS to economics.

This partial checkpoint will be expanded with a full source-path/commit/blob manifest, disabled workflows and missing NQC code, followed by separate validation. Do not merge while incomplete.
