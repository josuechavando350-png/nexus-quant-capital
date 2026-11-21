"""Grade freshly computed predictions on the eight published NQC header cohorts."""
from collections import Counter
from fractions import Fraction
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile

from .product_census_header import FIXTURE, FIXTURE_SHA, pinned
from .product_notice_ranking import ISOLATE
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .safe_io import canonical, strict_json
from .tools.evaluate_payload_types import CLASSIFIER, cases

SMOL = 'huggingface/smolagents'
HF = 'huggingface/transformers'
LANG = 'langfuse/langfuse'
RAGAS = 'vibrantlabsai/ragas'
PROMPT = 'promptfoo/promptfoo'
PINS = {
    SMOL: ('156-smolagents', '99721bdc3b6f502108751a93c5d7f08b1a04ce76',
           {'gaia_scorer.py': 'examples/open_deep_research/scripts/gaia_scorer.py'}),
    HF: ('164-transformers', '2f1bc5e321b9a736200a590d6e7743ccdeb60772',
         {'english_normalizer.py': 'src/transformers/models/whisper/english_normalizer.py'}),
    LANG: ('165-langfuse', '306cdfb8b38ac8ca35b9c09cebbf2cd110d06978',
           {'statistics.ts': 'web/src/features/score-analytics/lib/statistics-utils.ts'}),
    RAGAS: ('166-ragas', '8c63f10d500c44efbf24fdb9e2920de2104c321c',
            {'ragas_utils.py': 'src/ragas/metrics/utils.py'}),
    PROMPT: ('167-promptfoo', 'b1aca6657b8d7353815e78a9bd35273ddcd3fccc',
             {'equals.ts': 'src/assertions/equals.ts', 'normalize.ts': 'src/assertions/normalize.ts'}),
}
HOLDOUT = 'superhunter/product_supply/review-115-holdout.json'
HOLDOUT_SHA = 'cda3f55c1e72c527d5dcd2f84c4e3ce2252a3225d45243dfc47a2cc7d93df007'
REGEX_SHA = '8a966a5afe94ed9fb06deeecd9e3e51c3a5ab7d920e13f8128338e3fcdfed2b0'
WORKERS = (
    ('product_evaluation_worker.py', 'superhunter/product_evaluation_worker.py',
     '4c43938f7e9c82cfa9a4b47d7927a0047c3047689eaa7baa20b30f17c6c7b15f'),
    ('product_evaluation_worker.mjs', 'superhunter/product_supply/evaluation-worker-node.txt',
     '9142a8b2c81e206334b0670a419e697de17539f9b7049df31dda45590e136295'),
)
FIELDS = ('extraData', 'gasUsed', 'hash', 'logsBloom', 'miner')
MODES = ('original', 'without_extra_data', 'upper_case_fields', 'punctuated_fields', 'partial_field_mixup')


def samples(root):
    protocol = strict_json(pinned(ROOT, HOLDOUT, HOLDOUT_SHA))
    pinned(ROOT, 'superhunter/product_source_references.py', CLASSIFIER)
    block = strict_json(pinned(ROOT, FIXTURE, FIXTURE_SHA))['block']
    rows = {mode: [] for mode in MODES}
    keys = set()
    for cohort in protocol['cohorts']:
        blocks, labels = cases(cohort['seed'], block)
        if sha(canonical(blocks)) != cohort['inputs_sha256'] or sha(canonical(labels)) != cohort['labels_sha256']:
            raise EvidenceError('regenerated evaluation cohort differs from the released corpus')
        result = subprocess.run([*ISOLATE, sys.executable, '-B', '-m', 'superhunter.tools.evaluate_payload_types',
                                 '--predict', str(root.parent)], input=canonical(blocks), cwd=ROOT,
                                capture_output=True, check=True, timeout=30)
        predictions = strict_json(result.stdout)
        if predictions.keys() != labels.keys() or sha(canonical(predictions)) != cohort['predictions_sha256']:
            raise EvidenceError('fresh classifier output differs from the reviewed predictions')
        for key in sorted(labels):
            if key in keys:
                raise EvidenceError('case identifier repeated across cohorts')
            keys.add(key)
            target = labels[key] or ['valid']
            observed = predictions[key] or ['valid']
            if len(target) != 1 or len(observed) != 1:
                raise EvidenceError('invalid single-field evaluation case')
            truth, actual = target[0], observed[0]
            alternatives = (actual, 'valid' if actual == 'extraData' else actual,
                            actual.upper() if actual != 'valid' else actual,
                            actual[:1] + '.' + actual[1:] if actual != 'valid' else actual,
                            'hash' if actual == 'gasUsed' and int(key[-1], 16) < 8 else actual)
            for mode, answer in zip(MODES, alternatives, strict=True):
                rows[mode].append({'id': key, 'truth': truth, 'answer': answer})
    if len(keys) != 768:
        raise EvidenceError('case set incomplete')
    return rows


