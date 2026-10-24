"""Nine source-bound WETH/WETH gross-minus-gas observations, never net profit.

The two previous-block prices are historical reference valuations. A five-bps
flash fee in the original auditor is a sensitivity, not a paid or quoted cost.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from evidence_store import admit, read_batch
from historical_intake import (AUTHORITIES, EVIDENCE, ROOT, SOURCE, SOURCE_ID,
    build_ledger, fields, need, original_validator, same, utc)
from historical_pipeline import LEDGER_NAME, SOURCE_NAMES
from integrity import canonical, digest, read_regular, strict_json
from liquidator_intake import (CAPTURE_NAMES, build_liquidator_report,
    store_identities)

METADATA_SHA256='d4806f0f3478f80f035a6e60f5ae9969e3defc66690d9984d2199f67ce8285d3'
PRICE_SHA256='5ae6c45b53ded26f327270758c248f7f4ec0ff1365f550e54dcf28feb4a83a03'
PRICE_COMMIT='a569b0a6ba11c0d12de3a1ac0d16d85b896933f6'
PRICE_TREE='3c84f4fa3a2a0a62accde257029714177dc38b5a'
PRICE_NAMES={'weth-price-original.zip','weth-price-metadata.json'}
SCHEMA='nqc.omega.weth-cashflow-intake.v1'


def load_price(directory=EVIDENCE,root=ROOT):
    raw=read_regular(Path(directory)/'weth-price-metadata.json')
    need(digest(raw)==METADATA_SHA256,'price_metadata_pin_changed')
    meta=strict_json(raw);run,commit,artifact=(meta[k] for k in ('run','commit','artifact'))
    fields(run,{'id':37726618359,'head_sha':PRICE_COMMIT,'status':'completed',
        'conclusion':'success','run_attempt':1,'workflow_id':378073239,
        'path':'.github/workflows/nqc-rmc016-top-weth-oracle.yml',
        'head_branch':'nqc/rmc016-top2-weth-price-source-20261008'},'price_run')
    for name in ('repository','head_repository'):
        fields(run[name],{'id':SOURCE_ID,'full_name':SOURCE,'private':False},'price_repo')
    fields(commit,{'sha':PRICE_COMMIT},'price_commit');fields(commit['tree'],{'sha':PRICE_TREE},'price_tree')
    fields(run['head_commit'],{'id':PRICE_COMMIT,'tree_id':PRICE_TREE},'price_run_tree')
    fields(artifact,{'id':11527902751,'size_in_bytes':1979,'expired':False,
        'digest':'sha256:'+PRICE_SHA256,
        'name':'rmc016-two-weth-winner-historical-prices-'+PRICE_COMMIT},'price_artifact')
    fields(artifact['workflow_run'],{'id':run['id'],'head_sha':PRICE_COMMIT,
        'head_branch':run['head_branch'],'repository_id':SOURCE_ID,
        'head_repository_id':SOURCE_ID},'price_artifact_run')
    need(utc(run['created_at'])<=utc(artifact['created_at'])<=utc(run['updated_at'])
         <=utc(meta['retrieved_at'])<utc(artifact['expires_at']),'price_capture_time')
    archive=read_regular(Path(directory)/'weth-price-original.zip',128*1024)
    need(len(archive)==1979 and digest(archive)==PRICE_SHA256,'price_archive_pin_changed')
    # Freeze bytes before the original immutable ZIP/manifest validator reads them.
    original=original_validator(root)
    with tempfile.TemporaryDirectory(prefix='omega-price-') as tmp:
        p=Path(tmp)/'prices.zip';p.write_bytes(archive)
        members=original.authenticated_zip(p,PRICE_SHA256,{'top-two-weth-prices.json'})
    report=strict_json(members['top-two-weth-prices.json'])
    need(report['report_sha256']==digest(canonical({k:v for k,v in report.items() if k!='report_sha256'})),
         'price_report_commitment')
    fields(report,{'status':'TWO_HISTORICAL_WETH_WINNER_PREBLOCK_ORACLE_PRICES_PASS',
        'source_scope':'TWO_OBSERVED_COMPETITOR_WINNERS_NOT_NEXUS',
        'nexus_capture_proven':False,'nexus_realized_profitability_proven':False,
        'real_market_census_closed':False,'exact_intratransaction_price_proven':False},'price_report')
    return report,meta


def build_cashflow(directory=EVIDENCE,root=ROOT):
    ledger=build_ledger(directory,root)
    identities=build_liquidator_report(directory,root)
    price,meta=load_price(directory,root)
    original=original_validator(root)
    legs=[leg for r in ledger['records'] for leg in r['liquidation_legs']]
    receipts={r['transaction_hash']:r['receipt'] for r in ledger['records']}
    diagnostics=original.calculate(legs,receipts,price['transactions'])
    winners={r['transaction_hash']:r for r in identities['transactions']}
    priced={r['transaction_hash']:r for r in price['transactions']}
    rows=[]
    for d in diagnostics:
        tx=d['transaction_hash'];reference=priced.get(tx)
        row={'transaction_hash':tx,'block_number':d['block_number'],'block_hash':d['block_hash'],
            'liquidator_address':winners[tx]['single_event_liquidator_address'],
            'historical_rank_in_nine':d['historical_after_gas_rank_in_nine'],
            'weth_debt_wei':d['historical_weth_debt_raw_wei'],
            'weth_collateral_wei':d['historical_weth_collateral_raw_wei'],
            'same_asset_gross_delta_wei':d['collateral_minus_debt_wei'],
            'full_transaction_gas_wei':d['winner_full_tx_gas_wei'],
            'gross_delta_minus_full_transaction_gas_wei':d['collateral_minus_debt_minus_winner_gas_wei'],
            'gas_allocation':'ENTIRE_WINNER_TRANSACTION_CHARGED_TO_THIS_WETH_LEG',
            'receive_a_token':d['receive_a_token'],
            'preblock_price_reference':reference,
            'gross_minus_gas_usd_wad_at_preblock_reference':None if reference is None else str(
                original.signed_usd_wad(int(d['collateral_minus_debt_minus_winner_gas_wei']),
                                       reference['preblock']['oracle_usd_base_1e8'])),
            'hypothetical_fee_sensitivity':{
                'bps':5,'is_observed_cost':False,'is_provider_quote':False,
                'fee_wei_ceil':d['hypothetical_5bps_flash_premium_wei_ceil'],
                'remaining_before_other_costs_wei':d['conditional_remaining_before_other_costs_wei']},
            'oracle_update_block':None,'oracle_delay_blocks':None,
            'builder_payment_wei':None,'other_observed_costs_wei':None,
            'complete_net_profit_wei':None,'complete_net_profit_usd_wad':None,
            'nqc_execution':False,'complete_costs':False}
        row['record_commitment_sha256']=digest(canonical(row));rows.append(row)
    report={'schema':SCHEMA,'status':'HISTORICAL_GROSS_MINUS_GAS_ONLY',
        'scope':'NINE_RETROSPECTIVELY_SELECTED_WETH_WETH_COMPETITOR_TRANSACTIONS',
        'base_ledger_commitment':ledger['ledger_commitment_sha256'],
        'identity_report_commitment':identities['report_commitment_sha256'],
        'price_source':{'run_id':37726618359,'artifact_id':11527902751,'commit':PRICE_COMMIT,
            'tree':PRICE_TREE,'archive_sha256':PRICE_SHA256,'metadata_sha256':METADATA_SHA256,
            'capture_at':meta['retrieved_at'],'report_sha256':price['report_sha256'],
            'trust_basis':'REVIEWED_RETAINED_GITHUB_CAPTURE_NOT_FRESH_QUERY'},
        'records':rows,'summary':{'transaction_count':len(rows),'preblock_priced_count':len(priced),
            'priced_ranks':[r['historical_rank_in_nine'] for r in rows if r['preblock_price_reference']],
            'complete_cost_count':0,'observed_oracle_delay_count':0},
        'prices_are_transaction_prestate':False,'price_change_is_oracle_update_proof':False,
        'provider_receipts_fully_reconciled':False,'new_acquisition_performed':False,
        'monthly_or_capture_adjusted_profit':None,'authorities':AUTHORITIES}
    need(report['summary']['transaction_count']==9 and report['summary']['priced_ranks']==[1,3],
         'cashflow_scope_changed')
    report['report_commitment_sha256']=digest(canonical(report));return report


def verify_cashflow(value,directory=EVIDENCE,root=ROOT):
    expected=build_cashflow(directory,root)
    same(value,expected,'cashflow_differs_from_sources');return expected


def store_cashflow(store,directory=EVIDENCE,root=ROOT):
    base=store_identities(store,directory,root)
    objects=read_batch(store,base['identity_batch'])
    objects.update({n:read_regular(Path(directory)/n) for n in PRICE_NAMES})
    with tempfile.TemporaryDirectory(prefix='omega-cashflow-') as tmp:
        for n,b in objects.items():(Path(tmp)/n).write_bytes(b)
        report=build_cashflow(Path(tmp),root)
    objects['cashflow-report.json']=canonical(report)
    return {'identity_batch':base['identity_batch'],'cashflow_batch':admit(store,objects),'report':report}


def query_cashflow(store,batch,root=ROOT):
    objects=read_batch(store,batch)
    need(set(objects)==SOURCE_NAMES|CAPTURE_NAMES|PRICE_NAMES|
         {LEDGER_NAME,'liquidator-report.json','cashflow-report.json'},'cashflow_inventory')
    with tempfile.TemporaryDirectory(prefix='omega-cashflow-query-') as tmp:
        for n,b in objects.items():(Path(tmp)/n).write_bytes(b)
        from historical_intake import verify_ledger
        verify_ledger(strict_json(objects[LEDGER_NAME]),Path(tmp),root)
        same(strict_json(objects['liquidator-report.json']),build_liquidator_report(Path(tmp),root),
             'cashflow_identity_differs_from_sources')
        return verify_cashflow(strict_json(objects['cashflow-report.json']),Path(tmp),root)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path)
    a=p.parse_args()
    try:
        report=build_cashflow()
        if a.output:
            with a.output.open('xb') as f:f.write(canonical(report))
        print(json.dumps({'status':report['status'],**report['summary'],
                         'report_commitment_sha256':report['report_commitment_sha256'],'census_closed':False}));return 0
    except (ValueError,KeyError,TypeError,OSError) as e:
        print(json.dumps({'status':'CASHFLOW_INTAKE_BLOCKED','reason':str(e),'census_closed':False}));return 1


if __name__=='__main__':raise SystemExit(main())
