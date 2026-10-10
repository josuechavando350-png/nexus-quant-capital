#!/usr/bin/env python3
"""Bounded read-only Base/Aave seed capture. One endpoint, no retries or failover.

Stores application-level HTTP response bodies, headers and current receive times.
These are historical state observations, never original decision-time witnesses.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import time
import urllib.request
import urllib.error

ENDPOINT = 'https://mainnet.base.org'
PROVIDER = '0xe20fcbdbffc4dd138ce8b2e6fbb6cb49777ad64d'
POOL = '0xa238dd80c259a72e81d7e4664a9801593f98d1c5'
TARGET = int(dt.datetime(2026, 10, 1, 5, 23, 35, tzinfo=dt.timezone.utc).timestamp())
SLOT = '0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc'
SELECTORS = {'getPool()': '0x026b1d5f', 'getPriceOracle()': '0xfca513a8',
 'getPoolDataProvider()': '0xe860accb', 'getReservesList()': '0xd1946dbc',
 'FLASHLOAN_PREMIUM_TOTAL()': '0x074b2e43', 'getConfiguration(address)': '0xc44b11f7',
 'getReserveTokensAddresses(address)': '0xd2493b6c', 'getAssetPrice(address)': '0xb3596f07',
 'decimals()': '0x313ce567', 'balanceOf(address)': '0x70a08231', 'totalSupply()': '0x18160ddd',
 'getReserveNormalizedIncome(address)': '0xd15e0053',
 'getReserveNormalizedVariableDebt(address)': '0x386497fd', 'BASE_CURRENCY_UNIT()': '0x8c89b64f'}

def need(ok, why):
    if not ok:
        raise ValueError(why)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def encoded(x):
    return (json.dumps(x, sort_keys=True, indent=2) + '\n').encode()

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def words(value):
    need(isinstance(value, str) and value.startswith('0x') and len(value[2:]) % 64 == 0, 'ABI words')
    return [int(value[i:i+64], 16) for i in range(2, len(value), 64)]

def address(word):
    need(type(word) is int and 0 < word < 2**160, 'ABI nonzero address')
    return '0x' + format(word, '040x')

def scalar(value):
    w = words(value)
    need(len(w) == 1, 'ABI scalar length')
    return w[0]

def reserves(value):
    w = words(value)
    need(len(w) >= 2 and w[0] == 32 and 0 < w[1] <= 256 and len(w) == 2+w[1], 'ABI reserve array')
    values = [address(x) for x in w[2:]]
    need(len(values) == len(set(values)), 'duplicate reserve')
    return values

class Capture:
    def __init__(self, out):
        self.out = out
        out.mkdir(parents=True, exist_ok=False)
        self.records = []
        self.last = 0
        self.started = now()

    def rpc(self, label, method, params):
        need(method in {'eth_chainId','eth_getBlockByNumber','eth_getBlockByHash',
                        'eth_call','eth_getCode','eth_getStorageAt'}, 'read-only method whitelist')
        need(len(self.records) < 1200, 'bounded RPC request cap')
        time.sleep(max(0, 1.1 - (time.monotonic() - self.last)))
        self.last = time.monotonic()
        i = len(self.records) + 1
        request = encoded({'jsonrpc':'2.0','id':i,'method':method,'params':params})
        sent = now()
        raw, status, headers, error = b'', None, [], None
        try:
            req = urllib.request.Request(ENDPOINT, data=request, headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req, timeout=45) as response:
                raw, status, headers = response.read(), response.status, list(response.headers.items())
        except urllib.error.HTTPError as exc:
            raw, status, headers, error = exc.read(), exc.code, list(exc.headers.items()), str(exc)
        except Exception as exc:
            error = type(exc).__name__ + ': ' + str(exc)
        received = now()
        request_name, response_name = f'{i:04d}.request.json', f'{i:04d}.response.bin'
        (self.out/request_name).write_bytes(request)
        (self.out/response_name).write_bytes(raw)
        self.records.append({'id':i,'label':label,'request':request_name,'response':response_name,
            'request_sha256':sha(request),'response_sha256':sha(raw),'http_status':status,
            'response_headers':headers,'sent_at':sent,'received_at':received,'error':error})
        (self.out/'progress.json').write_bytes(encoded({'records':self.records,'status':'RUNNING'}))
        need(error is None and status == 200, 'HTTP/transport failure; stopped: '+str(error))
        result = json.loads(raw)
        need(result.get('id') == i and result.get('jsonrpc') == '2.0'
             and 'error' not in result and 'result' in result, 'RPC failure or identity mismatch')
        return result['result']

def capture(r):
    need(int(r.rpc('chain', 'eth_chainId', []),16) == 8453, 'wrong chain')
    tip = r.rpc('finalized', 'eth_getBlockByNumber', ['finalized',False])
    need(int(tip['timestamp'],16) > TARGET, 'finalized head older than requested scope')
    lo, hi = 0, int(tip['number'],16)
    while lo < hi:
        mid = (lo+hi+1)//2
        h = r.rpc(f'locate:{mid}', 'eth_getBlockByNumber',[hex(mid),False])
        need(int(h['number'],16) == mid, 'block search identity')
        if int(h['timestamp'],16) <= TARGET:
            lo = mid
        else:
            hi = mid-1
    anchor = r.rpc('anchor','eth_getBlockByNumber',[hex(lo),False])
    nxt = r.rpc('next','eth_getBlockByNumber',[hex(lo+1),False])
    parent = r.rpc('parent','eth_getBlockByNumber',[hex(lo-1),False])
    need(int(anchor['timestamp'],16) <= TARGET < int(nxt['timestamp'],16)
         and nxt['parentHash'] == anchor['hash'] and anchor['parentHash'] == parent['hash'], 'anchor boundary/lineage')
    block = {'blockHash':anchor['hash'], 'requireCanonical':True}
    def call(label, to, signature, arg=None):
        data = SELECTORS[signature] + (arg[2:].zfill(64) if arg else '')
        return r.rpc(label,'eth_call',[{'to':to,'data':data},block])
    pool = address(scalar(call('pool',PROVIDER,'getPool()')))
    need(pool == POOL,'provider/pool disagreement')
    oracle = address(scalar(call('oracle',PROVIDER,'getPriceOracle()')))
    data_provider = address(scalar(call('data-provider',PROVIDER,'getPoolDataProvider()')))
    for name, addr in [('provider',PROVIDER),('pool',pool),('oracle',oracle),('data-provider',data_provider)]:
        code = r.rpc('code:'+name,'eth_getCode',[addr,block])
        need(code not in ('0x','0x0',None),'empty deployed code')
    impl = address(scalar(r.rpc('pool-implementation','eth_getStorageAt',[pool,SLOT,block])))
    need(r.rpc('code:pool-implementation','eth_getCode',[impl,block]) != '0x','empty implementation')
    premium = scalar(call('flash-premium-bps',pool,'FLASHLOAN_PREMIUM_TOTAL()'))
    unit = scalar(call('oracle-unit',oracle,'BASE_CURRENCY_UNIT()'))
    assets = reserves(call('reserves',pool,'getReservesList()'))
    for asset in assets:
        tokens = words(call(asset+':tokens',data_provider,'getReserveTokensAddresses(address)',asset))
        need(len(tokens) == 3,'reserve token tuple')
        atoken, debt = address(tokens[0]), address(tokens[2])
        for suffix,to,sig,arg in [
            ('configuration',pool,'getConfiguration(address)',asset),
            ('price',oracle,'getAssetPrice(address)',asset),
            ('decimals',asset,'decimals()',None),
            ('underlying-at-atoken',asset,'balanceOf(address)',atoken),
            ('atoken-supply',atoken,'totalSupply()',None),
            ('variable-debt-supply',debt,'totalSupply()',None),
            ('liquidity-index',pool,'getReserveNormalizedIncome(address)',asset),
            ('variable-debt-index',pool,'getReserveNormalizedVariableDebt(address)',asset)]:
            scalar(call(asset+':'+suffix,to,sig,arg))
        for suffix,addr in [('underlying',asset),('atoken',atoken),('variable-debt',debt)]:
            need(r.rpc(asset+':code:'+suffix,'eth_getCode',[addr,block]) != '0x','empty token code')
    final = r.rpc('anchor-after','eth_getBlockByNumber',[hex(lo),False])
    need(final == anchor,'anchor changed during capture')
    return {'anchor':anchor,'asset_count':len(assets),'flash_premium_bps_observed':premium,
            'oracle_unit_observed':unit}

def main(out):
    r = Capture(out)
    result, failure = None, None
    try:
        result = capture(r)
    except Exception as exc:
        failure = type(exc).__name__+': '+str(exc)
    report = {'schema':'nqc-base-aave-seed-capture-v1','endpoint':ENDPOINT,'chain_id':8453,
        'target_timestamp':TARGET,'producer_sha256':sha(Path(__file__).read_bytes()),
        'started_at':r.started,'ended_at':now(),'status':'COMPLETE' if failure is None else 'FAILED',
        'failure':failure,'records':r.records,'result':result,'workers':1,
        'minimum_interval_seconds':'1.1','max_requests':1200,'retries':0,
        'gas_spent':False,'census_closed':False,'original_decision_time_evidence':False}
    (out/'acquisition.json').write_bytes(encoded(report))
    print(json.dumps({k:v for k,v in report.items() if k not in ('records','result')},sort_keys=True),flush=True)
    return 0 if failure is None else 1

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    raise SystemExit(main(p.parse_args().out))

