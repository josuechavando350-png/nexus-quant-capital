"""Source-bound review of existing Slither JSON; no analyzer or target execution.

Consumes the documented detector output, validates byte ranges against explicit
source snapshots, and keeps tool claims separate from independently proven facts.
Raw inputs stay in a PRIVATE bundle; rendered views are redacted, not public-safe.
"""
from __future__ import annotations

from collections import Counter
from bisect import bisect_right
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from dataclasses import asdict

from .native_runtime import load_components
from .privacy import PrivateArgumentParser, redact_text
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

MAX_SOURCES = 64
MAX_TOTAL_SOURCE_BYTES = 8_000_000
MAX_ALERTS = 1000
MAX_ELEMENTS = 128
MAX_TOTAL_ELEMENTS = 4096
MAX_MAPPED_BYTES = 32_000_000
HASH = re.compile(r'[0-9a-f]{64}\Z')
COMMIT = re.compile(r'[0-9a-f]{40}\Z')
CHECK = re.compile(r'[a-z][a-z0-9-]{0,95}\Z')
IMPACTS = ('High', 'Medium', 'Low', 'Informational', 'Optimization')
CONFIDENCES = ('High', 'Medium', 'Low')
BASE_FILES = {'context.json', 'slither.json', 'normalized.json', 'REVIEW.md', 'audit.json'}
ROOT = Path(__file__).resolve().parent


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise ValueError(code)


def _text(value, *, empty=False, maximum=65536) -> str:
    _require(type(value) is str and len(value.encode('utf-8')) <= maximum,
             'INVALID_TEXT')
    _require(empty or bool(value.strip()), 'EMPTY_TEXT')
    return value


def _path(value) -> str:
    value = _text(value, maximum=512)
    path = PurePosixPath(value)
    _require(not path.is_absolute() and ':' not in value and '\\' not in value and
             all(part not in ('', '.', '..') for part in value.split('/')) and
             not any(ord(c) < 32 or ord(c) == 127 for c in value) and
             path.suffix in ('.sol', '.vy'), 'UNSAFE_SOURCE_PATH')
    return value


def validate_context(context: dict) -> dict:
    _require(type(context) is dict and set(context) == {
        'schema_version', 'scope_id', 'repository', 'tool', 'detectors',
        'report_sha256', 'sources', 'input_kind'}, 'CONTEXT_FIELDS')
    _require(type(context['schema_version']) is int and context['schema_version'] == 1,
             'CONTEXT_VERSION')
    _text(context['scope_id'], maximum=200)
    repo = context['repository']
    _require(type(repo) is dict and set(repo) == {'repo', 'commit'}, 'REPOSITORY_FIELDS')
    _require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', _text(repo['repo'])) is not None,
             'REPOSITORY_NAME')
    _require(COMMIT.fullmatch(_text(repo['commit'])) is not None, 'COMMIT_FORMAT')
    tool = context['tool']
    _require(type(tool) is dict and set(tool) == {'name', 'version'} and
             tool['name'] == 'slither', 'TOOL_FIELDS')
    _text(tool['version'], maximum=100)
    _require(context['input_kind'] in ('synthetic-format-fixture', 'external-report'), 'INPUT_KIND')
    detectors = context['detectors']
    _require(type(detectors) is list and 1 <= len(detectors) <= MAX_ALERTS and
             all(type(d) is str and CHECK.fullmatch(d) for d in detectors) and
             len(set(detectors)) == len(detectors), 'DECLARED_DETECTORS')
    _require(HASH.fullmatch(_text(context['report_sha256'])) is not None, 'REPORT_HASH')
    sources = context['sources']
    _require(type(sources) is dict and 1 <= len(sources) <= MAX_SOURCES, 'SOURCE_INVENTORY')
    for name, digest in sources.items():
        _path(name)
        _require(type(digest) is str and HASH.fullmatch(digest) is not None, 'SOURCE_HASH')
    return context


def _verify_sources(context: dict, sources: dict[str, bytes]) -> None:
    _require(type(sources) is dict and set(sources) == set(context['sources']), 'SOURCE_SET_MISMATCH')
    total = 0
    for name, expected in context['sources'].items():
        raw = sources[name]
        _require(type(raw) is bytes and 0 < len(raw) <= 2_000_000, 'SOURCE_SIZE')
        total += len(raw)
        _require(total <= MAX_TOTAL_SOURCE_BYTES, 'TOTAL_SOURCE_LIMIT')
        _require(_sha(raw) == expected, 'SOURCE_CONTENT_MISMATCH')
        raw.decode('utf-8', errors='strict')


