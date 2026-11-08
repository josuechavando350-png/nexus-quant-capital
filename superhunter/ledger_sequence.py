"""Ordered, exact checks of supplied transfer ledgers; no EVM or target execution.

The profile models individually applied uint256 transfers. It does not model
credit accounts, rebases, fee-on-transfer tokens, callbacks or hidden state.
An order declaration is not an authenticated transaction trace. Both arithmetic
paths share these assumptions and must agree before evidence is emitted.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from decimal import Context, Decimal, Inexact, localcontext
import hashlib
import json
from pathlib import Path
import re
import uuid

from . import balance_reconciliation as accounting
from .native_runtime import load_components, source_inventory
from .privacy import PrivateArgumentParser
from .safe_io import MAX_BYTES, canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = 'declared-ordered-uint256-transfers-v1'
LIMIT = 2**256 - 1
FILES = {'ledger.json', 'sequence.json', 'result.json', 'audit.json', 'receipt.json', 'REVIEW.md'}
SOURCE_FILES = ('ledger_sequence.py', 'balance_reconciliation.py', 'native_runtime.py',
                'safe_io.py', 'privacy.py')
HEX = re.compile(r'[0-9a-f]{64}\Z')


class SequenceError(ValueError):
    """Fixed diagnostics only; no supplied identifiers or amounts in errors."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise SequenceError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def fields(value: object, expected: set[str], code: str) -> None:
    need(type(value) is dict and set(value) == expected, code)


def pin(value: object) -> None:
    need(type(value) is str and HEX.fullmatch(value) is not None, 'INVALID_EXTERNAL_PIN')


def identity() -> dict:
    return {'sources': {p: sha(read_artifact(ROOT, p)) for p in SOURCE_FILES},
            'native_sources': source_inventory()}


def validate(ledger: object, sequence: object) -> tuple[dict, dict]:
    data = accounting.validate(ledger)
    fields(sequence, {'schema_version', 'profile', 'ledger_sha256', 'order_coverage',
                      'steps_budget', 'entries'}, 'SEQUENCE_SCHEMA')
    need(type(sequence['schema_version']) is int and sequence['schema_version'] == 1, 'SEQUENCE_VERSION')
    need(sequence['profile'] == PROFILE, 'UNSUPPORTED_SEQUENCE_PROFILE')
    pin(sequence['ledger_sha256'])
    need(sequence['ledger_sha256'] == sha(canonical(data)), 'LEDGER_IDENTITY_MISMATCH')
    need(sequence['order_coverage'] in ('declared_total', 'unknown'), 'ORDER_COVERAGE')
    budget = sequence['steps_budget']
    need(type(budget) is int and 0 <= budget <= accounting.MAX_FLOWS, 'STEP_BUDGET')
    rows = sequence['entries']
    need(type(rows) is list and len(rows) <= accounting.MAX_FLOWS, 'ORDER_LIMIT')
    ids, positions = set(), set()
    for row in rows:
        fields(row, {'flow_id', 'position'}, 'ORDER_ENTRY_SCHEMA')
        accounting.identifier(row['flow_id'])
        need(row['flow_id'] not in ids, 'DUPLICATE_FLOW_ORDER')
        need(type(row['position']) is int and 0 <= row['position'] < 2**64, 'ORDER_POSITION')
        need(row['position'] not in positions, 'AMBIGUOUS_ORDER_POSITION')
        ids.add(row['flow_id']); positions.add(row['position'])
    need(ids == {flow['id'] for flow in data['flows']}, 'ORDER_MUST_COVER_EXACT_FLOW_SET')
    need(len(canonical(sequence)) <= MAX_BYTES, 'SEQUENCE_SIZE')
    return data, deepcopy(sequence)


def _ordered(ledger: dict, sequence: dict) -> list[tuple[dict, dict]]:
    flows = {row['id']: row for row in ledger['flows']}
    return [(row, flows[row['flow_id']]) for row in sorted(sequence['entries'], key=lambda r: r['position'])]


def _state_json(state: dict) -> dict:
    return {asset: {account: str(value) for account, value in sorted(balances.items())}
            for asset, balances in sorted(state.items())}


