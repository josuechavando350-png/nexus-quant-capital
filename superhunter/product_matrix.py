"""Materialize the product matrix exclusively from live product receipts."""
from collections import Counter

from .product_batches import coverage
from .product_reasoning import EvidenceError


def build(index):
    if any(x is None for x in (index.source_inventory, index.root_declarations, index.owned_source_checks,
                               index.census_header, index.geth_header, index.source_references, index.score_comparison)):
        raise EvidenceError('matrix requires the complete source audit and owned product session')
    result = coverage(index)
    rows = []
    for item in result['identities']:
        number = item['catalog_id']
        repo = index.lookup(item['repository'])
        source = repo['source_inventory']
        if source['evidence'] == 'local_git_tree':
            code = 'complete'
        elif number in (179, 191) and repo.get('owned_source_receipt'):
            code = 'excerpt'
        else:
            code = 'metadata'
        if code != 'complete' and repo['root_declarations']['tree'] != source['tree']:
            raise EvidenceError('matrix root and acquisition record disagree')
        rows.append({'id': number, 'repository': repo['repository'], 'nature': source['nature'],
                     'commit': source['revision'], 'source': code, 'role': item['observed_role'],
                     'session': item['session_role'], 'receipt': item['session_receipt'] or item['prior_receipt']})
    sources = Counter(r['source'] for r in rows)
    pending = Counter(r['source'] for r in rows if r['role'] == 'pending')
    return {'rows': rows, 'catalog': len(rows), 'sources': dict(sources), 'pending_by_source': dict(pending),
            'executable': result['executable_in_either'], 'references': result['reference_data_in_either'],
            'functional': result['with_receipts_in_either'], 'end_to_end': result['session_with_receipts'],
            'pending': result['pending'], 'remote_roots': index.root_declarations['remote_roots_verified']}


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
            '[Reproducción de la sesión](SOURCE_ASSURANCE.md) · [Estado histórico del PR 114]'
            '(https://github.com/josuechavando350-png/nexus-quant-capital/blob/ae02690627443df08b8eedb9d63a7a30cbda6c0e/superhunter/INTEGRATION_STATUS_200.md)',
            '', '| ID | Repositorio | Naturaleza | Fuente | Función acreditada | En esta sesión |',
            '|---:|---|---|---|---|---|']
    for row in matrix['rows']:
        text.append(f"| {row['id']} | {row['repository']} | {natures[row['nature']]} | {labels[row['source']]} "
                    f"| {labels[row['role']]} | {'Sí' if row['session'] != 'pending' else '—'} |")
    return '\n'.join(text) + '\n'
