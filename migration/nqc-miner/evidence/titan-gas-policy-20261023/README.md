# Same-source verification: Titan-only gas policy

Source commit: `ebdee791fdc80a49aa699373dd2c1dad792073d4`.

`verification.json` binds 249 passing Rust tests and the final 340 passing Python
tests to unchanged inputs, along with build, Clippy, formatting, identity and
isolation checks. The 21 new tests are included in that total.

`initial-full/` is the original failed complete attempt: seven checks passed;
Python could not read historical Git objects missing from the shallow clone.
Its failed summary and original logs are retained unchanged.
`interrupted-python/` retains a later run interrupted by an environment restart;
it has no successful completion. `python-final/` is the complete successful
Python rerun after historical objects were restored. Those five exact commits
are listed in its summary. No source inputs changed between these attempts.

Targeted logs are preparatory checks, not additional distinct tests. The initial
test-compilation type error is preserved. `continuity.json` records the unchanged
historical accounting body and absence of prior-evidence/observer changes.
`synthetic/` contains one actual CLI invocation over explicitly artificial input;
it reports missing sponsor terms, not a financed execution.

No actual sponsorship, source authentication, economic result or phase exit is
established. Global progress stays 43/100. See the audit in `../../docs/`.
