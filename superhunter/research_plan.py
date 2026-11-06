"""Traceable 25-initiative registry from the supplied PDFs; not 25 fake engines."""
from __future__ import annotations

import re
from pathlib import Path
from .safe_io import read_artifact, strict_json

ROOT = Path(__file__).resolve().parent
REFERENCES = ('OCTANE', 'OLYMPIX', 'CERTORA', 'IMMUNEFI', 'TRAIL_OF_BITS')
CODES = ('R1', 'R2', 'R3', 'D1', 'D2')
EXPECTED = [group + '.' + code for group in REFERENCES for code in CODES]


def load_plan(*, root: Path = ROOT, components: dict | None = None,
              passing_tests: set[str] | None = None) -> dict:
    data = strict_json(read_artifact(root, 'research_initiatives.json'))
    if set(data) != {'schema_version', 'sources', 'decision', 'items'} or type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ValueError('INITIATIVE_SCHEMA')
    if data['decision'] != 'LOCAL_MODULAR_DEVELOPMENT_ONLY':
        raise ValueError('INITIATIVE_DECISION')
    sources = data['sources']
    if type(sources) is not list or len(sources) != 2:
        raise ValueError('DOCUMENT_PROVENANCE')
    for source, filename in zip(sources, ('SUPERHUNTER_01_Investigacion.pdf', 'SUPERHUNTER_02_Verificacion.pdf')):
        if (type(source) is not dict or set(source) != {'filename', 'sha256', 'pages'} or
                source['filename'] != filename or type(source['pages']) is not int or source['pages'] != 3 or
                type(source['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', source['sha256'])):
            raise ValueError('DOCUMENT_PROVENANCE')
    items = data['items']
    if type(items) is not list or len(items) != 25:
        raise ValueError('ALL_25_INITIATIVES_REQUIRED')
    for item, identifier in zip(items, EXPECTED):
        if type(item) is not dict or set(item) != {'id', 'reference', 'code', 'title', 'source_page', 'status', 'scope', 'related_capabilities', 'components', 'required_tests'}:
            raise ValueError('INITIATIVE_FIELDS')
        if item['id'] != identifier or item['reference'] + '.' + item['code'] != identifier:
            raise ValueError('INITIATIVE_IDENTITY')
        page = 1 if item['reference'] in REFERENCES[:2] else 2
        if type(item['source_page']) is not int or item['source_page'] != page:
            raise ValueError('INITIATIVE_SOURCE_PAGE')
        if item['status'] not in ('PLANNED', 'PARTIAL'):
            raise ValueError('UNPROVEN_INITIATIVE_COMPLETION')
        if any(type(item[k]) is not str or not item[k].strip() for k in ('title', 'scope')):
            raise ValueError('INITIATIVE_TEXT')
        links = item['related_capabilities']
        if (type(links) is not list or not links or any(type(x) is not int or not 1 <= x <= 50 for x in links) or len(set(links)) != len(links)):
            raise ValueError('CAPABILITY_LINKS')
        refs, tests = item['components'], item['required_tests']
        if (type(refs) is not list or type(tests) is not list or
                any(type(x) is not str or not re.fullmatch(r'[a-z_]+', x) for x in refs) or
                any(type(x) is not str or not re.fullmatch(r'test_[A-Za-z0-9_.]+', x) for x in tests) or
                len(set(refs)) != len(refs) or len(set(tests)) != len(tests) or
                (item['status'] == 'PARTIAL') != bool(refs) or bool(refs) != bool(tests)):
            raise ValueError('INITIATIVE_EVIDENCE')
        if components is not None and any(ref not in components for ref in refs):
            raise ValueError('INITIATIVE_COMPONENT_MISSING')
        if passing_tests is not None and any(test not in passing_tests for test in tests):
            raise ValueError('INITIATIVE_TEST_NOT_PASSED')
    return data


def render_plan(data: dict) -> str:
    lines = ['# SUPERHUNTER — las 25 iniciativas de los dos resúmenes', '',
             'Registro de requisitos, no implementación de 25 motores. Se conserva además el plan de 27+50.',
             'Los requisitos se solapan: no sumar las listas para calcular un porcentaje de terminación.', '']
    for source in data['sources']:
        lines += [f"Documento: {source['filename']} · SHA-256 `{source['sha256']}`."]
    lines += ['']
    for item in data['items']:
        mark = '◐' if item['status'] == 'PARTIAL' else '○'
        lines += [f"{mark} **{item['id']} — {item['title']}**", item['scope'],
                  f"Fuente: Informe 01, página {item['source_page']}; requisitos previos: " +
                  ', '.join(map(str, item['related_capabilities'])) + '.', '']
    lines += ['No hay copia de implementaciones propietarias. Las integraciones de herramientas externas requieren revisión de versiones y licencias antes de distribuirse.', '']
    return '\n'.join(lines)
