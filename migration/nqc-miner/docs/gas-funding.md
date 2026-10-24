# Titan-only gas: current policy and offline term review

The user's correction supersedes the former MXN 2,000 operator allowance: Titan
is the designated gas sponsor. Operator gas prefunding, fallback, principal,
collateral, guarantees and recourse are prohibited. This is the required policy,
not evidence that Titan has accepted or financed any particular execution.

The current policy is `funding::policy()` and is included in `nqc-miner about`.
The former budget types are available only under
`controls::historical_own_gas`, for historical accounting replay. They retain
their prior counters, limits and disabled spending API. No former allowance is
exported as a current policy. Existing evidence is not rewritten.

## Review a concrete plan

```bash
nqc-miner assess-gas-funding --input fixtures/gas_funding.synthetic.json
```

The fixture is artificial and contains no sponsor claim. The command reports
`execution_specific_titan_terms_missing`; it never queries Titan or a chain.
Exit status zero means a report was produced, not that funding was verified.
Malformed inputs and arithmetic overflow exit unsuccessfully.

Each plan binds chain, exact bundle digest, execution code digest, parent block
number/hash and the immediately following target block. Changing any plan field
changes its policy-domain-separated SHA-256. The report includes the full plan,
the supplied claim and review context. Its input digest also binds time,
revocation and the artifact locator. Digests use compact serde JSON and the
ordered tuple `[policy_id, value]`; they identify normalized typed inputs, not
the original JSON whitespace. There is no persisted claim cache or approval.

The caller must supply a fresh parent and review time for every assessment.
A changed parent or chain, stale target, expired/future/revoked claim, different
plan, wrong sponsor or general statement blocks consistency. Simulated and
Shadow claims cannot pass the external-observation check. All context is
caller-supplied; matching parent metadata does not authenticate canonical state.

## Cost and liability boundaries

Amounts are canonical decimal strings holding uint256 native gas-asset wei.
The cost bound is checked integer arithmetic:

`gas_limit * max_fee_per_gas_wei + additional_network_fee_cap_wei`

The caller must explicitly bound additional network fees, including applicable
L1/blob charges. The module does not calculate those chain-specific charges or
verify the completeness of the supplied bound. Direct builder payments, flash
fees, swaps and operating costs require their own evidence; this is not a net
profit calculation. Sponsor designation never makes the network cost zero.

Declared caps for included success and included failure must each cover the
complete bound. A not-included network-gas term must be explicit (zero is
permitted because an unincluded bundle consumes no on-chain gas). Missing/null
caps remain unknown. Off-chain rejection fees and other commercial obligations
are not inferred from this network-gas term.

Any operator native-gas prefunding or fallback blocks the report. Explicit
principal, collateral, guarantee and recourse flags apply to **any asset**, not
only native currency. These fields are required; omission never means false.
Unknown authorization fields and legacy budget inputs are rejected. The module
does not infer financing of principal from gas sponsorship or arrange a flash
loan.

## Consistency is not coverage

`declared_terms_consistent=true` means only that supplied fields satisfy the
structural checks. Even fully consistent external-labelled test data retain:

- `input_state_authenticated=false`
- `sponsorship_authenticated=false`
- `execution_gas_coverage_verified=false`
- `activation_allowed=false`
- `spending_authorized=false`

The artifact hash is a locator, not a downloaded document, verified signature,
Titan API response, available balance or settlement receipt. An authenticated
sponsor integration, verified explicit execution authorization and a separately
reviewed operational bridge remain blockers on every report. This command does
not import receipts, credit P&L, replenish a wallet or advance a mine's phase.

The lifecycle and observer remain unchanged. No network-gas commitment or paid
execution is established by the synthetic tests or fixture.
