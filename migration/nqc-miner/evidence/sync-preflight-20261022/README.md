# Sync client preflight evidence

189 Python tests pass, including 29 new protocol, pipeline and runner regressions.
The real Rust verifier and Polars are used for source capture/preparation; the
client/database boundary is explicitly modelled offline. No new PostgreSQL
execution is claimed. The generated 17-check native test remains pending.

`verification.json` binds all source/input/evidence hashes. `environment.json`
records the socket restriction and test boundary. Earlier native collection
runtime evidence remains unchanged and does not certify this new client.
Global progress remains 43/100, with no additional operational credit.
