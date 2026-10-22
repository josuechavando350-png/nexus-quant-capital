# PostgreSQL contract check on Termux

Status: **prepared for user execution; runtime result pending**. Overall progress
remains **40/100**. The user-provided screenshot from 2026-10-22 shows PostgreSQL
18.6 initializing, starting, answering a local query against `nqc_miner_v1`, and
stopping successfully on native aarch64 Termux. It is a bootstrap observation,
not execution of the repository DDL or an audited importer integration.

The self-contained delivery is `scripts/nqc-miner-postgres-check.sh`. Run with
`bash /absolute/path/to/nqc-miner-postgres-check.sh` as the ordinary Termux user.
It needs only the PostgreSQL 18 package and standard shell utilities. It has no
downloads, remote connections, credentials, production data or spending paths.
It creates a **new random private directory** below the user's Termux home,
initializes a fresh cluster, disables TCP, uses peer authentication on a private
Unix socket, and creates a database and test roles solely inside that new cluster.
It does not reuse `~/nqc-miner-pg`, any existing database, or any Observer state.
All Termux sessions still share an OS user and installed packages; this is data
and process separation, not a security boundary against a hostile same-UID process.

The runner embeds the exact bytes of `infra/postgres.sql`, verifies their SHA-256
before applying them, and applies them under a dedicated non-superuser owner.
The generator and template remain in `scripts/`; regenerate with:

```bash
python3 scripts/build_termux_postgres_check.py
bash -n scripts/nqc-miner-postgres-check.sh
```

The 30 SQL checks cover the six tables' ownership, no PUBLIC access, local-only
connections, durable commit settings, fixed safety flags, evidence classes,
binary bytes, duplicate rejection, foreign keys, resource bounds, outbox routing,
atomic rollback after a failed outbox insertion, explicit rollback, inaccessible
live states and a limited writer's privileges. Additional runner checks reject
the wrong database and an existing schema, execute three denied writer mutations,
and compare the committed synthetic rows after an orderly server restart.

The fixture hashes and byte arrays are deliberately artificial and are not valid
Rust-verified journals. Success would validate these DDL/transaction behaviors
only: no importer, idempotent retry policy, quarantine service, concurrent relay,
crash/power-loss certification, external service or economic phase exit is tested.

The script shuts down **only its own newly created cluster**, including on failure,
and retains logs, input SQL, settings, snapshots, a SHA-256 manifest, and
`nqc-miner-postgres-evidence.tar.gz` in that directory. It does not erase failed
evidence or automatically upload anything. The database files stay on the phone
for inspection; the result archive contains the compact evidence directory only.
`result.json` records a failure unless all steps and final shutdown succeed.
An interrupted or incomplete archive must not be treated as a pass.

Review the returned archive, verify its hashes and source inputs, inspect expected
SQLSTATEs and the 30 individual labels, and compare restart snapshots before
crediting any result. Merely providing the script or seeing a success screenshot
does not close the integration gate.

References reviewed: PostgreSQL 18 documentation for `initdb`, `pg_ctl`, `psql`,
peer authentication, connection settings, privileges and PL/pgSQL exception blocks.
