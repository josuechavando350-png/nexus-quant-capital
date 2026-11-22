"""Native Slither diagnostics and crytic compilation on three immutable own sources."""
from pathlib import Path
import subprocess
import sys
import tempfile
from zipfile import ZipFile

from . import owned_slither_cases as controls, static_review
from .native_compile import PIN as SOLC
from .product_slither_native_network import LIBRARY_SHA, expected_proof
from .product_census_header import pinned
from .product_notice_ranking import ISOLATE
from .product_reasoning import EvidenceError
from .product_review import ROOT, copy_release, sha
from .safe_io import MAX_BYTES, canonical, strict_json

REPOSITORIES = {'crytic/slither': 'executable', 'crytic/crytic-compile': 'executable'}
SCOPES = {
    'crytic/slither': 'Execute tx-origin on three immutable own controls and bind diagnostics to exact source ranges.',
    'crytic/crytic-compile': 'Compile three immutable own controls; compare ABI, AST, creation and runtime bytecode with direct solc.',
}
REVISIONS = {
    'crytic/slither': '97c1d10d8107e76a9426dd484c03c1afd846c186',
    'crytic/crytic-compile': '7e8a89ddd7718d387b0c7b4e43a7391e1a6d79f3',
}
PINS = 'superhunter/product_supply/slither-native-pins.json'
PINS_SHA = 'fb6a9e23a5a66e5a63aa01097e50c0924d6b898a3053d974858651bd70d81087'


def compile_input(source):
    return {'language': 'Solidity', 'sources': {'Owned.sol': {'content': source.decode()}},
            'settings': {'optimizer': {'enabled': False}, 'evmVersion': 'cancun',
                         'metadata': {'bytecodeHash': 'none'},
                         'outputSelection': {'*': {'': ['ast'], '*': [
                             'abi', 'evm.bytecode.object', 'evm.deployedBytecode.object']}}}}


def observe(name, native, reference):
    """Reconcile actual native outputs; never manufacture missing compiler or detector data."""
    if name not in controls.SOURCES:
        raise EvidenceError('unknown owned Slither case')
    if any(row.get('severity') == 'error' for row in reference.get('errors', [])):
        raise EvidenceError('owned direct compiler failed')
    try:
        contract = reference['contracts']['Owned.sol']['OwnedFixture']
        ast = reference['sources']['Owned.sol']['ast']
        abi, runtime, init = contract['abi'], contract['evm']['deployedBytecode']['object'], contract['evm']['bytecode']['object']
        if (set(reference['contracts']) != {'Owned.sol'} or
                set(reference['contracts']['Owned.sol']) != {'OwnedFixture'} or
                native['abis'] != {'OwnedFixture': abi} or
                native['runtimes'] != {'OwnedFixture': runtime} or
                native['inits'] != {'OwnedFixture': init} or native['ast'] != ast or
                not runtime or not init or not abi or not ast):
            raise EvidenceError('crytic-compile disagrees with direct solc')
        runtime_raw, init_raw = bytes.fromhex(runtime), bytes.fromhex(init)
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidenceError('invalid owned compiler evidence') from exc
    source = controls.SOURCES[name]
    report = canonical({'success': True, 'error': None, 'results': {'detectors': native['detectors']}})
    normalized = static_review.normalize(report, controls.context(name, sha(report)), {'Owned.sol': source})
    count = 1 if name == 'positive' else 0
    if (not normalized['normalization_complete'] or normalized['unbound_alerts'] or
            normalized['raw_alert_count'] != count or normalized['unique_alert_count'] != count):
        raise EvidenceError('Slither owned positive or negative control disagrees')
    alerts = []
    for alert in normalized['alerts']:
        if (alert['check'] != 'tx-origin' or alert['tool_impact'] != 'Medium' or
                alert['tool_confidence'] != 'Medium' or alert['occurrences'] != 1):
            raise EvidenceError('unexpected owned Slither diagnostic')
        nodes = [loc for loc in alert['locations'] if loc['element_type'] == 'node']
        if (len(nodes) != 1 or source[nodes[0]['start_byte']:nodes[0]['start_byte']+nodes[0]['length_bytes']]
                != b'require(tx.origin == owner, "owner")'):
            raise EvidenceError('Slither diagnostic does not identify the owned authorization expression')
        alerts.append({key: alert[key] for key in (
            'fingerprint', 'check', 'tool_impact', 'tool_confidence', 'locations', 'occurrences')})
    return {'source_sha256': sha(source), 'abi': abi, 'ast_sha256': sha(canonical(ast)),
            'runtime_sha256': sha(runtime_raw), 'runtime_bytes': len(runtime_raw),
            'creation_sha256': sha(init_raw), 'creation_bytes': len(init_raw),
            'crytic_matches_direct_solc': True, 'alerts': alerts, 'alert_count': count}


