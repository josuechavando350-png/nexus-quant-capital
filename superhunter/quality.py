"""Executable QA gate for this package, not an autonomous security scanner.

Runs only the repository's own unit/regression suites through a fixed worker.
Module mappings are declared architecture, NOT inferred call graphs or coverage.
Receipts establish local consistency, not remote producer authentication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from .safe_io import canonical, read_artifact, strict_json, write_new_bundle
from .privacy import PrivateArgumentParser
from . import owned_process, qa_inputs

ROOT = Path(__file__).resolve().parent
COMPONENTS = {'accounting': {'files': ['balance_reconciliation.py'],
                'tests': ['test_balance_reconciliation.'],
                'depends': ['native', 'io', 'privacy']},
 'io': {'files': ['safe_io.py'], 'tests': ['test_integration.'], 'depends': []},
 'privacy': {'files': ['privacy.py', 'privacy_cli.py'], 'tests': ['test_privacy.'], 'depends': ['io']},
 'transport': {'files': ['bridge.py', 'integration.py'],
               'tests': ['test_bridge.', 'test_integration.'],
               'depends': ['io', 'privacy']},
 'native': {'files': ['native_runtime.py',
                      'native_sources/diablo/models.py',
                      'native_sources/diablo/audit.py',
                      'native_sources/diablo/scope.py', 'native_sources/diablo/ratelimit.py',
                      'native_sources/nqc/capacity.py'],
            'tests': ['test_local_lab.'],
            'depends': ['io']},
 'audit': {'files': ['audit_links.py', 'proof_graph.py'],
           'tests': ['test_audit_links.', 'test_proof_graph.'],
           'depends': ['io']},
 'lab': {'files': ['local_lab.py', 'lab_worker.py', 'lab_cli.py'],
         'tests': ['test_local_lab.', 'test_audit_links.'],
         'depends': ['native', 'audit', 'privacy']},
 'fuzz': {'files': ['fuzz_lab.py', 'fuzz_worker.py', 'fuzz_cli.py'],
          'tests': ['test_fuzz_lab.', 'test_fuzz_evidence.'],
          'depends': ['native', 'lab', 'audit', 'privacy']},
 'quality': {'files': ['quality.py', 'quality_worker.py'],
             'tests': ['test_quality.'],
             'depends': ['transport',
                         'lab',
                         'fuzz',
                         'privacy',
                         'permissions',
                         'static_review',
                         'research',
                         'permission_domain',
                         'accounting',
                         'source_graph',
                         'permission_smt']},
 'regression': {'files': ['regression.py'], 'tests': ['test_regression.'], 'depends': ['quality', 'privacy']},
 'context': {'files': ['project_context.py'], 'tests': ['test_reconciliation.'], 'depends': ['io']},
 'review': {'files': ['review.py'],
            'tests': ['test_review.'],
            'depends': ['quality', 'lab', 'fuzz', 'privacy', 'context']},
 'platform': {'files': ['platform.py'],
              'tests': ['test_platform.'],
              'depends': ['quality',
                          'lab',
                          'fuzz',
                          'privacy',
                          'review',
                          'regression',
                          'context',
                          'accounting',
                          'source_graph']},
 'sharing': {'files': ['sharing.py'], 'tests': ['test_sharing.'], 'depends': ['review', 'privacy']},
 'permission_domain': {'files': ['permission_domain.py'],
                       'tests': ['test_permission_domain.'],
                       'depends': ['permissions', 'native', 'io', 'privacy']},
 'permissions': {'files': ['permissions.py'],
                 'tests': ['test_permissions.'],
                 'depends': ['io', 'privacy', 'native']},
 'static_review': {'files': ['static_review.py'],
                   'tests': ['test_static_review.'],
                   'depends': ['io', 'privacy', 'native']},
 'research': {'files': ['research_plan.py'], 'tests': ['test_research_plan.'], 'depends': ['io']},
 'entrypoints': {'files': ['__init__.py', '__main__.py'],
                 'tests': ['test_integration.', 'test_local_lab.', 'test_fuzz_lab.'],
                 'depends': ['transport',
                             'lab',
                             'fuzz',
                             'quality',
                             'privacy',
                             'regression',
                             'review',
                             'platform',
                             'sharing',
                             'permissions',
                             'static_review',
                             'research',
                             'permission_domain',
                             'accounting',
                             'source_graph',
                             'permission_smt']},
 'source_graph': {'files': ['source_graph.py'], 'tests': ['test_source_graph.'], 'depends': ['io']},
 'permission_smt': {'files': ['permission_smt.py', 'smt_backend.py'],
                    'tests': ['test_permission_smt.', 'test_smt_backend.'],
                    'depends': ['permission_domain', 'permissions', 'native', 'io', 'privacy']}}
COMPONENTS['programs'] = {'files': ['program_registry.py'], 'tests': ['test_program_registry.'],
                          'depends': ['io', 'native', 'source_graph', 'transport']}
COMPONENTS['quality']['depends'].append('programs')
COMPONENTS['entrypoints']['depends'].append('programs')
COMPONENTS['rate_control'] = {'files': ['rate_control.py'], 'tests': ['test_rate_control.'],
                              'depends': ['native']}
COMPONENTS['lab']['depends'].append('rate_control')
COMPONENTS['native']['tests'].append('test_rate_control.')

REQUIRED_TESTS = ('test_bridge.BridgeTests.test_forge_wrong_target',
 'test_bridge.BridgeTests.test_nqc_unbound_economics',
 'test_integration.IntegrationTests.test_native_roundtrip_always_requires_review',
 'test_integration.IntegrationTests.test_cli_export_then_import',
 'test_integration.IntegrationTests.test_symlink_leaf_rejected',
 'test_local_lab.LocalLabTests.test_real_nqc_and_diablo_functions_are_called',
 'test_local_lab.LocalLabTests.test_cli_complete_run_and_verification',
 'test_audit_links.AuditLinkTests.test_input_hash_substitution_rejected_even_after_rehash',
 'test_proof_graph.CausalGraphTests.test_stored_bundle_receipt_catches_graph_reseal',
 'test_quality.QualityTests.test_skip_never_counts_as_pass',
 'test_quality.QualityTests.test_source_change_blocks_success',
 'test_fuzz_lab.FuzzLabTests.test_differential_64_cases',
 'test_fuzz_lab.FuzzLabTests.test_resealed_scope_decision_mismatch',
 'test_fuzz_lab.FuzzLabTests.test_cli_runs_bounded_fuzz_and_reverification',
 'test_fuzz_evidence.FuzzEvidenceTests.test_contradictory_completion_rejected_after_rehash',
 'test_fuzz_evidence.FuzzEvidenceTests.test_counts_require_integers',
 'test_privacy.PrivacyTests.test_cli_error_does_not_echo_unknown_fields',
 'test_privacy.PrivacyTests.test_cli_review_redacts_notes_without_changing_evidence',
 'test_privacy.PrivacyTests.test_fuzz_invalid_seed_is_not_echoed',
 'test_regression.RegressionTests.test_removed_test_never_counts_as_fix',
 'test_regression.RegressionTests.test_resealed_comparison_must_recompute',
 'test_review.ReviewTests.test_resealed_report_cannot_claim_production',
 'test_review.ReviewTests.test_missing_milestone_test_blocks_review',
 'test_platform.PlatformTests.test_all_original_ids_retained',
 'test_platform.PlatformTests.test_resealed_complete_claim_rejected',
 'test_platform.PlatformTests.test_input_change_after_review_rejected',
 'test_reconciliation.ReconciliationTests.test_checklists_share_status_and_evidence',
 'test_reconciliation.ReconciliationTests.test_public_diagnostics_hide_arguments',
 'test_sharing.SharingTests.test_private_artifacts_never_exported',
 'test_permissions.PermissionTests.test_known_bad_policy_fails',
 'test_permissions.PermissionTests.test_reference_disagreement_blocks_result',
 'test_static_review.StaticReviewTests.test_bundle_roundtrip',
 'test_static_review.StaticReviewTests.test_byte_range_mismatch_rejected',
 'test_research_plan.ResearchPlanTests.test_all_25_preserved',
 'test_permission_domain.DomainTests.test_budget_never_counts_as_verified',
 'test_permission_domain.DomainTests.test_enumerates_entire_four_configuration_domain',
 'test_permission_domain.DomainTests.test_resealed_false_approval_rejected',
 'test_balance_reconciliation.AccountingTests.test_one_atomic_unit_is_not_rounded_away',
 'test_balance_reconciliation.AccountingTests.test_incomplete_even_when_all_residuals_zero',
 'test_balance_reconciliation.AccountingTests.test_disagreement_blocks_evidence',
 'test_source_graph.SourceGraphTests.test_removed_module_detected',
 'test_source_graph.SourceGraphTests.test_no_analyzed_code_is_executed',
 'test_source_graph.SourceGraphTests.test_resealed_runtime_claim_rejected',
 'test_permission_smt.PermissionSMTTests.test_corrected_model_proved_with_full_enumeration',
 'test_permission_smt.PermissionSMTTests.test_real_resource_exhaustion_never_proves',
 'test_permission_smt.PermissionSMTTests.test_resealed_false_approval_rejected',
 'test_smt_backend.NativeSMTTests.test_native_sat_unsat_and_model')
REQUIRED_TESTS += (
    'test_program_registry.ProgramRegistryTests.test_twenty_programs_eight_platforms_without_cross_authorization',
    'test_program_registry.ProgramRegistryTests.test_changed_rules_invalidate_previous_approval',
    'test_program_registry.ProgramRegistryTests.test_verifier_rechecks_expiry_at_current_time',
    'test_program_registry.ProgramRegistryTests.test_candidate_adapter_checks_repo_and_all_contracts',
)
COMPONENTS['custody'] = {'files': ['custody.py'], 'tests': ['test_custody.'],
                         'depends': ['io', 'native', 'privacy']}
COMPONENTS['quality']['depends'].append('custody')
COMPONENTS['entrypoints']['depends'].append('custody')
REQUIRED_TESTS += (
    'test_custody.CustodyTests.test_rfc8032_known_vector_matches_real_crypto',
    'test_custody.CustodyTests.test_untrusted_valid_signer_rejected',
    'test_custody.CustodyTests.test_rehashed_modified_evidence_still_fails_signature_binding',
    'test_custody.CustodyTests.test_real_native_lab_bundle_can_be_sealed',
)
COMPONENTS['benchmark'] = {'files': ['benchmark.py', 'benchmark_controls.py'], 'tests': ['test_benchmark.'],
                           'depends': ['io', 'native', 'privacy', 'permissions']}
COMPONENTS['quality']['depends'].append('benchmark')
COMPONENTS['platform']['depends'].append('benchmark')
COMPONENTS['entrypoints']['depends'].append('benchmark')
REQUIRED_TESTS += (
    'test_benchmark.BenchmarkTests.test_missing_result_never_improves_recall',
    'test_benchmark.BenchmarkTests.test_abstention_remains_in_operational_recall',
    'test_benchmark.BenchmarkTests.test_resealed_metrics_rejected',
)
REQUIRED_TESTS += (
    'test_rate_control.RateControlTests.test_native_factory_resolves_original_dependency',
    'test_rate_control.RateControlTests.test_invalid_tokens_cannot_increase_available_credit',
    'test_rate_control.RateControlTests.test_solver_not_called_when_gate_defers',
)
COMPONENTS['case_review'] = {'files': ['case_review.py'], 'tests': ['test_case_review.'],
                            'depends': ['transport', 'programs', 'static_review', 'accounting', 'custody', 'privacy']}
COMPONENTS['quality']['depends'].append('case_review')
COMPONENTS['entrypoints']['depends'].append('case_review')
REQUIRED_TESTS += (
    'test_case_review.CaseReviewTests.test_individually_valid_foreign_static_commit_cannot_join',
    'test_case_review.CaseReviewTests.test_missing_contract_from_request_set_rejected',
    'test_case_review.CaseReviewTests.test_expired_scope_does_not_survive_bundle_verification',
    'test_case_review.CaseReviewTests.test_cli_two_real_processes',
)

COMPONENTS['ledger_sequence'] = {'files': ['ledger_sequence.py'], 'tests': ['test_ledger_sequence.'],
                                  'depends': ['accounting', 'native', 'io', 'privacy']}
for _component in ('quality', 'platform', 'entrypoints'):
    COMPONENTS[_component]['depends'].append('ledger_sequence')
REQUIRED_TESTS += (
    'test_ledger_sequence.LedgerSequenceTests.test_equal_totals_do_not_prove_possible_prefix',
    'test_ledger_sequence.LedgerSequenceTests.test_budget_does_not_certify_unseen_suffix',
    'test_ledger_sequence.LedgerSequenceTests.test_resealed_result_cannot_claim_success',
)
COMPONENTS['case_review']['tests'].append('test_ordered_case.')
COMPONENTS['case_review']['depends'].append('ledger_sequence')
REQUIRED_TESTS += (
    'test_ordered_case.OrderedCaseTests.test_equal_totals_wrong_order_blocks_v2_not_v1',
    'test_ordered_case.OrderedCaseTests.test_all_four_verifiers_really_called',
    'test_ordered_case.OrderedCaseTests.test_external_context_prevents_profile_downgrade',
    'test_ordered_case.OrderedCaseTests.test_foreign_valid_ledger_is_rejected',
)
COMPONENTS['storage_layout'] = {'files': ['storage_layout.py'], 'tests': ['test_storage_layout.'],
                                 'depends': ['native', 'io', 'privacy']}
COMPONENTS['quality']['depends'].append('storage_layout')
COMPONENTS['entrypoints']['depends'].append('storage_layout')
REQUIRED_TESTS += (
    'test_storage_layout.StorageLayoutTests.test_reordered_variables_not_hidden_by_same_total_size',
    'test_storage_layout.StorageLayoutTests.test_gap_consumption_not_automatically_approved',
    'test_storage_layout.StorageLayoutTests.test_resealed_approval_cannot_replace_result',
    'test_storage_layout.StorageLayoutTests.test_cli_roundtrip_separate_processes',
)

COMPONENTS['compiler_layout'] = {'files': ['compiler_layout.py', 'source_types.py'], 'tests': ['test_compiler_layout.', 'test_source_types.'],
                                    'depends': ['storage_layout', 'native', 'io', 'privacy']}
COMPONENTS['quality']['depends'].append('compiler_layout')
COMPONENTS['entrypoints']['depends'].append('compiler_layout')
REQUIRED_TESTS += (
    'test_compiler_layout.CompilerLayoutTests.test_actual_layout_analyzer_is_called',
    'test_compiler_layout.CompilerLayoutTests.test_omitted_state_variable_rejected',
    'test_compiler_layout.CompilerLayoutTests.test_error_json_cannot_be_used_as_success',
    'test_compiler_layout.CompilerLayoutTests.test_foreign_row_contract_rejected_even_if_wrapper_matches',
    'test_compiler_layout.CompilerLayoutTests.test_cli_create_verify_in_separate_processes',
    'test_source_types.TypedBindingTests.test_v1_missing_type_check_reproduced_and_v2_rejects',
    'test_source_types.TypedBindingTests.test_partial_type_span_cannot_hide_real_width',
    'test_source_types.TypedBindingTests.test_unsupported_shape_cannot_be_marked_preserved',
    'test_source_types.TypedBindingTests.test_external_reference_prevents_profile_downgrade',
)

COMPONENTS['solidity_stateful'] = {'files': ['solidity_stateful.py'],
    'tests': ['test_solidity_stateful.'], 'depends': ['native_compile', 'permission_smt', 'native', 'io', 'privacy']}
COMPONENTS['quality']['depends'].append('solidity_stateful')
COMPONENTS['entrypoints']['depends'].append('solidity_stateful')
REQUIRED_TESTS += (
    'test_solidity_stateful.StatefulTests.test_delayed_error_requires_third_step',
    'test_solidity_stateful.StatefulTests.test_unknown_cannot_become_safe',
    'test_solidity_stateful.StatefulTests.test_resealed_result_rejected',
)

COMPONENTS['bytecode_controls'] = {'files': ['bytecode_controls.py'],
    'tests': ['test_bytecode_controls.'], 'depends': ['solidity_stateful', 'native_compile', 'native', 'io', 'privacy']}
COMPONENTS['quality']['depends'].append('bytecode_controls')
COMPONENTS['entrypoints']['depends'].append('bytecode_controls')
REQUIRED_TESTS += (
    'test_bytecode_controls.BytecodeTests.test_formal_source_substitution_rejected',
    'test_bytecode_controls.BytecodeTests.test_source_property_not_promoted_to_bytecode_proof',
    'test_bytecode_controls.BytecodeTests.test_resealed_evm_claim_rejected',
)
FILES = {'receipt.json', 'quality.json', 'source-snapshot.json', 'CHECKLIST.md', 'tests.log'}


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


PORTFOLIO_DATA_FILES = (
    'repo_portfolio_50.json', 'repo_portfolio/01-vulnerabilities.json',
    'repo_portfolio/02-dfir.json', 'repo_portfolio/03-performance.json',
    'repo_portfolio/04-algorithms.json', 'repo_portfolio/05-operations.json')


def source_snapshot(root: Path = ROOT) -> dict[str, str]:
    """Capture executable package/test bytes and policy inputs; reject symlinks."""
    result = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d != '__pycache__')
        for name in dirs:
            if (Path(base)/name).is_symlink():
                raise ValueError('source directory symlink rejected')
        for name in sorted(files):
            rel = (Path(base)/name).relative_to(root).as_posix()
            if name.endswith('.py') or rel in PORTFOLIO_DATA_FILES or rel in ('tests/fixtures/compiler_variant_capture.json', 'tests/fixtures/evm_accounting_capture.json', 'tests/fixtures/evm_accounting_capture_io_v2.json', 'tests/fixtures/evm_state_capture.json', 'tests/fixtures/bytecode_native_capture.json', 'tests/fixtures/stateful_native_capture.json', 'capabilities.json', 'integration-checklist.json', 'integration_milestones.json', 'reconciliation-origins.json', 'requirements-local-lab.txt', 'requirements-custody.txt', 'requirements-owned-cross-evm.txt', 'requirements-owned-spec-evm.txt', 'requirements-otel-qa.txt', 'requirements-owned-slither.txt', 'research_initiatives.json'):
                result[rel] = sha(read_artifact(root, rel))
                if len(result) > 500:
                    raise ValueError('source inventory limit exceeded')
    if not result:
        raise ValueError('empty source inventory')
    return dict(sorted(result.items()))


def validate_components(snapshot: dict, components: dict = COMPONENTS) -> list[str]:
    errors, owners = [], {}
    for name, item in components.items():
        if not item['files'] or not item['tests']:
            errors.append(f'{name}: empty component definition')
        for path in item['files']:
            if path not in snapshot:
                errors.append(f'{name}: missing source {path}')
            if path in owners:
                errors.append(f'{name}: source assigned twice {path}')
            owners[path] = name
        if any(dep not in components for dep in item['depends']):
            errors.append(f'{name}: unknown dependency')
    for path in snapshot:
        if path.endswith('.py') and not path.startswith('tests/') and path not in owners:
            errors.append(f'unmapped runtime source: {path}')
    visiting, done = set(), set()

    def walk(name):
        if name in visiting:
            raise ValueError('component dependency cycle')
        if name in done:
            return
        visiting.add(name)
        for dep in components[name]['depends']:
            if dep in components:
                walk(dep)
        visiting.remove(name); done.add(name)
    try:
        for name in components:
            walk(name)
    except ValueError as exc:
        errors.append(str(exc))
    return errors


def catalog(root: Path = ROOT) -> dict:
    data = strict_json(read_artifact(root, 'capabilities.json'))
    if type(data.get('schema_version')) is not int or data['schema_version'] != 1:
        raise ValueError('unsupported capability catalog')
    items = data.get('items')
    if (type(items) is not list or len(items) != 50 or
            any(type(x) is not dict or type(x.get('id')) is not int for x in items) or
            [x['id'] for x in items] != list(range(1,51))):
        raise ValueError('catalog must preserve all 50 ordered unique IDs')
    for item in items:
        if set(item) != {'id', 'title', 'status', 'scope', 'components'}:
            raise ValueError('capability fields mismatch')
        if item['status'] not in ('PLANNED', 'PARTIAL', 'REDESIGN_REQUIRED'):
            raise ValueError('no capability may be certified complete by this catalog')
        if any(type(item[k]) is not str or not item[k].strip() for k in ('title', 'scope')):
            raise ValueError('capability title/scope missing')
        refs = item['components']
        if (type(refs) is not list or any(type(ref) is not str or ref not in COMPONENTS for ref in refs) or
                len(set(refs)) != len(refs)):
            raise ValueError('unknown or duplicate capability component')
        if (item['status'] == 'PARTIAL') != bool(refs):
            raise ValueError('partial capability requires actual components; planned capabilities cannot borrow proof')
    return data


def _assign_component_rows(rows: list[dict], components: dict) -> tuple[dict, bool]:
    """Route rows once; preserve startswith semantics, order and shared owners.

    Prefixes containing a dot can only match that same first identifier part.
    Broad prefixes (including an empty one) stay in a fallback list. This index
    exists only for this call and never caches evidence, source bytes or a PASS.
    """
    assigned = {name: [] for name in components}
    by_module, broad = {}, []
    for name, component in components.items():
        for prefix in component['tests']:
            module, separator, _ = prefix.partition('.')
            bucket = by_module.setdefault(module, []) if separator else broad
            bucket.append((name, prefix))
    unmapped = False
    for row in rows:
        identifier = row['id']
        candidates = by_module.get(identifier.partition('.')[0], ())
        matched = set()
        for owner, prefix in (*candidates, *broad):
            if owner not in matched and identifier.startswith(prefix):
                assigned[owner].append(row)
                matched.add(owner)
        unmapped |= not matched
    return assigned, unmapped


def assess(receipt: dict, snapshot: dict) -> dict:
    """Recompute the gate; a claimed PASS in the receipt is never trusted."""
    receipt = expand_partition_receipt(receipt, snapshot)
    errors = validate_components(snapshot)
    if 'partition_receipts' in receipt or 'execution_mode' in receipt:
        try:
            rebuilt = aggregate_receipts(receipt.get('partition_receipts'), snapshot)
            if canonical(rebuilt) != canonical(receipt):
                errors.append('aggregate differs from worker receipts')
        except (ValueError, KeyError, TypeError):
            errors.append('invalid worker partition evidence')
    if receipt.get('schema_version') != 1 or type(receipt.get('schema_version')) is not int:
        errors.append('invalid receipt schema')
    if receipt.get('sources_before') != snapshot or receipt.get('sources_after') != snapshot:
        errors.append('source changed, missing or stale')
    rows, expected = receipt.get('tests'), receipt.get('discovered')
    if type(rows) is not list or not rows or type(expected) is not list or not expected:
        raise ValueError('nonempty discovered tests and results required')
    if any(type(row) is not dict or set(row) != {'id', 'outcome'} or
           type(row['id']) is not str or type(row['outcome']) is not str for row in rows):
        raise ValueError('malformed per-test record')
    ids = [row['id'] for row in rows]
    id_set = set(ids)
    if (any(type(x) is not str for x in expected) or len(ids) != len(id_set) or
            len(expected) != len(set(expected)) or sorted(ids) != sorted(expected)):
        errors.append('test identities are duplicate, missing or unexpected')
    if type(receipt.get('tests_run')) is not int or receipt['tests_run'] != len(rows):
        errors.append('test count mismatch')
    if any(row['outcome'] != 'PASS' for row in rows):
        errors.append('at least one test failed, errored, skipped or was incomplete')
    for key in ('failures', 'errors', 'skipped', 'expected_failures', 'unexpected_successes'):
        if type(receipt.get(key)) is not int or receipt[key] != 0:
            errors.append(f'{key} not zero')
    for required in REQUIRED_TESTS:
        if required not in id_set:
            errors.append('missing mandatory test: ' + required)
    checks = {}
    assignments, unmapped = _assign_component_rows(rows, COMPONENTS)
    for name, component in COMPONENTS.items():
        assigned = assignments[name]
        checks[name] = {'status': 'TESTS_PASSED_LOCAL' if assigned and all(r['outcome']=='PASS' for r in assigned) else 'BLOCKED',
                        'test_count': len(assigned), 'depends_on': component['depends'], 'files': component['files']}
        if not assigned:
            errors.append(name + ': no execution evidence')
    if unmapped:
        errors.append('unmapped test suite')
    if errors:
        for check in checks.values():
            check['status'] = 'BLOCKED'
    return {'schema_version': 1, 'status': 'LOCAL_QA_PASS' if not errors else 'LOCAL_QA_BLOCKED',
            'source_digest': sha(canonical(snapshot)), 'tests_run': len(rows), 'components': checks,
            'reasons': errors, 'vulnerability_confirmed': False, 'production_certified': False}


def checklist(data: dict, result: dict | None = None) -> str:
    lines = ['# SUPERHUNTER — estado de las 50 capacidades', '',
             'Las pruebas del paquete no demuestran detección de vulnerabilidades ni completan estas capacidades.',
             '○ Pendiente · ◐ Parcial · ↻ Requiere reformulación defensiva. Ninguna está certificada completa.', '']
    if result:
        lines += [f"Comprobación local: {result['status']}; pruebas: {result['tests_run']}; código: `{result['source_digest']}`.", '']
    for item in data['items']:
        mark = {'PLANNED': '○', 'PARTIAL': '◐', 'REDESIGN_REQUIRED': '↻'}[item['status']]
        lines += [f"{mark} **{item['id']}. {item['title']}** — {item['scope']}", '']
    return '\n'.join(lines)


def verify_bundle(root: Path) -> dict:
    marker = strict_json(read_artifact(root, 'COMPLETE.json'))
    if (type(marker.get('schema_version')) is not int or marker['schema_version'] != 1 or
            type(marker.get('sha256')) is not dict or set(marker['sha256']) != FILES):
        raise ValueError('QA bundle manifest mismatch')
    values = {}
    for name, expected in marker['sha256'].items():
        raw = read_artifact(root, name)
        if sha(raw) != expected:
            raise ValueError('QA artifact digest mismatch')
        values[name] = raw
    snapshot = source_snapshot()
    if strict_json(values['source-snapshot.json']) != snapshot:
        raise ValueError('QA source snapshot is not the current package')
    result = assess(strict_json(values['receipt.json']), snapshot)
    if canonical(result) != values['quality.json']:
        raise ValueError('QA claimed verdict differs from recomputed verdict')
    if checklist(catalog(), result).encode() != values['CHECKLIST.md']:
        raise ValueError('capability checklist not bound to current catalog/verdict')
    return result



PARTITION_COUNT = 8

# When the suite passed 1,800 tests, the old QA receipt hit the fixed 2MB
# artifact ceiling. Do not increase global IO limits or omit test evidence.
# Store one hash for each original worker receipt, keeping common immutable
# source/global-inventory fields only once in the outer receipt. Verification
# expands and checks every original worker commitment before re-assessment.
PARTITION_COMMON = frozenset({'sources_before', 'sources_after', 'global_discovered'})
PARTITION_FORMAT = 'common-fields-with-worker-hashes-v1'


def compact_partition_receipt(receipt: dict) -> dict:
    if type(receipt) is not dict or type(receipt.get('partition_receipts')) is not list:
        raise ValueError('full worker receipt required for compact encoding')
    import copy
    result = copy.deepcopy(receipt)
    reduced = []
    for worker in result['partition_receipts']:
        if type(worker) is not dict or not PARTITION_COMMON <= set(worker):
            raise ValueError('worker missing required common fields')
        common = {k:worker[k] for k in PARTITION_COMMON}
        if (common['sources_before'] != receipt['sources_before'] or
                common['sources_after'] != receipt['sources_after'] or
                common['global_discovered'] != receipt['discovered']):
            raise ValueError('worker common fields disagree with aggregate')
        reduced.append({k:v for k,v in worker.items() if k not in PARTITION_COMMON} |
                       {'worker_sha256':sha(canonical(worker))})
    result['partition_receipts'] = reduced
    result['partition_receipts_format'] = PARTITION_FORMAT
    return result


def expand_partition_receipt(receipt: dict, snapshot: dict) -> dict:
    """Restore all original worker receipts and validate SHA of each full form.

    Old uncompressed receipts are still accepted for existing evidence bundles.
    Compact form is never trusted without reconstruction and exact comparison.
    """
    if type(receipt) is not dict or 'partition_receipts_format' not in receipt:
        return receipt
    if (receipt['partition_receipts_format'] != PARTITION_FORMAT or
            type(receipt.get('partition_receipts')) is not list or
            len(receipt['partition_receipts']) != PARTITION_COUNT or
            type(receipt.get('discovered')) is not list):
        raise ValueError('invalid compact QA receipt')
    import copy
    full = copy.deepcopy(receipt)
    restored = []
    for row in full['partition_receipts']:
        if (type(row) is not dict or 'worker_sha256' not in row or
                any(k in row for k in PARTITION_COMMON)):
            raise ValueError('invalid compact worker fields')
        expected = row.pop('worker_sha256')
        if type(expected) is not str or len(expected) != 64:
            raise ValueError('invalid worker receipt commitment')
        rebuilt = row | {'sources_before':snapshot, 'sources_after':snapshot,
                         'global_discovered':receipt['discovered']}
        if sha(canonical(rebuilt)) != expected:
            raise ValueError('worker receipt commitment mismatch')
        restored.append(rebuilt)
    full['partition_receipts'] = restored
    del full['partition_receipts_format']
    return full


def aggregate_receipts(receipts: list[dict], snapshot: dict) -> dict:
    """Require every exact partition against one shared source/test inventory."""
    from .quality_worker import partition_ids
    if type(receipts) is not list or len(receipts) != PARTITION_COUNT:
        raise ValueError('missing worker partition')
    ordered = {}
    counters = ('failures', 'errors', 'skipped', 'expected_failures', 'unexpected_successes')
    expected_fields = {'schema_version','sources_before','sources_after','discovered','tests',
                       'tests_run','python','log_privacy','global_discovered',
                       'partition_count','partition_index'} | set(counters)
    for receipt in receipts:
        if type(receipt) is not dict or set(receipt) != expected_fields:
            raise ValueError('worker receipt fields mismatch')
        index = receipt['partition_index']
        if (type(index) is not int or not 0 <= index < PARTITION_COUNT or index in ordered or
                type(receipt['partition_count']) is not int or receipt['partition_count'] != PARTITION_COUNT or
                type(receipt['schema_version']) is not int or receipt['schema_version'] != 1):
            raise ValueError('duplicate or invalid worker partition')
        if receipt['sources_before'] != snapshot or receipt['sources_after'] != snapshot:
            raise ValueError('worker source identity mismatch')
        ordered[index] = receipt
    all_ids = ordered[0]['global_discovered']
    groups = partition_ids(all_ids, PARTITION_COUNT)
    rows = []
    for index, receipt in sorted(ordered.items()):
        if receipt['global_discovered'] != all_ids or receipt['python'] != ordered[0]['python']:
            raise ValueError('worker inventory/runtime mismatch')
        if receipt['discovered'] != groups[index]:
            raise ValueError('worker partition inventory mismatch')
        tests = receipt['tests']
        if (type(tests) is not list or any(type(r) is not dict or set(r) != {'id','outcome'} or
                type(r['id']) is not str or r['outcome'] not in
                ('PASS','FAIL','ERROR','SKIP','INCOMPLETE','EXPECTED_FAILURE','UNEXPECTED_SUCCESS')
                for r in tests)):
            raise ValueError('worker test result schema mismatch')
        if sorted(r['id'] for r in tests) != groups[index]:
            raise ValueError('worker omitted or duplicated test')
        if type(receipt['tests_run']) is not int or receipt['tests_run'] != len(tests):
            raise ValueError('worker count mismatch')
        if any(type(receipt[k]) is not int or receipt[k] < 0 for k in counters):
            raise ValueError('worker counter must be a nonnegative integer')
        rows.extend(tests)
    return {
        'schema_version':1, 'execution_mode':f'{PARTITION_COUNT}-exact-worker-partitions',
        'sources_before':snapshot, 'sources_after':snapshot,
        'discovered':sorted(all_ids), 'tests':sorted(rows, key=lambda r:r['id']),
        'tests_run':len(rows), 'python':ordered[0]['python'],
        **{k:sum(r[k] for r in ordered.values()) for k in counters},
        'partition_receipts':[ordered[i] for i in range(PARTITION_COUNT)],
    }


def _run_qa_process(command: list[str], *, cwd: Path, env: dict, timeout: int):
    """Stop the fixed worker's session group before reaping its leader.

    This does not contain descendants that detach into another process group.
    Worker receipts/logs are explicit files; arbitrary console output is discarded.
    """
    return owned_process.run(command, cwd=cwd, env=env, timeout=timeout,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _worker_command(work: Path, index: int, cache: Path) -> list[str]:
    """Start the fixed QA worker with a new cache namespace, never an old pyc."""
    if type(index) is not int or not 0 <= index < PARTITION_COUNT:
        raise ValueError('invalid QA worker partition')
    cache.mkdir(mode=0o700, exist_ok=False)
    return [sys.executable, '-I', '-B', '-X', f'pycache_prefix={cache}',
            str(ROOT/'quality_worker.py'), str(work),
            '--partition-count',str(PARTITION_COUNT),'--partition-index',str(index)]


def run_check(out: Path) -> dict:
    if out.exists() or out.is_symlink():
        raise FileExistsError('QA requires a new private output directory')
    with qa_inputs.oversized_zero_input() as large_input:
        return _run_check(out, large_input)


def _run_check(out: Path, large_input: Path) -> dict:
    snapshot = source_snapshot()
    data = catalog()
    if validate_components(snapshot):
        raise ValueError('; '.join(validate_components(snapshot)))
    from .quality_worker import batch_succeeded
    from .qa_failure import FailureCapture
    capture = FailureCapture(out,snapshot)
    with tempfile.TemporaryDirectory(prefix='superhunter-qa-') as temp:
        active_work = None
        stage = 'worker_execution'
        try:
            receipts, logs, exits = [], [], []
            for index in range(PARTITION_COUNT):
                work = Path(temp)/f'worker-{index}'
                active_work = work
                stage = 'worker_execution'
                command = _worker_command(work,index,Path(temp)/f'cache-{index}')
                proc = _run_qa_process(command,
                                      cwd=ROOT.parent, env={'LANG':'C.UTF-8','LC_ALL':'C.UTF-8',
                                                           qa_inputs.ENV:str(large_input)},
                                      timeout=180)
                capture.record(index,proc.returncode,work)
                stage = 'worker_validation'
                if proc.returncode not in (0,1):
                    raise RuntimeError(f'QA worker infrastructure failure ({proc.returncode})')
                raw_receipt, raw_log = read_artifact(work,'receipt.json'), read_artifact(work,'tests.log')
                marker = strict_json(read_artifact(work,'COMPLETE.json'))
                if (type(marker.get('schema_version')) is not int or marker['schema_version'] != 1 or
                        marker.get('sha256') != {'receipt.json':sha(raw_receipt),'tests.log':sha(raw_log)}):
                    raise ValueError('worker artifact manifest mismatch')
                receipt = strict_json(raw_receipt)
                if receipt.get('partition_index') != index or source_snapshot() != snapshot:
                    raise ValueError('source or worker partition changed during QA')
                if (proc.returncode == 0) != batch_succeeded(receipt):
                    raise ValueError('worker exit/verdict mismatch')
                receipts.append(receipt); exits.append(proc.returncode)
                logs.append(f'=== FIXED QA PARTITION {index+1}/{PARTITION_COUNT} ===\n'.encode()+raw_log)
            stage = 'aggregate'
            receipt = aggregate_receipts(receipts, snapshot)
            result = assess(receipt, snapshot)
            if (all(code == 0 for code in exits)) != (result['status']=='LOCAL_QA_PASS'):
                raise ValueError('aggregate exit/verdict mismatch')
            if source_snapshot() != snapshot:
                raise ValueError('source changed during QA run')
            compact = compact_partition_receipt(receipt)
            if len(canonical(compact)) > 2_000_000:
                raise ValueError('compact QA receipt still exceeds artifact budget')
            write_new_bundle(out, {'receipt.json':canonical(compact), 'quality.json':canonical(result),
                                  'source-snapshot.json':canonical(snapshot), 'CHECKLIST.md':checklist(data,result).encode(),
                                  'tests.log':b'\n'.join(logs)})
            stage = 'bundle_validation'
            return verify_bundle(out)
        except (ValueError,OSError,RuntimeError,subprocess.TimeoutExpired,KeyError,TypeError) as error:
            if active_work is not None:
                capture.record(index,None,active_work)
            capture.save(stage,error)
            raise

def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Verify this package, never scan external targets')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('check').add_argument('--out', type=Path, required=True)
    sub.add_parser('verify-check').add_argument('--bundle', type=Path, required=True)
    sub.add_parser('capabilities')
    args = parser.parse_args(argv)
    try:
        if args.command == 'capabilities':
            print(checklist(catalog()))
            return 0
        result = run_check(args.out) if args.command=='check' else verify_bundle(args.bundle)
        print(json.dumps({k: result[k] for k in ('status','source_digest','tests_run','vulnerability_confirmed')}))
        return 0 if result['status']=='LOCAL_QA_PASS' else 1
    except (ValueError,OSError,RuntimeError,subprocess.TimeoutExpired,KeyError,TypeError) as exc:
        print(json.dumps({'status':'LOCAL_QA_ERROR','error_type':type(exc).__name__}))
        return 2



# Storage placement adds an independent local constraint, not compiler execution.
COMPONENTS['quality']['files'].append('qa_inputs.py')
COMPONENTS['source_types'] = {'files': ['source_types.py'], 'tests': ['test_source_types.'], 'depends': ['io']}
COMPONENTS['compiler_layout']['files'] = ['compiler_layout.py']
COMPONENTS['compiler_layout']['depends'].append('source_types')
COMPONENTS['storage_placement'] = {
    'files': ['storage_placement.py'], 'tests': ['test_storage_placement.'],
    'depends': ['source_types', 'io']}
COMPONENTS['compiler_layout']['depends'].append('storage_placement')
REQUIRED_TESTS += (
    'test_storage_placement.PlacementBindingTests.test_coherent_wrong_origin_passes_v2_but_v3_rejects',
    'test_storage_placement.PlacementBindingTests.test_custom_base_requires_review',
    'test_storage_placement.PlacementMathTests.test_reference_does_not_call_primary',
)


# Source-level inventory is a separate bounded check, not compiler execution.
COMPONENTS['solidity_inventory'] = {'files':['solidity_inventory.py'], 'tests':['test_solidity_inventory.'],
                                    'depends':['source_types','io']}
COMPONENTS['compiler_layout']['depends'].append('solidity_inventory')
COMPONENTS['quality']['depends'].append('solidity_inventory')
REQUIRED_TESTS += (
    'test_solidity_inventory.InventoryBindingTests.test_shared_omission_passes_v3_but_is_rejected_v4',
    'test_solidity_inventory.InventoryBindingTests.test_mutable_cannot_masquerade_as_constant',
    'test_solidity_inventory.InventoryBindingTests.test_manifest_downgrade_rejected',
)

# Executable driver is registered; passing its tests does not mean solc is installed.
COMPONENTS['native_compile'] = {
    'files':['native_compile.py','solc_worker.py'], 'tests':['test_native_compile.'],
    'depends':['compiler_layout','native','io','privacy']}
COMPONENTS['quality']['depends'].append('native_compile')
COMPONENTS['entrypoints']['depends'].append('native_compile')
REQUIRED_TESTS += (
    'test_native_compile.NativeCompileTests.test_missing_binary_blocks_without_output',
    'test_native_compile.NativeCompileTests.test_wrong_binary_never_executed',
    'test_native_compile.NativeCompileTests.test_exit_zero_with_errors_not_compilation_success',
)

COMPONENTS['native_layout'] = {
    'files':['native_layout.py'], 'tests':['test_native_layout.'],
    'depends':['native_compile','compiler_layout','native','io','privacy']}
COMPONENTS['quality']['depends'].append('native_layout')
COMPONENTS['entrypoints']['depends'].append('native_layout')
REQUIRED_TESTS += (
    'test_native_layout.NativeLayoutTests.test_missing_binary_blocks_without_output',
    'test_native_layout.NativeLayoutTests.test_both_native_replays_are_required',
    'test_native_layout.NativeLayoutTests.test_replay_disagreement_prevents_review',
)

# Multi-seed study using fixed owned-control EVM traces, not a live target scanner.
COMPONENTS['evm_seed_study'] = {
    'files': ['evm_seed_study.py'], 'tests': ['test_evm_seed_study.'],
    'depends': ['evm_guidance_benchmark','evm_coverage_guidance','evm_opcode_trace',
                'evm_sequence_fuzz','evm_execution','native_compile','accounting','native','io','privacy']}
COMPONENTS['entrypoints']['depends'].append('evm_seed_study')
REQUIRED_TESTS += (
    'test_evm_seed_study.SeedStudyTests.test_seed_changes_full_recipe_not_parity_only',
    'test_evm_seed_study.SeedStudyTests.test_both_arms_use_exact_recipe_and_budget',
    'test_evm_seed_study.SeedStudyTests.test_resealed_superiority_claim_rejected',
)



COMPONENTS['solidity_formal'] = {
    'files': ['solidity_formal.py'], 'tests': ['test_solidity_formal.'],
    'depends': ['native_compile', 'permission_smt', 'native', 'io', 'privacy']}
COMPONENTS['quality']['depends'].append('solidity_formal')
COMPONENTS['entrypoints']['depends'].append('solidity_formal')
REQUIRED_TESTS += (
    'test_solidity_formal.SolidityFormalTests.test_unsat_without_feasible_inputs_is_not_certification',
    'test_solidity_formal.SolidityFormalTests.test_real_z3_resource_exhaustion_is_unknown',
    'test_solidity_formal.SolidityFormalTests.test_resealed_favorable_result_rejected',
)

# Actual EVM runtime evidence is obtained with the native command, not unit mocks.
COMPONENTS['evm_execution'] = {'files': ['evm_execution.py', 'evm_worker.py'],
    'tests': ['test_evm_execution.'], 'depends': ['bytecode_controls', 'native_compile', 'native', 'io', 'privacy']}
COMPONENTS['quality']['depends'].append('evm_execution')
COMPONENTS['entrypoints']['depends'].append('evm_execution')
REQUIRED_TESTS += (
    'test_evm_execution.EVMTests.test_assertion_revert_does_not_commit_tentative_credit',
    'test_evm_execution.EVMTests.test_gas_budget_bound_in_genesis_not_only_cli',
    'test_evm_execution.EVMTests.test_resealed_favorable_result_rejected',
    'test_evm_execution.EVMTests.test_replay_never_executes_bundle_inputs',
)

COMPONENTS['evm_accounting'] = {'files': ['evm_accounting.py'], 'tests': ['test_evm_accounting.'],
    'depends': ['evm_execution', 'accounting', 'native', 'io', 'privacy']}
COMPONENTS['accounting']['tests'].append('test_internal_units.')
COMPONENTS['quality']['depends'].append('evm_accounting')
COMPONENTS['entrypoints']['depends'].append('evm_accounting')
REQUIRED_TESTS += (
    'test_evm_accounting.CommittedEffectsTests.test_reverts_contribute_no_transfers',
    'test_evm_accounting.CommittedEffectsTests.test_replay_regenerates_instead_of_executing_bundle',
    'test_internal_units.InternalUnitTests.test_offsetting_residuals_do_not_hide_mismatch',
)


# The joint native profile consumes QA; quality must not depend back on it.
COMPONENTS['native_platform'] = {
    'files': ['native_platform.py'], 'tests': ['test_native_platform.'],
    'depends': ['platform', 'evm_accounting', 'quality', 'native', 'io', 'privacy', 'review']}
COMPONENTS['entrypoints']['depends'].append('native_platform')
REQUIRED_TESTS += (
    'test_native_platform.NativePlatformTests.test_native_failure_cannot_emit_success',
    'test_native_platform.NativePlatformTests.test_replay_is_mandatory_even_after_creation',
    'test_native_platform.NativePlatformTests.test_wrong_qa_source_rejected_before_native_replay',
)

# This module consumes native QA; do not add a dependency cycle back from quality.
COMPONENTS['compiler_variants'] = {
    'files': ['compiler_variants.py'], 'tests': ['test_compiler_variants.'],
    'depends': ['native_platform', 'evm_execution', 'bytecode_controls', 'native_compile',
                'evm_accounting', 'accounting', 'quality', 'native', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('compiler_variants')
REQUIRED_TESTS += (
    'test_compiler_variants.CompilerVariantTests.test_committed_states_and_reverts_agree',
    'test_compiler_variants.CompilerVariantTests.test_changed_source_cannot_pose_as_another_optimization',
    'test_compiler_variants.CompilerVariantTests.test_replay_never_executes_supplied_variant_input',
)

# Bounded EVM mutation experiment over owned arithmetic controls. It calls the
# real pinned compiler/EVM at CLI acceptance, never external program targets.
COMPONENTS['evm_sequence_fuzz'] = {
    'files': ['evm_sequence_fuzz.py'], 'tests': ['test_evm_sequence_fuzz.'],
    'depends': ['compiler_variants', 'evm_execution', 'accounting', 'native', 'io', 'privacy', 'quality']}
COMPONENTS['entrypoints']['depends'].append('evm_sequence_fuzz')
REQUIRED_TESTS += (
    'test_evm_sequence_fuzz.EVMSequenceFuzzTests.test_first_corpus_reaches_third_step',
    'test_evm_sequence_fuzz.EVMSequenceFuzzTests.test_oracle_crosschecks_existing_reference',
    'test_evm_sequence_fuzz.EVMSequenceFuzzTests.test_compiler_and_native_disagreement_rejected',
    'test_evm_sequence_fuzz.EVMSequenceFuzzTests.test_resealed_favorable_bundle_rejected',
)

# EVM-observable feedback is derived only after a complete native replay.
# Not EVM instruction/branch coverage or an exploit-finding certificate.
COMPONENTS['evm_feedback'] = {
    'files': ['evm_feedback.py'], 'tests': ['test_evm_feedback.'],
    'depends': ['evm_sequence_fuzz', 'evm_execution', 'native', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('evm_feedback')
REQUIRED_TESTS += (
    'test_evm_feedback.EVMFeedbackTests.test_greedy_selection_retains_every_observed_feature',
    'test_evm_feedback.EVMFeedbackTests.test_assertion_prefix_is_observed_and_reverted',
    'test_evm_feedback.EVMFeedbackTests.test_resealed_false_coverage_claim_rejected',
)

# This is an observational Geth tracer; it does not assert full path coverage.
COMPONENTS['evm_opcode_trace'] = {
    'files': ['evm_opcode_trace.py', 'evm_trace_worker.py'],
    'tests': ['test_evm_opcode_trace.'],
    'depends': ['evm_feedback', 'evm_sequence_fuzz', 'evm_execution', 'io', 'native', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('evm_opcode_trace')
REQUIRED_TESTS += (
    'test_evm_opcode_trace.OpcodeTraceTests.test_push_immediate_cannot_count_as_instruction',
    'test_evm_opcode_trace.OpcodeTraceTests.test_branch_outcomes_distinguished',
    'test_evm_opcode_trace.OpcodeTraceTests.test_resealed_false_coverage_rejected',
)

# Closed-loop mutation on fixed own-contract EVM, using PC/JUMPI novelty.
# No scan of external programs, no claim of coverage completeness.
COMPONENTS['evm_coverage_guidance'] = {
    'files': ['evm_coverage_guidance.py'], 'tests': ['test_evm_coverage_guidance.'],
    'depends': ['evm_opcode_trace', 'evm_sequence_fuzz', 'evm_execution',
                'accounting', 'native', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('evm_coverage_guidance')
REQUIRED_TESTS += (
    'test_evm_coverage_guidance.GuidanceTests.test_bounded_mutations',
    'test_evm_coverage_guidance.GuidanceTests.test_parent_selection_uses_trace_novelty',
    'test_evm_coverage_guidance.GuidanceTests.test_resealed_result_cannot_pass_replay',
)

# Matched-budget, fixed-owned-code EVM comparison. Nothing uses external targets.
COMPONENTS['evm_guidance_benchmark'] = {
    'files': ['evm_guidance_benchmark.py'], 'tests': ['test_evm_guidance_benchmark.'],
    'depends': ['evm_coverage_guidance', 'evm_opcode_trace', 'evm_sequence_fuzz',
                'evm_execution', 'native_compile', 'accounting', 'native', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('evm_guidance_benchmark')
REQUIRED_TESTS += (
    'test_evm_guidance_benchmark.GuidanceBenchmarkTests.test_shared_baseline_and_budget',
    'test_evm_guidance_benchmark.GuidanceBenchmarkTests.test_fixed_parent_ignores_feedback',
    'test_evm_guidance_benchmark.GuidanceBenchmarkTests.test_resealed_favorable_claim_rejected',
)

# Mandatory QA evidence-packing controls; never drop a test to fit artifact limits.
REQUIRED_TESTS += (
    'test_quality.CompactReceiptTests.test_roundtrip_preserves_full_worker_evidence',
    'test_quality.CompactReceiptTests.test_worker_outcome_tamper_is_rejected_even_when_outer_report_rehashed',
    'test_quality.CompactReceiptTests.test_source_change_invalidates_every_worker_commitment',
)


# New fixed, owned EVM regression family: actual pause semantics vs a known mutant.
# A matched fixture is not a new vulnerability or a blind benchmark.
COMPONENTS['evm_pause_family'] = {
    'files':['evm_pause_family.py'], 'tests':['test_evm_pause_family.'],
    'depends':['evm_execution','native_compile','native','io','privacy']}
COMPONENTS['entrypoints']['depends'].append('evm_pause_family')
REQUIRED_TESTS += (
    'test_evm_pause_family.PauseFamilyTests.test_guard_rejects_paused_release',
    'test_evm_pause_family.PauseFamilyTests.test_mutant_commits_forbidden_release_in_reference',
    'test_evm_pause_family.PauseFamilyTests.test_native_replay_rejects_resealed_false_verdict',
)


# Closed two-caller authorization regression: admin and guest are synthetic fixed identities.
COMPONENTS['evm_access_family'] = {
    'files':['evm_access_family.py','evm_access_runner.py','evm_access_worker.py'], 'tests':['test_evm_access_family.'],
    'depends':['evm_execution','native_compile','native','io','privacy']}
COMPONENTS['entrypoints']['depends'].append('evm_access_family')
REQUIRED_TESTS += (
    'test_evm_access_family.AccessFamilyTests.test_guest_blocked_with_guard',
    'test_evm_access_family.AccessFamilyTests.test_mutant_guest_commits_known_effect',
    'test_evm_access_family.AccessFamilyTests.test_forged_report_rejected_with_replay',
)


# Replay-scored known owned EVM mutation controls, not a blind benchmark.
# The same case is compiled twice but contributes ONE labelled observation.
COMPONENTS['owned_mutation_evaluation'] = {
    'files': ['owned_mutation_evaluation.py'],
    'tests': ['test_owned_mutation_evaluation.'],
    'depends': ['evm_pause_family', 'evm_access_family', 'benchmark', 'quality',
                'native', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('owned_mutation_evaluation')
REQUIRED_TESTS += (
    'test_owned_mutation_evaluation.KnownMutationScoreTests.test_four_cases_not_eight',
    'test_owned_mutation_evaluation.KnownMutationScoreTests.test_observed_effect_independent_from_truth_labels',
    'test_owned_mutation_evaluation.KnownMutationScoreTests.test_resealed_favorable_report_rejected',
)

# Separated label commitment/freeze/reveal, offline only. Benchmarks are not
# blinded unless an external custodian independently enforces secrecy/order.
COMPONENTS['holdout_protocol'] = {
    'files': ['holdout_protocol.py'], 'tests': ['test_holdout_protocol.'],
    'depends': ['benchmark', 'io', 'native', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('holdout_protocol')
REQUIRED_TESTS += (
    'test_holdout_protocol.HoldoutTests.test_public_and_submission_contain_no_truth_labels',
    'test_holdout_protocol.HoldoutTests.test_external_frozen_pin_blocks_resealed_falsification',
    'test_holdout_protocol.HoldoutTests.test_withheld_labels_change_requires_new_commitment',
)

# Normalized DFIR evidence/order gate, standalone and non-intrusive.
COMPONENTS['forensic_timeline'] = {
    'files': ['forensic_timeline.py'], 'tests': ['test_forensic_timeline.'],
    'depends': ['io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('forensic_timeline')
REQUIRED_TESTS += (
    'test_forensic_timeline.TimelineTests.test_cli_end_to_end_and_replay',
    'test_forensic_timeline.TimelineTests.test_resealed_false_result_rejected',
    'test_forensic_timeline.TimelineTests.test_cycle_and_temporal_inversion_not_pass',
    'test_forensic_timeline.TimelineTests.test_symlink_input_rejected',
)

# Bounded real parser for pre-existing journalctl JSONL exports. Raw source is
# preserved privately; reconstructed evidence is cross-checked on replay.
COMPONENTS['journal_ingest'] = {
    'files': ['journal_ingest.py'], 'tests': ['test_journal_ingest.'],
    'depends': ['forensic_timeline', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('journal_ingest')
REQUIRED_TESTS += (
    'test_journal_ingest.JournalTests.test_cli_roundtrip_separate_processes',
    'test_journal_ingest.JournalTests.test_resealed_false_timeline_rejected',
    'test_journal_ingest.JournalTests.test_line_offsets_and_original_bytes',
    'test_journal_ingest.JournalTests.test_duplicates_and_invalid_timestamps_rejected',
)


# Replay-verified multi-source journal correlation, hypotheses still UNPROVEN.
COMPONENTS['journal_correlation'] = {
    'files': ['journal_correlation.py'], 'tests': ['test_journal_correlation.'],
    'depends': ['journal_ingest', 'forensic_timeline', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('journal_correlation')
REQUIRED_TESTS += (
    'test_journal_correlation.CorrelationTests.test_cli_two_source_replay',
    'test_journal_correlation.CorrelationTests.test_temporal_contradiction_and_cycle',
    'test_journal_correlation.CorrelationTests.test_resealed_false_result_rejected',
    'test_journal_correlation.CorrelationTests.test_source_tamper_rejected_before_ingestion',
    'test_journal_correlation.CorrelationTests.test_historical_worker_partition_ids_remain_stable',
)


# Offline Geth trace and replay-verified journal event, byte-bound only.
COMPONENTS['evm_forensic_binding'] = {
    'files': ['evm_forensic_binding.py'], 'tests': ['test_evm_forensic_binding.'],
    'depends': ['evm_opcode_trace', 'journal_ingest', 'forensic_timeline',
                'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('evm_forensic_binding')
REQUIRED_TESTS += (
    'test_evm_forensic_binding.EVMForensicBindingTests.test_cli_separate_processes',
    'test_evm_forensic_binding.EVMForensicBindingTests.test_anchor_mismatch_rejected',
    'test_evm_forensic_binding.EVMForensicBindingTests.test_resealed_false_result_rejected',
    'test_evm_forensic_binding.EVMForensicBindingTests.test_invalid_trace_terminal_rejected',
)


# Second, independently implemented EVM stack/PC interpreter for owned traces.
# Only a closed, stateless opcode subset is admitted: no native Geth execution.
COMPONENTS['evm_bounded_replay'] = {
    'files': ['evm_bounded_replay.py'], 'tests': ['test_evm_bounded_replay.'],
    'depends': ['evm_forensic_binding', 'evm_opcode_trace', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('evm_bounded_replay')
REQUIRED_TESTS += (
    'test_evm_bounded_replay.BoundedReplayTests.test_cli_separate_processes',
    'test_evm_bounded_replay.BoundedReplayTests.test_fake_taken_branch_rejected',
    'test_evm_bounded_replay.BoundedReplayTests.test_resealed_false_semantic_verdict_rejected',
    'test_evm_bounded_replay.BoundedReplayTests.test_unsupported_opcode_refused',
)


# Evidence-bound offline chain research triage; source bundles are independently
# replay-verified and impact remains entirely HYPOTHETICAL.
COMPONENTS['critical_chain'] = {
    'files': ['critical_chain.py'], 'tests': ['test_critical_chain.'],
    'depends': ['forensic_timeline', 'journal_correlation', 'evm_bounded_replay',
                'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('critical_chain')
REQUIRED_TESTS += (
    'test_critical_chain.CriticalChainTests.test_cli_review_and_verify_separate_processes',
    'test_critical_chain.CriticalChainTests.test_low_medium_chain_can_be_critical_research_without_critical_verdict',
    'test_critical_chain.CriticalChainTests.test_cycle_rejected_not_scored',
    'test_critical_chain.CriticalChainTests.test_resealed_false_critical_verdict_rejected',
    'test_critical_chain.CriticalChainTests.test_external_source_changed_rejected',
    'test_critical_chain.CriticalChainTests.test_evm_replay_object_sha_binding_to_real_replay',
)

# Independent offline proof-obligation audit for directed critical-chain hypotheses.
COMPONENTS['chain_path_audit'] = {
    'files': ['chain_path_audit.py'], 'tests': ['test_chain_path_audit.'],
    'depends': ['critical_chain', 'forensic_timeline', 'journal_correlation',
                'evm_bounded_replay', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('chain_path_audit')
REQUIRED_TESTS += (
    'test_chain_path_audit.ChainPathAuditTests.test_cli_two_independent_processes_private_stdout',
    'test_chain_path_audit.ChainPathAuditTests.test_longest_path_reports_unverified_link_without_false_critical',
    'test_chain_path_audit.ChainPathAuditTests.test_branch_not_misrepresented_as_one_end_to_end_chain',
    'test_chain_path_audit.ChainPathAuditTests.test_false_severity_claim_rejected_even_when_rehashed',
    'test_chain_path_audit.ChainPathAuditTests.test_external_source_change_invalidates_replay',
    'test_chain_path_audit.ChainPathAuditTests.test_current_source_identity_prevents_false_replay',
)


# Counterfactual loss-of-source experiments on existing private chain evidence.
COMPONENTS['evidence_ablation'] = {
    'files': ['evidence_ablation.py'], 'tests': ['test_evidence_ablation.'],
    'depends': ['chain_path_audit', 'critical_chain', 'forensic_timeline',
                'journal_correlation', 'evm_bounded_replay', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('evidence_ablation')
REQUIRED_TESTS += (
    'test_evidence_ablation.EvidenceAblationTests.test_cli_replay_independent_process',
    'test_evidence_ablation.EvidenceAblationTests.test_shared_source_failure_and_cover',
    'test_evidence_ablation.EvidenceAblationTests.test_resealed_fake_critical_claim_rejected',
    'test_evidence_ablation.EvidenceAblationTests.test_changed_original_source_rejected',
    'test_evidence_ablation.EvidenceAblationTests.test_exact_cover_oracle_500',
)


# Alias-aware common-bundle evidence failure analysis (no producer attestation).
COMPONENTS['evidence_common_mode'] = {
    'files': ['evidence_common_mode.py'], 'tests': ['test_evidence_common_mode.'],
    'depends': ['evidence_ablation', 'chain_path_audit', 'critical_chain',
                'forensic_timeline', 'journal_correlation', 'evm_bounded_replay',
                'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('evidence_common_mode')
REQUIRED_TESTS += (
    'test_evidence_common_mode.CommonEvidenceTests.test_identical_bundle_aliases_not_fake_independence',
    'test_evidence_common_mode.CommonEvidenceTests.test_cli_independent_replay',
    'test_evidence_common_mode.CommonEvidenceTests.test_resealed_false_diversity_rejected',
    'test_evidence_common_mode.CommonEvidenceTests.test_upstream_original_change_rejected',
)


# Exact minimal offline loss sets of already-verified evidence bundles.
COMPONENTS['evidence_cut_sets'] = {
    'files': ['evidence_cut_sets.py'], 'tests': ['test_evidence_cut_sets.'],
    'depends': ['evidence_common_mode', 'evidence_ablation', 'chain_path_audit',
                'critical_chain', 'forensic_timeline', 'journal_correlation',
                'evm_bounded_replay', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('evidence_cut_sets')
REQUIRED_TESTS += (
    'test_evidence_cut_sets.EvidenceCutSetTests.test_real_verified_bundle_replay',
    'test_evidence_cut_sets.EvidenceCutSetTests.test_exact_cut_oracle_600',
    'test_evidence_cut_sets.EvidenceCutSetTests.test_cli_processes_and_privacy',
    'test_evidence_cut_sets.EvidenceCutSetTests.test_resealed_false_cut_rejected',
    'test_evidence_cut_sets.EvidenceCutSetTests.test_changed_original_invalidates_review',
)


# Bounded higher-order common-bundle source-failure research, offline only.
COMPONENTS['evidence_joint_failure'] = {
    'files': ['evidence_joint_failure.py'], 'tests': ['test_evidence_joint_failure.'],
    'depends': ['evidence_common_mode', 'evidence_ablation',
                'chain_path_audit', 'critical_chain', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('evidence_joint_failure')
REQUIRED_TESTS += (
    'test_evidence_joint_failure.JointEvidenceTests.test_alias_group_is_one_failure_unit',
    'test_evidence_joint_failure.JointEvidenceTests.test_joint_minimal_cut_requires_two_distinct_bundle_hashes',
    'test_evidence_joint_failure.JointEvidenceTests.test_order_one_explicitly_not_exhaustive',
    'test_evidence_joint_failure.JointEvidenceTests.test_cli_review_and_verify_in_separate_processes',
    'test_evidence_joint_failure.JointEvidenceTests.test_forged_critical_impact_rejected_even_when_resealed',
    'test_evidence_joint_failure.JointEvidenceTests.test_edited_original_source_rejected',
)

# Partition stability is part of the mandatory QA contract.
REQUIRED_TESTS += (
    'test_quality.StableWorkerLayoutTests.test_existing_assignments_survive_module_growth',
    'test_quality.StableWorkerLayoutTests.test_new_module_does_not_relocate_existing_tests',
    'test_quality.StableWorkerLayoutTests.test_platform_has_separate_budget_from_evm_studies',
    'test_quality.StableWorkerLayoutTests.test_full_inventory_retained_once_with_eight_workers',
)

# Optional second EVM: unit checks are separate from native acceptance runs.
COMPONENTS['owned_cross_evm'] = {
    'files': ['owned_cross_evm.py', 'owned_cross_evm_worker.py',
              'owned_cross_evm_pins.py', 'requirements-owned-cross-evm.txt'],
    'tests': ['test_owned_cross_evm.'],
    'depends': ['owned_mutation_evaluation', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('owned_cross_evm')
REQUIRED_TESTS += (
    'test_owned_cross_evm.CrossEVMTests.test_matching_known_cases_not_extra_samples',
    'test_owned_cross_evm.CrossEVMTests.test_any_single_call_change_rejected',
    'test_owned_cross_evm.CrossEVMTests.test_resealed_result_cannot_claim_success',
    'test_owned_cross_evm.CrossEVMTests.test_modified_dependency_same_version_rejected',
    'test_owned_cross_evm.CrossEVMTests.test_fresh_cache_uses_verified_source_not_stale_bytecode',
)

# Structural source boundary review; does not recertify historical NQC.
COMPONENTS['repository_boundary'] = {
    'files': ['repository_boundary.py'], 'tests': ['test_repository_boundary.'],
    'depends': ['io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('repository_boundary')
REQUIRED_TESTS += (
    'test_repository_boundary.RepositoryBoundaryTests.test_extended_repository_preserves_legacy_without_recertifying',
    'test_repository_boundary.RepositoryBoundaryTests.test_original_verifier_cannot_be_silently_replaced',
    'test_repository_boundary.RepositoryBoundaryTests.test_active_workflow_rejected_at_root_and_nested',
    'test_repository_boundary.RepositoryBoundaryTests.test_concurrent_source_change_rejected',
)

COMPONENTS['native_doctor'] = {
    'files': ['native_doctor.py'], 'tests': ['test_native_doctor.'],
    'depends': ['owned_cross_evm', 'native_compile', 'evm_execution', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('native_doctor')
REQUIRED_TESTS += (
    'test_native_doctor.NativeDoctorTests.test_ready_is_not_execution_or_certification',
    'test_native_doctor.NativeDoctorTests.test_missing_optional_engine_preserves_other_profiles',
    'test_native_doctor.NativeDoctorTests.test_z3_bytes_checked_without_loading_library',
    'test_native_doctor.NativeDoctorTests.test_wrong_native_tools_do_not_execute',
)

COMPONENTS['owned_spec_evm'] = {
    'files': ['owned_spec_evm_worker.py','owned_spec_evm_pins.py','requirements-owned-spec-evm.txt'],
    'tests': ['test_owned_spec_evm.'],
    'depends': ['evm_pause_family','evm_access_family','native_compile','io','privacy']}
COMPONENTS['owned_cross_evm']['depends'].append('owned_spec_evm')
REQUIRED_TESTS += (
    'test_owned_spec_evm.SpecEVMTests.test_fixed_eels_cases_are_not_extra_samples',
    'test_owned_spec_evm.SpecEVMTests.test_wrong_selected_engine_rejected_before_execution',
    'test_owned_spec_evm.SpecEVMTests.test_installed_dependency_bytes_are_checked',
    'test_owned_spec_evm.SpecEVMTests.test_selected_profile_does_not_require_other_environment',
)

COMPONENTS['owned_quota_review'] = {
    'files': ['owned_quota_cases.py','owned_quota_review.py','owned_quota_worker.py',
              'owned_quota_execution.py','owned_quota_evm_worker.py'],
    'tests': ['test_owned_quota_review.'],
    'depends': ['benchmark','evm_execution','native_compile','io','privacy']}
COMPONENTS['entrypoints']['depends'].append('owned_quota_review')
REQUIRED_TESTS += (
    'test_owned_quota_review.QuotaReviewTests.test_six_known_cases_are_not_228_samples',
    'test_owned_quota_review.QuotaReviewTests.test_ablations_measure_real_omissions',
    'test_owned_quota_review.QuotaReviewTests.test_failing_detector_is_scored_not_promoted_to_pass',
    'test_owned_quota_review.QuotaReviewTests.test_verifier_reexecutes_and_rejects_resealed_false_score',
    'test_owned_quota_review.QuotaReviewTests.test_wrong_source_blocks_before_tools',
    'test_owned_quota_review.QuotaReviewTests.test_geth_worker_does_not_raise_inherited_two_gib_limit',
    'test_owned_quota_review.QuotaReviewTests.test_sealed_image_reuse_checks_bytes_and_does_not_close_caller_fd',
)

COMPONENTS['qa_failure'] = {'files':['qa_failure.py'],'tests':['test_qa_failure.'],
                            'depends':['io','privacy']}
COMPONENTS['quality']['depends'].append('qa_failure')
COMPONENTS['entrypoints']['depends'].append('qa_failure')
REQUIRED_TESTS += (
    'test_qa_failure.FailureEvidenceTests.test_setup_class_failure_keeps_unobserved_test_ids',
    'test_qa_failure.FailureEvidenceTests.test_real_orchestrator_preserves_timeout_without_success',
    'test_qa_failure.FailureEvidenceTests.test_resealed_pass_or_fewer_missing_tests_rejected',
)

COMPONENTS['quality']['tests'].append('test_quality_cache.')
REQUIRED_TESTS += (
    'test_quality_cache.QualityCacheTests.test_timestamp_cache_cannot_replace_verified_source',
    'test_quality_cache.QualityCacheTests.test_unchecked_hash_cache_cannot_replace_verified_source',
    'test_quality_cache.QualityCacheTests.test_real_orchestrator_selects_private_cache_and_cleans_on_timeout',
)

COMPONENTS['owned_quota_cross_evm'] = {
    'files':['owned_quota_cross_evm.py','owned_quota_spec_worker.py'],
    'tests':['test_owned_quota_cross_evm.'],
    'depends':['owned_quota_review','owned_cross_evm','owned_spec_evm']}
COMPONENTS['entrypoints']['depends'].append('owned_quota_cross_evm')
REQUIRED_TESTS += (
    'test_owned_quota_cross_evm.QuotaCrossEVMTests.test_each_changed_call_rejected',
    'test_owned_quota_cross_evm.QuotaCrossEVMTests.test_resealed_false_report_fails_regeneration',
    'test_owned_quota_cross_evm.QuotaCrossEVMTests.test_six_cases_not_twelve_or_456_independent_samples',
)

COMPONENTS['quality']['tests'].append('test_quality_process.')
REQUIRED_TESTS += (
    'test_quality_process.QualityProcessTests.test_timeout_stops_own_same_group_child',
    'test_quality_process.QualityProcessTests.test_success_also_stops_own_remaining_child',
    'test_quality_process.QualityProcessTests.test_failed_group_cleanup_cannot_report_success',
)

COMPONENTS['owned_platform'] = {
    'files': ['owned_platform.py'], 'tests': ['test_owned_platform.'],
    'depends': ['native_platform', 'native_doctor', 'owned_quota_cross_evm', 'platform', 'io']}
COMPONENTS['entrypoints']['depends'].append('owned_platform')
REQUIRED_TESTS += (
    'test_owned_platform.OwnedPlatformTests.test_completion_and_verification_require_native_replay',
    'test_owned_platform.OwnedPlatformTests.test_wrong_qa_packages_block_before_output',
    'test_owned_platform.OwnedPlatformTests.test_resealed_false_final_claim_rejected',
    'test_owned_platform.OwnedPlatformTests.test_changed_preparation_during_copy_rejected',
    'test_owned_platform.OwnedPlatformTests.test_failed_native_replay_leaves_no_final_marker',
)

COMPONENTS['owned_process'] = {
    'files': ['owned_process.py'], 'tests': ['test_owned_process.'], 'depends': []}
for _component in ('quality', 'owned_quota_review', 'owned_quota_cross_evm'):
    COMPONENTS[_component]['depends'].append('owned_process')
REQUIRED_TESTS += (
    'test_owned_process.OwnedProcessTests.test_leader_is_waitable_during_group_cleanup_then_reaped',
    'test_owned_process.OwnedProcessTests.test_timeout_stops_owned_group_before_reaping',
    'test_owned_process.OwnedProcessTests.test_lost_child_ownership_never_signals_numeric_group',
    'test_owned_process.OwnedProcessTests.test_native_timeout_preserves_typed_diagnostic',
    'test_owned_process.OwnedProcessTests.test_eels_normal_exit_cleans_own_child',
    'test_owned_process.OwnedProcessTests.test_late_observed_exit_does_not_bypass_deadline',
)

COMPONENTS['owned_authority'] = {
    'files': ['owned_authority_model.py', 'owned_authority_cases.py',
              'owned_authority_reference.py', 'owned_authority_review.py'],
    'tests': ['test_owned_authority.'], 'depends': ['benchmark', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('owned_authority')
REQUIRED_TESTS += (
    'test_owned_authority.AuthorityReviewTests.test_latent_defect_remains_an_explicit_omission',
    'test_owned_authority.AuthorityReviewTests.test_clean_and_latent_cases_are_observationally_identical',
    'test_owned_authority.AuthorityReviewTests.test_issued_snapshot_ablation_creates_false_positives',
    'test_owned_authority.AuthorityReviewTests.test_reference_disagreement_blocks_instead_of_inventing_a_verdict',
    'test_owned_authority.AuthorityReviewTests.test_rehashed_omission_removal_is_rejected_after_reexecution',
)

COMPONENTS['owned_authority_evm'] = {
    'files': ['owned_authority_evm_cases.py', 'owned_authority_geth.py',
              'owned_authority_evm_worker.py', 'owned_authority_spec_worker.py',
              'owned_authority_cross_evm.py'],
    'tests': ['test_owned_authority_evm.'],
    'depends': ['owned_authority', 'owned_quota_review', 'owned_quota_cross_evm', 'owned_process']}
COMPONENTS['entrypoints']['depends'].append('owned_authority_evm')
REQUIRED_TESTS += (
    'test_owned_authority_evm.AuthorityEVMTests.test_known_cases_keep_the_latent_omission',
    'test_owned_authority_evm.AuthorityEVMTests.test_vm_success_is_not_application_authorization',
    'test_owned_authority_evm.AuthorityEVMTests.test_engine_agreement_does_not_replace_python_model_comparison',
    'test_owned_authority_evm.AuthorityEVMTests.test_probe_that_changes_any_state_field_is_rejected',
    'test_owned_authority_evm.AuthorityEVMTests.test_marker_byte_change_during_replay_is_rejected',
)


# Optional OpenTelemetry profiling is instrumented ONLY for local owned QA.
# No OTLP exporter, collector endpoint, network permission or scanning is added.
COMPONENTS['otel_qa'] = {
    'files': ['otel_qa.py', 'otel_qa_schema.py', 'otel_dependency_integrity.py', 'otel_dependency_pins.py'],
    'tests': ['test_otel_qa.', 'test_otel_dependency_integrity.', 'test_otel_qa_schema.'],
    'depends': ['quality', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('otel_qa')
REQUIRED_TESTS += (
    'test_otel_qa_schema.TelemetrySchemaTests.test_resealed_private_error_rejected',
    'test_otel_qa_schema.TelemetrySDKPrivacyTests.test_private_exception_name_and_message_not_serialized',
    'test_otel_qa_schema.TelemetrySDKPrivacyTests.test_resource_environment_not_recorded',
    'test_otel_qa.OfflineOpenTelemetryTests.test_metadata_check_and_no_remote_operation',
    'test_otel_qa.OfflineOpenTelemetryTests.test_real_sdk_captures_qa_and_verifier_in_memory',
    'test_otel_qa.OfflineOpenTelemetryTests.test_verifier_exception_is_failure_not_pass',
    'test_otel_qa.OfflineOpenTelemetryTests.test_fail_open_resealed_failure_cannot_claim_pass',
    'test_otel_qa.OfflineOpenTelemetryTests.test_resealed_dependency_identity_change_is_rejected',
    'test_otel_qa.OfflineOpenTelemetryTests.test_legacy_v1_remains_unpinned_without_silent_promotion',
    'test_otel_qa.OfflineOpenTelemetryTests.test_dependency_change_after_qa_prevents_completion_marker',
    'test_otel_dependency_integrity.DependencyIntegrityTests.test_modified_runtime_bytes_rejected_with_unchanged_metadata',
    'test_otel_dependency_integrity.DependencyIntegrityTests.test_unrecorded_native_shadow_rejected',
    'test_otel_dependency_integrity.DependencyIntegrityTests.test_changed_files_during_review_rejected',
)


# Fixed OWNED Slither integration is executable only after local scanner/tool
# admission succeeds. It never accepts arbitrary targets or runs scans by QA.
COMPONENTS['slither_owned_runner'] = {
    'files': ['slither_owned_runner.py', 'slither_owned_worker.py'],
    'tests': ['test_slither_owned_runner.'],
    'depends': ['static_review', 'native_compile', 'owned_process', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('slither_owned_runner')
REQUIRED_TESTS += (
    'test_slither_owned_runner.SlitherOwnedTests.test_tool_launch_has_only_fixed_source_and_flags',
    'test_slither_owned_runner.SlitherOwnedTests.test_changed_owned_source_rejected',
    'test_slither_owned_runner.SlitherOwnedTests.test_process_failure_does_not_import',
    'test_slither_owned_runner.SlitherOwnedTests.test_direct_worker_rejects_non_fixture',
    'test_slither_owned_runner.SlitherOwnedTests.test_worker_rejects_oversized_source_and_compiler_before_exec',
)

# Differential Slither gate: controlled positive AND clean fixture are both
# mandatory before an OWNED experiment can be recorded as accepted.
COMPONENTS['slither_control_pair'] = {
    'files': ['slither_control_pair.py'],
    'tests': ['test_slither_control_pair.'],
    'depends': ['slither_owned_runner', 'static_review', 'native_compile', 'owned_process', 'io']}
COMPONENTS['entrypoints']['depends'].append('slither_control_pair')
REQUIRED_TESTS += (
    'test_slither_control_pair.SlitherPairTests.test_fixed_clean_source_differs_only_in_authorization',
    'test_slither_control_pair.SlitherPairTests.test_clean_control_must_have_no_false_positive',
    'test_slither_control_pair.SlitherPairTests.test_cross_source_and_boolean_counts_fail_closed',
    'test_slither_control_pair.SlitherPairTests.test_pair_verification_rejects_resealed_false_summary',
    'test_slither_control_pair.SlitherPairTests.test_missing_tool_blocks_before_creating_output',
    'test_slither_control_pair.SlitherPairTests.test_pair_rejects_reports_with_different_declared_commits',
    'test_slither_control_pair.SlitherPairTests.test_detector_specific_comparison_is_fixed_and_keeps_tx_origin',
    'test_slither_control_pair.SlitherPairTests.test_control_source_cannot_be_relabelled_to_opposite_polarity',
    'test_slither_control_pair.SlitherPairTests.test_comparison_wrong_declared_scope_rejected',
    'test_slither_control_pair.SlitherPairTests.test_comparison_false_positive_rejected_even_if_resealed',
    'test_slither_control_pair.SlitherPairTests.test_missing_third_control_rejected',
)

# Offline comparison of TWO source-bound Slither runs of THREE fixed controls.
# Real accept/check_context are called; evidence never authenticates producers.
COMPONENTS['slither_pair_replay'] = {
    'files': ['slither_pair_replay.py'],
    'tests': ['test_slither_pair_replay.'],
    'depends': ['slither_control_pair', 'static_review', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('slither_pair_replay')
REQUIRED_TESTS += (
    'test_slither_pair_replay.SlitherReplayTests.test_two_distinct_anchored_pairs_agree_offline',
    'test_slither_pair_replay.SlitherReplayTests.test_missing_or_forged_external_anchor_rejected',
    'test_slither_pair_replay.SlitherReplayTests.test_copied_bundle_with_equal_external_hash_cannot_masquerade_as_replay',
    'test_slither_pair_replay.SlitherReplayTests.test_same_anchor_is_rejected_before_reading_any_report',
    'test_slither_pair_replay.SlitherReplayTests.test_first_external_anchor_mutated_during_read_is_rejected',
    'test_slither_pair_replay.SlitherReplayTests.test_second_external_anchor_mutated_during_read_is_rejected',
    'test_slither_pair_replay.SlitherReplayTests.test_mutation_during_create_produces_no_successful_comparison_bundle',
    'test_slither_pair_replay.SlitherReplayTests.test_difference_in_alert_fingerprint_rejected',
    'test_slither_pair_replay.SlitherReplayTests.test_difference_in_severity_rejected',
    'test_slither_pair_replay.SlitherReplayTests.test_difference_in_declared_commit_rejected',
    'test_slither_pair_replay.SlitherReplayTests.test_third_control_semantic_divergence_is_detected',
    'test_slither_pair_replay.SlitherReplayTests.test_third_control_false_positive_blocks_before_comparison',
    'test_slither_pair_replay.SlitherReplayTests.test_report_tampering_rejected_after_manifest_reseal',
    'test_slither_pair_replay.SlitherReplayTests.test_symlink_pair_rejected',
)

# Real offline integration test of the original source-bound Slither importer,
# native audit chain, 3-case verifier, and 6-report replay. Its scanner JSON
# is SYNTHETIC and never constitutes proof of actual Slither execution.
COMPONENTS['slither_pair_replay']['tests'].append('test_slither_offline_endtoend.')
REQUIRED_TESTS += (
    'test_slither_offline_endtoend.SlitherOfflineEndToEndTests.test_real_offline_import_verification_and_six_report_comparison',
    'test_slither_offline_endtoend.SlitherOfflineEndToEndTests.test_real_importer_rejects_wrong_source_offsets_before_bundle',
    'test_slither_offline_endtoend.SlitherOfflineEndToEndTests.test_real_verifier_rejects_altered_original_source_even_if_content_resealed',
    'test_slither_offline_endtoend.SlitherOfflineEndToEndTests.test_synthetic_report_is_never_claimed_as_native_scanner_proof',
)

# Native evaluation is restricted to the same three immutable owned sources.
# Original scanner bytes and explicit empty-report conversion remain separate.
COMPONENTS['owned_slither_native'] = {
    'files':['owned_slither_native.py','owned_slither_native_worker.py','owned_slither_cases.py',
             'owned_slither_network.py','owned_slither_dependencies.py','owned_slither_pins.py'],
    'tests':['test_owned_slither_native.'],
    'depends':['quality','static_review','native_compile','owned_process','io','privacy']}
COMPONENTS['entrypoints']['depends'].append('owned_slither_native')
REQUIRED_TESTS += (
    'test_owned_slither_native.ConversionTests.test_generic_importer_still_rejects_missing_detector_field',
    'test_owned_slither_native.NativeEvidenceTests.test_original_bytes_and_real_importer_chain_are_retained',
    'test_owned_slither_native.NativeEvidenceTests.test_false_positive_and_omission_are_measured_not_hidden',
    'test_owned_slither_native.NativeEvidenceTests.test_replay_must_execute_three_new_cases',
    'test_owned_slither_native.NativeEvidenceTests.test_native_replay_difference_is_rejected',
    'test_owned_slither_native.NetworkFilterTests.test_sealed_filter_is_inherited_by_exec_child',
    'test_owned_slither_native.DependencyTests.test_entrypoint_metadata_change_is_rejected',
)

COMPONENTS['owned_defensive_acceptance'] = {
    'files':['owned_defensive_acceptance.py'],'tests':['test_owned_defensive_acceptance.'],
    'depends':['owned_platform','owned_authority_evm','quality','io','privacy']}
COMPONENTS['entrypoints']['depends'].append('owned_defensive_acceptance')
COMPONENTS['quality']['tests'].append('test_quality_entrypoint.')
REQUIRED_TESTS += (
    'test_owned_defensive_acceptance.DefensiveAcceptanceTests.test_both_native_cohorts_must_be_reexecuted',
    'test_owned_defensive_acceptance.DefensiveAcceptanceTests.test_complete_acceptance_retains_the_known_omission',
    'test_owned_defensive_acceptance.DefensiveAcceptanceTests.test_incompatible_case_units_are_not_pooled',
    'test_owned_defensive_acceptance.DefensiveAcceptanceTests.test_rehashed_omission_removal_is_rejected',
    'test_owned_defensive_acceptance.DefensiveAcceptanceTests.test_native_evidence_changed_after_replay_is_rejected',
    'test_quality_entrypoint.QualityEntrypointTests.test_direct_and_package_entrypoints_accept_the_same_unit_receipt',
    'test_quality_entrypoint.QualityEntrypointTests.test_missing_late_required_test_is_blocked_by_both_entrypoints',
    'test_owned_slither_native.ConversionTests.test_changed_literal_cannot_keep_historical_source_identity',
    'test_owned_slither_native.ConversionTests.test_changed_container_cannot_keep_historical_commit_claim',
    'test_owned_slither_native.DependencyTests.test_extra_visible_location_is_rejected_before_reading_its_metadata',
    'test_owned_slither_native.DependencyTests.test_duplicate_visible_distribution_is_rejected',
    'test_owned_slither_native.DependencyTests.test_visible_index_is_rechecked_after_file_inventory',
)


# Descriptive coverage of the unchanged OWNED event corpus; no new detector.
COMPONENTS['owned_authority_coverage'] = {
    'files': ['owned_authority_coverage.py', 'owned_authority_coverage_reference.py'],
    'tests': ['test_owned_authority_coverage.'],
    'depends': ['quality', 'owned_authority', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('owned_authority_coverage')
REQUIRED_TESTS += (
    'test_owned_authority_coverage.CoverageTests.test_latent_case_stays_identical_to_clean_repeat',
    'test_owned_authority_coverage.CoverageTests.test_history_reference_agrees_on_small_exhaustive_corpus',
    'test_owned_authority_coverage.CoverageTests.test_history_reference_agrees_on_seeded_multiscope_corpus',
    'test_owned_authority_coverage.CoverageBundleTests.test_resealed_false_coverage_is_rejected',
    'test_owned_authority_coverage.CoverageBundleTests.test_resealed_changed_input_cannot_replace_fixed_sequence',
    'test_owned_authority_coverage.CoverageBundleTests.test_cli_creates_and_verifies_in_separate_processes',
)


COMPONENTS['owned_authority_coverage_suite'] = {
    'files': ['owned_authority_coverage_cases.py', 'owned_authority_coverage_suite.py'],
    'tests': ['test_owned_authority_coverage_suite.'],
    'depends': ['owned_authority_coverage', 'owned_authority', 'quality', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('owned_authority_coverage_suite')
REQUIRED_TESTS += (
    'test_owned_authority_coverage_suite.CorpusTests.test_exact_expectations_match_both_algorithms',
    'test_owned_authority_coverage_suite.CorpusTests.test_missing_and_duplicate_pair_rejected',
    'test_owned_authority_coverage_suite.SuiteBundleTests.test_historical_identity_change_blocks_creation',
    'test_owned_authority_coverage_suite.SuiteBundleTests.test_resealed_false_report_rejected',
    'test_owned_authority_coverage_suite.SuiteBundleTests.test_cli_separate_processes',
)


COMPONENTS['owned_coverage_link'] = {
    'files': ['owned_coverage_link.py'], 'tests': ['test_owned_coverage_link.'],
    'depends': ['owned_authority_coverage', 'owned_authority_coverage_suite',
                'owned_authority', 'quality', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('owned_coverage_link')
REQUIRED_TESTS += (
    'test_owned_coverage_link.CoverageLinkTests.test_both_reports_are_regenerated_with_external_anchors',
    'test_owned_coverage_link.CoverageLinkTests.test_gaps_and_denominators_remain_separate',
    'test_owned_coverage_link.CoverageLinkTests.test_historical_marker_changed_after_replay_is_rejected',
    'test_owned_coverage_link.CoverageLinkTests.test_input_from_another_source_cannot_be_resealed_into_this_version',
    'test_owned_coverage_link.CoverageLinkTests.test_resealed_gap_erasure_is_rejected',
    'test_owned_coverage_link.CoverageLinkTests.test_cli_creates_and_verifies_in_separate_processes',
)


COMPONENTS['portfolio_inventory'] = {
    'files': ['portfolio_inventory.py', *PORTFOLIO_DATA_FILES],
    'tests': ['test_portfolio_inventory.'],
    'depends': ['platform', 'research', 'quality', 'owned_authority', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('portfolio_inventory')
REQUIRED_TESTS += (
    'test_portfolio_inventory.PortfolioTests.test_all_fifty_candidates_and_five_mirrors_agree',
    'test_portfolio_inventory.PortfolioTests.test_policy_changes_are_not_accepted_as_permissions',
    'test_portfolio_inventory.PortfolioTests.test_mirror_must_preserve_all_fields_not_only_ids',
    'test_portfolio_inventory.RegistryBundleTests.test_four_registries_keep_ids_counts_and_statuses_separate',
    'test_portfolio_inventory.RegistryBundleTests.test_all_nine_data_sources_are_bound_to_executable_snapshot',
    'test_portfolio_inventory.RegistryBundleTests.test_resealed_global_percentage_is_rejected',
    'test_portfolio_inventory.RegistryBundleTests.test_cli_creates_and_verifies_in_separate_processes',
)




COMPONENTS['owned_authority_behavior'] = {
    'files': ['owned_authority_behavior.py'], 'tests': ['test_owned_authority_behavior.'],
    'depends': ['owned_authority_coverage_suite', 'owned_authority', 'quality', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('owned_authority_behavior')
REQUIRED_TESTS += (
    'test_owned_authority_behavior.BehaviorTests.test_all_authored_decisions_and_effects_match_correct_model_and_reference',
    'test_owned_authority_behavior.BehaviorTests.test_control_commands_and_denied_uses_do_not_produce_effects',
    'test_owned_authority_behavior.BehaviorTests.test_each_accepted_use_changes_exactly_one_counter_by_one',
    'test_owned_authority_behavior.BehaviorTests.test_model_receives_only_event_records_and_only_correct_variant',
    'test_owned_authority_behavior.BehaviorTests.test_agreeing_wrong_model_and_reference_cannot_override_authored_expectation',
    'test_owned_authority_behavior.BehaviorBundleTests.test_resealed_altered_trace_is_rejected',
    'test_owned_authority_behavior.BehaviorBundleTests.test_cli_creation_and_verification_in_separate_processes',
)


COMPONENTS['owned_correct_cross_evm'] = {
    'files': ['owned_correct_evm_cases.py', 'owned_correct_geth.py', 'owned_correct_evm_worker.py',
              'owned_correct_spec_worker.py', 'owned_correct_cross_evm.py'],
    'tests': ['test_owned_correct_cross_evm.'],
    'depends': ['owned_authority_behavior', 'owned_authority_evm', 'owned_cross_evm',
                'owned_process', 'quality', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('owned_correct_cross_evm')
REQUIRED_TESTS += (
    'test_owned_correct_cross_evm.CorrectNativeTests.test_only_correct_source_and_fixed_codegen_are_accepted',
    'test_owned_correct_cross_evm.CorrectNativeTests.test_committed_denied_use_remains_false_in_projection',
    'test_owned_correct_cross_evm.CorrectNativeTests.test_one_gas_probe_cannot_persist_any_state',
    'test_owned_correct_cross_evm.CorrectNativeTests.test_agreeing_engines_with_wrong_permission_storage_are_rejected',
    'test_owned_correct_cross_evm.CorrectNativeTests.test_agreeing_engines_with_wrong_generation_are_rejected',
    'test_owned_correct_cross_evm.CorrectNativeBundleTests.test_verifier_requests_two_fresh_native_worker_runs',
    'test_owned_correct_cross_evm.CorrectNativeBundleTests.test_reexecution_failure_cannot_be_replaced_by_saved_receipt',
)


COMPONENTS['qa_custody'] = {
    'files': ['qa_custody.py'], 'tests': ['test_qa_custody.'],
    'depends': ['quality', 'custody', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('qa_custody')
REQUIRED_TESTS += (
    'test_qa_custody.QACustodyTests.test_real_signature_and_all_receipts_verified',
    'test_qa_custody.QACustodyTests.test_revoked_key_rejected',
    'test_qa_custody.QACustodyTests.test_resealed_worker_log_rejected',
    'test_qa_custody.QACustodyTests.test_report_cannot_promote_execution_authentication',
    'test_qa_custody.QACustodyTests.test_cli_creation_and_verification_in_separate_processes',
)


COMPONENTS['journal_custody'] = {
    'files': ['journal_custody.py'], 'tests': ['test_journal_custody.'],
    'depends': ['journal_ingest', 'custody', 'quality', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('journal_custody')
COMPONENTS['forensic_timeline']['tests'].append('test_timeline_boundaries.')
REQUIRED_TESTS += (
    'test_timeline_boundaries.TimelineBoundaryTests.test_maximum_time_with_uncertainty_is_inconclusive',
    'test_timeline_boundaries.TimelineBoundaryTests.test_minimum_time_with_uncertainty_is_inconclusive',
    'test_journal_custody.JournalCustodyTests.test_signed_overlap_stays_inconclusive',
    'test_journal_custody.JournalCustodyTests.test_signed_contradiction_stays_contradictory',
    'test_journal_custody.JournalCustodyTests.test_signature_does_not_replace_semantic_replay',
    'test_journal_custody.JournalCustodyTests.test_cli_separate_processes_preserve_nonzero_for_uncertainty',
)


COMPONENTS['owned_capture'] = {
    'files': ['owned_capture.py', 'owned_boundary_worker.py'], 'tests': ['test_owned_capture.'],
    'depends': ['owned_process', 'repository_boundary', 'quality', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('owned_capture')
REQUIRED_TESTS += (
    'test_owned_capture.OwnedCaptureTests.test_real_capture_and_read_only_verifier',
    'test_owned_capture.OwnedCaptureTests.test_original_anchor_rejects_rewritten_observation',
    'test_owned_capture.OwnedCaptureTests.test_rehashed_boundary_change_rejected',
    'test_owned_capture.OwnedCaptureTests.test_independent_authentication_cannot_be_promoted',
    'test_owned_capture.OwnedCaptureTests.test_cli_capture_and_verify_in_separate_processes',
)


COMPONENTS['owned_boundary_diagnosis'] = {
    'files': ['owned_boundary_diagnosis.py', 'owned_boundary_trial_worker.py'],
    'tests': ['test_owned_boundary_diagnosis.', 'test_owned_remediation.'],
    'depends': ['owned_capture', 'owned_process', 'repository_boundary', 'quality', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('owned_boundary_diagnosis')
REQUIRED_TESTS += (
    'test_owned_boundary_diagnosis.DiagnosisTests.test_real_faults_repairs_and_same_error_different_causes',
    'test_owned_boundary_diagnosis.DiagnosisTests.test_verifier_does_not_execute_or_modify_checkout',
    'test_owned_boundary_diagnosis.DiagnosisTests.test_timeout_preserves_partial_evidence_without_promotion',
    'test_owned_boundary_diagnosis.DiagnosisTests.test_cannot_hide_an_unexpected_result_with_later_repairs',
    'test_owned_boundary_diagnosis.DiagnosisTests.test_resealed_report_cannot_invent_hypotheses',
    'test_owned_boundary_diagnosis.DiagnosisTests.test_cli_real_experiment_and_separate_verifier',
    'test_owned_remediation.OwnedRemediationTests.test_findings_are_derived_from_actual_fault_and_restoration',
    'test_owned_remediation.OwnedRemediationTests.test_incomplete_verified_diagnosis_has_no_findings_or_actions',
    'test_owned_remediation.OwnedRemediationTests.test_resealed_action_cannot_enable_execution',
    'test_owned_remediation.OwnedRemediationTests.test_mode_only_plan_preserves_original_content_reference',
    'test_owned_remediation.OwnedRemediationTests.test_cli_reports_counts_without_private_paths_or_identity',
)


COMPONENTS['bundle_recovery'] = {
    'files': ['bundle_recovery.py', 'owned_bundle_interrupt_worker.py'],
    'tests': ['test_bundle_recovery.', 'test_bundle_writer.'],
    'depends': ['owned_capture', 'owned_process', 'quality', 'io', 'privacy']}
COMPONENTS['io']['tests'].append('test_bundle_writer.')
COMPONENTS['entrypoints']['depends'].append('bundle_recovery')
REQUIRED_TESTS += (
    'test_bundle_writer.BundleWriterTests.test_invalid_bytes_leave_no_directory_and_valid_retry_succeeds',
    'test_bundle_writer.InterruptedWriterTests.test_real_sigkill_during_marker_never_publishes_partial_complete',
    'test_bundle_writer.InterruptedWriterTests.test_real_sigkill_after_link_remains_cleanup_pending',
    'test_bundle_recovery.RecoveryTests.test_preservation_does_not_complete_or_change_input',
    'test_bundle_recovery.RecoveryTests.test_promoted_recovery_report_rejected_even_with_new_manifest',
    'test_bundle_recovery.RecoveryTests.test_cli_preserves_nonzero_for_incomplete_source',
)


COMPONENTS['preserved_copy'] = {
    'files': ['preserved_copy.py'], 'tests': ['test_preserved_copy.'],
    'depends': ['bundle_recovery', 'owned_capture', 'quality', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('preserved_copy')
REQUIRED_TESTS += (
    'test_preserved_copy.PreservedCopyTests.test_original_removed_copy_still_verifies_as_incomplete',
    'test_preserved_copy.PreservedCopyTests.test_changed_bytes_resealed_still_rejected_by_input_anchor',
    'test_preserved_copy.PreservedCopyTests.test_report_cannot_promote_original_completion',
    'test_preserved_copy.PreservedCopyTests.test_cli_after_original_removed_preserves_incomplete_status',
)


COMPONENTS['portable_copy'] = {
    'files': ['portable_copy.py'], 'tests': ['test_portable_copy.'],
    'depends': ['preserved_copy', 'bundle_recovery', 'owned_capture', 'quality', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('portable_copy')
REQUIRED_TESTS += (
    'test_portable_copy.PortableCopyTests.test_archive_verifies_after_source_and_copy_are_removed',
    'test_portable_copy.PortableCopyTests.test_private_bytes_need_explicit_acknowledgment',
    'test_portable_copy.PortableCopyTests.test_resealed_changed_content_cannot_replace_input_anchor',
    'test_portable_copy.PortableCopyTests.test_cli_preserves_incomplete_state_and_private_output',
    'test_portable_copy.PortableCopyTests.test_explicit_earlier_identity_keeps_history_and_current_reader_separate',
    'test_portable_copy.PortableCopyTests.test_earlier_identity_cannot_replace_current_reader_pin',
)


COMPONENTS['preserved_index'] = {
    'files': ['preserved_index.py'], 'tests': ['test_preserved_index.'],
    'depends': ['portable_copy', 'bundle_recovery', 'owned_capture', 'quality', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('preserved_index')
REQUIRED_TESTS += (
    'test_preserved_index.PreservedIndexTests.test_aliases_do_not_count_as_independent_evidence',
    'test_preserved_index.PreservedIndexTests.test_resealed_count_inflation_is_rejected',
    'test_preserved_index.PreservedIndexTests.test_earlier_archive_changed_during_later_verification_rejected',
    'test_preserved_index.PreservedIndexTests.test_cli_mixed_collection_stays_incomplete_and_private',
    'test_preserved_index.PreservedIndexTests.test_historical_index_identity_is_explicit_and_separate',
)


COMPONENTS['preserved_retention'] = {
    'files': ['preserved_retention.py'], 'tests': ['test_preserved_retention.'],
    'depends': ['preserved_index', 'bundle_recovery', 'owned_capture', 'quality', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('preserved_retention')
REQUIRED_TESTS += (
    'test_preserved_retention.PreservedRetentionTests.test_exact_duplicates_reviewed_incomplete_copies_kept',
    'test_preserved_retention.PreservedRetentionTests.test_missing_copies_are_unmet_never_fabricated',
    'test_preserved_retention.PreservedRetentionTests.test_budget_shortfall_preserves_required_copies',
    'test_preserved_retention.PreservedRetentionTests.test_resealed_decision_changes_are_rejected',
    'test_preserved_retention.PreservedRetentionTests.test_cli_incomplete_and_unmet_are_nonzero_and_private',
)


COMPONENTS['preserved_index']['tests'].append('test_preserved_index_cache.')
REQUIRED_TESTS += (
    'test_preserved_index_cache.PreservedIndexCacheTests.test_64_aliases_reuse_one_content_check_but_keep_64_entries',
    'test_preserved_index_cache.PreservedIndexCacheTests.test_same_archive_with_conflicting_any_producer_or_content_pin_rejects',
    'test_preserved_index_cache.PreservedIndexCacheTests.test_earlier_file_changed_during_cached_alias_is_rejected',
    'test_preserved_index_cache.PreservedIndexCacheTests.test_reuse_never_persists_across_calls',
)


COMPONENTS['preserved_custody'] = {
    'files': ['preserved_custody.py'], 'tests': ['test_preserved_custody.'],
    'depends': ['preserved_index', 'custody', 'bundle_recovery', 'owned_capture', 'quality', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('preserved_custody')
REQUIRED_TESTS += (
    'test_preserved_custody.PreservedCustodyTests.test_real_signature_and_archive_check_preserve_incomplete_state',
    'test_preserved_custody.PreservedCustodyTests.test_valid_signature_cannot_approve_false_index_counts',
    'test_preserved_custody.PreservedCustodyTests.test_revoked_key_with_updated_policy_anchor_is_rejected',
    'test_preserved_custody.PreservedCustodyTests.test_archive_change_during_final_signature_check_is_rejected',
    'test_preserved_custody.PreservedCustodyTests.test_cli_preserves_incomplete_state_and_private_identity',
)


COMPONENTS['owned_workspace'] = {
    'files': ['owned_workspace.py'],
    'tests': ['test_owned_workspace.', 'test_owned_workspace_admission.'], 'depends': []}
for _component in ('owned_capture', 'owned_boundary_diagnosis'):
    COMPONENTS[_component]['depends'].append('owned_workspace')
REQUIRED_TESTS += (
    'test_owned_workspace.WorkspaceTests.test_real_nested_cleanup_and_later_absence',
    'test_owned_workspace.WorkspaceTests.test_replaced_root_is_retained_without_deleting_replacement',
    'test_owned_workspace.WorkspaceTests.test_reappearance_is_rejected_without_deletion',
    'test_owned_workspace.WorkspaceTests.test_lost_descriptor_does_not_leak_other_owned_handle',
    'test_owned_workspace.WorkspaceTests.test_reassigned_descriptor_is_not_closed_as_the_original',
    'test_owned_workspace.WorkspaceTests.test_capture_blocks_publication_after_actual_root_replacement',
    'test_owned_workspace.WorkspaceTests.test_diagnosis_blocks_publication_after_actual_root_replacement',
)


COMPONENTS['owned_compute_guard'] = {
    'files': ['owned_compute_guard.py'], 'tests': ['test_owned_compute_guard.'],
    'depends': ['owned_slither_native', 'io']}
COMPONENTS['owned_restricted_review'] = {
    'files': ['owned_restricted_review.py', 'owned_restricted_worker.py'],
    'tests': ['test_owned_restricted_review.'],
    'depends': ['owned_compute_guard', 'owned_boundary_diagnosis', 'owned_capture',
                'owned_process', 'owned_workspace', 'repository_boundary', 'quality', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('owned_restricted_review')
REQUIRED_TESTS += (
    'test_owned_compute_guard.ComputeGuardTests.test_actual_filter_controls_and_preloaded_computation',
    'test_owned_compute_guard.ComputeGuardTests.test_extra_inherited_descriptor_is_rejected',
    'test_owned_compute_guard.ComputeGuardTests.test_real_anonymous_mapping_and_denied_mapping_variants',
    'test_owned_compute_guard.ComputeGuardTests.test_low_library_loading_limit_does_not_silently_fallback',
    'test_owned_restricted_review.RestrictedReviewTests.test_actual_five_restricted_trials_and_distinct_worker_identity',
    'test_owned_restricted_review.RestrictedReviewTests.test_verifier_never_reexecutes_filter_or_repairs_source',
    'test_owned_restricted_review.RestrictedReviewTests.test_actual_extra_descriptor_stops_producer_and_preserves_failed_trial',
    'test_owned_restricted_review.RestrictedReviewTests.test_legacy_unrestricted_stdout_cannot_pass_as_restricted',
    'test_owned_restricted_review.RestrictedReviewTests.test_filter_phase_must_be_inside_parent_observation',
    'test_owned_restricted_review.RestrictedReviewTests.test_resealed_report_promotion_is_rejected',
)


COMPONENTS['quality']['tests'].append('test_quality_row_index.')
REQUIRED_TESTS += (
    'test_owned_workspace_admission.WorkspaceAdmissionTests.test_replaced_directory_open_is_closed_without_deleting_replacement',
    'test_owned_workspace_admission.WorkspaceAdmissionTests.test_symlink_between_stat_and_open_preserves_target_and_closes_parent',
    'test_quality_row_index.QualityRowIndexTests.test_overlapping_prefixes_do_not_duplicate_shared_rows',
    'test_quality_row_index.QualityRowIndexTests.test_seeded_mixed_prefixes_match_direct_reference',
)


# Register the complete package before either CLI entry point runs.
COMPONENTS['owned_restricted_corroboration'] = {
    'files': ['owned_restricted_corroboration.py'],
    'tests': ['test_owned_restricted_corroboration.'],
    'depends': ['owned_boundary_diagnosis', 'owned_restricted_review', 'owned_capture',
                'quality', 'io', 'privacy']}
COMPONENTS['entrypoints']['depends'].append('owned_restricted_corroboration')
REQUIRED_TESTS += (
    'test_owned_restricted_corroboration.RestrictedCorroborationTests.test_actual_ten_trials_bind_two_existing_findings_and_plans',
    'test_owned_restricted_corroboration.RestrictedCorroborationTests.test_create_and_verify_never_launch_a_process',
    'test_owned_restricted_corroboration.RestrictedCorroborationTests.test_real_extra_descriptor_failure_cannot_corroborate_existing_findings',
    'test_owned_restricted_corroboration.RestrictedCorroborationTests.test_input_mutation_after_its_verification_prevents_publication',
    'test_owned_restricted_corroboration.RestrictedCorroborationTests.test_resealed_report_cannot_promote_guarantees_or_finding_count',
)


if __name__ == '__main__':
    raise SystemExit(main())
