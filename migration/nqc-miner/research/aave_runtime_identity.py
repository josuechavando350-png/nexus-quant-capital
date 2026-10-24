#!/usr/bin/env python3
"""Offline byte comparison for the retained Ethereum Aave revision-11 sample.

Only compiler-declared links/immutables and the Solidity library self-address
are substituted. Metadata is NOT removed and arbitrary transformations are
not accepted. This verifies runtime equivalence, not source-text uniqueness,
authenticated Ethereum state, transaction eligibility or a release tag.
"""
import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

MODULE = Path(__file__).resolve().parents[1]
EVIDENCE = MODULE / "evidence/aave-compiled-identity-20261023"
COMPILER_SHA = "b9977d500c17cba6f0032ca939ef98c4decf6363f19f386d05fb02f708115264"
COMPILER_VERSION = "0.8.27+commit.40a35a09"
PREFIX = "lib/aave-v3-origin-private/src/contracts/"
POOL_PATH = PREFIX + "instances/PoolInstance.sol"
POOL_BASE = PREFIX + "protocol/pool/Pool.sol"
FLASH_PATH = "src/contracts/protocol/libraries/logic/FlashLoanLogic.sol"
POOL = "0x728a138a4823392c2efa55e028d434f526fe03cf"
LIBRARIES = {
    "PoolLogic": "0xd70593841c57cbaa04957cc3eace95708e48853b",
    "BorrowLogic": "0x52da0ce88202d1542543598d1e1e27f0d344726a",
    "SupplyLogic": "0x584c7d8c4cb05304fe5ac7fbc97f20a10fb07564",
    "FlashLoanLogic": "0x6d414cd0d5eaf8c43200ac0c325a7e2ad83b8be6",
    "LiquidationLogic": "0x96d5686812e33ab509eccdb38c89d15607b2a413",
}
IMMUTABLES = {
    "ADDRESSES_PROVIDER": "0x2f39d218133afab8f2b819b1066c7e434ad94e9e",
    "RESERVE_INTEREST_RATE_STRATEGY": "0x9ec6f08190dea04a54f8afc53db96134e5e3fdfb",
}
SOURCE_HASHES = [
    "e97a0a8d5355f2e8c54e09ad4a4f56971d9037a7ed0e3577070ec47eb6ea2a58",
    "f55634f6387f8f8bac76ebda4a471b8d39c62856768c0994d4f12db3a3b48cfb",
    "a8ea09855b889e8516cabed58481394099983e973c99b43652234a9f16739210",
]
BLOCKS = (26248075, 26248113, 26248378)


