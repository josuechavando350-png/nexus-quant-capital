#!/usr/bin/env python3
"""Bind an NQC Miner run template to the exact clean binary identity."""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PLACEHOLDER = "__FROM_ABOUT__"


class BindError(ValueError):
    pass


def compute_build_identity(about):
    fields = [
        ("commit", about["code_commit"]),
        ("source", about["source_sha256"]),
        ("lock", about["cargo_lock_sha256"]),
        ("rustc", about["rustc_version"]),
        ("target", about["target"]),
        ("host", about["host"]),
        ("profile", about["profile"]),
        ("opt", about["opt_level"]),
        ("debug", "true" if about["debug"] else "false"),
        ("rustflags", about["rustflags_sha256"]),
    ]
    material = "\0".join(part for pair in fields for part in pair)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def load_json_strict(path: Path):
    def no_dupes(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise BindError(f"duplicate JSON key: {key}")
            out[key] = value
        return out

    data = path.read_bytes()
    if len(data) > 1_048_576:
        raise BindError("input JSON exceeds 1 MiB")
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=no_dupes)
    except UnicodeDecodeError as exc:
        raise BindError("input JSON is not UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise BindError(f"invalid JSON: {exc.msg}") from exc


def validate_about(about):
    required = {
        "name": "nqc-miner",
        "namespace": "nqc_miner_v1",
        "source_dirty": False,
        "observer_bridge_enabled": False,
        "signing_enabled": False,
        "gas_budget_mxn_centavos": 0,
        "economic_certification": False,
    }
    if not isinstance(about, dict):
        raise BindError("about must be a JSON object")
    for key, expected in required.items():
        if about.get(key) != expected:
            raise BindError(f"about field {key} is not the required isolated value")
    commit = about.get("code_commit")
    lock_hash = about.get("cargo_lock_sha256")
    if not isinstance(commit, str) or not HEX40.fullmatch(commit) or set(commit) == {"0"}:
        raise BindError("about code_commit is not a clean immutable SHA")
    if not isinstance(lock_hash, str) or not HEX64.fullmatch(lock_hash):
        raise BindError("about Cargo.lock SHA256 is invalid")
    if not isinstance(about.get("source_sha256"), str) or not HEX64.fullmatch(
        about["source_sha256"]
    ):
        raise BindError("about source SHA256 is invalid")
    for key in ("rustc_version", "target", "host", "profile", "opt_level"):
        if not isinstance(about.get(key), str) or not about[key].strip():
            raise BindError(f"about field {key} is missing build identity")
    if not isinstance(about.get("debug"), bool):
        raise BindError("about field debug is missing build identity")
    if not isinstance(about.get("rustflags_sha256"), str) or not HEX64.fullmatch(
        about["rustflags_sha256"]
    ):
        raise BindError("about rustflags SHA256 is invalid")
    if not isinstance(about.get("build_identity_sha256"), str) or not HEX64.fullmatch(
        about["build_identity_sha256"]
    ):
        raise BindError("about build identity SHA256 is invalid")
    if about["build_identity_sha256"] != compute_build_identity(about):
        raise BindError("about build identity does not match its compiler/source fields")
    return commit, lock_hash


def bind(template, about):
    if not isinstance(template, dict):
        raise BindError("template must be a JSON object")
    for field in ("code_commit", "cargo_lock_sha256", "build_identity_sha256"):
        if template.get(field) != PLACEHOLDER:
            raise BindError(f"template field {field} must equal {PLACEHOLDER}")
    if template.get("namespace") != "nqc_miner_v1" or template.get("producer") != "nqc-miner":
        raise BindError("foreign template namespace or producer")
    if template.get("observer_bridge_enabled") is not False:
        raise BindError("observer bridge must remain disabled")
    if template.get("signing_enabled") is not False:
        raise BindError("signing must remain disabled")
    if template.get("gas_budget_mxn_centavos") != 0:
        raise BindError("active gas budget must remain zero")
    commit, lock_hash = validate_about(about)
    result = dict(template)
    result["code_commit"] = commit
    result["cargo_lock_sha256"] = lock_hash
    result["build_identity_sha256"] = about["build_identity_sha256"]
    return result


def write_new_atomic(path: Path, payload):
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise BindError("output path already exists")
    encoded = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(prefix=".nqc-miner-config-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Bind an NQC Miner run template to a clean binary about record."
    )
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--about", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    template = load_json_strict(args.template)
    about = load_json_strict(args.about)
    bound = bind(template, about)
    write_new_atomic(args.output, bound)
    print(json.dumps({
        "status": "bound",
        "run_id": bound.get("run_id"),
        "code_commit": bound["code_commit"],
        "cargo_lock_sha256": bound["cargo_lock_sha256"],
        "build_identity_sha256": bound["build_identity_sha256"],
        "rustc_version": about["rustc_version"],
        "target": about["target"],
        "profile": about["profile"],
        "rustflags_sha256": about["rustflags_sha256"],
        "observer_bridge_enabled": False,
        "signing_enabled": False,
        "gas_budget_mxn_centavos": 0,
        "output": str(args.output),
    }, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (BindError, OSError) as exc:
        print(f"nqc-miner-config: {exc}", file=sys.stderr)
        raise SystemExit(1)
