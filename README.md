# NEXUS Quant Capital

NQC-only source isolation from `josuechavando350-png/nexus-engine` at immutable
commit `e259739c9f75fedcd1061d2f78d6b8852e7a3060`.

This snapshot contains Census, recovered Protocol/Fork source, measured
reimplementations, and NQC evidence tools. It contains no client application,
Vercel configuration, deployment hook, or active GitHub Actions workflow.
All 106 historical NQC workflow definitions are retained as inert `.disabled`
files under `ci/migration/legacy-workflows/` for audit and regression testing.

This is a source migration, not a new certification. Historical PASS results,
commit IDs, source repository IDs, run IDs and artifact IDs retain their original
meaning. They do not certify this repository, its new commit or current markets.

Read `migration/IMPORT-PLAN.md` before importing or enabling any workflow.
`migration/source-manifest.json` maps every source byte and all six path-only
test adaptations. Run `python3 migration/verify_isolation.py` for local package
consistency. Add `--source-git /path/to/original-object-store` to independently
verify those bytes against the original Git objects.

Offline Census tests:

```
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s ci/nqc-census -p 'test*.py'
(cd nqc-census && cargo test --workspace --all-targets --locked --offline)
```

The exact Rust toolchain is pinned in `nqc-census/rust-toolchain.toml`.
Full Python discovery includes seven documented historical/input-harness errors
also present in the original source snapshot; see `migration/VALIDATION.md`.
Recovered PFT code is immutable and requires its documented compatibility
overlays in a separate build directory. The historical PFT materializer requires
original Git ancestry; do not bypass that check or run it as though this new
snapshot inherited certification.