def material(work, root):
    origins = {}
    for repo, (checkout, revision, paths) in PINS.items():
        cmd = ['git', '--no-replace-objects', '-C', str(root / checkout)]
        def git(*args):
            return subprocess.run([*cmd, *args], check=True, capture_output=True, timeout=20).stdout
        if git('rev-parse', 'HEAD').decode().strip() != revision:
            raise EvidenceError('evaluation checkout differs from pinned source')
        origins[repo] = {}
        for name, path in paths.items():
            data = git('cat-file', 'blob', revision + ':' + path)
            (work / name).write_bytes(data)
            origins[repo][path] = sha(data)
    env_path = os.environ.get('NQC_EVALUATION_WHEEL')
    if not env_path:
        raise EvidenceError('NQC_EVALUATION_WHEEL must identify the regex wheel in the existing DSPy/Inspect kit')
    with Path(env_path).open('rb') as f:
        raw = f.read(1_000_001)
    if sha(raw) != REGEX_SHA:
        raise EvidenceError('evaluation regex wheel differs from the reviewed pin')
    with ZipFile(BytesIO(raw)) as z:
        for name in z.namelist():
            if name.startswith('regex/') and name.endswith(('.so', '.py')):
                dest = work/'lib'/name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(name))
    return origins


def agreement(rows):
    pairs = Counter((r['truth'], r['answer']) for r in rows)
    target = Counter(r['truth'] for r in rows)
    observed = Counter(r['answer'] for r in rows)
    n = len(rows)
    po = Fraction(sum(value for (a, b), value in pairs.items() if a == b), n)
    pe = sum(Fraction(count * observed[name], n * n) for name, count in target.items())
    kappa = (po - pe) / (1 - pe) if pe != 1 else Fraction(1)
    weighted = sum(Fraction(2 * pairs[name, name] * count, n * (count + observed[name])) for name, count in target.items())
    return {'kappa': float(kappa), 'agreement': float(po), 'weighted_f1': float(weighted)}


def fbeta(rows, field, beta):
    tp = sum(r['truth'] == r['answer'] == field for r in rows)
    true = sum(r['truth'] == field for r in rows)
    predicted = sum(r['answer'] == field for r in rows)
    weight = Fraction(str(beta)) ** 2
    return float((1 + weight) * tp / (weight*true + predicted)) if true or predicted else 0.


def score_record(rows, observed, expected):
    if len(observed) != len(rows) or any(type(v) is not bool for v in observed) or observed != expected:
        raise EvidenceError('upstream per-case grader differs from its independent oracle')
    errors = [r['id'] for r, passed in zip(rows, observed, strict=True) if not passed]
    return {'correct': len(rows) - len(errors), 'total': len(rows), 'errors_sha256': sha(canonical(sorted(errors))),
            'examples_of_errors': sorted(errors)[:4]}


