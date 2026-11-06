"""Execute eight fixed benign RBAC models for an evaluation smoke test.

These hand-designed regression fixtures are not a blind benchmark, vulnerability
corpus, critical findings, or a general estimate of detection effectiveness.
No uploaded code, external contracts, hosts or arbitrary engine are executable.
"""
from __future__ import annotations

from copy import deepcopy
import json
import hashlib
from pathlib import Path
from time import perf_counter_ns

from . import benchmark, permissions
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
FILES = {'corpus.json', 'run.json', 'traces.json', 'evaluation.json', 'REVIEW.md'}


def cases() -> list[dict]:
    """Reference labels declared before executing any engine."""
    rows = []
    for family in ('direct_roles', 'inherited_roles', 'revocation', 'disabled_user'):
        bad = permissions.example_policy()
        if family == 'direct_roles':
            bad['users']['alice']['roles'].append('approver')
            good = deepcopy(bad)
            good['roles']['preparer']['deny'] = ['approve']
        elif family == 'inherited_roles':
            bad['roles']['lead'] = {'inherits': ['preparer', 'approver'], 'allow': [], 'deny': []}
            bad['users']['alice']['roles'] = ['lead']
            good = deepcopy(bad)
            good['roles']['lead']['deny'] = ['approve']
        elif family == 'revocation':
            bad['roles']['alternate'] = {'inherits': ['reader'], 'allow': ['approve'], 'deny': []}
            bad['users']['bob']['roles'].append('alternate')
            good = deepcopy(bad)
            good['roles']['alternate']['deny'] = ['approve']
        else:
            bad['users']['bob']['disabled'] = True  # Contradicts its declared read-access property.
            good = deepcopy(bad)
            good['users']['bob']['disabled'] = False
        for truth, policy in (('positive', bad), ('negative', good)):
            # Illustrative property label; medium is a test taxonomy label, not bounty severity.
            rows.append({'case_id': family + '.' + truth, 'group_id': family,
                         'family': family, 'truth': truth, 'severity': 'medium' if truth == 'positive' else 'none',
                         'split': 'test', 'content_sha256': benchmark.digest(policy), 'policy': policy})
    return rows


def corpus_record() -> dict:
    return {'schema_version': 1, 'corpus_id': 'own-rbac-regressions-v1',
            'unit': 'one-reviewed-property-per-case', 'provenance': 'synthetic',
            'cases': [{k: v for k, v in row.items() if k != 'policy'} for row in cases()]}


def engine() -> dict:
    return {'control_source_sha256': benchmark.digest({
                name: hashlib.sha256(read_artifact(ROOT, name)).hexdigest()
                for name in ('benchmark_controls.py', 'permissions.py', 'benchmark.py', 'safe_io.py')}),
            'permissions_source_sha256': permissions._code_digest()}


