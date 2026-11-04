"""Offline Slither diagnostic intake, bound to explicitly supplied source bytes.

Consumes existing JSON; never runs Slither, a compiler, an exploit, RPC or a
remote target. Consistent output is not proof of execution or exploitability.
See STATIC_INTAKE.md for the strict, deliberately limited input profile.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .safe_io import MAX_BYTES, canonical, read_artifact, strict_json, write_new_bundle

MAX_FILES = 64
MAX_TOTAL_BYTES = 8_000_000
MAX_DIAGNOSTICS = 1000
MAX_ELEMENTS = 100
HEX64 = re.compile(r'[a-f0-9]{64}\Z')
REPO = re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z')
SHA40 = re.compile(r'[a-f0-9]{40}\Z')
CHECK = re.compile(r'[a-z][a-z0-9-]{0,95}\Z')
IMPACTS = {'High', 'Medium', 'Low', 'Informational', 'Optimization'}
CONFIDENCES = {'High', 'Medium', 'Low'}
BUNDLE_FIXED = {'manifest.json', 'slither.json', 'observations.json', 'REVIEW.md'}


class IntakeError(ValueError):
    """Invalid or unsupported evidence. Messages never include input values."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise IntakeError(code)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def text(value: Any, *, limit: int = 4096) -> str:
    require(type(value) is str and 0 < len(value.encode('utf-8')) <= limit, 'INVALID_TEXT')
    require(not any(ord(ch) < 32 and ch not in '\n\r\t' for ch in value), 'CONTROL_CHARACTER')
    return value


def source_path(value: Any) -> str:
    value = text(value, limit=512)
    path = PurePosixPath(value)
    require(not path.is_absolute() and '\\' not in value and ':' not in value and
            all(p not in ('', '.', '..') for p in value.split('/')) and
            path.suffix == '.sol' and all(ord(ch) >= 32 for ch in value), 'UNSAFE_SOURCE_PATH')
    return value


def validate_manifest(value: Any) -> dict:
    require(type(value) is dict and set(value) == {
        'schema_version', 'target', 'tool', 'sources', 'scope_id'}, 'MANIFEST_SCHEMA')
    require(type(value['schema_version']) is int and value['schema_version'] == 1, 'MANIFEST_VERSION')
    text(value['scope_id'], limit=128)
    target = value['target']
    require(type(target) is dict and set(target) == {'repo', 'commit'}, 'TARGET_SCHEMA')
    require(REPO.fullmatch(text(target['repo'], limit=256)) is not None, 'TARGET_REPO')
    require(SHA40.fullmatch(text(target['commit'], limit=40)) is not None, 'TARGET_COMMIT')
    tool = value['tool']
    require(type(tool) is dict and set(tool) == {'name', 'version', 'report_sha256', 'detectors'}, 'TOOL_SCHEMA')
    require(tool['name'] == 'slither', 'UNSUPPORTED_TOOL')
    text(tool['version'], limit=64)
    require(HEX64.fullmatch(text(tool['report_sha256'], limit=64)) is not None, 'REPORT_HASH_FORMAT')
    detectors = tool['detectors']
    require(type(detectors) is list and 1 <= len(detectors) <= 256 and
            all(type(x) is str and CHECK.fullmatch(x) for x in detectors) and
            len(set(detectors)) == len(detectors), 'DETECTOR_INVENTORY')
    sources = value['sources']
    require(type(sources) is list and 1 <= len(sources) <= MAX_FILES, 'SOURCE_INVENTORY')
    seen = set()
    for row in sources:
        require(type(row) is dict and set(row) == {'path', 'sha256'}, 'SOURCE_SCHEMA')
        path = source_path(row['path'])
        require(path not in seen, 'DUPLICATE_SOURCE')
        seen.add(path)
        require(HEX64.fullmatch(text(row['sha256'], limit=64)) is not None, 'SOURCE_HASH_FORMAT')
    return deepcopy(value)


