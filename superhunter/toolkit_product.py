"""Join live T36 results to SuperHunter's existing repository identities."""
import hashlib
import json
import re

from .product_sources import git
from .toolkit_setup import RELEASES
from .tools import verify_review_115 as archive

# GitHub repository 40892817 moved from ethereum to argotorg. Both pins must still match.
CATALOG_ALIASES = {'ethereum/solidity': 'argotorg/solidity'}

BASE_SESSION = 'consolidated-acceptance-publication-policy/first/session.json'
BASE_DIGEST = 'e931d8c1a0fd942758ff4e428589069e4ea8ff8da376b1c49820e4617fead9ad'


def prior_session():
    raw = archive.unpack(archive.pinned_file(BASE_SESSION, BASE_DIGEST))
    matrix = json.loads(raw.splitlines()[archive.response_keys(raw).index('integration-matrix')])
    return raw, matrix['rows']


def product_session(root, tools, result, work, runtime, run):
    """Use one compiler output and one immutable subject for all participating stages."""
    python = runtime / 'venv/bin/python'
    worker = root / 'superhunter/toolkit_compiler_worker.py'
    output = run([python, '-I', '-B', worker, runtime, root], work)
    compiler = json.loads(output)
    source = (work / 'src/NqcFlashFundingExecutor.sol').read_bytes()
    subject = hashlib.sha256(source).hexdigest()

    def evidence(repo, path):
        tool = tools[repo]
        return git(root / tool['path'], 'show', tool['commit'] + ':' + path).decode()

    rebasing = json.loads(evidence('pessimistic-io/slitherin', 'slitherin/utils/rebase_tokens.json'))
    deflationary = json.loads(evidence('pessimistic-io/slitherin', 'slitherin/utils/deflat_tokens.json'))['objects']
    listed = {r['address'].casefold() for r in [*rebasing.values(), *deflationary]}
    literal_addresses = {match.decode().lower() for match in re.findall(rb'\b0x[0-9a-fA-F]{40}\b', source)}
    token_profile = {'rebasing_entries': len(rebasing), 'deflationary_entries': len(deflationary),
                     'matched_literal_addresses': sorted(literal_addresses & listed)}
    functions = set(compiler['function_names'])
    concepts = set()
    if {'balanceOf', 'approve', 'transfer'} <= functions:
        concepts.add('ERC20')
    if {'flashLoan', 'receiveFlashLoan'} <= functions:
        concepts.add('Flash Loan')
    if deflationary and 'ERC20' in concepts:
        concepts.add('Fee On Transfer')
    if rebasing and 'ERC20' in concepts:
        concepts.add('Rebasing Tokens')
    glossary = evidence('solodit/solodit_content', 'report_tags.md')
    tags = {parts[1].strip(): number for number, line in enumerate(glossary.splitlines(), 1)
            if len(parts := line.split('|')) >= 4 and parts[1].strip() in concepts}
    if set(tags) != concepts:
        raise ValueError('Solodit did not resolve the token-review vocabulary')
    checklist = evidence('crytic/building-secure-contracts', 'development-guidelines/token_integration.md')
    control_terms = set()
    if 'transfer' in functions:
        control_terms.add('transfer')
    if 'Flash Loan' in tags:
        control_terms.add('flash')
    if 'balanceOf' in functions:
        control_terms.add('balance')
    if 'Fee On Transfer' in tags:
        control_terms.add('fee')
    start = checklist.index('## ERC20 Tokens')
    section = checklist[start:checklist.index('## ERC721 Tokens', start)]
    first_line = checklist[:start].count('\n') + 1
    checks = [{'line': index, 'text': line.removeprefix('- [ ] ').split('**')[1]} for index, line
              in enumerate(section.splitlines(), first_line) if line.startswith('- [ ] **')
              and any(term in line.casefold() for term in control_terms)]
    if not checks:
        raise ValueError('no matching token integration controls')
    raw, previous = prior_session()
    history_digest = hashlib.sha256(raw).hexdigest()
    # Validate the product's actual JSON export with the local file protocol.
    payload = {'subject_sha256': subject, 'source_metrics': compiler, 'token_profile': token_profile,
               'solodit_tags': tags, 'review_checklist': checks,
               'catalog': {'transcript_sha256': history_digest, 'repositories': len(previous),
                           'operations': sum(len(row['session_operations']) for row in previous)},
               'regression': {key: result[key] for key in ('forge', 'smtchecker', 'mutation',
                                                           'medusa_property', 'echidna', 'static_rule_groups')}}
    export = work / 'product-evidence.json'
    export.write_text(json.dumps(payload, sort_keys=True))
    template = {'id': 'nqc-local-product-export', 'info': {'name': 'NQC evidence export', 'author': 'nqc',
                'severity': 'info'}, 'file': [{'extensions': ['json'], 'matchers': [{'type': 'word',
                'condition': 'and', 'words': [subject, history_digest, '"method_selectors"', '"solodit_tags"', '"review_checklist"', '"regression"']}]}]}
    (work / 'export.yaml').write_text(json.dumps(template))
    events = run([runtime / 'nuclei', '-duc', '-ni', '-no-stdin', '-nh', '-file', '-pt', 'file',
                  '-t', 'export.yaml', '-u', export.resolve(), '-j', '-or', '-silent'], work)
    parsed = [json.loads(line) for line in events.splitlines() if line.strip()]
    if (len(parsed) != 1 or parsed[0].get('template-id') != template['id']
            or parsed[0].get('matcher-status') is not True
            or str(export.resolve()) != parsed[0].get('matched-at')):
        raise ValueError('Nuclei did not confirm the generated local export')

    operations = {
        'ethereum/solidity': ('engine', 'compile T36 and prove its plan length bound', result['smtchecker']),
        'foundry-rs/foundry': ('engine', 'run T36 regression suite', {'tests_passed': len(result['forge'])}),
        'crytic/properties': ('library', 'assert constructor roles in Forge', {'property': result['medusa_property']}),
        'crytic/echidna': ('engine', 'check constructor roles with a fixed seed', result['echidna']),
        'crytic/medusa': ('engine', 'check operator and strategy roles', {'property': result['medusa_property']}),
        'Certora/gambit': ('engine', 'mutate the plan validator and rerun Forge', result['mutation']),
        'Picodes/4naly3er': ('library', 'apply upstream rules to the compiler AST', {'groups': result['static_rule_groups']}),
        'crytic/slither': ('library', 'calculate ABI selectors and compare against solc', {'selectors': len(compiler['method_selectors'])}),
        'a16z/halmos': ('library', 'resolve the same selectors to contract AST names', {'mapped': len(compiler['method_selectors'])}),
        'trailofbits/manticore': ('library', 'parse ABI input tuples before selector reconciliation', {'parsed': len(compiler['method_selectors'])}),
        'Cyfrin/aderyn': ('library', 'tokenize source and count code lines', {'code_lines': compiler['code_lines']}),
        'semgrep/semgrep': ('library', 'parse Solidity and compare function declarations to solc', {'functions': compiler['grammar_functions']}),
        'fuzzland/ityfuzz': ('library', 'enumerate local runtime bytecode instruction boundaries', {'instructions': compiler['instructions']}),
        'Consensys/mythril': ('library', 'classify opcodes at the enumerated boundaries', {'frequencies': compiler['opcode_counts']}),
        'runtimeverification/kontrol': ('library', 'map checked instruction offsets to T36 source', {'mapped': compiler['mapped_to_source']}),
        'pessimistic-io/slitherin': ('reference_data', 'apply pinned token lists to T36 address literals', token_profile),
        'solodit/solodit_content': ('reference_data', 'resolve token behavior and protocol tags', tags),
        'crytic/building-secure-contracts': ('reference_data', 'select controls for token integration review', checks),
        'projectdiscovery/nuclei': ('engine', 'match the assembled JSON export on disk', {'matched': True, 'export_sha256': hashlib.sha256(export.read_bytes()).hexdigest()})
    }
    return join_results(previous, history_digest, tools, operations, subject, compiler)