def check(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def read_json(path):
    check(not path.is_symlink(), "symlink input")
    with gzip.open(path, "rb") if path.suffix == ".gz" else path.open("rb") as stream:
        raw = stream.read(16_000_001)
    check(len(raw) <= 16_000_000, "oversize input")
    return json.loads(raw)


def compilation_input(source):
    check(str(source["chainId"]) == "1" and source["address"].lower() == POOL, "source identity")
    check(source["compilation"]["compilerVersion"] == COMPILER_VERSION, "compiler version")
    check(source["compilation"]["fullyQualifiedName"] == POOL_PATH + ":PoolInstance", "compilation target")
    value = copy.deepcopy(source["stdJsonInput"])
    check(value["language"] == "Solidity", "language")
    check(value["sources"] == source["sources"], "source/input disagreement")
    for item in value["sources"].values():
        check(set(item) == {"content"} and isinstance(item["content"], str), "nonliteral source")
    check(value["settings"] == source["compilation"]["compilerSettings"], "settings disagreement")
    # Output selection alone is added. No source, optimizer, EVM or metadata edits.
    value["settings"]["outputSelection"] = {
        "*": {"*": ["evm.deployedBytecode"]},
        POOL_BASE: {"": ["ast"], "Pool": ["evm.deployedBytecode"]},
    }
    return value


def immutable_names(output):
    nodes = output["sources"][POOL_BASE]["ast"]["nodes"]
    pool = [n for n in nodes if n.get("nodeType") == "ContractDefinition" and n["name"] == "Pool"]
    check(len(pool) == 1, "Pool AST identity")
    names = {str(n["id"]): n["name"] for n in pool[0]["nodes"]
             if n.get("nodeType") == "VariableDeclaration" and n.get("mutability") == "immutable"}
    check(set(names.values()) == set(IMMUTABLES) and len(names) == 2, "unexpected immutables")
    return names


def flashloan_input(html):
    """Decode a single JS string literal as data; never execute webpage scripts."""
    check(len(html) <= 5_000_000, "explorer page size")
    check(re.search(r"Compiler Version[\s\S]{0,500}v0\.8\.27\+commit\.40a35a09", html), "explorer compiler version")
    matches = re.findall(r"var editor_contractJsonData = '((?:\\.|[^'\\])*)'", html)
    check(len(matches) == 1, "explorer source literal")
    token, parts, i = matches[0], [], 0
    while i < len(token):
        if token[i] == "\\":
            check(i + 1 < len(token), "unterminated escape")
            following = token[i + 1]
            check(following in '\"\\/bfnrtu\'`', "unsupported JS escape")
            parts.append(token[i:i + 2] if following in '\"\\/bfnrtu' else following)
            i += 2
        else:
            parts.append(token[i])
            i += 1
    value = json.loads(json.loads('"' + "".join(parts) + '"'))
    check(set(value) == {"language", "sources"} and value["language"] == "Solidity", "explorer source shape")
    settings = json.loads(value["sources"].pop("settings.json")["content"])
    check(FLASH_PATH in value["sources"], "FlashLoanLogic source path")
    for item in value["sources"].values():
        check(set(item) == {"content"} and isinstance(item["content"], str), "nonliteral explorer source")
    check(settings["evmVersion"] == "shanghai" and settings["viaIR"] is False
          and settings["optimizer"] == {"enabled": True, "runs": 200}, "library compilation profile")
    settings["outputSelection"] = {"*": {"*": ["evm.deployedBytecode"]}}
    value["settings"] = settings
    return value


def render_runtime(bytecode, address, names, is_library=False):
    """Return bytes and a complete, nonoverlapping deployment substitution list."""
    value = bytecode["object"]
    check(isinstance(value, str) and 0 < len(value) <= 131072 and len(value) % 2 == 0, "bytecode size")
    edits, covered = [], set()

    def replace(start, length, replacement, reason, identity):
        nonlocal value
        check(type(start) is int and type(length) is int and start >= 0 and length > 0
              and start + length <= len(value) // 2, "reference bounds")
        check(re.fullmatch(r"[0-9a-f]+", replacement) and len(replacement) == length * 2, "replacement encoding")
        locations = set(range(start, start + length))
        check(not locations & covered, "overlapping reference")
        covered.update(locations)
        value = value[:start * 2] + replacement + value[(start + length) * 2:]
        edits.append({"offset": start, "length": length, "reason": reason, "identity": identity,
                      "value": "0x" + replacement})

    for path, libraries in bytecode.get("linkReferences", {}).items():
        for name, refs in libraries.items():
            check(name in LIBRARIES and path in {p + "protocol/libraries/logic/" + name + ".sol"
                                               for p in (PREFIX, "src/contracts/")}, "unknown library")
            for ref in refs:
                check(ref["length"] == 20, "link width")
                replace(ref["start"], 20, LIBRARIES[name][2:], "library", path + ":" + name)
    for identity, refs in bytecode.get("immutableReferences", {}).items():
        check(identity in names, "unknown immutable")
        for ref in refs:
            check(ref["length"] == 32 and value[ref["start"] * 2:(ref["start"] + 32) * 2] == "00" * 32,
                  "immutable width or initial value")
            replace(ref["start"], 32, "00" * 12 + IMMUTABLES[names[identity]][2:], "immutable", names[identity])
    if is_library:
        check(value.startswith("73" + "00" * 20 + "3014"), "library self-address guard")
        check(address in LIBRARIES.values(), "library address")
        replace(1, 20, address[2:], "library_self_address", address)
    check(re.fullmatch(r"[0-9a-f]+", value), "unresolved bytecode")
    return bytes.fromhex(value), edits


def audit(source, output, histories, flash_output, flash_input):
    compilation_input(source)
    check(not any(e.get("severity") == "error" for e in output.get("errors", [])), "compiler error")
    check(not any(e.get("severity") == "error" for e in flash_output.get("errors", [])), "library compiler error")
    names = immutable_names(output)
    contracts = {"PoolInstance": (POOL_PATH, POOL), **{
        name: (PREFIX + "protocol/libraries/logic/" + name + ".sol", addr) for name, addr in LIBRARIES.items()}}
    results = []
    check(len(histories) == 3, "missing history")
    check(tuple(h["block"]["number"] for h in histories) == BLOCKS, "historical block coverage")
    for name, (path, address) in contracts.items():
        profile = "pool"
        if name == "FlashLoanLogic":
            profile, path = "flashloan", FLASH_PATH
            bytecode = flash_output["contracts"][path][name]["evm"]["deployedBytecode"]
        else:
            bytecode = output["contracts"][path][name]["evm"]["deployedBytecode"]
        runtime, substitutions = render_runtime(bytecode, address, names, name != "PoolInstance")
        blocks = []
        for observed in histories:
            samples = observed["runtimes"][address]
            check(set(samples) == {"ethereum-primary", "ethereum-secondary"}, "provider coverage")
            for sample in samples.values():
                check(isinstance(sample, str) and re.fullmatch(r"0x(?:[0-9a-f]{2})+", sample), "observed bytecode")
                check(runtime == bytes.fromhex(sample[2:]), "compiled runtime mismatch: " + name)
            blocks.append(observed["block"]["number"])
        if name == "PoolInstance":
            check(runtime == bytes.fromhex(source["runtimeBytecode"]["onchainBytecode"][2:]), "Sourcify historical mismatch")
        results.append({"name": name, "address": address, "source_path": path, "compilation_profile": profile, "bytes": len(runtime),
                        "runtime_sha256": sha(runtime), "blocks": blocks, "substitutions": substitutions,
                        "metadata_bytes_compared": True})
    return {"schema": "nqc-miner-aave-compiled-runtime-v1", "status": "pass", "contracts": results,
            "compiler_sha256": COMPILER_SHA, "compiler_version": COMPILER_VERSION,
            "source_files": {"pool": {p: sha(v["content"].encode()) for p, v in source["sources"].items()},
                             "flashloan": {p: sha(v["content"].encode()) for p, v in flash_input["sources"].items()}},
            "runtime_equivalence_verified": True, "original_source_text_authenticated": False,
            "source_metadata_hash_present": False, "state_authentication_verified": False,
            "release_tag_verified": False, "executable_eligibility_verified": False,
            "economic_certification": False, "activation_allowed": False, "observer_bridge_enabled": False}


def compile_source(compiler, value):
    check(compiler.is_file() and sha(compiler.read_bytes()) == COMPILER_SHA, "compiler checksum")
    # Only in-memory literal sources; no import callback, source checkout or network.
    with tempfile.TemporaryDirectory(prefix="nqc-miner-solc-") as directory:
        completed = subprocess.run([str(compiler.resolve()), "--standard-json", "--no-import-callback"], input=encoded(value),
                                   capture_output=True, cwd=directory, timeout=180, check=True)
    check(len(completed.stdout) <= 16_000_000 and len(completed.stderr) <= 100_000, "compiler output size")
    return completed.stdout, completed.stderr


def verify_provenance(source):
    retrieval = read_json(EVIDENCE / "retrieval.json")
    check(len(retrieval["records"]) == 2, "retrieval coverage")
    expected = {
        "source.json.gz": "https://sourcify.dev/server/v2/contract/1/" + POOL + "?fields=all",
        "compiler-list.json.gz": "https://raw.githubusercontent.com/ethereum/solc-bin/gh-pages/linux-amd64/list.json",
    }
    check({r["file"] for r in retrieval["records"]} == set(expected), "retrieval files")
    for record in retrieval["records"]:
        raw = gzip.decompress((EVIDENCE / record["file"]).read_bytes())
        check(record["source_url"] == expected[record["file"]]
              and sha(raw) == record["raw_sha256"] and len(raw) == record["raw_bytes"], "retrieval integrity")
    index = read_json(EVIDENCE / "compiler-list.json.gz")
    builds = [b for b in index["builds"] if b["longVersion"] == COMPILER_VERSION]
    check(len(builds) == 1 and builds[0]["sha256"] == "0x" + COMPILER_SHA, "official compiler index")
    flash = read_json(EVIDENCE / "flashloan-retrieval.json")
    raw = gzip.decompress((EVIDENCE / "flashloan-etherscan.html.gz").read_bytes())
    check(flash["source_url"] == "https://etherscan.io/address/" + LIBRARIES["FlashLoanLogic"] + "#code"
          and sha(raw) == flash["raw_sha256"] and len(raw) == flash["raw_bytes"], "explorer retrieval integrity")
    excerpts = read_json(EVIDENCE / "rule-excerpts.json")
    check(len(excerpts["entries"]) == 3, "rule coverage")
    for entry in excerpts["entries"]:
        original = source["sources"][entry["source_path"]]["content"]
        check(sha(original.encode()) == entry["source_sha256"], "rule source hash")
        check(Path(entry["excerpt"]).name == entry["excerpt"], "rule excerpt path")
        excerpt = ("\n".join(original.splitlines()[entry["first_line"] - 1:entry["last_line"]]) + "\n").encode()
        check(sha(excerpt) == entry["excerpt_sha256"] and (EVIDENCE / entry["excerpt"]).read_bytes() == excerpt, "rule excerpt content")
    return {"retrieval_sha256": sha((EVIDENCE / "retrieval.json").read_bytes()),
            "flashloan_retrieval_sha256": sha((EVIDENCE / "flashloan-retrieval.json").read_bytes()),
            "rule_excerpts_sha256": sha((EVIDENCE / "rule-excerpts.json").read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    source = read_json(EVIDENCE / "source.json.gz")
    provenance = verify_provenance(source)
    value = compilation_input(source)
    stdout, stderr = compile_source(args.compiler, value)
    (args.output / "compiler-input.json.gz").write_bytes(gzip.compress(encoded(value), mtime=0))
    (args.output / "compiler-output.json.gz").write_bytes(gzip.compress(stdout, mtime=0))
    (args.output / "compiler.stderr").write_bytes(stderr)
    flash_input = flashloan_input(gzip.decompress((EVIDENCE / "flashloan-etherscan.html.gz").read_bytes()).decode())
    flash_stdout, flash_stderr = compile_source(args.compiler, flash_input)
    (args.output / "flashloan-compiler-input.json.gz").write_bytes(gzip.compress(encoded(flash_input), mtime=0))
    (args.output / "flashloan-compiler-output.json.gz").write_bytes(gzip.compress(flash_stdout, mtime=0))
    (args.output / "flashloan-compiler.stderr").write_bytes(flash_stderr)
    # Replay network records and historical binding independently before comparison.
    import importlib.util
    spec = importlib.util.spec_from_file_location("aave_library_capture", EVIDENCE / "capture.py")
    capture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(capture)
    histories = capture.replay()
    report = audit(source, json.loads(stdout), histories, json.loads(flash_stdout), flash_input)
    report.update(**provenance, compiler_input_sha256=sha(encoded(value)), compiler_output_sha256=sha(stdout),
                  auditor_sha256=sha(Path(__file__).read_bytes()), source_response_sha256=sha(gzip.decompress((EVIDENCE / "source.json.gz").read_bytes())),
                  flashloan_compiler_input_sha256=sha(encoded(flash_input)), flashloan_compiler_output_sha256=sha(flash_stdout),
                  compiler_arguments=["--standard-json", "--no-import-callback"],
                  local_compilation_executed=True, network_used=False)
    (args.output / "audit.json").write_bytes(encoded(report))
    print(json.dumps({"status": report["status"], "contracts": len(report["contracts"]), "historical_comparisons": 36}))


if __name__ == "__main__":
    main()