def assess(rows_by_mode, py, js):
    if set(rows_by_mode) != set(MODES) or set(py) != set(MODES) or set(js) != set(MODES):
        raise EvidenceError('evaluation modes missing')
    out = {repo: {} for repo in PINS}
    for mode, rows in rows_by_mode.items():
        literal = [r['truth'] == r['answer'] for r in rows]
        gaia = [r['truth'].lower() == r['answer'].lower().replace('.', '') for r in rows]
        whisper = [r['truth'].lower() == r['answer'].lower().replace('.', ' ') for r in rows]
        out[PROMPT][mode] = score_record(rows, js[mode]['promptfoo'], literal)
        out[SMOL][mode] = score_record(rows, py[mode]['gaia'], gaia)
        out[HF][mode] = score_record(rows, py[mode]['whisper'], whisper)
        for repo, flags in [(SMOL, gaia), (HF, whisper)]:
            out[repo][mode]['false_accepts_against_literal_fields'] = sum(v and not e for v, e in zip(flags, literal))
        stats = js[mode]['langfuse']
        oracle = agreement(rows)
        if (set(stats) != set(oracle) or any(type(stats[k]) not in (int, float) or
                not abs(oracle[k] - stats[k]) <= .0005000001 for k in oracle)):
            raise EvidenceError('Langfuse categorical statistics differ from contingency-table arithmetic')
        out[LANG][mode] = stats
        grades = py[mode]['ragas']
        if set(grades) != set(FIELDS):
            raise EvidenceError('missing per-field Ragas score')
        for name, beta_scores in grades.items():
            if set(beta_scores) != {'0.5', '1.0', '2.0'} or any(
                    not abs(score - fbeta(rows, name, beta)) <= 1e-12 for beta, score in beta_scores.items()):
                raise EvidenceError('Ragas F-beta differs from independent field counts')
        out[RAGAS][mode] = grades
    if (out[PROMPT]['original']['correct'] != 768 or out[PROMPT]['without_extra_data']['correct'] >= 768
            or out[SMOL]['punctuated_fields']['false_accepts_against_literal_fields'] != 384
            or out[HF]['upper_case_fields']['false_accepts_against_literal_fields'] != 384
            or out[HF]['punctuated_fields']['false_accepts_against_literal_fields'] != 0):
        raise EvidenceError('grading controls failed to distinguish field identity and text normalization')
    mixup = out[RAGAS]['partial_field_mixup']
    if not (0 < mixup['gasUsed']['2.0'] < mixup['gasUsed']['0.5'] < 1
            and 0 < mixup['hash']['0.5'] < mixup['hash']['2.0'] < 1):
        raise EvidenceError('precision and recall controls failed to distinguish asymmetric errors')
    return out


def review(source_root: Path):
    root = Path(source_root).resolve()
    rows = samples(root)
    data = canonical(rows)
    node = shutil.which('node')
    if not node:
        raise EvidenceError('evaluation requires Node with native TypeScript and module hooks')
    with tempfile.TemporaryDirectory(prefix='nqc-grade-') as w:
        work = Path(w)
        origins = material(work, root)
        (work/'package.json').write_text('{"type":"module"}')
        for filename, resource, expected in WORKERS:
            (work / filename).write_bytes(pinned(ROOT, resource, expected))
        def run(args):
            result = subprocess.run([*ISOLATE, '/usr/bin/prlimit', '--cpu=25', '--nofile=96', '--', *args],
                                    input=data, cwd=work, env={'HOME': w}, check=True, capture_output=True, timeout=32)
            return strict_json(result.stdout)
        py = run([sys.executable, '-I', '-B', 'product_evaluation_worker.py'])
        js = run([node, '--max-old-space-size=128', 'product_evaluation_worker.mjs'])
    result = assess(rows, py, js)
    roles = {SMOL: 'score field answers with GAIA normalization and detect false agreements',
             HF: 'measure Whisper normalization collisions against exact header field identities',
             RAGAS: 'score recall and precision sensitivities for five exact field classes with F-beta',
             LANG: 'grade categorical agreement, weighted F1 and Cohen kappa',
             PROMPT: 'score structured invalid_fields predictions with object equality'}
    return {repo: {'operation': roles[repo], 'revision': PINS[repo][1], 'source_sha256': origins[repo],
                   'case_matrix_sha256': sha(data), 'cases': 768, 'cohorts': 8, 'modes': values,
                   'published_protocol_sha256': HOLDOUT_SHA} for repo, values in result.items()}
