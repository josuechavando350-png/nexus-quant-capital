"""Compile fixed own contracts with Hardhat and validate their storage upgrades."""
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

from .native_compile import PIN as SOLC
from .product_census_header import pinned
from .product_evm_native import NODE_SHA
from .product_notice_ranking import ISOLATE
from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .safe_io import MAX_BYTES, canonical, strict_json

REPOSITORIES = {'NomicFoundation/hardhat': 'executable',
                'OpenZeppelin/openzeppelin-upgrades': 'executable'}
SCOPES = {
    'NomicFoundation/hardhat': 'Compile own local layout variants with pinned solc and reject an invalid Solidity control; compare compiler output with direct solc.',
    'OpenZeppelin/openzeppelin-upgrades': 'Compare compiler-derived layouts of own compatible/incompatible upgrades with all storage safety overrides disabled.',
}
PINS = 'superhunter/product_supply/upgrades-native-npm-pins.json'
PINS_SHA = 'a69db3fc8d376a7eedd74a758cbfcd2e62d4907094f27c108f76dc54478f6bc5'
SOURCE = 'superhunter/product_supply/upgrades-native-owned.txt'
SOURCE_SHA = '04fb8f418025989f5574afee4d2cb561f7fab113825b26450c76aba7cbbd729e'
WORKER = 'superhunter/product_supply/upgrades-native-worker.txt'
WORKER_SHA = 'aa3b525339d7365bf50e0ef091a88b76f96971e295f16ea70d8e394b57422c1e'
SOURCE_NAME = 'project/contracts/Owned.sol'
INVALID_SOURCE = '// SPDX-License-Identifier: MIT\npragma solidity 0.8.30;\ncontract Invalid { uint256 public balance = ; }\n'


def field(label, slot, typ):
    return {'label': label, 'slot': str(slot), 'offset': 0, 'type': typ}


BALANCE = field('balance', 0, 'uint256')
OWNER = field('owner', 1, 'address')
EXPECTED_LAYOUTS = {
    'Base': [BALANCE, OWNER],
    'Append': [BALANCE, OWNER, field('nonce', 2, 'uint256')],
    'Narrow': [field('balance', 0, 'uint128'), OWNER],
    'Reorder': [field('owner', 0, 'address'), field('balance', 1, 'uint256')],
    'Delete': [BALANCE],
    'Rename': [field('funds', 0, 'uint256'), OWNER],
}


def expected_comparisons():
    def operation(kind, before=None, after=None):
        return {'kind': kind, 'original': before, 'updated': after}
    return {
        'Base': {'compatible': True, 'operations': []},
        'Append': {'compatible': True, 'operations': []},
        'Narrow': {'compatible': False, 'operations': [operation('typechange', BALANCE, EXPECTED_LAYOUTS['Narrow'][0])]},
        'Reorder': {'compatible': False, 'operations': [operation('delete', BALANCE),
            operation('layoutchange', OWNER, EXPECTED_LAYOUTS['Reorder'][0]),
            operation('insert', after=EXPECTED_LAYOUTS['Reorder'][1])]},
        'Delete': {'compatible': False, 'operations': [operation('delete', OWNER)]},
        'Rename': {'compatible': False, 'operations': [operation('rename', BALANCE, EXPECTED_LAYOUTS['Rename'][0])]},
    }


def checked_inputs(result):
    try:
        valid, invalid = result['compiled'], result['invalid']
        expected_sources = [{'project/contracts/Owned.sol': {'content': pinned(ROOT, SOURCE, SOURCE_SHA).decode()}},
                            {'project/contracts/Invalid.sol': {'content': INVALID_SOURCE}}]
        for row, sources in zip((valid, invalid), expected_sources):
            compiler_input = row['input']
            settings = compiler_input['settings']
            if (compiler_input['language'] != 'Solidity' or compiler_input['sources'] != sources or
                    settings['evmVersion'] != 'paris' or settings['optimizer'] != {'enabled': False} or
                    settings['metadata'] != {'bytecodeHash': 'none'} or settings['remappings'] != [] or
                    settings['outputSelection']['*'][''] != ['ast'] or
                    not {'abi', 'storageLayout', 'evm.bytecode', 'evm.deployedBytecode'}.issubset(settings['outputSelection']['*']['*'])):
                raise EvidenceError('Hardhat changed owned compilation inputs')
        if valid['status'] != 'BUILD_SUCCESS' or invalid['status'] != 'BUILD_FAILURE':
            raise EvidenceError('Hardhat compilation controls failed')
    except (KeyError, TypeError) as exc:
        raise EvidenceError('incomplete Hardhat build evidence') from exc
    return valid['input'], invalid['input']


