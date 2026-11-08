"""Bounded mutation corpus over owned, fixed Solidity state controls.

Runs the *real* pinned solc and Geth EVM, compares every observed committed
state/return/revert with two concrete arithmetic oracles, and checks a second
codegen profile. No external source, address, RPC, exploit or target is accepted.
A matching finite corpus is NOT a security certificate or universal fuzzing.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re

from . import bytecode_controls as builds, compiler_variants as variants
from . import evm_execution as evm, native_compile as compiler, quality
from . import balance_reconciliation as accounting
from .native_runtime import load_components
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILES = ('legacy_unoptimized', 'ir_optimized')
CONTROLS = ('conservation', 'delayed_credit')
MAX_CASES = 24
MIN_CASES = 9
STEPS = 4
FILES = {'sequences.json', 'result.json', 'audit.json', 'REVIEW.md'}
PROFILE = 'fixed-owned-evm-sequence-mutation-v1'


class SequenceFuzzError(ValueError):
    """Fixed error codes, never raw inputs or source text."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise SequenceFuzzError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def arguments(seed: object, cases: object) -> None:
    need(type(seed) is int and 0 <= seed < 2**64, 'SEED_UINT64_REQUIRED')
    need(type(cases) is int and MIN_CASES <= cases <= MAX_CASES, 'CASE_BUDGET')


def _sequence(values: tuple[int, ...], gas_low: int = -1) -> tuple[tuple[int, int], ...]:
    return tuple((q, 1 if i == gas_low else evm.GAS) for i, q in enumerate(values))


def corpus(seed: int, cases: int) -> list[list[list[int]]]:
    """Boundary-first, seeded mutations; generated only from local arithmetic.

    A sequence is four (uint8, gas) pairs. No response from an external target
    guides generation. No claim of branch, instruction or path coverage is made.
    """
    arguments(seed, cases)
    anchors = [
        _sequence((0, 0, 0, 0)),   # reach third assertion
        _sequence((15, 0, 0, 0)),  # exhaust debit
        _sequence((2, 16, 3, 4)),  # exceeding available debit
        _sequence((16, 0, 0, 0)),  # first call fails, later can succeed
        _sequence((1, 1, 1, 1)),   # fourth call guarded
        _sequence((0, 0, 0, 0), 2), # OOG between successful calls
        _sequence((0, 0, 0, 0), 3), # OOG after third success/revert
        _sequence((2, 3, 4, 5)),
        _sequence((255, 15, 0, 0)),
    ]
    values, seen = [], set()
    def add(candidate: tuple[tuple[int, int], ...]) -> None:
        key = canonical(candidate)
        if key not in seen:
            seen.add(key)
            values.append([[q, gas] for q, gas in candidate])
    for case in anchors:
        add(case)
    rng = random.Random(seed)
    while len(values) < cases:
        parent = deepcopy(rng.choice(values))
        index = rng.randrange(STEPS)
        choices = (0, 1, 2, 3, 4, 14, 15, 16, 17, 255, rng.randrange(256))
        parent[index][0] = rng.choice(choices)
        if rng.randrange(5) == 0:
            parent[index][1] = evm.GAS if parent[index][1] == 1 else 1
        add(tuple((q, gas) for q, gas in parent))
    return values


def independent_oracle(name: str, before: dict, quantity: int, gas: int) -> dict:
    """Separate arithmetic implementation; intentionally does not call evm.reference."""
    need(name in builds.formal.NAMES and type(quantity) is int and 0 <= quantity <= 255 and
         type(gas) is int and gas in (1, evm.GAS) and
         type(before) is dict and set(before) == {'debit','credit','steps'} and
         all(type(x) is int for x in before.values()), 'ORACLE_INPUT')
    state = dict(before)
    if gas == 1:
        outcome, data, error = 'RESOURCE_EXHAUSTED', '0x', 'out of gas'
    elif name == 'unreachable' or before['steps'] >= 3 or quantity > before['debit']:
        outcome, data, error = 'PRECONDITION_REVERT', '0x', 'execution reverted'
    elif name == 'delayed_credit' and before['steps'] == 2:
        outcome, data, error = 'ASSERTION_REVERT', evm.PANIC_ASSERT, 'execution reverted'
    else:
        state['debit'] -= quantity
        state['credit'] += quantity
        state['steps'] += 1
        outcome, data, error = 'COMMITTED', '0x', None
    return {'status': outcome, 'state': state, 'return_data': data, 'error': error}


