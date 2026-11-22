"""Audit published measurement coverage and generate mobile inventory report headers offline."""
import ast
from collections import Counter
from io import BytesIO
import math
from pathlib import Path
import sys
import tempfile
from zipfile import ZipFile

from .product_languages_batch import run
from .product_review import sha
from .product_sources import git
from .repository_boundary import git_object
from .safe_io import canonical, strict_json
from .product_reasoning import EvidenceError

AFL = 'AFLplusplus/AFLplusplus'
MOBSF = 'MobSF/Mobile-Security-Framework-MobSF'
AFL_REV = 'd798677805de81b50aa8f45beb0342ae1617b9d8'
MOBSF_REV = 'fa87c37892b264cf76bed8c358cc2d5d5323c8c2'
JADX_REV = '3cbbc2348141b7b51dbec2b227f334d6785547e6'
STUDY = 'benchmark/benchmark-results.jsonl'
WRITER = 'benchmark/benchmark.py'
TECH = 'mobsf/StaticAnalyzer/views/common/technology.py'
EXAMPLES = {
    'jadx-cli/src/test/resources/samples/resources-only.apk': 'abf0068451db0003c8491f67d37f55c1a154a74b',
    'jadx-cli/src/test/resources/samples/small.apk': '7ad35494a6edeb0ccd9d24cfe8d0f35a9d20f90f',
}

# The third-party module receives a fixed, finite map of archive member names.
# No APK bytes, report text, application packages or arbitrary inputs enter the worker.
WORKER = """import json, sys
sys.path.insert(0, '.')
from technology import detect_technologies
print(json.dumps({label: detect_technologies({'files': members}, 'android')
                  for label, members in json.load(sys.stdin).items()}))
"""


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def pinned_blobs(repo, revision, files):
    require(not repo.is_symlink() and git(repo, 'rev-parse', 'HEAD').decode().strip() == revision,
            'source checkout differs from the reviewed report revision')
    output = {}
    for path, (mode, blob) in files.items():
        require(git(repo, 'ls-tree', '-z', revision, '--', path) == f'{mode} blob {blob}\t{path}\0'.encode(),
                'report dependency is absent from the pinned source tree')
        size = int(git(repo, 'cat-file', '-s', blob))
        require(0 < size <= 500_000, 'report dependency size exceeds bound')
        raw = git(repo, 'cat-file', 'blob', blob)
        require(len(raw) == size and git_object('blob', raw) == blob, 'report dependency differs from its Git blob')
        output[path] = raw
    return output


def study_model(source):
    """Read the source producer's field declarations without importing or executing it."""
    model = {}
    for cls in ast.parse(source).body:
        if isinstance(cls, ast.ClassDef) and cls.name in ('Config', 'Hardware', 'Results', 'Run'):
            require(any(isinstance(d, ast.Name) and d.id == 'dataclass' for d in cls.decorator_list),
                    'benchmark record is missing its source annotation')
            model[cls.name] = {field.target.id: ast.unparse(field.annotation) for field in cls.body
                               if isinstance(field, ast.AnnAssign) and isinstance(field.target, ast.Name)}
    require(model.get('Run') == {'execs_per_sec': 'float', 'execs_total': 'float', 'fuzzers_used': 'int'}
            and set(model) == {'Config', 'Hardware', 'Results', 'Run'},
            'unreviewed historical benchmark field meanings')
    return model


def study_coverage(rows, model):
    """Count records eligible for a within-record comparison without comparing or ranking speeds."""
    outcomes = Counter()
    archived = set()
    for row in rows:
        require(isinstance(row, dict) and set(row) == set(model['Results'])
                and isinstance(row['config'], dict) and set(row['config']) == set(model['Config'])
                and isinstance(row['hardware'], dict) and set(row['hardware']) == set(model['Hardware'])
                and isinstance(row['targets'], dict)
                and row['targets'], 'benchmark row does not match the source model')
        signature = sha(canonical(row))
        require(signature not in archived, 'duplicate historical measurement record')
        archived.add(signature)
        for modes in row['targets'].values():
            require(isinstance(modes, dict) and modes and set(modes) <= {'singlecore', 'multicore'},
                    'unknown or missing benchmark measurement mode')
            for mode, run_row in modes.items():
                require(isinstance(run_row, dict) and set(run_row) == set(model['Run']), 'measurement fields differ from the source producer')
                speed, total, workers = (run_row[k] for k in ('execs_per_sec', 'execs_total', 'fuzzers_used'))
                require(type(speed) in (float, int) and math.isfinite(speed) and speed > 0
                        and type(total) is int and total > 0 and type(workers) is int and workers > 0
                        and (mode != 'singlecore' or workers == 1), 'inconsistent historical measurement')
                outcomes[mode] += 1
            outcomes['target_records'] += 1
            if len(modes) == 2 and modes['multicore']['fuzzers_used'] > 1:
                outcomes['paired_with_different_worker_counts'] += 1
            if 'multicore' in modes and modes['multicore']['fuzzers_used'] == 1:
                outcomes['multicore_label_with_one_worker'] += 1
    require(archived, 'empty benchmark archive')
    return {'archived_records': len(archived), 'measurement_slots': outcomes['singlecore'] + outcomes['multicore'],
            'target_records': outcomes['target_records'], 'singlecore_slots': outcomes['singlecore'],
            'multicore_slots': outcomes['multicore'], 'single_worker_multicore_labels': outcomes['multicore_label_with_one_worker'],
            'paired_within_one_target_record': outcomes['paired_with_different_worker_counts'],
            'target_records_without_eligible_pair': outcomes['target_records'] - outcomes['paired_with_different_worker_counts']}


