"""Render localized links to the archived NQC coverage comparison using pinned report messages."""
import argparse
from html import escape
import json
from pathlib import Path
import re
from string import Formatter
import sys

from .product_infra_batch import capture
from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .product_sources import git
from .safe_io import canonical, read_artifact, strict_json


SUBJECT = 'OWASP/Nettacker'
REVISION = '6e04aa1f9cf29b35cae5ba1bb5043fd7b9b651b5'
DIRECTORY = '094-nettacker'
LOCALES = ('ar', 'bn', 'de', 'el', 'en', 'es', 'fa', 'fr', 'hi', 'hy', 'id', 'it',
           'iw', 'ja', 'ko', 'nl', 'ps', 'pt-br', 'ru', 'tr', 'ur', 'uz', 'vi', 'zh-cn')
SOURCES = {SUBJECT: (DIRECTORY, REVISION, tuple(f'nettacker/locale/{code}.yaml' for code in LOCALES))}
REPORT_FILE = 'pr119-140-vs-157.json'
REPORT_PATH = 'superhunter/product_supply/acceptance-120/' + REPORT_FILE
REPORT_SHA = '47f431bc49d63da05838eb75f4695b9e45aafca812b41ef93726cda15735d9fc'
MESSAGE = 'compare_report_saved'


def message(raw):
    # Only this root-level key is consumed. The pinned catalogs use single-line
    # plain or double-quoted values for it. Do not interpret the rest of the YAML.
    values = [line.partition(':')[2].strip() for line in raw.splitlines()
              if line.startswith(MESSAGE + ':')]
    if not values:
        return None
    if len(values) != 1:
        raise EvidenceError('duplicate localized comparison message')
    value, = values
    if value.startswith('"'):
        value = json.loads(value)
    elif not value or value[0] in "|>'&*!#[]%@`":
        raise EvidenceError('unsupported scalar in the pinned report catalogs')
    if not isinstance(value, str) or not value or any(ord(char) < 32 for char in value):
        raise EvidenceError('invalid comparison message')
    return value


def split_path(template):
    """Return the literal text around exactly one unmodified filename field."""
    if template is None:
        return None, 'missing_message'
    try:
        parts = list(Formatter().parse(template))
    except ValueError:
        return None, 'invalid_path_field'
    fields = [(field, spec, conv) for _, field, spec, conv in parts if field is not None]
    if not fields:
        return None, 'missing_path'
    if fields != [('0', '', None)]:
        return None, 'invalid_path_field'
    before, after = [], []
    side = before
    for text, field, _, _ in parts:
        side.append(text)
        if field is not None:
            side = after
    return (''.join(before), ''.join(after)), None


def language(code):
    return {'iw': 'he', 'pt-br': 'pt-BR', 'zh-cn': 'zh-CN'}.get(code, code)


def markdown_text(text):
    return re.sub(r'([\\`*_{}\[\]()#!|~])', r'\\\1', escape(text, quote=False))


def render(templates, report, *, markdown=False):
    if set(templates) != set(LOCALES):
        raise EvidenceError('incomplete set of localized catalog observations')
    fallback, error = split_path(templates['en'])
    if error:
        raise EvidenceError('English fallback must preserve the report filename')
    counts = {'parallel': report['pr119_verified_content']['session'],
              'consolidated': report['consolidated']['independently_counted']['session'],
              'shared': report['overlap']['common_identities']}
    heading = 'Comparación de cobertura de SUPERHUNTER'
    coverage = (f"PR 119 · {counts['parallel']} identidades. PR 120 · {counts['consolidated']} identidades. "
                f"Coinciden {counts['shared']} en las revisiones de este informe.")
    explanation = 'Los enlaces abren el mismo informe JSON. Cada etiqueta indica el idioma del mensaje.'
    lines = ['<!doctype html>', '<html lang="es"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; base-uri \'none\'">',
             f'<title>{heading}</title></head><body><main><h1>{heading}</h1>',
             f'<p>{coverage}</p>', f'<p>{explanation}</p>', '<ul>']
    if markdown:
        lines = [f'# {heading}', '', coverage, '', explanation, '']
    statuses = {}
    for code in LOCALES:
        fragments, reason = split_path(templates[code])
        requested = language(code)
        actual = 'en' if reason else requested
        direction = 'rtl' if actual in {'ar', 'he', 'fa', 'ps', 'ur'} else 'ltr'
        before, after = fallback if reason else fragments
        note = ' · mensaje en inglés' if reason else ''
        filename = f'<bdi dir="ltr">{REPORT_FILE}</bdi>'
        if markdown:
            label = markdown_text(before) + filename + markdown_text(after)
            lines.append(f'- **{requested}**{note} · <span lang="{actual}" dir="{direction}">'
                         f'[{label}]({REPORT_FILE})</span>')
        else:
            lines.append(f'<li><code>{requested}</code>{note} · '
                         f'<a href="{REPORT_FILE}" lang="{actual}" dir="{direction}">{escape(before)}'
                         f'{filename}{escape(after)}</a></li>')
        statuses[code] = {'requested_language': requested, 'text_language': actual,
                          'direction': direction, 'fallback_reason': reason}
    if not markdown:
        lines.append('</ul></main></body></html>')
    else:
        lines.extend(['', 'Los mensajes proceden de OWASP/Nettacker. NQC comprueba que cada traducción '
                      'conserva el nombre del archivo y la adapta a un enlace al informe publicado. '
                      f'[Catálogos en la revisión de origen](https://github.com/OWASP/Nettacker/tree/{REVISION}/nettacker/locale) · '
                      '[Licencia de los mensajes](nettacker-report-messages-license.txt)'])
    return ('\n'.join(lines) + '\n').encode(), counts, statuses


def prepare(root, *, markdown=False):
    if git(root / DIRECTORY, 'rev-parse', 'HEAD').decode().strip() != REVISION:
        raise EvidenceError('report translation checkout differs from reviewed commit')
    files, manifest = capture(root, SUBJECT, SOURCES)
    report = read_artifact(ROOT, REPORT_PATH)
    if sha(report) != REPORT_SHA:
        raise EvidenceError('published NQC comparison report differs')
    templates = {code: message(files[f'nettacker/locale/{code}.yaml']) for code in LOCALES}
    comparison = strict_json(report)
    html, counts, statuses = render(templates, comparison)
    output = render(templates, comparison, markdown=True)[0] if markdown else html
    return output, {SUBJECT: {'revision': REVISION, 'role': 'reference',
                             'operation': 'localize_access_to_archived_comparison',
                             'source_manifest_sha256': sha(canonical(manifest)), 'report_path': REPORT_PATH,
                             'report_sha256': REPORT_SHA, 'result': {
                                 'comparison': counts, 'links': len(statuses),
                                 'index_sha256': sha(html), 'locales': statuses}}}


def review(root):
    return prepare(root)[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True,
                        help='directory containing the pinned direct checkouts, including 094-nettacker')
    parser.add_argument('--format', choices=('html', 'markdown'), default='html',
                        help='HTML for local viewing or Markdown for a sibling file in GitHub')
    args = parser.parse_args()
    document, _ = prepare(args.source_root, markdown=args.format == 'markdown')
    sys.stdout.buffer.write(document)


if __name__ == '__main__':
    main()
