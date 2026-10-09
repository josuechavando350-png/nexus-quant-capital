# Evidence-bound temporal research package v1

This additive research package constructs episode rows from immutable prepared witnesses and independently reconstructs their coverage, conservation, censoring and dispositions. It is offline and uses only Python's standard library. It does not change historical source files, D06, stage pins, workflows, deployment settings or final Census authority.

## Run from repository root

    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s research/temporal-evidence-v1 -p 'test*.py'

The 40 tests include permanent runners for 29 independently designed source-negative cases and ten fully rehashed output/inventory forgeries. Tests use bundled diagnostic JSON copies, so the directory also works after relocation outside this repository.

Generate a fresh, explicitly synthetic example in separate output directories:

    PYTHONDONTWRITEBYTECODE=1 python3 research/temporal-evidence-v1/synthetic_fixture.py --out /tmp/temporal-input
    PYTHONDONTWRITEBYTECODE=1 python3 research/temporal-evidence-v1/build_temporal_package.py --input /tmp/temporal-input/source.json --evidence-root /tmp/temporal-input --out /tmp/temporal-package
    PYTHONDONTWRITEBYTECODE=1 python3 research/temporal-evidence-v1/verify_temporal_package.py --package /tmp/temporal-package

Output directories must not already exist. Package output must be outside the immutable input directory. Examples and logs are generated when needed rather than committed.

## Contents

- `temporal_common.py`: strict JSON/types, safe file IO, nonzero SHA-256 and size bindings, exact order points, population and prepared witness schemas.
- `build_temporal_package.py`: deterministic chronological episode construction and typed blocking dispositions.
- `verify_temporal_package.py`: a separate coverage/episode reconstruction; it never imports or calls the builder and compares exact canonical expected output bytes. Formats, cryptographic IO and narrow evidence primitives are shared, so this is not a second independent EVM implementation.
- `synthetic_fixture.py`: clearly labeled, non-evidentiary fixture generator.
- `test*.py` and `regression_cases/`: positive, negative, determinism and independent-review reproductions.
- `real-inputs/`: four byte-identical historical/current JSON declarations for diagnostic refusal tests; `provenance.json` binds their original repository, commit, blob, SHA-256 and size. These are aggregates or blocked declarations, not recovered ledgers or new authority.
- `DATA_REQUIREMENTS.json`: exact missing evidence and unsupported production obligations.

## Guarantees within the supported prepared-witness format

All required trigger classes must have exhaustive interval structure and bound provider/operator identities. Derived interest-only triggers use their own typed causal input, algorithm and equivalence commitments; a generic event or invented second RPC provider cannot replace a deterministic derivation. The relevant acquired inputs must cover the entire derived interval. Real provider identity and actual acquisition truth still require external authentication.

Each declared population lineage is conserved. Trigger linkage is exact-order or immediate PRE_TX/LOG to POST_TX in the same transaction. An observed birth and a measured terminal transition need admitted immediate causes; missing causes remain evidence insufficiency. Exact start/end order points prevent the start of the final block from masquerading as its end.

An unknown left-censored birth never gains an invented full lifetime. Right-censoring is permitted only at the declared end boundary. Missing acquisition tails are blockers, even if the last known state was healthy or recovered. Competitor arrival remains explicitly unobserved.

`PROVEN_REJECTION`, `EVIDENCE_INSUFFICIENT` and `ACQUISITION_INCOMPLETE` are distinct. Supported structural negative predicates require a same-lineage, exact-order witness in admitted state history; detached or contradictory states do not prove rejection. Unknowns cannot be renamed into a zero-UNKNOWN result.

## Authority and economic limits

Every result keeps `terminal_authority=false` and `real_market_census_closed=false`. Synthetic inputs remain `SYNTHETIC_NON_EVIDENTIARY`. A complete local candidate means internally complete supplied prepared-witness structure only. It does not prove the user's broader Census scope, raw chain acquisition, actual population completeness, provider independence, EVM execution, canonical-chain authority, capture or profitability.

The report also keeps chain semantic replay, provider identity, economic semantic verification and terminal-outcome semantic verification false. The economics record binds a supplied net amount and references; it does not independently recompute all costs, native-gas feasibility, routes, capital or shared resources. Typed terminal provenance is not an independently decoded real liquidation or NQC capture.

Builder exit 0 means locally complete prepared-witness structure. Incomplete real inputs and blocked packages return 2. Verifier exit 0 can verify either a complete **or blocked** local result; inspect `source_status` and `material_unknown_count`. A valid audit of a blocked package is not admission.

The historical D15B aggregate covers a different population/window from the later 857-account, 7,200-block study. Its 6,720 missing event blocks remain missing; neither study silently replaces the user's wider scope. No raw original ledger was recovered by this package. Current real inputs are refused with their missing data listed.

## Policy boundary

This module does not change capital policy or economic thresholds. Historical sources retain their original constraints. It neither authorizes nor performs funding, wallet creation or live execution. Economic decisions remain outside this technical package.

## Repository boundary

This directory is self-contained and additive. It leaves every pre-existing file unchanged. The original `migration/verify_isolation.py` is intentionally a verifier of the historical import layout, not a general validator permitting new research directories; it is not modified here. Base-file preservation and the additive tree delta must be checked separately when reviewing this draft. No workflow is added or activated, and no historical certification transfers to this package.