def _step(index: int, order: dict, flow: dict, before: dict, after: dict,
          source_balance: int | None, destination_balance: int | None,
          reasons: list[str]) -> dict:
    return {'index': index, 'flow_id': flow['id'], 'position': order['position'],
            'flow_sha256': sha(canonical(flow)), 'before_sha256': sha(canonical(before)),
            'after_sha256': sha(canonical(after)), 'source_balance_atomic':
            None if source_balance is None else str(source_balance),
            'destination_balance_atomic': None if destination_balance is None else str(destination_balance),
            'applied': not reasons, 'contradictions': reasons}


def _primary(ledger: dict, sequence: dict) -> dict:
    """Mutable integer state, preconditions checked before applying each transfer."""
    state = {a: {u: int(v) for u, v in balances.items()} for a, balances in ledger['before'].items()}
    trace = []
    if sequence['order_coverage'] == 'declared_total':
        for index, (order, flow) in enumerate(_ordered(ledger, sequence)[:sequence['steps_budget']]):
            asset, src, dst, amount = flow['asset'], flow['from'], flow['to'], int(flow['amount_atomic'])
            before = _state_json(state)
            source_balance = None if src is None else state[asset][src]
            target_balance = None if dst is None else state[asset][dst]
            reasons = []
            if src is not None and source_balance < amount:
                reasons.append('INSUFFICIENT_DECLARED_BALANCE')
            if dst is not None and target_balance + amount > LIMIT:
                reasons.append('UINT256_BALANCE_OVERFLOW')
            if not reasons:
                if src is not None:
                    state[asset][src] -= amount
                if dst is not None:
                    state[asset][dst] += amount
            trace.append(_step(index, order, flow, before, _state_json(state),
                               source_balance, target_balance, reasons))
            if reasons:
                break  # Do not invent execution after a failed prefix.
    return {'trace': trace, 'last_supported_state': _state_json(state)}


def _reference(ledger: dict, sequence: dict) -> dict:
    """Independent arithmetic path: opening + cumulative credits - cumulative debits.

    No call to _primary; exact Decimal context is fixed, not inherited. This is
    arithmetic cross-checking of the same declared model, not independent EVM.
    """
    with localcontext(Context(prec=128, Emin=-999999, Emax=999999)) as context:
        context.traps[Inexact] = True
        opening = {(a, u): Decimal(v) for a, balances in ledger['before'].items() for u, v in balances.items()}
        credits = {cell: Decimal(0) for cell in opening}
        debits = {cell: Decimal(0) for cell in opening}

        def balances() -> dict:
            result = {a: {} for a in sorted(ledger['assets'])}
            for (a, u), value in sorted(opening.items()):
                result[a][u] = str(int(value + credits[a, u] - debits[a, u]))
            return result

        trace = []
        if sequence['order_coverage'] == 'declared_total':
            flow_map = {flow['id']: flow for flow in ledger['flows']}
            ordered = sorted(sequence['entries'], key=lambda row: row['position'])
            for index, order in enumerate(ordered[:sequence['steps_budget']]):
                flow = flow_map[order['flow_id']]
                a, src, dst, value = flow['asset'], flow['from'], flow['to'], Decimal(flow['amount_atomic'])
                before = balances()
                left = None if src is None else opening[a, src] + credits[a, src] - debits[a, src]
                right = None if dst is None else opening[a, dst] + credits[a, dst] - debits[a, dst]
                reasons = []
                if left is not None and left - value < 0:
                    reasons.append('INSUFFICIENT_DECLARED_BALANCE')
                if right is not None and right + value >= Decimal(2)**256:
                    reasons.append('UINT256_BALANCE_OVERFLOW')
                if not reasons:
                    if src is not None:
                        debits[a, src] += value
                    if dst is not None:
                        credits[a, dst] += value
                trace.append(_step(index, order, flow, before, balances(),
                                   None if left is None else int(left), None if right is None else int(right), reasons))
                if reasons:
                    break
        return {'trace': trace, 'last_supported_state': balances()}


