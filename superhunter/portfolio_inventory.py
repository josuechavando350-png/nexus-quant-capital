"""Read-only reconciliation of the existing documentary registries.

Catalogued repositories are not installations or integrations. This module
does not fetch URLs, load packages, run tools, or promote any status.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
import json
from pathlib import Path
import re

from . import platform, quality, research_plan
from .owned_authority_model import need
from .privacy import PrivateArgumentParser
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

ROOT = Path(__file__).resolve().parent
PROFILE = 'documentary-registries-and-external-portfolio-v1'
FILES = {'inventory.json', 'REVIEW.md'}
DOMAINS = (
    ('VULNERABILITY_RESEARCH', '01-10', 'repo_portfolio/01-vulnerabilities.json'),
    ('DIGITAL_FORENSICS', '11-20', 'repo_portfolio/02-dfir.json'),
    ('DISTRIBUTED_PERFORMANCE', '21-30', 'repo_portfolio/03-performance.json'),
    ('RESEARCH_ALGORITHMS', '31-40', 'repo_portfolio/04-algorithms.json'),
    ('BUGBOUNTY_OPERATIONS', '41-50', 'repo_portfolio/05-operations.json'))
PORTFOLIO_FILES = ('repo_portfolio_50.json', *(row[2] for row in DOMAINS))
CATALOG_FILES = ('integration-checklist.json', 'capabilities.json',
                 'research_initiatives.json', *PORTFOLIO_FILES)
ENTRY_KEYS = {'id', 'name', 'repository', 'url', 'license_observed', 'priority',
              'role', 'rationale', 'integration_contract', 'acceptance_gate',
              'caveat', 'status', 'code_ingested'}
POLICY = {
    'default': 'NO_EXECUTION_NO_CLONING_NO_EXTERNAL_SCANNING',
    'authorized_scope': 'Only owned/offline labs or specifically permitted in-scope programs; per-operation authorization',
    'promotion': 'Separate reviewed PR, pinned commit and hashes, license/SBOM, sandbox, positive/negative/adversarial tests, independent replay, benchmark and real consumer',
    'evidence': 'Do not infer true incident from hash consistency; preserve fail/inconclusive and private evidences',
    'deployment': 'No subscriptions, funds, signatures, broadcasts, workflows, new permissions or infrastructure without explicit separate approval'}


def load_portfolio(root: Path = ROOT) -> dict:
    before = {name: read_artifact(root, name) for name in PORTFOLIO_FILES}
    data = strict_json(before['repo_portfolio_50.json'])
    need(set(data) == {'schema_version', 'title', 'date_utc', 'count', 'status', 'code_ingested',
                      'original_internal_catalogs', 'domains', 'policy', 'entries'}, 'PORTFOLIO_SCHEMA')
    need(type(data['schema_version']) is int and data['schema_version'] == 1 and
         type(data['count']) is int and data['count'] == 50, 'PORTFOLIO_VERSION_COUNT')
    need(data['status'] == 'CATALOGUED_NOT_INTEGRATED' and data['code_ingested'] is False,
         'PORTFOLIO_DOCUMENTARY_STATUS')
    need(all(type(data[k]) is str and 0 < len(data[k].strip()) <= 2048
             for k in ('title', 'date_utc', 'original_internal_catalogs')), 'PORTFOLIO_CONTEXT')
    need(date.fromisoformat(data['date_utc']).isoformat() == data['date_utc'], 'PORTFOLIO_DATE')
    domains = [{'name': name, 'range': span, 'path': 'superhunter/' + path, 'count': 10}
               for name, span, path in DOMAINS]
    need(canonical(data['domains']) == canonical(domains), 'PORTFOLIO_DOMAINS')
    need(canonical(data['policy']) == canonical(POLICY), 'PORTFOLIO_POLICY')
    entries = data['entries']
    need(type(entries) is list and len(entries) == 50, 'PORTFOLIO_ALL_50_REQUIRED')
    repositories = set()
    for number, entry in enumerate(entries, 1):
        need(type(entry) is dict and set(entry) == ENTRY_KEYS, 'PORTFOLIO_ENTRY_SCHEMA')
        need(type(entry['id']) is int and entry['id'] == number, 'PORTFOLIO_ORDERED_IDENTITIES')
        need(entry['status'] == 'CATALOGUED_NOT_INTEGRATED' and entry['code_ingested'] is False,
             'PORTFOLIO_ENTRY_DOCUMENTARY_STATUS')
        need(all(type(entry[k]) is str and 0 < len(entry[k].strip()) <= 4096
                 for k in ENTRY_KEYS - {'id', 'code_ingested'}), 'PORTFOLIO_ENTRY_TEXT')
        need(entry['priority'] in ('P0', 'P1', 'P2', 'P3'), 'PORTFOLIO_PRIORITY')
        repository = entry['repository']
        need(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository) is not None and
             all(part not in ('.', '..') for part in repository.split('/')) and
             entry['url'] == 'https://github.com/' + repository, 'PORTFOLIO_REPOSITORY_REFERENCE')
        need(repository.casefold() not in repositories, 'PORTFOLIO_DUPLICATE_REPOSITORY')
        repositories.add(repository.casefold())
    for index, (name, span, path) in enumerate(DOMAINS):
        mirror = strict_json(before[path])
        expected = {'schema_version': 1, 'group': name, 'range': span,
                    'entries': entries[index*10:(index+1)*10]}
        need(canonical(mirror) == canonical(expected), 'PORTFOLIO_MIRROR_DISAGREEMENT')
    need(before == {name: read_artifact(root, name) for name in PORTFOLIO_FILES},
         'PORTFOLIO_CHANGED_DURING_READ')
    return data


def _registry(name: str, rows: list, title: str) -> dict:
    return {'registry_id': name, 'title': title, 'declared_items': len(rows),
            'declared_status_counts': dict(sorted(Counter(row['status'] for row in rows).items())),
            'items': [{'id': row['id'], 'title': row.get('title', row.get('name')),
                       'declared_status': row['status']} for row in rows],
            'implementation_verified_here': False}


def _report(expected: str, hashes: dict[str, str]) -> dict:
    portfolio = load_portfolio()
    integration = platform.integration_plan()
    capabilities = quality.catalog()
    initiatives = research_plan.load_plan(components=quality.COMPONENTS)
    registries = [
        _registry('integration_requirements', integration['items'], 'Requisitos de integración'),
        _registry('internal_capabilities', capabilities['items'], 'Capacidades internas'),
        _registry('research_initiatives', initiatives['items'], 'Iniciativas'),
        _registry('external_repository_candidates', portfolio['entries'], 'Repositorios externos candidatos')]
    return {'schema_version': 1, 'profile': PROFILE, 'status': 'LOCAL_REGISTRY_INVENTORY_REVIEWED',
            'source_digest': expected, 'catalog_sha256': hashes, 'registries': registries,
            'external_catalog_snapshot_date': portfolio['date_utc'],
            'external_domain_mirrors_checked': len(DOMAINS),
            'external_reference_syntax_checked': True, 'remote_repository_existence_verified': False,
            'external_catalog_promoted': False, 'external_code_ingested_here': False,
            'installation_state_inferred': False, 'license_acceptance_verified': False,
            'qa_evidence_consumed': False, 'native_execution_performed': False,
            'registry_denominators_pooled': False, 'global_progress': None,
            'platform_complete': False, 'vulnerability_confirmed': False,
            'additional_master_plan_proposals_counted': False,
            'later_lab_evidence_replaces_catalog_states': False}


def _render(report: dict) -> bytes:
    lines = ['# Inventario de registros de SuperHunter', '',
             'Se verificó la estructura de cuatro registros documentales distintos.',
             'Los estados se leen del registro; no se certifica aquí su implementación.', '',
             '| Registro | Elementos declarados | Estados declarados |',
             '| --- | ---: | --- |']
    for registry in report['registries']:
        counts = ', '.join(f'{name}: {count}' for name, count in registry['declared_status_counts'].items())
        lines.append(f"| {registry['title']} | {registry['declared_items']} | {counts} |")
    lines += ['', 'Los 50 candidatos externos y las 50 capacidades internas tienen identidades separadas.',
              'No se suman estas listas ni se calcula un porcentaje global.',
              'Los cinco desgloses externos coinciden con sus diez entradas canónicas respectivas.',
              'Las referencias GitHub se comprobaron sintácticamente; no se consultaron ni ejecutaron.',
              'El catálogo externo es una instantánea documental. No se deduce el estado de instalación actual.',
              'La evidencia posterior de laboratorios tiene sus propios perfiles y límites.',
              'Un SDK de telemetría no acredita por sí mismo la integración de un Collector.',
              'No se validaron licencias, integraciones de producción o capacidades generales.']
    return ('\n'.join(lines) + '\n').encode()


def _execute(expected: str) -> dict[str, bytes]:
    before = quality.source_snapshot()
    need(quality.sha(canonical(before)) == expected, 'REGISTRY_INVENTORY_SOURCE')
    raw = {name: read_artifact(ROOT, name) for name in CATALOG_FILES}
    hashes = {name: quality.sha(value) for name, value in raw.items()}
    need(all(before.get(name) == digest for name, digest in hashes.items()),
         'REGISTRY_INVENTORY_UNBOUND_CATALOG')
    report = _report(expected, hashes)
    need(raw == {name: read_artifact(ROOT, name) for name in CATALOG_FILES} and
         before == quality.source_snapshot(), 'REGISTRY_INVENTORY_CHANGED')
    return {'inventory.json': canonical(report), 'REVIEW.md': _render(report)}


def create(out: Path) -> dict:
    need(not out.exists() and not out.is_symlink() and
         not out.resolve().is_relative_to(ROOT.parent), 'REGISTRY_INVENTORY_PRIVATE_OUTPUT')
    files = _execute(quality.sha(canonical(quality.source_snapshot())))
    write_new_bundle(out, files)
    return strict_json(files['inventory.json'])


def _capture(root: Path) -> dict[str, bytes]:
    need(root.is_dir() and not root.is_symlink(), 'REGISTRY_INVENTORY_DIRECTORY')
    names = set()
    for index, entry in enumerate(root.iterdir()):
        need(index < len(FILES) + 1, 'REGISTRY_INVENTORY_FILES')
        names.add(entry.name)
    need(names == FILES | {'COMPLETE.json'}, 'REGISTRY_INVENTORY_FILES')
    return {name: read_artifact(root, name) for name in sorted(names)}


def verify(root: Path, expected: str) -> dict:
    saved = _capture(root)
    marker = {'schema_version': 1, 'sha256': {name: quality.sha(saved[name]) for name in FILES}}
    need(canonical(strict_json(saved['COMPLETE.json'])) == canonical(marker), 'REGISTRY_INVENTORY_HASH')
    fresh = _execute(expected)
    need(all(saved[name] == raw for name, raw in fresh.items()), 'REGISTRY_INVENTORY_REPLAY_MISMATCH')
    need(saved == _capture(root), 'REGISTRY_INVENTORY_REPORT_CHANGED')
    need(quality.sha(canonical(quality.source_snapshot())) == expected, 'REGISTRY_INVENTORY_SOURCE')
    return strict_json(fresh['inventory.json'])


def main(argv: list[str] | None = None) -> int:
    parser = PrivateArgumentParser(description='Review four fixed documentary registries without executing tools')
    subs = parser.add_subparsers(dest='command', required=True)
    make = subs.add_parser('review-registry-inventory'); make.add_argument('--out', type=Path, required=True)
    check = subs.add_parser('verify-registry-inventory')
    check.add_argument('--bundle', type=Path, required=True); check.add_argument('--expected-source', required=True)
    args = parser.parse_args(argv)
    try:
        result = create(args.out) if args.command == 'review-registry-inventory' else verify(args.bundle, args.expected_source)
        print(json.dumps({key: result[key] for key in (
            'status', 'source_digest', 'external_domain_mirrors_checked', 'global_progress', 'vulnerability_confirmed')}))
        return 0
    except (ValueError, OSError, KeyError, TypeError):
        print(json.dumps({'status': 'LOCAL_REGISTRY_INVENTORY_BLOCKED'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
