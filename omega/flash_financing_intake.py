"""One retained Morpho flash principal/repayment observation, not NQC funding."""
import argparse
import copy
import json
from pathlib import Path
import re

from cashflow_intake import build_cashflow
from direct_payment_intake import build_report as build_payments, load_capture as operation_capture
from execution_intake import build_execution_report, seal
from historical_intake import AUTHORITIES, EVIDENCE, ROOT, build_ledger, need, original_validator, same, utc
from inclusion_fee_intake import address, uint
from integrity import canonical, digest, read_regular, strict_json

CAPTURE_NAME = 'flash-financing-capture.json'
CAPTURE_SHA256 = '8bb0bde55bd501175f54148561a508fcab0bf296e5bfa10123b4fde3acdc8701'
MORPHO = '0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb'
WETH = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'
FLASH = '0xc76f1b4fe4396ac07a9fa55a415d4ca430e72651d37d3401f3bed7cb13fc4f12'
TRANSFER = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
WITHDRAWAL = '0x7fcf532c15f0a6db0bd6d0e038bea71d30d808c7d98cb3bf7268a95bf5081b65'


def quantity(v):
    need(type(v) is str and re.fullmatch(r'0x(?:0|[1-9a-f][0-9a-f]*)',v)
         and int(v,16)<2**256, 'financing_hex_quantity')
    return int(v,16)


def word(v):
    need(type(v) is str and re.fullmatch(r'0x[0-9a-f]{64}',v), 'financing_abi_word')
    return int(v,16)


def topic_address(v):
    word(v); need(v[2:26]=='0'*24, 'financing_address_padding')
    return '0x'+v[26:]


def load_capture(directory=EVIDENCE):
    raw=read_regular(Path(directory)/CAPTURE_NAME)
    need(digest(raw)==CAPTURE_SHA256, 'financing_capture_changed')
    c=strict_json(raw); need(canonical(c)==raw, 'financing_capture_noncanonical')
    return c


def reconcile(capture, cashflow, payments, operations, ledger, economics, root=ROOT):
    row=cashflow['records'][0]; tx=row['transaction_hash']
    need(row['historical_rank_in_nine']==1 and len(cashflow['records'])==9, 'financing_scope')
    need(capture['schema']=='nqc.omega.flash-financing-capture.v1' and capture['provider']=='ROUTESCAN'
         and type(capture['chain_id']) is int and capture['chain_id']==1
         and capture['transaction_hash']==tx, 'financing_capture_scope')
    record=capture['record']; raw=record['raw_body'].encode()
    need(type(record['http_status']) is int and record['http_status']==200
         and digest(raw)==record['raw_sha256'], 'financing_raw_digest')
    need(record['url']=='https://api.routescan.io/v2/network/mainnet/evm/1/etherscan/api?module=proxy&action=eth_getTransactionReceipt&txhash='+tx,
         'financing_request')
    response=strict_json(raw)
    need(set(response)=={'jsonrpc','id','result'} and response['jsonrpc']=='2.0'
         and type(response['id']) is int and response['id']==1, 'financing_rpc_response')
    receipt=response['result']; source=next(r for r in ledger['records'] if r['transaction_hash']==tx)
    witness=payments['records'][0]['direct_payment_witness']; executor=row['liquidator_address']
    need(receipt['transactionHash']==tx and receipt['blockHash']==row['block_hash']
         and quantity(receipt['blockNumber'])==row['block_number']
         and quantity(receipt['transactionIndex'])==source['transaction_index'], 'financing_receipt_anchor')
    need(receipt['status']=='0x1' and receipt['type']=='0x2' and receipt['contractAddress'] is None,
         'financing_receipt_status')
    need(address(receipt['from'])==witness['transaction_sender'] and address(receipt['to'])==executor,
         'financing_receipt_actors')
    need(quantity(receipt['cumulativeGasUsed'])>=quantity(receipt['gasUsed']), 'financing_cumulative_gas')
    # This loader freezes all original imports. Reuse its exact receipt normalizer.
    original=original_validator(root)
    normalize=original.load_source.__globals__['receipt_normalized']
    normalized=normalize(tx,source['events'],receipt)
    same(normalized,source['receipt'],'financing_drpc_normalized_disagreement')
    ops=[o for r in operations['records'][:3] for o in strict_json(r['raw_body'])['items']]
    need(operations['transaction_hash']==tx, 'financing_operation_scope')
    by_index={o['opIndex']:o for o in ops}; first=by_index[0]
    need(utc(first['timestamp'])<=utc(record['retrieved_at']), 'financing_capture_time')
    for i, sender, target, selector in [(1,executor,MORPHO,'0xe0232b42'),
                                       (3,MORPHO,executor,'0x31f57072')]:
        o=by_index[i]
        need(o['type']=='CALL' and o['status'] is True and o['value']=='0'
             and address(o['from'])==sender and address(o['to'])==target
             and o['methodId']==selector, 'financing_flash_call')
    logs=receipt['logs']
    need(type(logs) is list and len(logs)==17
         and [quantity(l['logIndex']) for l in logs]==list(range(7,24)), 'financing_log_inventory')
    for l in logs:
        need(l['transactionHash']==tx and l['blockHash']==row['block_hash']
             and l['blockNumber']==receipt['blockNumber']
             and l['transactionIndex']==receipt['transactionIndex'] and l['removed'] is False
             and quantity(l['blockTimestamp'])==int(utc(first['timestamp']).timestamp()), 'financing_log_anchor')
        address(l['address']); need(type(l['topics']) is list and 0<len(l['topics'])<=4, 'financing_log_topics')
        for t in l['topics']: word(t)
    flash=[l for l in logs if address(l['address'])==MORPHO]
    need(len(flash)==1 and len(flash[0]['topics'])==3 and flash[0]['topics'][0]==FLASH
         and topic_address(flash[0]['topics'][1])==executor
         and topic_address(flash[0]['topics'][2])==WETH, 'financing_flash_event')
    principal=word(flash[0]['data']); need(principal==uint(row['weth_debt_wei'])>0, 'financing_principal')
    transfers=[l for l in logs if address(l['address'])==WETH and l['topics'][0]==TRANSFER]
    need(len(transfers)==4 and all(len(l['topics'])==3 for l in transfers), 'financing_transfer_inventory')
    decoded=[(quantity(l['logIndex']),topic_address(l['topics'][1]),topic_address(l['topics'][2]),word(l['data'])) for l in transfers]
    lender=[t for t in decoded if MORPHO in t[1:3]]
    need(lender==[(8,MORPHO,executor,principal),(22,executor,MORPHO,principal)], 'financing_principal_repayment')
    collateral, debt=decoded[1],decoded[2]
    need(collateral[0]==15 and debt[0]==20 and collateral[1]==debt[2]
         and collateral[2]==debt[1]==executor
         and collateral[3]==uint(row['weth_collateral_wei']) and debt[3]==principal, 'financing_liquidation_flows')
    withdrawal=[l for l in logs if address(l['address'])==WETH and l['topics'][0]==WITHDRAWAL]
    need(len(withdrawal)==1 and len(withdrawal[0]['topics'])==2
         and quantity(withdrawal[0]['logIndex'])==23 and topic_address(withdrawal[0]['topics'][1])==executor
         and word(withdrawal[0]['data'])==uint(witness['unwrap_native_transfer_wei'])
         and collateral[3]-principal==word(withdrawal[0]['data']), 'financing_withdrawal')
    fee=economics['records'][0]['execution_witness']['costs']['CAPITAL_FEE']
    need(fee['status']=='SIMULATED_FORK_ONLY' and fee['paid_amount_wei'] is None, 'financing_fork_scope')
    return {'lender_address':MORPHO,'lender_documentation_name':'Morpho Blue', 'asset':WETH,
        'principal_wei':str(principal),'repayment_wei':str(lender[1][3]),
        'observed_weth_repayment_premium_wei':str(lender[1][3]-lender[0][3]),
        'flash_event_log_index':7,'principal_transfer_log_index':8,'repayment_transfer_log_index':22,
        'normalized_receipt_commitment':normalized['receipt_evidence_sha256'],
        'normalized_receipt_matches_retained_drpc':True,'full_receipt_cross_provider_parity':False,
        'lender_deployed_code_identity_verified':False,'raw_call_ancestry_proven':False,
        'scope':'ONE_HISTORICAL_EVENT_AND_WETH_PRINCIPAL_REPAYMENT_NOT_ALL_FINANCING_COSTS',
        'other_financing_costs_wei':None,'retained_aave_fork_fee_wei':fee['simulated_amount_wei'],
        'fork_fee_is_observed_winner_fee':False,'nqc_morpho_route_validated':False,
        'current_flash_liquidity_verified':False,'nqc_cost_saving_proven':False}


