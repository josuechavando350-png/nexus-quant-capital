"""Differential code-generation checks for three fixed OWNED arithmetic controls.

This is a bounded regression laboratory, not a scanner, exploit generator, or
universal compiler-equivalence prover. It consumes a verified native acceptance
and executes two additional compile profiles of exactly the same fixed sources.
No source, target, RPC, calldata, optimizer flag or external query is accepted.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from . import native_platform as joint, evm_execution as evm, evm_accounting as effects
from . import bytecode_controls as builds, native_compile as compiler
from . import balance_reconciliation as accounting, quality
from .native_runtime import load_components
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILES = ('legacy_unoptimized', 'legacy_optimized', 'ir_optimized')
PROFILE = 'fixed-owned-codegen-comparison-v1'
FILES = {'variants.json', 'comparison.json', 'audit.json', 'REVIEW.md'}
sha = evm.sha


class VariantError(ValueError):
    """Fixed diagnostics only; do not echo supplied paths or artifact content."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise VariantError(code)


def build_input(name: str, profile: str) -> dict:
    need(type(name) is str and name in builds.formal.NAMES and
         type(profile) is str and profile in PROFILES, 'FIXED_CONTROL_AND_PROFILE_REQUIRED')
    inp = builds.build_input(name)
    if profile != PROFILES[0]:
        inp['settings']['optimizer'] = {'enabled': True, 'runs': 200}
    if profile == 'ir_optimized':
        inp['settings']['viaIR'] = True
    return inp


def inspect_build(name: str, profile: str, build: dict, original: dict) -> tuple[dict, dict]:
    """Check freshly produced bytes, not just a claimed settings label."""
    need(type(build) is dict and set(build) == {'input', 'output_utf8', 'stderr_utf8'}, 'BUILD_SCHEMA')
    inp = build_input(name, profile)
    need(canonical(build['input']) == canonical(inp), 'COMPILE_PROFILE_MISMATCH')
    base_input = builds.build_input(name)
    need(canonical(original['input']) == canonical(base_input), 'BASELINE_SOURCE_MISMATCH')
    need(canonical(inp['sources']) == canonical(base_input['sources']), 'SOURCE_CHANGED_BETWEEN_PROFILES')
    need(type(build['output_utf8']) is str and build['stderr_utf8'] == '', 'COMPILER_OUTPUT_REQUIRED')
    raw = build['output_utf8'].encode()
    status = compiler.classify_output(inp, raw)
    need(status['status'] == 'SOLC_COMPILATION_COMPLETED', 'PROFILE_COMPILATION_FAILED')
    output = strict_json(raw)
    need(set(output['contracts']) == {builds.SOURCE_FILE} and
         set(output['contracts'][builds.SOURCE_FILE]) == {builds.CONTRACT}, 'FIXED_CONTRACT_SET')
    contract = output['contracts'][builds.SOURCE_FILE][builds.CONTRACT]
    base = strict_json(original['output_utf8'])['contracts'][builds.SOURCE_FILE][builds.CONTRACT]
    need(canonical(contract.get('abi')) == canonical(builds.EXPECTED_ABI) and
         canonical(contract.get('storageLayout')) == canonical(base['storageLayout']), 'ABI_OR_LAYOUT_CHANGED')
    bytecode = contract.get('evm')
    need(type(bytecode) is dict and set(bytecode) == {'bytecode', 'deployedBytecode', 'methodIdentifiers'}, 'BYTECODE_SCHEMA')
    init, runtime = bytecode['bytecode'], bytecode['deployedBytecode']
    need(type(init) is dict and set(init) == {'object', 'linkReferences'} and
         type(runtime) is dict and set(runtime) == {'object', 'linkReferences', 'immutableReferences'}, 'OBJECT_SCHEMA')
    need(init['linkReferences'] == {} and runtime['linkReferences'] == {} and
         runtime['immutableReferences'] == {}, 'UNRESOLVED_LINKS')
    init_bytes = builds._object(init['object'], 'CREATION_OBJECT')
    run_bytes = builds._object(runtime['object'], 'RUNTIME_OBJECT')
    need(canonical(bytecode['methodIdentifiers']) == canonical(base['evm']['methodIdentifiers']), 'SELECTOR_CHANGED')
    metadata = strict_json(contract.get('metadata', ''))
    base_metadata = strict_json(base['metadata'])
    settings = metadata.get('settings', {})
    need(metadata.get('compiler', {}).get('version') == compiler.PIN['version'], 'METADATA_COMPILER')
    need(settings.get('compilationTarget') == {builds.SOURCE_FILE: builds.CONTRACT} and
         settings.get('evmVersion') == 'cancun' and settings.get('libraries') == {} and
         settings.get('remappings') == [], 'METADATA_SETTINGS')
    expected_optimizer = {'enabled': profile != PROFILES[0], 'runs': 200}
    need(canonical(settings.get('optimizer')) == canonical(expected_optimizer) and
         settings.get('viaIR', False) is (profile == 'ir_optimized'), 'METADATA_PROFILE_MISMATCH')
    need(canonical(metadata.get('sources')) == canonical(base_metadata.get('sources')), 'METADATA_SOURCE_CHANGED')
    return contract, {'input_sha256': sha(canonical(inp)), 'output_sha256': sha(raw),
                      'source_sha256': sha(inp['sources'][builds.SOURCE_FILE]['content'].encode()),
                      'creation_bytes': len(init_bytes), 'runtime_bytes': len(run_bytes),
                      'creation_sha256': sha(init_bytes), 'runtime_sha256': sha(run_bytes),
                      'compiler_warnings': status['warnings']}


