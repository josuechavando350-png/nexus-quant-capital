"""Build the small, pinned upstream components used by the offline T36 review."""
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

from .product_sources import git, toolkit_sources

RUST = {
    'rustc': '51d7773f06394088baf08a2d6a172982d49b274710bf3efbd69e304bf8982500',
    'rust-std': '431763d8cc3bf88e3e01090d1c68f08873ec74ee0c3dbb591ec949b5cdfea5ea',
}
TARGET = 'x86_64-unknown-linux-gnu'
DEPS = (
    ('tree-sitter', 'tree-sitter/tree-sitter', 'da6fe9beb4f7f67beb75914ca8e0d48ae48d6406'),
    ('revm', 'fuzzland/revm', '1dead511260119867b220b38298ddca07f406357'),
    ('ply', 'dabeaz/ply', '0f398b72618c1564d71f7dc0558e6722b241875a'),
    ('pyevmasm', 'crytic/pyevmasm', '7929d63d6047a9b67e9e875a961071fe56c57e4f'),
    ('future', 'PythonCharmers/python-future', '2bdbfa5664241fee622b23590abd3492f973afc9'),
    ('rich', 'Textualize/rich', '43d3b04725ab9731727fb1126e35980c62f32377'),
    ('markdown-it-py', 'executablebooks/markdown-it-py', 'bee6d1953be75717a3f2f6a917da6f464bed421d'),
    ('mdurl', 'executablebooks/mdurl', '596bf1c8752de45fa576a52c315d6d8cc5bb1a4e'),
)


def run(*args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True, timeout=600)


def rust_compiler(stage):
    root = stage / 'rust'
    for name, expected in RUST.items():
        package = f'{name}-1.88.0-{TARGET}'
        archive = stage / (name + '.tgz')
        run('curl', '-fsSL', '--retry', '2', '--max-time', '240', '-o', archive,
            f'https://registry.npmjs.org/@rustbin/{package}/-/{package}-1.88.0.tgz')
        with archive.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise ValueError('Rust toolchain checksum mismatch: ' + name)
        prefix = 'package/' + ('rustc' if name == 'rustc' else f'rust-std-{TARGET}') + '/'
        with tarfile.open(archive) as tar:
            for item in tar:
                if not item.isfile() or not item.name.startswith((prefix + 'bin/', prefix + 'lib/')):
                    continue
                dest = root / item.name.removeprefix(prefix)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with tar.extractfile(item) as source, dest.open('wb') as target:
                    shutil.copyfileobj(source, target)
                dest.chmod(item.mode & 0o755)
    return root / 'bin/rustc'


def build_components(root, folder):
    tools = {row['repository']: row for row in toolkit_sources()}
    def data(repo, path):
        row = tools[repo]
        return git(root / row['path'], 'show', row['commit'] + ':' + path)

    with tempfile.TemporaryDirectory(dir=folder) as tmp:
        stage = Path(tmp)
        rustc = rust_compiler(stage)
        stats = stage / 'stats'
        stats.mkdir()
        for name in ('token', 'util', 'cloc'):
            (stats / (name + '.rs')).write_bytes(data('Cyfrin/aderyn', f'aderyn_core/src/stats/{name}.rs'))
        (stage / 'stats.rs').write_text('pub mod util; pub mod token; pub mod cloc;')
        (stage / 'metrics.rs').write_text(
            'mod stats; use std::io::Read; fn main() { let mut source = String::new();'
            'std::io::stdin().read_to_string(&mut source).unwrap();'
            'println!("{}", stats::cloc::count_code_lines(&stats::token::tokenize(&source))); }')
        run(rustc, '--edition=2024', '-Awarnings', stage / 'metrics.rs', '-o', folder / 'aderyn-lines')
        (stage / 'walk.rs').write_bytes(data('fuzzland/ityfuzz', 'src/evm/bytecode_iterator.rs'))
        opcodes = (folder / 'revm/crates/interpreter/src/instructions/opcode.rs').read_text()
        values = re.findall(r'^pub const (?:JUMP|JUMPI|STOP|RETURN|REVERT|INVALID): u8 = 0x[\da-f]+;', opcodes, re.M)
        if len(values) != 6:
            raise ValueError('unexpected pinned revm opcode definitions')
        (stage / 'inspect.rs').write_text('extern crate self as revm_interpreter; pub mod opcode {'
            + '\n'.join(values) + '} mod walk; use std::io::Read; fn main() {let mut bytes = vec![];'
            'std::io::stdin().read_to_end(&mut bytes).unwrap();'
            'unsafe {walk::SKIP_CBOR = true;} for (pc, op) in walk::all_bytecode(&bytes) {println!("{pc} {op}");}}')
        run(rustc, '--edition=2024', '-Awarnings', stage / 'inspect.rs', '-o', folder / 'ityfuzz-opcodes')
        grammar = 'languages/solidity/tree-sitter/semgrep-solidity/lib/'
        for name in ('parser.c', 'tree_sitter/parser.h', 'tree_sitter/alloc.h', 'tree_sitter/array.h'):
            destination = stage / name
            destination.parent.mkdir(exist_ok=True)
            destination.write_bytes(data('semgrep/semgrep', grammar + name))
        lib = folder / 'tree-sitter/lib'
        run('gcc', '-O2', '-std=gnu11', '-fPIC', '-shared', '-I', stage, '-I', lib / 'include',
            '-I', lib / 'src', stage / 'parser.c', lib / 'src/lib.c', '-o', folder / 'semgrep-solidity.so')
