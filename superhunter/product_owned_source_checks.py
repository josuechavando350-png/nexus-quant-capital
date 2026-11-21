"""Produce evidence on fixed NQC source, package declarations and interface types."""
import ast
import base64
from io import BytesIO
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from zipfile import ZipFile

from . import smartbugs_region
from .product_census_header import pinned
from .product_notice_ranking import ISOLATE, install_wheels
from .product_reasoning import EvidenceError, declared_facts, python_name
from .product_remote_roots import parse_tree, roots
from .product_review import ROOT, capture_inputs, copy_release, sha
from .product_solidity_headers import SOLC_SHA, inputs, run
from .product_source_references import WETH, signatures
from .product_sources import git
from .repository_boundary import git_object
from .safe_io import canonical, read_artifact, strict_json

SUPPLY = 'superhunter/product_supply/'
LOCK = SUPPLY + 'bandit-linux-py312.txt'
LOCK_SHA = 'be52ce92610b9035e1ac4f8fb8ebed4960ea969172a8b68da1502927d6ee7704'
SCOPE = 'superhunter/native_sources/diablo/scope.py'
SCOPE_SHA = 'c54fae956f8868dc551a59e0927a96e4a4caa65ba8d51488ec539cbb9755e37c'
TREE_PROOFS = SUPPLY + 'source-excerpts/trees.json'
TREE_SHA = '2bc34435f830bbe3aa6db05c7075935e7d86a2d7f7ee0ef2fca9fbb48c65a36a'
BANDIT = '2d5467c45c3189f4d7d07e8022276bc73a478abd'
OPENSSF = 'aaefca1f03b51a4e26db1fad48b172279a2e41a9'
OSV_DIR = 'osv/malicious/pypi'
CONTROL_PATH = OSV_DIR + '/0requests/MAL-2026-15859.json'
FILES = {179: ('sb', 'sarif.py', 'sarif-source.txt'),
         191: ('development-guidelines', 'token_integration.md', 'token-guide.txt')}


def excerpt_files():
    proofs = strict_json(pinned(ROOT, TREE_PROOFS, TREE_SHA))['sources']
    selected = {r['id']: (r, entries) for r, entries in roots() if r['id'] in FILES}
    if [r['id'] for r in proofs] != [179, 191]:
        raise EvidenceError('bounded source proof scope differs')
    for proof in proofs:
        num = proof['id']
        row, entries = selected[num]
        folder, name, local = FILES[num]
        if (folder, name) != (proof['directory'], proof['file']):
            raise EvidenceError('bounded source path differs')
        mode, oid = entries[folder.encode()]
        children = parse_tree(base64.b64decode(proof['tree_bytes'], validate=True), oid)
        file_mode, blob = children[name.encode()]
        if mode != b'40000' or file_mode != b'100644':
            raise EvidenceError('expected upstream directory and regular source')
        yield num, row, folder + '/' + name, local, blob


def checked_excerpts(kit):
    docs = {}
    for num, _, _, local, blob in excerpt_files():
        raw = read_artifact(kit, local)
        if git_object('blob', raw) != blob:
            raise EvidenceError('bounded source bytes differ from Git')
        docs[num] = raw
    def region(raw):
        funcs = [n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name == 'result_region']
        if len(funcs) != 1:
            raise EvidenceError('upstream source-region function missing')
        return ast.get_source_segment(raw.decode(), funcs[0])
    if region(docs[179]) != region(read_artifact(ROOT, 'superhunter/smartbugs_region.py')):
        raise EvidenceError('local source-region function differs from upstream')
    clauses = read_artifact(ROOT, SUPPLY + 'source-excerpts/token-types.txt').decode().splitlines()
    headings = re.findall(r'(?m)^- \[ \] \*\*(.*?)\*\*', docs[191].decode())
    if len(clauses) != 2 or any(headings.count(c) != 1 for c in clauses):
        raise EvidenceError('Crytic rule missing or ambiguous')
    return clauses


