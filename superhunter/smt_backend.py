"""Small original binding to an installed Z3 C API; no downloaded/vendored engine.

Used only by the generated RBAC encoding. No arbitrary SMT, paths, dynamic
libraries or solver flags are accepted by the public command line interface.
The native library is trusted code, NOT contained by a Python sandbox.
"""
from __future__ import annotations

import ctypes as c
import hashlib
from pathlib import Path
import threading

PATHS = ('/lib/x86_64-linux-gnu/libz3.so.4', '/usr/lib/x86_64-linux-gnu/libz3.so.4',
         '/lib/aarch64-linux-gnu/libz3.so.4', '/usr/lib/aarch64-linux-gnu/libz3.so.4')
_LOCK = threading.RLock()
_ERROR_HANDLER = c.CFUNCTYPE(None, c.c_void_p, c.c_int)


class SolverError(ValueError):
    """Fixed diagnostics only; never echo a policy or an SMT input."""


def _library_path() -> Path:
    for path in PATHS:
        p = Path(path)
        if p.is_file():
            return p.resolve()
    raise SolverError('Z3_NATIVE_LIBRARY_UNAVAILABLE')


def _bind(lib, name, result, *args):
    try:
        fn = getattr(lib, name)
    except AttributeError as exc:
        raise SolverError('Z3_API_UNAVAILABLE') from exc
    fn.restype, fn.argtypes = result, list(args)
    return fn