def run_case(name: str, contract: dict, image: bytes, property_status: str) -> dict:
    """Execute constructor and fixed message sequence with the existing pinned worker."""
    birth = evm._run(image, prestate=evm.genesis(), creation=contract['evm']['bytecode']['object'])
    need(birth['observed']['error'] is None and birth['observed']['return_data'] ==
         '0x' + contract['evm']['deployedBytecode']['object'], 'CONSTRUCTOR_RUNTIME')
    alloc = birth['observed']['alloc']
    initial = evm.decode_state(alloc, contract)
    need(set(alloc) == {evm.SENDER, evm.RECEIVER} and initial == {'debit': 15, 'credit': 0, 'steps': 0}, 'INITIAL_STATE')
    state = initial
    calls = []
    for i, (quantity, gas) in enumerate(evm.STEPS):
        calldata = contract['evm']['methodIdentifiers']['move(uint8)'] + format(quantity, '064x')
        observation = evm._run(image, prestate=evm.genesis(alloc, gas=gas), calldata=calldata, gas=gas)
        after = evm.decode_state(observation['observed']['alloc'], contract)
        calls.append({'index': i, 'quantity': quantity, 'reference': evm.reference(name, state, quantity, gas),
                      'state_before': state, 'state_after': after, 'execution': observation})
        state, alloc = after, observation['observed']['alloc']
    row = {'constructor': birth, 'constructor_state': initial, 'calls': calls,
           'final_state': state, 'source_property_status': property_status}
    evm.validate_case(name, row, contract)  # Includes every revert/return/prestate binding.
    return row


def _accounts(observed: dict) -> dict:
    # Code and trie hashes must differ across compiled artifacts. Only these fields
    # are excluded from cross-profile comparison; full bytes remain in evidence.
    return {a: {k: row[k] for k in ('balance', 'nonce', 'storage')}
            for a, row in sorted(observed['alloc'].items())}


def observable_trace(row: dict) -> dict:
    birth = evm.parse_run(row['constructor']['stdout_utf8'].encode())
    steps = []
    for call in row['calls']:
        run = call['execution']
        observed = evm.parse_run(run['stdout_utf8'].encode())
        steps.append({'index': call['index'], 'quantity': call['quantity'], 'gas_limit': run['gas_limit'],
                      'calldata': run['calldata'], 'accounts': _accounts(observed),
                      'return_data': observed['return_data'], 'error': observed['error']})
    return {'constructor_accounts': _accounts(birth), 'calls': steps}


