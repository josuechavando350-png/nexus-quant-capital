"""Offline subprocess boundary for complete, immutable NQC037 verification.

Reads a bounded JSON prefix from stdin. No RPC, journal writes, credential
arguments or automatic acquisition. Every invocation rebuilds state from zero.
Run with Python -I to exclude caller PYTHONPATH and user site packages.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import sys

BASE_COMMIT = "a6e4600962dca78ddb4e02cc12c920a3df96d169"
MANIFEST_BLOB = "43e5d0a800a97015970def154b829aec3897dccf"
BRIDGE_BLOB = "93dade5bc13a892b9cb84ab69caee207b8075350"
INTAKE_BLOB = "c36d60ce83e73d246496bd0b72bc6cbe00d5893e"
ENGINE_PINS = {
    "nqc-047-remote-ledger/ledger_engine.js": "fcd3cc0d7c5a71a8e4ef12f621fd6c5b0b28b3ee",
    "nqc-048-durable-chunked-receipts/chunked_ledger.js": "a317e3f1b69927dcf25dec4d418091701d699f41",
}
MAX_RESPONSE = 16 * 1024 * 1024
MAX_INPUT = 8 * MAX_RESPONSE + 1024


class Blocked(ValueError):
    pass


def require(condition):
    if not condition:
        raise Blocked("LOCAL_CHECK_FAILED")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def read_file(root, relative, limit=MAX_RESPONSE):
    relative = Path(relative)
    require(not relative.is_absolute() and ".." not in relative.parts)
    path = root
    for part in relative.parts:
        path = path / part
        require(not path.is_symlink())
    require(path.is_file())
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit)
    return raw


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def invalid_constant(_):
    raise Blocked("NON_JSON_CONSTANT")


def decode(raw):
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                      parse_constant=invalid_constant)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode()


def load_original(repo_root):
    experiments = Path(repo_root).resolve() / "migration/experiments"
    root = experiments / "nqc-037-historical-state"
    raw = read_file(root, "MANIFEST.json")
    require(blob(raw) == MANIFEST_BLOB)
    manifest = decode(raw)
    require(len(manifest["files"]) == 42)
    for item in manifest["files"]:
        raw = read_file(root, item["path"])
        require(len(raw) == item["bytes"] and sha(raw) == item["sha256"])
    for relative, expected in ENGINE_PINS.items():
        require(blob(read_file(experiments, relative)) == expected)
    bridge_path = experiments / "nqc-049-offline-nqc037-replay/offline_bridge.py"
    require(blob(read_file(experiments, str(bridge_path.relative_to(experiments)))) == BRIDGE_BLOB)
    spec = importlib.util.spec_from_file_location("nqc049_pinned", bridge_path)
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    bridge.source_bindings(experiments)
    plan = bridge.check_plan(decode(read_file(experiments, "nqc-038-archive-access/TRIPORT_PLAN.json")))
    versions = {}
    for requirement in (root / "requirements.txt").read_text().splitlines():
        name, expected = requirement.split("==")
        actual = importlib.metadata.version(name)
        require(actual == expected)
        versions[name] = actual
    # Prevent an imported substitute from winning Python's module cache.
    for name in ("intake", "verify", "storage_proof", "util"):
        require(name not in sys.modules)
    sys.path.insert(0, str(root / "src"))
    intake = importlib.import_module("intake")
    origins = {"intake": "src/intake.py", "verify": "src/verify.py",
               "storage_proof": "vendor/nqc031/storage_proof.py", "util": "vendor/nqc031/util.py"}
    for name, relative in origins.items():
        require(Path(sys.modules[name].__file__).resolve() == (root / relative).resolve())
    require(intake.plan() == plan)
    import rlp
    from Crypto.Hash import keccak
    # Published Keccak vectors, not NIST SHA3 and not the NQC050 overlay.
    require(keccak.new(digest_bits=256, data=b"").hexdigest() ==
            "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
    require(keccak.new(digest_bits=256, data=b"abc").hexdigest() ==
            "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45")
    require("nqc-050" not in rlp.__file__ and "nqc-050" not in keccak.__file__)
    return intake, plan, {"manifest_files_verified": 42, "intake_git_blob": INTAKE_BLOB,
                          "complete_original_modules_loaded": True,
                          "dependency_versions": versions}


def reject_network(event, args):
    if event.startswith("socket.") or event.startswith("urllib."):
        raise Blocked("OFFLINE_BOUNDARY")


def reject_process(event, args):
    if event in ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"):
        raise Blocked("OFFLINE_BOUNDARY")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    sys.addaudithook(reject_network)
    result = {"status": "BLOCKED_SOURCE_OR_DEPENDENCY", "responses_validated": 0,
              "commercial_admission": False, "live_enabled": False,
              "triport_requests_sent": 0, "historical_state_proofs_acquired": 0}
    try:
        intake, plan, evidence = load_original(args.repo_root)
        # Native PyCryptodome initialization uses platform.architecture()/file.
        # Network is already blocked; child processes are blocked for validation.
        sys.addaudithook(reject_process)
        result.update(evidence)
        if args.check:
            result["status"] = "ORIGINAL_RUNTIME_VERIFIED"
        else:
            raw = sys.stdin.buffer.read(MAX_INPUT + 1)
            require(len(raw) <= MAX_INPUT)
            result["input_sha256"] = sha(raw)
            data = decode(raw)
            require(isinstance(data, dict) and set(data) == {"responses"})
            responses = data["responses"]
            require(isinstance(responses, list) and 1 <= len(responses) <= 8)
            state = {}
            result["status"] = "BLOCKED_NQC037_VALIDATION"
            for index, response in enumerate(responses):
                require(len(canonical(response)) <= MAX_RESPONSE)
                result["failed_purpose"] = plan[index]["purpose"]
                intake.validate_step(plan[index], response, state)
                result["responses_validated"] += 1
            del result["failed_purpose"]
            result["status"] = "OFFLINE_PREFIX_VERIFIED"
            result["gates"] = sys.modules["verify"].closed_gates()
    except Exception:
        # No input, endpoint, provider text, secret, or traceback in the response.
        pass
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in {"ORIGINAL_RUNTIME_VERIFIED", "OFFLINE_PREFIX_VERIFIED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
