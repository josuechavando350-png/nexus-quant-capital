"""Self-contained review of existing local evidence, never an exploit runner.

Verifiers recompute QA, native-lab and numerical-fuzz evidence from captured
bytes. A consistent package is not an authenticated remote execution or a bug.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import tempfile
import uuid

from . import quality, local_lab, fuzz_lab
from .research_plan import load_plan, render_plan
from .privacy import PrivateArgumentParser, redact_text
from .project_context import verify_projection, test_inventory
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
SECTION_FILES = {
    'qa': frozenset(quality.FILES | {'COMPLETE.json'}),
    'lab': frozenset(local_lab.BUNDLE_FILES | {'COMPLETE.json'}),
    'fuzz': frozenset(fuzz_lab.ARTIFACT_FILES | {'COMPLETE.json'}),
}
PACKED_FILES = frozenset(f'{group}--{name}' for group, names in SECTION_FILES.items() for name in names)
REPORT_FILES = frozenset({'review.json', 'REVIEW.md', 'index.html', 'milestones.json', 'capabilities.json'})
ALL_FILES = PACKED_FILES | REPORT_FILES


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def milestones() -> dict:
    data = strict_json(read_artifact(ROOT, 'integration_milestones.json'))
    if type(data.get('schema_version')) is not int or data['schema_version'] != 1:
        raise ValueError('invalid milestone schema')
    items = data.get('items')
    if (type(items) is not list or len(items) != 27 or any(type(i) is not dict for i in items) or
            [i.get('id') for i in items] != [f'B{i:02d}' for i in range(1,28)]):
        raise ValueError('all 27 original milestones must be preserved in order')
    for i in items:
        if set(i) != {'id','group','title','status','boundary','tests'}:
            raise ValueError('milestone fields mismatch')
        if type(i['group']) is not int or not 1 <= i['group'] <= 5:
            raise ValueError('milestone group invalid')
        if i['status'] not in ('BOUNDED_IMPLEMENTED','PARTIAL','PENDING'):
            raise ValueError('unearned milestone certification')
        if any(type(i[k]) is not str or not i[k].strip() for k in ('title','boundary')):
            raise ValueError('milestone text missing')
        tests = i['tests']
        if (type(tests) is not list or any(type(t) is not str or not t.startswith('test_') for t in tests) or
                len(set(tests)) != len(tests) or (i['status']!='PENDING') != bool(tests)):
            raise ValueError('milestone evidence references invalid')
    verify_projection(strict_json(read_artifact(ROOT, 'integration-checklist.json')), data)
    return data


def _verify_sections(packed: dict[str, bytes]) -> dict:
    """Reconstitute precisely the captured artifacts, preserving their markers."""
    if set(packed) != PACKED_FILES:
        raise ValueError('missing or unexpected evidence section')
    with tempfile.TemporaryDirectory(prefix='superhunter-review-') as tmp:
        base = Path(tmp)
        for group, names in SECTION_FILES.items():
            sub = base/group
            sub.mkdir(mode=0o700)
            for name in names:
                raw = packed[f'{group}--{name}']
                if type(raw) is not bytes or len(raw) > 2_000_000:
                    raise ValueError('invalid evidence bytes')
                with (sub/name).open('xb') as stream:
                    stream.write(raw)
                (sub/name).chmod(0o600)
        qa = quality.verify_bundle(base/'qa')
        if qa['status'] != 'LOCAL_QA_PASS':
            raise ValueError('combined QA has not passed')
        fixed = local_lab.verify_local_bundle(base/'lab')
        fuzz = fuzz_lab.verify_fuzz(base/'fuzz')
    receipt = strict_json(packed['qa--receipt.json'])
    if sorted(receipt['discovered']) != test_inventory(ROOT):
        raise ValueError('QA must contain the complete current test inventory')
    return {'qa': qa, 'lab': fixed, 'fuzz': fuzz}


def _facts(packed: dict[str, bytes], checked: dict, plan: dict, caps: dict) -> dict:
    receipt = strict_json(packed['qa--receipt.json'])
    passed = {t['id'] for t in receipt['tests'] if t['outcome']=='PASS'}
    for item in plan['items']:
        if any(test not in passed for test in item['tests']):
            raise ValueError('milestone lacks an executed passing test: '+item['id'])
    return {
        'status': 'LOCAL_REVIEW_PASS',
        'source_digest': checked['qa']['source_digest'],
        'unit_tests': checked['qa']['tests_run'],
        'components': checked['qa']['components'],
        'synthetic_cases': {'fixed': checked['lab']['cases_passed'], 'fuzz': checked['fuzz']['cases_verified']},
        'proof_graph_root': checked['lab']['proof_graph_root'],
        'section_sha256': {g:digest(packed[g+'--COMPLETE.json']) for g in SECTION_FILES},
        'milestones': {'bounded': sum(i['status']=='BOUNDED_IMPLEMENTED' for i in plan['items']),
                       'partial': sum(i['status']=='PARTIAL' for i in plan['items']),
                       'pending': sum(i['status']=='PENDING' for i in plan['items'])},
        'capabilities': {s:sum(i['status']==s for i in caps['items'])
                         for s in ('PARTIAL','PLANNED','REDESIGN_REQUIRED')},
        'capabilities_complete': 0,
        'vulnerability_confirmed': False,
        'production_certified': False,
        'producer_authenticated': False,
        'evidence_level': 'current-code-reverification-of-local-artifacts',
    }


def render_markdown(result: dict, plan: dict, caps: dict) -> str:
    lines = ['# SUPERHUNTER — revisión integrada', '',
             f"Estado: **{result['status']}**. Identidad de código: `{result['source_digest']}`.",
             f"Pruebas del paquete: **{result['unit_tests']}**. Casos numéricos sintéticos: "
             f"{result['synthetic_cases']['fixed']} fijos y {result['synthetic_cases']['fuzz']} generados.", '',
             '**No es un hallazgo, una certificación de seguridad ni prueba de rentabilidad.** '
             'La revisión recalcula los artefactos con el código actual; no autentica al productor remoto.', '',
             '## Componentes enlazados y comprobados', '']
    for name, component in sorted(result['components'].items()):
        lines.append(f"- {name}: {component['status']}; {component['test_count']} referencias de pruebas. "
                     f"Depende de: {', '.join(component['depends_on']) or 'ninguno'}.")
    lines += ['', 'Los grupos pueden compartir pruebas; sus cantidades no se suman.', '',
              '## Los 27 puntos de integración originales', '',
              '✓ Implementación de alcance limitado · ◐ Parcial · ○ Pendiente. No es un porcentaje de la plataforma.','']
    for item in plan['items']:
        mark = {'BOUNDED_IMPLEMENTED':'✓','PARTIAL':'◐','PENDING':'○'}[item['status']]
        lines += [f"{mark} **{item['id']}. {item['title']}** — {item['boundary']}", '']
    lines += ['## Las 50 capacidades', '', quality.checklist(caps), '', render_plan(load_plan(components=quality.COMPONENTS)), '',
              '## Límites de la evidencia', '',
              'Los tests de contrato Candidate/Reconstruction verifican transporte y consistencia; '
              'no ejecutan una PoC ni reconstruyen un protocolo. El laboratorio y el fuzzer utilizan '
              'datos sintéticos y funciones propias fijadas. El grafo representa relaciones entre '
              'artefactos, no flujos SlithIR ni contratos de terceros. Ningún pendiente se elimina '
              'ni se declara completo por pasar estas pruebas.','']
    lines += ['Paquete privado: incluye evidencias originales. Revisión humana necesaria antes de compartir.', '']
    return redact_text('\n'.join(lines)).text


def render_html(markdown: str) -> bytes:
    # No scripts, external resources, clickable user-controlled URLs or raw HTML.
    return ("<!doctype html><html lang=\"es\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">"
            "<title>SUPERHUNTER — revisión local</title>"
            "<style>body{font:16px/1.6 system-ui,sans-serif;max-width:1050px;margin:40px auto;padding:0 24px;}"
            "pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;}h1{font-size:1.5rem}</style>"
            "</head><body><h1>SUPERHUNTER · Evidencia y pendientes</h1><pre>"+
            escape(redact_text(markdown).text)+"</pre></body></html>\n").encode()


def create_review(qa: Path, lab: Path, fuzz: Path, out: Path) -> dict:
    if out.exists() or out.is_symlink():
        raise FileExistsError('review output must be a new private directory')
    if out.resolve().is_relative_to(ROOT.parent):
        raise ValueError('review evidence must remain outside the source checkout')
    before = quality.source_snapshot()
    packed = {}
    for group, directory in (('qa',qa),('lab',lab),('fuzz',fuzz)):
        for name in SECTION_FILES[group]:
            packed[f'{group}--{name}'] = read_artifact(directory, name)
    checked = _verify_sections(packed)
    plan, caps = milestones(), quality.catalog()
    result = {'schema_version':1, 'review_id':str(uuid.uuid4()),
              'created_at':datetime.now(timezone.utc).isoformat(), **_facts(packed,checked,plan,caps)}
    markdown = render_markdown(result,plan,caps)
    if quality.source_snapshot() != before:
        raise ValueError('source changed during review')
    files = {**packed, 'review.json':canonical(result), 'REVIEW.md':markdown.encode(),
             'index.html':render_html(markdown), 'milestones.json':canonical(plan),
             'capabilities.json':canonical(caps)}
    write_new_bundle(out,files)
    return verify_review(out)


def verify_review(root: Path) -> dict:
    before = quality.source_snapshot()
    marker = strict_json(read_artifact(root,'COMPLETE.json'))
    if (type(marker.get('schema_version')) is not int or marker['schema_version']!=1 or
            type(marker.get('sha256')) is not dict or set(marker['sha256'])!=ALL_FILES):
        raise ValueError('review bundle is incomplete or has unexpected files')
    files = {}
    for name, expected in marker['sha256'].items():
        raw = read_artifact(root,name)
        if digest(raw)!=expected:
            raise ValueError('review artifact hash mismatch')
        files[name]=raw
    packed = {k:files[k] for k in PACKED_FILES}
    checked = _verify_sections(packed)
    plan,caps = milestones(),quality.catalog()
    if files['milestones.json']!=canonical(plan) or files['capabilities.json']!=canonical(caps):
        raise ValueError('project context differs from the current source')
    result = strict_json(files['review.json'])
    facts = _facts(packed,checked,plan,caps)
    if set(result)!=set(facts)|{'schema_version','review_id','created_at'}:
        raise ValueError('review verdict fields mismatch')
    if type(result['schema_version']) is not int or result['schema_version']!=1:
        raise ValueError('invalid review schema')
    if type(result['review_id']) is not str or str(uuid.UUID(result['review_id']))!=result['review_id']:
        raise ValueError('invalid review ID')
    if type(result['created_at']) is not str or datetime.fromisoformat(result['created_at']).tzinfo is None:
        raise ValueError('review time must be explicit and timezone-aware')
    if canonical({k:result[k] for k in facts})!=canonical(facts):
        raise ValueError('claimed review verdict differs from recomputed facts')
    markdown=render_markdown(result,plan,caps)
    if files['REVIEW.md']!=markdown.encode() or files['index.html']!=render_html(markdown):
        raise ValueError('rendered report differs from evidence')
    if quality.source_snapshot() != before:
        raise ValueError('source changed during review verification')
    return result


def main(argv: list[str]) -> int:
    parser=PrivateArgumentParser(description='Review existing local evidence; never execute targets')
    sub=parser.add_subparsers(dest='command',required=True)
    make=sub.add_parser('review')
    for name in ('qa','lab','fuzz','out'):
        make.add_argument('--'+name,type=Path,required=True)
    sub.add_parser('verify-review').add_argument('--bundle',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        result=(create_review(args.qa,args.lab,args.fuzz,args.out) if args.command=='review'
                else verify_review(args.bundle))
        print(json.dumps({k:result[k] for k in ('status','review_id','unit_tests','vulnerability_confirmed')}))
        return 0
    except (OSError,ValueError,KeyError,TypeError,RecursionError) as exc:
        print(json.dumps({'status':'LOCAL_REVIEW_ERROR','error_type':type(exc).__name__}))
        return 2