def _location(element: dict, sources: dict[str, bytes], metadata: dict) -> dict | None:
    _require(type(element) is dict, 'ELEMENT_OBJECT')
    mapping = element.get('source_mapping')
    if mapping is None or mapping == {}:
        return None
    _require(type(mapping) is dict, 'LOCATION_OBJECT')
    # No fallback to absolute/short paths and no lookup outside the allowlist.
    name = _path(mapping.get('filename_relative'))
    _require(name in sources, 'LOCATION_OUTSIDE_SOURCE_INVENTORY')
    raw = sources[name]
    start, length = mapping.get('start'), mapping.get('length')
    _require(type(start) is int and type(length) is int and start >= 0 and
             length > 0 and start + length <= len(raw), 'LOCATION_BYTE_RANGE')
    _require(not 0x80 <= raw[start] <= 0xBF, 'LOCATION_UTF8_BOUNDARY')
    fragment = raw[start:start + length]
    fragment.decode('utf-8', errors='strict')
    first = bisect_right(metadata[name]['line_starts'], start) + 1
    # Slither maps the exclusive end offset as well, so an endpoint after a LF
    # may name the next line. Byte positions, not Python string indices.
    last = bisect_right(metadata[name]['line_starts'], start + length) + 1
    lines = mapping.get('lines')
    _require(type(lines) is list and all(type(x) is int for x in lines) and
             lines == list(range(first, last + 1)), 'LOCATION_LINES_MISMATCH')
    kind = _text(element.get('type'), maximum=80)
    label = _text(element.get('name'), empty=True, maximum=8192)
    return {'file': name, 'start_byte': start, 'length_bytes': length,
            'lines': lines, 'source_sha256': metadata[name]['sha256'], 'fragment_sha256': _sha(fragment),
            'element_type': kind, 'name_sha256': _sha(label.encode())}


