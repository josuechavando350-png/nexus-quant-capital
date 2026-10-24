# Aave dependency runtime evidence, 2026-10-23

Source commit: `421f7f236d5523dd8f279e4759b71336e6c34557`.
Bundle prerequisite: `550963b88ca120adc19dcdeef2fbfe2fc9093340`.

`public/` retains 132 requests and responses at the three original block hashes.
Each provider reads four token proxy slots, four proxy runtimes, four
implementation runtimes and the shared strategy runtime, with chain/finality
and repeated header checks. The first attempt timed out before a complete
observation; `public-initial/failure.json` and `execution-notes.json` retain the
failure and preflight corrections. Responses from different attempts were not
combined.

`sources/` retains three complete Sourcify responses and retrieval hashes/URLs.
`profiles.json` pins source, settings, compiler and compiler-output identities.
`compiler/` retains literal unchanged-source inputs, independent outputs/ASTs
and stderr. A second fresh compilation reproduced all retained bytes exactly.
The official compiler index is reused from
`../aave-compiled-identity-20261023/compiler-list.json.gz`.

`audit.json` records three implementation artifacts, thirty byte comparisons,
all compiler-declared immutable substitutions and the explicit limits.
`targeted.txt` contains the twelve new tests. `offline/` contains the complete
project verification, input manifest, binary source identity and isolation.
`verification.json` binds these files, final documentation and the source bundle.

The eight proxy addresses correspond to twelve observations across the original
three blocks; they are not twelve different implementations. Both token types
share a single implementation each. The rate strategy is a third implementation.
No new historical event, token execution, authenticated state, certified proxy
dispatch or executable liquidation is claimed. Observer and activation remain
unchanged. This evidence grants no progress points or operational authority.