def reconcile_case(row: dict, contract: dict) -> dict:
    """Use NQC-side arithmetic on observed persistent units, never tentative credit."""
    before = evm.decode_state(evm.parse_run(row['constructor']['stdout_utf8'].encode())['alloc'], contract)
    cells = 0
    outcomes = Counter()
    applied = 0
    for index, call in enumerate(row['calls']):
        observed = evm.parse_run(call['execution']['stdout_utf8'].encode())
        after = evm.decode_state(observed['alloc'], contract)
        outcome = effects.classify(observed)
        amount = evm.STEPS[index][0] if outcome == 'COMMITTED' else 0
        moves = [] if amount == 0 else [{'id': f'call-{index}', 'from': 'debit', 'to': 'credit', 'amount_units': str(amount)}]
        balances = lambda x: {k: str(x[k]) for k in ('debit', 'credit')}
        eq = accounting.reconcile_internal_units(balances(before), balances(after), moves)
        need(eq['status'] == 'UNIT_BALANCES_RECONCILED', 'PERSISTENT_UNITS_MISMATCH')
        cells += len(eq['rows']); outcomes[outcome] += 1; applied += amount
        before = after
    return {'final_state': before, 'applied_units': str(applied), 'accounting_cells': cells,
            'outcomes': dict(sorted(outcomes.items())), 'monetary_value_usd': None}


def analyze(baseline: dict, variants: dict) -> dict:
    """Recalculate a captured comparison; this alone does NOT demonstrate execution."""
    evm.result_from(baseline, '2026-01-01T00:00:00+00:00')
    need(type(variants) is dict and set(variants) == set(builds.formal.NAMES), 'VARIANT_CONTROL_COVERAGE')
    cases = {}
    totals = Counter()
    for name in builds.formal.NAMES:
        need(type(variants[name]) is dict and set(variants[name]) == set(PROFILES[1:]), 'VARIANT_PROFILE_COVERAGE')
        original = baseline['builds']['cases'][name]
        rows = {PROFILES[0]: {'build': original, 'execution': baseline['cases'][name]}, **variants[name]}
        metrics, observations = {}, {}
        for profile in PROFILES:
            item = rows[profile]
            need(type(item) is dict and set(item) == {'build', 'execution'}, 'VARIANT_RECORD_SCHEMA')
            contract, build_info = inspect_build(name, profile, item['build'], original)
            row = item['execution']
            need(row['source_property_status'] == baseline['cases'][name]['source_property_status'], 'FALSE_FORMAL_BINDING')
            evm.validate_case(name, row, contract)
            units = reconcile_case(row, contract)
            observations[profile] = observable_trace(row)
            metrics[profile] = {**build_info, **units, 'observable_sha256': sha(canonical(observations[profile]))}
            totals.update(units['outcomes'])
        for profile in PROFILES[1:]:
            need(canonical(observations[profile]) == canonical(observations[PROFILES[0]]), 'OBSERVABLE_BEHAVIOR_DISAGREEMENT')
        cases[name] = {'profiles': metrics, 'same_observed_behavior': True,
                       'distinct_runtimes': len({m['runtime_sha256'] for m in metrics.values()}),
                       'source_property_status': baseline['cases'][name]['source_property_status']}
    return {'cases': cases, 'profile_count': 3, 'controls': 3, 'constructors': 9, 'message_calls': 54,
            'cross_profile_observation_pairs': 42, 'outcomes': dict(sorted(totals.items())),
            'all_paths_proved': False, 'gas_cost_equivalence_proved': False,
            'independent_compiler_used': False, 'independent_evm_used': False,
            'formal_proof_transferred_to_optimized_bytecode': False}


def compile_variants(baseline: dict, solc: Path, evm_path: Path) -> dict:
    image = evm.read_evm(evm_path)
    solc_image = compiler.read_pinned_binary(solc)
    rows = {}
    for name in builds.formal.NAMES:
        rows[name] = {}
        original = baseline['builds']['cases'][name]
        for profile in PROFILES[1:]:
            inp = build_input(name, profile)
            raw, err = compiler._execute(solc_image, 'compile', canonical(inp))
            item = {'input': inp, 'output_utf8': raw.decode('utf-8'), 'stderr_utf8': err.decode('utf-8')}
            contract, _ = inspect_build(name, profile, item, original)
            row = run_case(name, contract, image, baseline['cases'][name]['source_property_status'])
            rows[name][profile] = {'build': item, 'execution': row}
    return rows


