# Collateral exhaustion and final fee evidence

Source: `83d4d4d70eb3d3fddc0236f153e9232c0aab6dab`.
Publication base: `389ac273d2a29807170d2f884e413eeb20d60fbb`.

- `compiler/`: checksum-pinned solc input/output and stderr.
- `targeted-initial.txt`: five targeted Rust tests and 1089-case main comparison.
- `python-targeted.txt`: four targeted provenance, CLI and composition tests.
- `offline/`: full clean-source offline verification and all input/log hashes.
- `source-history.bundle`: executable source history, requiring the publication base.
- `verification.json`: delivery hashes and result.

The reference executes byte-exact non-contiguous original excerpts and imports
unchanged helpers. Its token and post-liquidator balance are synthetic. Actual
intervening debt/token operations, their error ordering, historical state and
economic outcomes are not certified. See `../../docs/aave-collateral.md` and
`../../docs/AUDIT_AAVE_COLLATERAL_20261023.md` for the precise boundary.