def normalize(report_raw: bytes, context: dict, sources: dict[str, bytes]) -> dict:
    """Review a supported documented output shape. It never validates an exploit."""
    validate_context(context)
    _verify_sources(context, sources)
    _require(type(report_raw) is bytes and _sha(report_raw) == context['report_sha256'],
             'REPORT_CONTENT_MISMATCH')
    report = strict_json(report_raw)
    _require(set(report) == {'success', 'error', 'results'} and
             type(report['success']) is bool and type(report['results']) is dict,
             'SLITHER_ENVELOPE')
    base = {'schema_version': 1, 'adapter_sha256': _sha(Path(__file__).read_bytes()),
            'context_sha256': _sha(canonical(context)), 'report_sha256': _sha(report_raw),
            'repository_declared': context['repository'], 'scope_id_declared': context['scope_id'],
            'tool_declared': context['tool'], 'detectors_declared': sorted(context['detectors']),
            'input_kind': context['input_kind'], 'source_sha256': dict(sorted(context['sources'].items())),
            'scanner_execution_verified': False, 'producer_authenticated': False,
            'repository_commit_verified': False, 'scope_authorization_verified': False,
            'vulnerability_confirmed': False, 'code_certified_safe': False,
            'ignored_result_sections': sorted(set(report['results']) - {'detectors'})}
    if report['success'] is False:
        _require(report['error'] is None or type(report['error']) is str, 'TOOL_ERROR_FORMAT')
        partial = report['results'].get('detectors')
        partial_count = len(partial) if type(partial) is list else None
        return {**base, 'status': 'TOOL_ERROR', 'alerts': [], 'raw_alert_count': partial_count,
                'unique_alert_count': 0, 'duplicate_count': 0, 'source_bound_alerts': 0,
                'unbound_alerts': 0, 'tool_impact_counts': {}, 'normalization_complete': False}
    _require(report['error'] is None, 'CONTRADICTORY_TOOL_ERROR')
    detectors = report['results'].get('detectors')
    _require(type(detectors) is list and len(detectors) <= MAX_ALERTS, 'DETECTOR_RESULTS_REQUIRED')
    metadata = {name: {'sha256': context['sources'][name],
                       'line_starts': [m.end() for m in re.finditer(b'\n', raw)]}
                for name, raw in sources.items()}
    groups = {}
    element_count, mapped_bytes = 0, 0
    for index, row in enumerate(detectors):
        _require(type(row) is dict and {'check', 'impact', 'confidence', 'description', 'elements'} <= set(row),
                 'DETECTOR_FIELDS')
        check = _text(row['check'], maximum=96)
        _require(check in context['detectors'], 'UNDECLARED_DETECTOR')
        _require(row['impact'] in IMPACTS and row['confidence'] in CONFIDENCES, 'TOOL_CLASSIFICATION')
        description = _text(row['description'])
        elements = row['elements']
        _require(type(elements) is list and len(elements) <= MAX_ELEMENTS, 'ELEMENT_LIMIT')
        locations = []
        missing = 0
        for element in elements:
            element_count += 1
            _require(element_count <= MAX_TOTAL_ELEMENTS, 'TOTAL_ELEMENT_LIMIT')
            if type(element) is dict and type(element.get('source_mapping')) is dict:
                length = element['source_mapping'].get('length')
                if type(length) is int and length > 0:
                    mapped_bytes += length
                    _require(mapped_bytes <= MAX_MAPPED_BYTES, 'MAPPED_BYTE_BUDGET')
            loc = _location(element, sources, metadata)
            if loc is None:
                missing += 1
            else:
                locations.append(loc)
        # Remove repeated location witnesses; order is not part of the identity.
        locations = [json.loads(k) for k in sorted({canonical(v).decode() for v in locations})]
        bound = bool(locations) and missing == 0
        # Unbound alerts require textual identity too; never silently conflate two
        # unknown locations. Bound alerts retain ALL distinct tool descriptions.
        identity = {'repository': context['repository'], 'scope': context['scope_id'],
                    'check': check, 'locations': locations, 'missing': missing,
                    'unbound_description_sha256': _sha(description.encode()) if not bound else None}
        fingerprint = _sha(canonical(identity))
        record = {'fingerprint': fingerprint, 'check': check, 'tool_impact': row['impact'],
                  'tool_confidence': row['confidence'], 'source_bound': bound,
                  'missing_location_count': missing if elements else 1, 'locations': locations,
                  'status': 'STATIC_ALERT_UNVERIFIED', 'vulnerability_confirmed': False,
                  'root_cause_independently_verified': False, 'descriptions_redacted': [],
                  'description_sha256': [], 'detector_indices': [], 'occurrences': 0}
        old = groups.setdefault(fingerprint, record)
        _require((old['tool_impact'], old['tool_confidence']) == (row['impact'], row['confidence']),
                 'CONTRADICTORY_DUPLICATE_CLASSIFICATION')
        filtered = redact_text(description).text
        old['descriptions_redacted'] = sorted(set(old['descriptions_redacted'] + [filtered]))
        old['description_sha256'] = sorted(set(old['description_sha256'] + [_sha(description.encode())]))
        old['detector_indices'].append(index)
        old['occurrences'] += 1
    alerts = [groups[k] for k in sorted(groups)]
    unbound = sum(not row['source_bound'] for row in alerts)
    status = ('INCOMPLETE_SOURCE_BINDING' if unbound else
              'STATIC_REVIEW_REQUIRED' if alerts else 'NO_ALERTS_IN_SUPPLIED_REPORT')
    return {**base, 'status': status, 'alerts': alerts,
            'raw_alert_count': len(detectors), 'unique_alert_count': len(alerts),
            'duplicate_count': len(detectors) - len(alerts),
            'source_bound_alerts': len(alerts) - unbound, 'unbound_alerts': unbound,
            'tool_impact_counts': dict(sorted(Counter(a['tool_impact'] for a in alerts).items())),
            'normalization_complete': not unbound}


def render_report(result: dict) -> bytes:
    lines = ['# SUPERHUNTER — alertas estáticas importadas', '',
             f"Estado: {result['status']}",
             f"Alertas recibidas: {result['raw_alert_count']}; únicas: {result['unique_alert_count']}; "
             f"duplicadas: {result['duplicate_count']}.", '',
             'Las severidades son afirmaciones de Slither. No hay PoC, confirmación de vulnerabilidad, '
             'verificación de permisos del programa ni autenticación del productor.',
             'Cero alertas no demuestra que el código sea seguro. Este paquete contiene fuentes y resultados '
             'originales privados; no debe publicarse.', '']
    for alert in result['alerts']:
        lines += [f"## {alert['check']} · impacto declarado: {alert['tool_impact']}",
                  f"Identidad: `{alert['fingerprint']}` · fuentes vinculadas: {alert['source_bound']}"]
        for loc in alert['locations']:
            lines += [f"{loc['file']} · bytes {loc['start_byte']}:{loc['start_byte'] + loc['length_bytes']} "
                      f"· líneas {loc['lines'][0]}–{loc['lines'][-1]}"]
        lines += alert['descriptions_redacted'] + ['']
    return redact_text('\n'.join(lines)).text.encode()


def _source_artifact(digest: str) -> str:
    return 'source-' + digest + '.txt'


def _audit_events(context: dict, result: dict) -> list[tuple[str, dict]]:
    return [('static.import', {'context_sha256': _sha(canonical(context)), 'report_sha256': result['report_sha256']})] + [
        ('static.source', {'file_sha256': _sha(name.encode()), 'content_sha256': digest})
        for name, digest in sorted(context['sources'].items())] + [
        ('static.normalized', {'result_sha256': _sha(canonical(result)), 'status': result['status']})]


