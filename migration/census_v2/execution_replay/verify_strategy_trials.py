#!/usr/bin/env python3
"""Authenticate retained trial sources, outcomes, failures and offline RPC replay."""
import argparse
import json
from pathlib import Path
import re
import tempfile
import zipfile

from native_realization import NATIVE_SOURCE_SHA, WITNESS_SHA
from run_fork import TEST_PATH, FORGE_SHA, SOLC_SHA
from rpc_witness import Witness, canonical, sha
from verify_native import verify as verify_parent

HERE = Path(__file__).resolve().parent
ARCHIVE_SHA = 'f5d4b38801e98f46d72116a22806ec6484507f5ffd2459622679ac938617ffea'
PARENT_SHA = '46bdc3d97787154e286a8c210bdfdf07d2faf4788dc0fd8d52dc58357dd0643a'
TESTS = {'testAaveWithSameBidCannotRepayAndRollsBack', 'testAtomicNativeRealizationPreservesPriorInventory',
         'testBalancerBeforeEligibilityRollsBack', 'testImpossibleProfitClaimRevertsAndCannotSpendExistingBalances',
         'testNativeRealizationRevertPreservesAllBalances', 'testZeroOwnWethFeeWithoutExternalSponsorHasPositiveForkSurplus'}


def need(ok, message):
    if not ok: raise ValueError(message)


def metrics(raw):
    text = raw.decode()
    passed = re.findall(r'^\[PASS\] (\w+)\(\)', text, re.M)
    need(len(passed) == 6 and set(passed) == TESTS and '[FAIL' not in text and
         '6 passed; 0 failed; 0 skipped' in text, 'six successful exact tests missing')
    pairs = re.findall(r'^  NQC_TRIAL_([A-Z_]+): ([0-9]+)$', text, re.M)
    need(len(pairs) == 3 and len(dict(pairs)) == 3, 'trial metrics missing or duplicated')
    values = {k: int(v) for k, v in pairs}
    need(values == {'AAVE_FEE_WEI': 5342006927278914,
                    'AAVE_SHORTFALL_BEFORE_GAS_WEI': 5101616615551362,
                    'REJECTED_PREVIOUS_HF_WAD': 1000000001993818630}, 'trial economic boundary drift')
    need('InsufficientForRepaymentAndProfit(10689355861485106786' in text,
         'exact Aave repayment rejection missing')
    need('custom error 0x930bb771' in text, 'exact historical health factor rejection missing')
    return values