def reconcile(result, direct_valid, direct_invalid):
    checked_inputs(result)
    try:
        if result['compiled']['output'] != direct_valid:
            raise EvidenceError('Hardhat compiler output differs from independent direct solc invocation')
        if direct_valid.get('errors') or set(direct_valid['contracts'][SOURCE_NAME]) != set(EXPECTED_LAYOUTS):
            raise EvidenceError('unexpected owned compilation diagnostics or contracts')
        ast = direct_valid['sources'][SOURCE_NAME]['ast']
        if (ast['nodeType'] != 'SourceUnit' or
                {row['name'] for row in ast['nodes'] if row['nodeType'] == 'ContractDefinition'} != set(EXPECTED_LAYOUTS)):
            raise EvidenceError('incomplete compiler AST evidence')
        if set(result['layouts']) != set(EXPECTED_LAYOUTS):
            raise EvidenceError('incomplete OpenZeppelin storage layouts')
        compiler, extracted, runtime = {}, {}, {}
        for name in EXPECTED_LAYOUTS:
            compiled = direct_valid['contracts'][SOURCE_NAME][name]
            output_layout = compiled['storageLayout']
            actual = result['layouts'][name]
            if actual.get('flat') is not True or actual.get('layoutVersion') != '1.2':
                raise EvidenceError('OpenZeppelin did not use detailed compiler layouts')
            def compact(layout):
                return [{'label': row['label'], 'slot': row['slot'], 'offset': row['offset'],
                         'type': layout['types'][row['type']]['label']} for row in layout['storage']]
            compiler[name], extracted[name] = compact(output_layout), compact(actual)
            if compiler[name] != EXPECTED_LAYOUTS[name] or extracted[name] != compiler[name]:
                raise EvidenceError('storage slots or types differ from independent owned expectations')
            code = bytes.fromhex(compiled['evm']['deployedBytecode']['object'])
            if not code:
                raise EvidenceError('missing native compiled runtime')
            runtime[name] = {'bytes': len(code), 'sha256': sha(code)}
        expected_error = [{'type': 'ParserError', 'severity': 'error', 'code': '6933',
                           'message': 'Expected primary expression.'}]
        direct_errors = [{'type': row['type'], 'severity': row['severity'], 'code': row['errorCode'],
                          'message': row['message']} for row in direct_invalid['errors']]
        if (direct_errors != expected_error or result['invalid']['errors'] != expected_error or
                direct_invalid.get('contracts')):
            raise EvidenceError('invalid-source rejection differs from direct solc')
        if result['comparisons'] != expected_comparisons():
            raise EvidenceError('OpenZeppelin upgrade decisions or incompatible operations differ')
        if result['incomplete_inputs'] != {'storage_layout': 'rejected_before_comparison', 'ast': 'rejected_before_comparison'}:
            raise EvidenceError('missing compiler evidence was not rejected')
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidenceError('incomplete native upgrade evidence') from exc
    return {'layouts': compiler, 'upgrade_comparisons': result['comparisons'],
            'incomplete_inputs': result['incomplete_inputs'], 'compiled_runtimes': runtime,
            'hardhat': {'compiled_contracts': len(EXPECTED_LAYOUTS),
                        'direct_solc_output_identical': True, 'invalid_source_errors': direct_errors,
                        'compiler_input_sha256': sha(canonical(result['compiled']['input'])),
                        'compiler_output_sha256': sha(canonical(direct_valid))},
            'owned_source_sha256': SOURCE_SHA, 'worker_sha256': WORKER_SHA,
            'safety_options': {'unsafeSkipStorageCheck': False, 'unsafeAllowRenames': False,
                               'unsafeAllowCustomTypes': False},
            'interpretation': 'Known local controls: unchanged and append-only layouts pass; type narrowing, reordering, deletion and unapproved renaming fail. Storage layout compatibility only; no deployment, initializer, authorization, proxy or complete upgrade-safety claim. Missing compiler layout/AST is rejected before comparison.'}


