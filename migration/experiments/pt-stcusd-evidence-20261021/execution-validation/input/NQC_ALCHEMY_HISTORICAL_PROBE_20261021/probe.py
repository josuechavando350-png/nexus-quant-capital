#!/usr/bin/env python3
"""NQC: bounded READ-ONLY probe for the historical PT-stcUSD liquidation.

Uses only standard library. API credentials are accepted only through NQC_RPC_URL.
No transaction signing, sending, secret persistence, package installation or daemon.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import sys
import urllib.request
import urllib.error

TX_HASH = '0x87de0f52c1c8c2dac00671a8dba7058ccf20301107a7450471edec6a0f6f3bc2'
BLOCK_NUMBER = 25666958
PARENT_NUMBER = BLOCK_NUMBER - 1
MORPHO_BLUE = '0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb'
EXECUTOR = '0x3f73fb5e1984d73d5e9065fbf7ab80d1ee73860e'
MAX_RESULT_BYTES = 30_000_000

class RPCFailure(Exception):
    def __init__(self, category, code=None):
        self.category = category
        self.code = code
        super().__init__(category)

def request_rpc(url, method, params, timeout=12, opener=None):
    # Strict method allowlist: cannot accidentally sign, broadcast, deploy or spend.
    allowed = {'eth_chainId', 'eth_getBlockByNumber', 'eth_getTransactionByHash',
               'eth_getTransactionReceipt', 'eth_getCode', 'eth_getProof', 'debug_traceTransaction'}
    if method not in allowed:
        raise ValueError('Method not on read-only allowlist')
    body = json.dumps({'jsonrpc':'2.0', 'id':1, 'method':method, 'params':params},
                      separators=(',',':')).encode()
    req = urllib.request.Request(url, body, method='POST', headers={'Content-Type':'application/json'})
    if opener is None:
        opener = urllib.request.urlopen
    try:
        with opener(req, timeout=timeout) as resp:
            raw = resp.read(MAX_RESULT_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise RPCFailure('HTTP_ERROR', exc.code) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RPCFailure('TRANSPORT_OR_DNS_ERROR') from None
    if len(raw) > MAX_RESULT_BYTES:
        raise RPCFailure('RESPONSE_TOO_LARGE')
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        raise RPCFailure('INVALID_JSON') from None
    if not isinstance(data, dict):
        raise RPCFailure('INVALID_RESPONSE')
    if 'error' in data:
        rpc_error = data['error']
        code = rpc_error.get('code') if isinstance(rpc_error,dict) else None
        raise RPCFailure('RPC_ERROR', code)
    if 'result' not in data:
        raise RPCFailure('MISSING_RESULT')
    return data['result']

def run_probe(url, output_dir, trace=False, transport=request_rpc):
    if not (url.startswith('https://eth-mainnet.g.alchemy.com/v2/') and
            len(url.split('/v2/', 1)[1]) >= 10):
        raise ValueError('Provide an Ethereum Mainnet Alchemy HTTPS endpoint via NQC_RPC_URL')
    output_dir = pathlib.Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    methods = [
        ('chain_id','eth_chainId',[]),
        ('parent_header','eth_getBlockByNumber',[hex(PARENT_NUMBER), False]),
        ('target_header','eth_getBlockByNumber',[hex(BLOCK_NUMBER), False]),
        ('original_transaction','eth_getTransactionByHash',[TX_HASH]),
        ('original_receipt','eth_getTransactionReceipt',[TX_HASH]),
        ('executor_code_parent','eth_getCode',[EXECUTOR,hex(PARENT_NUMBER)]),
        ('morpho_account_proof_parent','eth_getProof',[MORPHO_BLUE, [], hex(PARENT_NUMBER)])
    ]
    if trace:
        methods += [
            ('prestate_trace','debug_traceTransaction',
             [TX_HASH, {'tracer':'prestateTracer', 'timeout':'10s'}]),
            ('call_trace','debug_traceTransaction',
             [TX_HASH, {'tracer':'callTracer', 'timeout':'10s'}]),
        ]
    report = {'status':'BLOCKED', 'chain_id_expected':'0x1', 'block':BLOCK_NUMBER,
              'parent_block':PARENT_NUMBER,'tx_hash':TX_HASH,
              'mode':'READ_ONLY','trace_requested':trace,
              'runs':{}, 'rpc_endpoint_saved':False,'authorized_live_trading':False}
    chain_ok = False
    for label, method, params in methods:
        if label != 'chain_id' and not chain_ok:
            report['runs'][label] = {'status':'NOT_ATTEMPTED_CHAIN_UNVERIFIED'}
            continue
        try:
            result = transport(url,method,params)
            if result is None:
                raise RPCFailure('NULL_RESULT')
            if label=='chain_id':
                chain_ok = result == '0x1'
                if not chain_ok:
                    raise RPCFailure('WRONG_CHAIN')
            if label=='parent_header' and (not isinstance(result,dict) or int(result['number'],16)!=PARENT_NUMBER):
                raise RPCFailure('WRONG_PARENT_BLOCK')
            if label=='target_header' and (not isinstance(result,dict) or int(result['number'],16)!=BLOCK_NUMBER):
                raise RPCFailure('WRONG_TARGET_BLOCK')
            if label=='original_transaction' and (not isinstance(result,dict) or
                 (result['hash'].lower()!=TX_HASH or int(result['blockNumber'],16)!=BLOCK_NUMBER or
                  int(result['transactionIndex'],16)!=0)):
                raise RPCFailure('TX_NOT_AT_EXPECTED_POSITION')
            if label=='original_receipt' and (not isinstance(result,dict) or
                 result.get('transactionHash','').lower()!=TX_HASH or result.get('status')!='0x1'):
                raise RPCFailure('RECEIPT_MISMATCH')
            serialized = (json.dumps(result,sort_keys=True,separators=(',',':'),ensure_ascii=True)+'\n').encode()
            fname = f'{label}.json'
            (output_dir/fname).write_bytes(serialized)
            report['runs'][label] = {'status':'SAVED','filename':fname,'sha256':hashlib.sha256(serialized).hexdigest(), 'bytes':len(serialized)}
        except RPCFailure as exc:
            report['runs'][label]={'status':'BLOCKED', 'category':exc.category,'code':exc.code}
        except (KeyError, TypeError, ValueError) as exc:
            report['runs'][label]={'status':'BLOCKED','category':'UNEXPECTED_SHAPE'}
    must_have = ('chain_id','parent_header','target_header','original_transaction','original_receipt')
    basic = all(report['runs'][x]['status']=='SAVED' for x in must_have)
    report['status']='BASE_READS_PASS_REPLAY_NOT_VERIFIED' if basic else 'BLOCKED'
    report['timestamp_utc']=dt.datetime.now(dt.timezone.utc).isoformat()
    (output_dir/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf8')
    return report

def main():
    parser=argparse.ArgumentParser(description='NQC: archive data check, no signatures or broadcasts')
    parser.add_argument('--output',default='nqc_archive_probe_output')
    parser.add_argument('--trace', action='store_true',help='Optional 2 extra historical trace requests (may use more provider credits)')
    args=parser.parse_args()
    url=os.environ.get('NQC_RPC_URL','')
    if not url:
        print('BLOCKED_MISSING_NQC_RPC_URL: set it locally in your terminal, never paste it into GitHub.'); return 2
    try:
        report=run_probe(url,args.output,trace=args.trace)
    except ValueError as exc:
        print('BLOCKED_INVALID_PROVIDER_CONFIG'); return 2
    for name,result in report['runs'].items():
        print(f"{name}: {result['status']}"+(f" ({result['category']})" if 'category' in result else ''))
    print('Report:',str(pathlib.Path(args.output)/'report.json'))
    print('No keys, RPC URL, contracts deployed, live transactions, or signed payloads.')
    return 0 if report['status']=='BASE_READS_PASS_REPLAY_NOT_VERIFIED' else 2

if __name__=='__main__':
    sys.exit(main())