def analyze(ledger: object, sequence: object) -> dict:
    data, order = validate(ledger, sequence)
    totals = accounting.reconcile(data)  # Both accounting implementations execute.
    primary, reference = _primary(data, order), _reference(data, order)
    need(canonical(primary) == canonical(reference), 'REPLAY_IMPLEMENTATIONS_DISAGREE')
    trace, count = primary['trace'], len(data['flows'])
    applied = sum(row['applied'] for row in trace)
    first_bad = next((row for row in trace if row['contradictions']), None)
    complete = order['order_coverage'] == 'declared_total' and applied == count and first_bad is None
    final_differences = []
    if complete:
        for a in sorted(data['assets']):
            for u in sorted(data['accounts']):
                calculated, declared = primary['last_supported_state'][a][u], data['after'][a][u]
                if calculated != declared:
                    final_differences.append({'asset': a, 'account': u, 'calculated_atomic': calculated,
                                              'declared_atomic': declared, 'delta_atomic': str(int(declared) - int(calculated))})
    reasons = []
    if data['flow_coverage'] != 'declared_complete':
        reasons.append('FLOW_COVERAGE_INCOMPLETE')
    if order['order_coverage'] != 'declared_total':
        reasons.append('ORDER_UNKNOWN')
    if not complete and first_bad is None and order['order_coverage'] == 'declared_total':
        reasons.append('STEP_BUDGET_EXHAUSTED')
    status = ('LEDGER_SEQUENCE_INCONCLUSIVE' if reasons else
              'LEDGER_SEQUENCE_CONTRADICTION' if first_bad or final_differences else
              'LEDGER_SEQUENCE_CONSISTENT')
    result = {'schema_version': 1, 'profile': PROFILE, 'status': status,
              'ledger_sha256': sha(canonical(data)), 'sequence_sha256': sha(canonical(order)),
              'case_id': data['case_id'], 'subject': data['subject'],
              'aggregate_status': totals['status'], 'aggregate_unexplained_cells': totals['unexplained_cells'],
              'steps_declared': count, 'steps_attempted': len(trace), 'steps_applied': applied,
              'steps_not_attempted': count - len(trace), 'full_replay_complete': complete,
              'stop_after_contradiction': first_bad is not None,
              'first_contradiction': first_bad, 'final_differences': final_differences,
              'inconclusive_reasons': reasons, **primary,
              'arithmetic_crosscheck_passed': True, 'flow_coverage_authenticated': False,
              'order_authenticated': False, 'chain_state_authenticated': False,
              'execution_verified': False, 'evm_executed': False, 'causal_impact_proven': False,
              'vulnerability_confirmed': False, 'human_review_required': True}
    need(len(canonical(result)) <= MAX_BYTES, 'RESULT_TOO_LARGE')
    return result


def render(result: dict) -> bytes:
    # Deliberately no user-supplied account IDs, descriptions or amounts in the summary.
    text = ['# Comprobación de secuencia contable', '', 'Estado: ' + result['status'],
            f"Movimientos declarados: {result['steps_declared']}; intentados: {result['steps_attempted']}; "
            f"aplicados en el modelo: {result['steps_applied']}; no examinados: {result['steps_not_attempted']}.",
            'Los dos cálculos aritméticos coinciden bajo el perfil declarado.',
            'Se detiene en la primera precondición incumplida; no inventa el estado del resto.', '',
            'Un saldo final correcto no garantiza un orden intermedio posible.',
            'La cobertura y el orden son declaraciones, no trazas autenticadas.',
            'No se ejecutó EVM, red, contrato, préstamo ni explotación. No se confirma una vulnerabilidad.',
            'El perfil no representa deudas, rebases ni tokens con reglas de transferencia especiales.',
            'El paquete completo es privado. La revisión humana sigue siendo necesaria.', '']
    return '\n'.join(text).encode()


