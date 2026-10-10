#!/usr/bin/env python3
"""Authenticate the actual denied Base preflight; never admit market state."""
import argparse
import datetime as dt
import io
import json
from pathlib import Path
import zipfile

from collect import ENDPOINT, TARGET, encoded, need, sha

HERE = Path(__file__).resolve().parent
ARCHIVE_SHA = '8aae30b9c374603b3461ab46d5cf9644d4d45ebfdf4f4539bc621622d7de9819'
SOURCE_SHA = '2299440c4101165210e3edf648dc6151d9068b1008caedeb9616ffb56b424740'
ADDRESS_BOOK_SHA = '135e2f325b53140c5a82895cf40debc80323fed77bd3ebb240a8d00248ba02ae'

def members(raw):
    need(len(raw) == 6734 and sha(raw) == ARCHIVE_SHA, 'archive bytes/digest')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        expected = {'0001.request.json','0001.response.bin','acquisition.json','progress.json','collect.py'}
        need(len(z.namelist()) == len(expected) and set(z.namelist()) == expected, 'archive member inventory')
        return {n:z.read(n) for n in z.namelist()}

def reconcile(files):
    acq = json.loads(files['acquisition.json'])
    need(acq['schema'] == 'nqc-base-aave-seed-capture-v1'
         and acq['endpoint'] == ENDPOINT and acq['chain_id'] == 8453
         and acq['target_timestamp'] == TARGET, 'capture scope')
    need(acq['producer_sha256'] == sha(files['collect.py']) == SOURCE_SHA, 'producer source identity')
    need(acq['status'] == 'FAILED' and acq['result'] is None
         and '403' in acq['failure'], 'failure must remain failed')
    need(acq['workers'] == 1 and acq['retries'] == 0
         and acq['max_requests'] == 1200 and acq['minimum_interval_seconds'] == '1.1', 'capture controls')
    need(all(acq[k] is False for k in ['gas_spent','census_closed','original_decision_time_evidence']), 'non-claims')
    records = acq['records']
    need(len(records) == 1 and json.loads(files['progress.json'])['records'] == records, 'no retry / exact progress records')
    row = records[0]
    need(row['id'] == 1 and row['label'] == 'chain'
         and row['request'] == '0001.request.json' and row['response'] == '0001.response.bin', 'request binding')
    need(sha(files[row['request']]) == row['request_sha256']
         and sha(files[row['response']]) == row['response_sha256'], 'raw request/response digests')
    need(json.loads(files[row['request']]) == {'id':1,'jsonrpc':'2.0','method':'eth_chainId','params':[]}, 'read-only request')
    need(row['http_status'] == 403 and row['error'] == 'HTTP Error 403: Forbidden'
         and files[row['response']] == b'error code: 1010\n', 'exact access rejection')
    dates = [acq['started_at'], row['sent_at'], row['received_at'], acq['ended_at']]
    parsed = [dt.datetime.fromisoformat(x) for x in dates]
    need(all(x.tzinfo is not None for x in parsed) and parsed == sorted(parsed), 'capture chronology')
    return {'schema':'nqc-base-aave-preflight-readback-v1','status':'BASE_RPC_ACCESS_BLOCKED',
        'archive_sha256':ARCHIVE_SHA,'producer_sha256':SOURCE_SHA,'endpoint':ENDPOINT,
        'intended_chain_id':8453,'chain_id_observed':None,'anchor_observed':None,
        'http_requests':1,'http_status':403,'provider_error_code':1010,
        'request_sha256':row['request_sha256'],'response_sha256':row['response_sha256'],
        'received_at':row['received_at'],'reserve_count':None,'state_verified_reserves':0,
        'market_discovery_complete':False,'principal_funding_verified':False,
        'net_pnl':None,'census_closed':False,'gas_spent':False,
        'next_dependency':'Authorized Base RPC access accepting read-only queries from the existing server',
        'documentary_source':{'repository':'aave-dao/aave-address-book',
          'commit':'6a83d11893d6687bf6b9fd091a2a5320b3e1966e',
          'path':'src/AaveV3Base.sol','sha256':ADDRESS_BOOK_SHA,
          'historical_deployment_state_proven':False}}

def verify():
    need(sha((HERE/'AaveV3Base.source.sol').read_bytes()) == ADDRESS_BOOK_SHA,'documentary source digest')
    need(sha((HERE/'collect.py').read_bytes()) == SOURCE_SHA,'local collector/source mismatch')
    return reconcile(members((HERE/'capture-001.zip').read_bytes()))

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    with a.out.open('xb') as f:
        f.write(encoded(verify()))
