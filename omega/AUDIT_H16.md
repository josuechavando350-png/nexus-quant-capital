# H16 — nine historical WETH cashflows with two price references

Local validation: **445/445** full Omega tests passed with original D15B/D16
archives and no failures/errors/skips, including 12 new cashflow tests. Isolation
passed for 118 reviewed Omega files, preserving all original source identity.
Exact-producer remote execution is pending. Certified components remain 0/36, Census remains
open, and the 45% product target is not declared achieved.

Recovered original source: nexus-engine run **37726618359**, success, artifact
**11527902751**, 1979 bytes, SHA256
`5ae6c45b53ded26f327270758c248f7f4ec0ff1365f550e54dcf28feb4a83a03`.
Original producer **a569b0a6ba11c0d12de3a1ac0d16d85b896933f6**, tree
**3c84f4fa3a2a0a62accde257029714177dc38b5a**. Run, artifact and commit identities
were read independently through GitHub before intake. The retained capture is
`evidence/weth-price-metadata.json`; no source workflow was activated.

All nine WETH/WETH rows reproduce the unchanged original auditor's amounts and
rank ordering. The two price references cover ranks 1 and 3; seven prices remain
unknown. Rank-one gross-minus-gas is 96136430295441074 wei. All nine observed
liquidator identities bind to the H15 capture and original event commitments.
The original five-bps fee is retained only as a hypothetical sensitivity. No
row proves complete net profit or oracle causality.

Report commitment:
`69ab8830eb3e4184c25a83742b6b6648150d53e39cab13ff4ebaab82a6a0da9f`.

Tests cover real source conservation, integer arithmetic, missing prices, unknown
costs, hypothetical-fee semantics, false authority, no-network reproducibility,
rehashed fabricated profits/identities/prices, row substitutions, archive and
metadata pin tampering, symlinks, full store restore, revocation, and internally
consistent stores containing altered base or derived reports. No synthetic case
is counted as historical economic evidence.

CI's existing `test*intake.py` pattern includes these tests alongside H14/H15.
Workflow bytes, permissions, artifact bounds and physical-gate steps are unchanged.
The bounded runtime pipeline report still represents H14; the intake test record
also binds the later test source hashes. Pending runs are not passing evidence.
