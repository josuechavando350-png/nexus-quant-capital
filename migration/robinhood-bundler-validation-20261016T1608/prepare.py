"""Prepare offline compiler/tracer inputs; never install packages or call a chain."""
import argparse
import hashlib
import json
import posixpath
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(aa, oz, bundler, solc, typescript, geth):
    out = HERE / 'build'
    out.mkdir(exist_ok=False)
    for path, commit in [(aa, '7af70c8993a6f42973f520ae0752386a5032abe7'),
                         (oz, 'dbb6104ce834628e473d2173bbc9d47f81a9eec3'),
                         (bundler, '1868538f1d7678576291d2ecabb4443c797ad133')]:
        assert subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip() == commit
    assert sha(solc) == '28726a452290c70e1984f15c53ad3088e7d98783ee3070b11b3664da77415732'
    sources = {}
    def add(name):
        if name in sources:
            return
        if name.startswith('@openzeppelin/contracts/'):
            path = oz / name.replace('@openzeppelin/', '', 1)
        else:
            path = aa / name
        text = path.read_text()
        # Verify worktree bytes against the pinned source, not just HEAD identity.
        origin = oz if name.startswith('@openzeppelin/') else aa
        rel = str(path.relative_to(origin))
        assert path.read_bytes() == subprocess.check_output(['git', '-C', str(origin), 'show', 'HEAD:' + rel])
        sources[name] = {'content': text}
        for imported in re.findall(r'import[^;]*?["\']([^"\']+)["\']\s*;', text):
            add(posixpath.normpath(posixpath.join(posixpath.dirname(name), imported)) if imported.startswith('.') else imported)
    entry = 'contracts/core/EntryPointSimulations.sol'
    add(entry)
    request = {'language': 'Solidity', 'sources': sources, 'settings': {
        'optimizer': {'enabled': True, 'runs': 200}, 'evmVersion': 'paris',
        'outputSelection': {entry: {'EntryPointSimulations': ['abi', 'evm.deployedBytecode.object', 'evm.methodIdentifiers', 'storageLayout']}}}}
    (out / 'compiler-input.json').write_text(json.dumps(request, indent=2) + '\n')
    run = subprocess.run([str(solc), '--standard-json'], input=json.dumps(request), text=True,
                         capture_output=True, timeout=120)
    (out / 'compiler-stderr.txt').write_text(run.stderr)
    run.check_returncode()
    compiled = json.loads(run.stdout)
    assert not [e for e in compiled.get('errors', []) if e['severity'] == 'error'], compiled.get('errors')
    artifact = compiled['contracts'][entry]['EntryPointSimulations']
    (out / 'simulation-artifact.json').write_text(json.dumps(artifact, indent=2) + '\n')
    for name in ['BundlerCollectorTracer.ts', 'GethTracer.ts', 'TracerResultParser.ts', 'ValidationManager.ts']:
        path = bundler / 'packages/validation-manager/src' / name
        assert path.read_bytes() == subprocess.check_output(['git', '-C', str(bundler), 'show', 'HEAD:packages/validation-manager/src/' + name])
        shutil.copyfile(path, out / name)
    for name, source in [('LICENSE-bundler.md', bundler/'LICENSE.md'), ('LICENSE-aa', aa/'LICENSE'), ('LICENSE-oz', oz/'LICENSE')]:
        shutil.copyfile(source, out/name)
    subprocess.run(['node', str(HERE / 'extract-tracer.cjs'), str(typescript), str(out)], check=True, timeout=20)
    pin = {'bundler_commit': '1868538f1d7678576291d2ecabb4443c797ad133',
           'account_abstraction_commit': '7af70c8993a6f42973f520ae0752386a5032abe7',
           'openzeppelin_commit': 'dbb6104ce834628e473d2173bbc9d47f81a9eec3',
           'solc_sha256': sha(solc), 'geth_sha256': sha(geth), 'typescript_js_sha256': sha(typescript),
           'geth_version': subprocess.check_output([str(geth), 'version'], text=True),
           'node_version': subprocess.check_output(['node', '--version'], text=True).strip(),
           'solidity_source_files': len(sources), 'typescript_version': '4.9.5',
           'full_bundler_dependencies_available': False, 'full_bundler_execution': False}
    (HERE/'toolchain.json').write_text(json.dumps(pin, indent=2)+'\n')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    for name in ['aa', 'oz', 'bundler', 'solc', 'typescript', 'geth']:
        ap.add_argument('--'+name, type=Path, required=True)
    prepare(**vars(ap.parse_args()))
