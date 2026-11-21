"""Materialize the product matrix exclusively from live product receipts."""
from collections import Counter

from .product_batches import coverage
from .product_reasoning import EvidenceError
from .product_review import sha
from .safe_io import read_artifact


def published_excerpts():
    from .product_owned_source_checks import excerpt_files
    from .product_passive_source_batch import checked_origins
    from .product_remediation_batch import origins
    from .product_review import ROOT

    records = [dict((k, row[k]) for k in ('id', 'repository', 'revision', 'tree', 'path', 'blob', 'sha256'))
               for row in [*checked_origins(), *origins()]]
    previous = {
        179: ('superhunter/smartbugs_region.py', '0aae0bcb0d699c0cb65c63c1e436c163b7196f8aec9387a8cc2d136b1daa3684'),
        191: ('superhunter/product_supply/source-excerpts/token-types.txt',
              'ab5a4f99a70b5cadb4c139876522567b130320be3843edaaaaa151653eb34826'),
    }
    for number, origin, path, _, blob in excerpt_files():
        local, digest = previous[number]
        if sha(read_artifact(ROOT, local)) != digest:
            raise EvidenceError('historical published excerpt differs from its verified bytes')
        records.append({'id': number, 'repository': origin['repository'], 'revision': origin['commit'],
                        'tree': origin['tree'], 'path': path, 'blob': blob, 'sha256': digest})
    records = sorted(records, key=lambda r: r['id'])
    if len({r['id'] for r in records}) != len(records):
        raise EvidenceError('duplicate published excerpt')
    return records


def build(index):
    if any(x is None for x in (index.source_inventory, index.root_declarations, index.owned_source_checks,
                               index.census_header, index.geth_header, index.source_references, index.score_comparison, index.fork_headers)):
        raise EvidenceError('matrix requires the complete source audit and owned product session')
    result = coverage(index)
    excerpts = {r['id']: r for r in published_excerpts()}
    rows = []
    notices = 0
    tree_count = 0
    for item in result['identities']:
        number = item['catalog_id']
        repo = index.lookup(item['repository'])
        source = repo['source_inventory']
        if number in excerpts and any(source[k] != excerpts[number][k] for k in ('repository', 'revision', 'tree')):
            raise EvidenceError('published excerpt has a different catalog identity or revision')
        if source['evidence'] == 'local_git_tree':
            code = 'complete'
        elif number in excerpts:
            code = 'excerpt'
        else:
            code = 'metadata'
        if code != 'complete' and repo['root_declarations']['tree'] != source['tree']:
            raise EvidenceError('matrix root and acquisition record disagree')
        review = source.get('resolved_notice_scan') or source['notice_scan']
        if not review.get('detected_expression') or not review.get('sha256'):
            raise EvidenceError('source matrix requires the reviewed license notice')
        notices += 1
        recursive = repo.get('recursive_tree_inventory')
        if code == 'complete':
            if source['contents'] is None:
                raise EvidenceError('local source row has no tree inventory')
            scope = 'checked_out_contents'
            nested = len(source['contents']['nested_gitlinks'])
            manifests = sum(source['contents']['manifest_counts_by_filename'].values())
        else:
            if not recursive or recursive['root'] != source['tree'] or recursive['commit'] != source['revision']:
                raise EvidenceError('missing verified recursive tree inventory')
            scope = 'recursive_tree_objects'
            nested = recursive['nested_gitlinks']
            manifests = sum(recursive['manifest_counts'].values())
        tree_count += 1
        operations = item['session_operations']
        previous = item['prior_receipt']
        rows.append({'id': number, 'repository': repo['repository'], 'nature': source['nature'],
                     'commit': source['revision'], 'source': code, 'role': item['observed_role'],
                     'session': item['session_role'], 'receipt': item['session_receipt'] or item['prior_receipt'],
                     'session_operations': operations,
                     'session_evidence_sha256': operations[0]['evidence_sha256'] if operations else None,
                     'historical_line_sha256': previous['line_sha256'] if previous else None,
                     'tree': source['tree'], 'verification_scope': scope, 'nested_gitlinks': nested,
                     'recognized_manifest_paths': manifests,
                     'license': {'document': source['notice_path'], 'detected_expression': review['detected_expression'],
                                 'effective_text_sha256': review['sha256']},
                     'commercial_review': 'pending'})
    sources = Counter(r['source'] for r in rows)
    pending = Counter(r['source'] for r in rows if r['role'] == 'pending')
    return {'rows': rows, 'published_excerpts': list(excerpts.values()), 'catalog': len(rows), 'sources': dict(sources), 'pending_by_source': dict(pending),
            'executable': result['executable_in_either'], 'references': result['reference_data_in_either'],
            'functional': result['with_receipts_in_either'], 'end_to_end': result['session_with_receipts'],
            'session_operation_count': sum(len(r['session_operations']) for r in rows),
            'session_multi_operation_repositories': sum(len(r['session_operations']) > 1 for r in rows),
            'pending': result['pending'], 'verified_trees': tree_count, 'notices_reviewed': notices,
            'commercial_reviews_completed': 0, 'remote_roots': index.root_declarations['remote_roots_verified']}


def markdown(matrix):
    labels = {'complete': 'Completa', 'excerpt': 'Extracto verificado', 'metadata': 'Metadatos',
              'pending': 'Pendiente', 'reference_data': 'Referencia', 'executable': 'Ejecución'}
    natures = {'reference': 'Referencia', 'corpus_or_lab': 'Corpus o laboratorio', 'agent_framework': 'Framework de agentes',
               'library_or_engine': 'Biblioteca o motor', 'analyzer_or_verifier': 'Analizador o verificador',
               'auxiliary_tool': 'Herramienta auxiliar', 'executable_tool': 'Herramienta ejecutable'}
    text = ['# SUPERHUNTER · Matriz de integración', '',
            f"El producto conserva {matrix['catalog']} identidades. Hay {matrix['sources']['complete']} checkouts completos, "
            f"{matrix['sources'].get('excerpt', 0)} extractos verificados y {matrix['sources'].get('metadata', 0)} "
            "proyectos con alcance documental y de metadatos.", '',
            f"Participación acreditada de {matrix['functional']} proyectos, con {matrix['executable']} de ejecución y "
            f"{matrix['references']} referencias. En la sesión completa participaron {matrix['end_to_end']}. "
            f"Quedan {matrix['pending']} sin recibo funcional.", '',
            f"Se verificaron el commit y el árbol de {matrix['verified_trees']} identidades y se cotejó un aviso "
            f"por proyecto. Las obligaciones de distribución del producto completo siguen pendientes. La consulta "
            "`integration-matrix` conserva la ruta y el hash del aviso, el árbol, los manifiestos y el recibo por fila.", '',
            '[Reproducción de la sesión](SOURCE_ASSURANCE.md) · [Estado histórico del PR 114]'
            '(https://github.com/josuechavando350-png/nexus-quant-capital/blob/ae02690627443df08b8eedb9d63a7a30cbda6c0e/superhunter/INTEGRATION_STATUS_200.md)',
            '', '| ID | Repositorio | Naturaleza | Fuente | Función acreditada | En esta sesión |',
            '|---:|---|---|---|---|---|']
    for row in matrix['rows']:
        text.append(f"| {row['id']} | [{row['repository']}](https://github.com/{row['repository']}/tree/{row['commit']}) "
                    f"| {natures[row['nature']]} | {labels[row['source']]} "
                    f"| {labels[row['role']]} | {'Sí' if row['session'] != 'pending' else '—'} |")
    return '\n'.join(text) + '\n'
