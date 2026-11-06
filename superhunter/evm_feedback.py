"""Observable EVM feedback and bounded corpus reduction for owned controls.

Every published decision requires replaying the fixed solc/Geth experiment.
Features describe observed status/state/input classes, NOT EVM instruction,
branch, path coverage, unknown bugs, or attacks. Witnesses are shortest
OBSERVED prefixes, never globally minimal exploit sequences.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from . import evm_sequence_fuzz as fuzz
from .native_runtime import load_components
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
FILES = {'feedback.json', 'audit.json', 'REVIEW.md', 'source-binding.json'}
OUTCOMES = {'COMMITTED', 'PRECONDITION_REVERT', 'ASSERTION_REVERT', 'RESOURCE_EXHAUSTED'}
PROFILE = 'evm-observable-feedback-v1'


class FeedbackError(ValueError):
    """Errors have fixed identifiers; never display original program inputs."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise FeedbackError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _input_class(quantity: int, gas: int, debit: int) -> str:
    if gas == 1:
        return 'forced-low-gas'
    if quantity == 0:
        return 'zero-quantity'
    if quantity > debit:
        return 'above-balance'
    if quantity == debit:
        return 'exact-balance'
    return 'below-balance'


def features(run: dict) -> dict:
    """Read only recorded observable EVM outcomes. Does not assert their origin.

    Callers MUST use evm_sequence_fuzz.replay before publishing. This pure
    calculation is independently unit-testable using clearly synthetic rows.
    """
    require(type(run) is dict and run.get('profile') == fuzz.PROFILE and
            run.get('schema_version') == 1 and type(run.get('seed')) is int and
            type(run.get('cases_per_control')) is int, 'RUN_SCHEMA')
    count = run['cases_per_control']
    require(run.get('sequences') == fuzz.corpus(run['seed'], count), 'CORPUS_NOT_CURRENT_GENERATOR')
    require(run.get('calls_per_sequence') == fuzz.STEPS and
            run.get('executions') == count * fuzz.STEPS * len(fuzz.CONTROLS) * len(fuzz.PROFILES) and
            run.get('constructor_executions') == len(fuzz.CONTROLS) * len(fuzz.PROFILES),
            'NATIVE_COUNTS')
    controls = run.get('controls')
    require(type(controls) is dict and set(controls) == set(fuzz.CONTROLS), 'CONTROL_INVENTORY')
    case_features: list[set[str]] = [set() for _ in range(count)]
    outcome_counts = Counter()
    witnesses: list[dict] = []
    for name in fuzz.CONTROLS:
        row = controls[name]
        require(type(row) is dict and set(row.get('profiles', {})) == set(fuzz.PROFILES), 'PROFILE_INVENTORY')
        first = row['profiles'][fuzz.PROFILES[0]]['runs']
        second = row['profiles'][fuzz.PROFILES[1]]['runs']
        require(type(first) is list and type(second) is list and
                len(first) == len(second) == count, 'CASE_INVENTORY')
        matching = []
        for index, sequence in enumerate(run['sequences']):
            base, alt = first[index], second[index]
            require(type(base) is dict and type(alt) is dict and
                    base.get('sequence_sha256') == alt.get('sequence_sha256') == sha(canonical(sequence)),
                    'SEQUENCE_IDENTITY')
            steps, other = base.get('steps'), alt.get('steps')
            require(type(steps) is list and type(other) is list and
                    len(steps) == len(other) == fuzz.STEPS, 'STEP_INVENTORY')
            previous = {'debit':15, 'credit':0, 'steps':0}
            for pos, ((quantity, gas), record, alt_record) in enumerate(zip(sequence, steps, other)):
                require(type(record) is dict and type(alt_record) is dict, 'STEP_SCHEMA')
                keys = ('quantity','gas','outcome','state_before','state_after','return_data','error')
                require(all(record.get(k) == alt_record.get(k) for k in keys),
                        'OBSERVABLE_CODEGEN_DISAGREEMENT')
                require(type(record.get('quantity')) is int and record['quantity'] == quantity and
                        type(record.get('gas')) is int and record['gas'] == gas and
                        type(record.get('state_before')) is dict and
                        record['state_before'] == previous and
                        type(record.get('state_after')) is dict and
                        set(record['state_after']) == {'debit','credit','steps'} and
                        all(type(v) is int and 0 <= v <= 255 for v in record['state_after'].values()) and
                        record.get('outcome') in OUTCOMES, 'OBSERVABLE_STEP_SCHEMA')
                # These oracles are NOT independent EVMs. Native replay is the
                # evidence source; the check protects this derivative from drift.
                observed = fuzz.verify_oracles(name, previous, quantity, gas)
                require(record['outcome'] == observed['status'] and
                        record['state_after'] == observed['state'] and
                        record['return_data'] == observed['return_data'] and
                        record['error'] == observed['error'], 'OBSERVABLE_REFERENCE_DISAGREEMENT')
                cls = _input_class(quantity, gas, previous['debit'])
                signature = f'{name}|phase={previous["steps"]}|input={cls}|outcome={record["outcome"]}'
                case_features[index].add(signature)
                outcome_counts[record['outcome']] += 1
                if record['outcome'] == 'ASSERTION_REVERT':
                    matching.append({'control': name, 'case_index': index,
                                     'prefix_length': pos+1, 'prefix':sequence[:pos+1],
                                     'trace_sha256':sha(canonical(steps[:pos+1])),
                                     'terminal_state_root':record['observed_state_root'],
                                     'terminal_outcome':'ASSERTION_REVERT',
                                     'assertion_reverted_and_not_persisted':True})
                previous = record['state_after']
            require(previous == base.get('final_state') == alt.get('final_state'),
                    'CASE_FINAL_STATE_DISAGREEMENT')
        if matching:
            witnesses.append(min(matching, key=lambda x:(x['prefix_length'],x['case_index'])))
    all_features = set().union(*case_features)
    require(bool(all_features), 'NO_OBSERVATIONS')
    # Deterministic set-cover heuristic, then remove any redundant selection.
    # This proves only single-deletion irredundancy, NOT global minimum size.
    remaining, available, selection = set(all_features), set(range(count)), []
    while remaining:
        selected = min(available, key=lambda i:(-len(case_features[i] & remaining),i))
        require(bool(case_features[selected] & remaining), 'COVERAGE_STALLED')
        selection.append(selected)
        remaining.difference_update(case_features[selected])
        available.remove(selected)
    for i in reversed(selection[:]):
        if set().union(*(case_features[j] for j in selection if j != i)) == all_features:
            selection.remove(i)
    assert set().union(*(case_features[i] for i in selection)) == all_features
    require(all(set().union(*(case_features[j] for j in selection if j != i)) != all_features
                for i in selection), 'CORPUS_NOT_IRREDUNDANT')
    return {'schema_version':1, 'profile':PROFILE,
            'native_source_digest':run['source_digest'],
            'source_run_sha256':sha(canonical(run)),
            'controls':list(fuzz.CONTROLS),
            'original_cases_per_control':count,
            'observed_step_count_one_profile':sum(outcome_counts.values()),
            'observed_step_count_all_profiles':sum(outcome_counts.values())*len(fuzz.PROFILES),
            'observed_outcome_counts_one_profile':dict(sorted(outcome_counts.items())),
            'observed_feature_count':len(all_features),
            'observed_features':sorted(all_features),
            'per_case_features':[{'case_index':i,'features':sorted(f)} for i,f in enumerate(case_features)],
            'selected_indices':sorted(selection),
            'selected_case_hashes':[sha(canonical(run['sequences'][i])) for i in sorted(selection)],
            'selection_method':'deterministic-greedy-with-single-removal',
            'all_observed_features_preserved':True,
            'global_minimum_corpus_proved':False,
            'witnesses':witnesses,
            'witness_minimality':'shortest-observed-prefix-per-control-not-global',
            'native_evm_replay_required':True,
            'evm_instruction_coverage_measured':False,
            'evm_branch_coverage_measured':False,
            'unknown_vulnerability_discovered':False,
            'vulnerability_confirmed':False,
            'external_target_executed':False,
            'independent_evm_used':False}