def token_types(clauses, solkit, authority):
    if not authority:
        raise EvidenceError('token type comparison requires the OpenZeppelin interface receipt')
    first = re.fullmatch(r'`(\w+)` and `(\w+)` return a boolean\.', clauses[0])
    second = re.fullmatch(r'`(\w+)` returns a `(uint[0-9]+)`\.', clauses[1])
    if not first or not second:
        raise EvidenceError('unsupported token type clause')
    rules = {fn[0].lower() + fn[1:]: 'bool' for fn in first.groups()}
    rules[second[1].lower()] = second[2]
    source = inputs()[0][WETH]
    start = source.index('interface IMainnetWeth {')
    fragment = source[start:source.index('}', start)+1]
    altered = fragment.replace('function decimals() external view returns (uint8)',
                               'function decimals() external view returns (uint256)')
    altered = re.sub(r'(function transfer\(address recipient, uint256 amount\) external returns \()bool', r'\1uint256', altered)
    with tempfile.TemporaryDirectory(prefix='nqc-token-types-') as tmp:
        work = Path(tmp)
        copy_release('solc', solkit/'solc', work/'solc', SOLC_SHA)
        report = run([work/'solc', '--no-import-callback', '--standard-json'], work, {'HOME': tmp}, {
            'language': 'Solidity', 'sources': {n: {'content': 'pragma solidity ^0.8.24;\n' + text}
                                              for n, text in [('owned.sol', fragment), ('control.sol', altered)]},
            'settings': {'stopAfter': 'parsing', 'outputSelection': {'*': {'': ['ast']}}}})
    if any(e['severity'] == 'error' for e in report.get('errors', [])):
        raise EvidenceError('source type comparison could not parse inputs')
    observed = {n: signatures(ast_data['ast'], 'IMainnetWeth') for n, ast_data in report['sources'].items()}
    def mismatches(fields):
        return sorted(k for k, expected in rules.items() if k not in fields or fields[k][1] != [expected])
    differences = {n: mismatches(fields) for n, fields in observed.items()}
    if differences != {'owned.sol': [], 'control.sol': ['decimals', 'transfer']}:
        raise EvidenceError('type authority disagrees with owned controls')
    if any(observed['owned.sol'][k] != authority['signatures'][k] for k in ('transfer', 'transferFrom')):
        raise EvidenceError('Crytic and OpenZeppelin disagree on the owned interface')
    return {'rules': rules, 'differences': differences, 'fixture_sha256': sha(source.encode()),
            'control_sha256': sha(altered.encode()), 'solc_sha256': SOLC_SHA,
            'authority_sha256': sha(canonical(authority))}


def package_lookup(checkout):
    repo = checkout/'upstream/145-malicious-packages'
    if git(repo, 'rev-parse', 'HEAD').decode().strip() != OPENSSF:
        raise EvidenceError('OpenSSF data checkout revision differs')
    data = git(repo, 'cat-file', 'tree', OPENSSF + ':' + OSV_DIR)
    tree = 'd743c02ad6952121c199bc4f4d1379ce967d1694'
    names = {python_name(k.decode()) for k, (mode, _) in parse_tree(data, tree).items() if mode == b'40000'}
    fixed = {(name, version) for path, name, version in declared_facts(capture_inputs())
             if path.endswith('requirements.txt')}
    overlaps = sorted(n for n in {n for n, _ in fixed} if n in names)
    raw = git(repo, 'show', OPENSSF + ':' + CONTROL_PATH)
    if git_object('blob', raw) != '5ff498c50337859eba4f72fc488e14e21ba9e463':
        raise EvidenceError('OpenSSF advisory control differs')
    record = strict_json(raw)
    affected, = record['affected']
    if (record.get('withdrawn') or affected['package']['ecosystem'] != 'PyPI'
            or affected.get('ranges') or affected['package']['name'] not in names):
        raise EvidenceError('OpenSSF control requires a current explicit-version record')
    samples = {'0.0.1': 'LISTED', '0.0.2': 'ABSENT_FROM_RECORD'}
    result = {v: ('LISTED' if v in affected['versions'] else 'ABSENT_FROM_RECORD') for v in samples}
    if result != samples:
        raise EvidenceError('OpenSSF version controls disagree')
    return {'tree': tree, 'control_blob': git_object('blob', raw), 'control_record': record['id'],
            'control_versions': result, 'indexed_pypi_names': len(names), 'owned_name_versions': len(fixed),
            'owned_names': len({n for n, _ in fixed}), 'name_overlaps_requiring_review': overlaps,
            'owned_pairs_sha256': sha(canonical(sorted(fixed)))}


