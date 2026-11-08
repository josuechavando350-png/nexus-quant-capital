"""Offline evidence bridge and fixed native lab; no RPC or automatic disclosure."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .bridge import ContractError, evaluate, load_json, render_report
from .integration import export_diablo, import_nqc
from .safe_io import canonical, read_artifact, write_new_bundle
from .privacy import redact_record, PrivateArgumentParser


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] in ('review-preserved-retention', 'verify-preserved-retention'):
        from .preserved_retention import main as retention_main
        return retention_main(argv)
    if argv and argv[0] in ('index-preserved-archives', 'verify-preserved-index'):
        from .preserved_index import main as index_main
        return index_main(argv)
    if argv and argv[0] in ('export-preserved-copy', 'verify-preserved-archive'):
        from .portable_copy import main as portable_main
        return portable_main(argv)
    if argv and argv[0] == 'verify-preserved-copy':
        from .preserved_copy import main as preserved_main
        return preserved_main(argv[1:])
    if argv and argv[0] in ('inspect-local-bundle', 'preserve-local-bundle', 'verify-preserved-bundle'):
        from .bundle_recovery import main as recovery_main
        return recovery_main(argv)
    if argv and argv[0] in ('diagnose-owned-boundary', 'verify-owned-boundary-diagnosis'):
        from .owned_boundary_diagnosis import main as diagnosis_main
        return diagnosis_main(argv)
    if argv and argv[0] in ('capture-owned-boundary', 'verify-owned-boundary-capture'):
        from .owned_capture import main as owned_capture_main
        return owned_capture_main(argv)
    if argv and argv[0] in ('review-journal-custody', 'verify-journal-custody'):
        from .journal_custody import main as journal_custody_main
        return journal_custody_main(argv)
    if argv and argv[0] in ('review-qa-custody', 'verify-qa-custody'):
        from .qa_custody import main as qa_custody_main
        return qa_custody_main(argv)
    if argv and argv[0] in ('compare-owned-correct-engines', 'verify-owned-correct-engines'):
        from .owned_correct_cross_evm import main as correct_native_main
        return correct_native_main(argv)
    if argv and argv[0] in ('review-owned-correct-behavior', 'verify-owned-correct-behavior'):
        from .owned_authority_behavior import main as behavior_main
        return behavior_main(argv)
    if argv and argv[0] in ('review-registry-inventory', 'verify-registry-inventory'):
        from .portfolio_inventory import main as inventory_main
        return inventory_main(argv)
    if argv and argv[0] in ('link-owned-coverage', 'verify-owned-coverage-link'):
        from .owned_coverage_link import main as coverage_link_main
        return coverage_link_main(argv)
    if argv and argv[0] in ('review-owned-coverage-suite', 'verify-owned-coverage-suite'):
        from .owned_authority_coverage_suite import main as coverage_suite_main
        return coverage_suite_main(argv)
    if argv and argv[0] in ('review-owned-authority-coverage', 'verify-owned-authority-coverage'):
        from .owned_authority_coverage import main as coverage_main
        return coverage_main(argv)
    if argv and argv[0] in ('finish-owned-defensive','verify-owned-defensive'):
        from .owned_defensive_acceptance import main as defensive_acceptance_main
        return defensive_acceptance_main(argv)
    if argv and argv[0] in ('evaluate-owned-slither-native','verify-owned-slither-native'):
        from .owned_slither_native import main as owned_native_slither_main
        return owned_native_slither_main(argv)
    if argv and argv[0] in ("compare-owned-slither-pairs", "verify-owned-slither-comparison"):
        from .slither_pair_replay import main as slither_compare_main
        return slither_compare_main(argv)
    if argv and argv[0] in ("run-owned-slither-pair", "verify-owned-slither-pair"):
        from .slither_control_pair import main as slither_pair_main
        return slither_pair_main(argv)
    if argv and argv[0] in ("doctor-owned-slither", "run-owned-slither"):
        from .slither_owned_runner import main as owned_slither_main
        return owned_slither_main(argv)
    if argv and argv[0] in ('doctor-otel-qa', 'profile-owned-qa', 'verify-owned-qa-profile'):
        from .otel_qa import main as otel_main
        return otel_main(argv)
    if argv and argv[0] in ('compare-owned-authority-engines', 'verify-owned-authority-engines'):
        from .owned_authority_cross_evm import main as authority_cross_main
        return authority_cross_main(argv)
    if argv and argv[0] in ('evaluate-owned-authority', 'verify-owned-authority'):
        from .owned_authority_review import main as authority_main
        return authority_main(argv)
    if argv and argv[0] in ('prepare-owned-platform', 'verify-owned-preparation',
                           'finish-owned-platform', 'verify-owned-platform'):
        from .owned_platform import main as owned_platform_main
        return owned_platform_main(argv)
    if argv and argv[0] == "verify-failed-check":
        from .qa_failure import main as failure_main
        return failure_main(argv[1:])
    if argv and argv[0] in ("evaluate-owned-quota", "verify-owned-quota"):
        from .owned_quota_review import main as quota_main
        return quota_main(argv)
    if argv and argv[0] in ("audit-evidence-cuts", "verify-evidence-cuts"):
        from .evidence_cut_sets import main as cut_main
        return cut_main(argv)
    if argv and argv[0] in ("audit-joint-evidence", "verify-joint-evidence"):
        from .evidence_joint_failure import main as joint_main
        return joint_main(argv)
    if argv and argv[0] in ("audit-common-evidence", "verify-common-evidence"):
        from .evidence_common_mode import main as common_main
        return common_main(argv)
    if argv and argv[0] in ("audit-source-ablation", "verify-source-ablation"):
        from .evidence_ablation import main as ablation_main
        return ablation_main(argv)
    if argv and argv[0] in ("audit-chain-paths", "verify-chain-paths"):
        from .chain_path_audit import main as path_audit_main
        return path_audit_main(argv)
    if argv and argv[0] in ("triage-critical-chains", "verify-critical-triage"):
        from .critical_chain import main as triage_main
        return triage_main(argv)
    if argv and argv[0] in ("replay-evm-forensic", "verify-evm-replay"):
        from .evm_bounded_replay import main as replay_main
        return replay_main(argv)
    if argv and argv[0] in ("review-evm-forensic", "verify-evm-forensic"):
        from .evm_forensic_binding import main as bridge_main
        return bridge_main(argv)
    if argv and argv[0] in ("correlate-journals", "verify-journal-correlations"):
        from .journal_correlation import main as correlation_main
        return correlation_main(argv)
    if argv and argv[0] in ("ingest-journal", "verify-journal"):
        from .journal_ingest import main as journal_main
        return journal_main(argv)
    if argv and argv[0] in ("review-forensic-timeline", "verify-forensic-timeline"):
        from .forensic_timeline import main as forensic_main
        return forensic_main(argv)
    if argv and argv[0] in ("prepare-holdout", "freeze-holdout", "score-holdout", "verify-holdout"):
        from .holdout_protocol import main as holdout_main
        return holdout_main(argv)
    if argv and argv[0] == "doctor-owned-lab":
        from .native_doctor import main as doctor_main
        return doctor_main(argv[1:])
    if argv and argv[0] == "review-repository-boundary":
        from .repository_boundary import main as boundary_main
        return boundary_main(argv[1:])
    if argv and argv[0] in ("compare-owned-evm-engines", "verify-owned-evm-engines"):
        from .owned_cross_evm import main as cross_evm_main
        return cross_evm_main(argv)
    if argv and argv[0] in ("score-owned-evm", "verify-owned-evm-score"):
        from .owned_mutation_evaluation import main as mutation_score_main
        return mutation_score_main(argv)
    if argv and argv[0] in ("run-owned-access-lab", "verify-owned-access-lab"):
        from .evm_access_family import main as access_main
        return access_main(argv)
    if argv and argv[0] in ("run-owned-pause-lab", "verify-owned-pause-lab"):
        from .evm_pause_family import main as pause_main
        return pause_main(argv)
    if argv and argv[0] in ("study-owned-evm", "verify-owned-evm-study"):
        from .evm_seed_study import main as study_main
        return study_main(argv)
    if argv and argv[0] in ("compare-owned-evm", "verify-owned-evm-comparison"):
        from .evm_guidance_benchmark import main as comparison_main
        return comparison_main(argv)
    if argv and argv[0] in ("guide-owned-evm", "verify-guided-evm"):
        from .evm_coverage_guidance import main as guided_main
        return guided_main(argv)
    if argv and argv[0] in ("review-opcode-traces", "verify-opcode-traces"):
        from .evm_opcode_trace import main as opcode_main
        return opcode_main(argv)
    if argv and argv[0] in ("review-evm-feedback", "verify-evm-feedback"):
        from .evm_feedback import main as feedback_main
        return feedback_main(argv)
    if argv and argv[0] in ("fuzz-owned-evm", "replay-owned-evm"):
        from .evm_sequence_fuzz import main as fuzz_evm_main
        return fuzz_evm_main(argv)
    if argv and argv[0] in ("review-compiler-variants", "replay-compiler-variants"):
        from .compiler_variants import main as variants_main
        return variants_main(argv)
    if argv and argv[0] in ("review-native-platform", "verify-native-platform"):
        from .native_platform import main as native_platform_main
        return native_platform_main(argv)
    if argv and argv[0] in ("run-evm-accounting", "replay-evm-accounting"):
        from .evm_accounting import main as effects_main
        return effects_main(argv)
    if argv and argv[0] in ("run-evm-state-controls", "replay-evm-state-controls"):
        from .evm_execution import main as evm_main
        return evm_main(argv)
    if argv and argv[0] in ("build-stateful-bytecode", "replay-stateful-bytecode"):
        from .bytecode_controls import main as bytecode_main
        return bytecode_main(argv)
    if argv and argv[0] in ("prove-stateful-controls", "replay-stateful-controls"):
        from .solidity_stateful import main as stateful_main
        return stateful_main(argv)
    if argv and argv[0] in ("prove-solidity-controls", "replay-solidity-controls"):
        from .solidity_formal import main as formal_main
        return formal_main(argv)
    if argv and argv[0] in ("review-native-layout", "verify-native-layout"):
        from .native_layout import main as native_layout_main
        return native_layout_main(argv)
    if argv and argv[0] in ("inspect-solc", "compile-solidity", "replay-compilation"):
        from .native_compile import main as native_compile_main
        return native_compile_main(argv)
    if argv and argv[0] in ("review-compiler-layout", "verify-compiler-layout"):
        from .compiler_layout import main as compiler_layout_main
        return compiler_layout_main(argv)
    if argv and argv[0] in ("review-layout", "verify-layout"):
        from .storage_layout import main as layout_main
        return layout_main(argv)
    if argv and argv[0] in ("replay-ledger", "verify-ledger-replay"):
        from .ledger_sequence import main as sequence_main
        return sequence_main(argv)
    if argv and argv[0] in ("review-case", "verify-case"):
        from .case_review import main as case_main
        return case_main(argv)
    if argv and argv[0] in ("benchmark-permissions", "verify-permission-benchmark"):
        from .benchmark_controls import main as controls_main
        return controls_main(argv)
    if argv and argv[0] in ("evaluate-benchmark", "verify-benchmark"):
        from .benchmark import main as benchmark_main
        return benchmark_main(argv)
    if argv and argv[0] in ("seal-evidence", "verify-custody"):
        from .custody import main as custody_main
        return custody_main(argv)
    if argv and argv[0] in ("review-programs", "verify-programs"):
        from .program_registry import main as programs_main
        return programs_main(argv)
    if argv and argv[0] in ("audit-wiring", "verify-wiring"):
        from .source_graph import main as wiring_main
        return wiring_main(argv)
    if argv and argv[0] in ("check-permission-smt", "verify-permission-smt"):
        from .permission_smt import main as smt_main
        return smt_main(argv)
    if argv and argv[0] in ('reconcile-balances', 'verify-balances'):
        from .balance_reconciliation import main as accounting_main
        return accounting_main(argv)
    if argv and argv[0] in ("check-permission-domain", "verify-permission-domain"):
        from .permission_domain import main as domain_main
        return domain_main(argv)
    if argv and argv[0] in ("import-slither", "verify-slither"):
        from .static_review import main as static_main
        return static_main(argv)
    if argv == ["initiatives"]:
        from .research_plan import load_plan, render_plan
        print(render_plan(load_plan()))
        return 0
    if argv and argv[0] in ("audit-permissions", "verify-permissions"):
        from .permissions import main as permissions_main
        return permissions_main(argv)
    if argv and argv[0] in ("share-review", "verify-shared"):
        from .sharing import main as sharing_main
        return sharing_main(argv)
    if argv and argv[0] in ("review-platform", "verify-platform"):
        from .platform import main as platform_main
        return platform_main(argv)
    if argv and argv[0] in ("review", "verify-review"):
        from .review import main as review_main
        return review_main(argv)
    if argv and argv[0] in ("compare-checks", "verify-comparison"):
        from .regression import main as regression_main
        return regression_main(argv[1:], verify=argv[0] == "verify-comparison")
    if argv and argv[0] == "redact-log":
        from .privacy_cli import main as privacy_main
        return privacy_main(argv[1:])
    if argv and argv[0] in ("compare-owned-quota-engines", "verify-owned-quota-engines"):
        from .owned_quota_cross_evm import main as quota_cross_main
        return quota_cross_main(argv)
    if argv and argv[0] in ("check", "verify-check", "capabilities"):
        from .quality import main as quality_main
        return quality_main(argv)
    if argv and argv[0] in ("fuzz-lab", "verify-fuzz"):
        from .fuzz_cli import main as fuzz_main
        return fuzz_main(argv[1:], verify=argv[0] == "verify-fuzz")
    if argv and argv[0] in ("local-lab", "verify-lab"):
        from .lab_cli import main as lab_main
        return lab_main(argv[1:], verify=argv[0] == "verify-lab")
    mode = argv.pop(0) if argv and argv[0] in ("export-diablo", "import-nqc") else "legacy"
    parser = PrivateArgumentParser(description="Offline SUPERHUNTER evidence adapters")
    if mode == "export-diablo":
        parser.add_argument("finding", type=Path)
        parser.add_argument("context", type=Path)
        parser.add_argument("forge_output", type=Path)
    elif mode == "import-nqc":
        parser.add_argument("request", type=Path)
        parser.add_argument("response", type=Path)
        parser.add_argument("admission", type=Path)
    else:
        parser.add_argument("candidate", type=Path)
        parser.add_argument("reconstruction", type=Path)
        parser.add_argument("admission", type=Path)
    if mode != "export-diablo":
        parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path, help="NEW private output directory; never overwritten")
    args = parser.parse_args(argv)
    try:
        if mode == "export-diablo":
            request = export_diablo(load_json(args.finding), load_json(args.context),
                                   read_artifact(args.forge_output.parent, args.forge_output.name))
            write_new_bundle(args.out, {"candidate.json": canonical(request["candidate"]),
                                       "request.json": canonical(request)})
            print(json.dumps({"status": "EXPORTED_UNVERIFIED", "candidate_id": request["candidate"]["id"]}))
            return 0
        report_path = str(args.out / "review.md")
        if mode == "import-nqc":
            result = import_nqc(load_json(args.request), load_json(args.response), load_json(args.admission),
                                evidence_root=args.evidence_root, report_path=report_path)
        else:
            result = evaluate(load_json(args.candidate), load_json(args.reconstruction), load_json(args.admission),
                              evidence_root=args.evidence_root, report_path=report_path)
        result, privacy = redact_record(result)
        result["privacy"] = privacy
        files = {"decision.json": canonical(result)}
        if "diablo_feedback" in result:
            files["diablo-feedback.json"] = canonical(result["diablo_feedback"])
        if result["status"] == "REVIEW_REQUIRED":
            files["review.md"] = render_report(result["draft"]).encode()
        write_new_bundle(args.out, files)
        print(json.dumps({"status": result["status"], "execution_verified": False}))
        return 0 if result["status"] == "REVIEW_REQUIRED" else 1
    except (ContractError, OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        # No raw evidence, amounts, reports or keys printed to shared console logs.
        print(json.dumps({"status": "REJECTED", "error_type": type(exc).__name__, "error_code": "INVALID_CONTRACT_OR_ARTIFACT"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
