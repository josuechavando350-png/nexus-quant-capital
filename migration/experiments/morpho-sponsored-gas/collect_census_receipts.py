"""Bounded, public, read-only receipt collection for the frozen diagnostic sample.

No signing, submission, credentials, retries or alternative endpoints. Existing
responses are immutable. A null receipt remains missing evidence. This script is
optional; monthly_census.py reproduces the analysis entirely offline.
"""
import datetime
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / 'evidence/2026-10-17-monthly'
URL = 'https://rpc.flashbots.net/fast'
CASE_B = '0x46300e9614c547118ecdd524bc7218208088cc4ae9e5bd534e62055d38f9925b'


def main():
    selection = json.loads((EVIDENCE / 'receipt-selection.json').read_text())
    rows = selection['transactions']
    if len(rows) > 30 or len({x['tx_hash'] for x in rows}) != len(rows):
        raise ValueError('bounded unique diagnostic sample required')
    for index, row in enumerate(rows):
        tx_hash = row['tx_hash']
        if tx_hash == CASE_B:
            print('reuse archived B receipt', flush=True)
            continue
        path = EVIDENCE / f'receipt-{index:02}.json'
        if path.exists():
            cached = json.loads(path.read_text())
            if (cached.get('http_status') != 200 or cached.get('response', {}).get('error')
                    or 'result' not in cached.get('response', {})):
                print('Stopped at cached access/transport/RPC error; no retry.', flush=True)
                return 2
            print('cached', path.name, flush=True)
            continue
        request = {'jsonrpc': '2.0', 'id': 1,
                   'method': 'eth_getTransactionReceipt', 'params': [tx_hash]}
        record = {'url': URL, 'request': request,
                  'retrieved_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        try:
            with urllib.request.urlopen(urllib.request.Request(
                    URL, json.dumps(request).encode(), {'Content-Type': 'application/json'}),
                    timeout=20) as response:
                record.update(http_status=response.status, response=json.load(response))
        except urllib.error.HTTPError as error:
            record.update(http_status=error.code, body=error.read().decode())
        except (TimeoutError, urllib.error.URLError, ValueError) as error:
            record.update(error=str(error))
        # Exclusive creation prevents accidental replacement of evidence.
        with path.open('x') as output:
            output.write(json.dumps(record, indent=2) + '\n')
        result = record.get('response', {})
        print(path.name, record.get('http_status'),
              'receipt' if result.get('result') else 'unavailable', flush=True)
        if record.get('http_status') != 200 or result.get('error') or 'result' not in result:
            print('Stopped on access, transport or RPC error; no retry.', flush=True)
            return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
