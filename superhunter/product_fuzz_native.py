"""Seeded Echidna search, fixed Medusa replay, and independent owned trace checks."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from zipfile import ZipFile

from .native_compile import PIN as SOLC
from .product_census_header import pinned
from .product_notice_ranking import ISOLATE
from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .product_slither_native import PINS as PYTHON_PINS, PINS_SHA as PYTHON_PINS_SHA
from .product_solidity_headers import FORGE_SHA
from .safe_io import MAX_BYTES, canonical, read_artifact, strict_json

REPOSITORIES = {'crytic/echidna': 'executable', 'crytic/medusa': 'executable'}
SCOPES = {
    'crytic/echidna': 'Seeded bounded invariant search on own broken/fixed cumulative-cap contracts, with native trace replay in Foundry.',
    'crytic/medusa': 'Replay a fixed own minimized counterexample, then check the repaired variant; PRNG generation is not seed-controlled.',
}
BINARIES = {
    'echidna': 'a3f1ff5116839965524af797702c1fa4e57793ece8d9cd5365c0381fea1a6da4',
    'medusa': '86e54c586e49e6bf9676f448218e10475afacb0a8bd5ca1aea234f66db7169d6',
    'solc': SOLC['sha256'], 'forge': FORGE_SHA,
}
CONTROLS = 'superhunter/product_supply/fuzz-native-controls.json'
CONTROLS_SHA = '777b6236a4c8d76f2cc7c64cc145455569e2647e73f6e6bd73b01245b7793e75'
EXPECTED = {'echidna': [0, 9], 'medusa': [18, 1]}


def echidna_result(raw, broken):
    # The pinned release emits progress records even with quiet+JSON selected.
    # Require one final JSON object; never choose between competing reports.
    lines = [line for line in raw.splitlines() if line.strip()]
    if not lines or [i for i, line in enumerate(lines) if line.startswith(b'{')] != [len(lines)-1]:
        raise EvidenceError('ambiguous Echidna output framing')
    for line in lines[:-1]:
        if not (re.fullmatch(rb'Loaded \d+ transaction sequences from corpus/(reproducers|coverage)', line) or
                re.match(rb'\[\d{4}-\d{2}-\d{2} [0-9:.]+\] ', line) or
                line == b'  Call sequence:' or
                re.fullmatch(rb'OwnedCap.credit\(\d+\)( Time delay: \d+ seconds Block delay: \d+)?', line)):
            raise EvidenceError('unexpected Echidna progress output')
    row = strict_json(lines[-1])
    if (set(row) != {'success', 'error', 'tests', 'seed', 'coverage'} or
            row['success'] is not True or row['error'] is not None or row['seed'] != 20261121 or
            not isinstance(row['tests'], list) or len(row['tests']) != 1 or not row['coverage']):
        raise EvidenceError('invalid Echidna campaign evidence')
    test = row['tests'][0]
    if test.get('type') != 'property' or test.get('error') is not None:
        raise EvidenceError('Echidna did not execute the owned property')
    if broken:
        if test.get('status') not in ('shrinking', 'solved') or test.get('reason') != 'ReturnFalse':
            raise EvidenceError('Echidna missed the owned invariant violation')
        transactions = test.get('transactions')
        if (not isinstance(transactions, list) or len(transactions) != 2 or
                any(t.get('function') != 'credit' or t.get('arguments') != [str(n)] or
                    t.get('value') != '0x0' or t.get('gasprice') != '0x0'
                    for t, n in zip(transactions, EXPECTED['echidna']))):
            raise EvidenceError('Echidna counterexample differs from the pinned own sequence')
    elif (test.get('status') not in ('fuzzing', 'passed') or
          test.get('reason') is not None or test.get('transactions') is not None):
        raise EvidenceError('Echidna repaired control failed')
    return {'native_status': test['status'], 'native_reported_name': test.get('name'),
            'counterexample': EXPECTED['echidna'] if broken else None,
            'reason': test.get('reason')}


def medusa_result(raw, returncode, broken):
    text = re.sub(r'\x1b\[[0-9;]*m', '', raw.decode('utf-8'))
    summary = re.findall(r'Test summary: (\d+) test\(s\) passed, (\d+) test\(s\) failed', text)
    expected = ('0', '1') if broken else ('1', '0')
    status = 'FAILED' if broken else 'PASSED'
    if (returncode != (7 if broken else 0) or summary != [expected] or
            'Initializing corpus...' not in text or
            f'[{status}] Property Test: OwnedCap.echidna_total_bounded()' not in text):
        raise EvidenceError('Medusa did not replay the owned property controls')
    trace = [int(n) for n in re.findall(r'^\d+\) OwnedCap\.credit\(uint8\)\((\d+)\) ', text, re.M)]
    if trace != (EXPECTED['medusa'] if broken else []):
        raise EvidenceError('Medusa replay sequence differs')
    if broken and '=> [return (false)]' not in text:
        raise EvidenceError('Medusa did not report the false property return')
    return {'native_status': status, 'counterexample': trace if broken else None,
            'fixed_corpus_loaded': True}


def arithmetic_trace(values, repaired):
    total, states = 0, []
    for amount in values:
        if type(amount) is not int or not 0 <= amount <= 255:
            raise EvidenceError('owned trace amount is outside uint8')
        delta = amount % 10 + 1
        if not repaired or total + delta <= 10:
            total += delta
        states.append(total)
    return states


def replay_source():
    lines = ['// SPDX-License-Identifier: MIT', 'pragma solidity ^0.8.0;',
             'import {OwnedCap as Broken} from "./Broken.sol";',
             'import {OwnedCap as Fixed} from "./Fixed.sol";', 'contract OwnedReplayTest {']
    for tool, amounts in EXPECTED.items():
        for repaired in (False, True):
            variant = 'Fixed' if repaired else 'Broken'
            test = tool.title()+variant
            body = f'{variant} c = new {variant}(); '
            body += ' '.join(f'c.credit({n});' for n in amounts)
            body += f' assert({"" if repaired else "!"}c.echidna_total_bounded());'
            body += f' assert(c.total() == {arithmetic_trace(amounts, repaired)[-1]});'
            lines.append(f'function test{test}() public {{ {body} }}')
    return ('\n'.join(lines)+'\n}\n').encode()


def forge_result(raw):
    report = strict_json(raw)
    expected = {'test'+tool.title()+kind+'()' for tool in EXPECTED for kind in ('Broken', 'Fixed')}
    if set(report) != {'test/Replay.t.sol:OwnedReplayTest'}:
        raise EvidenceError('independent trace verifier contract differs')
    tests = report['test/Replay.t.sol:OwnedReplayTest'].get('test_results', {})
    if set(tests) != expected or any(t.get('status') != 'Success' or t.get('reason') is not None for t in tests.values()):
        raise EvidenceError('independent native trace replay failed')
    return {name: {'status': row['status'], 'gas': row['kind']['Unit']['gas']}
            for name, row in sorted(tests.items())}


def run(kit):
    if sys.version_info[:2] != (3, 12):
        raise EvidenceError('owned fuzzing kit requires CPython 3.12')
    controls = strict_json(pinned(ROOT, CONTROLS, CONTROLS_SHA))
    packages_raw = pinned(ROOT, PYTHON_PINS, PYTHON_PINS_SHA)
    pins = strict_json(packages_raw)['packages']
    with tempfile.TemporaryDirectory(prefix='nqc-fuzz-native-') as tmp:
        work, kit = Path(tmp), Path(kit)
        (work/'bin').mkdir()
        for name, digest in BINARIES.items():
            copy_release(name, kit/name, work/'bin'/name, digest)
        for index, row in enumerate(pins):
            archive = work/f'package-{index}.whl'
            copy_release(row['name'], kit/row['filename'], archive, row['sha256'], executable=False)
            with ZipFile(archive) as wheel:
                wheel.extractall(work/'packages'/row['directory'])
        (work/'packages.json').write_bytes(packages_raw)
        launcher = ('#!'+sys.executable+' -S\n').encode()+read_artifact(ROOT, 'superhunter/product_supply/fuzz-native-crytic.txt')
        (work/'bin/crytic-compile').write_bytes(launcher)
        (work/'bin/crytic-compile').chmod(0o500)
        env = {'HOME': tmp, 'TMPDIR': tmp, 'PATH': str(work/'bin')+':/usr/bin:/bin',
               'LC_ALL': 'C', 'GOMEMLIMIT': '512MiB'}
        def execute(mode, folder, expected_code=0):
            proc = subprocess.run([*ISOLATE, sys.executable, '-I', '-B', '-S',
                Path(__file__).with_name('product_fuzz_native_worker.py'), mode], cwd=folder,
                env=env, capture_output=True, timeout=120)
            if (proc.returncode != expected_code or len(proc.stdout) > MAX_BYTES or
                    len(proc.stderr) > MAX_BYTES or proc.stderr):
                error = EvidenceError('owned native fuzzing process failed')
                error.stderr, error.returncode = proc.stderr[:MAX_BYTES], proc.returncode
                raise error
            return proc
        campaigns = {}
        for tool in EXPECTED:
            campaigns[tool] = {}
            for variant in ('broken', 'fixed'):
                folder = work/(tool+'-'+variant)
                folder.mkdir()
                (folder/'Owned.sol').write_text(controls['sources'][variant])
                if tool == 'echidna':
                    (folder/'config.json').write_bytes(canonical(controls['echidna_config']))
                    proc = execute(tool, folder, 1 if variant == 'broken' else 0)
                    observation = echidna_result(proc.stdout, variant == 'broken')
                else:
                    (folder/'medusa.json').write_bytes(canonical(controls['medusa_config']))
                    corpus = folder/'medusa-corpus/test_results'
                    corpus.mkdir(parents=True)
                    (corpus/'owned-counterexample.json').write_bytes(canonical(controls['medusa_reproducer']))
                    proc = execute(tool, folder, 7 if variant == 'broken' else 0)
                    observation = medusa_result(proc.stdout, proc.returncode, variant == 'broken')
                campaigns[tool][variant] = observation
        replay = work/'replay'
        (replay/'test').mkdir(parents=True)
        for variant in ('broken', 'fixed'):
            (replay/'test'/(variant.title()+'.sol')).write_text(controls['sources'][variant])
        harness = replay_source()
        (replay/'test/Replay.t.sol').write_bytes(harness)
        (replay/'foundry.toml').write_text('[profile.default]\nevm_version = "paris"\noffline = true\noptimizer = false\n')
        verified = forge_result(execute('forge', replay).stdout)
    return {'campaigns': campaigns, 'independent_replay': verified,
            'replay_harness_sha256': sha(harness), 'controls_sha256': CONTROLS_SHA,
            'source_sha256': {k: sha(v.encode()) for k, v in controls['sources'].items()},
            'arithmetic_states': {tool: {variant: arithmetic_trace(values, variant == 'fixed')
                for variant in ('broken', 'fixed')} for tool, values in EXPECTED.items()},
            'binary_sha256': dict(BINARIES), 'dependency_lock_sha256': PYTHON_PINS_SHA,
            'tools': {
                'crytic/echidna': {'version': '2.4.0', 'catalog_revision': 'fb0fd78b9c3c46ac4127279da2313e727a66e5ad',
                    'release_tag_revision': '8e0f8258a53993a477040a6fa6250d643f863159',
                    'scope': SCOPES['crytic/echidna'], 'seed': 20261121, 'workers': 1, 'configured_test_limit': 1024},
                'crytic/medusa': {'version': '1.5.1', 'catalog_revision': 'b86c3bbafb9e80f7dcb09533006ecb15dbbbdc98',
                    'release_tag_revision': '540a483b7a2a35b0a6d210aeb6ae6015aa7a0f62',
                    'scope': SCOPES['crytic/medusa'], 'fixed_prng_seed': False, 'workers': 1,
                    'configured_test_limit': 1, 'test_limit_polled_and_may_overshoot': True,
                    'reproducer_sha256': sha(canonical(controls['medusa_reproducer']))}},
            'interpretation': 'Known own controls. Echidna searches with a fixed seed; Medusa replays fixed corpus and its later generation is not deterministic. Both counterexamples are checked on broken and repaired sources in Foundry/revm using the same solc. No counterexample within a budget is not a security proof. No external target or original vulnerability.'}
