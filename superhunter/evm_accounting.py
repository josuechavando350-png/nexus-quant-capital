"""Fixed owned EVM controls -> observed committed storage -> exact unit equations.

Not a token adapter, financial loss estimator, arbitrary contract executor or
exploit planner. Native runs/replays regenerate ONLY the existing fixed controls.
Pure derivation rechecks captured observations but does not authenticate execution.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import json

from . import evm_execution as evm, balance_reconciliation as accounting
from .native_runtime import load_components
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = 'fixed-evm-committed-internal-units-v1'
UNIT = 'owned-control-integer-unit-not-a-token'
FILES = {'effects.json', 'audit.json', 'REVIEW.md'} | {'evm--' + n for n in evm.FILES}
IDENTITY_FILES = ('evm_accounting.py', 'balance_reconciliation.py', 'safe_io.py', 'privacy.py')


class EffectsError(ValueError):
    """Only stable codes, never raw input, appear in CLI errors."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise EffectsError(code)


def identity() -> dict:
    return {'sources_sha256': {n: evm.sha(read_artifact(ROOT, n)) for n in IDENTITY_FILES},
            'execution_engine': evm.engine_identity()}


def classify(observed: dict) -> str:
    """Decide from raw EVM error/return, NOT from the supplied model verdict."""
    if observed['error'] is None and observed['return_data'] == '0x':
        return 'COMMITTED'
    if observed['error'] == 'execution reverted':
        if observed['return_data'] == evm.PANIC_ASSERT:
            return 'ASSERTION_REVERT'
        if observed['return_data'] == '0x':
            return 'PRECONDITION_REVERT'
    if observed['error'] == 'out of gas' and observed['return_data'] == '0x':
        return 'RESOURCE_EXHAUSTED'
    raise EffectsError('UNSUPPORTED_FIXED_CALL_OUTCOME')


def _balances(state: dict) -> dict:
    return {k: str(state[k]) for k in ('debit', 'credit')}


def _transfer(index: int, amount: int) -> list[dict]:
    return [] if amount == 0 else [{'id': f'call-{index}', 'from': 'debit',
                                   'to': 'credit', 'amount_units': str(amount)}]