def stage(kit, work):
    manifest = strict_json(pinned(ROOT, PINS, PINS_SHA))
    for name, digest in [('solc', SOLC['sha256']), ('node', NODE_SHA)]:
        copy_release(name, kit/name, work/name, digest)
    # Extract shorter paths first so nested dependencies get their own directories.
    for index, row in enumerate(sorted(manifest['packages'], key=lambda row: (len(Path(row['path']).parts), row['path']))):
        archive = work/f'package-{index}.tgz'
        copy_release(row['path'], kit/row['filename'], archive, row['sha256'], executable=False)
        unpacked = work/f'extract-{index}'
        unpacked.mkdir()
        with tarfile.open(archive, 'r:gz') as package:
            package.extractall(unpacked, filter='data')
        destination = work/row['path']
        destination.parent.mkdir(parents=True, exist_ok=True)
        (unpacked/row['archive_prefix']).rename(destination)
    for group in manifest['source_comparisons'].values():
        for row in group['files']:
            if sha((work/group['package_path']/row['path']).read_bytes()) != row['package_sha256']:
                raise EvidenceError('packaged TypeScript source differs from provenance comparison')
    (work/'worker.mjs').write_bytes(pinned(ROOT, WORKER, WORKER_SHA))
    (work/'Owned.sol').write_bytes(pinned(ROOT, SOURCE, SOURCE_SHA))
    (work/'package.json').write_text('{"type":"module","private":true}\n')
    return manifest


def run(kit):
    with tempfile.TemporaryDirectory(prefix='nqc-upgrade-layout-') as tmp:
        work = Path(tmp)
        manifest = stage(Path(kit), work)
        env = {'HOME': tmp, 'TMPDIR': tmp, 'PATH': str(work)+':/usr/bin:/bin', 'LC_ALL': 'C',
               'XDG_CACHE_HOME': tmp, 'XDG_CONFIG_HOME': tmp, 'HARDHAT_DISABLE_TELEMETRY_PROMPT': 'true'}
        def execute(command, payload=None):
            proc = subprocess.run([*ISOLATE, *command], input=None if payload is None else canonical(payload),
                cwd=work, env=env, capture_output=True, timeout=120)
            if proc.returncode or proc.stderr or len(proc.stdout) > MAX_BYTES:
                error = EvidenceError('native owned upgrade process failed')
                error.stderr, error.returncode = proc.stderr[:MAX_BYTES], proc.returncode
                raise error
            return strict_json(proc.stdout)
        observed = execute([sys.executable, '-I', '-B', '-S',
                            Path(__file__).with_name('product_upgrade_layout_native_worker.py')])
        valid_input, invalid_input = checked_inputs(observed)
        direct_valid = execute([work/'solc', '--no-import-callback', '--standard-json'], valid_input)
        direct_invalid = execute([work/'solc', '--no-import-callback', '--standard-json'], invalid_input)
        report = reconcile(observed, direct_valid, direct_invalid)
    tools = {}
    for repo, group in manifest['source_comparisons'].items():
        matches = [r for r in group['files'] if r['package_sha256'] == r['catalog_sha256']]
        differences = [r for r in group['files'] if r not in matches]
        tools[repo] = {'catalog_revision': group['catalog_revision'], 'version': group['version'],
                      'scope': SCOPES[repo], 'executed_form': 'official npm distribution',
                      'package_sha256': next(row['sha256'] for row in manifest['packages'] if row['path'] == group['package_path']),
                      'typescript_sources_matching_catalog': len(matches),
                      'typescript_source_differences': differences,
                      'distribution_rebuilt_from_catalog_revision': False}
    report.update({'tools': tools, 'npm_pins_sha256': PINS_SHA, 'pinned_npm_packages': len(manifest['packages']),
                   'solc_sha256': SOLC['sha256'], 'node_sha256': NODE_SHA})
    return report
