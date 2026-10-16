#!/usr/bin/env python3
"""Reconcile preserved local receipts. No price oracle, projections or LIVE approval."""
import argparse
from decimal import Decimal
import json
from pathlib import Path

def summarize(evidence):
    identity=json.loads((evidence/'comparison.json').read_text())
    assert identity['full_byte_equality_including_metadata'] is True
    assert identity['compiled_sha256']==identity['observed_sha256']
    report=json.loads((evidence/'local/local-receipts.json').read_text())
    assert report['runtime_sha256']==identity['observed_sha256']
    assert report['actual_chain_rpc_used'] is False
    rows=[]
    for x in report['records']:
        fee=int(x['receipt']['gasUsed'],16)*int(x['receipt']['effectiveGasPrice'],16)
        assert fee==x['bundler_tx_fee_wei']
        assert x['tx']['to']==identity['address']
        event=x['userop_event']
        if event is not None:
            assert int(x['receipt']['status'],16)==1
            assert event['actualGasCost']==x['paymaster_debit_wei']==x['beneficiary_credit_wei']
            assert x['budget_reserved_wei']>=event['actualGasCost']
        else:
            assert int(x['receipt']['status'],16)==0
            assert x['paymaster_debit_wei']==x['beneficiary_credit_wei']==x['budget_reserved_wei']==0
        # Internal sponsor -> bundler transfers must not be counted twice as
        # expenditure when they belong to one consolidated operator.
        rows.append({'scenario':x['scenario'],'transaction_gas':int(x['receipt']['gasUsed'],16),
            'sponsor_debit_eth':str(Decimal(x['paymaster_debit_wei'])/10**18),
            'bundler_transaction_fee_eth':str(Decimal(fee)/10**18),
            'billed_userop_gas':event['actualGasUsed'] if event else None,
            'userop_success':event['success'] if event else False})
    original=next(x for x in report['records'] if x['scenario']=='success_original_limits')
    reduced=next(x for x in report['records'] if x['scenario']=='success_reduced_limits')
    saving=original['paymaster_debit_wei']-reduced['paymaster_debit_wei']
    assert saving==240_000_000_000_000
    return {'status':'LOCAL_ACCOUNTING_PASS_COMMERCIAL_GATE_BLOCKED','identity_block':identity['block'],
        'rows':rows,'local_sponsor_saving_wei':saving,
        'local_sponsor_saving_percent':str(100*Decimal(saving)/original['paymaster_debit_wei']),
        'missing_evidence':['fresh pinned Robinhood state and actual route replay',
            'L1 data component on Nitro for the full signed transaction',
            'actual account deployment and production account policy',
            'ERC-7562 validation, stake and supported EntryPoint admission from a bundler',
            'funded external sponsor with explicit failure costs and no personal recourse',
            'prospective net profit after all costs and failed attempts'],
        'synthetic_loan_surplus_not_usd_revenue':True,'nqc_realized_usd':'0',
        'owner_capital_spent_usd':'0','monetization_proven':False,'live_authorized':False}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--evidence',type=Path,default=Path(__file__).with_name('evidence'))
    ap.add_argument('--out',type=Path)
    args=ap.parse_args()
    value=summarize(args.evidence)
    text=json.dumps(value,indent=2)+'\n'
    if args.out:args.out.write_text(text)
    print(text)

if __name__=='__main__': main()
