#!/usr/bin/env python3
"""Reconcile historical Nitro receipt charges. Does not estimate an NQC transaction."""
import argparse
from decimal import Decimal
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'robinhood-route-admission-20261016'
spec = importlib.util.spec_from_file_location('route_audit', PREVIOUS / 'route_audit.py')
route = importlib.util.module_from_spec(spec)
spec.loader.exec_module(route)


def receipt_fee(receipt):
    gas = route.number(receipt['gasUsed'])
    price = route.number(receipt['effectiveGasPrice'])
    route.require(gas > 0 and price > 0, 'invalid gas/price')
    poster = route.number(receipt['gasUsedForL1']) if 'gasUsedForL1' in receipt else None
    route.require(poster is None or poster <= gas, 'poster gas exceeds total gas')
    # gasUsedForL1 is already expressed in child-chain gas units; do not add it twice.
    # This partition describes the receipt, not the sequencer's physical blob invoice.
    total = gas * price
    return {'total_gas': gas, 'gas_price_wei': price, 'total_fee_wei': total,
            'total_fee_eth': format(Decimal(total) / 10**18, 'f'),
            'reported_l1_gas_in_l2_units': poster,
            'remaining_gas': gas - poster if poster is not None else None,
            'l1_allocation_at_receipt_price_wei': poster * price if poster is not None else None,
            'remaining_allocation_wei': (gas - poster) * price if poster is not None else None,
            'missing_l1_field_is_not_zero': poster is None,
            'physical_blob_cost_measured': False}


def report():
    # Includes the prior source hash checks and receipt identity checks.
    audited = route.audit(PREVIOUS / 'evidence')
    cases = {case['tx']: case for case in audited['cases']}
    path = PREVIOUS / 'evidence/historical-receipts/rpc_original_receipts.json'
    rows = []
    for record in json.loads(path.read_text())[1:]:
        receipt = record['result']
        result = receipt_fee(receipt)
        case = cases[receipt['transactionHash']]
        rows.append({'tx': receipt['transactionHash'], 'block': int(receipt['blockNumber'], 16),
                     'block_hash': receipt['blockHash'], 'route_class': case['classification'], **result})
    return {'scope': 'ARCHIVED_THIRD_PARTY_NITRO_RECEIPTS_NOT_NQC_COST',
            'chain_id': 4663, 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'receipt_count': len(rows),
            'positive_reported_l1_gas_count': sum(r['reported_l1_gas_in_l2_units'] > 0 for r in rows),
            'zero_reported_l1_gas_count': sum(r['reported_l1_gas_in_l2_units'] == 0 for r in rows),
            'total_fee_eth_range': [min(rows, key=lambda r: r['total_fee_wei'])['total_fee_eth'],
                                    max(rows, key=lambda r: r['total_fee_wei'])['total_fee_eth']],
            'nqc_full_route_replayed': False, 'nqc_total_cost_wei': None,
            'zero_l1_does_not_mean_da_is_free': True, 'rows': rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    result = report()
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, indent=2))


if __name__ == '__main__':
    main()
