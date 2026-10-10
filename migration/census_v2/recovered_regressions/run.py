#!/usr/bin/env python3
"""Replay the four remaining original suites with authenticated real archives.

This runner is offline and never rewrites imported source or issued evidence.
Historical assertions retain their original scope and are not new authority.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
V2 = HERE.parent
REPO = V2.parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(V2))
from replay_historical_regressions import (
    blob, canonical, catalog_compatibility, create_copy, metadata_identity, need, sha,
)

BASE = 'd03333d5a4c8c503afc06ad295c8292afaaa3ba0'
CATALOG = 'ci/nqc-census/rmc011-capital-source-universe.json'
SUITES = (
    'rmc011_four_native_original_source_join',
    'rmc011_independent_seven_bounded_rejections',
    'rmc011_independent_thirteen_source_pins',
    'rmc011_independent_discovery_admission',
)
FILES = tuple('ci/nqc-census/' + prefix + name + '.py'
              for name in SUITES for prefix in ('', 'test_')) + (
    CATALOG,
    'ci/nqc-census/rmc011-external-capital-provider-registry.json',
    'ci/nqc-census/rmc011-execution-plan-requirement-catalog.json',
    'ci/nqc-census/final-census-authority-lock.json',
    'ci/nqc-census/capital-census-scope.json',
    'ci/nqc-census/rmc011-capital-family-discovery.json',
    'ci/migration/legacy-workflows/nqc-census-capital-terminal-readiness.yml.disabled',
)


def source_files():
    result = {}
    for path in FILES:
        raw = (REPO / path).read_bytes()
        pin = subprocess.check_output(
            ['git', '-C', str(REPO), 'rev-parse', BASE + ':' + path], text=True).strip()
        need(blob(raw) == pin, 'imported source changed: ' + path)
        result[path] = raw
    return result


def verify_inputs():
    missing = V2 / 'evidence/historical-regressions/missing-inputs.json'
    need(blob(missing.read_bytes()) == subprocess.check_output(
        ['git', '-C', str(REPO), 'rev-parse', BASE + ':' + str(missing.relative_to(REPO))],
        text=True).strip(), 'original missing-input pins changed')
    pins = json.loads(missing.read_bytes())['archives']
    need(len(pins) == 5 and len({p['artifact_id'] for p in pins}) == 5,
         'archive population mismatch')
    records = []
    paths = {}
    for p in pins:
        path = HERE / 'inputs' / (str(p['artifact_id']) + '.zip')
        need(path.is_file() and not path.is_symlink(), 'missing/nonregular archive')
        raw = path.read_bytes()
        need(sha(raw) == p['sha256'], 'original archive hash mismatch')
        metadata = [(HERE / 'inputs' / (p['label'] + '.' + k + '.json')).read_bytes()
                    for k in ('run', 'artifact', 'commit')]
        identity = metadata_identity(*metadata, {**p, 'artifact_digest': 'sha256:' + p['sha256']})
        artifact = json.loads(metadata[1])
        need(artifact['size_in_bytes'] == len(raw) and artifact['expired'] is False,
             'archive size or expiry mismatch')
        records.append({**identity, 'label': p['label'], 'sha256': sha(raw), 'bytes': len(raw),
                        'metadata_sha256': {k: sha(v) for k, v in
                                            zip(('run', 'artifact', 'commit'), metadata)}})
        paths[p['label']] = path
    return paths, records


def run(out):
    out = out.resolve()
    need(not out.exists(), 'append-only output directory required')
    need(not out.is_relative_to(REPO) and not REPO.is_relative_to(out),
         'replay must be outside repository')
    originals = source_files()
    archives, refs = verify_inputs()
    current = originals[CATALOG]
    nine = (V2 / 'evidence/historical-regressions/universe-nine.json').read_bytes()
    thirteen = (HERE / 'inputs/universe-thirteen.json').read_bytes()
    compatibility = [catalog_compatibility(raw, pin, current, count)
                     for raw, pin, count in (
                         (nine, 'c1b9f136a13f220af9dceaae50e5caa3105121eb', 9),
                         (thirteen, '9dee5fe5035fad450ede25462728eba26beffb49', 13))]
    catalogs = {'nine': nine, 'thirteen': thirteen, 'current': current}
    out.mkdir(parents=True)
    roots = {key: create_copy(out / key, originals, value) for key, value in catalogs.items()}

    def arguments(label, prefix, suffixes=('zip', 'run', 'artifact')):
        result = []
        for suffix in suffixes:
            file = archives[label] if suffix == 'zip' else HERE / 'inputs' / (label + '.' + suffix + '.json')
            result += ['--' + (prefix + '-' if prefix else '') + suffix, str(file)]
        return result

    pair_args = arguments('d08-native', 'd08') + arguments('native-dual', 'dual')
    seven_args = ['--archive', str(archives['seven']),
                  '--run-meta', str(HERE / 'inputs/seven.run.json'),
                  '--artifact-meta', str(HERE / 'inputs/seven.artifact.json')]
    tasks = [(SUITES[0], 'nine', pair_args), (SUITES[1], 'nine', seven_args),
             (SUITES[2], 'thirteen', arguments('thirteen', 'new') + pair_args),
             (SUITES[3], 'current', arguments('discovery', '', ('zip', 'run', 'artifact', 'commit')))]
    checks = []
    for name, context, args in tasks:
        command = [sys.executable, 'ci/nqc-census/test_' + name + '.py', *args, '-v']
        env = {k: v for k, v in os.environ.items()
               if k not in ('PYTHONPATH', 'PYTHONHOME') and not k.startswith('GITHUB_')}
        env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONHASHSEED='0')
        # Original unit tests already supply fixture producer/run identities.
        # This label completes that fixture; it never asserts an actual workflow.
        fixture_env = ({'GITHUB_WORKFLOW': 'OFFLINE_TEST_FIXTURE_NOT_GITHUB_ACTIONS'}
                       if name == SUITES[0] else {})
        env.update(fixture_env)
        started = datetime.now(timezone.utc).isoformat()
        result = subprocess.run(command, cwd=roots[context], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (out / (name + '.log')).write_bytes(result.stdout)
        log = result.stdout.decode('utf-8')
        counts = re.findall(r'^Ran (\d+) tests? in .+$', log, re.M)
        # The duplicate-ZIP negative test emits a warning before its `ok`.
        # Count unique test headers; require clean process status and bare OK.
        names = re.findall(r'^(test_\S+ \([^\n]+\)) \.\.\.', log, re.M)
        passed = (result.returncode == 0 and len(counts) == 1 and int(counts[0]) > 0
                  and int(counts[0]) == len(names) == len(set(names))
                  and re.search(r'^OK$', log, re.M) is not None)
        checks.append({'suite': name, 'context': context, 'command': command,
                       'status': 'PASS' if passed else 'FAIL', 'exit_code': result.returncode,
                       'fixture_environment_overrides': fixture_env,
                       'tests_passed': len(names), 'reported_counts': counts,
                       'started_at': started, 'finished_at': datetime.now(timezone.utc).isoformat(),
                       'log_sha256': sha(result.stdout), 'log_file': name + '.log'})
        (out / 'partial-checks.json').write_bytes(canonical(checks))
        print(name, checks[-1]['status'], 'tests', len(names), flush=True)
        need(passed, 'historical suite failed; preserve log: ' + name)
    need(source_files() == originals, 'imported source mutated')
    for context, root in roots.items():
        for path, raw in originals.items():
            need((root / path).read_bytes() == (catalogs[context] if path == CATALOG else raw),
                 'fresh-copy source mutated: ' + path)
    report = {
        'schema': 'nqc-four-recovered-historical-regressions-v1',
        'status': 'FOUR_PREVIOUSLY_BLOCKED_SUITES_PASS_NOT_CENSUS_CERTIFICATION',
        'producer_repository': 'josuechavando350-png/nexus-quant-capital',
        'producer_repository_id': 1411047452, 'source_base_commit': BASE,
        'runner_sha256': sha(Path(__file__).read_bytes()), 'archives': refs,
        'source_files': [{'path': p, 'git_blob': blob(raw), 'sha256': sha(raw)}
                         for p, raw in sorted(originals.items())],
        'catalog_compatibility': compatibility, 'checks': checks,
        'tests_passed': sum(c['tests_passed'] for c in checks), 'skips': 0,
        'four_missing_archive_setup_dependencies_resolved': True,
        'original_broad_result_relabelled': False, 'source_modified': False,
        'network_requests_by_runner': 0, 'active_workflows_created': 0,
        'capital_or_economic_admission_changed': False,
        'mxn_2000_policy_changed_or_applied_retroactively': False,
        'independent_certification_issued': False, 'real_market_census_closed': False,
    }
    (out / 'report.json').write_bytes(canonical(report))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    report = run(parser.parse_args().out)
    print(report['status'], 'tests', report['tests_passed'])
