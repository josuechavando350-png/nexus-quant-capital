"""Summarize verified product evidence from one query session in two stable cohorts."""
from collections import Counter

from .product_reasoning import EvidenceError

# Integration receipts published before the first split, at fa5e498d9c7d7ad3d8b685c6c2f127247899ac3c.
BASELINE_IDS = frozenset((24, 30, 41, 45, 111, 131, 136, 140, 142, 143, 147, 150, 157, 159, 199))
# Preserve the 15 baseline identities and prioritize inventory, code parsing and review work.
CATEGORIES = ('SUPPLY', 'CODIGO', 'FORMAL', 'OBSERVACION', 'METODO', 'BINARIOS', 'AGENTES')
RECEIPTS = {
    'anchore/syft': 'evidence', 'cvc5/cvc5': 'evidence',
    'tree-sitter/tree-sitter': 'sbom_location_evidence', 'ast-grep/ast-grep': 'registry_checksum_evidence',
    'tlaplus/tlaplus': 'profile_grouping_evidence', 'microsoft/sarif-sdk': 'sarif_evidence',
    'lief-project/lief': 'runtime_inventory_evidence', 'cdxgen/cdxgen': 'cyclonedx_evidence',
    'ossf/scorecard': 'license_file_evidence', 'guacsec/guac': 'guac_evidence',
    'embarkstudios/cargo-deny': 'license_evidence', 'aboutcode-org/scancode-toolkit': 'license_evidence',
    'deepset-ai/haystack': 'notice_ranking_evidence', 'qdrant/qdrant': 'notice_search_evidence',
    'dependencytrack/dependency-track': 'spdx_group_evidence',
    'qemu/qemu': 'arm_inventory_evidence',
    'rustsec/rustsec': 'lock_graph_evidence', 'pgvector/pgvector': 'notice_similarity_evidence',
}


def cohorts(repositories):
    priorities = {category: i for i, category in enumerate(CATEGORIES)}
    rows = list(repositories)
    if (len(rows) != 200 or {r['catalog_id'] for r in rows} != set(range(1, 201))
            or len({r['repository'].casefold() for r in rows}) != 200):
        raise EvidenceError('batch partition requires all 200 distinct PR 110 identities')
    rows.sort(key=lambda r: (r['catalog_id'] not in BASELINE_IDS,
                             priorities.get(r['category'], len(priorities)), r['catalog_id']))
    return rows[:100], rows[100:]


def receipt(row):
    name = row['repository'].casefold()
    if name in RECEIPTS and row.get(RECEIPTS[name]):
        return 'executable', RECEIPTS[name]
    role = row.get('supply_role') or {}
    if name == 'in-toto/in-toto' and role.get('role') == 'executable' and role.get('artifact') == 'supply.link':
        return 'executable', 'supply.link'
    if name in ('owasp/asvs', 'owasp/cheatsheetseries') and role.get('role') == 'reference_data' and row.get('controls'):
        return 'reference_data', role['artifact']
    return 'pending', None


def summary(index, number):
    group = cohorts(index.repos.values())[number - 1]
    identities = []
    for item in group:
        name = item['repository']
        row = index.lookup(name)
        kind, proof = receipt(row)
        identities.append({'catalog_id': row['catalog_id'], 'repository': name, 'role': kind, 'receipt': proof})
    counts = Counter(r['role'] for r in identities)
    return {'batch': number, 'identities': identities, 'executable': counts['executable'],
            'reference_data': counts['reference_data'], 'pending': counts['pending'],
            'with_evidence': len(identities) - counts['pending']}
