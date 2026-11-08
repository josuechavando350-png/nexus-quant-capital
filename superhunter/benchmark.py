"""Offline evaluation of one labelled property per case, not a security scanner.

Exact case inventory; explicit abstentions/errors; corpus partition checks;
independent integer counting; private, reproducible evidence and DIABLO audit.
Labels, producer claims and source hashes do not authenticate a discovery.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .native_runtime import load_components, source_inventory
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
MAX_CASES = 4000
ID = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,95}\Z')
HASH = re.compile(r'[0-9a-f]{64}\Z')
SEVERITIES = ('low', 'medium', 'high', 'critical')
DECISIONS = ('positive', 'negative', 'abstain', 'error')
SPLITS = ('train', 'development', 'test')
FILES = {'corpus.json', 'run.json', 'evaluation.json', 'audit.json', 'REVIEW.md'}
CODE_FILES = ('benchmark.py', 'native_runtime.py', 'safe_io.py', 'privacy.py')


class BenchmarkError(ValueError):
    """Fixed error codes: no user-provided details printed by the CLI."""


def need(ok: bool, code: str) -> None:
    if not ok:
        raise BenchmarkError(code)


def fields(value: Any, keys: set[str], code: str) -> None:
    need(type(value) is dict and set(value) == keys, code)


def identifier(value: Any) -> None:
    need(type(value) is str and ID.fullmatch(value) is not None, 'INVALID_IDENTIFIER')


def hash_text(value: Any) -> None:
    need(type(value) is str and HASH.fullmatch(value) is not None, 'INVALID_SHA256')


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def validate_corpus(value: Any) -> dict:
    fields(value, {'schema_version', 'corpus_id', 'unit', 'provenance', 'cases'}, 'CORPUS_SCHEMA')
    need(type(value['schema_version']) is int and value['schema_version'] == 1, 'VERSION')
    identifier(value['corpus_id'])
    need(value['unit'] == 'one-reviewed-property-per-case', 'UNSUPPORTED_EVALUATION_UNIT')
    need(value['provenance'] in ('synthetic', 'curated'), 'PROVENANCE')
    rows = value['cases']
    need(type(rows) is list and 1 <= len(rows) <= MAX_CASES, 'CASE_LIMIT')
    ids, contents, groups = set(), {}, {}
    for row in rows:
        fields(row, {'case_id', 'group_id', 'content_sha256', 'split', 'family', 'truth', 'severity'}, 'CASE_SCHEMA')
        for key in ('case_id', 'group_id', 'family'):
            identifier(row[key])
        hash_text(row['content_sha256'])
        need(row['case_id'] not in ids, 'DUPLICATE_CASE_ID')
        ids.add(row['case_id'])
        need(row['split'] in SPLITS, 'CASE_SPLIT')
        need(row['truth'] in ('positive', 'negative'), 'CASE_TRUTH')
        need((row['truth'] == 'positive' and row['severity'] in SEVERITIES) or
             (row['truth'] == 'negative' and row['severity'] == 'none'), 'TRUTH_SEVERITY')
        previous = contents.get(row['content_sha256'])
        need(previous is None, 'DUPLICATE_CONTENT_OR_SPLIT_LEAKAGE')
        contents[row['content_sha256']] = row['split']
        old_split = groups.setdefault(row['group_id'], row['split'])
        need(old_split == row['split'], 'RELATED_GROUP_CROSSES_SPLITS')
    return deepcopy(value)


def validate_run(value: Any, corpus: dict) -> dict:
    fields(value, {'schema_version', 'run_id', 'producer', 'corpus_sha256', 'evaluation_split', 'records'}, 'RUN_SCHEMA')
    need(type(value['schema_version']) is int and value['schema_version'] == 1, 'VERSION')
    identifier(value['run_id'])
    producer = value['producer']
    fields(producer, {'name', 'source_sha256'}, 'PRODUCER_SCHEMA')
    identifier(producer['name']); hash_text(producer['source_sha256'])
    hash_text(value['corpus_sha256'])
    need(value['corpus_sha256'] == digest(corpus), 'RUN_CORPUS_BINDING')
    need(value['evaluation_split'] in ('development', 'test'), 'EVALUATION_SPLIT')
    selected = {c['case_id'] for c in corpus['cases'] if c['split'] == value['evaluation_split']}
    need(bool(selected), 'EMPTY_EVALUATION_SPLIT')
    rows = value['records']
    need(type(rows) is list and 1 <= len(rows) <= MAX_CASES, 'RESULT_LIMIT')
    ids = set()
    for row in rows:
        fields(row, {'case_id', 'decision', 'elapsed_ms', 'cost_micro_usd'}, 'RESULT_SCHEMA')
        identifier(row['case_id'])
        need(row['case_id'] not in ids, 'DUPLICATE_RESULT')
        ids.add(row['case_id'])
        need(type(row['decision']) is str and row['decision'] in DECISIONS, 'DECISION')
        need(type(row['elapsed_ms']) is int and 0 <= row['elapsed_ms'] <= 10**12, 'ELAPSED_MS')
        cost = row['cost_micro_usd']
        need(cost is None or (type(cost) is int and 0 <= cost <= 10**18), 'COST_MICRO_USD')
    # No silent subset scoring: explicitly record errors/abstentions for every case.
    need(ids == selected, 'INCOMPLETE_OR_UNEXPECTED_CASE_INVENTORY')
    return deepcopy(value)


def ratio(numerator: int, denominator: int) -> dict:
    return {'numerator': numerator, 'denominator': denominator,
            'value': numerator / denominator if denominator else None}


def _counts(rows: list[tuple[dict, dict]]) -> dict:
    totals = {key: 0 for key in ('tp', 'fp', 'tn', 'fn', 'abstain_positive', 'abstain_negative',
                                 'error_positive', 'error_negative')}
    for case, record in rows:
        truth, decision = case['truth'], record['decision']
        if decision == 'positive':
            key = 'tp' if truth == 'positive' else 'fp'
        elif decision == 'negative':
            key = 'fn' if truth == 'positive' else 'tn'
        else:
            key = decision + '_' + truth
        totals[key] += 1
    return totals


def _reference_counts(rows: list[tuple[dict, dict]]) -> dict:
    """Independent set intersections, not a call to the primary counter."""
    positives = {c['case_id'] for c, _ in rows if c['truth'] == 'positive'}
    negatives = {c['case_id'] for c, _ in rows if c['truth'] == 'negative'}
    decisions = {d: {c['case_id'] for c, r in rows if r['decision'] == d} for d in DECISIONS}
    return {'tp': len(positives & decisions['positive']), 'fp': len(negatives & decisions['positive']),
            'tn': len(negatives & decisions['negative']), 'fn': len(positives & decisions['negative']),
            'abstain_positive': len(positives & decisions['abstain']),
            'abstain_negative': len(negatives & decisions['abstain']),
            'error_positive': len(positives & decisions['error']),
            'error_negative': len(negatives & decisions['error'])}


def _section(rows: list[tuple[dict, dict]]) -> dict:
    counts = _counts(rows)
    need(counts == _reference_counts(rows), 'COUNTER_DISAGREEMENT')
    tp, fp, tn, fn = (counts[k] for k in ('tp', 'fp', 'tn', 'fn'))
    positive_n = tp + fn + counts['abstain_positive'] + counts['error_positive']
    negative_n = tn + fp + counts['abstain_negative'] + counts['error_negative']
    return {'cases': len(rows), 'positive_cases': positive_n, 'negative_cases': negative_n,
            'counts': counts, 'not_detected_positives': positive_n - tp,
            'precision': ratio(tp, tp + fp),
            'recall_all_positives': ratio(tp, positive_n),
            'recall_decided_cases_only': ratio(tp, tp + fn),
            'false_positive_rate_decided_negatives': ratio(fp, fp + tn),
            'decision_coverage': ratio(tp + fp + tn + fn, len(rows))}


def evaluate(raw_corpus: Any, raw_run: Any) -> dict:
    corpus = validate_corpus(raw_corpus)
    run = validate_run(raw_run, corpus)
    records = {r['case_id']: r for r in run['records']}
    rows = [(c, records[c['case_id']]) for c in sorted(corpus['cases'], key=lambda x: x['case_id'])
            if c['split'] == run['evaluation_split']]
    overall = _section(rows)
    by_severity = {}
    # Truth severity can stratify recall, not precision: false alarms have no true severity.
    for severity in SEVERITIES:
        selected = [(c, r) for c, r in rows if c['truth'] == 'positive' and c['severity'] == severity]
        result = _section(selected)
        by_severity[severity] = {'positive_cases': len(selected), 'detected': result['counts']['tp'],
            'missed_by_negative': result['counts']['fn'], 'abstained': result['counts']['abstain_positive'],
            'errored': result['counts']['error_positive'], 'recall_all_positives': result['recall_all_positives']}
    costs = [r['cost_micro_usd'] for _, r in rows]
    all_costs = all(x is not None for x in costs)
    known_costs = sum(x for x in costs if x is not None)
    total_cost = known_costs if all_costs else None
    tp = overall['counts']['tp']
    return {'schema_version': 1, 'status': 'LABELED_CASE_EVALUATION', 'unit': corpus['unit'],
            'corpus_sha256': digest(corpus), 'run_sha256': digest(run), 'producer_claimed': run['producer'],
            'evaluation_split': run['evaluation_split'], 'corpus_provenance': corpus['provenance'],
            'overall': overall, 'recall_by_label_severity': by_severity,
            'by_family': {family: _section([(c, r) for c, r in rows if c['family'] == family])
                          for family in sorted({c['family'] for c, _ in rows})},
            'resources': {'cost_complete': all_costs, 'known_cost_micro_usd': known_costs,
                'unknown_cost_cases': sum(x is None for x in costs), 'total_cost_micro_usd': total_cost,
                'cost_micro_usd_per_true_positive': ratio(total_cost, tp) if all_costs and tp else None,
                'sum_declared_case_elapsed_ms': sum(r['elapsed_ms'] for _, r in rows),
                'wall_clock_time_measured_here': False},
            'decisions': [{'case_id': c['case_id'], 'truth': c['truth'], 'decision': r['decision']} for c, r in rows],
            'complete_declared_case_inventory': True, 'declared_partition_checks_passed': True,
            'independent_counting_agreed': True, 'labels_authenticated': False,
            'producer_execution_authenticated': False, 'blind_evaluation_established': False,
            'generalization_established': False, 'vulnerability_confirmed': False,
            'external_targets_executed': False}


def code_identity() -> dict:
    return {'files': {name: hashlib.sha256(read_artifact(ROOT, name)).hexdigest() for name in CODE_FILES},
            'native_sources': source_inventory()}


def _audit(result: dict, at: str | None = None) -> dict:
    native = load_components()
    log = native.audit.AuditLog(**({'clock': lambda: at} if at else {}))
    log.append('benchmark.start', {'corpus_sha256': result['corpus_sha256'], 'run_sha256': result['run_sha256']})
    for row in result['decisions']:
        log.append('benchmark.case', {'case_sha256': digest(row)})
    log.append('benchmark.complete', {'result_sha256': digest(result)})
    log.assert_intact()
    return {'entries': [asdict(row) for row in log.entries], 'head': log.head, 'engine': code_identity()}


def _verify_audit(audit: dict, result: dict) -> None:
    fields(audit, {'entries', 'head', 'engine'}, 'AUDIT_SCHEMA')
    need(canonical(audit['engine']) == canonical(code_identity()), 'ENGINE_IDENTITY_MISMATCH')
    native = load_components()
    expected = [('benchmark.start', {'corpus_sha256': result['corpus_sha256'], 'run_sha256': result['run_sha256']})]
    expected += [('benchmark.case', {'case_sha256': digest(row)}) for row in result['decisions']]
    expected += [('benchmark.complete', {'result_sha256': digest(result)})]
    entries = audit['entries']
    need(type(entries) is list and len(entries) == len(expected), 'AUDIT_COVERAGE')
    previous = '0' * 64
    for index, (row, (event, data)) in enumerate(zip(entries, expected)):
        fields(row, {'index', 'timestamp', 'event', 'data', 'prev_hash', 'hash'}, 'AUDIT_ENTRY')
        need(type(row['index']) is int and row['index'] == index and row['prev_hash'] == previous, 'AUDIT_CHAIN')
        need(row['event'] == event and canonical(row['data']) == canonical(data), 'AUDIT_SEMANTICS')
        # Event time is bookkeeping, not a trusted timestamp.
        need(type(row['timestamp']) is str and 0 < len(row['timestamp']) <= 128, 'AUDIT_TIMESTAMP')
        need(native.audit.AuditEntry(**row).recompute() == row['hash'], 'AUDIT_HASH')
        previous = row['hash']
    need(previous == audit['head'], 'AUDIT_HEAD')


def render(result: dict) -> bytes:
    section = result['overall']
    lines = ['# SUPERHUNTER — evaluación de casos etiquetados', '',
             'Métricas del corpus declarado; no certificación ni eficacia general de SUPERHUNTER.',
             'No se ejecutan objetivos ni analizadores al puntuar resultados aportados.', '',
             f"Casos: {section['cases']}; positivos: {section['positive_cases']}; negativos: {section['negative_cases']}.",
             f"TP={section['counts']['tp']}; FP={section['counts']['fp']}; TN={section['counts']['tn']}; FN={section['counts']['fn']}."]
    for key in ('precision', 'recall_all_positives', 'recall_decided_cases_only', 'decision_coverage'):
        metric = section[key]
        lines.append(f"{key}: {metric['numerator']}/{metric['denominator']} = " +
                     ('no definida' if metric['value'] is None else format(metric['value'], '.6f')))
    lines += ['', f"Positivos no detectados, incluidas abstenciones/errores: {section['not_detected_positives']}.",
              'Las abstenciones no son aciertos; los errores tampoco desaparecen del denominador.',
              f"Costos completos: {result['resources']['cost_complete']}. Un costo desconocido no vale cero.", '',
              'No se acredita ceguera, representatividad, validez externa de etiquetas ni ejecución del productor.',
              'Los paquetes originales son privados. Su autenticidad debe comprobarse mediante custodia externa.', '']
    return '\n'.join(lines).encode()


def create(corpus_path: Path, run_path: Path, out: Path) -> dict:
    need(not out.exists() and not out.is_symlink(), 'NEW_OUTPUT_REQUIRED')
    need(not out.resolve().is_relative_to(ROOT.parent), 'OUTPUT_INSIDE_CODE')
    before = code_identity()
    raw_corpus, raw_run = (read_artifact(p.parent, p.name) for p in (corpus_path, run_path))
    result = evaluate(strict_json(raw_corpus), strict_json(raw_run))
    audit = _audit(result)
    need(before == code_identity(), 'CODE_CHANGED_DURING_EVALUATION')
    write_new_bundle(out, {'corpus.json': raw_corpus, 'run.json': raw_run,
                          'evaluation.json': canonical(result), 'audit.json': canonical(audit),
                          'REVIEW.md': render(result)})
    return verify(out, expected_corpus_sha256=result['corpus_sha256'])


def verify(root: Path, *, expected_corpus_sha256: str) -> dict:
    hash_text(expected_corpus_sha256)
    need(not root.is_symlink(), 'BUNDLE_ROOT_SYMLINK')
    marker = strict_json(read_artifact(root, 'COMPLETE.json'))
    fields(marker, {'schema_version', 'sha256'}, 'BUNDLE_SCHEMA')
    need(type(marker['schema_version']) is int and marker['schema_version'] == 1 and
         type(marker['sha256']) is dict and set(marker['sha256']) == FILES, 'BUNDLE_SCHEMA')
    need({p.name for p in root.iterdir()} == FILES | {'COMPLETE.json'}, 'BUNDLE_FILE_SET')
    data = {name: read_artifact(root, name) for name in sorted(FILES)}
    need(all(hashlib.sha256(raw).hexdigest() == marker['sha256'][name] for name, raw in data.items()), 'BUNDLE_HASH')
    corpus = strict_json(data['corpus.json'])
    need(digest(corpus) == expected_corpus_sha256, 'EXTERNAL_CORPUS_PIN_MISMATCH')
    result = evaluate(corpus, strict_json(data['run.json']))
    need(canonical(result) == data['evaluation.json'] and render(result) == data['REVIEW.md'], 'METRICS_REPLAY_DISAGREEMENT')
    _verify_audit(strict_json(data['audit.json']), result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Evaluate existing labelled results, not arbitrary code or targets')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('evaluate-benchmark')
    for name in ('corpus', 'run', 'out'):
        make.add_argument('--' + name, type=Path, required=True)
    check = sub.add_parser('verify-benchmark')
    check.add_argument('--bundle', type=Path, required=True)
    check.add_argument('--expected-corpus-sha256', required=True)
    args = parser.parse_args(argv)
    try:
        result = create(args.corpus, args.run, args.out) if args.command == 'evaluate-benchmark' else verify(
            args.bundle, expected_corpus_sha256=args.expected_corpus_sha256)
        print(json.dumps({'status': result['status'], 'cases': result['overall']['cases'],
                          'corpus_sha256': result['corpus_sha256'], 'vulnerability_confirmed': False,
                          'generalization_established': False}))
        return 0  # Score computed, not a declaration of model quality.
    except (ValueError, OSError, TypeError, KeyError, OverflowError, RecursionError):
        print(json.dumps({'status': 'BENCHMARK_EVALUATION_ERROR', 'vulnerability_confirmed': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