def _binding(native_root: Path, expected: str) -> dict:
    return {'schema_version':1,'native_source_digest':expected,
            'native_artifact_sha256':{n:sha(read_artifact(native_root,n))
                                       for n in sorted(fuzz.FILES|{'COMPLETE.json'})}}


def _audit(report: dict, bound: dict, created: str) -> bytes:
    native=load_components()
    log=native.audit.AuditLog(clock=lambda:created)
    log.append('evm.coverage.start',{'native_bundle_sha256':sha(canonical(bound))})
    log.append('evm.coverage.features',{'features_sha256':sha(canonical(report['observed_features']))})
    for witness in report['witnesses']:
        log.append('evm.coverage.witness',{'witness_sha256':sha(canonical(witness))})
    log.append('evm.coverage.complete',{'report_sha256':sha(canonical(report))})
    log.assert_intact()
    return canonical({'created_at':created,'entries':[asdict(e) for e in log.entries],
                      'native_provenance':list(native.provenance),
                      'remote_producer_authenticated':False})


def _render(report: dict) -> bytes:
    return ('# Evidencia de cobertura observable EVM\n\n'
            f"Rasgos distintos observados: {report['observed_feature_count']}.\n"
            f"Secuencias originales por control: {report['original_cases_per_control']}; "
            f"subconjunto greedy: {len(report['selected_indices'])}.\n"
            f"Prefijos observados con reversión por aserción: {len(report['witnesses'])}.\n\n"
            'Una reversión NO es pérdida persistente ni hallazgo explotable.\n'
            'Estos son rasgos de salida, estado e input, NO cobertura de PC/opcodes/ramas EVM.\n'
            'El subconjunto no es mínimo global. Los prefijos son los más cortos OBSERVADOS,\n'
            'no minimizaciones globales ni ejecuciones nuevas.\n'
            'Se requiere replay nativo completo del paquete fuente con los mismos motores.\n'
            'No se analizaron objetivos externos ni se autentica el productor remoto.\n').encode()


