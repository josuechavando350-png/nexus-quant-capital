"""Reproduce original PFT materialization and bind it to a clean NQC commit.

Offline provenance only. The unchanged materializer runs in the ORIGINAL Git
checkout, with its ancestry gate intact. No CI or market authority is created.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from integrity import canonical, digest, git_blob, read_regular, strict_json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "josuechavando350-png/nexus-engine"
SOURCE_ID = 1333360261
DESTINATION = "josuechavando350-png/nexus-quant-capital"
DESTINATION_ID = 1411047452
SOURCE_COMMIT = "e259739c9f75fedcd1061d2f78d6b8852e7a3060"
SOURCE_TREE = "c9cc97b31daa96c3c427c6781333a706e988f342"
CERTIFIED_COMMIT = "5b4a0cb778cb4370cd54eb6fcba765dc8d7cecdf"
CERTIFIED_TREE = "ef3498da528f85cdb9fdd82222d64773a557f853"
MATERIALIZER = "ci/nqc-census/materialize_effective_source.py"
PROFILE = "ci/nqc-census/effective-source-profile.json"
PINS = {MATERIALIZER: "7433151b85ecc85f719078f4d1b35c5cf27a6a32",
        PROFILE: "d4b599e6427744e15d89906a9e6c7cb2fb857576"}
PROTECTED = ("ci/nqc-protocol-fork/recovered-source",
             "ci/nqc-protocol-fork/reimplementation",
             "ci/nqc-protocol-fork/compatibility",
             "ci/nqc-protocol-fork/locks",
             "ci/nqc-protocol-fork/PROTOCOL_FORK_TRUTH_CONTRACT.json",
             "ci/nqc-protocol-fork/PROTOCOL_FORK_FINAL_CLOSEOUT.json")
FALSE_AUTHORITY = ("canonical_recertification", "production_authority",
                   "census_closed", "phase_advance_authorized", "signing_authorized",
                   "broadcast_authorized", "spending_authorized")


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def offline_env() -> dict[str, str]:
    # Do not inherit Git redirections/replacements or Python import overrides.
    return {"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1",
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_NO_REPLACE_OBJECTS": "1", "GIT_OPTIONAL_LOCKS": "0",
            "GIT_NO_LAZY_FETCH": "1", "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "protocol.allow", "GIT_CONFIG_VALUE_0": "never",
            "GIT_TERMINAL_PROMPT": "0"}


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, env=offline_env(), capture_output=True,
                          check=False)


def git(root: Path, *args: str) -> bytes:
    result = run(["git", "--no-replace-objects", "-C", str(root), *args], root)
    require(result.returncode == 0, "git_check_failed: " + " ".join(args))
    return result.stdout


def regular_directory(path: Path) -> Path:
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), "symlink_directory")
    require(path.is_dir(), "missing_directory")
    return path.resolve(strict=True)


def verify_git_context(root: Path) -> None:
    regular_directory(root)
    require(Path(git(root, "rev-parse", "--show-toplevel").decode().strip()) == root,
            "not_checkout_root")
    common = Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
                  .decode().strip())
    require(not (common / "info/grafts").exists(), "git_grafts_forbidden")
    require(not git(root, "for-each-ref", "--format=%(refname)", "refs/replace"),
            "git_replacements_forbidden")
    require(git(root, "rev-parse", "--is-shallow-repository").strip() == b"false",
            "shallow_history_forbidden")


def verify_commit(root: Path, commit: str, tree: str | None = None) -> str:
    require(isinstance(commit, str) and len(commit) == 40
            and all(c in "0123456789abcdef" for c in commit), "invalid_commit")
    raw = git(root, "cat-file", "commit", commit)
    actual = hashlib.sha1(b"commit " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    require(actual == commit, "commit_object_mismatch")
    actual_tree = git(root, "rev-parse", commit + "^{tree}").decode().strip()
    require(tree is None or actual_tree == tree, "commit_tree_mismatch")
    # Walk the real parent graph. A boundary/missing parent must not pass merely
    # because the named commit and its tree are present.
    git(root, "rev-list", "--parents", commit)
    return actual_tree


def verify_checkout_bytes(root: Path, commit: str, paths: tuple[str, ...] = ()) -> int:
    entries = git(root, "ls-tree", "-r", "-z", commit, "--", *paths).split(b"\0")
    count = 0
    for entry in filter(None, entries):
        meta, raw_path = entry.split(b"\t", 1)
        mode, kind, blob = meta.decode().split()
        require(kind == "blob" and mode in {"100644", "100755"}, "nonregular_git_entry")
        path = root / raw_path.decode()
        require(git_blob(read_regular(path, limit=16 * 1024 * 1024)) == blob,
                "checkout_blob_mismatch: " + raw_path.decode())
        actual_mode = "100755" if path.stat().st_mode & stat.S_IXUSR else "100644"
        require(actual_mode == mode, "checkout_mode_mismatch")
        count += 1
    require(count > 0, "empty_checkout_inventory")
    return count


def verify_clean_head(root: Path, expected_commit: str) -> str:
    verify_git_context(root)
    require(git(root, "rev-parse", "HEAD").decode().strip() == expected_commit,
            "producer_head_mismatch")
    tree = verify_commit(root, expected_commit)
    require(not git(root, "status", "--porcelain=v1", "--untracked-files=all"),
            "dirty_checkout")
    return tree


def verify_identities(manifest: dict) -> None:
    require((manifest.get("source_repository"), manifest.get("source_repository_id"),
             manifest.get("source_commit"), manifest.get("source_tree"))
            == (SOURCE, SOURCE_ID, SOURCE_COMMIT, SOURCE_TREE), "source_identity_mismatch")
    require((manifest.get("proposed_destination"), manifest.get("destination_repository_id"))
            == (DESTINATION, DESTINATION_ID), "destination_identity_mismatch")
    require(manifest.get("authority") == "SOURCE_SNAPSHOT_ONLY_NO_NEW_CERTIFICATION",
            "relabelled_source_certificate")


def verify_source(root: Path, source: Path) -> None:
    require(verify_clean_head(source, SOURCE_COMMIT) == SOURCE_TREE, "source_tree_mismatch")
    verify_commit(source, CERTIFIED_COMMIT, CERTIFIED_TREE)
    git(source, "merge-base", "--is-ancestor", CERTIFIED_COMMIT, SOURCE_COMMIT)
    git(source, "diff", "--no-ext-diff", "--quiet", CERTIFIED_COMMIT, SOURCE_COMMIT,
        "--", *PROTECTED)
    # Also verify every object in the evidence store, not just names returned by
    # rev-parse. This rejects corrupt objects before executing pinned code.
    git(source, "fsck", "--full", "--no-reflogs", "--no-dangling", SOURCE_COMMIT)
    verify_checkout_bytes(source, SOURCE_COMMIT, (MATERIALIZER, PROFILE, *PROTECTED))
    for path, blob in PINS.items():
        require(git_blob(read_regular(source / path)) == blob, "source_code_pin_mismatch")
        require(git_blob(read_regular(root / path)) == blob, "destination_code_pin_mismatch")


def tree_digest(root: Path) -> str:
    """Same digest encoding as the pinned materializer; reject nonregular entries."""
    regular_directory(root)
    hasher = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "symlink_effective_tree")
        if path.is_dir():
            continue
        data = read_regular(path, limit=16 * 1024 * 1024)
        rel = path.relative_to(root).as_posix().encode()
        mode = b"755" if path.stat().st_mode & stat.S_IXUSR else b"644"
        hasher.update(len(rel).to_bytes(4, "big") + rel + mode
                      + len(data).to_bytes(8, "big") + hashlib.sha256(data).digest())
    return hasher.hexdigest()


def verify_receipt(reference: bytes, effective: Path) -> dict:
    receipt_bytes = read_regular(effective / "MATERIALIZATION.json")
    # Strict parsing rejects duplicate keys even if JSON parsers could agree.
    prior, receipt = strict_json(reference), strict_json(receipt_bytes)
    require(canonical(prior) == canonical(receipt), "source_receipt_mismatch")
    require(receipt.get("authority") == "NQC_RMC_CERTIFIED_EFFECTIVE_SOURCE_V1"
            and receipt.get("materializer_head") == SOURCE_COMMIT
            and receipt.get("protocol_fork_certified_commit") == CERTIFIED_COMMIT
            and receipt.get("protocol_fork_certified_tree") == CERTIFIED_TREE,
            "relabelled_materialization_certificate")
    require(receipt["invariants"]["production_authority"] is False
            and receipt["truth_boundaries"]["production_authority"] is False,
            "unexpected_materialization_authority")
    for path, key in (("recovered-source", "effective_recovered_source_tree_sha256"),
                      ("reimplementation", "reimplementation_bundle_tree_sha256")):
        require(tree_digest(effective / path) == receipt[key], "effective_tree_mismatch")
    return receipt


def new_output(path: Path, inputs: tuple[Path, ...]) -> Path:
    path = Path(path).absolute()
    require(not any(p.is_symlink() for p in (path, *path.parents)), "symlink_output")
    path = path.resolve()
    require(not path.exists(), "output_already_exists")
    for source in inputs:
        source = Path(source).resolve()
        require(not path.is_relative_to(source) and not source.is_relative_to(path),
                "output_overlaps_input")
    return path


def build_binding(root: Path, source: Path, reference: Path, output: Path,
                  expected_commit: str) -> dict:
    root, source = regular_directory(root), regular_directory(source)
    require(not root.is_relative_to(source) and not source.is_relative_to(root),
            "source_destination_overlap")
    output = new_output(output, (root, source, reference))
    reference_bytes = read_regular(reference)
    tree = verify_clean_head(root, expected_commit)
    tracked_count = verify_checkout_bytes(root, expected_commit)
    manifest_bytes = read_regular(root / "migration/source-manifest.json")
    verify_identities(strict_json(manifest_bytes))
    verify_source(root, source)
    isolation = run([sys.executable, str(root / "omega/isolation.py"),
                     "--root", str(root), "--source-git", str(source)], root)
    require(isolation.returncode == 0, "full_isolation_failed")
    isolation_report = strict_json(isolation.stdout)
    require(isolation_report.get("status") == "OMEGA_OFFLINE_ISOLATION_PASS",
            "unexpected_isolation_result")
    output.mkdir(parents=True, exist_ok=False)
    effective = output / "effective"
    result = run([sys.executable, str(source / MATERIALIZER), "--output", str(effective)], source)
    (output / "materializer.stdout.log").write_bytes(result.stdout)
    (output / "materializer.stderr.log").write_bytes(result.stderr)
    require(result.returncode == 0, "original_materializer_failed")
    receipt = verify_receipt(reference_bytes, effective)
    # Recheck both identities and all relevant bytes after executing the original.
    require(verify_clean_head(root, expected_commit) == tree, "producer_changed_during_run")
    verify_checkout_bytes(root, expected_commit)
    verify_clean_head(source, SOURCE_COMMIT)
    verify_checkout_bytes(source, SOURCE_COMMIT, (MATERIALIZER, PROFILE, *PROTECTED))
    report = {
        "schema": "nqc.omega.pft-source-binding.v1",
        "status": "OFFLINE_SOURCE_BINDING_PASS",
        "evidence_scope": "LOCAL_REPRODUCTION_NOT_CI_CERTIFICATION",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_repository": SOURCE, "source_repository_id": SOURCE_ID,
        "source_commit": SOURCE_COMMIT, "source_tree": SOURCE_TREE,
        "producer_repository": DESTINATION, "producer_repository_id": DESTINATION_ID,
        "producer_commit": expected_commit, "producer_tree": tree,
        "producer_tracked_files_verified": tracked_count,
        "producer_workflow": None, "producer_run": None, "producer_artifact": None,
        "remote_producer_identity_authenticated": False,
        "original_ancestry_gate_preserved": True,
        "destination_ancestry_claimed": False,
        "source_manifest_sha256": digest(manifest_bytes),
        "original_materializer_git_blob": PINS[MATERIALIZER],
        "original_profile_git_blob": PINS[PROFILE],
        "adapter_sha256": digest(read_regular(root / "omega/pft_source_binding.py")),
        "reference_receipt_sha256": digest(reference_bytes),
        "materialization_receipt_sha256": digest(read_regular(effective / "MATERIALIZATION.json")),
        "materialization_receipt": receipt,
        "isolation": isolation_report,
        "materializer_stdout_sha256": digest(result.stdout),
        "materializer_stderr_sha256": digest(result.stderr),
        "historical_forks_executed": False, "disconnected_replay_executed": False,
        **{key: False for key in FALSE_AUTHORITY},
    }
    report["report_commitment_sha256"] = digest(canonical(report))
    with (output / "binding.json").open("xb") as handle:
        handle.write(canonical(report))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--source-checkout", required=True, type=Path)
    parser.add_argument("--source-receipt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()
    try:
        report = build_binding(args.root, args.source_checkout, args.source_receipt,
                               args.output, args.expected_commit)
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"status": "OFFLINE_SOURCE_BINDING_BLOCKED", "reason": str(error),
                          **{key: False for key in FALSE_AUTHORITY}}, sort_keys=True))
        return 1
    print(json.dumps({"status": report["status"], "producer_commit": report["producer_commit"],
                      "canonical_recertification": False, "report": str(args.output / "binding.json")},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
