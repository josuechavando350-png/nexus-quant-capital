"""Offline observation of one winner's direct fee-recipient transfer.

Routescan pagination is complete for this indexed operation listing, not a raw
trace, state-transition proof, full cost account or execution by NQC/Titan.
"""
import argparse
import copy
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import parse_qs, urlsplit

from cashflow_intake import build_cashflow
from evidence_store import admit, audit_store, create, export_store, read_batch, restore_store, revoke
from execution_intake import build_execution_report, seal
from historical_intake import AUTHORITIES, EVIDENCE, ROOT, build_ledger, need, same, utc
from inclusion_fee_intake import (address, build_inclusion_report, load_capture as inclusion_capture,
    query_inclusion_report, store_inclusion_report, uint)
from integrity import canonical, digest, read_regular, strict_json

CAPTURE_NAME = 'direct-payment-capture.json'
REPORT_NAME = 'direct-payment-report.json'
BINDING_NAME = 'direct-payment-parent.json'
CAPTURE_SHA256 = 'b139de8b1dd63d1c87c629b6dbab4f4239c7a03b7a2d69082cffff61d6c43f12'
BASE = 'https://api.routescan.io'
PATH = '/v2/network/mainnet/evm/1/internal-operations'
WETH = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'


def load_capture(directory=EVIDENCE):
    raw = read_regular(Path(directory)/CAPTURE_NAME)
    need(digest(raw) == CAPTURE_SHA256, 'direct_capture_changed')
    capture = strict_json(raw)
    need(canonical(capture) == raw, 'direct_capture_noncanonical')
    need(capture['schema'] == 'nqc.omega.direct-payment-capture.v1'
         and capture['provider'] == 'ROUTESCAN', 'direct_capture_scope')
    return capture


