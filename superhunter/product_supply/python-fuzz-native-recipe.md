# Native Python fuzzing: Atheris, catalog 114

This adapter executes the official `atheris==3.1.0` CPython 3.12 Linux x86-64
wheel. The loaded implementation is Atheris's native extension and its built-in
libFuzzer. It operates on the fixed owned two-byte debit parser recorded in
`python-fuzz-native-owned.json`.

The catalog identity is `google/atheris` at
`e36da74cf42b5834c4e31d7cabb58d796695d29f`. **The release wheel has not been
rebuilt from that commit, and binary equivalence to that commit is not claimed.**
The installed Python/native module hashes refer to the release wheel. They are
not represented as catalog Git blob proofs.

## Acquisition and pins

The reviewed release artifact is:

- Filename: `atheris-3.1.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl`
- Size: 36,875,908 bytes.
- SHA-256: `ec5e11f21a4c197fe91f7aea2b2de88e623c73a21fc07b105ac6329a1588457b`.
- Release metadata: <https://pypi.org/pypi/atheris/3.1.0/json>.
- Exact artifact URL: recorded in `python-fuzz-native-sources.json`.

On the supported Python/platform combination, obtain the wheel before the
offline run:

```sh
python -m pip download --only-binary=:all: --no-deps --require-hashes \
  --dest /tmp/atheris-kit \
  -r superhunter/product_supply/python-fuzz-native-linux-py312.txt
```

No source distribution, dependency resolution, source patch, global installation
or live target is used by the adapter. A fresh private installation uses the
pinned wheel with pip's `--no-index --no-deps --require-hashes` options in a
disconnected network namespace. The adapter verifies all 31 shipped Python and
native code members, release metadata, wheel metadata and the Apache-2.0 notice
against the pinned archive. The presence of 31 files is an inventory check; it
does not credit 31 independent capabilities.

Linux user/network namespaces and CPython 3.12 are required. If namespace
creation fails, the adapter fails; it does not retry with network access.

## Execute and preserve the native receipt

From the product checkout:

```python
from superhunter.product_python_fuzz_native import run
from superhunter.safe_io import canonical

report = run('/tmp/atheris-kit', evidence_dir='/tmp/atheris-evidence-1')
print(canonical(report).decode(), end='')
```

The output directory must be new. It contains the raw seven-control native
receipt, the actual fresh failing corpus, the previously observed pinned corpus,
the canonical report and the artifact completion manifest. Running again with
a new output directory creates another private wheel installation and another
pair of real native campaigns.

Both campaigns use seed `20261121`, at most 512 executions, at most two input
bytes, a three-second per-input timeout and libFuzzer's 512 MB RSS limit. Each
worker additionally has a 15-second CPU limit, a 35-second parent deadline,
bounded output files, no core dumps, and no network interfaces or Python socket
access. Only the fixed owned fixture is accepted. The clean replay allows three
bytes to exercise the parser's invalid-length branch without libFuzzer
truncating that control to two bytes.

## What the seven controls establish

1. A native campaign begins from the valid seed `1001`. The original parser
   incorrectly wraps an overdraft into an unsigned byte. libFuzzer must generate
   a failing input outside that seed, produce a real corpus file, execute the
   instrumented callback and report the specific owned invariant exception.
2. The fresh corpus is independently checked using ordinary integer arithmetic
   and replayed through native Atheris on the original parser. The failure must
   reproduce.
3. The same fresh corpus is replayed on the repaired parser. It must be rejected
   as an overdraft without an invariant violation.
4. The historical observed corpus `a8ac` is replayed on the original parser.
   Balance 168 minus amount 172 must reveal the erroneous wrapped result 252.
5. The historical corpus is replayed on the repaired parser, which must return
   rejection rather than a wrapped balance.
6. Seven clean controls exercise accepted debits, boundary values and lengths
   zero, one and three. Every recorded callback result is independently checked.
7. A fresh campaign on the repaired parser must complete 512 native callbacks,
   exercise mutated inputs and invalid lengths, and finish without an invariant
   violation.

The verifier requires actual callbacks, the pinned native module identities,
coverage/execution statistics, exact replay input membership, the generated
corpus, the expected exit codes and the arithmetic witness. A version string,
process failure alone, absent callback data, a missing replay, or a shortened
repaired campaign cannot earn participation credit.

## Recorded reproduction

Two fresh installations and runs completed all seven controls. In both recorded
runs, the original campaign found `a8ac` after seven callbacks; each failing
replay executed one callback and returned 77; each repaired replay returned 0;
the seven clean inputs passed; and the repaired campaign completed 512
callbacks. The actual two-byte corpus is preserved as
`discovered-counterexample.bin` in each runtime receipt directory, SHA-256
`aa5751c50bf076fe0c95757e2cc9237e0d395b7f6ede1fe6fa3cab63db93761d`.

The canonical reports were byte-identical:

`50f7cdcb8c76d5b5c02382b0d74594f8ce5e27cfdf66726862993f530b6d7426`.

The source-controlled owned-input record and native sample preserve its exact
hexadecimal bytes as `a8ac`; no binary payload is added to the source repository.

`python-fuzz-native-reproduction.json` records the two raw-receipt hashes,
callback counts and exit codes. `python-fuzz-native-sample.json` preserves the
first native receipt for verifier regression tests. The raw receipts have
different hashes, as expected for temporary paths, process identifiers and
runtime statistics. The canonical result deliberately excludes fresh mutated
bytes, intermediate input sequences, time-to-failure, coverage counts, timing,
memory and process identifiers. Every fresh witness is still independently
checked and replayed on both implementations before a canonical result can be
produced. This is reproducibility of validated outcomes, not a claim that the
fuzzer's complete execution trace is deterministic.

Run the 14 focused verifier tests with:

```sh
python -m unittest superhunter.tests.test_product_python_fuzz_native -v
```

## Practical limits

This contributes one executable native Python fuzzing and replay capability to
the product. It demonstrates the complete discovery-to-repair control on one
deliberately defective owned fixture. It does not establish exhaustive coverage,
native-extension sanitizer coverage, equivalence to the catalog source build,
general detection rates, or a newly discovered vulnerability in a third-party
application. Original vulnerabilities confirmed by this integration: **0**.
