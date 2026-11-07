"""Execute Slither 0.11.6 on ONE immutable, owned Solidity fixture.

No arbitrary target, RPC URL, user-supplied Solidity, network scanner or signer.
Uses the existing source-bound Slither importer for the actual result, with
failure-closed tool admission and the owned subprocess group supervisor.

The wrapper observes a local run but does not authenticate the producer or
constitute independent execution replay. Host/network sandboxing is out of scope.
"""
from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
import subprocess
from pathlib import Path
import platform
import re
import sys
import tempfile

from . import native_compile, owned_process, static_review
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json

ROOT = Path(__file__).resolve().parent
SCANNER_VERSION = "0.11.6"
DETECTOR = "tx-origin"
SOURCE_NAME = "Owned.sol"
REPORT_NAME = "slither.json"
MAX_SOLIDITY_BYTES = 4096
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
# The fixture is a deliberately weak authorization control, never deployed.
OWNED_SOURCE = (
    "// SPDX-License-Identifier: MIT\n"
    "pragma solidity ^0.8.0;\n"
    "contract OwnedFixture {\n"
    "    address private immutable owner;\n"
    "    constructor() { owner = msg.sender; }\n"
    "    function inspect() external view returns (bool) {\n"
    "        return tx.origin == owner;\n"
    "    }\n"
    "}\n"
).encode("ascii")


class OwnedSlitherError(ValueError):
    """Errors never interpolate local paths or scanner output."""


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _allow_output(out: Path) -> None:
    if (out.exists() or out.is_symlink() or
            out.resolve().is_relative_to(ROOT.parent) or
            out.parent.resolve().is_relative_to(ROOT.parent)):
        raise OwnedSlitherError("OUTPUT_EXISTS_OR_IN_CHECKOUT")


def _package_state() -> dict:
    try:
        installed = version("slither-analyzer")
    except PackageNotFoundError:
        installed = None
    try:
        crytic = version("crytic-compile")
    except PackageNotFoundError:
        crytic = None
    return {"package": "slither-analyzer", "required_version": SCANNER_VERSION,
            "installed_version": installed, "crytic_compile_version": crytic,
            "matches": installed == SCANNER_VERSION and crytic == "0.4.2"}


def doctor(solc: Path) -> dict:
    """Read-only admission; never imports or executes Slither."""
    tool = _package_state()
    host_ok = platform.system() == "Linux" and platform.machine() in ("x86_64", "amd64")
    compiler_ok = False
    if host_ok and tool["matches"]:
        try:
            image = native_compile.read_pinned_binary(solc)
            compiler_ok = bool(image)
        except (OSError, ValueError, RuntimeError):
            pass
    return {"status": "OWNED_SLITHER_READY" if host_ok and compiler_ok and tool["matches"]
            else "OWNED_SLITHER_BLOCKED", "host_supported": host_ok,
            "slither": tool, "pinned_compiler_available": compiler_ok,
            "fixture_sha256": sha(OWNED_SOURCE), "targets_external": False,
            "network_isolated_by_wrapper": False, "scanner_executed": False}


def _write_local(path: Path, content: bytes, mode: int) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(path, mode)


