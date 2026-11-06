"""Fixed native Solidity assertion laboratory, not a general vulnerability hunter.

Only three own, pure arithmetic controls are compiled. solc emits SMT-LIB2;
the installed Z3 C API answers those exact queries, then solc consumes the
responses. No external source, SMT, target, transaction or exploit input exists.
An exhaustive finite-domain reference and feasibility probe supplement the
compiler/solver. This is NOT EVM execution or an independently checked proof.
"""
from __future__ import annotations

from copy import deepcopy
import ctypes as c
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from . import native_compile as compiler, smt_backend
from .native_runtime import load_components, source_inventory
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
NAMES = ('conservation', 'off_by_one', 'unreachable')
ROLES = ('property', 'feasibility')
BUDGETS = {'normal': 1_000_000, 'exhausted': 1}
MAX_QUERY = 100_000
FILES = {'execution.json', 'result.json', 'audit.json', 'REVIEW.md'}
CODE = ('solidity_formal.py', 'native_compile.py', 'solc_worker.py', 'smt_backend.py',
        'native_runtime.py', 'safe_io.py')
KEY = re.compile(r'0x[0-9a-f]{64}\Z')
GET_VALUES = re.compile(r'\(get-value \((?:\|EVALEXPR_[0-9]+\|\s*)+\)\)\s*\Z')
MODEL_VALUE = re.compile(r'\(\|?EVALEXPR_([0-9]+)\|?\s+([0-9]+)\)')
ALLOWED_VARS = ('debit', 'credit', 'quantity', 'finalDebit', 'finalCredit')


