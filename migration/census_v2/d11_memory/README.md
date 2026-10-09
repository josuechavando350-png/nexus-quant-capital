# D11 bounded historical replay overlay

The immutable imported source is unchanged. `prepare.py` checks the base Git
tree, exports it to a new directory outside the repository, checks every
preimage, applies the pinned patch, then checks all postimages.

The memory portion preserves the validators and serializers:

- Regenerated JSONL is compared byte by byte against the observed bundle, using
  the original serializer, order, newline, manifest and digest rules. It avoids
  retaining a second 3.76 GB source file. Four adversarial unit tests include a
  frozen original exporter for full bundle parity.
- Settlement validation does not clone all sources when there are no feasible
  results. No settlement validation call would occur in that original loop.
  The feasible case retains the original complete-source validation.
- A new directory verifier first fully validates the capital bundle, retains
  its verified context, drops the large bundle, then reads and independently
  reimports D08/D09. Its closeout construction is shared with the old verifier.
  A test compares exact old/new closeouts and rejects changed downstream and
  upstream bytes and missing files.
- A research export mode writes **no closeout**. The wrapper then runs the full
  verifier twice in separate processes. It installs a final research closeout
  only if both successful outputs are byte-identical. All nine files must also
  match the pinned original core before parity can be reported.

Historical reproduction also needs the correct importer. The imported base
groups token admission by address; original D11 commit `83395dc` groups it by
address **and role**. The real D08 input has 44 repeated addresses and zero
duplicate token/role keys. Using the imported address-only implementation adds
`D08_INCONSISTENT_DUPLICATE_TOKEN_ADMISSION`, changes source IDs and changes
commitments. The memory-only run completed but did **not** reproduce original
D11 bytes; its mismatch and source diff are preserved.

The final replay adapter includes the exact historical `upstream.rs` as a
separate `historical_upstream` module, pinned by SHA-256 and acquisition URL.
Only the research builder and its upstream replay select that module. The
imported original files in the repository remain unchanged. This is explicit
historical semantic restoration, not a claim that the current importer has
identical behavior. The newer module and its duplicate-conflict tests remain
available. The replay test fixture now declares the Aave role that the exact
historical importer requires; real input bytes are unchanged.

Cargo normalized the order of two package entries. The overlay pins that exact
lockfile too; parsed package versions, dependencies and checksums are identical.

Historical commit/tree values supplied to the binary are serialization/replay
parameters. They are **not** the actual producer identity. The outer research
envelope records the exact base, overlay hash, binaries, commands, lock hash and
execution time. Conditional historical authority flags do not certify NQC.

Use a new external `CARGO_TARGET_DIR`, the pinned toolchain, and fresh paths:

```bash
python3 migration/census_v2/d11_memory/prepare.py --repo "$REPO" --out "$BUILD"
cargo test --offline --manifest-path "$BUILD/nqc-census/Cargo.toml" -p nqc-census-capital -j1
cargo build --offline --release --manifest-path "$BUILD/nqc-census/Cargo.toml" \
  -p nqc-census-capital --bin nqc-rmc011-capital-build --bin nqc-rmc011-bounded-replay -j1
python3 migration/census_v2/d11_memory/run_replay.py \
  --binary "$CARGO_TARGET_DIR/release/nqc-rmc011-capital-build" \
  --replay "$AUTHENTICATED_UPSTREAM_REPLAY" --out "$NEW_REPLAY" --staged
python3 migration/census_v2/d11_memory/verify_parity.py \
  --core "$ORIGINAL_D11_CORE_ZIP" --replay "$NEW_REPLAY" --out "$NEW_REPORT"
```

The failed monolithic runs are retained in the evidence failure ledger. A
successful bounded replay resolves reproduction within this memory limit;
it does not resolve the original terminal-capital flag, financing, economics,
source completeness, independent authority, or Census closure.
