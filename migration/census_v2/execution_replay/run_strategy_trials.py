#!/usr/bin/env python3
"""Bounded offline trials over one already-selected historical fork witness."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import zipfile

from native_realization import NATIVE_SOURCE_SHA, WITNESS_SHA
from run_fork import TEST_PATH, FORGE_SHA, SOLC_SHA
from run_comparison import INPUTS_SHA
from rpc_witness import Witness, serve, canonical, sha, now, PREVIOUS, WINNER

BASE = 'a1292b8a46e225934b1e1c5f375418718739a68b'
ARCHIVE_SHA = '46bdc3d97787154e286a8c210bdfdf07d2faf4788dc0fd8d52dc58357dd0643a'
HERE = Path(__file__).resolve().parent


def run(args):
    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'nqc-strategy-boundary-trials-v1', 'source_commit': BASE,
              'started_at': now(), 'mode': 'OFFLINE_ONLY', 'status': 'FAILED', 'runs': [],
              'historical_cases': 1, 'selection': 'RETROSPECTIVE_ALREADY_EXAMINED_CASE',
              'complete_profit_wei': None, 'census_closed': False,
              'independent_certification': False, 'live_transaction_sent': False,
              'original_executor_modified': False, 'production_gas_quote_proven': False,
              'success_probability': None, 'producer_sha256': sha(Path(__file__).read_bytes())}
    server = witness = None
    try:
        raw = Path(args.archive).read_bytes()
        assert sha(raw) == ARCHIVE_SHA, 'native archive identity'
        assert sha(Path(args.forge).read_bytes()) == FORGE_SHA, 'forge identity'
        assert sha(Path(args.solc).read_bytes()) == SOLC_SHA, 'solc identity'
        extension = (HERE / 'strategy_trials.sol').read_bytes()
        with zipfile.ZipFile(args.archive) as z:
            manifest_raw = z.read('inputs/sources.json')
            assert sha(manifest_raw) == INPUTS_SHA, 'input manifest'
            manifest = json.loads(manifest_raw)
            source = root / 'source'
            for name, pin in manifest['files'].items():
                original = z.read('inputs/' + name)
                effective = z.read('offline-001/source/' + name)
                assert sha(original) == pin['sha256'], 'original source'
                assert sha(effective) == (NATIVE_SOURCE_SHA if name == TEST_PATH else pin['sha256']), 'effective source'
                dst = source / name
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(effective + b'\n' + extension if name == TEST_PATH else effective)
            witness_bytes = z.read('witness.jsonl')
            assert sha(witness_bytes) == WITNESS_SHA, 'witness identity'
            replay = root / 'witness.jsonl'; replay.write_bytes(witness_bytes)
        # Retain this registration before any compilation or execution.
        registration = {'source_commit': BASE, 'archive_sha256': ARCHIVE_SHA,
            'extension_sha256': sha(extension), 'effective_test_sha256': sha((source / TEST_PATH).read_bytes()),
            'executor_sha256': sha((source / 'src/NqcFlashFundingExecutor.sol').read_bytes()),
            'witness_sha256': WITNESS_SHA, 'forge_sha256': FORGE_SHA, 'solc_sha256': SOLC_SHA,
            'registered_at': now(), 'existing_tests_retained': 4,
            'new_trials': ['Aave same principal, payment and minimum profit: exact repayment rejection',
                           'Balancer at predecessor timestamp: exact eligibility rejection'],
            'new_sample': False, 'selection_bias_removed': False}
        (root / 'registration.json').write_text(canonical(registration) + '\n')
        report['registration_sha256'] = sha((root / 'registration.json').read_bytes())
        for mode in ['build', 'normal', 'isolated']:
            cmd = [args.forge, 'build' if mode == 'build' else 'test', '--root', str(source),
                   '--use', args.solc, '--offline']
            env = dict(os.environ)
            if mode != 'build':
                if witness is None:
                    witness = Witness(root / 'rpc', replay=replay, provider='nodies')
                    server = serve(witness)
                previous = witness.call('eth_getBlockByNumber', [hex(PREVIOUS), False])
                winner = witness.call('eth_getBlockByNumber', [hex(WINNER), False])
                env.update(NQC_RMC016_RANK1_BORROWER=manifest['borrower'],
                           NQC_RMC016_RANK1_PREVIOUS_TIMESTAMP=str(int(previous['timestamp'], 16)),
                           NQC_RMC016_RANK1_WINNER_TIMESTAMP=str(int(winner['timestamp'], 16)))
                cmd += ['--fork-url', 'http://127.0.0.1:' + str(server.server_address[1]),
                        '--fork-block-number', str(PREVIOUS), '--fork-retries', '0', '--no-storage-caching',
                        '--gas-price', '0', '--threads', '1', '--color', 'never',
                        '--match-contract', 'NqcStrategyBoundaryForkTest', '-vvvv']
                if mode == 'isolated': cmd += ['--isolate']
            log = root / (mode + '.log')
            with log.open('w') as f:
                result = subprocess.run(cmd, cwd=source, env=env, stdout=f, stderr=subprocess.STDOUT,
                                        timeout=180, check=False)
            report['runs'].append({'mode': mode, 'command': cmd, 'exit_code': result.returncode,
                                   'log_sha256': sha(log.read_bytes())})
            if result.returncode: raise RuntimeError('failed: ' + mode)
        report['status'] = 'BOUNDARIES_REPRODUCED_NOT_ECONOMIC_ADMISSION'
    except Exception as error:
        report['failure'] = str(error)
    finally:
        if server: server.shutdown(); server.server_close()
        report.update(finished_at=now(), upstream_requests=witness.count if witness else 0)
        (root / 'report.json').write_text(canonical(report) + '\n')
    print(canonical(report), flush=True)
    return int(report['status'] == 'FAILED')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['out', 'archive', 'forge', 'solc']: parser.add_argument('--' + name, required=True)
    raise SystemExit(run(parser.parse_args()))
