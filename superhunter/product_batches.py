"""Summarize verified product evidence from one query session in two stable cohorts."""
from collections import Counter

from .product_reasoning import EvidenceError

# Integration receipts published before the first split, at fa5e498d9c7d7ad3d8b685c6c2f127247899ac3c.
BASELINE_IDS = frozenset((24, 30, 41, 45, 111, 131, 136, 140, 142, 143, 147, 150, 157, 159, 199))
# Preserve the 15 baseline identities and prioritize inventory, code parsing and review work.
CATEGORIES = ('SUPPLY', 'CODIGO', 'FORMAL', 'OBSERVACION', 'METODO', 'BINARIOS', 'AGENTES')
RECEIPTS = {
    'ethers-io/ethers.js': 'census_header_evidence', 'wevm/viem': 'census_header_evidence',
    'ethereumjs/ethereumjs-monorepo': 'census_header_evidence',
    'foundry-rs/foundry': 'solidity_metadata_evidence',
    'ack3-ai/wake': 'solidity_metadata_evidence',
    'argotorg/solidity': 'solidity_metadata_evidence',
    'google/osv-scanner': 'spdx_identifier_evidence',
    'anchore/syft': 'evidence', 'cvc5/cvc5': 'evidence',
    'tree-sitter/tree-sitter': 'sbom_location_evidence', 'ast-grep/ast-grep': 'registry_checksum_evidence',
    'tlaplus/tlaplus': 'profile_grouping_evidence', 'microsoft/sarif-sdk': 'sarif_evidence',
    'lief-project/lief': 'runtime_inventory_evidence', 'cdxgen/cdxgen': 'cyclonedx_evidence',
    'ossf/scorecard': 'license_file_evidence', 'guacsec/guac': 'guac_evidence',
    'embarkstudios/cargo-deny': 'license_evidence', 'aboutcode-org/scancode-toolkit': 'license_evidence',
    'deepset-ai/haystack': 'notice_ranking_evidence', 'qdrant/qdrant': 'notice_search_evidence',
    'dependencytrack/dependency-track': 'spdx_group_evidence',
    'alivetoolkit/alive2': 'license_choice_evidence', 'klee/klee': 'license_choice_evidence',
    'dafny-lang/dafny': 'license_choice_evidence',
    'diffblue/cbmc': 'license_choice_evidence',
    'esbmc/esbmc': 'license_choice_evidence',
    'fstarlang/fstar': 'license_choice_evidence',
    'galoisinc/saw-script': 'license_choice_evidence',
    'model-checking/kani': 'license_choice_evidence',
    'rocq-prover/rocq': 'license_choice_evidence',
    'seahorn/seahorn': 'license_choice_evidence',
    'verifast/verifast': 'license_choice_evidence',
    'verus-lang/verus': 'license_choice_evidence',
    'run-llama/llama_index': 'citation_evidence', 'langchain-ai/langgraph': 'wheel_decision_evidence',
    'proptest-rs/proptest': 'batch_property_evidence',
    'pmd/pmd': 'notice_passage_evidence',
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
    if name in ('ethereum/eips', 'ethereum/execution-specs') and row.get('census_header_reference'):
        return 'reference_data', 'census_header_reference'
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


def coverage(index):
    """Join the pinned PR 111 evidence and this session by catalog ID, retaining both origins."""
    from .product_review import ROOT, sha
    from .safe_io import read_artifact, strict_json

    raw = read_artifact(ROOT, 'superhunter/product_supply/coverage-d94b58f.json')
    if sha(raw) != 'b47f69c24ee583c5e8ef61954439b56818bccf6e3fa35a60bf099381d10bc1bd':
        raise EvidenceError('unexpected historical coverage snapshot')
    history = strict_json(raw)
    prior = {row['catalog_id']: row for row in history['receipts']}
    entries = []
    cohort_ids = {r['catalog_id']: number for number, rows in enumerate(cohorts(index.repos.values()), start=1)
                  for r in rows}
    for item in sorted(index.repos.values(), key=lambda r: r['catalog_id']):
        row = index.lookup(item['repository'])
        ident = row['catalog_id']
        previous = prior.get(ident)
        role, proof = receipt(row)
        if previous and (previous['repository'] != row['repository'] or
                         (role != 'pending' and previous['role'] != role)):
            raise EvidenceError('inconsistent historical and session coverage')
        entries.append({'catalog_id': ident, 'repository': row['repository'], 'batch': cohort_ids[ident],
                        'prior_receipt': previous, 'session_role': role, 'session_receipt': proof,
                        'observed_role': previous['role'] if previous else role,
                        'upstream_notice_verified': 'upstream_notice' in row})
    counts = Counter(r['observed_role'] for r in entries)
    return {'catalog_count': len(entries), 'prior_commit': history['commit'],
            'prior_transcript_sha256': history['transcript_sha256'], 'prior_with_receipts': len(prior),
            'session_with_receipts': sum(r['session_role'] != 'pending' for r in entries),
            'with_receipts_in_either': len(entries) - counts['pending'],
            'executable_in_either': counts['executable'], 'reference_data_in_either': counts['reference_data'],
            'pending': counts['pending'], 'verified_upstream_notices': sum(r['upstream_notice_verified'] for r in entries),
            'identities': entries}
