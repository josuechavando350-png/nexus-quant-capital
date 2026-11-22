"""Reconcile published report counts without retaining source paths or request content."""
from collections import Counter
from math import isclose
import re
from xml.etree import ElementTree

from .product_reasoning import EvidenceError
from .product_review import sha
from .product_sources import git
from .repository_boundary import git_object
from .safe_io import canonical, strict_json

FUZZTEST = 'google/fuzztest'
RESOURCE_TEST = 'centipede/stats_test.cc'
DYNAMORIO = 'DynamoRIO/dynamorio'
WINDOWS = ('clients/drcachesim/tests/offline-skip.expect', 'clients/drcachesim/tests/offline-skip2.expect')
WINDOW_SOURCE = 'suite/tests/CMakeLists.txt'
ZAP = 'zaproxy/zaproxy'
RESTLER = 'microsoft/restler-fuzzer'
OSS_FUZZ = 'google/oss-fuzz'
ZAP_MERGED = 'examples/ZAP_2.4.3_report-merged.xml'
ZAP_FLAT = 'examples/ZAP_2.4.3_report-unmerged.xml'
SPEC_COVERAGE = 'restler/unit_tests/log_baseline_test_files/ab_flaky_b_all_combinations_speccov.json'
LLVM_SUMMARY = 'infra/cifuzz/test_data/example_coverage_report_summary.json'
PROJECTS = {
    FUZZTEST: ('116-fuzztest', '29e1c6a0fc149dc108dfff122bd6aac5efbe85b5', {
        RESOURCE_TEST: '491a428d9bb3271f38ff71efe6b4dc1acdb0ba41'}),
    DYNAMORIO: ('133-dynamorio', '0fd459d944cb13056c7f29eba1d593a637bf3b68', {
        WINDOWS[0]: 'a4db056f9b6b99e5409870d266683fbc53b26f30',
        WINDOWS[1]: '444c2c81bb46e0c14b2d103379404b5e524a89ca',
        WINDOW_SOURCE: '1379fa9c4e374b993b67944b8f9cea11dcf0b706'}),
    ZAP: ('002-zaproxy', '42d1450e6cedc921dae6b4b7103cbe40f8cd98df', {
        ZAP_MERGED: 'c28968d7deb23628341d85cc6d1caba80b9cb2ef',
        ZAP_FLAT: 'e7d9fcdcb0b6f98de2aa78e8b3f44db2b5bfdbbd'}),
    RESTLER: ('029-restler-fuzzer', '6d984deedbc54aad957fa3da0c7e9e5df23a2aee', {
        SPEC_COVERAGE: 'd4eff36363905dfae253bd8ac1b124cf9d3ba87a'}),
    OSS_FUZZ: ('117-oss-fuzz', '48099ac8ad840c31d745f6e2a7627195481cb1df', {
        LLVM_SUMMARY: '0004a1b57b276950566d1316ce8ec6ea9d70b278'}),
}
METRICS = ('branches', 'functions', 'instantiations', 'lines', 'regions')
FAILURE_FLAGS = ('sequence_failure', 'resource_failure', 'parser_failure', '500')


def zap_counts(raw, *, merged):
    if len(raw) > 500_000 or b'\0' in raw or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise EvidenceError('invalid coverage XML input')
    try:
        root = ElementTree.fromstring(raw)
    except ElementTree.ParseError as exc:
        raise EvidenceError('malformed coverage XML') from exc
    if root.tag != 'OWASPZAPReport' or root.get('version') != '2.4.3':
        raise EvidenceError('unknown report version')
    groups = Counter()
    samples = 0
    alerts = root.findall('site/alerts/alertitem')
    if not alerts or len(alerts) > 4096 or len(root.findall('site')) != 1:
        raise EvidenceError('invalid fixed report membership')

    def integer(row, field):
        items = row.findall(field)
        if len(items) != 1 or not re.fullmatch('[0-9]{1,8}', items[0].text or ''):
            raise EvidenceError('invalid numeric report field')
        return int(items[0].text)

    for row in alerts:
        key = integer(row, 'pluginid'), integer(row, 'riskcode'), integer(row, 'confidence')
        if key[0] < 1 or key[1] > 3 or key[2] > 4:
            raise EvidenceError('invalid report classification')
        if merged:
            count = integer(row, 'count')
            visible = len(row.findall('instances/instance'))
            if key in groups or len(row.findall('instances')) != 1 or not 0 < visible <= count or row.find('uri') is not None:
                raise EvidenceError('invalid grouped occurrences')
            samples += visible
        else:
            if len(row.findall('uri')) != 1 or row.find('instances') is not None or row.find('count') is not None:
                raise EvidenceError('invalid individual occurrence')
            count = 1
        groups[key] += count
    return groups, samples