def validate_sources(manifest: dict, sources: dict[str, bytes]) -> None:
    require(type(sources) is dict and set(sources) == {r['path'] for r in manifest['sources']}, 'SOURCE_SET_MISMATCH')
    require(all(type(raw) is bytes and len(raw) <= MAX_BYTES for raw in sources.values()), 'SOURCE_SIZE_LIMIT')
    require(sum(map(len, sources.values())) <= MAX_TOTAL_BYTES, 'TOTAL_SOURCE_SIZE_LIMIT')
    for row in manifest['sources']:
        raw = sources[row['path']]
        require(digest(raw) == row['sha256'], 'SOURCE_HASH_MISMATCH')
        try:
            raw.decode('utf-8', errors='strict')
        except UnicodeError as exc:
            raise IntakeError('SOURCE_NOT_UTF8') from exc


def _location(element: Any, sources: dict[str, bytes]) -> dict:
    require(type(element) is dict, 'ELEMENT_SCHEMA')
    kind = text(element.get('type'), limit=64)
    name = element.get('name')
    require(type(name) is str and len(name.encode('utf-8')) <= 4096, 'ELEMENT_NAME')
    mapping = element.get('source_mapping')
    require(type(mapping) is dict, 'MISSING_SOURCE_MAPPING')
    path = source_path(mapping.get('filename_relative'))
    require(path in sources, 'UNDECLARED_SOURCE')
    start, length = mapping.get('start'), mapping.get('length')
    require(type(start) is int and type(length) is int and start >= 0 and length > 0,
            'SOURCE_RANGE_TYPE')
    raw = sources[path]
    end = start + length
    require(end <= len(raw), 'SOURCE_RANGE_BOUNDS')
    # Solidity/Slither offsets are BYTES, not Python Unicode character indices.
    try:
        raw[:start].decode('utf-8', errors='strict')
        raw[start:end].decode('utf-8', errors='strict')
    except UnicodeError as exc:
        raise IntakeError('SOURCE_RANGE_UTF8_BOUNDARY') from exc
    first = raw.count(b'\n', 0, start) + 1
    # Slither's _compute_line maps the exclusive end offset too.
    last = raw.count(b'\n', 0, end) + 1
    actual_lines = list(range(first, last + 1))
    lines = mapping.get('lines')
    require(type(lines) is list and all(type(n) is int for n in lines) and lines == actual_lines,
            'SOURCE_LINES_MISMATCH')
    return {'type': kind, 'name': name, 'file': path, 'source_sha256': digest(raw),
            'start_byte': start, 'length_bytes': length, 'lines': actual_lines,
            'span_sha256': digest(raw[start:end])}


