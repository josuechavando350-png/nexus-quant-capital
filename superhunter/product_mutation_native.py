"""Measure strong and deliberately weak tests with native Mewt-generated arithmetic mutants."""
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .safe_io import canonical, read_artifact, strict_json

REPOSITORIES = {'trailofbits/mewt': 'executable'}
PINS = 'superhunter/product_supply/mutation-native-pins.json'
PINS_SHA = 'fe0d4370567bb0ee3b5b2f718735abc78a320cc51cf76a28f03389b98a734dd8'
CASES = 'superhunter/product_supply/mutation-native-owned.json'
WORKER = 'superhunter/product_mutation_native_worker.py'
ISOLATE = ('unshare', '--user', '--map-current-user', '--net')


def inputs():
    raw = read_artifact(ROOT, PINS)
    if sha(raw) != PINS_SHA:
        raise EvidenceError('mutation producer pins differ from reviewed artifacts')
    pins = strict_json(raw)
    cases = read_artifact(ROOT, CASES)
    worker = read_artifact(ROOT, WORKER)
    if sha(cases) != pins['cases_sha256'] or sha(worker) != pins['worker_sha256']:
        raise EvidenceError('owned mutation controls or runner differ')
    return pins, strict_json(cases), worker


def worker_result(raw, source, expected_exit):
    record = strict_json(raw.strip())
    wanted = {'compiled': True, 'exit_code': expected_exit, 'source_sha256': sha(source)}
    if (record != wanted or type(record.get('compiled')) is not bool or
            type(record.get('exit_code')) is not int):
        raise EvidenceError('mutation test did not prove successful compilation and its checked exit')
    return record


def normalized_campaign(report, source, target_path, profile):
    """Bind every generated mutation and test result to the original OWNED bytes."""
    if profile not in ('strong', 'weak') or not isinstance(report, dict) or set(report) != {'results'}:
        raise EvidenceError('unknown mutation profile or output envelope')
    results = report['results']
    if not isinstance(results, list) or len(results) != 4:
        raise EvidenceError('native mutation campaign did not test all four arithmetic replacements')
    offset = source.index(b'+')
    line = source[:offset].count(b'\n')
    rows, ids, operators = [], set(), set()
    for record in results:
        mutant, target, outcome = (record[k] for k in ('mutant', 'target', 'outcome'))
        operator = mutant['new_text']
        if (set(record) != {'mutant', 'target', 'outcome'} or
                set(mutant) != {'id', 'target_id', 'mutation_slug', 'byte_offset', 'line_offset', 'old_text', 'new_text'} or
                set(target) != {'id', 'path', 'file_hash', 'language'} or
                set(outcome) != {'mutant_id', 'status', 'output', 'time', 'duration_ms'} or
                type(mutant['id']) is not int or mutant['id'] <= 0 or mutant['id'] in ids or
                type(target['id']) is not int or target['id'] != 1 or mutant['target_id'] != target['id'] or
                (mutant['mutation_slug'], mutant['byte_offset'], mutant['line_offset'], mutant['old_text']) !=
                ('AOS', offset, line, '+') or operator not in ('-', '*', '/', '%') or operator in operators or
                target['file_hash'] != sha(source) or target['language'] != 'cpp' or
                target['path'] != Path(target_path).name or outcome['mutant_id'] != mutant['id'] or
                type(outcome['duration_ms']) is not int or not 0 <= outcome['duration_ms'] <= 5000 or
                type(outcome['time']) is not str or not outcome['time'] or len(outcome['time']) > 64):
            raise EvidenceError('native mutation identity, location, source, or runtime differs')
        ids.add(mutant['id'])
        operators.add(operator)
        mutated = source[:offset] + operator.encode() + source[offset+1:]
        survived = profile == 'weak' and operator == '*'
        expected_status = 'Uncaught' if survived else 'TestFail'
        if outcome['status'] != expected_status:
            raise EvidenceError('strong/weak mutation control differs or was skipped/timed out')
        output = outcome['output'].encode()
        prefix, suffix = b'STDOUT:\n', b'\n\nSTDERR:\n'
        if not output.startswith(prefix) or not output.endswith(suffix):
            raise EvidenceError('mutation worker output has diagnostics or an unexpected native envelope')
        checked = worker_result(output[len(prefix):-len(suffix)], mutated, 0 if survived else 1)
        rows.append({'operator': operator, 'byte_offset': offset, 'line': line+1,
                     'source_sha256': checked['source_sha256'], 'status': outcome['status'],
                     'compiled': True, 'assertion_exit': checked['exit_code']})
    if operators != {'-', '*', '/', '%'}:
        raise EvidenceError('mutation replacement set differs')
    rows.sort(key=lambda r: r['operator'])
    survivors = [r['operator'] for r in rows if r['status'] == 'Uncaught']
    return {'generated': len(rows), 'killed': len(rows)-len(survivors), 'survivors': survivors,
            'compilation_failures': 0, 'timeouts': 0, 'skipped': 0, 'mutants': rows}