def derive(execution: dict, at: str) -> dict:
    """Project fresh/captured fixed execution; no new native execution here.

    Intent comes from the bound source/calldata, never from fitting a movement to
    the observed delta. A non-successful call contributes NO transfer. Observed
    before/after values are decoded again from original EVM stdout/storage.
    """
    engine = identity()
    native = evm.result_from(execution, at)  # Checks ALL calls/constructors and code bindings.
    need(canonical(execution['engine']) == canonical(engine['execution_engine']), 'STALE_EVM_ENGINE')
    cases = {}; outcomes = Counter(); total_rows = 0
    for name in evm.builds.formal.NAMES:
        case = execution['cases'][name]
        build = execution['builds']['cases'][name]
        contract = strict_json(build['output_utf8'])['contracts'][evm.builds.SOURCE_FILE][evm.builds.CONTRACT]
        birth = evm.parse_run(case['constructor']['stdout_utf8'].encode())
        initial = evm.decode_state(birth['alloc'], contract)
        before = initial
        before_alloc = birth['alloc']
        journal, transfers = [], []
        for index, call in enumerate(case['calls']):
            parsed = evm.parse_run(call['execution']['stdout_utf8'].encode())
            after = evm.decode_state(parsed['alloc'], contract)
            status = classify(parsed)
            quantity = evm.STEPS[index][0]  # Fixed intent, already bound to calldata by result_from.
            amount = quantity if status == 'COMMITTED' else 0
            expected_transfers = _transfer(index, amount)
            if status != 'COMMITTED':
                need(canonical(before_alloc) == canonical(parsed['alloc']), 'FAILED_CALL_CHANGED_ALLOC')
            equations = accounting.reconcile_internal_units(_balances(before), _balances(after), expected_transfers)
            need(equations['status'] == 'UNIT_BALANCES_RECONCILED', 'EVM_UNEXPLAINED_UNIT_CHANGE')
            entry = {'index': index, 'outcome': status, 'requested_units': str(quantity),
                     'applied_transfer_units': str(amount), 'transfers': expected_transfers,
                     'before_units': _balances(before), 'after_units': _balances(after),
                     'before_alloc_sha256': evm.sha(canonical(before_alloc)),
                     'after_alloc_sha256': evm.sha(canonical(parsed['alloc'])),
                     'raw_output_sha256': evm.sha(call['execution']['stdout_utf8'].encode()),
                     'state_before_steps': before['steps'], 'state_after_steps': after['steps'],
                     'equations': equations,
                     'discarded_model_state': call['reference'].get('uncommitted_model_state'),
                     'discarded_state_is_observed_storage': False}
            journal.append(entry); transfers.extend(expected_transfers)
            total_rows += len(equations['rows']); outcomes[status] += 1
            before, before_alloc = after, parsed['alloc']
        net = accounting.reconcile_internal_units(_balances(initial), _balances(before), transfers)
        need(net['status'] == 'UNIT_BALANCES_RECONCILED', 'AGGREGATE_UNIT_MISMATCH')
        cases[name] = {'unit': UNIT, 'constructor_units': _balances(initial),
                       'final_units': _balances(before), 'journal': journal,
                       'applied_transfers': transfers,
                       'applied_transfer_units': str(sum(int(t['amount_units']) for t in transfers)),
                       'equations': net, 'source_property_status': case['source_property_status'],
                       'gas_cost_usd': None, 'financial_loss_usd': None,
                       'source_counterexample_is_financial_loss': False}
    need(dict(outcomes) == native['call_outcomes'], 'OUTCOME_COVERAGE_MISMATCH')
    need(identity() == engine, 'ENGINE_CHANGED_DURING_DERIVATION')
    return {'schema_version': 1, 'profile': PROFILE, 'status': 'FIXED_EVM_UNIT_EFFECTS_RECONCILED',
            'created_at': at, 'engine': engine, 'execution_sha256': evm.sha(canonical(execution)),
            'unit': UNIT, 'cases': cases, 'call_outcomes': dict(sorted(outcomes.items())),
            'calls_checked': sum(outcomes.values()), 'per_call_cells_checked': total_rows,
            'transfer_count': sum(len(c['applied_transfers']) for c in cases.values()),
            'failed_calls_without_transfer': sum(v for k, v in outcomes.items() if k != 'COMMITTED'),
            'derivation_reran_evm': False, 'native_replay_required_for_execution_claim': True,
            'monetary_valuation_usd': None, 'gas_cost_measured': False, 'token_balances_measured': False,
            'vulnerability_confirmed': False, 'all_paths_proved': False, 'independent_evm_used': False,
            'network_used': False, 'platform_complete': False}


def render(result: dict) -> bytes:
    lines = ['# Efectos persistentes de los controles EVM', '',
             'Unidades internas de contratos propios; NO tokens, dinero ni beneficios.',
             f"Llamadas comprobadas: {result['calls_checked']}.",
             f"Transferencias del modelo aplicadas: {result['transfer_count']}.",
             f"Llamadas fallidas sin transferencia aplicada: {result['failed_calls_without_transfer']}.", '']
    for name, case in result['cases'].items():
        lines += [f"{name}: debit={case['final_units']['debit']}, credit={case['final_units']['credit']}; "
                  f"unidades trasladadas={case['applied_transfer_units']}."]
    lines += ['', 'La derivación por sí sola no acredita ejecución: replay vuelve a compilar y ejecutar.',
              'Las intenciones proceden del código/calldata fijo, no de ajustar movimientos a los saldos.',
              'Un contraejemplo de aserción revertida no equivale a una pérdida persistente.',
              'Agotamiento de gas no demuestra seguridad. No se cuantifica costo de gas ni USD.',
              'Solo tres controles conocidos; no prueba ausencia de fallos ni usa una EVM independiente.', '']
    return '\n'.join(lines).encode()


