"""Summarize verified product evidence from one query session in two stable cohorts."""
from collections import Counter
from functools import cache
import re

from .product_reasoning import EvidenceError
from .product_review import ROOT, sha
from .safe_io import canonical, read_artifact, strict_json

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


# Reviewed outputs for the fixed NQC fixtures. Each producer still has to rerun before
# a receipt is attached. A name, an arbitrary nonempty adapter or a copied source row is insufficient.
FIXED_SOURCE_RECEIPTS = {
    'securego/gosec': ('executable', 'go_source_receipt', {
        'query': 'go-header-digest', 'revision': '244f1f6f4d1d0d14f89e79a73dab1219eabb5228',
        'report_sha256': 'eb0004a88829551a8ac553286ec1ac8160048178df27dc071fca147b3cc2a95c'}),
    'paradigmxyz/reth': ('reference_data', 'fork_header_reference', {
        'query': 'fork-headers', 'revision': '53b5db1c3bc841bae679e58a625485d3d44d5b74',
        'files': {'hoodi': '4b6b5713490ff9adabca742b7864f866dd124203'},
        'result_sha256': '6ba1e02e5ac1d70ed5a0ae4ee675d5108b4f0650fe9fb673d8fc0cdbc269cbfb'}),
    'besu-eth/besu': ('reference_data', 'fork_header_reference', {
        'query': 'fork-headers', 'revision': '10dc5130f7424488cc5730fca1e98565a313714b',
        'files': {'mainnet': '48278986a699799d6aeca615a4170df6fd991843',
                  'hoodi': '1433e48c970339ef6011ab33ab822e4ef33efbd5'},
        'result_sha256': '6ba1e02e5ac1d70ed5a0ae4ee675d5108b4f0650fe9fb673d8fc0cdbc269cbfb'}),
    'ethereum/hive': ('reference_data', 'fork_header_reference', {
        'query': 'fork-headers', 'revision': 'befb5c9edf4e1df25351e2a4ebdaca15e3d5d01b',
        'files': {'genesis': 'd28bb525d1b5cc92e4c65fdbb15ddf371f65c75b',
                  'headblock': '445cad762489de4a3c99d77e9ffcd70d0c496fa8',
                  'headnewpayload': '39fce1189642cb3554899f3475283bd89ca01062',
                  'headfcu': 'f84d9e5a625f30fdbbc2ba430d071a5f1354cc2c'},
        'result_sha256': '6ba1e02e5ac1d70ed5a0ae4ee675d5108b4f0650fe9fb673d8fc0cdbc269cbfb'}),
    'stanfordnlp/dspy': ('executable', 'score_comparison_receipt', {
        'query': 'score-comparison', 'engine': 'dspy', 'revision': '226d534da38ab8a39e4d6383e01e121dab50da51',
        'case_sha256': 'b3212debe6576bb0e5f3d9b011aab1339f05448f8dd9e33e1b572e10900d0038',
        'result_sha256': '7a1d2fff22878043d4b2cdc4e00f2b62475a9a3f19682daba327ee0901b73841'}),
    'ukgovernmentbeis/inspect_ai': ('executable', 'score_comparison_receipt', {
        'query': 'score-comparison', 'engine': 'inspect', 'revision': '82925564c9330e5440d490a7d97d037e11e66c9a',
        'case_sha256': 'b3212debe6576bb0e5f3d9b011aab1339f05448f8dd9e33e1b572e10900d0038',
        'result_sha256': '950182072b97dc7256838c5c06ce82ad22b1c82ec4f185c4632c497d81de1843'}),
    'pycqa/bandit': ('executable', 'owned_source_receipt', {
        'query': 'owned-source-checks', 'section': 'yaml', 'revision': '2d5467c45c3189f4d7d07e8022276bc73a478abd',
        'sha256': '1e7c745055c409f85a1824324cbcfca57318edd1f5583add46c89685ace670b6'}),
    'smartbugs/smartbugs': ('executable', 'owned_source_receipt', {
        'query': 'owned-source-checks', 'section': 'yaml', 'revision': 'a246003622775c730d5522429d8fed8846406e17',
        'sha256': '1e7c745055c409f85a1824324cbcfca57318edd1f5583add46c89685ace670b6'}),
    'ossf/malicious-packages': ('reference_data', 'owned_source_receipt', {
        'query': 'owned-source-checks', 'section': 'packages', 'revision': 'aaefca1f03b51a4e26db1fad48b172279a2e41a9',
        'sha256': '1e38dce3684e4366b3166687b475d3807646858419e7df2139f3410405de410b'}),
    'crytic/building-secure-contracts': ('reference_data', 'owned_source_receipt', {
        'query': 'owned-source-checks', 'section': 'token_types', 'revision': '0e679905ce336d81b1eade9cfe924011e9073339',
        'sha256': '75c548dd47fb7bdfba7c177a20e61a4a8a3b0b9aedaf2a9bf763ad99117749b6'}),
    'ethereum/go-ethereum': ('executable', 'geth_header_evidence', {
        'report': 'geth-census', 'revision': '2b7829ea6aed9a95a3fd793cca46731202c6c310',
        'binary_sha256': '11ad28b59b30c1fabb60c68616bc1b8ff676e484ce15dfcecec57fa2ef7f100d',
        'report_sha256': 'ca134db9b8984ea0d776c4236ac8c6ecb98f905fd2b1882bc36d81dfb71286f0'}),
    'openzeppelin/openzeppelin-contracts': ('reference_data', 'source_reference', {
        'report': 'source-references', 'revision': '5172e1681f05f4aa189b7740bf2c0316af67c3b3',
        'report_sha256': 'e41dd7e73dbd9d22b178736dabdf05460851f15201b633a9739184b432d85a22'}),
    'ethereum/consensus-specs': ('reference_data', 'source_reference', {
        'report': 'source-references', 'revision': '2d519bc04f0f9c52f0e0876f69b238a9523f1ef8',
        'report_sha256': '77046aa1df356c21d1b9578f54f5ea0c0a9d10bff291eed82344cf7821a42490'})}