def run(kit):
    """Run only these fixed controls; no target, command, network, or source parameter is accepted."""
    kit = Path(kit)
    pins, cases, worker = inputs()
    loader = pins['host_loader']
    if sha(Path(loader['path']).read_bytes()) != loader['sha256']:
        raise EvidenceError('mutation host ELF loader differs from the reviewed runtime')
    with tempfile.TemporaryDirectory(prefix='nqc-mutation-native-') as tmp:
        root = Path(tmp)
        for name, artifact in pins['files'].items():
            destination = root/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            copy_release(name, kit/name, destination, artifact['sha256'], limit=artifact['bytes'],
                         executable=artifact['executable'])
        (root/'runner.py').write_bytes(worker)
        env = {'HOME': tmp, 'XDG_CONFIG_HOME': tmp, 'PATH': str(root/'bin')+':/usr/bin:/bin',
               'LD_LIBRARY_PATH': str(root/'lib'), 'LC_ALL': 'C', 'TMPDIR': tmp,
               'PYTHONDONTWRITEBYTECODE': '1', 'TOKIO_WORKER_THREADS': '2'}
        source = cases['source'].encode()
        results, baselines = {}, {}

        def execute(args, cwd, expected=0, timeout=45):
            result = subprocess.run([*ISOLATE, *map(str, args)], cwd=cwd, env=env,
                                    stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
            if result.returncode != expected or len(result.stdout) > 200_000 or len(result.stderr) > 200_000:
                raise EvidenceError('bounded owned mutation producer failed')
            return result

        for profile in ('strong', 'weak'):
            work = root/profile
            work.mkdir()
            (work/'arithmetic.cpp').write_bytes(source)
            (work/'assertions.c').write_text(cases['assertions'][profile])
            command = [sys.executable, '-I', '-B', root/'runner.py']
            baseline = execute(command, work)
            if baseline.stderr:
                raise EvidenceError('owned mutation baseline emitted diagnostics')
            baselines[profile] = worker_result(baseline.stdout, source, 0)
            config = 'db = "campaign.sqlite"\n[log]\nlevel = "error"\ncolor = false\n'
            (work/'mewt.toml').write_text(config)
            execute([root/'mewt', '--config', work/'mewt.toml', 'run', 'arithmetic.cpp',
                     '--mutations', 'AOS', '--comprehensive', '--test.timeout', '5',
                     '--test.cmd', shlex.join(map(str, command))], work)
            native = execute([root/'mewt', '--config', work/'mewt.toml', 'results', '--all', '--format', 'json'], work)
            if native.stderr or (work/'arithmetic.cpp').read_bytes() != source:
                raise EvidenceError('native mutation campaign did not restore the OWNED source')
            result = normalized_campaign(strict_json(native.stdout), source, work/'arithmetic.cpp', profile)
            offset = source.index(b'+')
            for mutant in result['mutants']:
                changed = source[:offset] + mutant['operator'].encode() + source[offset+1:]
                (work/'arithmetic.cpp').write_bytes(changed)
                replay = execute(command, work, expected=mutant['assertion_exit'])
                if replay.stderr:
                    raise EvidenceError('independent owned mutant replay emitted diagnostics')
                worker_result(replay.stdout, changed, mutant['assertion_exit'])
            (work/'arithmetic.cpp').write_bytes(source)
            result['direct_replays_matched'] = len(result['mutants'])
            results[profile] = result
    return {'schema_version': 1, 'query': 'mutation-native', 'repository': pins['repository'],
            'revision': pins['revision'], 'version': pins['version'], 'producer_kind': pins['producer_kind'],
            'producer_sha256': pins['files']['mewt']['sha256'], 'pins_sha256': PINS_SHA,
            'cases_sha256': pins['cases_sha256'], 'baselines': baselines, 'campaigns': results,
            'scope': 'fixed OWNED arithmetic; four C++ grammar mutations compiled as freestanding C11',
            'limitations': ['one function and arithmetic replacement family',
                           'direct replay uses the same pinned C compiler, not an independent compiler or host',
                           'no test-strength score extrapolation to other applications'],
            'original_vulnerabilities_confirmed': 0}