def verify(path):
    need(sha(Path(path).read_bytes()) == ARCHIVE_SHA, 'trial archive digest')
    parent = HERE / 'inputs/native-realization.zip'
    parent_result = verify_parent(parent)
    replay_counts, trial_metrics = {}, {}
    with zipfile.ZipFile(path) as z, zipfile.ZipFile(parent) as p:
        manifest = json.loads(z.read('manifest.json'))
        need(manifest['native_parent_archive_sha256'] == PARENT_SHA, 'native parent identity')
        need(len(z.namelist()) == len(set(z.namelist())) == 26 and
             set(z.namelist()) == set(manifest['files']) | {'manifest.json'}, 'trial archive membership')
        for name, pin in manifest['files'].items():
            raw = z.read(name)
            need((len(raw), sha(raw)) == (pin['bytes'], pin['sha256']), 'trial member digest')
        for attempt, version in [('offline-001', 'producer-v1'), ('offline-002', 'producer-v2')]:
            r = json.loads(z.read(attempt + '/report.json'))
            registration_raw = z.read(attempt + '/registration.json')
            registration = json.loads(registration_raw)
            need(sha(registration_raw) == r['registration_sha256'], 'registration identity')
            need(registration['archive_sha256'] == PARENT_SHA and
                 registration['forge_sha256'] == FORGE_SHA and registration['solc_sha256'] == SOLC_SHA,
                 'registered toolchain or input changed')
            producer = z.read(version + '/run_strategy_trials.py')
            need(sha(producer) == r['producer_sha256'] == sha((HERE / 'run_strategy_trials.py').read_bytes()), 'producer drift')
            extension = z.read(version + '/strategy_trials.sol')
            need(sha(extension) == registration['extension_sha256'], 'extension drift')
            baseline = p.read('offline-001/source/' + TEST_PATH)
            effective = z.read(attempt + '/source/' + TEST_PATH)
            need(sha(baseline) == NATIVE_SOURCE_SHA and effective == baseline + b'\n' + extension and
                 sha(effective) == registration['effective_test_sha256'], 'existing test assertions changed')
            for name in ['src/NqcFlashFundingExecutor.sol', 'foundry.toml']:
                need(z.read(attempt + '/source/' + name) == p.read('offline-001/source/' + name), 'original executor or config changed')
            need(sha(z.read(attempt + '/witness.jsonl')) == WITNESS_SHA and
                 z.read(attempt + '/witness.jsonl') == p.read('witness.jsonl'), 'witness substituted')
            need(r['mode'] == 'OFFLINE_ONLY' and r['upstream_requests'] == 0 and
                 r['historical_cases'] == 1 and r['success_probability'] is None and r['complete_profit_wei'] is None,
                 'unsupported economic or network claim')
            need(all(r[k] is False for k in ['census_closed', 'independent_certification', 'live_transaction_sent',
                                            'original_executor_modified', 'production_gas_quote_proven']), 'unsupported authority')
            expected_modes = ['build', 'normal'] if attempt == 'offline-001' else ['build', 'normal', 'isolated']
            need([run['mode'] for run in r['runs']] == expected_modes, 'run inventory')
            for run in r['runs']:
                raw = z.read(attempt + '/' + run['mode'] + '.log')
                need(sha(raw) == run['log_sha256'], 'log identity')
                expected_exit = 1 if attempt == 'offline-001' and run['mode'] == 'normal' else 0
                need(run['exit_code'] == expected_exit, 'run exit claim')
                if attempt == 'offline-002' and run['mode'] != 'build':
                    trial_metrics[run['mode']] = metrics(raw)
            if attempt == 'offline-001':
                need(r['status'] == 'FAILED' and r['failure'] == 'failed: normal', 'failed trial concealed')
                bad = z.read(attempt + '/normal.log').decode()
                need('4 passed; 2 failed; 0 skipped' in bad and 'offline witness miss' in bad and
                     'UNEXPECTED_REJECTION_REASON' in bad, 'failure history missing')
            else:
                need(r['status'] == 'BOUNDARIES_REPRODUCED_NOT_ECONOMIC_ADMISSION', 'successful status')
                need(extension == (HERE / 'strategy_trials.sol').read_bytes(), 'current trial source drift')
            with tempfile.TemporaryDirectory() as d:
                replay = Path(d) / 'witness.jsonl'; replay.write_bytes(z.read(attempt + '/witness.jsonl'))
                w = Witness(Path(d) / 'rpc', replay=replay, provider='nodies')
                need(len(w.cache) == 127, 'retained state population')
                requests = [json.loads(l) for l in z.read(attempt + '/rpc/requests.jsonl').splitlines()]
                for request in requests:
                    value = w.call(request['method'], request['params'])
                    need(request['source'] == 'retained_response' and sha(canonical(value).encode()) == request['result_sha256'], 'RPC replay mismatch')
                need(w.count == 0, 'network unexpectedly opened')
                replay_counts[attempt] = len(requests)
            errors = [json.loads(l) for l in z.read(attempt + '/rpc/client-errors.jsonl').splitlines()]
            need(len(errors) == 2, 'client error inventory')
            if attempt == 'offline-002':
                need(all(e['request']['method'] == 'eth_getAccountInfo' and
                         e['error'] == 'method or parameters outside read-only scope' for e in errors), 'unresolved successful-run state miss')
    return {'schema': 'nqc-strategy-boundary-readback-v1', 'archive_sha256': ARCHIVE_SHA,
            'consumer_sha256': sha(Path(__file__).read_bytes()), 'parent_readback_sha256': sha(canonical(parent_result).encode()),
            'metrics': trial_metrics, 'offline_response_bindings_verified': replay_counts, 'upstream_requests': 0,
            'historical_cases': 1, 'new_trials': 2, 'new_holdout_cases': 0,
            'failed_first_attempt_retained': True, 'original_executor_modified': False,
            'complete_profit_wei': None, 'capture_probability': None, 'census_closed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args(); Path(args.output).write_text(canonical(verify(args.archive)) + '\n')