def reconcile_alerts(merged, flat):
    groups, samples = zap_counts(merged, merged=True)
    individuals, _ = zap_counts(flat, merged=False)
    if groups != individuals:
        raise EvidenceError('group counts disagree with individual occurrences')
    risks = Counter()
    for (_, risk, _), count in groups.items():
        risks[str(risk)] += count
    return {'rules': len({key[0] for key in groups}), 'occurrences': groups.total(),
            'displayed_examples': samples, 'occurrences_by_risk': dict(sorted(risks.items()))}


def specification_coverage(raw):
    rows = strict_json(raw)
    decisions = Counter()
    if not rows or len(rows) > 4096:
        raise EvidenceError('invalid specification coverage inventory')
    for row in rows.values():
        valid = row['valid']
        flags = [row['invalid_due_to_' + name] for name in FAILURE_FLAGS]
        if any(type(bit) is not int or bit not in (0, 1) for bit in [valid, *flags]):
            raise EvidenceError('invalid specification coverage flag')
        status = row['status_code']
        if status is not None and (not isinstance(status, str) or not re.fullmatch('[1-5][0-9]{2}', status)):
            raise EvidenceError('invalid coverage response status')
        if valid and (any(flags) or status is None):
            raise EvidenceError('successful coverage record has inconsistent outcome')
        if valid:
            outcome = 'valid_response'
        elif status is None:
            outcome = 'no_response'
        else:
            outcome = 'invalid_response'
        decisions[outcome] += 1
    return {'cases': len(rows), 'outcomes': dict(sorted(decisions.items()))}


def _llvm_metric(metric):
    count, covered, percent = metric['count'], metric['covered'], metric['percent']
    if (type(count) is not int or type(covered) is not int or not 0 <= covered <= count
            or type(percent) not in (int, float) or not 0 <= percent <= 100):
        raise EvidenceError('invalid LLVM coverage count')
    if ('notcovered' in metric and
            (type(metric['notcovered']) is not int or metric['notcovered'] != count - covered)):
        raise EvidenceError('inconsistent uncovered count')
    if count and not isclose(percent, 100 * covered / count, rel_tol=0, abs_tol=0.01):
        raise EvidenceError('coverage percentage disagrees with counts')
    return count, covered


def llvm_coverage(raw):
    doc = strict_json(raw)
    if doc['type'] != 'llvm.coverage.json.export' or doc['version'] != '2.0.1' or len(doc['data']) != 1:
        raise EvidenceError('unsupported LLVM coverage summary')
    data, = doc['data']
    files = data['files']
    if not isinstance(files, list) or not 0 < len(files) <= 4096:
        raise EvidenceError('invalid coverage file inventory')
    names = [row['filename'] for row in files]
    if any(type(name) is not str or not name for name in names) or len(set(names)) != len(names):
        raise EvidenceError('invalid or repeated coverage source name')
    totals = {}
    for kind in METRICS:
        counts = [_llvm_metric(row['summary'][kind]) for row in files]
        count, covered = _llvm_metric(data['totals'][kind])
        if (count, covered) != (sum(pair[0] for pair in counts), sum(pair[1] for pair in counts)):
            raise EvidenceError('LLVM coverage file and aggregate counts disagree')
        totals[kind] = {'count': count, 'covered': covered}
    return {'files': len(files), 'totals': totals}


RESOURCE_COLUMNS = {
    'EngineRusageAvgCores_Max': 'engine_rusage_avg_millicores',
    'EngineRusageCpuPct_Max': 'engine_rusage_cpu_percent',
    'EngineRusageRssMb_Max': 'engine_rusage_rss_mb',
    'EngineRusageVSizeMb_Max': 'engine_rusage_vsize_mb',
}


