"""Retained time-only fork diagnostics bound to predecessor-state evidence.

Two operators corroborated timestamps; only dRPC supplied the original forks.
Endpoint measurements neither locate a first crossing nor prove an actual
intra-block cause, prospective discovery, execution or complete profit.
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import re
import tempfile

from cashflow_intake import PRICE_NAMES, verify_cashflow
from evidence_store import admit, read_batch, safe_path
from historical_intake import (API, AUTHORITIES, EVIDENCE, ROOT, SOURCE, SOURCE_ID,
    fields, need, same, unpack, utc, verify_ledger)
from historical_pipeline import LEDGER_NAME, SOURCE_NAMES
from historical_state_intake import (REPORT_NAME as STATE_REPORT, STATE_NAMES,
    WAD, build_state_report, store_state_report, uint, verify_state_report)
from integrity import canonical, digest, read_regular, strict_json
from liquidator_intake import CAPTURE_NAMES, build_liquidator_report

SCHEMA = 'nqc.omega.retained-time-only-diagnostic.v1'
PIN_SHA256 = '35d536ca5a238f3c2c76f8a63edd76fed5fbb02f5a715a07645a68284e07bb83'
TEMPORAL_NAMES = {'temporal-pin.json', 'temporal-original.zip', 'temporal-metadata.json'}
REPORT_NAME = 'temporal-report.json'
SOURCE_TEST = 'ci/nqc-census/weth-physical/test/NqcRmc015WethTimeOnlyHF.t.sol'
SOURCE_INPUT = 'ci/nqc-census/rmc015_weth_time_only_inputs.py'
SOURCE_CONFIG = 'ci/nqc-census/weth-physical/foundry-time-only.toml'


def manifest(raw):
    rows = raw.decode('ascii').splitlines()
    result = {}
    for line in rows:
        need(re.fullmatch(r'[0-9a-f]{64}  [a-zA-Z0-9._/-]+', line), 'temporal_manifest_line')
        sha, name = line.split('  ', 1)
        need(name not in result, 'temporal_manifest_duplicate')
        result[name] = sha
    need(bool(result), 'temporal_manifest_empty')
    return result


def load_temporal_source(directory=EVIDENCE, root=ROOT):
    directory, root = Path(directory), Path(root)
    raw = read_regular(directory / 'temporal-pin.json')
    need(digest(raw) == PIN_SHA256, 'temporal_pin_changed')
    pin = strict_json(raw)
    need(canonical(pin) == raw, 'temporal_pin_not_canonical')
    raw_meta = read_regular(directory / 'temporal-metadata.json')
    need(digest(raw_meta) == pin['metadata_sha256'], 'temporal_metadata_changed')
    meta = strict_json(raw_meta)
    run, commit, artifact = (meta[k] for k in ('run', 'commit', 'artifact'))
    fields(run, {'id': pin['run_id'], 'head_sha': pin['commit'], 'head_branch': pin['branch'],
        'status': 'completed', 'conclusion': 'success', 'run_attempt': 1,
        'workflow_id': pin['workflow_id'], 'path': pin['workflow'],
        'url': API + f"/actions/runs/{pin['run_id']}"}, 'temporal_run')
    for key in ('repository', 'head_repository'):
        fields(run[key], {'id': SOURCE_ID, 'full_name': SOURCE, 'private': False}, 'temporal_repo')
    fields(run['head_commit'], {'id': pin['commit'], 'tree_id': pin['tree']}, 'temporal_head')
    fields(commit, {'sha': pin['commit'], 'url': API + '/git/commits/' + pin['commit']}, 'temporal_commit')
    fields(commit['tree'], {'sha': pin['tree']}, 'temporal_tree')
    fields(artifact, {'id': pin['artifact_id'], 'name': pin['artifact_name'],
        'expired': False, 'size_in_bytes': pin['archive_bytes'],
        'digest': 'sha256:' + pin['archive_sha256'],
        'url': API + f"/actions/artifacts/{pin['artifact_id']}"}, 'temporal_artifact')
    fields(artifact['workflow_run'], {'id': pin['run_id'], 'head_sha': pin['commit'],
        'head_branch': pin['branch'], 'repository_id': SOURCE_ID,
        'head_repository_id': SOURCE_ID}, 'temporal_artifact_run')
    need(utc(run['created_at']) <= utc(run['run_started_at']) <= utc(artifact['created_at'])
         <= utc(run['updated_at']) <= utc(meta['retrieved_at']) < utc(artifact['expires_at']),
         'temporal_capture_time')
    archive = read_regular(directory / 'temporal-original.zip', 128 * 1024)
    need(len(archive) == pin['archive_bytes'] and digest(archive) == pin['archive_sha256'],
         'temporal_archive_changed')
    members = unpack(archive, pin['members'])
    same(manifest(members['archive.sha256']),
         {n: digest(b) for n, b in members.items() if n != 'archive.sha256'}, 'temporal_inner_manifest')
    for path, sha in pin['source_files'].items():
        need(digest(read_regular(root / path)) == sha, 'temporal_original_source_changed:' + path)
    same(manifest(members['source-sha256.txt']),
         {p: pin['source_files'][p] for p in (SOURCE_INPUT, SOURCE_TEST)}, 'temporal_source_manifest')
    same(manifest(members['formatted-tested-source.sha256']), {
        'foundry.toml': pin['source_files'][SOURCE_CONFIG],
        'test/NqcRmc015WethTimeOnlyHF.t.sol':
            'ee8f9b688fd8760a7592eaba93debf13215b9b101a5a57b6effa439cc0915841'},
        'temporal_formatted_source_manifest')
    need(b'Compiler run successful!' in members['build.txt'], 'temporal_original_build_missing')
    anchors, conclusion = (strict_json(members[n]) for n in ('anchors.json', 'time-only-conclusion.json'))
    for report in (anchors, conclusion):
        need(report['report_sha256'] == digest(canonical({k: v for k, v in report.items()
             if k != 'report_sha256'})), 'temporal_source_report_commitment')
    provenance = {'repository': SOURCE, 'repository_id': SOURCE_ID, 'run_id': pin['run_id'],
        'producer_commit': pin['commit'], 'producer_tree': pin['tree'],
        'artifact_id': pin['artifact_id'], 'archive_sha256': pin['archive_sha256'],
        'metadata_sha256': pin['metadata_sha256'], 'retrieved_at': meta['retrieved_at'],
        'anchor_report_sha256': anchors['report_sha256'],
        'conclusion_report_sha256': conclusion['report_sha256'],
        'timestamp_operator_count': 2, 'original_fork_provider_ids': ['drpc'],
        'original_fork_provider_count': 1, 'source_files': pin['source_files'],
        'trust_basis': 'REVIEWED_RETAINED_GITHUB_CAPTURE_NOT_FRESH_CHAIN_OBSERVATION'}
    return anchors, conclusion, members, provenance


def read_measurement(raw):
    log = raw.decode('utf-8')
    need(log.count('[PASS] testPreviousHealthFactorAndWinnerTimestampOnly()') == 1
         and log.count('Suite result: ok. 1 passed; 0 failed; 0 skipped;') == 1
         and '[FAIL' not in log, 'temporal_fork_not_pass')
    values = {}
    for name in ('HF_BEFORE_WAD', 'HF_AFTER_WAD', 'COLLATERAL_BASE_AFTER',
                 'DEBT_BASE_AFTER', 'CROSSED_BELOW_ONE'):
        matches = re.findall(r'^\s*NQC_TIME_ONLY_' + name + r': ([^\r\n]+)\s*$', log, re.MULTILINE)
        need(len(matches) == 1, 'temporal_measurement_count:' + name)
        values[name] = uint(matches[0])
    need(all(values[k] > 0 for k in ('HF_BEFORE_WAD', 'HF_AFTER_WAD',
             'COLLATERAL_BASE_AFTER', 'DEBT_BASE_AFTER')), 'temporal_zero_account_value')
    need(values['HF_BEFORE_WAD'] > WAD, 'temporal_predecessor_not_healthy')
    need(values['CROSSED_BELOW_ONE'] == int(values['HF_AFTER_WAD'] < WAD),
         'temporal_crossing_marker')
    return values


def validate_temporal_join(state, anchors, conclusion, members):
    fields(anchors, {'schema_version': 1,
        'status': 'RMC015_REAL_TOP3_WETH_PREBLOCK_AND_WINNER_TIME_ANCHORS_PASS',
        'source_artifact_sha256': state['source_provenance']['top3-health']['archive_sha256'],
        'source_report_sha256': state['source_provenance']['top3-health']['source_report_sha256'],
        'historical_retroactively_selected_competitor_count': 3,
        'source_all_three_previous_health_factors_above_one': True,
        'source_time_window_verified_for_all_three': True,
        'source_two_operator_time_consensus': True, 'time_only_fork_execution_performed': False,
        'actual_intrablock_trigger_certified': False, 'capturable_ex_ante_opportunity_proven': False,
        'actual_nexus_liquidation_or_positive_pnl_proven': False,
        'own_capital_zero_gas_sponsor_proven': False, 'real_market_census_closed': False}, 'temporal_anchors')
    fields(conclusion, {'schema_version': 1,
        'status': 'RMC015_TOP3_TIME_ONLY_REAL_FORK_DIAGNOSTIC_PASS',
        'observed_case_count': 3, 'selected_using_future_winners': True,
        # Preserve the original source's spelling; do not silently rewrite it.
        'intrablack_original_transactions_replayed': False,
        'nexus_execution_or_capture_proven': False, 'external_gas_and_flash_funding_proven': False,
        'nexus_net_profit_proven': False, 'real_market_census_closed': False}, 'temporal_conclusion')
    operators = anchors['operator_progress']
    need(type(operators) is list and len(operators) == 2, 'temporal_operator_count')
    for p, pid, operator in zip(operators, ('drpc', 'blast'), ('dRPC', 'BlastAPI')):
        fields(p, {'provider_id': pid, 'operator': operator}, 'temporal_operator')
        same(p['time_records'], anchors['canonical_time_anchors'], 'temporal_operator_disagreement')
    rows, measurements = anchors['canonical_time_anchors'], conclusion['measurements']
    need(type(rows) is list and len(rows) == 3 and type(measurements) is list
         and len(measurements) == 3 and len(state['records']) == 9, 'temporal_row_inventory')
    witnesses = []
    for rank, (row, measurement, cash) in enumerate(zip(rows, measurements, state['records']), 1):
        pre = cash['predecessor_state']
        need(pre is not None, 'temporal_missing_predecessor')
        borrower_fingerprint = digest(('0x' + pre['borrower_address'][2:].rjust(64, '0')).encode())
        fields(row, {'rank': rank, 'historical_winner_tx': cash['transaction_hash'],
            'borrower': pre['borrower_address'], 'source_borrower_identity_sha256': borrower_fingerprint,
            'previous_block_number': pre['predecessor_block']['number'],
            'previous_block_hash': pre['predecessor_block']['hash'],
            'winning_block_number': cash['block_number'], 'winning_block_hash': cash['block_hash'],
            'previous_health_factor_wad': pre['account_data']['health_factor_wad']}, 'temporal_identity')
        t0, t1 = row['previous_block_timestamp'], row['winning_block_timestamp']
        need(type(t0) is int and type(t1) is int and 0 < t0 < t1 < 2**64
             and t1 - t0 <= 120, 'temporal_timestamp_window')
        need(row['winning_block_number'] == row['previous_block_number'] + 1, 'temporal_block_order')
        raw = members[f'rank-{rank}.txt']
        values = read_measurement(raw)
        need(str(values['HF_BEFORE_WAD']) == row['previous_health_factor_wad'], 'temporal_before_hf')
        below = values['HF_AFTER_WAD'] < WAD
        fields(measurement, {'rank': rank, 'previous_hf_wad': str(values['HF_BEFORE_WAD']),
            'winner_time_only_hf_wad': str(values['HF_AFTER_WAD']),
            'time_only_below_one': below}, 'temporal_measurement')
        witnesses.append({'transaction_hash': cash['transaction_hash'], 'rank': rank,
            'canonical_anchor': copy.deepcopy(row), 'elapsed_seconds': t1 - t0,
            'previous_hf_wad': str(values['HF_BEFORE_WAD']),
            'time_only_after_hf_wad': str(values['HF_AFTER_WAD']),
            'time_only_hf_delta_wad': str(values['HF_AFTER_WAD'] - values['HF_BEFORE_WAD']),
            'time_only_collateral_base_after': str(values['COLLATERAL_BASE_AFTER']),
            'time_only_debt_base_after': str(values['DEBT_BASE_AFTER']),
            'time_only_below_one': below,
            'threshold_diagnostic': 'TIME_ONLY_ENDPOINT_BELOW_ONE' if below else 'TIME_ONLY_ENDPOINT_NOT_BELOW_ONE',
            'retained_fork_log_sha256': digest(raw), 'original_fork_provider_id': 'drpc',
            'first_crossing_timestamp': None, 'intrablock_transactions_replayed': False,
            'actual_cause_proven': False, 'interest_accrual_cause_proven': False,
            'fresh_fork_execution_performed': False, 'prospective_prediction_proven': False})
    fields(conclusion, {'time_only_below_one_count': sum(w['time_only_below_one'] for w in witnesses)},
           'temporal_crossing_count')
    return witnesses


def build_temporal_report(directory=EVIDENCE, root=ROOT):
    state = build_state_report(directory, root)
    anchors, conclusion, members, provenance = load_temporal_source(directory, root)
    joined = validate_temporal_join(state, anchors, conclusion, members)
    by_tx = {w['transaction_hash']: w for w in joined}
    rows = []
    for original in state['records']:
        row = copy.deepcopy(original)
        row.pop('record_commitment_sha256')
        row['temporal_witness'] = by_tx.get(row['transaction_hash'])
        row['temporal_status'] = ('UNOBSERVED' if row['temporal_witness'] is None
                                  else row['temporal_witness']['threshold_diagnostic'])
        row['decision_blockers'].append('TIME_ONLY_DIAGNOSTIC_NOT_TRANSACTION_PRESTATE'
            if row['temporal_witness'] is not None else 'TEMPORAL_STATE_UNOBSERVED')
        row['record_commitment_sha256'] = digest(canonical(row))
        rows.append(row)
    below = sum(w['time_only_below_one'] for w in joined)
    report = {'schema': SCHEMA, 'status': 'RETAINED_TIME_ONLY_DIAGNOSTIC_JOINED',
        'predecessor_report_commitment': state['report_commitment_sha256'],
        'temporal_source_provenance': provenance, 'records': rows,
        'summary': {'cashflow_transactions': 9, 'historical_corpus_transactions': 127,
            'temporal_diagnostic_count': len(joined), 'time_only_endpoint_below_one_count': below,
            'time_only_endpoint_not_below_one_count': len(joined) - below,
            'temporal_unknown_count': len(rows) - len(joined), 'complete_cost_count': 0,
            'prospectively_discovered_count': 0, 'executable_candidate_count': 0},
        'new_chain_acquisition_performed': False, 'new_temporal_fork_execution_performed': False,
        'original_timestamp_two_operator_agreement': True,
        'original_fork_two_operator_agreement': False, 'actual_transaction_prestate_proven': False,
        'oracle_cause_observed': False, 'oracle_update_delay_blocks': None,
        'nqc_realized_profit_wei': None, 'authorities': dict(AUTHORITIES)}
    report['report_commitment_sha256'] = digest(canonical(report))
    return report


def verify_temporal_report(report, directory=EVIDENCE, root=ROOT):
    expected = build_temporal_report(directory, root)
    same(report, expected, 'temporal_report_differs_from_sources')
    return expected


def store_temporal_report(store, directory=EVIDENCE, root=ROOT):
    base = store_state_report(store, directory, root)
    objects = read_batch(store, base['state_batch'])
    objects.update({n: read_regular(Path(directory) / n) for n in TEMPORAL_NAMES})
    with tempfile.TemporaryDirectory(prefix='omega-temporal-') as tmp:
        for n, b in objects.items(): (Path(tmp) / n).write_bytes(b)
        report = build_temporal_report(Path(tmp), root)
    objects[REPORT_NAME] = canonical(report)
    return {'state_batch': base['state_batch'], 'temporal_batch': admit(store, objects), 'report': report}


def query_temporal_report(store, batch, root=ROOT):
    objects = read_batch(store, batch)
    expected = SOURCE_NAMES | CAPTURE_NAMES | PRICE_NAMES | STATE_NAMES | TEMPORAL_NAMES | {
        LEDGER_NAME, 'liquidator-report.json', 'cashflow-report.json', STATE_REPORT, REPORT_NAME}
    need(set(objects) == expected, 'temporal_batch_inventory')
    with tempfile.TemporaryDirectory(prefix='omega-temporal-query-') as tmp:
        directory = Path(tmp)
        for n, b in objects.items(): (directory / n).write_bytes(b)
        verify_ledger(strict_json(objects[LEDGER_NAME]), directory, root)
        same(strict_json(objects['liquidator-report.json']), build_liquidator_report(directory, root),
             'temporal_identity_differs_from_sources')
        verify_cashflow(strict_json(objects['cashflow-report.json']), directory, root)
        verify_state_report(strict_json(objects[STATE_REPORT]), directory, root)
        return verify_temporal_report(strict_json(objects[REPORT_NAME]), directory, root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=EVIDENCE)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    safe_path(args.out)
    need(not args.out.resolve().is_relative_to(ROOT), 'output_inside_source')
    report = build_temporal_report(args.evidence)
    with args.out.open('xb') as stream: stream.write(canonical(report))
    print(report['status'], report['summary'])


if __name__ == '__main__': main()