class FormalError(ValueError):
    """Fixed diagnostics without source code, private paths or solver payloads."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise FormalError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def control_source(name: str, role: str) -> str:
    need(type(name) is str and name in NAMES, 'FIXED_CONTROL_REQUIRED')
    need(type(role) is str and role in ROLES, 'FIXED_ROLE_REQUIRED')
    extra = 1 if name == 'off_by_one' else 0
    assumption = 'false' if name == 'unreachable' else 'debit <= 15 && credit <= 15 && quantity <= debit'
    assertion = 'false' if role == 'feasibility' else 'finalDebit + finalCredit == uint16(debit) + uint16(credit)'
    return ('// SPDX-License-Identifier: MIT\n'
            '// Own fixed arithmetic control. No tokens, storage, calls or funds.\n'
            'pragma solidity 0.8.30;\n'
            'contract ConservationControl {\n'
            '    function check(uint8 debit, uint8 credit, uint8 quantity) public pure {\n'
            f'        require({assumption});\n'
            '        uint16 finalDebit = uint16(debit) - uint16(quantity);\n'
            f'        uint16 finalCredit = uint16(credit) + uint16(quantity) + {extra};\n'
            f'        assert({assertion});\n'
            '    }\n}\n')


def fixed_input(name: str, role: str, responses: dict | None = None) -> dict:
    data = {'language': 'Solidity', 'sources': {'Control.sol': {'content': control_source(name, role)}},
            'settings': {'optimizer': {'enabled': False}, 'evmVersion': 'cancun',
                'modelChecker': {'engine': 'bmc', 'targets': ['assert'], 'solvers': ['smtlib2'],
                                 'timeout': 3000, 'showProvedSafe': True,
                                 'showUnproved': True, 'showUnsupported': True},
                'outputSelection': {'*': {'': ['ast']}}}}
    if responses is not None:
        need(type(responses) is dict and len(responses) <= 1, 'RESPONSE_SET')
        for key, response in responses.items():
            need(type(key) is str and KEY.fullmatch(key) is not None and
                 type(response) is str and len(response) <= 16_000, 'RESPONSE_SCHEMA')
        data['auxiliaryInput'] = {'smtlib2responses': deepcopy(responses)}
    return data


def reference(name: str) -> dict:
    """Finite truth table for the fixed arithmetic control, not Solidity execution."""
    need(type(name) is str and name in NAMES, 'FIXED_CONTROL_REQUIRED')
    feasible = failed = 0
    for debit in range(16):
        for credit in range(16):
            for quantity in range(16):
                if name == 'unreachable' or quantity > debit:
                    continue
                feasible += 1
                # Independent conservation equation: net debits + net credits.
                net = -quantity + quantity + (1 if name == 'off_by_one' else 0)
                failed += net != 0
    return {'enumerated_input_tuples': 4096, 'feasible_input_tuples': feasible,
            'violating_input_tuples': failed, 'domain': 'three-uint8-values-restricted-by-fixed-guards',
            'is_evm_execution': False}


def split_query(query: str) -> tuple[str, str]:
    """Narrow profile of queries emitted by the pinned compiler for these controls."""
    need(type(query) is str and 0 < len(query.encode('utf-8')) <= MAX_QUERY, 'QUERY_BUDGET')
    need(query.startswith('(set-option :produce-models true)\n(set-option :timeout 3000)\n(set-logic ALL)\n'),
         'QUERY_PREFIX')
    need(query.count('(check-sat)\n') == 1, 'SINGLE_CHECK_REQUIRED')
    before, after = query.split('(check-sat)\n')
    need(GET_VALUES.fullmatch(after) is not None, 'QUERY_MODEL_REQUEST')
    need(not any(x in before for x in ('(exit', '(reset', '(include', ':output-channel', ':rlimit',
                                      '(get-', '(check-sat', '(set-option :timeout 0)')), 'QUERY_COMMAND_PROFILE')
    return before + '(check-sat)\n', after


def solve_compiler_query(query: str, *, budget: str) -> dict:
    """Internal only: queries originate in execute_control(), never in CLI input.

    A fresh context prevents state leakage. The original compiler query is
    retained; the fixed resource/seed prefix is separately recorded.
    """
    need(type(budget) is str and budget in BUDGETS, 'BUDGET_PROFILE')
    check, get_value = split_query(query)
    prefix = f'(set-option :rlimit {BUDGETS[budget]})\n(set-option :random-seed 0)\n'
    with smt_backend._LOCK:
        lib, identity = smt_backend._open_library()
        evaluate = smt_backend._bind(lib, 'Z3_eval_smtlib2_string', c.c_char_p, c.c_void_p, c.c_char_p)
        cfg = lib.Z3_mk_config()
        need(bool(cfg), 'Z3_CONFIG')
        try:
            context = lib.Z3_mk_context(cfg)
        finally:
            lib.Z3_del_config(cfg)
        need(bool(context), 'Z3_CONTEXT')
        errors = []
        handler = smt_backend._ERROR_HANDLER(lambda _ctx, code: errors.append(code))
        try:
            lib.Z3_set_error_handler(context, handler)
            answer = (evaluate(context, (prefix + check).encode('utf-8')) or b'').decode('utf-8')
            need(not errors and not lib.Z3_get_error_code(context), 'Z3_CHECK_ERROR')
            status = answer.strip()
            need(status in ('sat', 'unsat', 'unknown'), 'Z3_UNKNOWN_RESPONSE')
            values = ''
            if status == 'sat':
                values = (evaluate(context, get_value.encode('ascii')) or b'').decode('ascii')
                need(not errors and not lib.Z3_get_error_code(context) and bool(values.strip()), 'Z3_MODEL_ERROR')
            response = answer + values
            need(len(response.encode()) <= 16_000, 'Z3_RESPONSE_BUDGET')
            return {'status': status.upper(), 'response': response, 'query_sha256': sha(query.encode()),
                    'resource_prefix': prefix, 'evaluated_check_sha256': sha((prefix + check).encode()),
                    'resource_limit': BUDGETS[budget], 'timeout_ms': 3000, 'engine': identity}
        finally:
            lib.Z3_del_context(context)


def _read_output(raw: bytes) -> dict:
    data = strict_json(raw)
    diagnostics = data.get('errors', [])
    need(type(diagnostics) is list and all(type(x) is dict for x in diagnostics), 'COMPILER_DIAGNOSTICS')
    need(not any(x.get('severity') == 'error' for x in diagnostics), 'SOLIDITY_COMPILATION_FAILED')
    need(type(data.get('sources')) is dict and set(data['sources']) == {'Control.sol'} and
         data['sources']['Control.sol'].get('ast', {}).get('nodeType') == 'SourceUnit', 'COMPILED_AST_REQUIRED')
    return data


def compiler_queries(data: dict) -> dict:
    requested = data.get('auxiliaryInputRequested', {})
    need(type(requested) is dict and set(requested).issubset({'smtlib2queries'}), 'UNSUPPORTED_COMPILER_REQUEST')
    queries = requested.get('smtlib2queries', {})
    need(type(queries) is dict and len(queries) <= 1, 'QUERY_COUNT_PROFILE')
    for key, query in queries.items():
        need(type(key) is str and KEY.fullmatch(key) is not None, 'COMPILER_QUERY_KEY')
        split_query(query)
    return queries


def classify_target(name: str, role: str, data: dict) -> str:
    """Require an explicit target diagnostic. No warning is NOT a proof here."""
    source = control_source(name, role).encode()
    start = source.index(b'assert(')
    end = source.index(b';', start)
    markers = {'2961': 'UNSAT', '4661': 'SAT', '7812': 'UNKNOWN'}
    targets = []
    for diag in data.get('errors', []):
        code = str(diag.get('errorCode', ''))
        loc = diag.get('sourceLocation')
        if code in markers:
            need(canonical(loc) == canonical({'file': 'Control.sol', 'start': start, 'end': end}), 'TARGET_LOCATION_MISMATCH')
            targets.append(markers[code])
        elif code == '2072' and role == 'feasibility' and diag.get('message') == 'Unused local variable.':
            # The artificial false assertion intentionally does not reference the two locals.
            need(type(loc) is dict and loc.get('file') == 'Control.sol' and
                 type(loc.get('start')) is int and type(loc.get('end')) is int and
                 source[loc['start']:loc['end']] in (b'uint16 finalDebit', b'uint16 finalCredit'),
                 'UNEXPECTED_UNUSED_VARIABLE_DIAGNOSTIC')
        elif diag.get('severity') == 'warning':
            # A missing solver or unsupported feature never creates a safe verdict.
            raise FormalError('UNSUPPORTED_OR_UNPROVED_COMPILER_DIAGNOSTIC')
    need(len(targets) == 1, 'EXPLICIT_TARGET_REQUIRED')
    return targets[0]


def model_values(query: str, response: str) -> dict:
    values = {int(i): int(value) for i, value in MODEL_VALUE.findall(response)}
    rows = re.findall(r'\(assert \(= \|EVALEXPR_([0-9]+)\| ([A-Za-z]+)_[0-9]+_[0-9]+\)\)', query)
    out = {}
    for index, name in rows:
        if name in ALLOWED_VARS:
            need(int(index) in values and name not in out, 'MODEL_VALUE_MISSING_OR_DUPLICATE')
            out[name] = values[int(index)]
    need(set(out) == set(ALLOWED_VARS), 'CONCRETE_COUNTEREXAMPLE_REQUIRED')
    return out


def check_witness(name: str, role: str, values: dict) -> None:
    need(set(values) == set(ALLOWED_VARS) and all(type(x) is int for x in values.values()), 'WITNESS_SCHEMA')
    a, b, q = (values[k] for k in ('debit', 'credit', 'quantity'))
    need(name != 'unreachable' and 0 <= a <= 15 and 0 <= b <= 15 and 0 <= q <= a, 'WITNESS_ASSUMPTIONS')
    final_a, final_b = a - q, b + q + (1 if name == 'off_by_one' else 0)
    need(values['finalDebit'] == final_a and values['finalCredit'] == final_b, 'WITNESS_ARITHMETIC')
    if role == 'property':
        need(final_a + final_b != a + b, 'WITNESS_DOES_NOT_VIOLATE_PROPERTY')


def execute_control(image: bytes, name: str, role: str, budget: str) -> dict:
    inp = fixed_input(name, role)
    first, stderr = compiler._execute(image, 'compile', canonical(inp))
    need(not stderr, 'UNEXPECTED_COMPILER_STDERR')
    parsed = _read_output(first)
    queries = compiler_queries(parsed)
    record = {'source': control_source(name, role), 'input': inp, 'initial_output_utf8': first.decode(),
              'queries': queries, 'solver': None, 'final_input': None, 'final_output_utf8': None,
              'status': 'NO_TARGET', 'witness': None}
    if not queries:
        # No query, an unreachable assertion or no diagnosis: no positive proof.
        return record
    key, query = next(iter(queries.items()))
    answer = solve_compiler_query(query, budget=budget)
    final_input = fixed_input(name, role, {key: answer['response']})
    final, stderr = compiler._execute(image, 'compile', canonical(final_input))
    need(not stderr, 'UNEXPECTED_COMPILER_STDERR')
    done = _read_output(final)
    need(not compiler_queries(done), 'UNANSWERED_COMPILER_QUERY')
    status = classify_target(name, role, done)
    need(status == answer['status'], 'COMPILER_SOLVER_DISAGREEMENT')
    witness = None
    if status == 'SAT':
        witness = model_values(query, answer['response'])
        check_witness(name, role, witness)
    record.update(solver=answer, final_input=final_input, final_output_utf8=final.decode(),
                  status=status, witness=witness)
    return record


def adjudicate(name: str, property_status: str, feasibility_status: str) -> dict:
    need(property_status in ('SAT', 'UNSAT', 'UNKNOWN', 'NO_TARGET') and
         feasibility_status in ('SAT', 'UNSAT', 'UNKNOWN', 'NO_TARGET'), 'CONTROL_STATUS')
    exact = reference(name)
    if not exact['feasible_input_tuples']:
        need(property_status != 'SAT' and feasibility_status != 'SAT', 'INFEASIBLE_REFERENCE_DISAGREEMENT')
        status = 'VACUOUS_NO_CERTIFICATION'
    elif property_status in ('UNKNOWN', 'NO_TARGET') or feasibility_status in ('UNKNOWN', 'NO_TARGET'):
        status = 'FORMAL_INCONCLUSIVE'
    else:
        need(feasibility_status == 'SAT', 'FEASIBILITY_DISAGREEMENT')
        expected = 'SAT' if exact['violating_input_tuples'] else 'UNSAT'
        need(property_status == expected, 'EXHAUSTIVE_REFERENCE_DISAGREEMENT')
        status = 'PROPERTY_VIOLATED_IN_FIXED_MODEL' if expected == 'SAT' else 'PROPERTY_PROVED_IN_FIXED_MODEL'
    return {'status': status, 'reference': exact, 'nonvacuity_established': feasibility_status == 'SAT',
            'solidity_property_confirmed_only_within_fixed_model': status == 'PROPERTY_PROVED_IN_FIXED_MODEL',
            'vulnerability_confirmed': False, 'evm_executed': False}


def engine_identity() -> dict:
    return {'sources': {n: sha(read_artifact(ROOT, n)) for n in CODE},
            'native_sources': source_inventory(), 'compiler': compiler.PIN,
            'solver': smt_backend.engine_identity()}


def execute_lab(binary: Path, budget: str = 'normal') -> dict:
    need(type(budget) is str and budget in BUDGETS, 'BUDGET_PROFILE')
    image = compiler.read_pinned_binary(binary)
    version, stderr = compiler._execute(image, 'version')
    compiler.verify_version(version)
    need(not stderr, 'UNEXPECTED_COMPILER_STDERR')
    identity = engine_identity()
    cases = {}
    for name in NAMES:
        runs = {role: execute_control(image, name, role, budget) for role in ROLES}
        verdict = adjudicate(name, runs['property']['status'], runs['feasibility']['status'])
        cases[name] = {'runs': runs, 'verdict': verdict}
    solver_calls = sum(case['runs'][role]['solver'] is not None
                       for case in cases.values() for role in ROLES)
    need(solver_calls > 0, 'NO_SOLVER_EXECUTION')
    need(engine_identity() == identity, 'ENGINE_CHANGED_DURING_RUN')
    return {'schema_version': 1, 'profile': 'fixed-solidity-bmc-conservation-v1',
            'budget': budget, 'engine': identity, 'compiler_version_utf8': version.decode(),
            'solver_queries_executed': solver_calls,
            'compiler_processes_executed': 1 + len(NAMES) * len(ROLES) + solver_calls,
            'cases': cases, 'solc_executed_locally': True, 'z3_called_locally': True,
            'evm_executed': False, 'external_targets': False, 'vulnerability_confirmed': False,
            'proof_certificate_independently_checked': False}


def result_from(execution: dict, *, produced_at: str) -> dict:
    need(type(execution) is dict and set(execution.get('cases', {})) == set(NAMES), 'CASE_COVERAGE')
    moment = datetime.fromisoformat(produced_at)
    need(moment.tzinfo is not None, 'PRODUCED_AT_TIMEZONE')
    statuses = {name: execution['cases'][name]['verdict']['status'] for name in NAMES}
    return {'schema_version': 1,
            'status': 'FORMAL_CONTROLS_INCONCLUSIVE' if 'FORMAL_INCONCLUSIVE' in statuses.values()
                      else 'FORMAL_CONTROLS_COMPLETED',
            'execution_sha256': sha(canonical(execution)), 'controls': statuses, 'produced_at': produced_at,
            'solidity_compiler_executed': True, 'solver_executed': True, 'evm_executed': False,
            'vulnerability_confirmed': False, 'platform_complete': False,
            'independent_evm_reproduction': False, 'human_review_required': True}


def _audit(result: dict) -> dict:
    # The observed wall clock is retained, not independently authenticated.
    audit = load_components().audit.AuditLog(clock=lambda: result['produced_at'])
    audit.append('solidity.formal.execution', {'execution_sha256': result['execution_sha256']})
    for name, state in result['controls'].items():
        audit.append('solidity.formal.control', {'name': name, 'status': state})
    audit.append('solidity.formal.complete', {'result_sha256': sha(canonical(result))})
    audit.assert_intact()
    return {'clock_authenticated': False, 'events': [asdict(x) for x in audit.entries]}


def render(result: dict) -> bytes:
    return ('# Propiedades Solidity — laboratorio formal fijo\n\n' + result['status'] + '\n\n' +
            '\n'.join(f'{name}: {state}' for name, state in result['controls'].items()) +
            '\n\nFuentes propias, compilador y Z3 reales. Pruebas sobre controles conocidos, no descubrimiento.\n'
            'No se ejecutó EVM. UNSAT depende del modelo, compilador y solver; no se verificó un certificado independiente.\n'
            'Una precondición imposible no certifica la propiedad. UNKNOWN nunca significa seguro.\n').encode()


def _documents(execution: dict, *, produced_at: str) -> dict[str, bytes]:
    result = result_from(execution, produced_at=produced_at)
    return {'execution.json': canonical(execution), 'result.json': canonical(result),
            'audit.json': canonical(_audit(result)), 'REVIEW.md': render(result)}


def create(binary: Path, out: Path, *, budget: str = 'normal') -> dict:
    need(not out.exists() and not out.is_symlink(), 'NEW_OUTPUT_REQUIRED')
    need(not out.resolve().is_relative_to(ROOT.parent), 'OUTPUT_INSIDE_CODE')
    execution = execute_lab(binary, budget)
    produced_at = datetime.now(timezone.utc).isoformat()
    docs = _documents(execution, produced_at=produced_at)
    write_new_bundle(out, docs)
    return result_from(execution, produced_at=produced_at)


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
    claimed = strict_json(data['execution.json'])
    need(claimed.get('budget') == expected_budget, 'EXTERNAL_BUDGET_MISMATCH')
    # Do not solve supplied SMT or sources: regenerate all controls with current pinned code.
    actual = execute_lab(binary, expected_budget)
    produced_at = strict_json(data['result.json']).get('produced_at')
    need(type(produced_at) is str and len(produced_at) <= 40, 'PRODUCED_AT')
    expected = _documents(actual, produced_at=produced_at)
    need(data == expected, 'NATIVE_FORMAL_REPLAY_MISMATCH')
    result = result_from(actual, produced_at=produced_at)
    result['same_compiler_and_solver_reexecuted'] = True
    result['independent_engine'] = False
    return result


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Fixed own Solidity assertion controls; no targets or arbitrary queries')
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('prove-solidity-controls')
    run.add_argument('--out', type=Path, required=True)
    verify = sub.add_parser('replay-solidity-controls')
    verify.add_argument('--bundle', type=Path, required=True)
    for p in (run, verify):
        p.add_argument('--binary', type=Path, required=True)
        p.add_argument('--budget', choices=tuple(BUDGETS), default='normal')
    args = parser.parse_args(argv)
    try:
        result = (create(args.binary, args.out, budget=args.budget)
                  if args.command == 'prove-solidity-controls' else
                  replay(args.bundle, args.binary, expected_budget=args.budget))
        print(json.dumps(result, sort_keys=True))
        return 1 if result['status'] == 'FORMAL_CONTROLS_INCONCLUSIVE' else 0
    except (ValueError, OSError, KeyError, TypeError, UnicodeError, RecursionError):
        print(json.dumps({'status': 'FORMAL_CONTROLS_BLOCKED', 'vulnerability_confirmed': False,
                          'evm_executed': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