def normalize(manifest: Any, report_raw: bytes, sources: dict[str, bytes]) -> dict:
    """Normalize all diagnostics without converting them into confirmed Findings.

    Rule+locations group repeated observations, but every raw record is retained
    by index and digest. Conflicting labels are explicit, never averaged away.
    """
    manifest = validate_manifest(manifest)
    validate_sources(manifest, sources)
    require(type(report_raw) is bytes and len(report_raw) <= MAX_BYTES, 'REPORT_SIZE_LIMIT')
    require(digest(report_raw) == manifest['tool']['report_sha256'], 'REPORT_HASH_MISMATCH')
    report = strict_json(report_raw)
    require(set(report) == {'success', 'error', 'results'} and type(report['success']) is bool,
            'SLITHER_ENVELOPE')
    require(type(report['results']) is dict, 'SLITHER_RESULTS')
    require((report['success'] is True and report['error'] is None) or
            (report['success'] is False and type(report['error']) is str), 'SLITHER_ERROR_CONTRADICTION')
    groups: dict[str, dict] = {}
    supplied = report['results'].get('detectors')
    if not report['success']:
        require(supplied is None or supplied == [], 'FAILED_RUN_WITH_RESULTS')
        state, records = 'STATIC_TOOL_ERROR', []
    elif supplied is None:
        # Slither may omit this key for zero results OR excluded detector output.
        # Those alternatives cannot be distinguished from JSON alone.
        state, records = 'STATIC_COVERAGE_UNKNOWN', []
    else:
        require(type(supplied) is list and len(supplied) <= MAX_DIAGNOSTICS, 'DETECTOR_RESULTS_LIMIT')
        state, records = ('STATIC_REVIEW_REQUIRED' if supplied else 'STATIC_NO_DIAGNOSTICS'), supplied
    for index, item in enumerate(records):
        require(type(item) is dict, 'DIAGNOSTIC_SCHEMA')
        check = text(item.get('check'), limit=96)
        require(CHECK.fullmatch(check) is not None and check in manifest['tool']['detectors'], 'UNDECLARED_DETECTOR')
        impact, confidence = item.get('impact'), item.get('confidence')
        require(type(impact) is str and impact in IMPACTS, 'UNSUPPORTED_IMPACT')
        require(type(confidence) is str and confidence in CONFIDENCES, 'UNSUPPORTED_CONFIDENCE')
        description = text(item.get('description'), limit=64_000)
        elements = item.get('elements')
        require(type(elements) is list and 1 <= len(elements) <= MAX_ELEMENTS, 'ELEMENTS_REQUIRED')
        locations = [_location(e, sources) for e in elements]
        locations = sorted({canonical(loc): loc for loc in locations}.values(), key=canonical)
        key = {'target': manifest['target'], 'scope_id': manifest['scope_id'],
               'check': check, 'locations': locations}
        identifier = digest(canonical(key))
        group = groups.setdefault(identifier, {
            'observation_id': identifier, 'check': check, 'locations': locations, 'records': [],
            'status': 'UNVERIFIED_STATIC_OBSERVATION'})
        group['records'].append({'input_index': index, 'raw_record_sha256': digest(canonical(item)),
                                 'tool_impact': impact, 'tool_confidence': confidence,
                                 'description': description})
    observations = []
    for identifier in sorted(groups):
        group = groups[identifier]
        group['conflicting_labels'] = len({(r['tool_impact'], r['tool_confidence']) for r in group['records']}) > 1
        group['record_count'] = len(group['records'])
        observations.append(group)
    result = {
        'schema_version': 1, 'profile': 'slither-json-bound-source-v1', 'status': state,
        'manifest_sha256': digest(canonical(manifest)), 'report_sha256': digest(report_raw),
        'target': manifest['target'], 'scope_id': manifest['scope_id'],
        'tool_version_claimed': manifest['tool']['version'],
        'source_count': len(sources), 'source_bytes': sum(map(len, sources.values())),
        'diagnostics_received': len(records), 'observation_groups': len(observations),
        'grouping_is_bounty_duplicate_check': False,
        'impact_counts_as_reported': dict(sorted(Counter(r['impact'] for r in records).items())),
        'observations': observations, 'tool_executed_here': False, 'execution_authenticated': False,
        'scope_authorization_verified': False, 'target_commit_authenticated': False,
        'vulnerability_confirmed': False, 'absence_of_vulnerabilities_proven': False,
        'human_review_required': True,
    }
    require(len(canonical(result)) <= MAX_BYTES, 'NORMALIZED_OUTPUT_LIMIT')
    return result


def render_review(result: dict) -> bytes:
    # Do not echo input descriptions, names, paths, repo strings, keys or URLs.
    # Full input and observations remain PRIVATE artifacts in the evidence bundle.
    lines = ['# Revisión de diagnósticos estáticos', '',
             f"Estado: {result['status']}",
             f"Registros recibidos: {result['diagnostics_received']}",
             f"Grupos por regla y ubicación: {result['observation_groups']}",
             f"Archivos de fuente vinculados: {result['source_count']}", '',
             'No se ejecutó Slither en este módulo. No se confirma explotabilidad,',
             'autorización del programa, correspondencia con un commit remoto ni ausencia de bugs.',
             'El paquete contiene fuentes y mensajes originales privados. No publicarlo.', '']
    for group in result['observations']:
        lines.append('Observación ' + group['observation_id'] +
                     f" — {group['record_count']} registros; etiquetas contradictorias: " +
                     ('sí' if group['conflicting_labels'] else 'no'))
    return ('\n'.join(lines) + '\n').encode('utf-8')


