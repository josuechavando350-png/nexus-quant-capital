"""Verified, minimized derivatives of private SUPERHUNTER review bundles.

No original artifacts are exported, no remote system is contacted, and no
publication occurs. Redaction is bounded pattern matching, not a secrecy proof.
A self-consistent derivative does not authenticate its source or producer.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
from html import escape

from . import quality, review
from .privacy import PrivateArgumentParser, POLICY_ID, redact_record
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

POLICY = 'superhunter-minimized-review-v2'
MAX_TOTAL_BYTES = 32_000_000
OUTPUT_FILES = frozenset({'summary.json', 'SUMMARY.md', 'index.html', 'export.json'})
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
RULES = frozenset({'secret-field', 'recovery-phrase', 'authorization', 'bearer-token',
                  'session-cookie', 'url-userinfo', 'jwt-shaped', 'private-key-block',
                  'sensitive-record-field'})
SUMMARY_KEYS = frozenset({'schema_version', 'status', 'review_id', 'source_digest', 'unit_tests',
                         'synthetic_cases', 'integration', 'capabilities', 'vulnerability_confirmed',
                         'production_certified', 'producer_authenticated', 'manual_review_required'})
META_KEYS = frozenset({'schema_version', 'policy', 'policy_code_sha256', 'source_manifest_sha256',
                      'redaction', 'original_evidence_included', 'manual_review_required',
                      'producer_authenticated'})


def _need(condition: bool) -> None:
    if not condition:
        # Never echo paths, unexpected field names or input values.
        raise ValueError('invalid review export structure or consistency')


def _object(value, keys) -> None:
    _need(type(value) is dict and set(value) == set(keys))


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _integer(value, minimum=0) -> None:
    _need(type(value) is int and minimum <= value <= 10_000_000)


def _text(value) -> None:
    _need(type(value) is str and bool(value.strip()) and len(value.encode('utf-8')) <= 4_096)
    _need(not any(ord(c) < 32 and c not in '\n\r\t' for c in value))


def _capture(root: Path, expected: frozenset[str]) -> dict[str, bytes]:
    """Capture a closed set of bounded regular files with its ORIGINAL manifest."""
    _need(not root.is_symlink() and root.is_dir())
    _need({p.name for p in root.iterdir()} == expected | {'COMPLETE.json'})
    marker_raw = read_artifact(root, 'COMPLETE.json')
    marker = strict_json(marker_raw)
    _object(marker, {'schema_version', 'sha256'})
    _need(type(marker['schema_version']) is int and marker['schema_version'] == 1)
    _object(marker['sha256'], expected)
    captured = {'COMPLETE.json': marker_raw}
    total = len(marker_raw)
    for name in sorted(expected):
        wanted = marker['sha256'][name]
        _need(type(wanted) is str and HEX64.fullmatch(wanted) is not None)
        raw = read_artifact(root, name)
        total += len(raw)
        _need(total <= MAX_TOTAL_BYTES and _sha(raw) == wanted)
        captured[name] = raw
    _need(read_artifact(root, 'COMPLETE.json') == marker_raw)
    return captured


def _verify_captured(captured: dict[str, bytes]) -> dict:
    """Run existing QA/lab/fuzz/graph verifiers on exactly the captured bytes."""
    with tempfile.TemporaryDirectory(prefix='superhunter-share-source-') as tmp:
        root = Path(tmp)
        for name, raw in captured.items():
            fd = os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
        return review.verify_review(root)


def _policy_code() -> str:
    root = Path(__file__).resolve().parent
    return _sha(canonical({name: _sha(read_artifact(root, name))
                           for name in ('sharing.py', 'privacy.py')}))


def _validate_summary(summary: dict) -> None:
    _object(summary, SUMMARY_KEYS)
    _need(type(summary['schema_version']) is int and summary['schema_version'] == 1)
    _need(summary['status'] == 'REDACTED_REVIEW_DRAFT')
    _need(type(summary['review_id']) is str and str(uuid.UUID(summary['review_id'])) == summary['review_id'])
    _need(type(summary['source_digest']) is str and HEX64.fullmatch(summary['source_digest']) is not None)
    _integer(summary['unit_tests'], 1)
    _object(summary['synthetic_cases'], {'fixed', 'fuzz'})
    _need(type(summary['synthetic_cases']['fixed']) is int and summary['synthetic_cases']['fixed'] == 5)
    _need(type(summary['synthetic_cases']['fuzz']) is int and 1 <= summary['synthetic_cases']['fuzz'] <= 256)
    for key in ('vulnerability_confirmed', 'production_certified', 'producer_authenticated'):
        _need(summary[key] is False)
    _need(summary['manual_review_required'] is True)
    plan = summary['integration']
    _object(plan, {'bounded', 'partial', 'pending', 'items'})
    _integer(plan['bounded']); _integer(plan['partial']); _integer(plan['pending'])
    _need(type(plan['items']) is list and len(plan['items']) == 27)
    for i, item in enumerate(plan['items'], 1):
        _object(item, {'id', 'group', 'title', 'status', 'boundary'})
        _need(item['id'] == f'B{i:02d}' and type(item['group']) is int and 1 <= item['group'] <= 5)
        _need(item['status'] in ('BOUNDED_IMPLEMENTED', 'PARTIAL', 'PENDING'))
        _text(item['title']); _text(item['boundary'])
    _need(plan['bounded'] == sum(i['status'] == 'BOUNDED_IMPLEMENTED' for i in plan['items']))
    _need(plan['partial'] == sum(i['status'] == 'PARTIAL' for i in plan['items']))
    _need(plan['pending'] == sum(i['status'] == 'PENDING' for i in plan['items']))
    _need(plan['bounded'] + plan['partial'] + plan['pending'] == 27)
    caps = summary['capabilities']
    _object(caps, {'complete', 'counts', 'items'})
    _need(type(caps['complete']) is int and caps['complete'] == 0)
    statuses = {'PARTIAL', 'PLANNED', 'REDESIGN_REQUIRED'}
    _object(caps['counts'], statuses)
    _need(type(caps['items']) is list and len(caps['items']) == 50)
    for i, item in enumerate(caps['items'], 1):
        _object(item, {'id', 'title', 'status', 'scope'})
        _need(type(item['id']) is int and item['id'] == i and item['status'] in statuses)
        _text(item['title']); _text(item['scope'])
    for status in statuses:
        _integer(caps['counts'][status])
        _need(caps['counts'][status] == sum(i['status'] == status for i in caps['items']))
    clean, _ = redact_record(summary)
    _need(canonical(clean) == canonical(summary))


def _validate_metadata(metadata: dict) -> None:
    _object(metadata, META_KEYS)
    _need(type(metadata['schema_version']) is int and metadata['schema_version'] == 1)
    _need(metadata['policy'] == POLICY and metadata['policy_code_sha256'] == _policy_code())
    _need(type(metadata['source_manifest_sha256']) is str and HEX64.fullmatch(metadata['source_manifest_sha256']) is not None)
    _need(metadata['original_evidence_included'] is False and metadata['manual_review_required'] is True
          and metadata['producer_authenticated'] is False)
    redaction = metadata['redaction']
    _object(redaction, {'policy', 'matches_by_rule', 'redactions_present', 'manual_review_required', 'all_secrets_detected'})
    _need(redaction['policy'] == POLICY_ID and redaction['manual_review_required'] is True
          and redaction['all_secrets_detected'] is False)
    counts = redaction['matches_by_rule']
    _need(type(counts) is dict and set(counts) <= RULES)
    for count in counts.values():
        _integer(count, 1)
    _need(redaction['redactions_present'] is bool(counts))


def _md(text: str) -> str:
    """Inert display text: no raw HTML/images, control sequences or extra headings."""
    text = escape(text, quote=False).replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
    return re.sub(r'([\\`*_{}\[\]()#!|])', r'\\\1', text)


def render_summary(summary: dict) -> str:
    _validate_summary(summary)
    lines = ['# SUPERHUNTER — resumen para revisión', '',
             '**DERIVADO FILTRADO. Requiere revisión humana antes de compartir.**', '',
             'No incluye evidencias originales, logs de ejecución ni pruebas de concepto. '
             'No autentica al productor ni confirma vulnerabilidades.', '',
             f"Pruebas locales del paquete: {summary['unit_tests']}. "
             f"Casos sintéticos: {summary['synthetic_cases']['fixed']} fijos, {summary['synthetic_cases']['fuzz']} generados.",
             f"Identidad de código: `{summary['source_digest']}`.", '',
             '## 27 hitos de integración', '',
             '✓ Alcance limitado implementado · ◐ Parcial · ○ Pendiente. No representa porcentaje de plataforma.', '']
    for item in summary['integration']['items']:
        mark = {'BOUNDED_IMPLEMENTED': '✓', 'PARTIAL': '◐', 'PENDING': '○'}[item['status']]
        lines += [f"{mark} **{item['id']}. {_md(item['title'])}** — {_md(item['boundary'])}", '']
    lines += ['## 50 capacidades', '', 'Ninguna capacidad completa está certificada.', '']
    for item in summary['capabilities']['items']:
        mark = {'PARTIAL': '◐', 'PLANNED': '○', 'REDESIGN_REQUIRED': '↻'}[item['status']]
        lines += [f"{mark} **{item['id']}. {_md(item['title'])}** — {_md(item['scope'])}", '']
    lines += ['## Limitaciones', '',
              'La redacción aplica reglas finitas. Los secretos sin etiquetas, ofuscados o desconocidos '
              'pueden no detectarse. La verificación del derivado sin la carpeta fuente solo comprueba '
              'consistencia interna, no ejecución real ni autenticidad.', '']
    return '\n'.join(lines)


def _project(captured: dict[str, bytes], facts: dict) -> dict[str, bytes]:
    plan = strict_json(captured['milestones.json'])
    caps = strict_json(captured['capabilities.json'])
    summary = {
        'schema_version': 1, 'status': 'REDACTED_REVIEW_DRAFT',
        'review_id': facts['review_id'], 'source_digest': facts['source_digest'],
        'unit_tests': facts['unit_tests'], 'synthetic_cases': facts['synthetic_cases'],
        'integration': {**facts['milestones'], 'items': [
            {k: item[k] for k in ('id', 'group', 'title', 'status', 'boundary')} for item in plan['items']]},
        'capabilities': {'complete': 0, 'counts': facts['capabilities'], 'items': [
            {k: item[k] for k in ('id', 'title', 'status', 'scope')} for item in caps['items']]},
        'vulnerability_confirmed': False, 'production_certified': False,
        'producer_authenticated': False, 'manual_review_required': True,
    }
    summary, redaction = redact_record(summary)
    _validate_summary(summary)
    metadata = {'schema_version': 1, 'policy': POLICY, 'policy_code_sha256': _policy_code(),
                'source_manifest_sha256': _sha(captured['COMPLETE.json']), 'redaction': redaction,
                'original_evidence_included': False, 'manual_review_required': True,
                'producer_authenticated': False}
    _validate_metadata(metadata)
    markdown = render_summary(summary)
    return {'summary.json': canonical(summary), 'SUMMARY.md': markdown.encode(),
            'index.html': review.render_html(markdown), 'export.json': canonical(metadata)}


def _load_verified_source(source: Path) -> tuple[dict[str, bytes], dict]:
    before = quality.source_snapshot()
    captured = _capture(source, review.ALL_FILES)
    facts = _verify_captured(captured)
    _need(_capture(source, review.ALL_FILES) == captured)
    _need(quality.source_snapshot() == before)
    return captured, facts


def create_shared(source: Path, out: Path) -> dict:
    """Reverify source in a private snapshot, then export only allowlisted facts."""
    if out.exists() or out.is_symlink():
        raise FileExistsError('new output directory required')
    _need(not out.resolve().is_relative_to(quality.ROOT.parent))
    _need(not out.resolve().is_relative_to(source.resolve()) and
          not source.resolve().is_relative_to(out.resolve()))
    before = quality.source_snapshot()
    captured, facts = _load_verified_source(source)
    projected = _project(captured, facts)
    _need(quality.source_snapshot() == before)
    _need(_capture(source, review.ALL_FILES) == captured)
    write_new_bundle(out, projected)
    result = verify_shared(out)
    return {**result, 'status': 'SHARED_REVIEW_CREATED', 'source_reverified': True}


def verify_shared(root: Path, source: Path | None = None) -> dict:
    """With no private source, validate only consistency of the derivative."""
    captured = _capture(root, OUTPUT_FILES)
    summary = strict_json(captured['summary.json'])
    metadata = strict_json(captured['export.json'])
    _validate_summary(summary); _validate_metadata(metadata)
    markdown = render_summary(summary)
    _need(captured['summary.json'] == canonical(summary) and captured['export.json'] == canonical(metadata))
    _need(captured['SUMMARY.md'] == markdown.encode() and captured['index.html'] == review.render_html(markdown))
    if source is not None:
        original, facts = _load_verified_source(source)
        expected = _project(original, facts)
        _need(all(captured[name] == expected[name] for name in OUTPUT_FILES))
    return {'status': 'SHARED_REVIEW_SOURCE_MATCH' if source is not None else 'SHARED_REVIEW_CONSISTENT',
            'source_reverified': source is not None, 'manual_review_required': True,
            'original_evidence_included': False, 'vulnerability_confirmed': False,
            'producer_authenticated': False, 'production_certified': False}


def main(argv: list[str]) -> int:
    parser = PrivateArgumentParser(description='Export minimized local-review facts, never publish them')
    sub = parser.add_subparsers(dest='command', required=True)
    make = sub.add_parser('share-review')
    make.add_argument('--review', type=Path, required=True)
    make.add_argument('--out', type=Path, required=True)
    verify = sub.add_parser('verify-shared')
    verify.add_argument('--bundle', type=Path, required=True)
    verify.add_argument('--review', type=Path)
    args = parser.parse_args(argv)
    try:
        result = (create_shared(args.review, args.out) if args.command == 'share-review'
                  else verify_shared(args.bundle, args.review))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, RecursionError, AttributeError):
        print(json.dumps({'status': 'SHARED_REVIEW_ERROR', 'error_code': 'INVALID_EXPORT_OR_SOURCE'}))
        return 2