def _open_library():
    path = _library_path()
    try:
        lib = c.CDLL(str(path))
    except OSError as exc:
        raise SolverError('Z3_NATIVE_LOAD_FAILED') from exc
    p, u, s = c.c_void_p, c.c_uint, c.c_char_p
    signatures = (
        ('Z3_get_full_version', s, ()), ('Z3_mk_config', p, ()),
        ('Z3_del_config', None, (p,)), ('Z3_mk_context', p, (p,)),
        ('Z3_del_context', None, (p,)), ('Z3_set_error_handler', None, (p, _ERROR_HANDLER)),
        ('Z3_get_error_code', c.c_int, (p,)), ('Z3_mk_solver', p, (p,)),
        ('Z3_solver_inc_ref', None, (p,p)), ('Z3_solver_dec_ref', None, (p,p)),
        ('Z3_mk_params', p, (p,)), ('Z3_params_inc_ref', None, (p,p)),
        ('Z3_params_dec_ref', None, (p,p)), ('Z3_mk_string_symbol', p, (p,s)),
        ('Z3_params_set_uint', None, (p,p,p,u)), ('Z3_solver_set_params', None, (p,p,p)),
        ('Z3_solver_from_string', None, (p,p,s)), ('Z3_solver_check', c.c_int, (p,p)),
        ('Z3_solver_get_reason_unknown', s, (p,p)), ('Z3_solver_get_model', p, (p,p)),
        ('Z3_model_inc_ref', None, (p,p)), ('Z3_model_dec_ref', None, (p,p)),
        ('Z3_mk_bool_sort', p, (p,)), ('Z3_mk_const', p, (p,p,p)),
        ('Z3_model_eval', c.c_bool, (p,p,p,c.c_bool,c.POINTER(p))),
        ('Z3_get_bool_value', c.c_int, (p,p)),
    )
    for name, result, args in signatures:
        _bind(lib,name,result,*args)
    identity = {'engine': 'Z3', 'version': lib.Z3_get_full_version().decode('ascii'),
                'library_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'interface': 'C-API-via-ctypes', 'downloaded_here': False}
    return lib, identity


def engine_identity() -> dict:
    with _LOCK:
        return _open_library()[1]


def solve_generated(program: str, variables: int, *, timeout_ms: int = 1000,
                    resource_limit: int = 1_000_000) -> dict:
    """Internal API for generated QF_LIA programs. Return SAT/UNSAT/UNKNOWN.

    UNKNOWN, resource exhaustion and API errors are never converted to UNSAT.
    This is not a public arbitrary-query service. Caller bounds all inputs.
    """
    if (type(program) is not str or not program.startswith('(set-logic QF_LIA)\n') or
        not 0 < len(program.encode()) <= 1_000_000 or
        type(variables) is not int or not 0 <= variables <= 16 or
        type(timeout_ms) is not int or not 1 <= timeout_ms <= 5000 or
        type(resource_limit) is not int or not 1 <= resource_limit <= 10_000_000):
        raise SolverError('INVALID_GENERATED_QUERY_OR_BUDGET')
    with _LOCK:
        lib, identity = _open_library()
        config = lib.Z3_mk_config()
        if not config:
            raise SolverError('Z3_CONFIG_FAILED')
        try:
            context = lib.Z3_mk_context(config)
        finally:
            lib.Z3_del_config(config)
        if not context:
            raise SolverError('Z3_CONTEXT_FAILED')
        errors = []
        handler = _ERROR_HANDLER(lambda _ctx, code: errors.append(code))
        solver = params = model = None
        try:
            lib.Z3_set_error_handler(context, handler)
            solver = lib.Z3_mk_solver(context)
            if not solver:
                raise SolverError('Z3_SOLVER_FAILED')
            lib.Z3_solver_inc_ref(context, solver)
            params = lib.Z3_mk_params(context)
            lib.Z3_params_inc_ref(context, params)
            for name, value in (('timeout', timeout_ms), ('rlimit', resource_limit), ('random_seed', 0)):
                symbol = lib.Z3_mk_string_symbol(context, name.encode('ascii'))
                lib.Z3_params_set_uint(context, params, symbol, value)
            lib.Z3_solver_set_params(context, solver, params)
            lib.Z3_solver_from_string(context, solver, program.encode('ascii'))
            if errors or lib.Z3_get_error_code(context):
                raise SolverError('Z3_REJECTED_GENERATED_QUERY')
            value = lib.Z3_solver_check(context, solver)
            if errors or lib.Z3_get_error_code(context):
                raise SolverError('Z3_CHECK_ERROR')
            result = {'status': {1:'SAT', -1:'UNSAT', 0:'UNKNOWN'}.get(value),
                      'query_sha256': hashlib.sha256(program.encode('ascii')).hexdigest(),
                      'timeout_ms': timeout_ms, 'resource_limit': resource_limit,
                      'assignment': None, 'unknown_reason': None, 'engine': identity}
            if result['status'] is None:
                raise SolverError('Z3_INVALID_RESULT')
            if value == 0:
                why = (lib.Z3_solver_get_reason_unknown(context, solver) or b'').lower()
                result['unknown_reason'] = ('TIMEOUT' if b'timeout' in why else
                                            'RESOURCE_LIMIT' if b'resource' in why or b'canceled' in why else 'OTHER')
            elif value == 1:
                model = lib.Z3_solver_get_model(context, solver)
                if not model:
                    raise SolverError('Z3_MISSING_MODEL')
                lib.Z3_model_inc_ref(context, model)
                sort = lib.Z3_mk_bool_sort(context)
                assignment = []
                for i in range(variables):
                    symbol = lib.Z3_mk_string_symbol(context, f'x{i}'.encode('ascii'))
                    atom = lib.Z3_mk_const(context, symbol, sort)
                    evaluated = c.c_void_p()
                    if not lib.Z3_model_eval(context, model, atom, True, c.byref(evaluated)):
                        raise SolverError('Z3_MODEL_EVALUATION_FAILED')
                    boolean = lib.Z3_get_bool_value(context, evaluated)
                    if boolean not in (-1,1):
                        raise SolverError('Z3_NON_BOOLEAN_ASSIGNMENT')
                    assignment.append(boolean == 1)
                result['assignment'] = assignment
            if errors or lib.Z3_get_error_code(context):
                raise SolverError('Z3_RESULT_ERROR')
            return result
        finally:
            if model:
                lib.Z3_model_dec_ref(context, model)
            if params:
                lib.Z3_params_dec_ref(context, params)
            if solver:
                lib.Z3_solver_dec_ref(context, solver)
            lib.Z3_del_context(context)
