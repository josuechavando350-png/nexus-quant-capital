#!/usr/bin/env python3
"""Capture one finite read-only Miner run, including failures and exact byte hashes.

No endpoint values are serialized. The output must be a new directory under an
existing non-symlink parent. This captures evidence; it grants no spending or
observer authority. RPC agreement is not independent chain authentication.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from bind_run_config import BindError, bind, load_json_strict, validate_about, write_new_atomic


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def safe_path(path):
    path = Path(path).absolute()
    if ".." in path.parts or any(p.is_symlink() for p in (path, *path.parents)):
        raise BindError("capture paths must not contain symlinks or parent traversal")
    return path


def step(output, name, command, timeout):
    start = time.monotonic()
    timed_out = False
    # Command arguments include only local paths and CLI switches, never RPC URLs.
    with (output / (name + ".stdout")).open("xb") as out, \
            (output / (name + ".stderr")).open("xb") as err:
        try:
            result = subprocess.run(command, stdout=out, stderr=err, timeout=timeout,
                                    check=False, stdin=subprocess.DEVNULL)
            code = result.returncode
        except subprocess.TimeoutExpired:
            code, timed_out = 124, True
        except OSError:
            code = 127
    return {"name": name, "exit_code": code, "timed_out": timed_out,
            "elapsed_seconds": round(time.monotonic() - start, 3),
            "command": [str(item) for item in command]}


def classify(config, checks, verified, report, same_binary):
    """A successful subprocess is insufficient: require every intended scope."""
    needed = {"about-before", "validate", "scan", "verify", "report", "about-after"}
    successful = {c["name"] for c in checks if c["exit_code"] == 0}
    expected_owner = {k: config[k] for k in
                      ("namespace", "producer", "run_id", "data_class", "code_commit", "cargo_lock_sha256")}
    if config.get("schema_version") == 2:
        expected_owner["schema"] = "nqc-miner-owner-v2"
        expected_owner["build_identity_sha256"] = config["build_identity_sha256"]
    owners_match = all(isinstance(value.get("owner"), dict)
                       and all(value["owner"].get(k) == v for k, v in expected_owner.items())
                       for value in (verified, report))
    expected = {(s["id"], s["chain_id"], s["from_block"], s["to_block"]) for s in config["scopes"]}
    completed = report.get("scope_completion", [])
    actual = {(s.get("scope_id"), s.get("chain_id"), s.get("from_block"), s.get("to_block"))
              for s in completed if s.get("complete") is True}
    complete = (bool(expected) and needed <= successful and same_binary and owners_match
                and verified.get("integrity_verified") is True
                and verified.get("provisional_events") == 0
                and verified.get("invalidated_from") == {}
                and verified.get("completed_scopes") == len(expected)
                and len(completed) == len(expected) and actual == expected
                and report.get("activation_permitted") is False
                and report.get("measured_realized_profit") is None)
    return "complete_read_only_sample" if complete else "incomplete_or_rejected"


def capture(binary, template, output, timeout, transport_context):
    binary, template, output = map(safe_path, (binary, template, output))
    if not 1 <= timeout <= 3600:
        raise BindError("timeout must be between 1 and 3600 seconds")
    candidate = load_json_strict(template)
    # Avoid adopting existing evidence, even if it appears to be empty.
    output.mkdir(mode=0o700, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    checks = []
    before = digest(binary)
    config = None
    verified, report = {}, {}
    rejection = None
    try:
        checks.append(step(output, "about-before", [str(binary), "about"], 30))
        if checks[-1]["exit_code"] != 0:
            raise BindError("binary about failed")
        about = load_json_strict(output / "about-before.stdout")
        validate_about(about)
        config = bind(candidate, about)
        write_new_atomic(output / "config.json", config)
        checks.append(step(output, "validate", [str(binary), "validate-config", "--config",
                                               str(output / "config.json")], 30))
        if checks[-1]["exit_code"] != 0:
            raise BindError("configuration rejected before RPC access")
        checks.append(step(output, "scan", [str(binary), "scan", "--config",
                                           str(output / "config.json"), "--state",
                                           str(output / "state")], timeout))
        # Even a failed/timed-out scan must preserve and verify its partial journal.
        if (output / "state").is_dir():
            checks.append(step(output, "verify", [str(binary), "verify-journal", "--state",
                                                 str(output / "state")], 60))
            if checks[-1]["exit_code"] == 0:
                verified = load_json_strict(output / "verify.stdout")
            checks.append(step(output, "report", [str(binary), "report", "--config",
                                                 str(output / "config.json"), "--state",
                                                 str(output / "state")], 60))
            if checks[-1]["exit_code"] == 0:
                report = load_json_strict(output / "report.stdout")
    except (BindError, OSError, ValueError) as exc:
        # No subprocess response/URL/credential is interpolated into this field.
        rejection = type(exc).__name__
    try:
        after = digest(binary)
    except OSError:
        after = None
    checks.append(step(output, "about-after", [str(binary), "about"], 30))
    same_binary = (before == after and checks[0]["exit_code"] == 0
                   and checks[-1]["exit_code"] == 0
                   and (output / "about-before.stdout").read_bytes()
                   == (output / "about-after.stdout").read_bytes())
    status = (classify(config, checks, verified, report, same_binary)
              if config is not None and rejection is None else "incomplete_or_rejected")
    files = {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob("*")) if p.is_file()}
    summary = {"schema": "nqc-miner-capture-v1", "producer": "nqc-miner", "namespace": "nqc_miner_v1",
               "started_at_utc": started, "completed_at_utc": datetime.now(timezone.utc).isoformat(),
               "run_id": config.get("run_id") if config else None, "status": status,
               "transport_context": transport_context, "checks": checks, "rejection": rejection,
               "binary_before_sha256": before, "binary_after_sha256": after,
               "binary_unchanged": same_binary, "template_sha256": digest(template),
               "capture_script_sha256": digest(Path(__file__)), "files": files,
               "completed_scopes": verified.get("completed_scopes", 0),
               "canonical_events": verified.get("canonical_events", 0),
               "observer_bridge_enabled": False, "signing_enabled": False,
               "spending_authorized": False, "economic_certification": False,
               "source_authentication": "RPC agreement and local integrity only"}
    write_new_atomic(output / "capture.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--transport-context", choices=["public_rpc", "synthetic_fixture"], required=True)
    args = parser.parse_args()
    summary = capture(args.binary, args.template, args.output, args.timeout_seconds, args.transport_context)
    print(json.dumps({k: summary[k] for k in ("run_id", "status", "completed_scopes", "canonical_events")}))
    return 0 if summary["status"] == "complete_read_only_sample" else 1


if __name__ == "__main__":
    raise SystemExit(main())