def verify_oracles(name: str, before: dict, quantity: int, gas: int) -> dict:
    independent = independent_oracle(name, before, quantity, gas)
    native = evm.reference(name, before, quantity, gas)
    require = {k: native[k] for k in ('status', 'state', 'return_data', 'error')}
    need(canonical(independent) == canonical(require), 'INDEPENDENT_ORACLE_DISAGREEMENT')
    return independent


def _compile(name: str, profile: str, image: bytes, original: dict | None) -> tuple[dict, dict]:
    inp = variants.build_input(name, profile)
    out, err = compiler._execute(image, 'compile', canonical(inp))
    need(err == b'', 'COMPILER_STDERR')
    built = {'input': inp, 'output_utf8': out.decode('utf-8'), 'stderr_utf8': ''}
    if original is None:
        need(profile == PROFILES[0], 'PROFILE_ORDER')
        info = builds.inspect_output(name, out)
        contract = strict_json(out)['contracts'][builds.SOURCE_FILE][builds.CONTRACT]
    else:
        contract, info = variants.inspect_build(name, profile, built, original)
    return built, {'contract': contract, 'summary': info,
                   'creation_sha256': sha(bytes.fromhex(contract['evm']['bytecode']['object'])),
                   'runtime_sha256': sha(bytes.fromhex(contract['evm']['deployedBytecode']['object']))}


def _run_profile(name: str, profile: str, contract: dict, image: bytes,
                 sequences: list[list[list[int]]]) -> dict:
    birth = evm._run(image, prestate=evm.genesis(), creation=contract['evm']['bytecode']['object'])
    observed = birth['observed']
    need(observed['error'] is None and observed['return_data'] ==
         '0x'+contract['evm']['deployedBytecode']['object'], 'CONSTRUCTOR_FAILED')
    starting_alloc = observed['alloc']
    need(evm.decode_state(starting_alloc, contract) == {'debit':15,'credit':0,'steps':0}, 'CONSTRUCTOR_STATE')
    selector = contract['evm']['methodIdentifiers']['move(uint8)']
    def one_sequence(row: list[list[int]]) -> tuple[dict, Counter]:
        outcomes = Counter()
        current = deepcopy(starting_alloc)
        model = {'debit':15,'credit':0,'steps':0}
        steps = []
        for quantity, gas in row:
            expected = verify_oracles(name, model, quantity, gas)
            calldata = selector + format(quantity, '064x')
            run = evm._run(image, prestate=evm.genesis(current, gas=gas), calldata=calldata, gas=gas)
            actual = run['observed']
            after = evm.decode_state(actual['alloc'], contract)
            need(after == expected['state'] and actual['error'] == expected['error'] and
                 actual['return_data'] == expected['return_data'], 'NATIVE_EVM_ORACLE_DISAGREEMENT')
            if expected['status'] != 'COMMITTED':
                need(canonical(current) == canonical(actual['alloc']), 'REVERT_MODIFIED_PERSISTENT_STATE')
            amount = quantity if expected['status'] == 'COMMITTED' else 0
            flow = [] if amount == 0 else [{'id':'call', 'from':'debit', 'to':'credit', 'amount_units':str(amount)}]
            before_cells = {k:str(model[k]) for k in ('debit','credit')}
            after_cells = {k:str(after[k]) for k in ('debit','credit')}
            eq = accounting.reconcile_internal_units(before_cells, after_cells, flow)
            need(eq['status'] == 'UNIT_BALANCES_RECONCILED', 'ACCOUNTING_DISAGREEMENT')
            steps.append({'quantity':quantity, 'gas':gas, 'outcome':expected['status'],
                          'state_before':model, 'state_after':after,
                          'return_data':actual['return_data'], 'error':actual['error'],
                          'prestate_sha256':run['prestate_sha256'],
                          'stdout_sha256':sha(run['stdout_utf8'].encode()),
                          'observed_state_root':actual['state_root'],
                          'accounting_rows':len(eq['rows'])})
            outcomes[expected['status']] += 1
            model, current = after, actual['alloc']
        return {'sequence_sha256':sha(canonical(row)), 'steps':steps,
                'final_state':model}, outcomes
    # Each sequence has its own fresh constructor state. Only independent cases
    # run concurrently; within a case, calls are strictly sequential. A fixed
    # worker cap bounds native process pressure and keeps output order stable.
    with ThreadPoolExecutor(max_workers=3) as pool:
        complete = list(pool.map(one_sequence, sequences))
    evidence = [item for item, counts in complete]
    outcomes = Counter()
    for item, counts in complete:
        outcomes.update(counts)
    return {'name':name, 'profile':profile,
            'constructor_stdout_sha256':sha(birth['stdout_utf8'].encode()),
            'constructor_state_root':observed['state_root'],
            'runs':evidence, 'outcomes':dict(sorted(outcomes.items()))}