def _baseline(root: Path, solc: Path, evm_path: Path, expected: str) -> tuple[dict, dict]:
    # verify actually reruns solc/Z3/EVM and validates the complete current QA receipt.
    accepted = joint.verify(root, solc, evm_path, expected)
    need(accepted['status'] == 'FIXED_NATIVE_PLATFORM_REVIEW_PASS', 'NATIVE_ACCEPTANCE_REQUIRED')
    raw = read_artifact(root / 'native', 'evm--execution.json')
    need(sha(raw) == accepted['evidence_sha256']['native']['evm--execution.json'], 'BASE_CHANGED_AFTER_REPLAY')
    need(sha(raw) == accepted['native_controls']['execution_sha256'], 'BASE_EXECUTION_BINDING')
    return strict_json(raw), accepted


def execute(acceptance: Path, solc: Path, evm_path: Path, expected: str) -> dict:
    snapshot = quality.source_snapshot()
    need(type(expected) is str and re.fullmatch('[a-f0-9]{64}', expected) is not None and
         sha(canonical(snapshot)) == expected, 'EXTERNAL_SOURCE_REFERENCE_MISMATCH')
    baseline, accepted = _baseline(acceptance, solc, evm_path, expected)
    variants = compile_variants(baseline, solc, evm_path)
    summary = analyze(baseline, variants)
    need(quality.source_snapshot() == snapshot and joint._inputs(acceptance) == accepted['evidence_sha256'],
         'CODE_OR_BASE_CHANGED_DURING_COMPARISON')
    return {'schema_version': 1, 'profile': PROFILE, 'source_digest': expected,
            'acceptance_sha256': sha(canonical(accepted)), 'baseline_execution_sha256': sha(canonical(baseline)),
            'compiler_pin': compiler.PIN, 'evm_pin': evm.PIN,
            'variants': variants, 'comparison': summary}


def documents(execution: dict, at: str) -> dict[str, bytes]:
    need(type(at) is str and len(at) <= 40 and datetime.fromisoformat(at).tzinfo is not None, 'EXPLICIT_TIME_REQUIRED')
    result = {'schema_version': 1, 'profile': PROFILE, 'status': 'FIXED_COMPILER_VARIANTS_AGREE',
              'created_at': at, 'source_digest': execution['source_digest'],
              'acceptance_sha256': execution['acceptance_sha256'], 'execution_sha256': sha(canonical(execution)),
              **execution['comparison'], 'same_native_tools_reexecuted': True,
              'qa_tests_reexecuted_here': False, 'known_owned_controls_only': True,
              'network_used': False, 'vulnerability_confirmed': False, 'platform_complete': False}
    audit = load_components().audit.AuditLog(clock=lambda: at)
    audit.append('variants.acceptance', {'source_digest': result['source_digest'], 'acceptance_sha256': result['acceptance_sha256']})
    for name, case in result['cases'].items():
        audit.append('variants.case', {'case': name, 'comparison_sha256': sha(canonical(case))})
    audit.append('variants.complete', {'result_sha256': sha(canonical(result))})
    audit.assert_intact()
    text = ['# SUPERHUNTER — comparación de tres configuraciones de compilación', '', result['status'], '',
            f"Código esperado: `{result['source_digest']}`.",
            '9 constructores y 54 llamadas fijas; 42 pares de observaciones contrastados.',
            'Las tres configuraciones utilizan el MISMO solc y la MISMA EVM, no motores independientes.', '',
            '| Control | Perfil | Bytes runtime | Debit / credit / steps final |', '|---|---|---:|---|']
    for name, case in result['cases'].items():
        for profile, row in case['profiles'].items():
            s = row['final_state']
            text.append(f"| {name} | {profile} | {row['runtime_bytes']} | {s['debit']} / {s['credit']} / {s['steps']} |")
    text += ['', 'Se comparan balances, nonces, almacenamiento completo del perfil, retornos y resultados de llamadas.',
             'Bytecode, hash del código y raíz del estado no se exigen iguales entre perfiles: los bytes compilados difieren.',
             'Cada constructor sí debe producir su propio runtime y cada llamada conserva su gas límite.',
             'No se mide ni promete igualdad del consumo de gas. El ensayo incluye agotamiento con un gas.',
             'La prueba formal de la fuente NO se transfiere como garantía del bytecode optimizado.',
             'Requiere el paquete de aceptación nativa original y la huella de código externa.',
             'Los casos son conocidos. No prueba equivalencia universal, seguridad ni vulnerabilidades nuevas.', '']
    return {'variants.json': canonical(execution), 'comparison.json': canonical(result),
            'audit.json': canonical({'events': [asdict(e) for e in audit.entries]}), 'REVIEW.md': '\n'.join(text).encode()}


