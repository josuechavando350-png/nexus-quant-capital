#!/usr/bin/env python3
"""Prepare a fresh overlay and run local admission boundary regression tests."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'robinhood-aa-20261016'


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('overlay precondition failed: ' + old)
    return text.replace(old, new, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dependencies', type=Path, required=True)
    ap.add_argument('--foundry-bin', type=Path, required=True)
    ap.add_argument('--solc-019', type=Path, required=True)
    ap.add_argument('--solc-023', type=Path, required=True)
    ap.add_argument('--build', type=Path, required=True)
    args = ap.parse_args()
    lock = json.loads((PREVIOUS / 'toolchain.json').read_text())
    binaries = [(args.foundry_bin / name, digest) for name, digest in lock['binary_sha256'].items()]
    for path, expected in binaries + [(args.solc_019, lock['solc']['0.8.19']), (args.solc_023, lock['solc']['0.8.23'])]:
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('tool identity: ' + str(path))
    subprocess.run([sys.executable, str(PREVIOUS / 'prepare.py'), '--dependencies', str(args.dependencies),
                    '--build', str(args.build)], check=True, stdout=subprocess.DEVNULL)
    shutil.copy2(HERE / 'test/NqcAdmission.t.sol', args.build / 'robinhood/test/NqcAdmission.t.sol')
    # Correct fresh copies only. Keep the previous research and all archived bytes intact.
    previous_test = args.build / 'robinhood/test/NqcRobinhoodCycle.t.sol'
    previous_test.write_text(replace_once(previous_test.read_text(),
        'vm.store(EP,bytes32(0),bytes32(uint256(1)))',
        'vm.store(EP,bytes32(uint256(2)),bytes32(uint256(1)))'))
    runtime = PREVIOUS / 'evidence/runtime.json'
    code = bytes.fromhex(json.loads(runtime.read_text())['runtime'][2:])
    if hashlib.sha256(code).hexdigest() != '674d73ee2acf6d72a5b32b6e05150b9ddcfcee0429a0e7914929faccbc2bf4d5':
        raise ValueError('EntryPoint runtime identity')
    shutil.copy2(runtime, args.build / 'robinhood/runtime.json')
    results = args.build / 'results'
    results.mkdir()
    for lab, compiler, contract in [('morpho-native-lab', args.solc_019, 'NqcMorphoNativeCallbackLabTest'),
                                    ('baseline', args.solc_023, 'NqcRealEntryPointV07GasSponsorTest'),
                                    ('robinhood', args.solc_023, 'Nqc(Admission|RobinhoodCycle)Test')]:
        log = results / (lab + '.txt')
        with log.open('w') as file:
            subprocess.run([str(args.foundry_bin / 'forge'), 'test', '--root', str(args.build / lab),
                            '--use', str(compiler), '--match-contract', contract, '-vv'],
                           stdout=file, stderr=subprocess.STDOUT, check=True)
        print('PASS: ' + str(log), flush=True)
    layout = json.loads(subprocess.check_output([str(args.foundry_bin / 'forge'), 'inspect', 'EntryPoint',
        'storage-layout', '--root', str(args.build / 'robinhood'), '--use', str(args.solc_023), '--json'], text=True))
    status = [slot for slot in layout['storage'] if slot['label'] == '_status']
    if len(status) != 1 or status[0]['slot'] != '2' or status[0]['offset'] != 0:
        raise ValueError('unexpected EntryPoint guard storage layout')
    (results / 'entrypoint-storage-layout.json').write_text(json.dumps(layout, indent=2) + '\n')
    scripts = args.build / 'corrected-local-scripts'
    scripts.mkdir()
    shutil.copy2(PREVIOUS / 'run_local.py', scripts / 'run_local.py')
    local = replace_once((PREVIOUS / 'local_receipts.py').read_text(),
        "rpc('anvil_setStorageAt',[EP,'0x'+'00'*32,'0x'+'00'*31+'01'])",
        "rpc('anvil_setStorageAt',[EP,'0x'+'00'*31+'02','0x'+'00'*31+'01'])\n"
        "    assert int(rpc('eth_getStorageAt',[EP,'0x2','latest']),16)==1\n"
        "    assert int(rpc('eth_getStorageAt',[EP,'0x0','latest']),16)==0")
    local = replace_once(local, "'nqc_realized_usd':'0','deployment_receipt':deployment,'records':records}",
        "'nqc_realized_usd':'0','deployment_receipt':deployment,'records':records,\n"
        "        'entrypoint_constructor_state':{'guard_slot':2,'guard_initial_value':1,'mapping_root_untouched':True}}")
    (scripts / 'local_receipts.py').write_text(local)
    with (results / 'local-receipts.txt').open('w') as file:
        subprocess.run([sys.executable, str(scripts / 'run_local.py'), '--foundry-bin', str(args.foundry_bin),
            '--build', str(args.build), '--out', str(results / 'local')], stdout=file, stderr=subprocess.STDOUT, check=True)
    print('PASS: corrected constructor state, compiler layout and seven cold receipts', flush=True)
    provenance = {'base_research': 'migration/robinhood-aa-20261016',
                  'producer_base_commit': '1c912476c6e0179a84e301ca708736e6e250a446',
                  'toolchain': lock, 'scope': 'LOCAL_TESTS_NOT_FULL_BUNDLER_ADMISSION',
                  'entrypoint_guard_slot': 2,
                  'source_overlays': ['fresh NqcRobinhoodCycle.t.sol: initialize guard slot 2',
                                      'fresh local_receipts.py: initialize and assert guard slot 2'],
                  'corrected_runner_sha256': hashlib.sha256(local.encode()).hexdigest(),
                  'added_test_sha256': hashlib.sha256((HERE / 'test/NqcAdmission.t.sol').read_bytes()).hexdigest()}
    (results / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')


if __name__ == '__main__':
    main()