def _events(result: dict) -> list[tuple[str, dict]]:
    events = [('ledger.sequence.start', {'ledger_sha256': result['ledger_sha256'],
                                       'sequence_sha256': result['sequence_sha256']})]
    events += [('ledger.sequence.step', {'index': row['index'], 'step_sha256': sha(canonical(row))})
               for row in result['trace']]
    events.append(('ledger.sequence.complete', {'result_sha256': sha(canonical(result)),
                                              'status': result['status'], 'vulnerability_confirmed': False}))
    return events


def create(ledger_raw: bytes, sequence_raw: bytes, out: Path, *, ledger_pin: str, sequence_pin: str) -> dict:
    pin(ledger_pin); pin(sequence_pin)
    need(type(ledger_raw) is bytes and type(sequence_raw) is bytes and
         max(len(ledger_raw), len(sequence_raw)) <= MAX_BYTES, 'INPUT_SIZE')
    data, order = strict_json(ledger_raw), strict_json(sequence_raw)
    need(sha(canonical(data)) == ledger_pin and sha(canonical(order)) == sequence_pin, 'EXTERNAL_IDENTITY_MISMATCH')
    need(not out.exists() and not out.is_symlink(), 'OUTPUT_EXISTS')
    need(not out.resolve().is_relative_to(ROOT.parent), 'OUTPUT_INSIDE_CODE')
    before = identity(); result = analyze(data, order)
    native = load_components(); audit = native.audit.AuditLog(); run_id = str(uuid.uuid4())
    for event, values in _events(result):
        audit.append(event, values)
    audit.assert_intact()
    receipt = {'schema_version': 1, 'run_id': run_id, 'engine': before, 'audit_head': audit.head}
    need(identity() == before, 'ENGINE_CHANGED')
    write_new_bundle(out, {'ledger.json': ledger_raw, 'sequence.json': sequence_raw,
                          'result.json': canonical(result), 'audit.json': canonical({'entries': [asdict(e) for e in audit.entries]}),
                          'receipt.json': canonical(receipt), 'REVIEW.md': render(result)})
    return verify(out, ledger_pin=ledger_pin, sequence_pin=sequence_pin)


def verify(root: Path, *, ledger_pin: str, sequence_pin: str) -> dict:
    pin(ledger_pin); pin(sequence_pin)
    need(not root.is_symlink(), 'BUNDLE_ROOT_SYMLINK')
    marker = strict_json(read_artifact(root, 'COMPLETE.json'))
    fields(marker, {'schema_version', 'sha256'}, 'MANIFEST_SCHEMA')
    need(type(marker['schema_version']) is int and marker['schema_version'] == 1, 'MANIFEST_VERSION')
    fields(marker['sha256'], FILES, 'MANIFEST_FILES')
    need({p.name for p in root.iterdir()} == FILES | {'COMPLETE.json'}, 'UNDECLARED_BUNDLE_FILES')
    raw = {name: read_artifact(root, name) for name in sorted(FILES)}
    need(all(sha(v) == marker['sha256'][k] for k, v in raw.items()), 'ARTIFACT_CHANGED')
    before = identity()
    ledger, sequence = strict_json(raw['ledger.json']), strict_json(raw['sequence.json'])
    need(sha(canonical(ledger)) == ledger_pin and sha(canonical(sequence)) == sequence_pin, 'EXTERNAL_IDENTITY_MISMATCH')
    result = analyze(ledger, sequence)
    need(raw['result.json'] == canonical(result) and raw['REVIEW.md'] == render(result), 'RESULT_REPLAY_MISMATCH')
    receipt = strict_json(raw['receipt.json'])
    fields(receipt, {'schema_version', 'run_id', 'engine', 'audit_head'}, 'RECEIPT_SCHEMA')
    need(type(receipt['schema_version']) is int and receipt['schema_version'] == 1, 'RECEIPT_VERSION')
    need(type(receipt['run_id']) is str and str(uuid.UUID(receipt['run_id'])) == receipt['run_id'], 'RECEIPT_ID')
    need(canonical(receipt['engine']) == canonical(before), 'STALE_ENGINE')
    log = strict_json(raw['audit.json']); fields(log, {'entries'}, 'AUDIT_SCHEMA')
    expected = _events(result)
    need(type(log['entries']) is list and len(log['entries']) == len(expected), 'AUDIT_COVERAGE')
    prev, timestamp = '0' * 64, None
    native = load_components()
    for index, (entry, (event, values)) in enumerate(zip(log['entries'], expected)):
        fields(entry, {'index', 'timestamp', 'event', 'data', 'prev_hash', 'hash'}, 'AUDIT_ENTRY')
        need(type(entry['index']) is int and entry['index'] == index and entry['event'] == event and
             canonical(entry['data']) == canonical(values), 'AUDIT_SEMANTICS')
        need(type(entry['timestamp']) is str, 'AUDIT_TIME')
        current = datetime.fromisoformat(entry['timestamp'])
        need(current.tzinfo is not None and (timestamp is None or current >= timestamp), 'AUDIT_TIME')
        need(entry['prev_hash'] == prev and native.audit.AuditEntry(**entry).recompute() == entry['hash'], 'AUDIT_CHAIN')
        prev, timestamp = entry['hash'], current
    need(prev == receipt['audit_head'] and identity() == before, 'AUDIT_OR_ENGINE_CHANGED')
    return {'status': result['status'], 'ledger_sha256': result['ledger_sha256'],
            'sequence_sha256': result['sequence_sha256'], 'steps_declared': result['steps_declared'],
            'steps_attempted': result['steps_attempted'], 'steps_applied': result['steps_applied'],
            'steps_not_attempted': result['steps_not_attempted'], 'full_replay_complete': result['full_replay_complete'],
            'aggregate_status': result['aggregate_status'], 'order_authenticated': False,
            'execution_verified': False, 'vulnerability_confirmed': False}


