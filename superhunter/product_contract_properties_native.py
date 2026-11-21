"""Execute upstream ERC20 properties and Immunefi token controls on own local fixtures."""
from pathlib import Path
import subprocess
import tempfile

from .native_compile import PIN as SOLC
from .product_census_header import pinned
from .product_notice_ranking import ISOLATE
from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .product_solidity_headers import FORGE_SHA
from .safe_io import MAX_BYTES, canonical, strict_json

REPOSITORIES = {'crytic/properties': 'executable',
                'immunefi-team/forge-poc-templates': 'executable'}
SCOPES = {
    'crytic/properties': 'Execute three unchanged ERC20 balance/supply properties against own broken and repaired ledgers.',
    'immunefi-team/forge-poc-templates': 'Execute upstream fee-transfer and false-return token controls to validate local transfer accounting.',
}
PINS = 'superhunter/product_supply/contract-properties-native-pins.json'
PINS_SHA = 'f65ee692dc507c7963ae0de30f27cf73144312e8f01258ef100d9f078c022007'
HARNESS = 'superhunter/product_supply/contract-properties-native-owned.txt'
HARNESS_SHA = 'e2fcb6c81ccbc5a457f7c490b0c49177f7832e7dc494058e05112ef75c1c6177'
TESTS = {
    'crytic/properties': {f'testCrytic{prop}{case}()' for prop in ('Balance', 'Aggregate', 'ZeroBalance')
                         for case in ('Violation', 'Repaired')},
    'immunefi-team/forge-poc-templates': {'testImmunefiFeeAccounting()', 'testImmunefiZeroFeeControl()',
        'testImmunefiFalseReturnNoCredit()', 'testImmunefiSuccessReturnCredit()'},
}


def reconcile(raw):
    data = strict_json(raw)
    if set(data) != {'test/Owned.t.sol:OwnedPropertiesReplayTest'}:
        raise EvidenceError('unexpected own property test contract')
    suite = data['test/Owned.t.sol:OwnedPropertiesReplayTest']
    tests = suite.get('test_results', {})
    if set(tests) != set.union(*TESTS.values()) or suite.get('warnings') != []:
        raise EvidenceError('incomplete own property controls')
    result = {}
    for name, row in tests.items():
        try:
            gas = row['kind']['Unit']['gas']
            if (row['status'] != 'Success' or row['reason'] is not None or
                    row['counterexample'] is not None or type(gas) is not int or gas <= 0):
                raise EvidenceError('own native property control did not pass')
        except (KeyError, TypeError) as exc:
            raise EvidenceError('malformed own native property control') from exc
        result[name] = {'status': row['status'], 'gas': gas}
    return {repo: {name: result[name] for name in sorted(names)} for repo, names in TESTS.items()}


def run(kit):
    pins = strict_json(pinned(ROOT, PINS, PINS_SHA))['sources']
    harness = pinned(ROOT, HARNESS, HARNESS_SHA)
    with tempfile.TemporaryDirectory(prefix='nqc-contract-properties-') as tmp:
        work, kit = Path(tmp), Path(kit)
        copy_release('solc', kit/'solc', work/'solc', SOLC['sha256'])
        copy_release('forge', kit/'forge', work/'forge', FORGE_SHA)
        for row in pins:
            target = work/row['kit_path']
            target.parent.mkdir(parents=True, exist_ok=True)
            copy_release(row['source_path'], kit/row['kit_path'], target, row['sha256'], executable=False)
        (work/'test').mkdir()
        (work/'test/Owned.t.sol').write_bytes(harness)
        (work/'foundry.toml').write_text('[profile.default]\nevm_version = "paris"\noffline = true\noptimizer = false\nremappings = ["forge-std/=lib/forge-std/"]\n')
        proc = subprocess.run([*ISOLATE, work/'forge', 'test', '--root', work, '--use', work/'solc',
            '--offline', '--match-contract', 'OwnedPropertiesReplayTest', '--json'], cwd=work,
            env={'HOME': tmp, 'TMPDIR': tmp, 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'},
            capture_output=True, timeout=120, check=True)
        if proc.stderr or len(proc.stdout) > MAX_BYTES:
            raise EvidenceError('unexpected property execution output')
        tests = reconcile(proc.stdout)
    tools = {}
    for repo in REPOSITORIES:
        sources = [row for row in pins if row['repository'] == repo]
        tools[repo] = {'catalog_revision': sources[0]['revision'], 'scope': SCOPES[repo],
                       'executed_source_files': len(sources), 'source_set_sha256': sha(canonical(sources))}
    return {'tools': tools, 'native_tests': tests, 'source_pins_sha256': PINS_SHA,
            'owned_harness_sha256': HARNESS_SHA, 'solc_sha256': SOLC['sha256'], 'forge_sha256': FORGE_SHA,
            'properties': ['user balance <= total supply', 'selected balances sum <= total supply',
                           'zero address balance == zero'],
            'token_controls': {'fee_transfer': {'sent': 10, 'received': 8, 'fee': 2},
                               'zero_fee': {'sent': 10, 'received': 10, 'fee': 0},
                               'false_return': {'requested': 101, 'received': 0, 'sender_balance': 100},
                               'successful_return': {'requested': 10, 'received': 10, 'sender_balance': 90}},
            'interpretation': 'Known local controls only. Broken own ledgers must produce Solidity assertion panic 1; repaired controls must return successfully. Fee-transfer and false-return behavior use unchanged upstream simulation contracts. No third-party live target, new vulnerability or general ERC20 compliance claim.'}