def bandit(checkout, kit):
    from .product_notices import read_wheel
    repo = checkout/'upstream/104-bandit'
    if git(repo, 'rev-parse', 'HEAD').decode().strip() != BANDIT:
        raise EvidenceError('Bandit checkout revision differs')
    filename = 'bandit-1.9.4-py3-none-any.whl'
    wheel = read_wheel(kit/filename)
    if sha(wheel) != 'f89ffa663767f5a0585ea075f01020207e966a9c0f2b9ef56a57c7963a3f6f8e':
        raise EvidenceError('Bandit distribution differs')
    with ZipFile(BytesIO(wheel)) as archive:
        files = {n: git_object('blob', archive.read(n)) for n in archive.namelist()
                 if n.startswith('bandit/') and n.endswith('.py')}
    tracked = git(repo, 'ls-tree', '-rz', BANDIT, '--', 'bandit')
    tree_files = {}
    for row in tracked.split(b'\0'):
        if row:
            meta, name = row.split(b'\t', 1)
            if name.endswith(b'.py'):
                tree_files[name.decode()] = meta.split()[2].decode()
    if not files or files != tree_files:
        raise EvidenceError('Bandit runtime Python files differ from catalog revision')
    source = pinned(ROOT, SCOPE, SCOPE_SHA).decode()
    target = 'yaml.safe_load(fh)'
    if source.count(target) != 1:
        raise EvidenceError('expected owned loader call')
    samples = {'original.py': source, 'explicit.py': source.replace(target, 'yaml.load(fh, Loader=yaml.SafeLoader)'),
               'changed.py': source.replace(target, 'yaml.load(fh)')}
    with tempfile.TemporaryDirectory(prefix='nqc-bandit-') as tmp:
        work = Path(tmp)
        env = {'HOME': tmp, 'TMPDIR': tmp, 'PATH': '/usr/bin:/bin'}
        install_wheels(kit, work, env, lock_path=LOCK, lock_digest=LOCK_SHA, producer='Bandit')
        for name, text in samples.items():
            (work/name).write_text(text)
        command = "import sys;sys.path.insert(0,'lib');from bandit.cli.main import main;main()"
        proc = subprocess.run([*ISOLATE, sys.executable, '-I', '-B', '-S', '-c', command, '-q', '-t', 'B506',
                               '--format', 'json', '--exit-zero', *sorted(samples)], cwd=work, env=env,
                              capture_output=True, check=True, timeout=45)
    report = strict_json(proc.stdout)
    if report['errors'] or {Path(n).name for n in report['metrics'] if n != '_totals'} != samples.keys():
        raise EvidenceError('Bandit skipped an owned source')
    issues = report['results']
    if len(issues) != 1 or issues[0]['test_id'] != 'B506' or Path(issues[0]['filename']).name != 'changed.py':
        raise EvidenceError('Bandit control outcomes differ')
    issue = issues[0]
    lineno, = [node.lineno for node in ast.walk(ast.parse(samples['changed.py']))
               if isinstance(node, ast.Call) and ast.unparse(node.func) == 'yaml.load']
    if issue['line_number'] != lineno:
        raise EvidenceError('Bandit location differs from Python syntax tree')
    region = smartbugs_region.result_region({'line': issue['line_number'], 'line_end': issue['line_range'][-1],
                                             'column': issue['col_offset']+1, 'column_end': issue['end_col_offset']+1})
    if not region or region['startLine'] != lineno or region['endLine'] != lineno:
        raise EvidenceError('SmartBugs converted an inconsistent source span')
    text = samples['changed.py'].splitlines()[lineno-1]
    if text[region['startColumn']-1:region['endColumn']-1] != 'yaml.load(fh)':
        raise EvidenceError('SARIF location does not identify the controlled call')
    sarif = {'version': '2.1.0', 'runs': [{'tool': {'driver': {'name': 'Bandit', 'version': '1.9.4'}},
             'results': [{'ruleId': 'B506', 'message': {'text': 'Controlled YAML loader declaration'},
                          'locations': [{'physicalLocation': {'artifactLocation': {'uri': 'changed.py'},
                                                              'region': region}}]}]}]}
    return {'release_sha256': sha(wheel), 'python_files_matching_git': len(files), 'wheel_lock_sha256': LOCK_SHA,
            'fixture_sha256': SCOPE_SHA, 'file_sha256': {k: sha(v.encode()) for k, v in samples.items()},
            'outcomes': {k: int(k == 'changed.py') for k in samples}, 'sarif': sarif}


def attach(index, checkout, kit, solkit):
    if not checkout or not solkit or not index.source_references:
        raise EvidenceError('owned source checks require source references and Solidity kit')
    clauses = checked_excerpts(kit)
    reports = {'yaml': bandit(checkout, kit), 'packages': package_lookup(checkout),
               'token_types': token_types(clauses, solkit, index.source_references['openzeppelin/openzeppelin-contracts'])}
    index.owned_source_checks = reports
    for name, section, revision in (
            ('pycqa/bandit', 'yaml', BANDIT), ('smartbugs/smartbugs', 'yaml', 'a246003622775c730d5522429d8fed8846406e17'),
            ('ossf/malicious-packages', 'packages', OPENSSF),
            ('crytic/building-secure-contracts', 'token_types', '0e679905ce336d81b1eade9cfe924011e9073339')):
        index.repos[name]['owned_source_receipt'] = {'query': 'owned-source-checks', 'section': section,
                                                    'revision': revision, 'sha256': sha(canonical(reports[section]))}
