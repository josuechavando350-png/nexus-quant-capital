#!/usr/bin/env python3
"""Bounded read-only simulations through the documented public QuickNode demo.

Ephemeral state overrides provision NQC fixtures; they never write chain state.
Only fixed, archived blocks and read methods are accepted. No signing/broadcast.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request
import urllib.error

PUBLIC_DEMO = 'https://docs-demo.robinhood-mainnet.quiknode.pro/'
BLOCKS = {'0x3fa6f61', '0x3fa6f62',
          '0x53f9d3bedcdd3554f7447343ca03f9c9a5a7b61c692057f431d9225e04e1a917',
          '0x8e702487ffdd8f2ff97528407ba671f1a1d1d6f16a812e85fb5cb6625b6886d7'}
METHODS = {'eth_getCode', 'eth_call', 'debug_traceCall', 'eth_getBlockByHash'}
FIXTURES = {'0x0000000071727de22e5e9d8baf0edac6f37da032',
            '0xa16e02e87b7454126e5e10d957a927a7f5b5d2be',
            '0xb7a5bd0345ef1cc5e66bf61bdec17d2461fbd968',
            '0xeebe00ac0756308ac4aabfd76c05c4f3088b8883',
            '0x10c6e9530f1c1af873a391030a1d9e8ed0630d26',
            '0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError('redirect refused')


def validate(item):
    method, params = item['method'], item['params']
    if method not in METHODS or not item['label'].replace('-', '').replace('_', '').isalnum():
        raise ValueError('read-only method/label required')
    block = params[0] if method == 'eth_getBlockByHash' else params[1]
    if isinstance(block, dict):
        if block.get('requireCanonical') is not True:
            raise ValueError('canonical block required')
        block = block.get('blockHash')
    if block not in BLOCKS:
        raise ValueError('only the two fixed historical blocks are permitted')
    if method == 'debug_traceCall':
        config = params[2]
        if (config.get('tracer') not in {'callTracer', 'prestateTracer'} or
                config.get('timeout') != '10s' or config.get('reexec') != 0 or
                config.get('txIndex', '0x1') != '0x1'):
            raise ValueError('bounded built-in tracer required')
        overrides = config.get('stateOverrides', {})
    else:
        overrides = params[2] if method == 'eth_call' and len(params) > 2 else {}
    if not isinstance(overrides, dict) or not set(overrides) <= FIXTURES:
        raise ValueError('only NQC test fixtures may be overridden; protocol state must remain real')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--requests', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    plan = json.loads(args.requests.read_text())
    if not 1 <= len(plan) <= 8 or args.out.exists():
        raise ValueError('new output and at most eight requests required')
    for item in plan:
        validate(item)
    args.out.mkdir(parents=True)
    http = urllib.request.build_opener(NoRedirect())
    records, total = [], 0
    for i, item in enumerate(plan, 1):
        payload = {'jsonrpc': '2.0', 'id': i, 'method': item['method'], 'params': item['params']}
        record = {'label': item['label'], 'request': payload}
        records.append(record)
        try:
            request = urllib.request.Request(PUBLIC_DEMO, data=json.dumps(payload).encode(),
                                            headers={'Content-Type': 'application/json'})
            with http.open(request, timeout=20) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
            total += len(raw)
            if len(raw) > 8 * 1024 * 1024 or total > 32 * 1024 * 1024:
                raise ValueError('response budget exceeded')
            message = json.loads(raw)
            if message.get('id') != i or message.get('jsonrpc') != '2.0':
                raise ValueError('RPC envelope mismatch')
            filename = f'{i:02d}-{item["label"]}.json'
            (args.out / filename).write_bytes(raw)
            record.update(response_file=filename, response_sha256=hashlib.sha256(raw).hexdigest())
            # Fixed public endpoint contains no credentials. Preserve RPC errors
            # here to distinguish revert reasons from method/access restrictions.
            if 'error' in message:
                record['rpc_error'] = message['error']
                print(item['label'], 'RPC_ERROR', str(message['error'])[:500], flush=True)
            else:
                result = message.get('result')
                brief = {'error': result.get('error'), 'gasUsed': result.get('gasUsed'),
                         'output_prefix': str(result.get('output'))[:130]} if isinstance(result, dict) else str(result)[:130]
                print(item['label'], brief, flush=True)
        except urllib.error.HTTPError as error:
            record['http_error'] = error.code
            print('STOP HTTP', error.code, flush=True)
            break
        except (OSError, ValueError, RuntimeError) as error:
            record['stopped'] = type(error).__name__
            print('STOP', type(error).__name__, flush=True)
            break
        finally:
            (args.out / 'requests.json').write_text(json.dumps(records, indent=2) + '\n')


if __name__ == '__main__':
    main()
