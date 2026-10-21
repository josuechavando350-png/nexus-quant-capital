#!/usr/bin/env python3
"""Bounded read-only acquisition. No signing, sends, paid services or secrets in output."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

TX = '0x87de0f52c1c8c2dac00671a8dba7058ccf20301107a7450471edec6a0f6f3bc2'
PARENT = 25666957
BLOCK = PARENT + 1
LIMIT = 30_000_000
READS = {'eth_chainId', 'eth_getBlockByNumber', 'eth_getTransactionByHash',
         'eth_getTransactionReceipt', 'eth_getCode', 'eth_getStorageAt',
         'eth_getBalance', 'eth_getTransactionCount', 'eth_getProof',
         'eth_call', 'debug_traceTransaction'}

def redact(s):
    for name in ('NQC_RPC_URL', 'NQC_BLOCKSCOUT_SESSION'):
        secret = os.environ.get(name, '')
        if secret:
            s = s.replace(secret, '[REDACTED]')
            if name == 'NQC_RPC_URL':
                s = s.replace(secret.rsplit('/', 1)[-1], '[REDACTED]')
    return s

def fetch(url, payload=None, headers=None):
    headers = headers or {}
    req = urllib.request.Request(url, data=payload, headers=headers)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=18) as r:
                raw = r.read(LIMIT + 1)
                status = r.status
            if len(raw) > LIMIT:
                return {'status': 'BLOCKED', 'reason': 'RESPONSE_TOO_LARGE'}
            return {'status': 'RECEIVED', 'http_status': status,
                    'body': redact(raw.decode('utf-8', errors='replace'))}
        except urllib.error.HTTPError as e:
            if e.code >= 500 and attempt < 3:
                continue
            return {'status': 'BLOCKED', 'http_status': e.code,
                    'body': redact(e.read(16384).decode('utf-8', errors='replace'))}
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return {'status': 'BLOCKED', 'reason': type(e).__name__, 'message': redact(str(e))}

def rpc(url, method, params):
    if method not in READS:
        raise ValueError('READ_ONLY_ALLOWLIST')
    result = fetch(url, json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode(),
                   {'Content-Type': 'application/json'})
    if result['status'] == 'RECEIVED':
        try:
            obj = json.loads(result['body'])
            if not isinstance(obj, dict) or obj.get('jsonrpc') != '2.0' or obj.get('id') != 1:
                result.update(status='BLOCKED', reason='INVALID_RPC_ENVELOPE')
            elif 'error' in obj:
                result.update(status='BLOCKED', reason='RPC_ERROR', rpc_error=obj['error'])
            elif obj.get('result') is None:
                result.update(status='BLOCKED', reason='NULL_OR_MISSING_RESULT')
        except ValueError:
            result.update(status='BLOCKED', reason='INVALID_JSON')
    return result

def save(out, label, result, request):
    result = dict(result, request=request, timestamp_utc=dt.datetime.now(dt.timezone.utc).isoformat())
    path = out / (label + '.json')
    with path.open('x') as f:
        json.dump(result, f, indent=2, sort_keys=True); f.write('\n')
    print(label, result['status'], result.get('http_status', result.get('reason', '')))
    return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--source', choices=['publicnode', 'drpc', 'alchemy', 'blockscout-trace'], required=True)
    args = p.parse_args()
    out = args.output; out.mkdir(parents=True, exist_ok=True)
    if args.source == 'blockscout-trace':
        session = os.environ.get('NQC_BLOCKSCOUT_SESSION')
        if not session:
            return 2
        params = {'chain_id':'1', 'endpoint_path':f'/api/v2/transactions/{TX}/raw-trace', 'session_id':session}
        url = 'https://mcp.blockscout.com/v1/direct_api_call?' + urllib.parse.urlencode(params)
        result = fetch(url, headers={'User-Agent':'Blockscout-SkillGuidedScript/0.6.0',
                                    'X-Blockscout-Allow-Large-Response':'true'})
        save(out, 'blockscout_raw_trace_transport', result, {k:v for k,v in params.items() if k != 'session_id'})
        return 0 if result['status'] == 'RECEIVED' else 2
    if args.source == 'alchemy':
        url = os.environ.get('NQC_RPC_URL', '')
        parsed = urllib.parse.urlsplit(url)
        if not url:
            save(out, 'alchemy_configuration', {'status':'BLOCKED','reason':'MISSING_NQC_RPC_URL'}, {'source':'alchemy','requests_sent':0})
            return 2
        if parsed.scheme != 'https' or parsed.hostname != 'eth-mainnet.g.alchemy.com' or not parsed.path.startswith('/v2/') or parsed.query or parsed.username:
            raise ValueError('INVALID_ALCHEMY_ENDPOINT')
    elif args.source == 'drpc':
        # Public endpoint published by https://drpc.org/docs/ethereum-api.
        url = 'https://eth.drpc.org/'
    else:
        # Public read-only endpoint published by https://ethereum.publicnode.com/.
        url = 'https://ethereum-rpc.publicnode.com'
    source = args.source
    r = save(out, source + '_chain', rpc(url, 'eth_chainId', []), {'method':'eth_chainId','params':[],'source':source})
    try:
        ok = r['status'] == 'RECEIVED' and json.loads(r.get('body','{}')).get('result') == '0x1'
    except ValueError:
        ok = False
    if not ok:
        return 2
    calls = [('parent_header','eth_getBlockByNumber',[hex(PARENT),False]),
             ('target_header','eth_getBlockByNumber',[hex(BLOCK),False]),
             ('transaction','eth_getTransactionByHash',[TX]),
             ('receipt','eth_getTransactionReceipt',[TX]),
             ('morpho_code_parent','eth_getCode',['0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb',hex(PARENT)]),
             ('prestate','debug_traceTransaction',[TX,{'tracer':'prestateTracer','timeout':'10s'}]),
             ('call_trace','debug_traceTransaction',[TX,{'tracer':'callTracer','tracerConfig':{'withLog':True},'timeout':'10s'}]),
             ('state_diff','debug_traceTransaction',[TX,{'tracer':'prestateTracer','tracerConfig':{'diffMode':True},'timeout':'10s'}])]
    failed = False
    for label, method, params in calls:
        result = save(out, source+'_'+label, rpc(url,method,params), {'method':method,'params':params,'source':source})
        failed |= result['status'] != 'RECEIVED'
        if result.get('http_status') in (401,403,429):
            break  # Do not continue against an authentication, access or rate limit.
    return 2 if failed else 0

if __name__ == '__main__':
    raise SystemExit(main())
