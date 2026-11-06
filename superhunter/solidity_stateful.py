"""Fixed, owned Solidity state-transition controls using real solc CHC and Z3.

Not an EVM, arbitrary-source analyzer, transaction planner or exploit workflow.
Only source strings generated below are compiled. All reference witnesses are
from finite-model search, NOT traces extracted from CHC or executed bytecode.
"""
from __future__ import annotations

from collections import deque
import ctypes as c
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from itertools import product
from pathlib import Path
import re
import json

from . import native_compile as compiler, smt_backend
from .native_runtime import load_components, source_inventory
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
NAMES = ('conservation', 'delayed_credit', 'unreachable')
ROLES = ('property', 'third_step_reachable')
BUDGETS = {'normal': 1_000_000, 'exhausted': 1}
OUTCOMES = ('SAFE', 'VIOLATED', 'UNKNOWN')
FILES = {'execution.json', 'result.json', 'audit.json', 'REVIEW.md'}
CODE = ('solidity_stateful.py', 'native_compile.py', 'solc_worker.py', 'smt_backend.py',
        'native_runtime.py', 'safe_io.py')
KEY = re.compile(r'0x[0-9a-f]{64}\Z')
MAX_QUERY = 150_000


class StateProofError(ValueError):
    """Fixed error codes, without user paths or compiler/solver payloads."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise StateProofError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def control_source(name: str, role: str) -> str:
    need(type(name) is str and name in NAMES, 'FIXED_CONTROL_REQUIRED')
    need(type(role) is str and role in ROLES, 'FIXED_ROLE_REQUIRED')
    guard = 'false' if name == 'unreachable' else 'steps < 3 && quantity <= debit'
    extra = 1 if name == 'delayed_credit' else 0
    assertion = 'debit + credit == 15' if role == 'property' else 'steps != 3'
    return ('// SPDX-License-Identifier: MIT\n'
            '// Own finite control: no tokens, addresses, external calls or funds.\n'
            'pragma solidity 0.8.30;\n'
            'contract StatefulConservation {\n'
            ' uint16 private debit = 15;\n'
            ' uint16 private credit = 0;\n'
            ' uint8 private steps = 0;\n'
            ' function move(uint8 quantity) public {\n'
            f'  require({guard});\n'
            '  debit -= quantity;\n'
            f'  credit += uint16(quantity) + (steps == 2 ? {extra} : 0);\n'
            '  steps++;\n'
            f'  assert({assertion});\n'
            ' }\n}\n')


def fixed_input(name: str, role: str, responses: dict | None = None) -> dict:
    data = {'language': 'Solidity', 'sources': {'State.sol': {'content': control_source(name, role)}},
            'settings': {'optimizer': {'enabled': False}, 'evmVersion': 'cancun',
                         'modelChecker': {'engine': 'chc', 'targets': ['assert'],
                             'solvers': ['smtlib2'], 'timeout': 3000, 'showProvedSafe': True,
                             'showUnproved': True, 'showUnsupported': True},
                         'outputSelection': {'*': {'': ['ast']}}}}
    if responses is not None:
        need(type(responses) is dict and len(responses) == 1, 'RESPONSE_SET')
        for key, value in responses.items():
            need(type(key) is str and KEY.fullmatch(key) is not None and
                 value in ('sat\n', 'unsat\n', 'unknown\n'), 'RESPONSE_PROFILE')
        data['auxiliaryInput'] = {'smtlib2responses': dict(responses)}
    return data


def check_query(query: str) -> None:
    need(type(query) is str and 0 < len(query.encode()) <= MAX_QUERY, 'QUERY_BUDGET')
    prefix = '(set-option :timeout 3000)\n(set-logic HORN)\n'
    need(query.startswith(prefix) and query.endswith('(check-sat)\n') and
         query.count('(check-sat)') == 1 and query.count('(set-option') == 1 and
         query.count('(set-logic') == 1, 'FIXED_HORN_QUERY_REQUIRED')
    need(not any(x in query for x in ('(exit', '(reset', '(include', '(get-', '(eval',
                                     ':output-channel', ':global-decls')), 'QUERY_COMMAND_PROFILE')
    # This is a narrow compiler-output check, not an arbitrary SMT parser/sandbox.


def solve(query: str, budget: str) -> dict:
    check_query(query)
    need(type(budget) is str and budget in BUDGETS, 'BUDGET_PROFILE')
    prefix = f'(set-option :rlimit {BUDGETS[budget]})\n(set-option :random-seed 0)\n'
    with smt_backend._LOCK:
        lib, identity = smt_backend._open_library()
        evaluate = smt_backend._bind(lib, 'Z3_eval_smtlib2_string', c.c_char_p, c.c_void_p, c.c_char_p)
        cfg = lib.Z3_mk_config()
        need(bool(cfg), 'Z3_CONFIG')
        try:
            ctx = lib.Z3_mk_context(cfg)
        finally:
            lib.Z3_del_config(cfg)
        need(bool(ctx), 'Z3_CONTEXT')
        errors = []
        handler = smt_backend._ERROR_HANDLER(lambda _ctx, code: errors.append(code))
        try:
            lib.Z3_set_error_handler(ctx, handler)
            answer = (evaluate(ctx, (prefix + query).encode()) or b'').decode('ascii')
            need(not errors and not lib.Z3_get_error_code(ctx), 'Z3_EXECUTION_ERROR')
            need(answer in ('sat\n', 'unsat\n', 'unknown\n'), 'Z3_RESPONSE_PROFILE')
        finally:
            lib.Z3_del_context(ctx)
    # HORN satisfiability has opposite polarity to the earlier BMC bug query.
    outcome = {'sat\n': 'SAFE', 'unsat\n': 'VIOLATED', 'unknown\n': 'UNKNOWN'}[answer]
    return {'response': answer, 'horn_satisfiability': answer.strip().upper(),
            'assertion_outcome': outcome, 'query_sha256': sha(query.encode()),
            'evaluated_sha256': sha((prefix + query).encode()), 'resource_prefix': prefix,
            'engine': identity, 'proof_certificate_independently_checked': False}


def _output(raw: bytes) -> dict:
    data = strict_json(raw)
    diagnostics = data.get('errors', [])
    need(type(diagnostics) is list and all(type(x) is dict for x in diagnostics), 'DIAGNOSTICS_SCHEMA')
    need(not any(x.get('severity') == 'error' for x in diagnostics), 'COMPILATION_FAILED')
    sources = data.get('sources')
    need(type(sources) is dict and set(sources) == {'State.sol'} and
         sources['State.sol'].get('ast', {}).get('nodeType') == 'SourceUnit', 'AST_REQUIRED')
    return data


def queries(data: dict) -> dict:
    requested = data.get('auxiliaryInputRequested', {})
    need(type(requested) is dict and set(requested).issubset({'smtlib2queries'}), 'COMPILER_REQUEST_PROFILE')
    q = requested.get('smtlib2queries', {})
    need(type(q) is dict and len(q) <= 1, 'QUERY_COUNT')
    for key, value in q.items():
        need(type(key) is str and KEY.fullmatch(key) is not None, 'QUERY_KEY')
        check_query(value)
    return q


def classification(name: str, role: str, data: dict) -> str:
    source = control_source(name, role).encode()
    start = source.index(b'assert(')
    location = {'file': 'State.sol', 'start': start, 'end': source.index(b';', start)}
    known = {('9576', 'CHC: Assertion violation check is safe!'): 'SAFE',
             ('6328', 'CHC: Assertion violation happens here.'): 'VIOLATED',
             ('6328', 'CHC: Assertion violation might happen here.'): 'UNKNOWN'}
    results = []
    for diag in data.get('errors', []):
        key = (str(diag.get('errorCode', '')), diag.get('message'))
        need(key in known, 'UNSUPPORTED_DIAGNOSTIC')
        need(canonical(diag.get('sourceLocation')) == canonical(location), 'ASSERTION_LOCATION')
        results.append(known[key])
    need(len(results) == 1, 'EXPLICIT_SINGLE_TARGET_REQUIRED')
    return results[0]


def execute_role(image: bytes, name: str, role: str, budget: str) -> dict:
    inp = fixed_input(name, role)
    first, err = compiler._execute(image, 'compile', canonical(inp))
    need(not err, 'COMPILER_STDERR')
    initial = _output(first)
    q = queries(initial)
    need(len(q) == 1, 'NO_SOLVER_QUERY_NO_CERTIFICATION')
    key, query = next(iter(q.items()))
    answer = solve(query, budget)
    final_input = fixed_input(name, role, {key: answer['response']})
    final, err = compiler._execute(image, 'compile', canonical(final_input))
    need(not err, 'COMPILER_STDERR')
    done = _output(final)
    need(not queries(done), 'UNANSWERED_COMPILER_QUERY')
    outcome = classification(name, role, done)
    need(outcome == answer['assertion_outcome'], 'COMPILER_SOLVER_DISAGREEMENT')
    return {'input': inp, 'initial_output_utf8': first.decode(), 'queries': q,
            'solver': answer, 'final_input': final_input, 'final_output_utf8': final.decode(),
            'assertion_outcome': outcome}


def graph_reference(name: str) -> dict:
    """Explicit finite-state graph; transitions use concrete arithmetic, not SMT."""
    need(type(name) is str and name in NAMES, 'FIXED_CONTROL_REQUIRED')
    initial = (0, 15, 0)  # steps, debit, credit
    seen, queue = {initial}, deque([(initial, [])])
    transitions = 0
    witness = None
    while queue:
        state, path = queue.popleft()
        step, debit, credit = state
        if name == 'unreachable' or step == 3:
            continue
        for q in range(16):
            if q > debit:
                continue
            after = (step + 1, debit - q, credit + q + int(name == 'delayed_credit' and step == 2))
            transitions += 1
            if after[1] + after[2] != 15 and witness is None:
                witness = {'quantities': path + [q], 'final_state': list(after),
                           'origin': 'finite-reference-not-solver-or-evm'}
            if after not in seen:
                seen.add(after)
                queue.append((after, path + [q]))
    return {'states': [list(x) for x in sorted(seen)], 'transition_count': transitions,
            'third_step_states': sum(x[0] == 3 for x in seen),
            'violating_states': sum(x[1] + x[2] != 15 for x in seen), 'witness': witness}


def sequence_reference(name: str) -> dict:
    """Independent enumeration: derive balances from prefix sums, not graph steps."""
    need(type(name) is str and name in NAMES, 'FIXED_CONTROL_REQUIRED')
    states = {(0, 15, 0)}
    valid = violations = checked = 0
    shortest = None
    for sequence in product(range(16), repeat=3):
        checked += 1
        if name == 'unreachable':
            continue
        accepted = True
        for length in (1, 2, 3):
            spent = sum(sequence[:length])
            if spent > 15:
                accepted = False
                break
            credit = spent + int(name == 'delayed_credit' and length == 3)
            state = (length, 15 - spent, credit)
            states.add(state)
            if state[1] + state[2] != 15:
                shortest = length if shortest is None else min(length, shortest)
        if accepted:
            valid += 1
            violations += name == 'delayed_credit'
    return {'states': [list(x) for x in sorted(states)], 'sequences_examined': checked,
            'feasible_three_step_sequences': valid, 'violating_three_step_sequences': violations,
            'shortest_violation_steps': shortest}


def concrete_witness(name: str, witness: dict) -> None:
    need(type(witness) is dict and set(witness) == {'quantities', 'final_state', 'origin'}, 'WITNESS_SCHEMA')
    need(witness['origin'] == 'finite-reference-not-solver-or-evm', 'WITNESS_ORIGIN')
    qs = witness['quantities']
    need(name == 'delayed_credit' and type(qs) is list and len(qs) == 3 and
         all(type(q) is int and 0 <= q <= 15 for q in qs), 'WITNESS_DOMAIN')
    need(all(sum(qs[:i]) <= 15 for i in (1, 2, 3)), 'WITNESS_GUARD')
    expected = [3, 15 - sum(qs), sum(qs) + 1]
    need(canonical(witness['final_state']) == canonical(expected) and expected[1] + expected[2] == 16,
         'WITNESS_ARITHMETIC')


def adjudicate(name: str, property_outcome: str, reachability_outcome: str) -> dict:
    need(property_outcome in OUTCOMES and reachability_outcome in OUTCOMES, 'OUTCOME')
    graph, enumeration = graph_reference(name), sequence_reference(name)
    need(canonical(graph['states']) == canonical(enumeration['states']), 'REFERENCE_STATE_DISAGREEMENT')
    if graph['witness'] is not None:
        concrete_witness(name, graph['witness'])
    if 'UNKNOWN' in (property_outcome, reachability_outcome):
        status = 'STATEFUL_FORMAL_INCONCLUSIVE'
    else:
        reachable = enumeration['feasible_three_step_sequences'] > 0
        need((reachability_outcome == 'VIOLATED') == reachable, 'REACHABILITY_DISAGREEMENT')
        bad = enumeration['violating_three_step_sequences'] > 0
        need((property_outcome == 'VIOLATED') == bad, 'PROPERTY_REFERENCE_DISAGREEMENT')
        status = ('VACUOUS_STATEFUL_NO_CERTIFICATION' if not reachable else
                  'STATEFUL_PROPERTY_VIOLATED' if bad else 'STATEFUL_PROPERTY_PROVED_IN_FIXED_MODEL')
    return {'status': status, 'graph': graph, 'enumeration': enumeration,
            'third_step_nonvacuity': reachability_outcome == 'VIOLATED',
            'evm_executed': False, 'vulnerability_confirmed': False}


def engine_identity() -> dict:
    return {'sources': {n: sha(read_artifact(ROOT, n)) for n in CODE},
            'compiler': compiler.PIN, 'solver': smt_backend.engine_identity(),
            'native_sources': source_inventory()}


def execute_lab(binary: Path, budget: str = 'normal') -> dict:
    need(type(budget) is str and budget in BUDGETS, 'BUDGET_PROFILE')
    image = compiler.read_pinned_binary(binary)
    version, err = compiler._execute(image, 'version')
    compiler.verify_version(version)
    need(not err, 'COMPILER_STDERR')
    before = engine_identity()
    cases = {}
    for name in NAMES:
        runs = {role: execute_role(image, name, role, budget) for role in ROLES}
        cases[name] = {'runs': runs, 'verdict': adjudicate(name, runs['property']['assertion_outcome'],
                                                       runs['third_step_reachable']['assertion_outcome'])}
    need(engine_identity() == before, 'ENGINE_CHANGED_DURING_RUN')
    return {'schema_version': 1, 'profile': 'owned-solidity-stateful-chc-v1', 'budget': budget,
            'engine': before, 'compiler_version_utf8': version.decode(), 'cases': cases,
            'compiler_processes_executed': 13, 'solver_queries_executed': 6,
            'solc_executed_locally': True, 'z3_called_locally': True, 'evm_executed': False,
            'arbitrary_sources_accepted': False, 'external_targets': False,
            'vulnerability_confirmed': False, 'proof_certificate_independently_checked': False}


def result_from(execution: dict, produced_at: str) -> dict:
    need(type(produced_at) is str and len(produced_at) <= 40 and
         datetime.fromisoformat(produced_at).tzinfo is not None, 'PRODUCED_AT')
    need(type(execution) is dict and set(execution.get('cases', {})) == set(NAMES), 'CASE_COVERAGE')
    statuses = {n: execution['cases'][n]['verdict']['status'] for n in NAMES}
    return {'schema_version': 1, 'status': 'STATEFUL_CONTROLS_INCONCLUSIVE'
            if 'STATEFUL_FORMAL_INCONCLUSIVE' in statuses.values() else 'STATEFUL_CONTROLS_COMPLETED',
            'controls': statuses, 'produced_at': produced_at, 'execution_sha256': sha(canonical(execution)),
            'evm_executed': False, 'vulnerability_confirmed': False, 'platform_complete': False,
            'human_review_required': True}


def documents(execution: dict, produced_at: str) -> dict[str, bytes]:
    result = result_from(execution, produced_at)
    audit = load_components().audit.AuditLog(clock=lambda: produced_at)
    audit.append('stateful.execution', {'execution_sha256': result['execution_sha256']})
    for name, state in result['controls'].items():
        audit.append('stateful.control', {'name': name, 'status': state})
    audit.append('stateful.complete', {'result_sha256': sha(canonical(result))})
    audit.assert_intact()
    markdown = ('# Controles propios Solidity con estado persistente\n\n' + result['status'] + '\n\n' +
                '\n'.join(f'{n}: {s}' for n, s in result['controls'].items()) +
                '\n\nCompilador CHC y Z3 reales; referencias de estados y secuencias finitas.\n'
                'No es EVM ni ejecución de transacciones. El contraejemplo concreto proviene de la referencia.\n'
                'La factibilidad de la tercera operación se comprueba separadamente. UNKNOWN no certifica.\n'
                'Reproducir con los mismos motores no constituye prueba independiente de su corrección.\n')
    return {'execution.json': canonical(execution), 'result.json': canonical(result),
            'audit.json': canonical({'events': [asdict(e) for e in audit.entries], 'clock_authenticated': False}),
            'REVIEW.md': markdown.encode()}


def create(binary: Path, out: Path, *, budget: str = 'normal') -> dict:
    need(not out.exists() and not out.is_symlink(), 'NEW_OUTPUT_REQUIRED')
    need(not out.resolve().is_relative_to(ROOT.parent), 'OUTPUT_INSIDE_CODE')
    execution = execute_lab(binary, budget)
    at = datetime.now(timezone.utc).isoformat()
    write_new_bundle(out, documents(execution, at))
    return result_from(execution, at)


def replay(root: Path, binary: Path, *, expected_budget: str = 'normal') -> dict:
    need(type(expected_budget) is str and expected_budget in BUDGETS, 'BUDGET_PROFILE')
    need(not root.is_symlink(), 'BUNDLE_ROOT_SYMLINK')
    marker = strict_json(read_artifact(root, 'COMPLETE.json'))
    need(set(marker) == {'schema_version', 'sha256'} and type(marker['schema_version']) is int and
         marker['schema_version'] == 1 and type(marker['sha256']) is dict and
         set(marker['sha256']) == FILES, 'BUNDLE_SCHEMA')
    need({p.name for p in root.iterdir()} == FILES | {'COMPLETE.json'}, 'BUNDLE_FILES')
    data = {name: read_artifact(root, name) for name in FILES}
    need(all(sha(raw) == marker['sha256'][name] for name, raw in data.items()), 'BUNDLE_HASH')
    claim = strict_json(data['execution.json'])
    need(claim.get('budget') == expected_budget, 'EXTERNAL_BUDGET_MISMATCH')
    # Regenerate own sources/queries. Never run a query or source taken from this bundle.
    actual = execute_lab(binary, expected_budget)
    at = strict_json(data['result.json']).get('produced_at')
    need(data == documents(actual, at), 'STATEFUL_REPLAY_MISMATCH')
    return {**result_from(actual, at), 'same_engines_reexecuted': True, 'independent_engine': False}


def main(argv: list[str] | None = None) -> int:
    p = PrivateArgumentParser(description='Fixed local stateful Solidity controls, not EVM or external targets')
    sub = p.add_subparsers(dest='command', required=True)
    run = sub.add_parser('prove-stateful-controls')
    run.add_argument('--solc', type=Path, required=True)
    run.add_argument('--out', type=Path, required=True)
    run.add_argument('--budget', choices=tuple(BUDGETS), default='normal')
    check = sub.add_parser('replay-stateful-controls')
    check.add_argument('--solc', type=Path, required=True)
    check.add_argument('--bundle', type=Path, required=True)
    check.add_argument('--expected-budget', choices=tuple(BUDGETS), default='normal')
    args = p.parse_args(argv)
    try:
        result = (create(args.solc, args.out, budget=args.budget) if args.command == 'prove-stateful-controls'
                  else replay(args.bundle, args.solc, expected_budget=args.expected_budget))
        print(json.dumps(result, sort_keys=True))
        return 1 if result['status'] == 'STATEFUL_CONTROLS_INCONCLUSIVE' else 0
    except (ValueError, OSError, KeyError, TypeError, RecursionError, OverflowError):
        print(json.dumps({'status': 'STATEFUL_CONTROLS_BLOCKED', 'evm_executed': False,
                          'vulnerability_confirmed': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
