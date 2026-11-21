"""Compare two independent native scorers on NQC's fixed payload representability task."""
import math
from pathlib import Path
import subprocess
import sys
import tempfile

from .product_census_header import FIXTURE, FIXTURE_SHA, pinned
from .product_notice_ranking import ISOLATE, install_wheels
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_sources import git
from .repository_boundary import git_object
from .safe_io import canonical, read_artifact, strict_json
from .tools.evaluate_payload_types import CLASSIFIER, SEED, cases

ENGINES = {
    'dspy': {'repo': 'stanfordnlp/dspy', 'folder': 'upstream/155-dspy', 'prefix': '',
             'revision': '226d534da38ab8a39e4d6383e01e121dab50da51',
             'lock': '086ca7d8bb5f5d490fbbb3c5613c2d75819bf0a35a35c5b46bc38c7d5cebf8d0',
             'modules': ['dspy/evaluate/evaluate.py', 'dspy/primitives/example.py']},
    'inspect': {'repo': 'ukgovernmentbeis/inspect_ai', 'folder': 'upstream/168-inspect_ai', 'prefix': 'src/',
                'revision': '82925564c9330e5440d490a7d97d037e11e66c9a',
                'lock': 'b98b0a49a2b350e5503fb6be225dbceebe188884125a6e2bc831c14fa3bd4afb',
                'modules': ['inspect_ai/scorer/_classification.py', 'inspect_ai/scorer/_metrics/accuracy.py',
                            'inspect_ai/scorer/_metric.py', 'inspect_ai/solver/_task_state.py']}}


def lockfile(engine):
    return 'superhunter/product_supply/' + engine + '-scores-linux-py312.txt'


def observations(checkout):
    pinned(ROOT, 'superhunter/product_source_references.py', CLASSIFIER)
    base = strict_json(pinned(ROOT, FIXTURE, FIXTURE_SHA))['block']
    blocks, labels = cases(SEED, base)
    proc = subprocess.run([*ISOLATE, sys.executable, '-B', '-m', 'superhunter.tools.evaluate_payload_types',
                           '--predict', str(checkout.resolve())], input=canonical(blocks), cwd=ROOT,
                          check=True, capture_output=True, timeout=30)
    guesses = strict_json(proc.stdout)
    if set(guesses) != set(labels):
        raise EvidenceError('prediction coverage differs from withheld labels')
    rows = {'all_fields': {}, 'without_extra_data': {}}
    def encode(names):
        return 'valid' if not names else 'invalid ' + ' '.join(names)
    for key, prediction in guesses.items():
        for mode, observed in (('all_fields', prediction), ('without_extra_data', [n for n in prediction if n != 'extraData'])):
            rows[mode][key] = {'expected': encode(labels[key]), 'observed': encode(observed)}
    return rows


def assess(rows, native):
    if native.keys() != rows.keys():
        raise EvidenceError('native scorer omitted a trial')
    results = {}
    for name, caseset in rows.items():
        expected = {k: v['expected'] == v['observed'] for k, v in caseset.items()}
        got = native[name]
        percentage = round(100 * sum(expected.values())/len(expected), 2)
        reported = got.get('percentage')
        if (type(reported) not in (int, float) or not math.isfinite(reported) or
                canonical(got.get('by_id')) != canonical(expected) or abs(percentage - reported) > 0.00501):
            raise EvidenceError('native scorer disagrees with case-level reference')
        results[name] = {'cases': len(expected), 'correct': sum(expected.values()), 'percentage': percentage,
                         'errors': sorted(k for k, success in expected.items() if not success),
                         'verdicts_sha256': sha(canonical(expected))}
    if results['all_fields']['correct'] <= results['without_extra_data']['correct']:
        raise EvidenceError('evaluation did not detect the removed check')
    return results


def native_score(name, checkout, wheelhouse, rows):
    engine = ENGINES[name]
    repo = checkout/engine['folder']
    if git(repo, 'rev-parse', 'HEAD').decode().strip() != engine['revision']:
        raise EvidenceError('scorer source revision differs')
    with tempfile.TemporaryDirectory(prefix='nqc-native-scores-') as tmp:
        work = Path(tmp)
        env = {'HOME': tmp, 'TMPDIR': tmp, 'PATH': '/usr/bin:/bin', 'OPENBLAS_NUM_THREADS': '1',
               'OMP_NUM_THREADS': '1', 'DSPY_CACHEDIR': str(work/'cache'), 'HF_HUB_OFFLINE': '1',
               'DO_NOT_TRACK': '1', 'PYTHONIOENCODING': 'utf-8'}
        install_wheels(wheelhouse, work, env, lock_path=lockfile(name), lock_digest=engine['lock'], producer=name)
        source_blobs = {}
        for path in engine['modules']:
            oid = git(repo, 'rev-parse', engine['revision'] + ':' + engine['prefix'] + path).decode().strip()
            if git_object('blob', read_artifact(work/'lib', path)) != oid:
                raise EvidenceError('installed native scoring module differs from reviewed source')
            source_blobs[path] = oid
        worker = Path(__file__).with_name('product_scores_worker.py')
        proc = subprocess.run([*ISOLATE, sys.executable, '-I', '-B', '-S', str(worker), name], input=canonical(rows),
                              cwd=work, env=env, capture_output=True, timeout=90)
        if proc.returncode:
            raise EvidenceError(name + ' scoring worker failed: ' + proc.stderr.decode(errors='replace')[-700:])
        result = assess(rows, strict_json(read_artifact(work, 'scores.json')))
    return {'trials': result, 'revision': engine['revision'], 'lock_sha256': engine['lock'],
            'active_source_blobs': source_blobs}


def attach(index, checkout, kit):
    if checkout is None or index.census_header is None:
        raise EvidenceError('scoring experiment requires the pinned Census session')
    rows = observations(checkout)
    outputs = {k: native_score(k, checkout, kit/(k+'-wheels'), rows) for k in ENGINES}
    if outputs['dspy']['trials'] != outputs['inspect']['trials']:
        raise EvidenceError('independent scorers disagree')
    index.score_comparison = {'cases_sha256': sha(canonical(rows)), 'fixture_sha256': FIXTURE_SHA,
                              'classifier_sha256': CLASSIFIER, 'seed': SEED, 'engines': outputs}
    for name, engine in ENGINES.items():
        index.repos[engine['repo']]['score_comparison_receipt'] = {
            'query': 'score-comparison', 'engine': name, 'revision': engine['revision'],
            'case_sha256': sha(canonical(rows)), 'result_sha256': sha(canonical(outputs[name]))}
