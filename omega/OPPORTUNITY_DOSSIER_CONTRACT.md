# Omega Opportunity Dossier — Census contract

Status: offline evidence schema only. This contract does **not** certify Evidence Vault,
market completeness, P&L, signing, broadcasting, spending, or phase advancement.

Each dossier binds one position and market to one exact state anchor. Its identity is
SHA-256 over the canonical `state_anchor`, `protocol`, and `position` objects. The
full dossier has a second SHA-256 commitment over every field except the commitment
itself.

Census dossiers may record only `NO-GO` or `OBSERVAR`. `GO`, NQC execution, realized
NQC P&L, spending authority, signing authority, broadcasting authority, Census
closeout, and phase advancement are rejected by the validator.

The economics object always contains all 14 cost categories used by the Census
economics crate. Unknown costs are explicit `null`; they are never silently treated
as zero. A complete vector requires a value and evidence commitment for every cost.

Competition evidence is all-or-none at this layer: winner, oracle-update block,
winner block, builder-payment share, and evidence digest. Incomplete competition
fields must remain `null`.

`store_dossier` publishes a canonical JSON record using an atomic, no-clobber,
content-addressed filename. `query_dossiers` validates every record before returning
metadata and fails closed on unknown or malformed vault entries.

This is an Omega-specific dossier/query layer above the existing durable Census
store. It is not yet wired into the Rust store, replicated durability, reorg
reconciliation, or current live acquisition; component 29 remains partial.