def execute() -> tuple[dict, dict, dict]:
    """Actual function calls on frozen fixtures; no result substitution."""
    before = engine()
    corpus = corpus_record()
    benchmark.validate_corpus(corpus)
    records, traces = [], []
    for case in cases():
        start = perf_counter_ns()
        result = permissions.analyze_policy(case['policy'])
        elapsed_ms = max(0, (perf_counter_ns() - start + 999_999) // 1_000_000)
        status = result['status']
        decision = {'POLICY_ASSERTIONS_FAIL': 'positive', 'POLICY_ASSERTIONS_PASS': 'negative',
                    'POLICY_REVIEW_ONLY': 'abstain'}.get(status)
        benchmark.need(decision is not None, 'UNEXPECTED_PERMISSION_VERDICT')
        records.append({'case_id': case['case_id'], 'decision': decision,
                        'elapsed_ms': elapsed_ms, 'cost_micro_usd': None})
        traces.append({'case_id': case['case_id'], 'policy': case['policy'], 'result': result})
    benchmark.need(before == engine(), 'ENGINE_CHANGED_DURING_CONTROL')
    run = {'schema_version': 1, 'run_id': 'fixed-permissions-control',
           'producer': {'name': 'superhunter.permissions', 'source_sha256': before['permissions_source_sha256']},
           'corpus_sha256': benchmark.digest(corpus), 'evaluation_split': 'test', 'records': records}
    return corpus, run, {'schema_version': 1, 'fixed_fixture_only': True, 'engine': before, 'cases': traces}


def create(out: Path) -> dict:
    benchmark.need(not out.exists() and not out.is_symlink(), 'NEW_OUTPUT_REQUIRED')
    benchmark.need(not out.resolve().is_relative_to(ROOT.parent), 'OUTPUT_INSIDE_CODE')
    corpus, run, traces = execute()
    result = benchmark.evaluate(corpus, run)
    write_new_bundle(out, {'corpus.json': canonical(corpus), 'run.json': canonical(run),
                          'traces.json': canonical(traces), 'evaluation.json': canonical(result),
                          'REVIEW.md': benchmark.render(result)})
    return verify(out)


def verify(root: Path) -> dict:
    benchmark.need(not root.is_symlink(), 'ROOT_SYMLINK')
    marker = strict_json(read_artifact(root, 'COMPLETE.json'))
    benchmark.fields(marker, {'schema_version', 'sha256'}, 'CONTROL_MANIFEST')
    benchmark.need(type(marker['schema_version']) is int and marker['schema_version'] == 1 and
                   type(marker['sha256']) is dict and set(marker['sha256']) == FILES, 'CONTROL_MANIFEST')
    benchmark.need({p.name for p in root.iterdir()} == FILES | {'COMPLETE.json'}, 'CONTROL_FILE_SET')
    import hashlib
    data = {name: read_artifact(root, name) for name in FILES}
    benchmark.need(all(hashlib.sha256(raw).hexdigest() == marker['sha256'][name]
                       for name, raw in data.items()), 'CONTROL_HASH')
    corpus = corpus_record()
    benchmark.need(data['corpus.json'] == canonical(corpus), 'FIXED_CORPUS_CHANGED')
    traces = strict_json(data['traces.json'])
    benchmark.fields(traces, {'schema_version', 'fixed_fixture_only', 'engine', 'cases'}, 'TRACES_SCHEMA')
    benchmark.need(type(traces['schema_version']) is int and traces['schema_version'] == 1 and
                   traces['fixed_fixture_only'] is True and traces['engine'] == engine(), 'CONTROL_ENGINE_CHANGED')
    run = benchmark.validate_run(strict_json(data['run.json']), corpus)
    benchmark.need(run['producer'] == {'name': 'superhunter.permissions',
                   'source_sha256': engine()['permissions_source_sha256']}, 'CONTROL_PRODUCER')
    records = {row['case_id']: row for row in run['records']}
    benchmark.need(type(traces['cases']) is list and len(traces['cases']) == len(cases()), 'TRACE_COUNT')
    for expected, trace in zip(cases(), traces['cases']):
        benchmark.fields(trace, {'case_id', 'policy', 'result'}, 'TRACE_SCHEMA')
        benchmark.need(trace['case_id'] == expected['case_id'] and
                       canonical(trace['policy']) == canonical(expected['policy']), 'CONTROL_POLICY_CHANGED')
        actual = permissions.analyze_policy(expected['policy'])
        benchmark.need(canonical(trace['result']) == canonical(actual), 'CONTROL_REPLAY_MISMATCH')
        decision = 'positive' if actual['status'] == 'POLICY_ASSERTIONS_FAIL' else 'negative'
        benchmark.need(records[expected['case_id']]['decision'] == decision, 'CONTROL_DECISION_MISMATCH')
    result = benchmark.evaluate(corpus, run)
    benchmark.need(data['evaluation.json'] == canonical(result) and
                   data['REVIEW.md'] == benchmark.render(result), 'CONTROL_SCORE_MISMATCH')
    # This reexecutes known local properties, NOT a foreign producer or vulnerability.
    return {'status': 'FIXED_PERMISSION_EVALUATION_REPLAYED', 'cases': len(cases()),
            'counts': result['overall']['counts'], 'corpus_sha256': result['corpus_sha256'],
            'generalization_established': False, 'vulnerability_confirmed': False}


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Run or replay fixed benign RBAC benchmark controls only')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('benchmark-permissions').add_argument('--out', type=Path, required=True)
    sub.add_parser('verify-permission-benchmark').add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = create(args.out) if args.command == 'benchmark-permissions' else verify(args.bundle)
        print(json.dumps(result))
        return 0
    except (ValueError, OSError, KeyError, TypeError, RecursionError):
        print(json.dumps({'status': 'FIXED_BENCHMARK_ERROR', 'vulnerability_confirmed': False}))
        return 2


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1:]))
