#!/usr/bin/env python3
"""Compile a synthetic caller of the unchanged runtime-matched Aave function."""
import argparse
import gzip
import json
from pathlib import Path
import aave_runtime_identity as identity

NAME = "fixtures/AaveValidationHarness.sol"
SIGNATURE = "check((address,address,uint256,uint256,uint40,uint40,uint16,uint256,uint256,uint256))"


def build(compiler, output):
    source = identity.read_json(identity.EVIDENCE / "source.json.gz")
    identity.verify_provenance(source)
    original = identity.compilation_input(source)
    harness = (identity.MODULE / NAME).read_text()
    original["sources"][NAME] = {"content": harness}
    original["settings"]["outputSelection"] = {NAME: {"AaveValidationHarness": [
        "evm.deployedBytecode", "evm.methodIdentifiers", "storageLayout"]}}
    raw, stderr = identity.compile_source(compiler, original)
    result = json.loads(raw)
    identity.check(not any(e.get("severity") == "error" for e in result.get("errors", [])), "harness compile error")
    contract = result["contracts"][NAME]["AaveValidationHarness"]
    code = contract["evm"]["deployedBytecode"]
    identity.check(not code["linkReferences"] and not code["immutableReferences"], "unexpected deployment references")
    runtime = bytes.fromhex(code["object"])
    fixture = {"schema": "nqc-miner-aave-validation-harness-v1", "kind": "synthetic_fixture",
               "compiler_sha256": identity.COMPILER_SHA, "compiler_version": identity.COMPILER_VERSION,
               "compiler_input_sha256": identity.sha(identity.encoded(original)),
               "compiler_output_sha256": identity.sha(raw), "harness_source_sha256": identity.sha(harness.encode()),
               "runtime_sha256": identity.sha(runtime), "runtime_code": "0x" + runtime.hex(),
               "selector": "0x" + contract["evm"]["methodIdentifiers"][SIGNATURE],
               "storage_layout": contract["storageLayout"], "original_sources": {
                   path: identity.sha(value["content"].encode()) for path, value in source["sources"].items()},
               "reference_runtime_audit": "evidence/aave-compiled-identity-20261023/local/audit.json",
               "executable_eligibility_verified": False, "activation_allowed": False}
    output.mkdir(parents=True, exist_ok=False)
    (output / "input.json.gz").write_bytes(gzip.compress(identity.encoded(original), mtime=0))
    (output / "output.json.gz").write_bytes(gzip.compress(raw, mtime=0))
    (output / "compiler.stderr").write_bytes(stderr)
    (identity.MODULE / "fixtures/aave_validation_harness.json").write_bytes(identity.encoded(fixture))
    print(json.dumps({"runtime_bytes": len(runtime), "selector": fixture["selector"], "runtime_sha256": fixture["runtime_sha256"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.compiler, args.output)
