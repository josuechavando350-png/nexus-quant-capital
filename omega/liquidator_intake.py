"""Retained Blockscout logs bound to all 139 original event commitments.

Identifies the protocol-event liquidator and borrower; no claim about beneficial
ownership, transaction sender, oracle causation, complete costs or NQC execution.
The log API omits block hash and removal status. Original pinned block hashes are
used only to verify old event commitments, never claimed as newly observed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import tempfile

from historical_intake import (EVIDENCE, ROOT, AUTHORITIES, build_ledger, verify_ledger, fields,
                               need, same, unpack, utc)
from integrity import canonical, digest, read_regular, strict_json
from evidence_store import admit, audit_store, read_batch
from historical_pipeline import SOURCE_NAMES, LEDGER_NAME, ingest, query

PIN_SHA256='65649ad0c3502e32edc430a33c1e09d7afe5fdfcfb3ef06b304d477d92ff057f'
POOL='0x87870bca3f3fd6335c3f4ce8392d69350b4fa4e2'
TOPIC='0xe413a321e8681d831f4dbccbca790d2952b56f977908e45be37335533e005286'
SCHEMA='nqc.omega.liquidator-intake.v1'
CAPTURE_NAMES={'liquidator-capture-pin.json','liquidator-log-capture.zip'}
SCOPES={'first':(25880316,25987833,63),'second':(25987834,26095351,76)}


def quantity(value):
    need(type(value) is str and re.fullmatch(r'0x(?:0|[1-9a-f][0-9a-f]*)',value), 'invalid_hex_quantity')
    return int(value,16)


def load_logs(directory=EVIDENCE):
    pin_raw=read_regular(Path(directory)/'liquidator-capture-pin.json')
    need(digest(pin_raw)==PIN_SHA256,'liquidator_capture_pin_changed')
    pin=strict_json(pin_raw)
    raw=read_regular(Path(directory)/'liquidator-log-capture.zip')
    need(digest(raw)==pin['archive_sha256'] and len(raw)==pin['archive_bytes'],'liquidator_archive_changed')
    members=unpack(raw,pin['members'])
    need(set(members)=={'first.json','second.json'},'liquidator_capture_inventory')
    logs=[];captures=[]
    for name,(start,end,count) in SCOPES.items():
        capture=strict_json(members[name+'.json'])
        same(capture['request'],{'chain_id':'1','endpoint_path':'/api','query_params':{
            'module':'logs','action':'getLogs','fromBlock':start,'toBlock':end,'address':POOL,'topic0':TOPIC}},
            'capture_request_scope')
        need(utc(capture['retrieved_at'])>utc('2026-10-22T00:00:00Z'),'capture_time')
        response=capture['response']
        fields(response,{'pagination':None},'capture_pagination')
        fields(response['data'],{'message':'OK','status':'1'},'capture_status')
        rows=response['data']['result']
        need(type(rows) is list and len(rows)==count<1000,'capture_row_count_or_cap')
        need(all(start<=quantity(r['blockNumber'])<=end for r in rows),'capture_row_outside_range')
        logs.extend(rows)
        captures.append({'range_start':start,'range_end':end,'count':count,
                         'retrieved_at':capture['retrieved_at'],'capture_sha256':digest(members[name+'.json'])})
    return logs,captures


def reconcile_logs(ledger,logs):
    source={(r['transaction_hash'],e['log_index']):(r,e) for r in ledger['records'] for e in r['events']}
    need(type(logs) is list and len(logs)==len(source)==139,'raw_event_universe')
    rows=[];seen=set()
    required={'address','blockNumber','data','gasPrice','gasUsed','logIndex','timeStamp','topics',
              'transactionHash','transactionIndex'}
    for raw in logs:
        need(type(raw) is dict and set(raw)==required,'raw_log_shape')
        need(raw['address']==POOL and type(raw['topics']) is list and len(raw['topics'])==4
             and raw['topics'][0]==TOPIC and all(type(t) is str and re.fullmatch(r'0x[0-9a-f]{64}',t)
                                               for t in raw['topics']),'raw_log_topics')
        need(type(raw['data']) is str and re.fullmatch(r'0x[0-9a-f]{256}',raw['data']),'raw_abi_length')
        need(all(t[2:26]=='0'*24 for t in raw['topics'][1:]),'indexed_address_padding')
        key=(raw['transactionHash'],quantity(raw['logIndex']))
        need(key in source and key not in seen,'unknown_or_duplicate_event')
        seen.add(key);r,e=source[key]
        block=quantity(raw['blockNumber']);index=quantity(raw['transactionIndex'])
        need(block==r['block_number'] and index==r['transaction_index'],'raw_log_anchor')
        proof={'pool':raw['address'],'topics':raw['topics'],'data':raw['data'],
            'block_hash':r['block_hash'],'block_number':block,'tx_hash':r['transaction_hash'],
            'tx_index':index,'log_index':e['log_index']}
        need(digest(canonical(proof))==e['event_commitment_sha256'],'original_event_commitment_mismatch')
        words=[raw['data'][2+64*i:2+64*(i+1)] for i in range(4)]
        need(words[2][:24]=='0'*24 and int(words[3],16) in (0,1),'raw_abi_padding_or_boolean')
        borrower='0x'+raw['topics'][3][-40:];liquidator='0x'+words[2][-40:]
        leg=next(l for l in r['liquidation_legs'] if l['log_index']==e['log_index'])
        fields(leg,{'borrower_identity_sha256':digest(raw['topics'][3].encode()),
            'liquidator_identity_sha256':digest(liquidator.encode()),
            'debt_to_cover_raw':str(int(words[0],16)),
            'collateral_liquidated_raw':str(int(words[1],16)),
            'collateral_asset':'0x'+raw['topics'][1][-40:],
            'debt_asset':'0x'+raw['topics'][2][-40:],
            'receive_a_token':bool(int(words[3],16))},'original_leg')
        gas,price=quantity(raw['gasUsed']),quantity(raw['gasPrice'])
        need(gas==int(r['receipt']['gas_used']) and price==int(r['receipt']['effective_gas_price_wei']),
             'log_gas_metadata_disagrees_with_drpc')
        locator={'schema':'nqc.omega.aave-position-locator.v1','chain_id':1,
                 'pool':POOL,'borrower_address':borrower}
        row={'transaction_hash':r['transaction_hash'],'block_number':block,
            'block_hash':r['block_hash'],'block_hash_basis':'PINNED_ORIGINAL_NOT_NEWLY_OBSERVED',
            'removed_status':None,'transaction_index':index,'log_index':e['log_index'],
            'liquidator_address':liquidator,'liquidator_role':'AAVE_LIQUIDATION_CALL_EVENT_ARGUMENT',
            'borrower_address':borrower,'position_locator':locator,
            'position_locator_sha256':digest(canonical(locator)),
            'event_commitment_sha256':e['event_commitment_sha256'],'raw_log_sha256':digest(canonical(raw)),
            'gas_metadata_matches_drpc':True,'execution_gas_wei':str(gas*price),
            'oracle_update_block':None,'oracle_to_liquidator_blocks':None,
            'builder_payment_usd_wad':None,'complete_net_margin_usd_wad':None,
            'nqc_execution':False,'beneficial_owner_identified':False,
            'protocol_position_truth_certified':False}
        row['record_commitment_sha256']=digest(canonical(row));rows.append(row)
    need(seen==set(source),'event_coverage_gap')
    return sorted(rows,key=lambda r:(r['block_number'],r['transaction_index'],r['log_index']))


def build_liquidator_report(directory=EVIDENCE,root=ROOT):
    ledger=build_ledger(directory,root);logs,captures=load_logs(directory)
    rows=reconcile_logs(ledger,logs);by_tx={}
    for r in rows:by_tx.setdefault(r['transaction_hash'],[]).append(r)
    transactions=[]
    for tx,group in sorted(by_tx.items()):
        addresses=sorted({r['liquidator_address'] for r in group})
        transactions.append({'transaction_hash':tx,'liquidator_addresses':addresses,
            'single_event_liquidator_address':addresses[0] if len(addresses)==1 else None,
            'event_count':len(group),'execution_gas_wei':group[0]['execution_gas_wei'],
            'oracle_to_liquidator_blocks':None,'complete_net_margin_usd_wad':None})
    report={'schema':SCHEMA,'status':'SOURCE_BOUND_LIQUIDATOR_IDENTITIES_VERIFIED',
        'scope':'HISTORICAL_PROTOCOL_EVENT_LIQUIDATORS_NOT_NQC_CAPTURE',
        'historical_ledger_commitment':ledger['ledger_commitment_sha256'],'captures':captures,
        'events':rows,'transactions':transactions,'summary':{
            'event_count':len(rows),'transaction_count':len(transactions),
            'identified_liquidator_transaction_count':sum(t['single_event_liquidator_address'] is not None for t in transactions),
            'distinct_liquidator_addresses':len({r['liquidator_address'] for r in rows}),
            'distinct_borrower_addresses':len({r['borrower_address'] for r in rows}),
            'execution_gas_wei_once_per_transaction':str(sum(int(t['execution_gas_wei']) for t in transactions)),
            'oracle_delay_observation_count':0,'complete_cost_transaction_count':0},
        'capture_replayed_offline':True,'new_api_query_performed':False,
        'independent_full_window_event_consensus':False,'full_receipt_parity_complete':False,
        'block_hashes_reobserved':False,'current_market_coverage_proven':False,
        'authorities':AUTHORITIES}
    report['report_commitment_sha256']=digest(canonical(report));return report


def store_identities(store,directory=EVIDENCE,root=ROOT):
    base=ingest(store,directory,root)
    objects=read_batch(store,base['batch'])
    objects.update({n:read_regular(Path(directory)/n) for n in CAPTURE_NAMES})
    with tempfile.TemporaryDirectory(prefix='omega-identities-') as tmp:
        for n,b in objects.items():(Path(tmp)/n).write_bytes(b)
        report=build_liquidator_report(Path(tmp),root)
    objects['liquidator-report.json']=canonical(report)
    batch=admit(store,objects)
    return {'base_batch':base['batch'],'identity_batch':batch,'report':report,
            'journal_head':audit_store(store)['journal_head']}


def query_identities(store,batch,root=ROOT):
    objects=read_batch(store,batch)
    need(set(objects)==SOURCE_NAMES|CAPTURE_NAMES|{LEDGER_NAME,'liquidator-report.json'},'identity_batch_inventory')
    with tempfile.TemporaryDirectory(prefix='omega-identity-query-') as tmp:
        for n,b in objects.items():(Path(tmp)/n).write_bytes(b)
        verify_ledger(strict_json(objects[LEDGER_NAME]),Path(tmp),root)
        expected=build_liquidator_report(Path(tmp),root)
    same(strict_json(objects['liquidator-report.json']),expected,'stored_identity_differs_from_sources')
    return expected


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path)
    a=p.parse_args()
    try:
        r=build_liquidator_report()
        if a.output:
            with a.output.open('xb') as f:f.write(canonical(r))
        print(json.dumps({'status':r['status'],**r['summary'],'report_commitment_sha256':r['report_commitment_sha256'],
                          'census_closed':False},sort_keys=True));return 0
    except (ValueError,KeyError,TypeError,OSError) as e:
        print(json.dumps({'status':'LIQUIDATOR_INTAKE_BLOCKED','reason':str(e),'census_closed':False}));return 1


if __name__=='__main__':raise SystemExit(main())
