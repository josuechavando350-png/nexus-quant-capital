"""Run fixed native provers on license choices, with a semantic negative control for each producer."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from .product_license_choices import prepare, report
from .product_proof_languages import program
from .product_reasoning import EvidenceError
from .product_review import copy_release, sha
from .safe_io import read_artifact, strict_json

ISOLATE = ['/usr/bin/unshare', '--user', '--map-current-user', '--net']
PINS = 'product_proof_releases.json'
EXECUTABLES = {
    'alive2': 'build/alive', 'klee': 'bin/klee',
    'cbmc': 'usr/bin/cbmc', 'esbmc': 'release/bin/esbmc', 'rocq': 'usr/bin/coqc',
    'dafny': 'dafny/dafny', 'verifast': 'verifast-26.10/bin/verifast', 'fstar': 'fstar/bin/fstar.exe',
    'saw': 'saw-1.6-ubuntu-22.04-X64-with-solvers/bin/saw', 'verus': 'verus-x86-linux/rust_verify',
    'kani': 'kani-0.68.0/bin/kani-driver', 'seahorn': 'SeaHorn-0.1.0-Linux-x86_64/bin/seahorn',
}


def cache_name(asset):
    return asset.get('file') or asset['url'].rsplit('/', 1)[-1]


def unpack(cache, work, spec):
    root = work/'kit'
    root.mkdir()
    for asset in spec['assets']:
        name = cache_name(asset)
        if 'install_as' in asset:
            dest = root/asset['install_as']
            dest.parent.mkdir(exist_ok=True, parents=True)
            copy_release('KLEE distribution member', cache/name, dest, asset['sha256'],
                         limit=asset['size'], executable=asset['install_as'] == 'bin/klee')
            continue
        file = work/name
        copy_release('license proof distribution', cache/name, file, asset['sha256'], limit=350 * 1024**2, executable=False)
        if name.endswith('.deb'):
            cmd = ['/usr/bin/dpkg-deb', '-x', str(file), str(root)]
        elif name.endswith('.zip'):
            cmd = ['/usr/bin/unzip', '-q', str(file), '-d', str(root)]
        elif name.endswith(('.tar.gz', '.tar.xz')):
            cmd = ['/usr/bin/tar', '--no-same-owner', '-xf', str(file), '-C', str(root)]
        else:
            raise EvidenceError('unknown proof distribution format')
        subprocess.run([*ISOLATE, *cmd], cwd=work, env={'HOME': str(work), 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'},
                       stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=120)
        file.unlink()
    return root


def invoke(command, folder, env):
    return subprocess.run([*ISOLATE, *map(str, command)], cwd=folder, env=env, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=150, text=True, errors='replace')


def build_alive(root, work, spec):
    source = root/'alive2-19.0'
    prefix = root/'usr'
    env = {'HOME': str(work), 'TMPDIR': str(work), 'LC_ALL': 'C', 'GIT_CONFIG_NOSYSTEM': '1',
           'PATH': str(prefix/'bin') + ':/usr/bin:/bin', 'LD_LIBRARY_PATH': str(prefix/'lib/x86_64-linux-gnu')}

    def run(args, input_bytes=None, timeout=120):
        result = subprocess.run([*ISOLATE, *args], cwd=source, env=env, input=input_bytes or b'',
                                capture_output=True, timeout=timeout)
        if result.returncode:
            raise EvidenceError('could not build pinned Alive2 source: ' + result.stdout[-700:].decode(errors='replace')
                                + result.stderr[-700:].decode(errors='replace'))
        return result.stdout.decode().strip()

    # CMake reads git-describe. Restore the exact source tree and upstream commit from the release.
    git = '/usr/bin/git'
    run([git, 'init', '-q'])
    run([git, 'add', '-f', '-A'])
    if run([git, 'write-tree']) != spec['tree']:
        raise EvidenceError('Alive2 release and upstream Git tree differ')
    commit = run([git, 'hash-object', '-w', '-t', 'commit', '--stdin'], spec['commit_object'].encode())
    if commit != spec['commit']:
        raise EvidenceError('Alive2 commit object mismatch')
    (source/'.git/shallow').write_text(commit + '\n')
    run([git, 'update-ref', 'HEAD', commit])
    run([git, 'update-ref', 'refs/tags/v19.0', commit])
    cmake = str(prefix/'bin/cmake')
    build = str(root/'build')
    run([cmake, '-GNinja', '-S', '.', '-B', build, '-DCMAKE_BUILD_TYPE=Release',
         '-DCMAKE_PREFIX_PATH=' + str(prefix), '-DBUILD_TV=OFF', '-DBUILD_LLVM_UTILS=OFF'])
    run([cmake, '--build', build, '--target', 'alive', '-j4'], timeout=600)


def environment(tool, root, work):
    binary = root/EXECUTABLES[tool]
    env = {'HOME': str(work), 'TMPDIR': str(work), 'LC_ALL': 'C.UTF-8',
           'PATH': str(binary.parent) + ':/usr/bin:/bin', 'TZ': 'UTC'}
    if tool == 'alive2':
        env['LD_LIBRARY_PATH'] = str(root/'usr/lib/x86_64-linux-gnu')
    if tool == 'klee':
        env.update({'LD_LIBRARY_PATH': str(root/'lib'), 'KLEE_RUNTIME_LIBRARY_PATH': str(root/'runtime')})
    if tool == 'cbmc':
        env['LD_LIBRARY_PATH'] = str(root/'usr/lib')
    if tool == 'rocq':
        config = work/'ocamlfind.conf'
        config.touch()
        env['OCAMLFIND_CONF'] = str(config)
    if tool in ('verus', 'kani'):
        compiler, = root.glob('rustc-*/rustc')
        std, = root.glob('rust-std-*/rust-std-x86_64-unknown-linux-gnu/lib/rustlib/x86_64-unknown-linux-gnu/lib')
        shutil.copytree(std, compiler/'lib/rustlib/x86_64-unknown-linux-gnu/lib', dirs_exist_ok=True)
        env.update({'RUSTC': str(compiler/'bin/rustc'), 'LD_LIBRARY_PATH': str(compiler/'lib'),
                    'PATH': str(compiler/'bin') + ':' + env['PATH']})
        if tool == 'verus':
            env['VERUS_Z3_PATH'] = str(binary.parent/'z3')
    return binary, env


def attempt(tool, binary, env, folder, claims, positive):
    folder.mkdir()
    name, source = program(tool, claims)
    (folder/name).write_text(source)
    if tool == 'seahorn':
        bin_dir = binary.parent
        for command in ([bin_dir/'clang-3.6', '-c', '-emit-llvm', '-O0', name, '-o', 'in.bc'],
                        [bin_dir/'seapp', 'in.bc', '-o', 'pre.bc'], [bin_dir/'seaopt', '-O1', 'pre.bc', '-o', 'opt.bc']):
            if invoke(command, folder, env).returncode:
                raise EvidenceError('SeaHorn could not prepare the fixed license model')
        args = ['--horn-solve', 'opt.bc']
    else:
        args = {'alive2': ['-root-only', '-disable-poison-input', '-disable-undef-input', name],
                'klee': ['--solver-backend=z3', '--output-dir=checked', name], 'cbmc': [name, '--json-ui'], 'esbmc': [name, '--multi-property'],
                'rocq': ['-noinit', '-boot', name], 'dafny': ['verify', name, '--cores', '1'],
                'verifast': ['-c', name], 'fstar': [name], 'saw': [name],
                'verus': [name, '--extern', 'vstd=' + str(binary.parent/'libvstd.rlib')], 'kani': [name]}[tool]
    run = invoke([binary, *args], folder, env)
    if not verdict(tool, run.returncode, run.stdout, len(claims), positive):
        raise EvidenceError(f'{tool} did not confirm the expected license proof result')
    if tool == 'klee':
        errors = sorted((folder/'checked').glob('*.err'))
        if positive and errors or not positive and not (
                len(errors) == 1 and errors[0].name.endswith('.nqc.err') and
                errors[0].read_text().splitlines()[0:1] == ['Error: NQC license choice']):
            raise EvidenceError('KLEE license error artifact differs from the expected outcome')
    if tool == 'rocq' and positive and not (folder/'Nqc.vo').is_file():
        raise EvidenceError('Rocq did not produce a checked proof object')
    return sha(source.encode())


def verdict(tool, code, output, count, positive):
    if tool == 'klee':
        errors = [line for line in output.splitlines() if line.startswith('KLEE: ERROR:')]
        return (code == 0 and 'KLEE: Using Z3 solver backend' in output
                and 'KLEE: done: completed paths = 1' in output.splitlines()
                and f'KLEE: done: partially completed paths = {int(not positive)}' in output.splitlines()
                and (not errors if positive else len(errors) == 1 and errors[0].endswith(' NQC license choice')))
    if tool == 'alive2':
        lines = output.splitlines()
        names = [f'Name: nqc_{i}_{direction}' for i in range(count) for direction in ('forward', 'reverse')]
        errors = [line for line in lines if line.startswith('ERROR:')]
        return (code == 0 and [line for line in lines if line.startswith('Name:')] == names
                and (not errors and lines.count('Transformation seems to be correct!') == count * 2 if positive
                     else errors == ['ERROR: Value mismatch'] * 2 and lines.count('Example:') == 2))
    if tool == 'cbmc':
        if code != (0 if positive else 10):
            return False
        entries = [r for section in json.loads(output) for r in section.get('result', [])]
        wanted = 'SUCCESS' if positive else 'FAILURE'
        return (len(entries) == count and {r['description'] for r in entries} == {f'nqc_{i}' for i in range(count)}
                and all(r['status'] == wanted for r in entries))
    if tool == 'seahorn':
        return code == 0 and output.splitlines()[-1:] == (['unsat'] if positive else ['sat'])
    if (code == 0) != positive:
        return False
    if tool == 'rocq':
        return not output.strip() if positive else 'expected to have type' in output
    if tool == 'dafny':
        return (f'{count} verified, 0 errors' in output if positive else
                'postcondition' in output.lower() and '1 error' in output)
    if tool == 'verus':
        return f'{count} verified, 0 errors' in output if positive else 'postcondition not satisfied' in output
    if tool == 'kani':
        return (f'{count} successfully verified harnesses, 0 failures, {count} total' in output if positive
                else 'VERIFICATION:- FAILED' in output and '1 failure' in output)
    if tool == 'esbmc':
        return (f'0 of {count} properties failed' in output and 'VERIFICATION SUCCESSFUL' in output
                if positive else 'VERIFICATION FAILED' in output and 'assertion' in output)
    if tool == 'verifast':
        return '0 errors found' in output and 'statements verified' in output if positive else 'Assertion might not hold' in output
    if tool == 'saw':
        return (all(f'nqc_{i}_proved' in output.splitlines() for i in range(count)) if positive
                else 'unsolved subgoal' in output and 'Invalid:' in output)
    if tool == 'fstar':
        return ('Verified module: Nqc' in output and 'All verification conditions discharged successfully' in output
                if positive else 'could not prove' in output.lower() or 'assertion failed' in output.lower())
    raise EvidenceError('unregistered license proof tool')


def build(cache, evidence):
    pins = strict_json(read_artifact(Path(__file__).parent, PINS))
    claims, negative = prepare(evidence)
    result = report(evidence, claims, negative)
    receipts = {}
    for tool, spec in pins.items():
        primary = cache_name(spec['assets'][0])
        if not (cache/primary).exists():
            continue
        with tempfile.TemporaryDirectory(prefix='nqc-license-proof-') as temp:
            work = Path(temp)
            root = unpack(cache, work, spec)
            if tool == 'alive2':
                build_alive(root, work, spec)
            binary, env = environment(tool, root, work)
            valid = attempt(tool, binary, env, work/'positive', claims, True)
            invalid = attempt(tool, binary, env, work/'negative', [negative], False)
        receipts[spec['repository']] = {'version': spec['version'], 'release_sha256': [a['sha256'] for a in spec['assets']],
            'claims_proved': len(claims), 'semantic_negative_controls_rejected': 1, 'choices_sha256': result['choices_sha256'],
            'sources_sha256': result['sources_sha256'], 'positive_input_sha256': valid, 'negative_input_sha256': invalid}
    if not receipts:
        raise EvidenceError('no registered license proof distributions present')
    return {**result, 'verified_by': sorted(receipts)}, receipts