@cache
def contracts():
    payload = read_artifact(ROOT, 'superhunter/product_supply/receipt-contracts.json')
    if sha(payload) != '4ff933ff8a15ce46424208347320ecc3b51eb27ab58edfaaaaa6a91d14c0af03':
        raise EvidenceError('reviewed receipt contracts changed')
    return strict_json(payload)


def check_native(name, payload):
    contract = contracts()['native'][name]
    if (not isinstance(payload, dict) or
            any(k not in payload or type(payload[k]).__name__ != t for k, t in contract['types'].items()) or
            any(payload[k] != v for k, v in contract['fixed'].items())):
        raise EvidenceError('native receipt differs from reviewed producer contract')
    for k, value in payload.items():
        if k.endswith('_sha256'):
            digests = value.values() if isinstance(value, dict) else value if isinstance(value, list) else [value]
            if not digests or any(not isinstance(v, str) or not re.fullmatch('[0-9a-f]{64}', v) for v in digests):
                raise EvidenceError('malformed native receipt digest')
    if name == 'anchore/syft' and payload['package_observations'] <= 0:
        raise EvidenceError('empty native package inventory')
    if name == 'cvc5/cvc5' and (payload['minimum_python_pin_groups'] < 1 or not payload['isolate_profile']):
        raise EvidenceError('missing native solver result')


def check_reference(name, payload):
    if sha(canonical(payload)) != contracts()['references'][name]:
        raise EvidenceError('reference receipt differs from reviewed fixed inputs')


def receipt(row):
    if 'component_control_receipt' in row:
        from .product_component_controls import role_for
        return role_for(row)
    name = row['repository'].casefold()
    if name in FIXED_SOURCE_RECEIPTS:
        role, key, expected = FIXED_SOURCE_RECEIPTS[name]
        if key not in row:
            return 'pending', None
        if row[key] != expected:
            raise EvidenceError('source receipt differs from the accepted product result')
        return role, key
    if name in RECEIPTS and row.get(RECEIPTS[name]):
        check_native(name, row[RECEIPTS[name]])
        return 'executable', RECEIPTS[name]
    if name in ('ethereum/eips', 'ethereum/execution-specs') and row.get('census_header_reference'):
        check_reference(name, row['census_header_reference'])
        return 'reference_data', 'census_header_reference'
    role = row.get('supply_role') or {}
    if name == 'in-toto/in-toto' and role.get('role') == 'executable' and role.get('artifact') == 'supply.link':
        check_reference(name, {'supply_role': role})
        return 'executable', 'supply.link'
    if name in ('owasp/asvs', 'owasp/cheatsheetseries') and role.get('role') == 'reference_data' and row.get('controls'):
        check_reference(name, {'supply_role': role, 'controls': row['controls']})
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


@cache
def verified_history():
    raw = read_artifact(ROOT, 'superhunter/product_supply/coverage-d94b58f.json')
    if sha(raw) != 'b47f69c24ee583c5e8ef61954439b56818bccf6e3fa35a60bf099381d10bc1bd':
        raise EvidenceError('unexpected historical coverage snapshot')
    history = strict_json(raw)
    transcript = read_artifact(ROOT, 'superhunter/product_supply/session-d94b58f.txt')
    if sha(transcript) != history['transcript_sha256']:
        raise EvidenceError('unverified historical transcript')
    lines = transcript.splitlines(keepends=True)
    for binding in history['receipts']:
        line = lines[binding['catalog_id'] - 1]
        row = strict_json(line)
        if (sha(line) != binding['line_sha256'] or
                (row['catalog_id'], row['repository']) != (binding['catalog_id'], binding['repository']) or
                receipt(row) != (binding['role'], binding['receipt'])):
            raise EvidenceError('historical evidence is detached from its producer')
    return history


def coverage(index):
    """Join the pinned PR 111 evidence and this session by catalog ID, retaining both origins."""
    history = verified_history()
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