def _csv_snapshots(block):
    # Decode only adjacent CSV literals in the expected-output initializer.
    rows, parts = [], []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith('"'):
            if line not in ('', '{', '},', '};') and not line.startswith('//'):
                raise EvidenceError('unexpected CSV fixture initializer')
            continue
        match = re.fullmatch(r'"([A-Za-z0-9_,.]*)"(,?)\s*(?://.*)?', line)
        if not match:
            raise EvidenceError('unexpected CSV fixture field encoding')
        parts.append(match[1])
        if match[2]:
            rows.append(''.join(parts))
            parts = []
    if parts or len(rows) != 4 or rows.pop() != '':
        raise EvidenceError('unexpected CSV snapshot count')
    columns = rows.pop(0).split(',')
    if columns.pop() != '' or len(set(columns)) != len(columns) or not RESOURCE_COLUMNS.keys() <= set(columns):
        raise EvidenceError('ambiguous resource column or missing maximum')
    snapshots = []
    for row in rows:
        fields = row.split(',')
        if fields.pop() != '' or len(fields) != len(columns):
            raise EvidenceError('resource CSV width differs from its header')
        record = dict(zip(columns, fields))
        snapshot = {}
        for key in RESOURCE_COLUMNS:
            if not re.fullmatch('[0-9]{1,12}', record[key]):
                raise EvidenceError('invalid resource maximum')
            snapshot[key] = int(record[key])
        snapshots.append(snapshot)
    return snapshots


def resource_peaks(raw):
    source = raw.decode('ascii')
    start, end = 'TEST(Stats, DumpStatsToCsvFile) {', 'TEST(Stats, DumpStatsToExistingCsvFile)'
    if source.count(start) != 1 or source.count(end) != 1:
        raise EvidenceError('resource fixture declaration differs')
    fixture = source.split(start)[1].split(end)[0]
    groups = re.findall(r'/\*experiment_name=\*/"(Experiment[AB])"', fixture)
    if groups != ['ExperimentA', 'ExperimentB', 'ExperimentA', 'ExperimentB']:
        raise EvidenceError('unexpected resource fixture shard membership')
    if ('const uint64_t j = i + 1;' not in fixture or
            'for (int i = 2; i < stats_vec.size(); ++i)' not in fixture):
        raise EvidenceError('unexpected resource fixture shard update order')
    expected = {}
    for key, field in RESOURCE_COLUMNS.items():
        matches = re.findall(r'/\*' + field + r'=\*/\s*(\d+) \* j,', fixture)
        if len(matches) != 1 or fixture.count('new_stats.' + field + ' += 1;') != 1:
            raise EvidenceError('resource maximum lacks an independent shard initializer')
        expected[key] = int(matches[0])
    if fixture.count('kExpectedCsvLines = {') != 1:
        raise EvidenceError('resource CSV table declaration differs')
    table = fixture.split('kExpectedCsvLines = {', 1)[1].split('\n  };', 1)[0]
    blocks = re.split(r'// CSV #[12]\.', table)
    if len(blocks) != 3:
        raise EvidenceError('missing resource CSV cohort')
    maxima = Counter()
    for group, block in zip(sorted(set(groups)), blocks[1:]):
        snapshots = _csv_snapshots(block)
        for step, snapshot in enumerate(snapshots):
            for key, value in snapshot.items():
                peak = max(unit * expected[key] + (step if unit > 2 else 0)
                           for unit, label in enumerate(groups, 1) if label == group)
                if value != peak:
                    raise EvidenceError('reported maximum differs from underlying resource samples')
                maxima[key] = max(maxima[key], value)
    return {'cohorts': 2, 'shards': len(groups), 'snapshots': 4,
            'fixture_peak_by_counter': {RESOURCE_COLUMNS[k]: v for k, v in maxima.items()}}