def benchmark_coverage(root):
    pins = {WRITER: ('100755', '2d0dccd127d08e93b42db7ce45dec24b515e271c'),
            STUDY: ('100644', 'e284eb6f82004929d0bd49179dd789a8b0dc038e')}
    raw = pinned_blobs(root/'042-aflplusplus', AFL_REV, pins)
    model = study_model(raw[WRITER])
    rows = [strict_json(line) for line in raw[STUDY].splitlines()]
    summary = study_coverage(rows, model)
    # Independent count: compare source record/target keys before projecting away their names.
    single, multi = set(), set()
    for number, row in enumerate(rows):
        for target, modes in row['targets'].items():
            if 'singlecore' in modes:
                single.add((number, target))
            if 'multicore' in modes and modes['multicore']['fuzzers_used'] > 1:
                multi.add((number, target))
    require(summary['paired_within_one_target_record'] == len(single & multi), 'pair coverage differs across readers')
    try:
        study_coverage([rows[0], rows[0]], model)
    except EvidenceError:
        pass
    else:
        raise EvidenceError('duplicate benchmark records contributed credit')
    return {'revision': AFL_REV, 'role': 'reference', 'operation': 'audit_archived_benchmark_comparison_coverage',
            'source_manifest_sha256': sha(canonical(pins)), 'result': {
                'scope': 'third_party_archive_only', 'counts': summary, 'duplicate_record': 'rejected',
                'independent_pair_count': len(single & multi), 'superhunter_runtime_measurements': 0}}


def android_headers(root):
    pins = {TECH: ('100644', 'd03e91b8b0a0b16d9cd20c13ff25bbcc04a0972b')}
    module = pinned_blobs(root/'096-mobile-security-framework-mobsf', MOBSF_REV, pins)[TECH]
    archive_pins = {p: ('100644', blob) for p, blob in EXAMPLES.items()}
    artifacts = pinned_blobs(root/'098-jadx', JADX_REV, archive_pins)
    manifests = {}
    for path, data in artifacts.items():
        with ZipFile(BytesIO(data)) as archive:
            names = sorted(entry.filename for entry in archive.infolist() if not entry.is_dir())
        require(len(names) == len(set(names)) and len(names) <= 100, 'ambiguous APK member inventory')
        manifests[Path(path).stem] = names
    # Central-directory facts independently witness the exact header contents.
    resources = manifests['resources-only']
    small = manifests['small']
    require([p for p in resources if p.endswith(('.dex', '.so'))] == ['lib/x86_64/libcode.so']
            and [p for p in small if p.endswith(('.dex', '.so'))] == ['classes.dex'],
            'fixed APK inventories no longer witness the two report cases')
    cases = dict(manifests, without_native_library=[p for p in resources if not p.endswith('.so')],
                 without_dex=[p for p in small if not p.endswith('.dex')],
                 irrelevant_data_file_added=small + ['assets/private-label.txt'])
    with tempfile.TemporaryDirectory(prefix='nqc-mobile-report-') as temp:
        work = Path(temp)
        (work/'technology.py').write_bytes(module)
        raw = run(work, [sys.executable, '-I', '-S', '-B', '-c', WORKER], canonical(cases))
    outputs = strict_json(raw)
    require(set(outputs) == set(cases), 'mobile report cases differ')
    items = {}
    for case, rows in outputs.items():
        items[case] = {group['label']: group['items'] for group in rows}
        require(len(items[case]) == len(rows), 'duplicate mobile report group')
    require(items == {'resources-only': {'Languages': ['C/C++'], 'Native ABIs': ['x86_64']},
                      'small': {'Languages': ['Java']}, 'without_native_library': {}, 'without_dex': {},
                      'irrelevant_data_file_added': {'Languages': ['Java']}}, 'mobile report differs from archive member evidence')
    return {'revision': MOBSF_REV, 'role': 'execution', 'operation': 'classify_offline_apk_inventory_for_report_header',
            'source_manifest_sha256': sha(canonical(pins)), 'result': {'header_groups': items,
                'fixture_revision': JADX_REV, 'fixture_blobs': EXAMPLES, 'inventory_sha256': sha(canonical(manifests)),
                'apk_members_executed': 0}}


def observations(root):
    return {AFL: benchmark_coverage(root), MOBSF: android_headers(root)}
