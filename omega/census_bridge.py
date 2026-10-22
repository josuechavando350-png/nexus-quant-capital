"""Read-only Omega bridge to the immutable RMC-016 historical aggregate auditor.

Only authentic source bytes enter this adapter. No GO, trading authority,
current market coverage, independent EVM replay or NQC revenue is produced.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from integrity import canonical, digest, git_blob, load_pinned_python, read_regular

ROOT = Path(__file__).resolve().parents[1]
AUDITOR_PATH = "ci/nqc-census/rmc016_winner_net_audit.py"
AUDITOR_BLOB = "fb0c6988edb30542c899e80c32c355e73e37dba2"
ECONOMIC_PATH = "ci/nqc-census/rmc016-production-evidence.json"
ECONOMIC_BLOB = "5d5ed3635a426d686c8a98aa3547fd5b9d8b95aa"
ARCHIVE_PINS = (
    "aff472236ff5177f123e4a6ccc95d4dae5fb37833f8645984116c407c179d790",
    "27bd8909f865429e6bbc4580adf52af985beab8ed45cc11850616ab53a02b199",
)


def build_report(d15_archive: Path, d16_archive: Path, root: Path = ROOT) -> dict:
    """Re-run the pinned original auditor on a frozen copy of authenticated inputs."""
    module = load_pinned_python(root / AUDITOR_PATH, AUDITOR_BLOB, "omega_legacy_rmc016")
    source = read_regular(root / ECONOMIC_PATH)
    if git_blob(source) != ECONOMIC_BLOB:
        raise ValueError("economic_source_blob_mismatch")
    inputs = [read_regular(d15_archive), read_regular(d16_archive)]
    if tuple(map(digest, inputs)) != ARCHIVE_PINS:
        raise ValueError("artifact_sha256_mismatch")
    # Freeze each read once: the original auditor checks the frozen copies again.
    with tempfile.TemporaryDirectory(prefix="nqc-omega-inputs-") as temp:
        paths = [Path(temp) / name for name in ("d15.zip", "d16.zip", "source.json")]
        for path, raw in zip(paths, [*inputs, source]):
            path.write_bytes(raw)
        baseline = module.audit(*paths)
    unsigned = {key: value for key, value in baseline.items()
                if key != "audit_commitment_sha256"}
    if baseline.get("audit_commitment_sha256") != digest(canonical(unsigned)):
        raise ValueError("legacy_report_commitment_mismatch")
    if (baseline.get("nexus_realized_profitability_proven") is not False
            or baseline.get("nexus_capture_probability_calibrated") is not False
            or baseline.get("nexus_monthly_pnl_estimate_usd_wad") is not None):
        raise ValueError("unsupported_nqc_profitability_claim")
    report = {
        "schema": "nqc.omega.census-bridge.v1",
        "decision": "OBSERVAR",
        "decision_scope": "HISTORICAL_EVIDENCE_INTAKE_ONLY_NOT_A_TRADE_DECISION",
        "census_closed": False,
        "phase_advance_authorized": False,
        "signing_authorized": False,
        "broadcast_authorized": False,
        "spending_authorized": False,
        "consumer_repository": "josuechavando350-png/nexus-quant-capital",
        "consumer_repository_id": 1411047452,
        "source_repository": "josuechavando350-png/nexus-engine",
        "source_repository_id": 1333360261,
        "consumer_baseline_commit": "16e352225ba8a6a931834c4edf3d86d9a2924b7d",
        "legacy_auditor_git_blob": AUDITOR_BLOB,
        "economic_source_git_blob": ECONOMIC_BLOB,
        "adapter_sha256": digest(read_regular(Path(__file__))),
        "integrity_helper_sha256": digest(read_regular(Path(__file__).with_name("integrity.py"))),
        "historical_baseline": baseline,
        "omega_census_metrics_not_established": {
            "winner_addresses_by_transaction": None,
            "blocks_from_oracle_to_winner": None,
            "builder_payment_share_of_bonus": None,
            "all_costs_net_margin_usd_wad": None,
            "current_market_coverage": None,
        },
        "blocking_reasons": sorted(set(baseline["blocking_reasons"] + [
            "OMEGA_THREE_WAY_TRUTH_PARITY_NOT_CERTIFIED",
            "OMEGA_ALL_SCOPED_POSITIONS_NOT_RECONCILED",
            "OMEGA_BONUS_WINNER_ORACLE_DELAY_AND_BUILDER_TIPS_NOT_RECONCILED",
            "LEGACY_AUTHORITY_IS_NOT_A_NEW_PRODUCER_CERTIFICATE",
        ])),
        "historical_policy_note": "LEGACY_ZERO_OWN_CAPITAL_AUTHORITY_UNCHANGED; "
                                  "V3_CANARY_GAS_POLICY_IS_SEPARATE_AND_INACTIVE",
    }
    report["report_commitment_sha256"] = digest(canonical(report))
    return report


def store_report(directory: Path, report: dict) -> Path:
    """Atomic, no-clobber content-addressed storage on a local POSIX filesystem.

    This is not a certified Evidence Vault, replication system or reorg journal.
    """
    if (report.get("schema") != "nqc.omega.census-bridge.v1"
            or report.get("decision") != "OBSERVAR"
            or any(report.get(key) is not False for key in (
                "census_closed", "phase_advance_authorized", "signing_authorized",
                "broadcast_authorized", "spending_authorized"))):
        raise ValueError("unsupported_report_authority")
    unsigned = {key: value for key, value in report.items() if key != "report_commitment_sha256"}
    commitment = digest(canonical(unsigned))
    if report.get("report_commitment_sha256") != commitment:
        raise ValueError("report_commitment_mismatch")
    directory = Path(directory).absolute()
    if any(part.is_symlink() for part in (directory, *directory.parents)):
        raise ValueError("symlink_output_directory")
    directory.mkdir(parents=True, exist_ok=True)
    final = directory / (commitment + ".json")
    raw = canonical(report)
    if final.exists() or final.is_symlink():
        if read_regular(final) != raw:
            raise ValueError("existing_evidence_mismatch")
        return final
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".omega-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, final)  # Atomic publication; never replace an existing record.
        except FileExistsError:
            if read_regular(final) != raw:
                raise ValueError("existing_evidence_mismatch") from None
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--d15-archive", required=True, type=Path)
    parser.add_argument("--d16-archive", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = build_report(args.d15_archive, args.d16_archive)
        path = store_report(args.out_dir, report)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        print(json.dumps({"decision": "NO-GO", "phase_advance_authorized": False,
                          "reason": str(error)}, sort_keys=True))
        return 1
    print(json.dumps({"decision": report["decision"], "evidence_file": str(path),
                      "census_closed": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
