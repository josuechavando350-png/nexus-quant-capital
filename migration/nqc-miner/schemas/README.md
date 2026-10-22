# Structural contracts

These Draft 2020-12 JSON Schemas describe the immutable journal owner, the four journal record variants, and the completed Parquet export manifest. Owner v1 is retained for historical verification; owner v2 requires an exact `build_identity_sha256` and is the format for new runs. Namespace/producer and evidence classes are explicit where those fields exist. `journal-envelope.schema.json` binds to the owner by hash; an envelope does not carry a second editable namespace field.

Schema validation does not validate SHA-256 tuples, canonical ABI encodings, provider agreement, event/chunk reconciliation, scope order, chain finality, or source authenticity. Run the actual Rust `nqc-miner verify-journal` against the exact immutable owner/configuration/journal bytes. The exporter does this automatically on a private copy and records the verifier build/hash.

JSON number maximums retain the exact decimal `u64::MAX`; consumers must parse them without a float roundtrip. Rust and Python integer parsing preserve this precision. `log_index` is a `u32`. Token base units remain decimal strings in the decoded payload.

`parquet-export.schema.json` validates an export completion marker. It does not infer scope completion from an empty or incomplete source journal. The marker's `complete` field and the journal's `scope_completed` record have different meanings. Cross-field count, order, hash and raw-byte consistency require the exporter/consumer checks in addition to JSON Schema.
