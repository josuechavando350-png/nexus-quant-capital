# Active gas policy — Titan

User directive, 2026-10-23: Titan supplies gas; the former MXN 2,000 operator
allowance is withdrawn. The current architecture records `payer=TITAN`, zero
operator gas allowance, no operator prefund and no own-gas fallback. Principal,
collateral and guarantees may not use operator funds. Census and Shadow do not
use funded system wallets. No signing, broadcasting or phase advance is enabled.

The active policy supersedes the 2,000 / 500 / 1,000 MXN allowance and recharge
rules. Historical source reports and audit records retain their original policy
and provenance; they are not instructions to replenish an operator wallet.

Titan's [official Sponsored Bundles documentation](https://docs.titanbuilder.xyz/api/eth_sendbundle),
reviewed 2026-10-23, describes conditional funding after an insufficient-gas-funds
failure. The bundle must repay the sponsorship and increase the builder's balance.
This public mechanism is not a receipt or acceptance for a particular NQC bundle.
No numerical sponsorship ceiling, remuneration rate or inclusion guarantee is
assumed here. Funding from Titan does not make gas or builder compensation free.

Before any executable classification, the exact candidate, anchor, gas need,
Titan coverage, repayment and compensation must be evidence-bound. Missing
coverage/paid-cost values stay null. A fork surplus or hypothetical budget cannot
satisfy that gate, and a coverage failure cannot select an operator-funded fallback.
The architecture flag `execution_coverage_proven=false` describes the evidence
available at this checkpoint; it does not contradict the required payer policy.
