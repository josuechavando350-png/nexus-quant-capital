"""Local SuperHunter toolkit for the NQC T36 regression suite and pinned manuals."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from .product_sources import checked_out, git, gitlinks, toolkit_sources
from .toolkit_reports import FORMATS, count_labels, read_reports, summarize

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = 'ci/nqc-t36/contracts'
TARGET = 'src/NqcFlashFundingExecutor.sol'
PROPERTY = 'test/OperatorProperty.sol'
TESTS = 'test/NqcFlashFundingExecutor.t.sol'


def source_index(root):
    links = gitlinks(root)
    result = []
    for tool in toolkit_sources():
        if links.get(tool['path']) != tool['commit']:
            raise ValueError('unexpected product pin: ' + tool['repository'])
        result.append(checked_out(root, tool))
    return result


def document(root, tool, path):
    return git(root / tool['path'], 'show', tool['commit'] + ':' + path).decode()


def reference(root, tools, terms):
    matches = []
    for tool in tools:
        lines = document(root, tool, tool['document']).splitlines()
        url = f'https://github.com/{tool["repository"]}/blob/{tool["commit"]}/{tool["document"]}'
        result = {'repository': tool['repository'], 'document': url, 'lines': len(lines)}
        if terms:
            result['matches'] = [
                {'line': number, 'text': line.strip()[:240]} for number, line in enumerate(lines, 1)
                if all(term.casefold() in line.casefold() for term in terms)
            ][:8]
        if terms and tool['repository'] == 'solodit/solodit_content':
            files = git(root / tool['path'], 'ls-tree', '-rz', '--name-only', tool['commit'], '--', 'reports')
            titles = [item.decode() for item in files.split(b'\0') if item.endswith(b'.md')]
            result['report_paths'] = [path for path in titles if all(term.casefold() in path.casefold()
                                                                    for term in terms)][:25]
        matches.append(result)
    return matches


def command(args, work, **kwargs):
    return subprocess.run(args, cwd=work, text=True, capture_output=True, timeout=120, **kwargs)


def checked(args, work, **kwargs):
    run = command(args, work, **kwargs)
    if run.returncode:
        raise ValueError(f'{Path(args[0]).name} exited {run.returncode}: ' + (run.stderr or run.stdout)[-900:])
    return run.stdout


def prepare(work, tools):
    for relative in (TARGET, TESTS, 'foundry.toml'):
        path = work / relative
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(git(ROOT, 'show', f'HEAD:{CONTRACTS}/{relative}'))
    (work / PROPERTY).write_bytes((ROOT / 'superhunter/toolkit_operator.sol').read_bytes())
    (work / 'test/PropertiesAsserts.sol').write_text(document(ROOT, tools['crytic/properties'],
                                                               'contracts/util/PropertiesAsserts.sol'))


def forge_tests(work, solc, *filters):
    output = command(['forge', 'test', '--root', '.', '--offline', '--use', solc, *filters, '--json'], work)
    if not output.stdout.strip():
        raise ValueError('Forge produced no test results: ' + output.stderr[-500:])
    suites = json.loads(output.stdout)
    tests = {suite + '/' + name: record['status'] for suite, data in suites.items()
             for name, record in data['test_results'].items()}
    if not tests or any(status not in ('Success', 'Failure') for status in tests.values()):
        raise ValueError('incomplete Forge results')
    if bool(output.returncode) != any(status == 'Failure' for status in tests.values()):
        raise ValueError('Forge exit code disagrees with test results')
    return tests


def prove_leg_bound(work, solc, source, ast):
    """Prove the extracted T36 plan guard admits one to four legs."""
    contract = next(node for node in ast['nodes'] if node.get('name') == 'NqcFlashFundingExecutor')
    nodes = contract['nodes']
    constant = next(node for node in nodes if node.get('name') == 'MAX_LEGS' and node.get('constant'))
    validate = next(node for node in nodes if node.get('name') == '_validatePlan')
    statements = validate['body']['statements']
    guard = next(node for node in statements if node['nodeType'] == 'IfStatement'
                 and node['trueBody'].get('errorCall', {}).get('expression', {}).get('name') == 'InvalidLegCount')

    def snippet(node):
        start, length, _ = map(int, node['src'].split(':'))
        return source.encode()[start:start + length].decode()

    model = ('// SPDX-License-Identifier: MIT\npragma solidity ^0.8.24;\ncontract LegBound {\n'
             + snippet(constant).rstrip(';') + ';\nfunction check(uint256 length) external pure {\n'
             + 'if (' + snippet(guard['condition']) + ') return;\nassert(length >= 1 && length <= 4);\n}}')
    settings = {'engine': 'chc', 'solvers': ['z3'], 'targets': ['assert'], 'showProvedSafe': True,
                'showUnproved': True, 'timeout': 5000}
    request = {'language': 'Solidity', 'sources': {'LegBound.sol': {'content': model}},
               'settings': {'modelChecker': settings, 'outputSelection': {'*': {'*': ['abi']}}}}
    result = json.loads(checked([solc, '--standard-json'], work, input=json.dumps(request)))
    messages = result.get('errors', [])
    proved = [entry for entry in messages if entry['severity'] == 'info'
              and 'Assertion violation check is safe!' in entry['message']]
    if len(proved) != 1 or any(entry['severity'] in ('error', 'warning') for entry in messages):
        raise ValueError('SMTChecker did not prove the extracted T36 length guard with Z3')
    return {'property': 'Every admitted plan length is between 1 and 4', 'guard': snippet(guard['condition']),
            'constant': snippet(constant), 'engine': 'CHC/Z3'}


def native_review(work, tools):
    solc = shutil.which('solc')
    if not solc:
        raise ValueError('solc 0.8.24 is required')
    version = checked([solc, '--version'], work)
    if 'Version: 0.8.24+' not in version:
        raise ValueError('the T36 suite requires solc 0.8.24')
    source = (work / TARGET).read_text()
    standard = {'language': 'Solidity', 'sources': {TARGET: {'content': source}},
                'settings': {'optimizer': {'enabled': True, 'runs': 1000000}, 'evmVersion': 'cancun',
                             'metadata': {'appendCBOR': False, 'bytecodeHash': 'none'},
                             'outputSelection': {'*': {'': ['ast'], '*': ['abi', 'evm.methodIdentifiers',
                              'evm.deployedBytecode.object', 'evm.deployedBytecode.sourceMap']}}}}
    compiled = json.loads(checked([solc, '--standard-json'], work, input=json.dumps(standard)))
    if any(row['severity'] == 'error' for row in compiled.get('errors', [])):
        raise ValueError('solc rejected T36')
    ast = compiled['sources'][TARGET]['ast']
    (work / 'input.json').write_text(json.dumps([{'name': TARGET, 'content': source, 'ast': ast}]))
    contract = compiled['contracts'][TARGET]['NqcFlashFundingExecutor']
    (work / 'joined-input.json').write_text(json.dumps({'contract': contract, 'ast': ast}))
    four = ROOT / tools['Picodes/4naly3er']['path']
    deps = Path(os.environ.get('SUPERHUNTER_4NALY3ER_MODULES', four / 'node_modules')).resolve()
    if not (deps / 'ts-node/register/transpile-only.js').is_file():
        raise ValueError('install the pinned 4naly3er JavaScript dependencies')
    env = {**os.environ, 'TS_NODE_PROJECT': str(deps / 'ts-node/node16/tsconfig.json'), 'NODE_PATH': str(deps),
           'TS_NODE_SKIP_IGNORE': 'true'}
    report = checked(['node', '-r', 'ts-node/register/transpile-only',
                      str(ROOT / 'superhunter/toolkit_4naly3er.cjs'), str(four), 'input.json'], work, env=env)
    tests = forge_tests(work, solc)
    if not all(status == 'Success' for status in tests.values()):
        raise ValueError('baseline Forge tests failed')
    return {'compiler': version.splitlines()[-1], 'forge': tests,
            'smtchecker': prove_leg_bound(work, solc, source, ast),
            'static_report': report, 'static_rule_groups': len(re.findall(r'^### <a name=', report, re.M))}


def property_test(work):
    checked(['medusa', 'init', 'solc', '--compilation-target', PROPERTY, '--out', 'medusa.json'], work)
    path = work / 'medusa.json'
    config = json.loads(path.read_text())
    config['slither']['useSlither'] = False
    fuzz = config['fuzzing']
    fuzz.update(targetContracts=['OperatorProperty'], testLimit=64, callSequenceLength=4, workers=1)
    fuzz['testing']['assertionTesting']['enabled'] = False
    fuzz['testing']['optimizationTesting']['enabled'] = False
    path.write_text(json.dumps(config))
    log = checked(['medusa', 'fuzz', '--config', 'medusa.json', '--no-color'], work)
    if '[PASSED] Property Test: OperatorProperty.property_configuredOperator()' not in log:
        raise ValueError('Medusa did not pass the expected property')
    return 'OperatorProperty.property_configuredOperator()'


def echidna_test(work):
    # Foundry project auto-discovery would override crytic-compile's single-file solc mode.
    with tempfile.TemporaryDirectory(prefix='nqc-echidna-') as temp:
        isolated = Path(temp)
        for path in (PROPERTY, TARGET, 'test/PropertiesAsserts.sol'):
            (isolated / path).parent.mkdir(exist_ok=True)
            shutil.copyfile(work / path, isolated / path)
        (isolated / 'echidna.yaml').write_text(
            'prefix: property_\ncryticArgs: ["--compile-force-framework", "solc"]\n')
        log = checked(['echidna', PROPERTY, '--contract', 'OperatorProperty', '--disable-onchain-sources',
                       '--disable-slither', '--format', 'text', '--seed', '1', '--test-limit', '64',
                       '--workers', '1', '--seq-len', '4', '--config', 'echidna.yaml'], isolated)
    if 'property_configuredOperator: passing' not in log or 'Total calls: 64' not in log:
        raise ValueError('Echidna did not finish the expected bounded property run')
    return {'property': 'property_configuredOperator', 'calls': 64, 'seed': 1}


def mutation_test(work, baseline):
    solc = shutil.which('solc')
    checked(['gambit', 'mutate', '-f', TARGET, '--functions', '_validatePlan', '--solc', solc,
             '--seed', '1', '-n', '1', '-o', 'variants'], work)
    mutants = json.loads((work / 'variants/gambit_results.json').read_text())
    if len(mutants) != 1 or mutants[0]['original'] != TARGET:
        raise ValueError('Gambit did not produce the expected T36 mutation')
    target = work / TARGET
    variant = work / 'variants/mutants/1' / TARGET
    if target.read_bytes() == variant.read_bytes():
        raise ValueError('mutation did not change the source')
    shutil.copyfile(variant, target)
    tested = forge_tests(work, solc)
    if tested.keys() != baseline.keys():
        raise ValueError('mutation and baseline suites differ')
    failures = [test for test, status in tested.items() if status == 'Failure']
    return {'generated': 1, 'detected': bool(failures), 'failing_tests': failures}


def installed_static_checks(work, runtime):
    results = {}
    with tempfile.TemporaryDirectory(prefix='nqc-static-') as temp:
        project = Path(temp)
        name = Path(TARGET).name
        shutil.copyfile(work / TARGET, project / name)
        native = runtime / 'static' if runtime else None
        slither = native / 'venv/bin/slither' if native and native.is_dir() else shutil.which('slither')
        semgrep = native / 'semgrep/osemgrep' if native and native.is_dir() else shutil.which('semgrep')
        env = os.environ.copy()
        env.pop('PYTHONPATH', None)
        if slither:
            detectors = json.loads(checked([slither, '--list-detectors-json'], project, env=env))
            names = sorted(row['check'] for row in detectors)
            if not names or len(names) != len(set(names)):
                raise ValueError('Slither did not return a distinct detector registry')
            completed = command([slither, name, '--solc', shutil.which('solc'), '--detect', ','.join(names),
                                 '--fail-none', '--json', 'slither.json'], project, env=env)
            report = project / 'slither.json'
            if (completed.returncode or not report.is_file() or 'Traceback' in completed.stderr
                    or f'with {len(names)} detectors)' not in completed.stderr):
                raise ValueError('Slither failed to complete its detector registry: ' + completed.stderr[-600:])
            if report.stat().st_size > 16 * 1024 * 1024:
                raise ValueError('T36 native Slither report exceeds 16 MiB')
            data = json.loads(report.read_bytes())
            if data.get('success') is not True:
                raise ValueError('Slither reported an unsuccessful execution')
            findings = count_labels(data['results'].get('detectors', []), 'check')
            for scanner, plugin in [('slither', False), ('slitherin', True)]:
                selected = [n for n in names if n.startswith('pess-') == plugin]
                if selected:
                    results[scanner] = {'detectors_run': len(selected),
                                        'detectors': {k: v for k, v in findings.items() if k in selected}}
        if semgrep:
            config = {'rules': [{'id': 'nqc-token-call-review', 'languages': ['solidity'],
                                 'message': 'Review return handling at this low-level token call',
                                 'severity': 'INFO', 'pattern': '$TOKEN.call(...)'}]}
            (project / 'semgrep.json').write_text(json.dumps(config))
            flags = ['--experimental'] if Path(semgrep).name == 'osemgrep' else []
            raw = checked([semgrep, 'scan', *flags, '--config', 'semgrep.json', '--metrics=off',
                           '--no-git-ignore', '--json', name], project, env=env)
            data = json.loads(raw)
            if data['paths']['scanned'] != [name] or data['errors']:
                raise ValueError('Semgrep did not complete the T36 source')
            source = (work / TARGET).read_bytes()
            compiled = json.loads((work / 'joined-input.json').read_bytes())['ast']
            pending = [compiled]
            lines = []
            while pending:
                item = pending.pop()
                if isinstance(item, dict):
                    pending.extend(item.values())
                    if (item.get('nodeType') == 'MemberAccess' and item.get('memberName') == 'call'
                            and item['expression'].get('name') == 'token'):
                        offset = int(item['src'].split(':', 1)[0])
                        lines.append(source.count(b'\n', 0, offset) + 1)
                elif isinstance(item, list):
                    pending.extend(item)
            matched = sorted(row['start']['line'] for row in data['results'])
            if not lines or sorted(lines) != matched:
                raise ValueError('Semgrep locations differ from token.call locations in the solc AST')
            results['semgrep'] = {**summarize('semgrep', raw.encode()), 'scanned': name,
                                  'verified_lines': matched, 'version': data['version']}
        aderyn = shutil.which('aderyn')
        if aderyn:
            version = checked([aderyn, '--version'], project).strip()
            if version.lower() != 'aderyn 0.6.8':
                raise ValueError('T36 requires the reviewed Aderyn 0.6.8 CLI')
            owned = project / 'aderyn-project'
            (owned / 'src').mkdir(parents=True)
            shutil.copyfile(work / TARGET, owned / 'src' / name)
            (owned / 'foundry.toml').write_text('[profile.default]\nsrc = "src"\nsolc_version = "0.8.24"\noffline = true\n')
            home = project / 'home'
            svm = home / '.svm/0.8.24'
            svm.mkdir(parents=True)
            (svm / 'solc-0.8.24').symlink_to(shutil.which('solc'))
            checked([aderyn, '.', '--skip-update-check', '--output', 'aderyn.json'], owned,
                    env={**env, 'HOME': str(home), 'XDG_DATA_HOME': str(home / '.local/share')})
            raw = (owned / 'aderyn.json').read_bytes()
            report = json.loads(raw)
            files = report['files_details']['files_details']
            if (report['files_summary']['total_source_units'] != 1 or len(files) != 1
                    or Path(files[0]['file_path']).name != name or not report['detectors_used']):
                raise ValueError('Aderyn did not report its detector run on T36')
            results['aderyn'] = {**summarize('aderyn', raw), 'scanned': name, 'version': version,
                                 'detectors_run': len(report['detectors_used'])}
    return results


def collect_session(folder):
    from .toolkit_product import product_session
    tools = {row['repository']: row for row in source_index(ROOT)}
    with tempfile.TemporaryDirectory(prefix='nqc-toolkit-') as tmp:
        work = Path(tmp)
        prepare(work, tools)
        result = native_review(work, tools)
        result['medusa_property'] = property_test(work)
        result['echidna'] = echidna_test(work)
        result['installed_static_checks'] = installed_static_checks(work, folder)
        result['mutation'] = mutation_test(work, result['forge'])
        # The mutation belongs only to the regression check.
        (work / TARGET).write_bytes(git(ROOT, 'show', f'HEAD:{CONTRACTS}/{TARGET}'))
        if folder:
            result['product_session'] = product_session(ROOT, tools, result, work, folder, checked)
    result['static_tools_unavailable'] = sorted({'slither', 'slitherin', 'semgrep', 'aderyn'}
                                                - result['installed_static_checks'].keys())
    result.update(target=CONTRACTS + '/' + TARGET, references=reference(ROOT, tools.values(), []),
                  executable_tools=['solc', '4naly3er', 'forge', 'medusa', 'echidna', 'gambit',
                                    *(['nuclei'] if folder else []),
                                    *result['installed_static_checks']],
                  solidity_test_library='crytic/properties')
    return result


def run_session(runtime, reports):
    imported = read_reports(reports)
    if runtime is None:
        installed = shutil.which('aderyn-lines')
        runtime = Path(installed).parent if installed else None
    if runtime is None:
        result = collect_session(None)
    else:
        folder = runtime.resolve(strict=True)
        for name in ('forge', 'solc', 'medusa', 'echidna', 'gambit', 'nuclei',
                     'ityfuzz-opcodes', 'aderyn-lines', 'semgrep-solidity.so', 'venv/bin/python'):
            if not (folder / name).is_file():
                raise ValueError('missing toolkit component: ' + name + '. Run toolkit setup in a new directory.')
        env = {**os.environ,
               'PATH': os.pathsep.join([str(folder / 'venv/bin'), str(folder), os.environ['PATH']]),
               'LD_LIBRARY_PATH': os.pathsep.join(filter(None, [str(folder), os.environ.get('LD_LIBRARY_PATH')])),
               'PYTHONPATH': os.pathsep.join([str(folder / 'cbor2'), str(folder / 'select')]),
               'SUPERHUNTER_4NALY3ER_MODULES': str(folder / 'js/node_modules')}
        job = subprocess.run([sys.executable, '-B', '-m', 'superhunter.toolkit', str(folder)], cwd=ROOT,
                             env=env, text=True, capture_output=True, timeout=900)
        if job.returncode:
            raise ValueError('T36 session failed: ' + job.stderr.strip()[-900:])
        result = json.loads(job.stdout)
    result['imported_reports'] = imported
    return result


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    if argv and argv[0] == 'setup':
        from .toolkit_setup import main as setup
        return setup(argv[1:])
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('setup', help='prepare the Linux runtime')
    benchmark = commands.add_parser('benchmark-canto', help='read the measured offline LendingLedger comparison')
    benchmark.add_argument('--capture', type=Path, help='verify the original report ZIP against the recorded hashes')
    commands.add_parser('references').add_argument('terms', nargs='*')
    check = commands.add_parser('check', help='run the local T36 regression suite')
    check.add_argument('--require-all-analyzers', action='store_true',
                       help='return a failure status when a native T36 analyzer is unavailable')
    check.add_argument('--runtime', type=Path, help='directory created by toolkit setup')
    reports = commands.add_parser('reports', help='summarize existing native reports offline')
    for subcommand in (check, reports):
        subcommand.add_argument('--report', nargs=2, metavar=('TOOL', 'FILE'), action='append',
                                required=subcommand is reports, default=[], help=', '.join(FORMATS))
    args = parser.parse_args(argv)
    try:
        if args.action == 'benchmark-canto':
            from .toolkit_reports import canto_comparison
            print(json.dumps(canto_comparison(ROOT, args.capture), ensure_ascii=False))
            return 0
        if args.action == 'reports':
            print(json.dumps({'imported_reports': read_reports(args.report)}, ensure_ascii=False))
            return 0
        if args.action == 'references':
            result = {'references': reference(ROOT, source_index(ROOT), args.terms)}
        else:
            result = run_session(args.runtime, args.report)
        print(json.dumps(result, ensure_ascii=False))
        if args.action == 'check' and args.require_all_analyzers and result['static_tools_unavailable']:
            return 2
        return 0
    except (OSError, KeyError, ValueError, subprocess.SubprocessError, StopIteration) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    # The parent supplies a private environment to the fixed-subject worker.
    folder, = sys.argv[1:]
    try:
        print(json.dumps(collect_session(Path(folder).resolve(strict=True))))
    except (OSError, KeyError, ValueError, subprocess.SubprocessError, StopIteration) as exc:
        sys.exit(str(exc))