def import_report(report_path: Path, context_path: Path, source_root: Path, out: Path) -> dict:
    _require(not out.exists() and not out.is_symlink(), 'OUTPUT_EXISTS')
    _require(not out.resolve().is_relative_to(ROOT.parent), 'OUTPUT_INSIDE_CHECKOUT')
    context_raw = read_artifact(context_path.parent, context_path.name)
    context = validate_context(strict_json(context_raw))
    report_raw = read_artifact(report_path.parent, report_path.name)
    sources = {name: read_artifact(source_root, name) for name in context['sources']}
    result = normalize(report_raw, context, sources)
    native = load_components()
    log = native.audit.AuditLog()
    for event, data in _audit_events(context, result):
        log.append(event, data)
    log.assert_intact()
    files = {'context.json': context_raw, 'slither.json': report_raw,
             'normalized.json': canonical(result), 'REVIEW.md': render_report(result),
             'audit.json': canonical({'entries': [asdict(e) for e in log.entries]})}
    for name, digest in context['sources'].items():
        files[_source_artifact(digest)] = sources[name]
    write_new_bundle(out, files)
    return verify_report(out)


def verify_report(root: Path) -> dict:
    marker = strict_json(read_artifact(root, 'COMPLETE.json'))
    _require(set(marker) == {'schema_version', 'sha256'} and
             type(marker['schema_version']) is int and marker['schema_version'] == 1 and
             type(marker['sha256']) is dict, 'BUNDLE_MANIFEST')
    context_raw = read_artifact(root, 'context.json')
    context = validate_context(strict_json(context_raw))
    expected_files = BASE_FILES | {_source_artifact(d) for d in context['sources'].values()}
    _require(set(marker['sha256']) == expected_files, 'BUNDLE_FILE_SET')
    _require({p.name for p in root.iterdir()} == expected_files | {'COMPLETE.json'}, 'UNDECLARED_BUNDLE_FILE')
    files = {name: read_artifact(root, name) for name in expected_files}
    _require(all(type(d) is str and HASH.fullmatch(d) and _sha(files[n]) == d
                 for n, d in marker['sha256'].items()), 'BUNDLE_HASH_MISMATCH')
    _require(files['context.json'] == context_raw, 'CONTEXT_CHANGED_DURING_VERIFICATION')
    sources = {name: files[_source_artifact(d)] for name, d in context['sources'].items()}
    result = normalize(files['slither.json'], context, sources)
    _require(files['normalized.json'] == canonical(result), 'NORMALIZED_RESULT_MISMATCH')
    _require(files['REVIEW.md'] == render_report(result), 'RENDERED_REPORT_MISMATCH')
    events = _audit_events(context, result)
    audit = strict_json(files['audit.json'])
    _require(set(audit) == {'entries'} and type(audit['entries']) is list and
             len(audit['entries']) == len(events), 'AUDIT_COVERAGE')
    native = load_components()
    previous, timestamp = '0' * 64, None
    for index, (row, (event, data)) in enumerate(zip(audit['entries'], events)):
        _require(type(row) is dict and set(row) == {'index', 'timestamp', 'event', 'data', 'prev_hash', 'hash'},
                 'AUDIT_FIELDS')
        _require(type(row['index']) is int and row['index'] == index and row['event'] == event and
                 canonical(row['data']) == canonical(data) and row['prev_hash'] == previous, 'AUDIT_BINDING')
        current = datetime.fromisoformat(_text(row['timestamp']))
        _require(current.tzinfo is not None and (timestamp is None or current >= timestamp), 'AUDIT_TIME')
        entry = native.audit.AuditEntry(**row)
        _require(entry.recompute() == row['hash'], 'AUDIT_HASH')
        previous, timestamp = row['hash'], current
    return result


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Review Slither output and source snapshots; no analyzer execution')
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('import-slither')
    for name in ('report', 'context', 'sources', 'out'):
        create.add_argument('--' + name, required=True, type=Path)
    sub.add_parser('verify-slither').add_argument('--bundle', required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = (import_report(args.report, args.context, args.sources, args.out)
                  if args.command == 'import-slither' else verify_report(args.bundle))
        print(json.dumps({k: result[k] for k in ('status', 'raw_alert_count', 'unique_alert_count',
                                                'source_bound_alerts', 'vulnerability_confirmed')}))
        return 0 if result['normalization_complete'] else 1
    except (ValueError, OSError, KeyError, TypeError, RecursionError) as exc:
        print(json.dumps({'status': 'STATIC_IMPORT_ERROR', 'error_type': type(exc).__name__,
                          'vulnerability_confirmed': False}))
        return 2