def documents(execution: dict, at: str) -> dict[str, bytes]:
    result = derive(execution, at)
    audit = load_components().audit.AuditLog(clock=lambda: at)
    audit.append('evm.units.start', {'profile': PROFILE, 'execution_sha256': result['execution_sha256']})
    for name, case in result['cases'].items():
        for entry in case['journal']:
            audit.append('evm.units.call', {'case': name, 'index': entry['index'],
                                          'entry_sha256': evm.sha(canonical(entry))})
        audit.append('evm.units.case', {'case': name, 'equations_sha256': evm.sha(canonical(case['equations']))})
    audit.append('evm.units.complete', {'result_sha256': evm.sha(canonical(result))})
    audit.assert_intact()
    files = {'evm--' + n: b for n, b in evm.documents(execution, at).items()}
    files.update({'effects.json': canonical(result),
                  'audit.json': canonical({'events': [asdict(e) for e in audit.entries]}),
                  'REVIEW.md': render(result)})
    return files


def _summary(result: dict, replayed: bool) -> dict:
    return {k: result[k] for k in ('status', 'calls_checked', 'transfer_count',
                                   'failed_calls_without_transfer', 'vulnerability_confirmed')} | {
            'native_execution_performed_here': True, 'same_engines_replayed': replayed,
            'monetary_valuation_usd': None}


def create(solc: Path, evm_path: Path, out: Path) -> dict:
    need(not out.exists() and not out.is_symlink() and not out.resolve().is_relative_to(ROOT.parent),
         'NEW_PRIVATE_OUTPUT_REQUIRED')
    before = identity()
    # No arbitrary candidate, calldata, source or program is accepted by this entrypoint.
    execution = evm.execute(solc, evm_path)
    at = datetime.now(timezone.utc).isoformat()
    files = documents(execution, at)
    need(identity() == before, 'ENGINE_CHANGED_DURING_EXECUTION')
    write_new_bundle(out, files)
    return _summary(strict_json(files['effects.json']), False)


def replay(root: Path, solc: Path, evm_path: Path) -> dict:
    need(not root.is_symlink(), 'BUNDLE_ROOT_SYMLINK')
    marker = strict_json(read_artifact(root, 'COMPLETE.json'))
    need(set(marker) == {'schema_version', 'sha256'} and type(marker['schema_version']) is int
         and marker['schema_version'] == 1 and type(marker['sha256']) is dict
         and set(marker['sha256']) == FILES, 'BUNDLE_MANIFEST')
    need({p.name for p in root.iterdir()} == FILES | {'COMPLETE.json'}, 'BUNDLE_FILES')
    data = {n: read_artifact(root, n) for n in FILES}
    need(all(evm.sha(b) == marker['sha256'][n] for n, b in data.items()), 'BUNDLE_HASH')
    # Stored claims never become inputs to native execution.
    at = strict_json(data['effects.json']).get('created_at')
    need(type(at) is str and datetime.fromisoformat(at).tzinfo is not None, 'RESULT_TIME')
    before = identity()
    execution = evm.execute(solc, evm_path)
    need(data == documents(execution, at), 'NATIVE_ACCOUNTING_REPLAY_MISMATCH')
    need(identity() == before, 'ENGINE_CHANGED_DURING_EXECUTION')
    return _summary(strict_json(data['effects.json']), True)


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Fixed owned EVM state to nonmonetary accounting; no arbitrary targets')
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run-evm-accounting'); run.add_argument('--out', type=Path, required=True)
    verify = sub.add_parser('replay-evm-accounting'); verify.add_argument('--bundle', type=Path, required=True)
    for p in (run, verify):
        p.add_argument('--solc', type=Path, required=True); p.add_argument('--evm', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = create(args.solc, args.evm, args.out) if args.command == 'run-evm-accounting' else replay(args.bundle, args.solc, args.evm)
        print(json.dumps(result)); return 0
    except (ValueError, OSError, KeyError, TypeError, OverflowError, RecursionError):
        print(json.dumps({'status': 'EVM_ACCOUNTING_BLOCKED', 'vulnerability_confirmed': False})); return 2


if __name__ == '__main__':
    raise SystemExit(main())