def reconcile(capture, cashflow, fees, ledger, observed_transaction):
    observed_time = observed_transaction['timestamp']
    row = cashflow['records'][0]; tx_hash = row['transaction_hash']
    need(row['historical_rank_in_nine'] == 1 and len(cashflow['records']) == 9,
         'direct_sample_scope')
    need(capture['transaction_hash'] == tx_hash, 'direct_transaction_scope')
    records = capture['records']
    need([r['name'] for r in records] == ['operations-0','operations-1','operations-2',
         'transaction','value-transfers'], 'direct_capture_inventory')
    decoded = {}
    for r in records:
        raw = r['raw_body'].encode()
        need(type(r['http_status']) is int and r['http_status'] == 200
             and digest(raw) == r['raw_sha256'], 'direct_raw_digest')
        need(utc(observed_time) <= utc(r['retrieved_at']), 'direct_capture_time')
        decoded[r['name']] = strict_json(raw)
    need(records[3]['url'] == BASE+'/v2/network/mainnet/evm/1/transactions/'+tx_hash
         and records[4]['url'] == BASE+'/v2/network/mainnet/evm/1/etherscan/api?module=account&action=txlistinternal&txhash='+tx_hash,
         'direct_metadata_request')
    tx = decoded['transaction']
    receipt = next(r for r in ledger['records'] if r['transaction_hash'] == tx_hash)
    fee = fees['records'][0]['fee_witness']
    need(tx['type'] == 'evm_tx' and tx['id'] == tx_hash and tx['chainId'] == '1'
         and tx['status'] is True, 'direct_transaction_identity')
    need(type(tx['blockNumber']) is int and type(tx['index']) is int
         and tx['blockNumber'] == row['block_number'] and tx['blockHash'] == row['block_hash']
         and tx['index'] == receipt['transaction_index']
         and utc(tx['timestamp']) == utc(observed_time), 'direct_transaction_anchor')
    need(tx['gasUsed'] == fee['gas_used'] and tx['gasPrice'] == fee['effective_gas_price_wei']
         and tx['burnedFees'] == fee['base_fee_burn_wei'], 'direct_gas_disagreement')
    sender, executor = address(tx['from']), address(tx['to'])
    recipient = fee['block_fee_recipient']
    need(sender == fee['transaction_sender'] and executor == row['liquidator_address'], 'direct_actor_disagreement')
    native_value = uint(tx['value'])
    need(tx['value'] == observed_transaction['value'], 'direct_native_value_disagreement')
    operations = []; next_url = BASE+PATH+'?txHash='+tx_hash+'&count=true'
    for i, record in enumerate(records[:3]):
        need(record['url'] == next_url, 'direct_cursor_disagreement')
        url = urlsplit(record['url']); query = parse_qs(url.query)
        need(url.scheme == 'https' and url.netloc == 'api.routescan.io' and url.path == PATH
             and query['txHash'] == [tx_hash] and query['count'] == ['true']
             and set(query) == ({'txHash','count'} if i == 0 else {'txHash','count','next'}),
             'direct_operation_request')
        page = decoded[record['name']]
        # The final cursor reports lowerBound; initial pages advertise exactly 57.
        # Require all 57 unique indices plus terminal pagination, not that label alone.
        need(type(page['count']) is int and page['count'] == 57
             and page['countType'] == ('lowerBound' if i == 2 else 'exact')
             and len(page['items']) == (7 if i == 2 else 25), 'direct_page_coverage')
        link = page.get('link', {}).get('next')
        need((type(link) is str and link.startswith(PATH+'?')) if i < 2 else link is None,
             'direct_page_not_terminal')
        next_url = BASE+link if link else None
        operations.extend(page['items'])
    need(all(type(o['opIndex']) is int for o in operations)
         and sorted(o['opIndex'] for o in operations) == list(range(57)), 'direct_operation_inventory')
    for o in operations:
        need(o['chainId'] == '1' and o['txHash'] == tx_hash
             and type(o['blockNumber']) is int and o['blockNumber'] == tx['blockNumber']
             and type(o['txIndex']) is int and o['txIndex'] == tx['index']
             and utc(o['timestamp']) == utc(tx['timestamp']), 'direct_operation_anchor')
        need(o['status'] is True and o['type'] in ('CALL','STATICCALL','DELEGATECALL'),
             'direct_operation_failed_or_unsupported')
        uint(o['value']); address(o['from']); address(o['to'])
    by_index = {o['opIndex']: o for o in operations}; root = by_index[0]
    need(root['type'] == 'CALL' and address(root['from']) == sender and address(root['to']) == executor
         and root['value'] == tx['value'] and root['gasUsed'] == tx['gasUsed'], 'direct_root_call')
    positive = [o for o in operations if o['opIndex'] != 0 and uint(o['value']) > 0]
    need(len(positive) == 3 and all(o['type'] == 'CALL' for o in positive), 'direct_transfer_inventory')
    def one(source, target=None):
        selected = [o for o in positive if address(o['from']) == source
                    and (address(o['to']) == target if target else address(o['to']) != recipient)]
        need(len(selected) == 1, 'direct_transfer_role'); return selected[0]
    unwrap, payment, residual = one(WETH, executor), one(executor, recipient), one(executor)
    need(uint(unwrap['value']) == uint(row['same_asset_gross_delta_wei'])
         and uint(payment['value']) + uint(residual['value']) == uint(unwrap['value']),
         'direct_native_split_disagreement')
    compat = decoded['value-transfers']
    need(compat['status'] == '1' and compat['message'] == 'OK'
         and len(compat['result']) == 3, 'direct_compat_scope')
    projected = []
    for v in compat['result']:
        need(v['blockNumber'] == str(tx['blockNumber'])
             and uint(v['timeStamp']) == int(utc(tx['timestamp']).timestamp())
             and v['type'] == 'call' and v['isError'] == '0' and v['errCode'] == '', 'direct_compat_anchor')
        projected.append((address(v['from']), address(v['to']), str(uint(v['value']))))
    same(sorted(projected), sorted((address(o['from']),address(o['to']),o['value']) for o in positive),
         'direct_same_provider_api_disagreement')
    return {'provider': 'ROUTESCAN', 'indexed_operation_count': 57, 'indexed_pages': 3,
        'indexed_operation_listing_complete': True, 'raw_trace_available': False,
        'full_call_ancestry_proven': False, 'native_balance_reconciliation_complete': False,
        'transaction_sender': sender, 'event_liquidator_address': executor,
        'block_fee_recipient': recipient, 'fee_recipient_builder_identity': None,
        'transaction_native_value_wei': str(native_value),
        'unwrap_native_transfer_wei': unwrap['value'], 'direct_fee_recipient_payment_wei': payment['value'],
        'residual_native_transfer_wei': residual['value'],
        'residual_recipient': address(residual['to']), 'residual_recipient_control': None,
        'residual_is_realized_profit': False,
        'payment_to_gross_delta_wad': str(uint(payment['value'])*10**18//uint(unwrap['value'])),
        'execution_gas_paid_wei': fee['execution_gas_paid_wei'],
        'direct_payment_is_separate_from_execution_gas': True,
        'exclusive_liquidation_cost_attribution_proven': False,
        'total_builder_compensation_wei': None,
        'same_provider_two_api_representations_agree': True,
        'independent_trace_provider_agreement': False}


def build_report(directory=EVIDENCE, root=ROOT):
    capture = load_capture(directory)
    cashflow, fees, ledger = build_cashflow(directory, root), build_inclusion_report(directory, root), build_ledger(directory, root)
    economics = build_execution_report(directory, root)
    first = next(r for r in inclusion_capture(directory)['records'] if r['rank'] == 1 and r['kind'] == 'transaction')
    witness = reconcile(capture, cashflow, fees, ledger, first['response']['data'])
    rows = [{'transaction_hash':r['transaction_hash'], 'historical_rank_in_nine':r['historical_rank_in_nine'],
             'direct_payment_witness': witness if i == 0 else None, 'complete_costs': False,
             'complete_net_profit_wei': None, 'nqc_execution': False, 'titan_coverage_proven': False}
            for i,r in enumerate(cashflow['records'])]
    return seal({'schema':'nqc.omega.direct-payment-intake.v1','status':'ONE_HISTORICAL_DIRECT_PAYMENT_OBSERVED',
        'capture_sha256':CAPTURE_SHA256,'inclusion_report_commitment':fees['report_commitment_sha256'],
        'cashflow_report_commitment':cashflow['report_commitment_sha256'],
        'gas_funding_policy':copy.deepcopy(economics['gas_funding_policy']),
        'gas_policy_sha256':economics['gas_policy_sha256'], 'records':rows,
        'summary':{'historical_corpus_transactions':127,'weth_sample_transactions':9,
                   'direct_fee_recipient_payment_observations':1,'unobserved_direct_payment_rows':8,
                   'complete_paid_cost_rows':0,'titan_covered_executions':0},
        'trust_basis':'REVIEWED_PUBLIC_ROUTESCAN_INDEXER_CAPTURE_NOT_STATE_TRANSITION_PROOF',
        'live_acquisition_during_replay':False,'authorities':dict(AUTHORITIES)})


def verify_report(report, directory=EVIDENCE, root=ROOT):
    expected = build_report(directory, root)
    same(report, expected, 'direct_report_differs_from_sources'); return expected


def store_report(path, root=ROOT):
    upstream = store_inclusion_report(path, root)
    parent = upstream['batch']; objects = read_batch(path, parent)
    objects[CAPTURE_NAME] = read_regular(Path(root)/'omega/evidence'/CAPTURE_NAME)
    with tempfile.TemporaryDirectory(prefix='omega-direct-admit-') as tmp:
        for name, raw in objects.items(): (Path(tmp)/name).write_bytes(raw)
        report = build_report(Path(tmp), root)
    objects[REPORT_NAME] = canonical(report)
    objects[BINDING_NAME] = canonical({'inclusion_batch': parent})
    return {'batch': admit(path, objects, parents=[parent]), 'parent': parent,
            'root_batch': upstream['root_batch'], 'report': report}


def query_report(path, batch, root=ROOT):
    objects = read_batch(path, batch)
    binding = strict_json(objects[BINDING_NAME])
    need(set(binding) == {'inclusion_batch'}, 'direct_parent_inventory')
    parent = binding['inclusion_batch']
    same(audit_store(path)['dependencies'].get(batch), [parent], 'direct_missing_declared_parent')
    query_inclusion_report(path, parent, root)
    inherited = read_batch(path, parent)
    need(set(objects) == set(inherited) | {CAPTURE_NAME, REPORT_NAME, BINDING_NAME},
         'direct_batch_inventory')
    need(all(objects[n] == b for n, b in inherited.items()), 'direct_inherited_bytes_changed')
    with tempfile.TemporaryDirectory(prefix='omega-direct-query-') as tmp:
        for name, raw in objects.items(): (Path(tmp)/name).write_bytes(raw)
        return verify_report(strict_json(objects[REPORT_NAME]), Path(tmp), root)


def exercise_fields(directory, root=ROOT):
    """Replay eight dependent batches; preserve all bytes after root revocation."""
    directory = Path(directory); path = create(directory/'source.sqlite')
    result = store_report(path, root); batch = result['batch']
    same(query_report(path, batch, root), result['report'], 'direct_query_mismatch')
    before = {b: read_batch(path, b) for b in audit_store(path)['active_batches']}
    need(len(before) == 8 and batch in before, 'direct_active_inventory')
    revoke(path, result['root_batch'], 'CONTROLLED_DIRECT_PAYMENT_DEPENDENCY_TEST',
           b'TEST_ONLY_NOT_A_REAL_CANONICAL_REORG')
    status = audit_store(path); snapshot = export_store(path)
    restored = directory/'restored.sqlite'; restore_store(restored, snapshot)
    same(audit_store(restored)['journal_head'], status['journal_head'], 'direct_restore_head')
    same(export_store(restored), snapshot, 'direct_restore_changed')
    for database in (path, restored):
        try: query_report(database, batch, root)
        except ValueError as e: need(str(e) == 'batch_inactive_or_missing', 'direct_block_reason')
        else: raise ValueError('revoked_direct_query_accepted')
        for ancestor, raw_objects in before.items():
            try: read_batch(database, ancestor)
            except ValueError as e: need(str(e) == 'batch_inactive_or_missing', 'direct_ancestor_block_reason')
            else: raise ValueError('revoked_direct_ancestor_accepted')
            need(read_batch(database, ancestor, include_revoked=True) == raw_objects,
                 'direct_forensic_bytes_changed')
    need(status['revoked_batches'] == [result['root_batch']]
         and set(status['invalidated_batches']) == set(before)-{result['root_batch']}
         and status['active_batches'] == [], 'direct_invalidation_partition')
    report = result['report']
    return {'schema': 'nqc.omega.direct-payment-local-replay.v1',
        'status': 'DIRECT_PAYMENT_LOCAL_REPLAY_PASS', 'direct_payment_report': report,
        'gas_funding_policy': copy.deepcopy(report['gas_funding_policy']),
        'gas_policy_sha256': report['gas_policy_sha256'],
        'direct_payment_batch': batch, 'inclusion_batch': result['parent'],
        'root_batch': result['root_batch'], 'snapshot_sha256': digest(canonical(snapshot)),
        'journal_head': status['journal_head'], 'blocked_batches': 8,
        'forensic_bytes_preserved': True, 'restore_byte_identical': True,
        'revoked_query_rejected': True, 'rust_transport_performed': False,
        'certified_components': 0, 'census_closed': False}


def verify_replay(report, root=ROOT):
    network = report.get('network', {})
    need(network.get('interfaces') == ['lo'] and network.get('routable_network') is False
         and all(type(network.get(k)) is str and re.fullmatch(r'net:\[[0-9]+\]', network[k])
                 for k in ('network_namespace', 'parent_network_namespace'))
         and network['network_namespace'] != network['parent_network_namespace'], 'direct_network')
    with tempfile.TemporaryDirectory(prefix='omega-direct-verify-') as tmp:
        expected = exercise_fields(tmp, root)
    expected['network'] = network
    same(report, seal(expected), 'direct_replay_differs_from_sources'); return report


def exercise(directory, network, root=ROOT):
    from rust_store_intake import new_directory
    directory = new_directory(directory, root)
    print('OMEGA_DIRECT_PAYMENT_BEGIN', flush=True)
    report = exercise_fields(directory, root); report['network'] = network; seal(report)
    verify_replay(report, root)
    (directory/'report.json').write_bytes(canonical(report))
    print('OMEGA_DIRECT_PAYMENT_REPORT ' + canonical(report).decode().strip(), flush=True)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output',type=Path); args=p.parse_args()
    report=build_report()
    if args.output:
        with args.output.open('xb') as stream: stream.write(canonical(report))
    print(json.dumps({'status':report['status'], **report['summary'],
                     'report_commitment_sha256':report['report_commitment_sha256']},sort_keys=True))


if __name__ == '__main__': main()
