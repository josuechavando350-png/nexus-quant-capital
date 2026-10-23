# Original debt/deficit bookkeeping evidence

Source: `3b6e088970c02223dfe9f6f2260ff03f018c65c6`.
Publication base: `01d72c3c1f183b2feb6c88caeca1b06a37381a03`.

- `compiler/`: pinned-solc input/output and stderr, unchanged original imports.
- `targeted-initial-compile-failure.txt`: retained ABI macro compatibility failure.
- `targeted-six-tests.txt`: first passing targeted suite after fixing test encoding.
- `targeted-final.txt`: seven tests, including expanded casts and full event checks.
- `python-targeted.txt`: four provenance, CLI, external-outcome and composition checks.
- `offline/`: full clean-source offline suite, exact input manifest and log hashes.
- `source-history.bundle`: recoverable executable source requiring the publication base.
- `verification.json`: final counts, evidence hashes and scope boundaries.

The harness invokes original `_burnDebtTokens` and ReserveLogic bookkeeping.
Its token/strategy responses are supplied, and its storage is synthetic. Rate
input probes intentionally revert. This is not full liquidation, token or
strategy authentication, historical execution or economic certification.