def example_input() -> tuple[dict, dict]:
    """Own synthetic transfer ledger: no contract, address target or exploit."""
    ledger = accounting.example_input()
    ledger['case_id'] = 'synthetic.ordered'
    ledger['assets'] = {'usd6': ledger['assets']['usd6']}
    ledger['prices'] = {}  # Monetary valuation is unrelated to chronological validity.
    ledger['before'] = {'usd6': {'vault': '10', 'alice': '0', 'fee': '0'}}
    ledger['after'] = {'usd6': {'vault': '3', 'alice': '0', 'fee': '7'}}
    ledger['flows'] = [{'id': 'fund', 'asset': 'usd6', 'from': 'vault', 'to': 'alice', 'amount_atomic': '7'},
                       {'id': 'send', 'asset': 'usd6', 'from': 'alice', 'to': 'fee', 'amount_atomic': '7'}]
    sequence = {'schema_version': 1, 'profile': PROFILE, 'ledger_sha256': sha(canonical(ledger)),
                'order_coverage': 'declared_total', 'steps_budget': 2,
                'entries': [{'flow_id': 'fund', 'position': 0}, {'flow_id': 'send', 'position': 1}]}
    return ledger, sequence


CONTROL_NAMES = ('ordered', 'funds_late', 'incomplete', 'budget')
CONTROL_FILES = tuple(sorted([f'{name}/{file}' for name in CONTROL_NAMES for file in FILES | {'COMPLETE.json'}] +
                             ['summary/COMPLETE.json', 'summary/result.json']))


def controls() -> dict[str, tuple[dict, dict]]:
    ledger, good = example_input()
    wrong = deepcopy(good)
    wrong['entries'][0]['position'], wrong['entries'][1]['position'] = 1, 0
    missing = deepcopy(ledger); missing['flow_coverage'] = 'declared_incomplete'
    unknown = deepcopy(wrong); unknown['ledger_sha256'] = sha(canonical(missing))
    budget = deepcopy(good); budget['steps_budget'] = 1
    return {'ordered': (ledger, good), 'funds_late': (ledger, wrong),
            'incomplete': (missing, unknown), 'budget': (ledger, budget)}