def build_report(directory=EVIDENCE,root=ROOT):
    capture=load_capture(directory); cashflow=build_cashflow(directory,root)
    payments=build_payments(directory,root); economics=build_execution_report(directory,root)
    witness=reconcile(capture,cashflow,payments,operation_capture(directory),build_ledger(directory,root),economics,root)
    rows=[{'transaction_hash':r['transaction_hash'],'historical_rank_in_nine':r['historical_rank_in_nine'],
           'financing_witness':witness if i==0 else None,'complete_costs':False,
           'complete_net_profit_wei':None,'nqc_execution':False,'titan_coverage_proven':False}
          for i,r in enumerate(cashflow['records'])]
    return seal({'schema':'nqc.omega.flash-financing-intake.v1','status':'ONE_HISTORICAL_FLASH_REPAYMENT_OBSERVED',
        'capture_sha256':CAPTURE_SHA256,'direct_payment_report_commitment':payments['report_commitment_sha256'],
        'execution_report_commitment':economics['report_commitment_sha256'],
        'gas_funding_policy':copy.deepcopy(economics['gas_funding_policy']),
        'gas_policy_sha256':economics['gas_policy_sha256'],'records':rows,
        'summary':{'historical_corpus_transactions':127,'weth_sample_transactions':9,
                   'flash_repayment_observations':1,'unobserved_financing_rows':8,
                   'complete_paid_cost_rows':0,'titan_covered_executions':0},
        'trust_basis':'REVIEWED_ROUTESCAN_RECEIPT_AND_INDEXED_CALLS_NOT_RECEIPT_TRIE_PROOF',
        'live_acquisition_during_replay':False,'authorities':dict(AUTHORITIES)})


def verify_report(report,directory=EVIDENCE,root=ROOT):
    expected=build_report(directory,root); same(report,expected,'financing_report_differs_from_sources'); return expected


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);a=p.parse_args()
    r=build_report()
    if a.output:
        with a.output.open('xb') as f:f.write(canonical(r))
    print(json.dumps({'status':r['status'],**r['summary'],'report_commitment_sha256':r['report_commitment_sha256']},sort_keys=True))


if __name__=='__main__': main()