def _observe(native_root: Path, solc: Path, evm_binary: Path, expected: str) -> tuple[dict,dict]:
    # Bind exactly the bytes verified, including the small original manifest.
    # A changed native source bundle between replay and derivation is invalid.
    names=sorted(fuzz.FILES | {'COMPLETE.json'})
    before={n:read_artifact(native_root,n) for n in names}
    fuzz.replay(native_root,solc,evm_binary,expected)
    after={n:read_artifact(native_root,n) for n in names}
    require(before == after, 'NATIVE_ARTIFACT_CHANGED')
    report=features(strict_json(after['sequences.json']))
    bound={'schema_version':1, 'native_source_digest':expected,
           'native_artifact_sha256':{n:sha(after[n]) for n in names}}
    return report,bound


def create(native_root: Path, solc: Path, evm_binary: Path, expected: str, out: Path) -> dict:
    require(not out.exists() and not out.is_symlink() and
            not out.resolve().is_relative_to(ROOT.parent) and
            not out.resolve().is_relative_to(native_root.resolve()),
            'OUTPUT_MUST_BE_NEW_AND_PRIVATE')
    report,bound=_observe(native_root,solc,evm_binary,expected)
    created=datetime.now(timezone.utc).isoformat()
    files={'feedback.json':canonical(report), 'source-binding.json':canonical(bound),
           'audit.json':_audit(report,bound,created),'REVIEW.md':_render(report)}
    write_new_bundle(out,files)
    return verify(out,native_root,solc,evm_binary,expected)


def verify(root: Path, native_root: Path, solc: Path, evm_binary: Path, expected: str) -> dict:
    require(not root.is_symlink() and root.is_dir(),'BUNDLE_ROOT')
    marker=strict_json(read_artifact(root,'COMPLETE.json'))
    require(type(marker) is dict and set(marker)=={'schema_version','sha256'} and
            type(marker['schema_version']) is int and marker['schema_version']==1 and
            type(marker['sha256']) is dict and set(marker['sha256'])==FILES and
            {p.name for p in root.iterdir()}==FILES|{'COMPLETE.json'},'BUNDLE_MANIFEST')
    data={n:read_artifact(root,n) for n in FILES}
    require(all(sha(data[n]) == marker['sha256'][n] for n in FILES), 'BUNDLE_HASH')
    claimed_audit=strict_json(data['audit.json'])
    created=claimed_audit.get('created_at')
    require(type(created) is str and len(created) <= 40, 'AUDIT_TIME')
    try:
        moment=datetime.fromisoformat(created)
        require(moment.tzinfo is not None, 'AUDIT_TIMEZONE')
    except (ValueError, TypeError) as exc:
        raise FeedbackError('AUDIT_TIME') from exc
    report,bound=_observe(native_root,solc,evm_binary,expected)
    require(data['feedback.json']==canonical(report) and
            data['source-binding.json']==canonical(bound) and
            data['audit.json']==_audit(report,bound,created) and
            data['REVIEW.md']==_render(report),'NATIVE_FEEDBACK_REPLAY_DISAGREEMENT')
    require(all(read_artifact(root,n)==data[n] for n in FILES), 'BUNDLE_CHANGED')
    return {'status':'NATIVE_OBSERVABLE_FEEDBACK_VERIFIED',
            'observed_features':report['observed_feature_count'],
            'selected_cases':len(report['selected_indices']),
            'observed_assertion_prefixes':len(report['witnesses']),
            'instruction_coverage_measured':False,'vulnerability_confirmed':False}


def main(argv: list[str] | None = None) -> int:
    p=PrivateArgumentParser(description='Recompute EVM observable feedback on fixed owned controls only')
    sub=p.add_subparsers(dest='command',required=True)
    for name in ('review-evm-feedback','verify-evm-feedback'):
        q=sub.add_parser(name)
        q.add_argument('--native-bundle',type=Path,required=True)
        q.add_argument('--solc',type=Path,required=True)
        q.add_argument('--evm',type=Path,required=True)
        q.add_argument('--expected-source',required=True)
        q.add_argument('--out' if name=='review-evm-feedback' else '--bundle',type=Path,required=True)
    a=p.parse_args(argv)
    try:
        result=(create(a.native_bundle,a.solc,a.evm,a.expected_source,a.out)
                if a.command=='review-evm-feedback' else
                verify(a.bundle,a.native_bundle,a.solc,a.evm,a.expected_source))
        print(json.dumps(result,sort_keys=True))
        return 0
    except (ValueError,OSError,KeyError,TypeError,RuntimeError,OverflowError,RecursionError):
        print(json.dumps({'status':'NATIVE_OBSERVABLE_FEEDBACK_BLOCKED',
                          'instruction_coverage_measured':False,'vulnerability_confirmed':False}))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