def _summary(results: dict) -> dict:
    need(tuple(results) == CONTROL_NAMES, 'CONTROL_INVENTORY')
    for name, status, applied in (('ordered', 'LEDGER_SEQUENCE_CONSISTENT', 2),
                                  ('funds_late', 'LEDGER_SEQUENCE_CONTRADICTION', 0),
                                  ('incomplete', 'LEDGER_SEQUENCE_INCONCLUSIVE', 0),
                                  ('budget', 'LEDGER_SEQUENCE_INCONCLUSIVE', 1)):
        need(results[name]['status'] == status and results[name]['steps_applied'] == applied, 'CONTROL_FAILED')
    return {'schema_version': 1, 'status': 'LOCAL_SEQUENCE_CONTROLS_PASS', 'cases_checked': 4,
            'results': results, 'fixture_only': True, 'evm_executed': False, 'vulnerability_confirmed': False}


def run_controls(out: Path) -> dict:
    need(not out.exists() and not out.is_symlink(), 'OUTPUT_EXISTS')
    need(not out.resolve().is_relative_to(ROOT.parent), 'OUTPUT_INSIDE_CODE')
    out.parent.mkdir(parents=True, exist_ok=True); out.mkdir(mode=0o700)
    results = {}
    for name, (ledger, order) in controls().items():
        results[name] = create(canonical(ledger), canonical(order), out / name,
                               ledger_pin=sha(canonical(ledger)), sequence_pin=sha(canonical(order)))
    write_new_bundle(out / 'summary', {'result.json': canonical(_summary(results))})
    return verify_controls(out)


def verify_controls(root: Path) -> dict:
    need({p.name for p in root.iterdir()} == set(CONTROL_NAMES) | {'summary'}, 'CONTROL_DIRECTORY_SET')
    results = {}
    for name, (ledger, order) in controls().items():
        need(read_artifact(root / name, 'ledger.json') == canonical(ledger) and
             read_artifact(root / name, 'sequence.json') == canonical(order), 'CONTROL_INPUT_CHANGED')
        results[name] = verify(root / name, ledger_pin=sha(canonical(ledger)), sequence_pin=sha(canonical(order)))
    expected = _summary(results)
    marker = strict_json(read_artifact(root / 'summary', 'COMPLETE.json'))
    fields(marker, {'schema_version', 'sha256'}, 'CONTROL_MANIFEST')
    need(type(marker['schema_version']) is int and marker['schema_version'] == 1, 'CONTROL_MANIFEST')
    fields(marker['sha256'], {'result.json'}, 'CONTROL_MANIFEST')
    need({p.name for p in (root / 'summary').iterdir()} == {'COMPLETE.json', 'result.json'}, 'CONTROL_SUMMARY_FILES')
    raw = read_artifact(root / 'summary', 'result.json')
    need(raw == canonical(expected) and sha(raw) == marker['sha256']['result.json'], 'CONTROL_RESULT_CHANGED')
    return expected


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Check a declared transfer order; no EVM, target execution or network')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('replay-ledger')
    make.add_argument('--ledger', type=Path, required=True)
    make.add_argument('--sequence', type=Path, required=True)
    make.add_argument('--out', type=Path, required=True)
    verify_parser = sub.add_parser('verify-ledger-replay')
    verify_parser.add_argument('--bundle', type=Path, required=True)
    for p in (make, verify_parser):
        p.add_argument('--ledger-sha256', required=True)
        p.add_argument('--sequence-sha256', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'replay-ledger':
            result = create(read_artifact(args.ledger.parent, args.ledger.name),
                            read_artifact(args.sequence.parent, args.sequence.name), args.out,
                            ledger_pin=args.ledger_sha256, sequence_pin=args.sequence_sha256)
        else:
            result = verify(args.bundle, ledger_pin=args.ledger_sha256, sequence_pin=args.sequence_sha256)
        print(json.dumps({k: result[k] for k in ('status', 'steps_attempted', 'steps_applied',
                                                'steps_not_attempted', 'execution_verified', 'vulnerability_confirmed')}))
        return 0 if result['status'] == 'LEDGER_SEQUENCE_CONSISTENT' else 1
    except (ValueError, OSError, TypeError, KeyError, AttributeError, RecursionError, ArithmeticError):
        print(json.dumps({'status': 'LEDGER_SEQUENCE_ERROR', 'execution_verified': False, 'vulnerability_confirmed': False}))
        return 2


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
