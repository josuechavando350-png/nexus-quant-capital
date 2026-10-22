"""Additive Omega boundary adapter. Never edits the legacy isolation verifier.

The frozen verifier rejects every new root. Project only the explicit Omega
extension out of a disposable copy, and run the ORIGINAL full verifier there.
No other root/path is hidden, and incomplete source copies cannot pass.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path

from audit import verify_plan
from integrity import digest, load_pinned_python, read_regular, strict_json

ROOT = Path(__file__).resolve().parents[1]
VERIFIER_BLOB = "3bb842872a4ca89e81bcf45839b42cc88d26f84e"
OMEGA_WORKFLOW = ".github/workflows/omega-h2-audit.yml"
WORKFLOW_TEMPLATE = "omega/h2_actions_workflow.yml.disabled"
WORKFLOW_SHA256 = "a2d101c69a6ce5aa0dc46065429547dbafec79c0d253afffce6c57231d755f16"
EXTENSION_FILES = frozenset({
    "omega/README.md", "omega/architecture_v3.json", "omega/audit.py",
    "omega/test_audit.py", "omega/integrity.py", "omega/census_bridge.py",
    "omega/isolation.py", "omega/test_integration.py", "omega/census_map.json",
    "omega/AUDIT_H2.md", "omega/AUDIT_H2_GIT_OBJECTS.md",
    "omega/evidence/historical-baseline.json",
    "omega/census_assessment.json", "omega/census_assessment.py",
    "omega/test_census_assessment.py",
    "omega/opportunity_vault.py", "omega/test_opportunity_vault.py",
    "omega/OPPORTUNITY_DOSSIER_CONTRACT.md", "omega/AUDIT_H4.md",
    "omega/liquidation_order_book.py", "omega/test_liquidation_order_book.py",
    "omega/LIQUIDATION_ORDER_BOOK_CONTRACT.md", "omega/AUDIT_H5.md",
    "omega/causal_graph.py", "omega/test_causal_graph.py",
    "omega/CAUSAL_GRAPH_CONTRACT.md", "omega/AUDIT_H6.md",
    "omega/oracle_semantics.py", "omega/test_oracle_semantics.py",
    "omega/ORACLE_SEMANTICS_CONTRACT.md", "omega/AUDIT_H7.md",
    "omega/long_tail.py", "omega/test_long_tail.py",
    "omega/LONG_TAIL_CONTRACT.md", "omega/AUDIT_H8.md",
    "omega/protocol_adapters.py", "omega/test_protocol_adapters.py",
    "omega/PROTOCOL_ADAPTER_CONTRACT.md", "omega/AUDIT_H9.md",
    "omega/truth_engine.py", "omega/test_truth_engine.py",
    "omega/TRUTH_TRIAD_CONTRACT.md", "omega/AUDIT_H10.md",
    "omega/competition_ledger.py", "omega/test_competition_ledger.py",
    "omega/COMPETITION_LEDGER_CONTRACT.md", "omega/AUDIT_H11.md",
    "omega/candidate_coherence.py", "omega/test_candidate_coherence.py",
    "omega/CANDIDATE_COHERENCE_CONTRACT.md", "omega/AUDIT_H12.md",
    "omega/regression.py", "omega/test_regression.py", "omega/historical_regression.py",
    "omega/AUDIT_H2_EXECUTABLE.md", "omega/evidence/h2-executable.json",
    "omega/evidence/h2-census-current.json", "omega/evidence/h2-census-source.json",
    "omega/evidence/h2-census-comparison.json", "omega/evidence/h2-omega.json",
    "omega/evidence/h2-historical.json", "omega/evidence/h2-fork-preflight.json",
    "omega/evidence/h2-execution-logs.json",
    "omega/pft_source_binding.py", "omega/test_pft_source_binding.py",
    "omega/PFT_SOURCE_BINDING_CONTRACT.md",
    "omega/AUDIT_H2_PFT_BINDING.md", "omega/evidence/h2-pft-binding.json",
    "omega/evidence/h2-pft-audit.json", "omega/evidence/h2-pft-logs.json",
    "omega/evidence/h2-pft-omega.json",
    "omega/h2_actions.py", "omega/test_h2_actions.py", WORKFLOW_TEMPLATE,
    "omega/ACTIONS_MIGRATION.md", "omega/AUDIT_H2_ACTIONS.md",
})
EXTENSION_DIRS = {"omega", "omega/evidence"}


def reviewed_workflow(root: Path) -> bool:
    """One explicit new workflow exception; historical workflows stay disabled."""
    template = read_regular(root / WORKFLOW_TEMPLATE)
    if digest(template) != WORKFLOW_SHA256:
        raise ValueError("workflow_template_digest_mismatch")
    active = root / OMEGA_WORKFLOW
    if not active.exists() and not active.is_symlink():
        return False
    if read_regular(active) != template or stat.S_IMODE(active.stat().st_mode) != 0o644:
        raise ValueError("unreviewed_active_workflow")
    return True


def inventory(root: Path) -> list[Path]:
    root = Path(root).absolute()
    if any(part.is_symlink() for part in (root, *root.parents)) or not root.is_dir():
        raise ValueError("invalid_repository_root")
    files = []
    seen = set()
    for current, directories, names in os.walk(root, followlinks=False):
        directory = Path(current)
        if directory == root:
            directories[:] = [name for name in directories if name != ".git"]
            names = [name for name in names if name != ".git"]
        for name in sorted(directories + names):
            path = directory / name
            relative = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError("nonregular_repository_entry: " + relative)
            if relative == "omega" or relative.startswith("omega/"):
                allowed = EXTENSION_DIRS if stat.S_ISDIR(mode) else EXTENSION_FILES
                if relative not in allowed:
                    raise ValueError("unreviewed_omega_path: " + relative)
                if stat.S_ISREG(mode):
                    seen.add(relative)
            if stat.S_ISREG(mode):
                files.append(path)
    if seen != EXTENSION_FILES:
        raise ValueError("missing_omega_paths: " + ",".join(sorted(EXTENSION_FILES - seen)))
    reviewed_workflow(root)
    return sorted(files)


def project_repository(root: Path, destination: Path) -> None:
    """Copy ALL non-Omega payload bytes and modes, including forbidden additions.

    Unknown paths must reach the old verifier and fail there, not be filtered out.
    .git is metadata already excluded by that verifier. Source is never edited.
    """
    root = Path(root).absolute()
    destination = Path(destination).absolute()
    if destination.is_relative_to(root) or root.is_relative_to(destination):
        raise ValueError("projection_overlaps_source")
    files = inventory(root)
    destination.mkdir(parents=True, exist_ok=False)
    for path in files:
        relative = path.relative_to(root)
        if relative.as_posix() in EXTENSION_FILES or relative.as_posix() == OMEGA_WORKFLOW:
            continue
        data = read_regular(path, limit=512 * 1024 * 1024)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(stat.S_IMODE(path.stat().st_mode))


def verify_repository(root: Path = ROOT, source_git: Path | None = None) -> dict:
    root = Path(root).absolute()
    problems = verify_plan(strict_json(read_regular(root / "omega/architecture_v3.json")))
    if problems:
        raise ValueError("architecture_invalid: " + ",".join(problems))
    original = load_pinned_python(root / "migration/verify_isolation.py", VERIFIER_BLOB,
                                  "omega_original_isolation")
    with tempfile.TemporaryDirectory(prefix="nqc-omega-isolation-") as temporary:
        projected = Path(temporary) / "legacy"
        project_repository(root, projected)
        result = original.verify(projected, source_git)
    if (result.get("status") != "ISOLATED_SOURCE_IDENTITY_PASS"
            or result.get("canonical_recertification") is not False
            or result.get("active_workflows") != 0):
        raise ValueError("unexpected_original_verifier_result")
    return {"status": "OMEGA_OFFLINE_ISOLATION_PASS", "legacy_result": result,
            "active_omega_workflows": int(reviewed_workflow(root)),
            "active_workflow_sha256": WORKFLOW_SHA256 if reviewed_workflow(root) else None,
            "extension_file_count": len(EXTENSION_FILES),
            "canonical_recertification": False, "phase_advance_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--source-git", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify_repository(args.root, args.source_git), sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError, RecursionError, subprocess.CalledProcessError) as error:
        print(json.dumps({"status": "OMEGA_ISOLATION_BLOCKED", "reason": str(error),
                          "phase_advance_authorized": False}, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
