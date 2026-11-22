"""Run native Atheris against a fixed owned parser and independently replay its witness."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from .product_notice_ranking import ISOLATE, install_wheels
from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .safe_io import canonical, read_artifact, strict_json, write_new_bundle

REPOSITORIES = {'google/atheris': 'executable'}
LOCK = 'superhunter/product_supply/python-fuzz-native-linux-py312.txt'
LOCK_SHA = '4e519c8e2b373b9310462ffda61c58a0d3e17d07f6e95d72d9965b6cc1817948'
PROOFS = 'superhunter/product_supply/python-fuzz-native-sources.json'
PROOFS_SHA = 'e2abe4f9ce926af5940c9a6660be12590590ab2f2810a45f495fd73388319ba4'
INPUTS = 'superhunter/product_supply/python-fuzz-native-owned.json'
INPUTS_SHA = '61f0c5f3f043fd90aae2786ed0f38508d4dab96a3a6bd2fec914c73e58498a8d'
WORKER = 'superhunter/product_python_fuzz_native_worker.py'
WORKER_SHA = 'f3e2c09f10e062233716ce9fe9b93b4ca10006d12015cd39448c267d8ba53b27'
VERSION = '3.1.0'
MODES = {
    'discovery': 'buggy_campaign', 'discovered_buggy': 'buggy_replay',
    'discovered_repaired': 'fixed_replay', 'pinned_buggy': 'buggy_replay',
    'pinned_repaired': 'fixed_replay', 'clean': 'clean_buggy', 'repaired_campaign': 'fixed_campaign',
}
NATIVE_MODULES = {
    'atheris.native': 'native.cpython-312-x86_64-linux-gnu.so',
    'atheris.core_with_libfuzzer': 'core_with_libfuzzer.cpython-312-x86_64-linux-gnu.so',
}


def checked(path, digest):
    raw = read_artifact(ROOT, path)
    if sha(raw) != digest:
        raise EvidenceError('Python fuzzing input or producer digest differs: ' + path)
    return raw


def inputs():
    return strict_json(checked(INPUTS, INPUTS_SHA))


def verify_installed(work, proof):
    expected = proof['installed_members']
    actual = {p.relative_to(work/'lib').as_posix() for p in (work/'lib/atheris').rglob('*')
              if p.suffix in ('.py', '.so')}
    actual.update(p.relative_to(work/'lib').as_posix() for p in (work/'lib').glob('*.so'))
    actual.update(p.relative_to(work/'lib').as_posix() for p in (work/'lib').glob('*.py'))
    executable_members = {name for name in expected if name.endswith(('.py', '.so'))}
    if actual != executable_members:
        raise EvidenceError('Python fuzzing installed code membership differs')
    for index, (name, metadata) in enumerate(sorted(expected.items())):
        source = work/'lib'/name
        if name.endswith('.so'):
            staged = work/f'verified-native-{index}'
            copy_release('Atheris native module', source, staged, metadata['sha256'],
                         limit=metadata['bytes'], executable=False)
            if staged.stat().st_size != metadata['bytes']:
                raise EvidenceError('Python fuzzing native module size differs')
            staged.replace(source)
        else:
            raw = read_artifact(work/'lib', name)
            if len(raw) != metadata['bytes'] or sha(raw) != metadata['sha256']:
                raise EvidenceError('Python fuzzing installed source or notice differs')
    return len(executable_members)


def decode_input(value):
    if type(value) is not str or not re.fullmatch(r'(?:[0-9a-f]{2}){0,3}', value):
        raise EvidenceError('Python fuzzing input must be an owned bounded byte string')
    return bytes.fromhex(value)


def witness(value):
    data = decode_input(value)
    if len(data) != 2 or data[1] <= data[0]:
        raise EvidenceError('Python fuzzing counterexample is not an overdraft')
    balance, amount = data
    return {'input_hex': value, 'balance': balance, 'amount': amount,
            'observed_remaining': (balance - amount) % 256, 'expected_remaining': None,
            'property': 'rejected_overdraft_or_exact_debit'}


def validate_case(native, mode, *, expected_inputs=None):
    fields = {'returncode', 'stdout', 'stderr', 'engine', 'observations', 'violation', 'counterexample_hex'}
    if type(native) is not dict or set(native) != fields:
        raise EvidenceError('Python fuzzing execution fields differ')
    if canonical(native['engine']) != canonical({'version': VERSION, 'mode': mode,
                                                 'native_modules': NATIVE_MODULES}):
        raise EvidenceError('Python fuzzing did not execute the pinned native engine')
    for field in ('stdout', 'stderr'):
        if type(native[field]) is not str or len(native[field]) > 100_000:
            raise EvidenceError('Python fuzzing output exceeds its bound')
    if 'INFO: Using built-in libfuzzer' not in native['stderr']:
        raise EvidenceError('Python fuzzing native libFuzzer marker is missing')
    rows = native['observations']
    if type(rows) is not list or not 1 <= len(rows) <= 512:
        raise EvidenceError('Python fuzzing requires real bounded callback executions')
    buggy = mode in ('buggy_campaign', 'buggy_replay', 'clean_buggy')
    failures, seen = [], []
    for row in rows:
        if type(row) is not dict or set(row) != {'input_hex', 'observed_remaining'}:
            raise EvidenceError('Python fuzzing observation fields differ')
        data = decode_input(row['input_hex'])
        actual = row['observed_remaining']
        if actual is not None and type(actual) is not int:
            raise EvidenceError('Python fuzzing observed value is not an integer or rejection')
        expected = None if len(data) != 2 or data[1] > data[0] else data[0] - data[1]
        implementation = ((data[0] - data[1]) % 256 if buggy and len(data) == 2 else expected)
        if actual != implementation:
            raise EvidenceError('Python fuzzing observed value disagrees with the independent witness')
        seen.append(row['input_hex'])
        if actual != expected:
            failures.append(row['input_hex'])
    fails = mode in ('buggy_campaign', 'buggy_replay')
    if fails:
        if (type(native['returncode']) is not int or native['returncode'] != 77
                or len(failures) != 1 or failures[0] != seen[-1]
                or canonical(native['violation']) != canonical(witness(failures[0]))
                or 'AssertionError: OWNED_ACCOUNTING_UNDERFLOW' not in native['stdout']
                or 'ERROR: libFuzzer: fuzz target exited' not in native['stderr']):
            raise EvidenceError('Python fuzzing failure is not a reproduced owned invariant violation')
    elif (type(native['returncode']) is not int or native['returncode'] != 0 or failures
          or native['violation'] is not None or native['counterexample_hex'] is not None
          or native['stdout'] or 'AssertionError' in native['stderr']):
        raise EvidenceError('Python fuzzing clean or repaired control did not pass')
    if expected_inputs is not None and set(seen) != set(expected_inputs):
        raise EvidenceError('Python fuzzing replay or clean control input membership differs')
    if mode.endswith('_campaign'):
        match = re.search(r'^stat::number_of_executed_units:\s+(\d+)\s*$', native['stderr'], re.M)
        if not match or int(match[1]) != len(rows) or not re.search(r'cov:\s+[1-9][0-9]*', native['stderr']):
            raise EvidenceError('Python fuzzing campaign lacks native execution and coverage statistics')
        if mode == 'buggy_campaign':
            if (native['counterexample_hex'] != failures[0]
                    or 'Test unit written to counterexample.bin' not in native['stderr']):
                raise EvidenceError('Python fuzzing failing corpus does not match its callback')
        elif len(rows) != 512 or all(len(decode_input(value)) == 2 for value in seen):
            raise EvidenceError('Python fuzzing repaired campaign did not complete its budget and parser control')
        if any(len(decode_input(value)) > 2 for value in seen):
            raise EvidenceError('Python fuzzing campaign exceeded the fixed two-byte target')
    elif 'Running: ' not in native['stderr']:
        raise EvidenceError('Python fuzzing did not replay concrete corpus files')
    return {'seen': seen, 'failures': failures}


def validate(evidence, payload):
    if type(evidence) is not dict or set(evidence) != set(MODES):
        raise EvidenceError('Python fuzzing control inventory differs')
    discovery = validate_case(evidence['discovery'], MODES['discovery'])
    discovered = discovery['failures'][0]
    seed = payload['seed_hex']
    if discovered == seed or seed not in discovery['seen']:
        raise EvidenceError('Python fuzzing must generate a counterexample beyond the valid seed')
    pinned = payload['pinned_counterexample_hex']
    for prefix, value in (('discovered', discovered), ('pinned', pinned)):
        witness(value)
        for suffix in ('buggy', 'repaired'):
            name = prefix + '_' + suffix
            validate_case(evidence[name], MODES[name], expected_inputs=[value])
    clean = payload['clean_inputs_hex']
    validate_case(evidence['clean'], MODES['clean'], expected_inputs=clean)
    repaired = validate_case(evidence['repaired_campaign'], MODES['repaired_campaign'])
    if seed not in repaired['seen'] or not set(repaired['seen']) - {'', seed}:
        raise EvidenceError('Python fuzzing repaired campaign did not mutate the seed')
    return {'fresh_campaign': {'counterexample_generated': True, 'independent_witness_validated': True,
                               'original_replay_failed': True, 'repaired_replay_passed': True},
            'pinned_counterexample': {**witness(pinned), 'input_sha256': sha(bytes.fromhex(pinned)),
                                      'original_replay_failed': True, 'repaired_replay_passed': True},
            'valid_and_invalid_length_controls': {'cases': len(clean), 'passed': True},
            'repaired_campaign': {'executed_units': 512, 'invariant_violations': 0,
                                  'mutations_exercised': True, 'invalid_lengths_exercised': True}}


def execute(work, tag, mode, source, payload, env, replay_hex=None):
    case = work/tag
    case.mkdir()
    (case/'Owned.py').write_text(source)
    if mode.endswith('_campaign'):
        (case/'corpus').mkdir()
        (case/'corpus/valid.bin').write_bytes(bytes.fromhex(payload['seed_hex']))
    elif mode == 'clean_buggy':
        (case/'clean').mkdir()
        for index, value in enumerate(payload['clean_inputs_hex']):
            (case/'clean'/f'{index:02}.bin').write_bytes(bytes.fromhex(value))
    else:
        (case/'case.bin').write_bytes(bytes.fromhex(replay_hex))
    proc = subprocess.run([*ISOLATE, sys.executable, '-I', '-B', '-S', str(work/'worker.py'), mode],
                          cwd=case, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=35)
    def optional_json(name):
        return strict_json(read_artifact(case, name)) if (case/name).exists() else None
    native = {'returncode': proc.returncode, 'stdout': proc.stdout.decode('utf-8'),
              'stderr': proc.stderr.decode('utf-8'), 'engine': optional_json('engine.json'),
              'observations': (optional_json('executed-inputs.json') or {}).get('observations'),
              'violation': optional_json('owned-violation.json'),
              'counterexample_hex': read_artifact(case, 'counterexample.bin').hex()
              if (case/'counterexample.bin').exists() else None}
    return native


def run(kit, *, evidence_dir=None):
    if sys.version_info[:2] != (3, 12):
        raise EvidenceError('Python fuzzing native kit requires CPython 3.12')
    payload = inputs()
    proof = strict_json(checked(PROOFS, PROOFS_SHA))
    worker = checked(WORKER, WORKER_SHA)
    with tempfile.TemporaryDirectory(prefix='nqc-python-fuzz-native-') as temp:
        work = Path(temp)
        env = {'HOME': temp, 'TMPDIR': temp, 'PATH': '/usr/bin:/bin', 'PYTHONIOENCODING': 'utf-8'}
        install_wheels(Path(kit), work, env, lock_path=LOCK, lock_digest=LOCK_SHA, producer='Atheris')
        count = verify_installed(work, proof)
        (work/'worker.py').write_bytes(worker)
        evidence = {'discovery': execute(work, 'discovery', MODES['discovery'],
                                         payload['buggy_source'], payload, env)}
        discovered = validate_case(evidence['discovery'], MODES['discovery'])['failures'][0]
        for prefix, value in (('discovered', discovered), ('pinned', payload['pinned_counterexample_hex'])):
            for suffix, source in (('buggy', payload['buggy_source']), ('repaired', payload['repaired_source'])):
                tag = prefix + '_' + suffix
                evidence[tag] = execute(work, tag, MODES[tag], source, payload, env, value)
        evidence['clean'] = execute(work, 'clean', MODES['clean'], payload['buggy_source'], payload, env)
        evidence['repaired_campaign'] = execute(work, 'repaired_campaign', MODES['repaired_campaign'],
                                                payload['repaired_source'], payload, env)
        observations = validate(evidence, payload)
    report = {'schema_version': 1, 'repository': 'google/atheris', 'catalog_id': 114,
              'revision': proof['catalog_revision'], 'version': VERSION,
              'wheel_sha256': proof['wheel']['sha256'], 'wheel_lock_sha256': LOCK_SHA,
              'source_proof_sha256': PROOFS_SHA, 'owned_inputs_sha256': INPUTS_SHA,
              'worker_sha256': WORKER_SHA, 'verified_installed_code_members': count,
              'observations': observations,
              'scope': {'fixed_owned_parser': 'two-byte debit with deliberately inserted underflow',
                        'native_campaign_run_budget_each': 512, 'network_access': False,
                        'catalog_commit_compiled': False, 'official_pinned_release_wheel': True,
                        'original_vulnerabilities_confirmed': 0, 'arbitrary_targets_accepted': False,
                        'normalization': 'Fresh mutated corpus bytes, intermediate inputs, number of runs before a failure, coverage counts, timing, memory, native addresses and process IDs are excluded from the canonical result; every fresh witness is independently checked and replayed on original and repaired fixtures. The optional raw receipt retains those observations.',
                        'limits': 'A bounded native fuzzing and replay control on owned Python code. It does not establish exhaustive path coverage, native-extension sanitizer coverage, general vulnerability discovery ability, or equivalence of the release binary to the catalog commit.'}}
    if evidence_dir is not None:
        write_new_bundle(Path(evidence_dir), {'native-evidence.json': canonical(evidence),
                                              'report.json': canonical(report),
                                              'discovered-counterexample.bin': bytes.fromhex(discovered),
                                              'pinned-counterexample.bin': bytes.fromhex(payload['pinned_counterexample_hex'])})
    return report