def join_results(previous, history_digest, tools, operations, subject, compiler):
    if set(operations) != set(tools):
        raise ValueError('session operations and declared toolkit repositories differ')
    releases = {repo: {'tag': tag, 'asset': asset, 'sha256': digest}
                for _, repo, tag, asset, _, digest in RELEASES}
    union = {row['repository'].casefold(): {
        'repository': row['repository'], 'catalog_id': row['id'], 'historical_commit': row['commit'],
        'historical_tree': row['tree'], 'historical_role': row['session'], 'historical_operations': row['session_operations']
    } for row in previous}
    if len(union) != len(previous):
        raise ValueError('duplicate identity in the accepted product session')
    for repo, (role, action, observation) in operations.items():
        key = CATALOG_ALIASES.get(repo.casefold(), repo.casefold())
        row = union.setdefault(key, {'repository': repo})
        if ('catalog_id' in row and (row['historical_commit'], row['historical_tree'])
                != (tools[repo]['commit'], tools[repo]['tree'])):
            raise ValueError('overlapping repository commit or tree differs: ' + repo)
        if key != repo.casefold():
            row['aliases'] = [repo]
        row['toolkit'] = {'repository': repo, 'source_path': tools[repo]['path'], 'tree': tools[repo]['tree'],
                          'commit': tools[repo]['commit'], 'role': role, 'operation': action, 'result': observation}
        if repo in releases:
            row['toolkit']['binary_release'] = releases[repo]
    return {'subject_sha256': subject, 'current_repositories': len(operations), 'historical_repositories': len(previous),
            'historical_transcript_sha256': history_digest, 'unique_repositories': len(union),
            'overlapping_repositories': sum('toolkit' in row and 'catalog_id' in row for row in union.values()),
            'repositories': list(union.values()), 'compiler_evidence': compiler}