def trace_window(raw):
    # Read the view's counters only. Operands and thread identifiers never enter the output.
    if len(raw) > 65536:
        raise EvidenceError('oversized trace window')
    lines = raw.splitlines()
    marker = b'View tool results:'
    if lines.count(marker) != 1:
        raise EvidenceError('missing or duplicate trace footer')
    footer = lines.index(marker)
    totals = [int(m[1]) for line in lines[footer + 1:]
              if (m := re.fullmatch(rb'\s*([0-9]+)\s*: total instructions', line))]
    records = {}
    ordinals = []
    for line in lines[:footer]:
        match = re.match(rb'\s*([0-9]+)\s+([0-9]+):\s+(W[0-9]+\.T[0-9]+)\s+ifetch\s+', line)
        if match:
            record, instruction = int(match[1]), int(match[2])
            key = (match[3], record)
            if key in records or (ordinals and instruction != ordinals[-1] + 1):
                raise EvidenceError('duplicate or discontinuous instruction in trace window')
            records[key] = (instruction, sha(line[match.end():].strip()))
            ordinals.append(instruction)
    if not records or totals != [len(records)]:
        raise EvidenceError('trace window and footer counts disagree')
    return ordinals[0], records


def reconcile_trace_windows(files):
    cmake = files[WINDOW_SOURCE].decode('utf-8')
    anchor = 'set(zip_path\n        "${PROJECT_SOURCE_DIR}/clients/drcachesim/tests/drmemtrace.allasm_x86_64.trace.zip")'
    blocks = [block for block in cmake.split(anchor)[1:]
              if block.lstrip().startswith('torunonly_api(tool.drcacheoff.skip ')]
    if len(blocks) != 1:
        raise EvidenceError('trace window source declaration differs')
    fragment = blocks[0].split('set(tool.drcacheoff.skip2_rawtemp', 1)[0]
    if 'set(zip_path' in fragment:
        raise EvidenceError('trace input changed between windows')
    windows = []
    for name, path in zip(('skip', 'skip2'), WINDOWS):
        match = re.search(r'torunonly_api\(tool\.drcacheoff\.' + name +
                          r' "\$\{drcachesim_path\}" "offline-' + name +
                          r'" ""[^)]*?-infile;\$\{zip_path\};\$\{test_mode_flag\};-skip_instrs;([0-9]+);', fragment)
        first, records = trace_window(files[path])
        if match is None or first != int(match[1]) + 1:
            raise EvidenceError('trace window differs from its declared input and offset')
        windows.append(records)
    left, right = windows
    shared = left.keys() & right.keys()
    if not shared or any(left[key] != right[key] for key in shared):
        raise EvidenceError('overlapping trace records disagree')
    return {'window_instructions': [len(left), len(right)], 'shared_instructions': len(shared),
            'distinct_instructions': len(left.keys() | right.keys())}


def pinned_files(root, project):
    directory, revision, manifest = PROJECTS[project]
    repo = root / directory
    if repo.is_symlink() or git(repo, 'rev-parse', 'HEAD').decode().strip() != revision:
        raise EvidenceError('coverage fixture producer revision differs')
    result = {}
    for path, oid in manifest.items():
        expected = f'100644 blob {oid}\t{path}\n'.encode()
        if git(repo, 'ls-tree', revision, '--', path) != expected:
            raise EvidenceError('coverage fixture path or mode differs')
        raw = git(repo, 'cat-file', 'blob', oid)
        if git_object('blob', raw) != oid:
            raise EvidenceError('coverage fixture bytes differ')
        result[path] = raw
    return result


def review(root):
    reports = {}
    for name, (_, revision, manifest) in PROJECTS.items():
        files = pinned_files(root, name)
        if name == FUZZTEST:
            operation = 'check_exported_resource_maxima_against_unit_test_shards'
            result = resource_peaks(files[RESOURCE_TEST])
        elif name == DYNAMORIO:
            operation = 'reconcile_overlapping_instruction_count_exports'
            result = reconcile_trace_windows(files)
        elif name == ZAP:
            operation = 'reconcile_grouped_and_individual_report_totals'
            result = reconcile_alerts(files[ZAP_MERGED], files[ZAP_FLAT])
        elif name == RESTLER:
            operation = 'distinguish_unanswered_and_invalid_coverage_cases'
            result = specification_coverage(files[SPEC_COVERAGE])
        else:
            operation = 'reconcile_file_and_total_source_coverage'
            result = llvm_coverage(files[LLVM_SUMMARY])
        reports[name] = {'revision': revision, 'role': 'reference', 'operation': operation,
                         'source_manifest_sha256': sha(canonical(manifest)), 'source_blobs': manifest,
                         'result': result}
    return reports