def _behavior(profile_row: dict) -> list[dict]:
    return [{'status':step['outcome'], 'state':step['state_after'],
             'data':step['return_data'], 'error':step['error']}
            for case in profile_row['runs'] for step in case['steps']]


def execute(solc: Path, evm_binary: Path, seed: int, cases: int, expected_source: str) -> dict:
    arguments(seed, cases)
    need(type(expected_source) is str and re.fullmatch('[a-f0-9]{64}',expected_source) is not None,
         'EXTERNAL_SOURCE_DIGEST_REQUIRED')
    before = quality.source_snapshot()
    need(sha(canonical(before)) == expected_source, 'SOURCE_IDENTITY_MISMATCH')
    solc_image, evm_image = compiler.read_pinned_binary(solc), evm.read_evm(evm_binary)
    inputs = corpus(seed, cases)
    all_rows = {}
    counts = Counter()
    for name in CONTROLS:
        base, first = _compile(name, PROFILES[0], solc_image, None)
        optimized, second = _compile(name, PROFILES[1], solc_image, base)
        profiles = {}
        for prof, comp in ((PROFILES[0], first), (PROFILES[1], second)):
            profiles[prof] = _run_profile(name, prof, comp['contract'], evm_image, inputs)
            counts.update(profiles[prof]['outcomes'])
        need(canonical(_behavior(profiles[PROFILES[0]])) == canonical(_behavior(profiles[PROFILES[1]])),
             'CROSS_CODEGEN_OBSERVABLE_DISAGREEMENT')
        all_rows[name] = {'builds':{PROFILES[0]:{'source_sha256':first['summary']['source_sha256'],
                                   'creation_sha256':first['creation_sha256'], 'runtime_sha256':first['runtime_sha256'],
                                   'compiler_output_sha256':sha(base['output_utf8'].encode())},
                                  PROFILES[1]:{'source_sha256':second['summary']['source_sha256'],
                                   'creation_sha256':second['creation_sha256'], 'runtime_sha256':second['runtime_sha256'],
                                   'compiler_output_sha256':sha(optimized['output_utf8'].encode())}},
                           'profiles':profiles, 'observable_agreement':True}
    need(counts['ASSERTION_REVERT'] > 0 and counts['COMMITTED'] > 0 and
         counts['PRECONDITION_REVERT'] > 0 and counts['RESOURCE_EXHAUSTED'] > 0,
         'NEGATIVE_AND_POSITIVE_CONTROL_COVERAGE')
    need(quality.source_snapshot() == before, 'SOURCE_MUTATED_DURING_EXECUTION')
    return {'schema_version':1,'profile':PROFILE,'seed':seed,'cases_per_control':cases,
            'calls_per_sequence':STEPS,'compiler_pin':compiler.PIN,'evm_pin':evm.PIN,
            'source_digest':expected_source,'sequences':inputs,'controls':all_rows,
            'executions':len(CONTROLS)*len(PROFILES)*cases*STEPS,
            'constructor_executions':len(CONTROLS)*len(PROFILES),
            'outcomes':dict(sorted(counts.items())),
            'different_codegen_observations_agree':True,
            'simulation_only':False, 'owned_fixed_controls_only':True,
            'unseen_state_space_proved_safe':False,'vulnerability_confirmed':False,
            'independent_evm_used':False,'network_used':False}


