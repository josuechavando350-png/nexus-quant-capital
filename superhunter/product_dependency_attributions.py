"""Reconcile the pinned Go requirements with the corresponding published third-party notices."""
import ast
from collections import Counter
import csv
from io import StringIO
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .product_reasoning import EvidenceError
from .product_report_quality_sources import pinned_blobs
from .product_review import copy_release, sha
from .product_state_formats_batch import GO_SHA
from .safe_io import canonical, strict_json

REPOSITORY = 'DataDog/stratus-red-team'
REVISION = 'dea75a460718e632e90d98093f982b64f9e60c02'
MOD = 'v2/go.mod'
NOTICES = 'LICENSE-3rdparty.csv'
PINS = {MOD: ('100644', '32dba0e79dce3924cb2e50598b48d2aa6b5e332d'),
        NOTICES: ('100644', '82608defafea154da3a7264736bc81bb7e8e7b55')}
COLUMNS = ['component', 'origin', 'license', 'copyright']
IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9.-]*\+?')
MODULE = re.compile(r'[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~+-]+)*')


def license_field(text):
    """Recognize the CSV's syntax for a list of labels, without interpreting legal rights."""
    if not text.strip():
        return 'missing_license', []
    if len(text) > 2048:
        return 'malformed_license', []
    try:
        items = ast.literal_eval(text)
    except (ValueError, SyntaxError, RecursionError):
        return 'malformed_license', []
    if type(items) is not list or len(items) > 32:
        return 'malformed_license', []
    if not items:
        return 'missing_license', []
    if any(type(item) is not str or not IDENTIFIER.fullmatch(item) for item in items):
        return 'malformed_license', []
    return 'has_labels', items


def notices(raw):
    if len(raw) > 500_000:
        raise EvidenceError('oversized attribution CSV')
    reader = csv.reader(StringIO(raw.decode('utf-8'), newline=''), strict=True)
    if next(reader, None) != COLUMNS:
        raise EvidenceError('unexpected attribution columns')
    rows = {}
    try:
        for values in reader:
            if not values:  # Empty physical lines carry no CSV record.
                continue
            if len(values) != len(COLUMNS):
                raise EvidenceError('malformed attribution row')
            name, origin, text, _ = values
            if not MODULE.fullmatch(name) or name in rows or not origin.strip():
                raise EvidenceError('missing or duplicate attribution identity or origin')
            rows[name] = license_field(text)
    except csv.Error as exc:
        raise EvidenceError('malformed attribution CSV') from exc
    if not rows:
        raise EvidenceError('empty attribution CSV')
    return rows


def declared(mod_json):
    if any(mod_json.get(key) for key in ('Replace', 'Exclude', 'Retract', 'Tool')):
        raise EvidenceError('unsupported module directives for this attribution comparison')
    module = mod_json['Module']['Path']
    requirements = {}
    for row in mod_json['Require']:
        name, version = row['Path'], row['Version']
        indirect = row.get('Indirect', False)
        if (not MODULE.fullmatch(name) or not re.fullmatch(r'v[0-9][A-Za-z0-9.+-]*', version)
                or name in requirements or type(indirect) is not bool):
            raise EvidenceError('invalid or duplicate declared dependency')
        requirements[name] = ('indirect' if indirect else 'direct', version)
    if not requirements or not MODULE.fullmatch(module) or module in requirements:
        raise EvidenceError('invalid module identity or requirement membership')
    return module, requirements


def parse_mod(raw, go):
    # Only a copy of go.mod is inspected. No other upstream file enters the process.
    with tempfile.TemporaryDirectory(prefix='nqc-attribution-mod-') as tmp:
        work = Path(tmp)
        go = go.resolve(strict=True)
        copy_release('Go module manifest reader', go, work/'go', GO_SHA)
        manifest = work/'go.mod'
        manifest.write_bytes(raw)
        env = {'HOME': tmp, 'PATH': '', 'GOENV': 'off', 'GOWORK': 'off', 'GOTOOLCHAIN': 'local',
               'GOPROXY': 'off', 'GOSUMDB': 'off', 'GOTELEMETRY': 'off', 'GOROOT': str(go.parent.parent),
               'GOMODCACHE': str(work/'module-cache')}
        result = subprocess.run([work/'go', 'mod', 'edit', '-json', manifest], cwd=work, env=env,
                                stdin=subprocess.DEVNULL, capture_output=True, timeout=20)
        if result.returncode or manifest.read_bytes() != raw:
            raise EvidenceError('pinned Go reader failed or modified the manifest')
        return declared(strict_json(result.stdout))


def reconcile(module, requirements, rows):
    counts = {group: Counter() for group in ('direct', 'indirect')}
    missing = {group: [] for group in counts}
    for name, (group, version) in sorted(requirements.items()):
        totals = counts[group]
        totals['declared'] += 1
        if name not in rows:
            totals['absent_from_csv'] += 1
            missing[group].append({'module': name, 'version': version})
            continue
        status, _ = rows[name]
        totals['exact_csv_row'] += 1
        totals[status] += 1
    issues = {}
    for name, (status, _) in sorted(rows.items()):
        if status == 'has_labels':
            continue
        if name == module:
            bucket = 'main_module'
        else:
            bucket = requirements[name][0] if name in requirements else 'outside_requirements'
        issues[name] = {'issue': status, 'membership': bucket}

    def group_summary(group):
        return {key: counts[group][key] for key in
                ('declared', 'exact_csv_row', 'absent_from_csv', 'has_labels', 'missing_license', 'malformed_license')}

    return {'main_module': module, 'attribution_rows': len(rows),
            'requirement_counts': {k: group_summary(k) for k in counts},
            'absent_from_csv': missing, 'license_field_issues': issues,
            'csv_only_outside_requirements': sorted(rows.keys() - requirements.keys()),
            'scope': 'Exact case-sensitive module paths in v2/go.mod and root CSV. Go indirect tags are declarations. '
                     'CSV labels have no module versions. Dependency resolution, license-text validation and commercial '
                     'approval remain outside this comparison.'}


def review(root):
    files = pinned_blobs(root/'081-stratus-red-team', REVISION, PINS)
    tool = os.environ.get('NQC_STATE_GO') or shutil.which('go')
    if not tool:
        raise EvidenceError('pinned Go manifest reader unavailable')
    module, requirements = parse_mod(files[MOD], Path(tool))
    result = reconcile(module, requirements, notices(files[NOTICES]))
    return {REPOSITORY: {'revision': REVISION, 'role': 'reference',
                         'operation': 'reconcile_declared_go_dependencies_with_published_attribution_rows',
                         'source_manifest_sha256': sha(canonical(PINS)), 'source_blobs': {k: v[1] for k, v in PINS.items()},
                         'go_reader_sha256': GO_SHA, 'result': result}}