def create(acceptance: Path, solc: Path, evm_path: Path, expected: str, out: Path) -> dict:
    need(not out.exists() and not out.is_symlink() and not out.resolve().is_relative_to(ROOT.parent) and
         not out.resolve().is_relative_to(acceptance.resolve()) and
         not acceptance.resolve().is_relative_to(out.resolve()), 'NEW_SEPARATE_OUTPUT_REQUIRED')
    result = execute(acceptance, solc, evm_path, expected)
    files = documents(result, datetime.now(timezone.utc).isoformat())
    write_new_bundle(out, files)
    return strict_json(files['comparison.json'])


def replay(root: Path, acceptance: Path, solc: Path, evm_path: Path, expected: str) -> dict:
    need(not root.is_symlink(), 'BUNDLE_ROOT_SYMLINK')
    marker = strict_json(read_artifact(root, 'COMPLETE.json'))
    need(set(marker) == {'schema_version', 'sha256'} and type(marker['schema_version']) is int and
         marker['schema_version'] == 1 and type(marker['sha256']) is dict and set(marker['sha256']) == FILES,
         'BUNDLE_MANIFEST')
    need({p.name for p in root.iterdir()} == FILES | {'COMPLETE.json'}, 'BUNDLE_INVENTORY')
    original = {n: read_artifact(root, n) for n in FILES}
    need(all(sha(b) == marker['sha256'][n] for n, b in original.items()), 'BUNDLE_HASH')
    at = strict_json(original['comparison.json']).get('created_at')
    # Never execute code, settings or calldata from original/variants.json.
    actual = execute(acceptance, solc, evm_path, expected)
    need(original == documents(actual, at), 'COMPILER_VARIANT_REPLAY_MISMATCH')
    need(all(read_artifact(root, n) == raw for n, raw in original.items()) and
         read_artifact(root, 'COMPLETE.json') == canonical(marker), 'BUNDLE_CHANGED_DURING_REPLAY')
    return strict_json(original['comparison.json'])


def main(argv: list[str] | None = None) -> int:
    p = PrivateArgumentParser(description='Compare fixed OWNED codegen controls; no targets or arbitrary sources')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('review-compiler-variants').add_argument('--out', type=Path, required=True)
    sub.add_parser('replay-compiler-variants').add_argument('--bundle', type=Path, required=True)
    for parser in sub.choices.values():
        for key in ('acceptance', 'solc', 'evm'):
            parser.add_argument('--' + key, type=Path, required=True)
        parser.add_argument('--expected-source', required=True)
    args = p.parse_args(argv)
    try:
        r = (create(args.acceptance, args.solc, args.evm, args.expected_source, args.out)
             if args.command == 'review-compiler-variants' else
             replay(args.bundle, args.acceptance, args.solc, args.evm, args.expected_source))
        print(json.dumps({k: r[k] for k in ('status', 'source_digest', 'constructors', 'message_calls',
                                          'independent_evm_used', 'vulnerability_confirmed')}))
        return 0
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, RecursionError, OverflowError):
        print(json.dumps({'status': 'COMPILER_VARIANT_REVIEW_BLOCKED', 'vulnerability_confirmed': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