def documents(run: dict, created: str) -> dict[str, bytes]:
    need(type(created) is str and len(created) <= 40 and
         datetime.fromisoformat(created).tzinfo is not None, 'CREATED_TIME')
    result = {k:run[k] for k in ('schema_version','profile','seed','cases_per_control',
                                 'source_digest','executions','constructor_executions',
                                 'outcomes','different_codegen_observations_agree',
                                 'unseen_state_space_proved_safe','vulnerability_confirmed',
                                 'independent_evm_used','network_used')}
    result.update({'status':'BOUNDED_NATIVE_SEQUENCE_FUZZ_PASS','created_at':created,
                   'run_sha256':sha(canonical(run))})
    audit = load_components().audit.AuditLog(clock=lambda:created)
    audit.append('fuzz.evm.start',{'run_sha256':result['run_sha256'], 'source_digest':run['source_digest']})
    for name, row in run['controls'].items():
        audit.append('fuzz.evm.control',{'name':name,'control_sha256':sha(canonical(row))})
    audit.append('fuzz.evm.complete',{'result_sha256':sha(canonical(result))})
    audit.assert_intact()
    text = ('# Fuzzing de secuencias EVM sobre controles propios\n\n'
            f"Estado: {result['status']}. Semilla: {run['seed']}.\n"
            f"Secuencias por control: {run['cases_per_control']}; llamadas nativas: {run['executions']}; "
            f"constructores: {run['constructor_executions']}.\n"
            'Dos rutas de compilación con el mismo solc y la misma EVM, no motores independientes.\n'
            'Todas las llamadas y movimientos están limitados a controles aritméticos propios.\n'
            'La comparación no mide exhaustividad, detectabilidad de bugs nuevos ni seguridad universal.\n'
            'Las aserciones revertidas no significan unidades monetarias robadas.\n'
            'No hubo RPC, escaneos externos, despliegue real ni envío de reportes.\n')
    return {'sequences.json':canonical(run), 'result.json':canonical(result),
            'audit.json':canonical({'entries':[asdict(e) for e in audit.entries], 'producer_authenticated':False}),
            'REVIEW.md':text.encode()}


def create(solc: Path, evm_binary: Path, seed: int, cases: int, expected: str, out: Path) -> dict:
    need(not out.exists() and not out.is_symlink() and
         not out.resolve().is_relative_to(ROOT.parent),'NEW_PRIVATE_OUTPUT_REQUIRED')
    data = execute(solc, evm_binary, seed, cases, expected)
    files = documents(data, datetime.now(timezone.utc).isoformat())
    write_new_bundle(out,files)
    return strict_json(files['result.json'])


def replay(root: Path, solc: Path, evm_binary: Path, expected: str) -> dict:
    need(not root.is_symlink(),'BUNDLE_SYMLINK')
    marker = strict_json(read_artifact(root,'COMPLETE.json'))
    need(type(marker) is dict and set(marker) == {'schema_version','sha256'} and
         type(marker['schema_version']) is int and marker['schema_version'] == 1 and
         type(marker['sha256']) is dict and set(marker['sha256']) == FILES,'BUNDLE_MANIFEST')
    need({p.name for p in root.iterdir()} == FILES | {'COMPLETE.json'},'BUNDLE_INVENTORY')
    saved = {name:read_artifact(root,name) for name in FILES}
    need(all(sha(saved[n]) == marker['sha256'][n] for n in FILES),'BUNDLE_DIGEST')
    result = strict_json(saved['result.json'])
    need(result.get('source_digest') == expected,'EXTERNAL_CODE_REFERENCE_MISMATCH')
    run = execute(solc, evm_binary, result['seed'],result['cases_per_control'],expected)
    need(saved == documents(run, result['created_at']),'NATIVE_REPLAY_DISAGREEMENT')
    need(all(read_artifact(root,n) == saved[n] for n in FILES),'BUNDLE_CHANGED_DURING_REPLAY')
    return result


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Fuzz only owned fixed Solidity controls in a local pinned EVM')
    sub = parser.add_subparsers(dest='command',required=True)
    sub.add_parser('fuzz-owned-evm').add_argument('--out',type=Path,required=True)
    sub.add_parser('replay-owned-evm').add_argument('--bundle',type=Path,required=True)
    for subparser in sub.choices.values():
        for key in ('solc','evm'):
            subparser.add_argument('--'+key,type=Path,required=True)
        subparser.add_argument('--expected-source',required=True)
    sub.choices['fuzz-owned-evm'].add_argument('--seed',type=int,default=20261105)
    sub.choices['fuzz-owned-evm'].add_argument('--cases',type=int,default=12)
    args = parser.parse_args(argv)
    try:
        result = (create(args.solc,args.evm,args.seed,args.cases,args.expected_source,args.out)
                  if args.command == 'fuzz-owned-evm' else
                  replay(args.bundle,args.solc,args.evm,args.expected_source))
        print(json.dumps({k:result[k] for k in ('status','seed','cases_per_control','executions',
                                                'vulnerability_confirmed')}))
        return 0
    except (ValueError,OSError,KeyError,TypeError,RuntimeError,OverflowError,RecursionError):
        print(json.dumps({'status':'EVM_SEQUENCE_FUZZ_BLOCKED','vulnerability_confirmed':False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