def run_owned(solc: Path, out: Path, *, repo_commit: str) -> dict:
    """Run a pinned scanner version on fixed source and use our existing importer.

    The subprocess has fixed arguments and no user-controlled target. No attempt
    is made to hide incomplete/failed Slither executions or to fabricate alerts.
    """
    if type(repo_commit) is not str or SHA40.fullmatch(repo_commit) is None:
        raise OwnedSlitherError("DECLARED_COMMIT_REQUIRED")
    _allow_output(out)
    state = doctor(solc)
    if state["status"] != "OWNED_SLITHER_READY":
        raise OwnedSlitherError("SCANNER_OR_COMPILER_NOT_READY")
    solc_bytes = native_compile.read_pinned_binary(solc)
    with tempfile.TemporaryDirectory(prefix="superhunter-owned-slither-") as tmp:
        work = Path(tmp)
        source = work / SOURCE_NAME
        compiler = work / "solc"
        _write_local(source, OWNED_SOURCE, 0o400)
        _write_local(compiler, solc_bytes, 0o500)
        # Explicit small worker with rlimits; owned_process kills its session.
        command = [sys.executable, "-I", "-B", str(ROOT / "slither_owned_worker.py"), str(work)]
        with (tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr):
            finished = owned_process.run(
                command, cwd=work,
                env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                     "HOME": str(work), "PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
                timeout=90, stdout=stdout, stderr=stderr)
            if finished.returncode != 0:
                raise OwnedSlitherError("SLITHER_PROCESS_FAILED")
            if (stdout.seek(0, os.SEEK_END) > 2_000_000 or
                    stderr.seek(0, os.SEEK_END) > 2_000_000):
                raise OwnedSlitherError("SLITHER_OUTPUT_TOO_LARGE")
        if (read_artifact(work, SOURCE_NAME) != OWNED_SOURCE or
                native_compile.read_pinned_binary(compiler) != solc_bytes):
            raise OwnedSlitherError("FIXTURE_OR_COMPILER_CHANGED")
        report = read_artifact(work, REPORT_NAME)
        parsed = strict_json(report)
        if (set(parsed) != {"success", "error", "results"} or
                parsed["success"] is not True or parsed["error"] is not None or
                type(parsed["results"]) is not dict or
                type(parsed["results"].get("detectors")) is not list):
            raise OwnedSlitherError("SLITHER_REPORT_NOT_COMPLETE")
        context = {
            "schema_version": 1,
            "scope_id": "owned-fixed-local-fixture",
            "repository": {"repo": "superhunter-owned/fixture", "commit": repo_commit},
            "tool": {"name": "slither", "version": SCANNER_VERSION},
            "detectors": [DETECTOR], "report_sha256": sha(report),
            "sources": {SOURCE_NAME: sha(OWNED_SOURCE)},
            "input_kind": "external-report",
        }
        context_path = work / "context.json"
        _write_local(context_path, canonical(context), 0o400)
        # No successful bundle is made until the complete report validates.
        normalized = static_review.normalize(report, context, {SOURCE_NAME: OWNED_SOURCE})
        if normalized["normalization_complete"] is not True:
            raise OwnedSlitherError("SLITHER_SOURCE_BINDING_INCOMPLETE")
        # The fixed fixture intentionally contains tx.origin. A silent detector
        # cannot pass the owned positive control merely by exiting successfully.
        if (normalized.get("source_bound_alerts") != 1 or
                normalized.get("unique_alert_count") != 1 or
                any(alert.get("check") != DETECTOR for alert in normalized.get("alerts", []))):
            raise OwnedSlitherError("OWNED_POSITIVE_CONTROL_NOT_DETECTED")
        if out.exists() or out.is_symlink():
            raise OwnedSlitherError("OUTPUT_CHANGED_DURING_SCAN")
        imported = static_review.import_report(work / REPORT_NAME, context_path, work, out)
        if (imported["normalization_complete"] is not True or
                imported["report_sha256"] != sha(report) or
                imported["source_sha256"] != {SOURCE_NAME: sha(OWNED_SOURCE)}):
            raise OwnedSlitherError("SLITHER_IMPORT_DIVERGED")
        return {
            "status": "OWNED_SLITHER_IMPORTED_UNVERIFIED",
            "local_scanner_process_observed": True,
            "independent_producer_authentication": False,
            "execution_replayed_independently": False,
            "source_bound_alerts": imported["source_bound_alerts"],
            "unique_alert_count": imported["unique_alert_count"],
            "vulnerability_confirmed": False,
            "source_sha256": sha(OWNED_SOURCE),
            "output_bundle": "existing import-slither format",
        }


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description="Run fixed OWNED Slither fixture only; no target options")
    sub = parser.add_subparsers(dest="command", required=True)
    health = sub.add_parser("doctor-owned-slither")
    health.add_argument("--solc", required=True, type=Path)
    scan = sub.add_parser("run-owned-slither")
    scan.add_argument("--solc", required=True, type=Path)
    scan.add_argument("--out", required=True, type=Path)
    scan.add_argument("--repo-commit", required=True)
    args = parser.parse_args(argv)
    try:
        result = doctor(args.solc) if args.command == "doctor-owned-slither" else (
            run_owned(args.solc, args.out, repo_commit=args.repo_commit))
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] != "OWNED_SLITHER_BLOCKED" else 3
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, TimeoutError,
            subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "OWNED_SLITHER_REJECTED",
                          "error_type": type(exc).__name__,
                          "vulnerability_confirmed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
