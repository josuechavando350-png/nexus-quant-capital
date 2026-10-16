#!/usr/bin/env python3
"""Compare archived gas receipts with a corrected, locally initialized EntryPoint."""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def compare(previous, corrected):
    before, after = json.loads(previous.read_text()), json.loads(corrected.read_text())
    if after.get('entrypoint_constructor_state') != {'guard_slot': 2, 'guard_initial_value': 1, 'mapping_root_untouched': True}:
        raise ValueError('missing corrected state evidence')
    if before['runtime_sha256'] != after['runtime_sha256'] or after['actual_chain_rpc_used']:
        raise ValueError('runtime/scope changed')
    old = {r['scenario']: r for r in before['records']}
    new = {r['scenario']: r for r in after['records']}
    if len(old) != 7 or set(old) != set(new) or len(new) != len(after['records']):
        raise ValueError('scenario coverage changed')
    rows = []
    for name, record in new.items():
        for source in [old[name], record]:
            receipt, event = source['receipt'], source['userop_event']
            gas = int(receipt['gasUsed'], 16)
            price = int(receipt['effectiveGasPrice'], 16)
            if gas != source['tx_gas_used'] or gas * price != source['bundler_tx_fee_wei']:
                raise ValueError('receipt fee mismatch')
            if event:
                if not (int(receipt['status'], 16) == 1 and event['actualGasCost'] == source['paymaster_debit_wei'] ==
                        source['beneficiary_credit_wei'] and source['budget_reserved_wei'] >= event['actualGasCost']):
                    raise ValueError('UserOperation accounting mismatch')
            elif not (int(receipt['status'], 16) == 0 and source['paymaster_debit_wei'] == source['beneficiary_credit_wei'] == 0):
                raise ValueError('rejected bundle accounting mismatch')
        if old[name]['loan_surplus_raw'] != record['loan_surplus_raw']:
            raise ValueError('economic fixture result changed')
        if bool(old[name]['userop_event'] and old[name]['userop_event']['success']) != bool(record['userop_event'] and record['userop_event']['success']):
            raise ValueError('execution outcome changed')
        rows.append({'scenario': name, 'old_transaction_gas': old[name]['tx_gas_used'],
                     'corrected_transaction_gas': record['tx_gas_used'],
                     'transaction_gas_difference': record['tx_gas_used'] - old[name]['tx_gas_used'],
                     'old_sponsor_debit_wei': old[name]['paymaster_debit_wei'],
                     'corrected_sponsor_debit_wei': record['paymaster_debit_wei'],
                     'sponsor_debit_difference_wei': record['paymaster_debit_wei'] - old[name]['paymaster_debit_wei'],
                     'corrected_bundler_tx_fee_wei': record['bundler_tx_fee_wei']})
    return {'correction': 'Initialize ReentrancyGuard _status in compiler slot 2 instead of mapping root 0.',
            'scope': 'LOCAL_SYNTHETIC_COLD_RECEIPTS_ONLY', 'l1_data_fee_measured': False,
            'real_route_gas_measured': False, 'full_bundler_admission_proven': False,
            'old_evidence_preserved': True, 'rows': rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--previous', type=Path, default=HERE.parent / 'robinhood-aa-20261016/evidence/local/local-receipts.json')
    ap.add_argument('--corrected', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    result = compare(args.previous, args.corrected)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