def capture_sources(manifest: dict, root: Path) -> dict[str, bytes]:
    captured, total = {}, 0
    for row in manifest['sources']:
        raw = read_artifact(root, row['path'])
        total += len(raw)
        require(total <= MAX_TOTAL_BYTES, 'TOTAL_SOURCE_SIZE_LIMIT')
        captured[row['path']] = raw
    validate_sources(manifest, captured)
    return captured


def source_filename(index: int) -> str:
    return f'source-{index:03d}.sol'


def create_intake(manifest_file: Path, report_file: Path, source_root: Path, out: Path) -> dict:
    require(not out.exists() and not out.is_symlink(), 'OUTPUT_EXISTS')
    require(not out.resolve().is_relative_to(Path(__file__).resolve().parent.parent), 'OUTPUT_INSIDE_CODE')
    require(not out.resolve().is_relative_to(source_root.resolve()), 'OUTPUT_INSIDE_SOURCES')
    manifest_raw = read_artifact(manifest_file.parent, manifest_file.name)
    manifest = validate_manifest(strict_json(manifest_raw))
    report_raw = read_artifact(report_file.parent, report_file.name)
    sources = capture_sources(manifest, source_root)
    result = normalize(manifest, report_raw, sources)
    files = {'manifest.json': manifest_raw, 'slither.json': report_raw,
             'observations.json': canonical(result), 'REVIEW.md': render_review(result)}
    for index, row in enumerate(manifest['sources']):
        files[source_filename(index)] = sources[row['path']]
    write_new_bundle(out, files)
    return verify_intake(out)


def verify_intake(root: Path) -> dict:
    marker = strict_json(read_artifact(root, 'COMPLETE.json'))
    require(set(marker) == {'schema_version', 'sha256'} and type(marker['schema_version']) is int
            and marker['schema_version'] == 1 and type(marker['sha256']) is dict, 'BUNDLE_SCHEMA')
    manifest_raw = read_artifact(root, 'manifest.json')
    manifest = validate_manifest(strict_json(manifest_raw))
    expected = BUNDLE_FIXED | {source_filename(i) for i in range(len(manifest['sources']))}
    require(set(marker['sha256']) == expected, 'BUNDLE_FILE_SET')
    require({p.name for p in root.iterdir()} == expected | {'COMPLETE.json'}, 'UNDECLARED_BUNDLE_FILE')
    data = {}
    total = 0
    for name in sorted(expected):
        raw = read_artifact(root, name)
        total += len(raw)
        require(total <= MAX_TOTAL_BYTES + 4*MAX_BYTES, 'BUNDLE_TOTAL_LIMIT')
        require(digest(raw) == marker['sha256'][name], 'BUNDLE_HASH_MISMATCH')
        data[name] = raw
    require(data['manifest.json'] == manifest_raw, 'MANIFEST_CHANGED')
    sources = {row['path']: data[source_filename(i)] for i, row in enumerate(manifest['sources'])}
    result = normalize(manifest, data['slither.json'], sources)
    require(data['observations.json'] == canonical(result), 'OBSERVATIONS_DIFFER_FROM_INPUT')
    require(data['REVIEW.md'] == render_review(result), 'REVIEW_DIFFER_FROM_INPUT')
    return result


class _PrivateParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.exit(2, 'Invalid arguments. Use --help; input values are not echoed.\n')


def main(argv: list[str] | None = None) -> int:
    parser = _PrivateParser(description='Bind existing Slither diagnostics to supplied source bytes; no execution')
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('import-static')
    for name in ('manifest', 'report', 'sources', 'out'):
        create.add_argument('--'+name, type=Path, required=True)
    sub.add_parser('verify-static').add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = (create_intake(args.manifest, args.report, args.sources, args.out)
                  if args.command == 'import-static' else verify_intake(args.bundle))
        print(json.dumps({k: result[k] for k in ('status', 'diagnostics_received', 'observation_groups',
                                                 'tool_executed_here', 'vulnerability_confirmed')}))
        return 1 if result['status'] in ('STATIC_TOOL_ERROR', 'STATIC_COVERAGE_UNKNOWN') else 0
    except (ValueError, OSError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        print(json.dumps({'status': 'STATIC_INTAKE_REJECTED', 'error_type': type(exc).__name__,
                          'vulnerability_confirmed': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
