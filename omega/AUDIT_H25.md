# H25 — offline Morpho probe; historical execution pending

Base producer: `96583258fefe9c1a3f5595dbc3f35b58814162bd`.
Separate branch: `feat/omega-h25-morpho-liquidation-20261024`.
This is a research checkpoint, not an upgrade of admitted H24 runtime v7.

## Result

- New same-asset WETH Morpho/Aave probe with 36 passing offline Solidity tests,
  zero failed/skipped, including 256 seeded fuzz cases.
- New immutable partial-capture verifier and safe offline build preparation;
  26 passing Python tests, zero failed/skipped.
- Abstract historical harness compiles with Solidity 0.8.24. It has no concrete
  reviewed implementation pins and no runnable historical test.
- 15 successful read-only RPC captures retained; seven categories agree exactly
  across two providers. A second WETH-code response and both implementation/
  preceding-transaction captures remain missing.
- Historical H25 fork executions: **zero**. Original-receipt replay: **unrun**.
  New route gas measurement, Titan execution coverage and full net profit:
  **unproven**. Product certification remains **0/36**.

The acquisition stopped with the tool-reported error:
`Network access to "https://eth-mainnet.public.blastapi.io:443" was blocked by policy.`
No alternate RPC route or remote CI execution was used after that block.

## Validation and preserved failures

The initial synthetic Solidity run had 35 passes and one failure: a negative
test attempted to read a mock pool getter after replacing its code. The test
snapshot was corrected; both subsequent complete unit runs passed all 36.
The first compile including the historical scaffold rejected two address
literal checksum spellings. Correcting capitalization preserved address bytes;
the fresh final build compiled all three Solidity files and passed all 36 tests.
Initial logs remain in the evidence package; they are not called successes.

Toolchain pins, also retained in the evidence package:

| Item | SHA-256 |
|---|---|
| Forge 1.7.1 archive | `cf7e688ed0c4c48adffca788b496076e31060b67ac5afe1e43dbb5499c20c88b` |
| Forge executable | `4f77da0810de94325734855d0ad58d70640aa8a5b2a837608ddf8c26da34355c` |
| Solidity 0.8.24 | `fb03a29a517452b9f12bcf459ef37d0a543765bb3bbc911e70a87d6a37c30d5f` |

Final affected-suite results: **103 Python tests passed** (26 H25, 34 integration
with both original archives supplied, 43 Actions/isolation-boundary tests),
zero failed or skipped. Isolation passed with 185 explicit Omega files, 531
original source files and 106 disabled legacy workflows. The unchanged active
workflow SHA-256 is
`8c1c20a8684a21728d7ebd83d0aac7ad93dc5840df34ec455e80e5eb0b3813be`.
Original Git object comparison was not requested (`original_objects_checked=false`);
the frozen original verifier's source-manifest checks passed.

| Validation artifact | SHA-256 |
|---|---|
| H25 Python report | `a772bcc2370c7cb8fd47bb0c9c3d98ab67baa325b0544bab740df9664952765d` |
| Integration Python report | `6b03479adac20760fbb7ad4023fe3418e8d6c76a8d44d075addbcdd68fc08baa` |
| Actions Python report | `e06e5a4e1c6fad7ce7eb47ae392edb9578026be035a7528e14078875b6bef64e` |
| Final Solidity log | `bb7b1c0e7375253ab599e19c75f052f8e84befe868c89595324a026c97684dff` |
| Isolation report | `167dd4de386771e8aabc09e9682d07c8a4af795c994c592814d7674e73678ff5` |

Reports and source hashes are retained in the evidence package.
Rust sources are unchanged; Rust suites and the full
H24 688-test suite are not rerun or credited to H25. H25 does not inherit H24's
remote CI certification. The active workflow and its producer remain unchanged.

See `MORPHO_EXPERIMENT_CONTRACT.md` for exact anchors, validation boundaries,
reproduction and remaining admission requirements. Titan remains mandatory;
operator gas allocation and own-gas fallback remain zero/disabled.