def reconcile(native, reference):
    if (set(native) != {'cases', 'network'} or native['network'] != expected_proof() or
            set(native['cases']) != set(controls.SOURCES) or set(reference) != set(controls.SOURCES)):
        raise EvidenceError('incomplete native Slither controls or network proof')
    return {name: observe(name, native['cases'][name], reference[name]) for name in sorted(controls.SOURCES)}


def run(kit):
    if sys.version_info[:2] != (3, 12):
        raise EvidenceError('Slither native kit requires CPython 3.12')
    provenance = controls.fixture_provenance()
    pin_bytes = pinned(ROOT, PINS, PINS_SHA)
    pins = strict_json(pin_bytes)['packages']
    with tempfile.TemporaryDirectory(prefix='nqc-slither-native-') as tmp:
        work, kit = Path(tmp), Path(kit)
        copy_release('solc', kit/'solc', work/'solc', SOLC['sha256'])
        copy_release('libseccomp', kit/'libseccomp.so.2', work/'libseccomp.so.2',
                     LIBRARY_SHA, executable=False)
        for index, row in enumerate(pins):
            archive = work/f'distribution-{index}.whl'
            copy_release(row['name'], kit/row['filename'], archive, row['sha256'], executable=False)
            with ZipFile(archive) as wheel:
                wheel.extractall(work/'packages'/row['directory'])
        (work/'packages.json').write_bytes(pin_bytes)
        for name, source in controls.SOURCES.items():
            (work/name).mkdir()
            (work/name/'Owned.sol').write_bytes(source)
        env = {'HOME': tmp, 'TMPDIR': tmp, 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}
        def execute(command, data=None):
            proc = subprocess.run([*ISOLATE, *command], input=data, capture_output=True,
                                  cwd=work, env=env, timeout=120, check=True)
            if len(proc.stdout) > MAX_BYTES or len(proc.stderr) > MAX_BYTES:
                raise EvidenceError('native Slither output exceeds budget')
            return strict_json(proc.stdout)
        native = execute([sys.executable, '-I', '-B', '-S',
                          Path(__file__).with_name('product_slither_native_worker.py')])
        reference = {name: execute([work/'solc', '--no-import-callback', '--standard-json'],
                                  canonical(compile_input(source)))
                     for name, source in controls.SOURCES.items()}
        cases = reconcile(native, reference)
    tools = {}
    for repo, name, count in [('crytic/slither', 'slither-analyzer', 538),
                              ('crytic/crytic-compile', 'crytic-compile', 41)]:
        row = next(row for row in pins if row['name'] == name)
        tools[repo] = {'version': row['version'], 'catalog_revision': REVISIONS[repo],
                       'wheel_sha256': row['sha256'], 'scope': SCOPES[repo],
                       'executed_form': 'official PyPI wheel',
                       'python_source_files_matching_catalog': count}
    return {'cases': cases, 'tools': tools, 'fixture_provenance': provenance,
            'solc': {'version': SOLC['version'], 'binary_sha256': SOLC['sha256']},
            'dependency_lock_sha256': PINS_SHA, 'pinned_distributions': len(pins),
            'network': native['network'], 'detector': 'tx-origin',
            'counts': {'tp': 1, 'tn': 2, 'fp': 0, 'fn': 0},
            'interpretation': 'Three known owned controls only. Direct solc and crytic-compile share the compiler. The tx.origin/msg.sender comparison is a detector exclusion, not proof of contract security. No external target or original vulnerability.'}
