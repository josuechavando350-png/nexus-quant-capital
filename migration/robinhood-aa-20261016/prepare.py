#!/usr/bin/env python3
"""Offline, pinned copies only. Build destination must be new and outside this repo."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARCHIVE = ROOT / 'migration/engine-v2-20261015/source/ci/nqc-census'
PINS = {
    'account-abstraction': '7af70c8993a6f42973f520ae0752386a5032abe7',
    'openzeppelin-contracts': 'dbb6104ce834628e473d2173bbc9d47f81a9eec3',
    'morpho-blue': '8e26ca6a8dbc5089edcd67fb576248810fd2870a',
}

def run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()

def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('overlay precondition failed: ' + old)
    return text.replace(old, new, 1)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dependencies', type=Path, required=True)
    ap.add_argument('--build', type=Path, required=True)
    args = ap.parse_args()
    build = args.build.resolve()
    if build.exists() or build == ROOT or ROOT in build.parents:
        raise ValueError('use a NEW destination OUTSIDE the repository')
    for name, pin in PINS.items():
        dep = args.dependencies / name
        if run('git', 'rev-parse', 'HEAD', cwd=dep) != pin:
            raise ValueError('wrong dependency commit: ' + name)
        if run('git', 'status', '--porcelain', '--untracked-files=all', cwd=dep):
            raise ValueError('dirty dependency: ' + name)
    original = ARCHIVE / 'morpho-native-lab/src/NqcMorphoNativeCallbackLab.sol'
    if run('git', 'hash-object', str(original)) != '33ba05d21472f4eaffb98c42f5cc2fd4454c6555':
        raise ValueError('executor source identity changed')
    suite = ARCHIVE / 'erc4337-real-source-lab/test/NqcRealEntryPointV07GasSponsor.t.sol'
    expected = run('git', 'rev-parse', '39b6ef490d8fee0bff5d3c9818465e128071dcbf:' + str(suite.relative_to(ROOT)), cwd=ROOT)
    if run('git', 'hash-object', str(suite)) != expected:
        raise ValueError('fixture source identity changed')
    build.mkdir(parents=True)
    ignore = shutil.ignore_patterns('.git', 'out', 'cache', '__pycache__')
    shutil.copytree(ARCHIVE / 'morpho-native-lab', build / 'morpho-native-lab', ignore=ignore)
    shutil.copytree(args.dependencies / 'morpho-blue', build / 'morpho-native-lab/lib/morpho-blue', ignore=ignore)
    shutil.copytree(ARCHIVE / 'erc4337-real-source-lab', build / 'baseline', ignore=ignore)
    (build / 'baseline/src').mkdir(exist_ok=True)
    shutil.copy2(original, build / 'baseline/src/NqcMorphoNativeCallbackLab.sol')
    for lab in ['baseline', 'robinhood']:
        for name in ['account-abstraction', 'openzeppelin-contracts']:
            shutil.copytree(args.dependencies / name, build / lab / 'lib' / name, ignore=ignore)
    lab = build / 'robinhood'
    shutil.copytree(HERE / 'src', lab / 'src')
    shutil.copytree(HERE / 'test', lab / 'test')
    patched = original.read_text()
    patched = replace_once(patched, 'pragma solidity ^0.8.19;', 'pragma solidity ^0.8.23;\nimport {NqcRobinhoodL2Expiry} from "./NqcRobinhoodL2Expiry.sol";')
    patched = replace_once(patched, 'contract NqcMorphoNativeCallbackLab {', 'contract NqcMorphoRobinhoodL2Lab is NqcRobinhoodL2Expiry {')
    patched = replace_once(patched, 'uint256 validThroughBlock,', 'uint256 validThroughL2Block,')
    patched = replace_once(patched, 'if (block.number > validThroughBlock) revert UnexpectedBlock();', '_checkL2Expiry(validThroughL2Block);')
    patched = replace_once(patched, 'maxRepaidAssets, minLoanProfit, minimumSwapOut)', 'maxRepaidAssets, minLoanProfit, minimumSwapOut, validThroughL2Block)')
    (lab / 'src/NqcMorphoRobinhoodL2Lab.sol').write_text(patched)
    # Reuse synthetic fixtures, retaining their exact source provenance. The historical
    # EIP712 name is corrected: its signature actually uses EIP-191 personal_sign.
    text = suite.read_text()
    header = text[text.index('import {IAccount}'):text.index('interface Vm4337Nqc')]
    header = header.replace('NqcMorphoNativeCallbackLab', 'NqcMorphoRobinhoodL2Lab')
    account = text[text.index('contract Nqc4337EIP712SignedAccountTestOnly'):text.index('// Research-only sponsor policy')]
    account = account.replace('Nqc4337EIP712SignedAccountTestOnly', 'NqcEip191AccountFixture')
    fixtures = '// SPDX-License-Identifier: MIT\npragma solidity ^0.8.23;\n' + header + account + text[text.index('// Typed Morpho interfaces'):]
    (lab / 'test/Fixtures.sol').write_text(fixtures)
    config = (ARCHIVE / 'erc4337-real-source-lab/foundry.toml').read_text()
    config = config.replace('optimizer_runs = 200', 'optimizer_runs = 1000000').replace('evm_version = "shanghai"', 'evm_version = "paris"')
    # EntryPoint is injected from authenticated runtime in tests, not this compilation.
    # The test contract embeds many fixture constructors; only the test harness
    # needs this enlarged limit. Each deployable fixture is separately size-checked.
    config = config.replace('[profile.default]', '[profile.default]\ncode_size_limit = 200000')
    config = config.replace('fs_permissions = [', 'fs_permissions = [{ access = "read", path = "runtime.json" }, ')
    (lab / 'foundry.toml').write_text(config)
    lock = {'dependencies': PINS, 'original_executor_blob': '33ba05d21472f4eaffb98c42f5cc2fd4454c6555',
            'fixture_blob': expected, 'patched_executor_sha256': hashlib.sha256(patched.encode()).hexdigest(),
            'archive_commit': '39b6ef490d8fee0bff5d3c9818465e128071dcbf',
            'producer_parent_commit': run('git', 'rev-parse', 'HEAD', cwd=ROOT),
            'research_input_sha256': {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(HERE.rglob('*')) if p.is_file() and p.suffix in ('.py','.sol') and 'evidence' not in p.relative_to(HERE).parts},
            'scope': 'LOCAL_SYNTHETIC_RESEARCH_ONLY'}
    (build / 'source-lock.json').write_text(json.dumps(lock, indent=2) + '\n')
    print(json.dumps(lock, indent=2))

if __name__ == '__main__':
    main()
