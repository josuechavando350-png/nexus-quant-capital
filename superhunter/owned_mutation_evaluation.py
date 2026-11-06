"""Actual EVM evidence -> labelled score for four KNOWN, OWNED guard controls.

Not blind: the protected/mutated source pair and labels are present in this
module. A separate observation detector uses persisted state transitions, not
variant identifiers or labels, to decide. Two compiler outputs corroborate one
case; they are NOT two statistically independent discoveries.

Never accepts untrusted contracts, calldata, targets, RPC, or transactions.
Replays always regenerate evidence from fixed owned Solidity through solc/Geth.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from . import benchmark, evm_access_family as access, evm_pause_family as pause, quality
from .native_runtime import load_components
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
FILES = frozenset({'pause.json', 'access.json', 'corpus.json', 'predictions.json',
                   'evaluation.json', 'audit.json', 'REVIEW.md'})
SHA = re.compile(r'[0-9a-f]{64}\Z')
FAMILIES = ('pause', 'access')
TRUTH = {('pause', 'guarded'): 'negative',
         ('pause', 'guard_missing'): 'positive',
         ('access', 'protected'): 'negative',
         ('access', 'missing_auth_guard'): 'positive'}


class OwnedScoreError(ValueError):
    """Fixed errors: no untrusted paths or trace content in shared logs."""


def need(condition: bool, code: str) -> None:
    if not condition:
        raise OwnedScoreError(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _model_call(family: str, call: dict) -> bool:
    """Detect observed unauthorized persistent transfer, without reading variant.

    The field written by the original runner is cross-checked, not trusted as
    a finding. A failed call, even with a tentative bad state, is NOT positive.
    """
    before, after, status = call['before'], call['after'], call['status']
    need(type(before) is dict and type(after) is dict and
         type(status) is str and status in ('COMMITTED','REVERTED','OUT_OF_GAS'),
         'INVALID_OBSERVATION')
    need(type(call['amount']) is int and 0 <= call['amount'] <= 255,
         'INVALID_AMOUNT')
    amount = call['amount']
    need(all(type(v) is int and v >= 0 for k,v in before.items() if k != 'admin') and
         all(type(v) is int and v >= 0 for k,v in after.items() if k != 'admin'),
         'INVALID_OBSERVED_UNITS')
    need(set(before) == set(after), 'CHANGED_STATE_SCHEMA')
    if status != 'COMMITTED':
        need(before == after, 'REVERT_COMMITTED_STATE')
        return False
    if family == 'pause':
        need(set(before) == {'remaining','distributed','paused'} and
             before['remaining'] + before['distributed'] == 15 and
             after['remaining'] + after['distributed'] == 15 and
             before['paused'] in (0,1) and after['paused'] in (0,1) and
             call['operation'] in ('pause','release'), 'PAUSE_STATE_PROFILE')
        if call['operation'] == 'pause':
            need(after['remaining'] == before['remaining'] and
                 after['distributed'] == before['distributed'] and
                 after['paused'] == amount, 'PAUSE_EFFECT_MISMATCH')
            return False
        need(before['remaining'] - after['remaining'] == amount and
             after['distributed'] - before['distributed'] == amount and
             after['paused'] == before['paused'], 'RELEASE_EFFECT_MISMATCH')
        return amount > 0 and before['paused'] == 1
    need(family == 'access' and set(before) == {'admin','remaining','distributed'} and
         before['admin'] == after['admin'] == access.evm.SENDER and
         before['remaining'] + before['distributed'] == 10 and
         after['remaining'] + after['distributed'] == 10,
         'ACCESS_STATE_PROFILE')
    need(before['remaining'] - after['remaining'] == amount and
         after['distributed'] - before['distributed'] == amount,
         'ACCESS_EFFECT_MISMATCH')
    return amount > 0 and call['caller'] == access.GUEST


def _observed_cases(family: str, result: dict) -> list[dict]:
    """Four case-level decisions (two families x two source variants).

    Both compiler configurations must have identical observed semantics. Input
    coverage and every recorded flag must agree with the independent detector.
    """
    module = pause if family == 'pause' else access
    need(type(result) is dict and result.get('source_digest') and
         result.get('profile') == module.PROFILE and
         result.get('known_intentional_fixture', result.get('known_intentional_mutation')) is True and
         result.get('vulnerability_confirmed') is False,
         'UNSUPPORTED_OWNED_EVIDENCE')
    need(set(result['cases']) == set(module.VARIANTS) and
         set(result['builds']) == set(module.VARIANTS), 'VARIANT_COVERAGE')
    out = []
    for variant in module.VARIANTS:
        observations = []
        codegen_digests = []
        for codegen in module.CODEGEN:
            need(set(result['cases'][variant]) == set(module.CODEGEN) and
                 set(result['builds'][variant]) == set(module.CODEGEN),
                 'COMPILER_VARIANT_COVERAGE')
            build = result['builds'][variant][codegen]
            need(type(build) is dict and
                 build.get('source_sha256') == sha(module.owned_source(variant).encode()),
                 'SOURCE_VARIANT_MISMATCH')
            codegen_digests.append(build.get('runtime_sha256'))
            rows = result['cases'][variant][codegen]
            need(type(rows) is list and len(rows) == len(module.SEQUENCES),
                 'SCENARIO_COVERAGE')
            witnesses = []
            observed_steps = []
            for index, (row, scenario) in enumerate(zip(rows, module.SEQUENCES)):
                need(type(row) is dict and type(row.get('case')) is int and
                     row['case'] == index and type(row.get('calls')) is list and
                     len(row['calls']) == len(scenario), 'SCENARIO_ID_OR_LENGTH')
                previous = None
                for step, (call, expected) in enumerate(zip(row['calls'], scenario)):
                    need(type(call) is dict and type(call.get('step')) is int and
                         call['step'] == step, 'CALL_ORDER')
                    if family == 'pause':
                        operation, amount, gas = expected
                        need((call['operation'],call['amount'],call['gas']) == expected,
                             'UNEXPECTED_PAUSE_INPUT')
                    else:
                        caller, amount, gas = expected
                        need((call['caller'],call['amount'],call['gas']) == expected,
                             'UNEXPECTED_ACCESS_INPUT')
                    if previous is not None:
                        need(call['before'] == previous, 'OBSERVED_STATE_CHAIN')
                    bad = _model_call(family, call)
                    flag = ('paused_release_persisted' if family == 'pause' else
                            'unauthorized_effect')
                    need(type(call.get(flag)) is bool and call[flag] == bad,
                         'FLAG_STATE_DISAGREEMENT')
                    if bad:
                        witnesses.append({'scenario':index,'step':step,
                                          'observed_transition_sha256':sha(canonical({
                                              'before':call['before'], 'after':call['after'],
                                              'status':call['status'], 'amount':amount}))})
                    observed_steps.append({'status':call['status'], 'before':call['before'],
                                           'after':call['after'], 'is_positive':bad})
                    previous = call['after']
                need(previous == row['final_state'], 'FINAL_STATE_MISMATCH')
            observations.append({'codegen':codegen, 'steps':observed_steps,
                                 'witnesses':witnesses})
        # Different bytecodes are corroboration, NOT extra samples.
        need(observations[0]['steps'] == observations[1]['steps'] and
             observations[0]['witnesses'] == observations[1]['witnesses'],
             'INDEPENDENT_CODEGEN_OBSERVATIONS_DISAGREE')
        need(all(type(x) is str and SHA.fullmatch(x) for x in codegen_digests),
             'RUNTIME_DIGEST_MISSING')
        out.append({'case_id':family+'-'+variant, 'family':family,'variant':variant,
                    'witnesses':observations[0]['witnesses'],
                    'status':'positive' if observations[0]['witnesses'] else 'negative',
                    'compiler_correlations':2,
                    'runtime_sha256':dict(zip(module.CODEGEN,codegen_digests)),
                    'observed_steps_per_codegen':len(observations[0]['steps'])})
    return out


def analyze(pause_result: dict, access_result: dict, source_digest: str) -> dict:
    need(type(source_digest) is str and SHA.fullmatch(source_digest) is not None,
         'EXTERNAL_SOURCE_DIGEST_REQUIRED')
    need(pause_result.get('source_digest') == access_result.get('source_digest') == source_digest,
         'SOURCE_DIGEST_DISAGREEMENT')
    need(pause_result.get('solc_sha256') == access_result.get('solc_sha256') and
         pause_result.get('evm_sha256') == access_result.get('evm_sha256'),
         'TOOL_IDENTITY_DISAGREEMENT')
    observed = _observed_cases('pause',pause_result) + _observed_cases('access',access_result)
    case_rows = []
    predictions = []
    for row in observed:
        key = (row['family'],row['variant'])
        # Labels are separate from prediction computation above; known mutations
        # are not blind and both codegen artifacts belong to ONE grouped case.
        case_rows.append({'case_id':row['case_id'],'group_id':row['case_id'],
                          'content_sha256':sha(canonical({'family':row['family'],
                               'runtimes':row['runtime_sha256']})),
                          'split':'test','family':row['family'], 'truth':TRUTH[key],
                          'severity':'low' if TRUTH[key] == 'positive' else 'none'})
        predictions.append({'case_id':row['case_id'],'decision':row['status']})
    corpus = {'schema_version':1,'corpus_id':'owned-known-mutant-four-controls',
              'unit':'one-reviewed-property-per-case','provenance':'synthetic','cases':case_rows}
    # Reuse the existing benchmark's real confusion-matrix implementation; this
    # profile does not fabricate per-case time or monetary cost measurements.
    pairs = [(c, next(r for r in predictions if r['case_id']==c['case_id']))
             for c in case_rows]
    score = benchmark._section(pairs)
    # Independent set-based counting provides a second way to audit the scores.
    need(score['counts'] == benchmark._reference_counts(pairs), 'SCORE_DISAGREEMENT')
    metrics = {'overall':score, 'by_family':{f:benchmark._section(
               [(c,r) for c,r in pairs if c['family']==f]) for f in FAMILIES},
               'case_inventory_complete':True,'economic_cost_measured':False,
               'wall_clock_benchmarked':False}
    need(len(observed)==4 and sum(x['status']=='positive' for x in observed)==2,
         'KNOWN_CONTROL_REGRESSION')
    return {'schema_version':1,'status':'KNOWN_OWNED_EVM_SCORE',
            'source_digest':source_digest,'solc_sha256':pause_result['solc_sha256'],
            'evm_sha256':pause_result['evm_sha256'],
            'observations':observed,'corpus':corpus,'predictions':predictions,'metrics':metrics,
            'case_count':4,'compiler_runs_per_case':2,
            'native_execution_regenerated_here':False,
            'labels_known_to_developers':True, 'blind_benchmark':False,
            'severity_labels_represent_real_impact':False,
            'negative_decision_proves_absence_of_bugs':False,
            'unknown_vulnerability_found':False,'external_programs_analyzed':0,
            'generalization_established':False, 'vulnerability_confirmed':False}


def _run_native(solc: Path, evm_binary: Path, digest: str) -> tuple[dict,dict]:
    # Each native producer checks the pinned solc/Geth and fixed source digest.
    return pause.execute(solc,evm_binary,digest), access.execute(solc,evm_binary,digest)


def _audit(report: dict, at: str) -> bytes:
    native = load_components()
    log = native.audit.AuditLog(clock=lambda:at)
    log.append('owned.score.start', {'source_digest':report['source_digest']})
    for row in report['observations']:
        log.append('owned.score.case',{'case_id':row['case_id'],'sha256':sha(canonical(row))})
    log.append('owned.score.complete', {'score_sha256':sha(canonical(report))})
    log.assert_intact()
    return canonical({'entries':[asdict(x) for x in log.entries]})


def render(report: dict) -> bytes:
    counts = report['metrics']['overall']['counts']
    return ('# Evaluación EVM de mutaciones conocidas y propias\n\n'
            'Cuatro casos independientes de etiquetas (dos familias, dos variantes);\n'
            'dos compilaciones por caso NO se contabilizan como casos adicionales.\n'
            f"TP={counts['tp']} FP={counts['fp']} TN={counts['tn']} FN={counts['fn']}.\n"
            'Las predicciones provienen de cambios persistentes observados, no del nombre\n'
            'de la variante. Las etiquetas pertenecen a mutantes CONOCIDOS.\n'
            'No es benchmark ciego, medición de severidad real, detección original\n'
            'ni evidencia de precisión/recall fuera de estos controles.\n'
            'El tiempo EVM y el coste monetario por caso NO se han medido aquí.\n'
            'No se inventan costes ni tiempos de ejecución.\n').encode()


def _package(report: dict, pause_raw: bytes, access_raw: bytes, at: str) -> dict:
    return {'pause.json':pause_raw,'access.json':access_raw,
            'corpus.json':canonical(report['corpus']),
            'predictions.json':canonical(report['predictions']),
            'evaluation.json':canonical(report), 'audit.json':_audit(report,at),
            'REVIEW.md':render(report)}


def create(out: Path, solc: Path, evm_binary: Path, expected_source: str) -> dict:
    need(not out.exists() and not out.is_symlink() and
         not out.resolve().is_relative_to(ROOT.parent), 'NEW_PRIVATE_OUTPUT_REQUIRED')
    before = quality.source_snapshot()
    need(expected_source == sha(canonical(before)),'SOURCE_CHANGED')
    p,a=_run_native(solc,evm_binary,expected_source)
    need(quality.source_snapshot()==before,'SOURCE_CHANGED_DURING_NATIVE_RUN')
    result=analyze(p,a,expected_source)
    at=datetime.now(timezone.utc).isoformat()
    write_new_bundle(out,_package(result,canonical(p),canonical(a),at))
    return {'status':'KNOWN_OWNED_EVM_SCORE_CREATED','cases':result['case_count'],
            'counts':result['metrics']['overall']['counts'], 'vulnerability_confirmed':False}


def verify(root: Path, solc: Path, evm_binary: Path, expected_source: str) -> dict:
    need(root.is_dir() and not root.is_symlink(),'BUNDLE_DIRECTORY')
    marker=strict_json(read_artifact(root,'COMPLETE.json'))
    need(type(marker) is dict and set(marker)=={'schema_version','sha256'} and
         type(marker['schema_version']) is int and marker['schema_version']==1 and
         type(marker['sha256']) is dict and set(marker['sha256'])==FILES,
         'BUNDLE_MANIFEST')
    need({p.name for p in root.iterdir()}==FILES|{'COMPLETE.json'},'BUNDLE_FILE_SET')
    files={n:read_artifact(root,n) for n in FILES}
    need(all(sha(raw)==marker['sha256'][n] for n,raw in files.items()), 'BUNDLE_HASH')
    original=strict_json(files['evaluation.json'])
    need(original.get('source_digest')==expected_source,'WRONG_EXTERNAL_CODE_REFERENCE')
    before=quality.source_snapshot()
    need(sha(canonical(before))==expected_source,'SOURCE_CHANGED')
    p,a=_run_native(solc,evm_binary,expected_source)
    need(quality.source_snapshot()==before,'SOURCE_CHANGED_DURING_REPLAY')
    computed=analyze(p,a,expected_source)
    # Preserve the original audit time, but compare the entire semantic chain.
    saved_audit=strict_json(files['audit.json'])
    need(type(saved_audit) is dict and type(saved_audit.get('entries')) is list and
         saved_audit['entries'],'AUDIT_MISSING')
    timestamp=saved_audit['entries'][0].get('timestamp')
    need(type(timestamp) is str and datetime.fromisoformat(timestamp).tzinfo is not None,
         'AUDIT_TIMESTAMP')
    expected=_package(computed,canonical(p),canonical(a),timestamp)
    need(all(files[name]==expected[name] for name in FILES),'NATIVE_SCORE_REPLAY_DISAGREEMENT')
    return {'status':'KNOWN_OWNED_EVM_SCORE_REPLAY_VERIFIED','cases':computed['case_count'],
            'counts':computed['metrics']['overall']['counts'], 'vulnerability_confirmed':False}


def main(argv: list[str] | None = None) -> int:
    parser=PrivateArgumentParser(description='Score fixed owned known-mutation EVM cases only')
    subs=parser.add_subparsers(dest='command',required=True)
    make=subs.add_parser('score-owned-evm');check=subs.add_parser('verify-owned-evm-score')
    for p in (make,check):
        p.add_argument('--solc',type=Path,required=True)
        p.add_argument('--evm',type=Path,required=True)
        p.add_argument('--source-digest',required=True)
    make.add_argument('--out',type=Path,required=True)
    check.add_argument('--bundle',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        result=(create(args.out,args.solc,args.evm,args.source_digest) if
                args.command=='score-owned-evm' else
                verify(args.bundle,args.solc,args.evm,args.source_digest))
        print(json.dumps(result,sort_keys=True))
        return 0
    except (ValueError,OSError,TypeError,KeyError,RecursionError,OverflowError):
        print(json.dumps({'status':'KNOWN_OWNED_EVM_SCORE_BLOCKED',
                          'vulnerability_confirmed':False}))
        return 2


if __name__=='__main__':
    raise SystemExit(main())
