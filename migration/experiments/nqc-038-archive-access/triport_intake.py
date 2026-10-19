"""Explicit fixed-number transport for the unchanged NQC037 proof verifier.

Plan is offline. Collect requires an operator-provided NQC_TRIPORT_API_KEY.
No account creation, retries, redirects, selector fallback or write methods.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'nqc-037-historical-state' / 'src'))
import intake
import verify as v

ENDPOINT = 'https://triport.io/rpc/robinhood'
MAX_RESPONSE = 16 * 1024 * 1024


def wire_plan():
    operations = copy.deepcopy(intake.plan())
    for operation in operations:
        request = operation['request']
        if request['method'] in {'eth_getProof', 'eth_getCode'}:
            selector = request['params'][-1]
            number = {v.PARENT_HASH: v.PARENT_NUMBER, v.ANCHOR_HASH: v.ANCHOR_NUMBER}[selector['blockHash']]
            request['params'][-1] = hex(number)
    return operations


def specification():
    return {
        'endpoint': ENDPOINT,
        'authentication': 'x-token from NQC_TRIPORT_API_KEY; never persisted',
        'logical_requests': intake.plan(),
        'wire_requests': wire_plan(),
        'selection': 'Explicit fixed block numbers; no EIP-1898 attempt or automatic fallback',
        'binding': 'Original header hashes, parent state root, account/storage proofs and code hashes remain mandatory',
        'canonicality': 'No requireCanonical assertion on the wire; independent canonicality remains unproved',
        'maximum_requests': 8,
        'gates': v.closed_gates(),
    }


class TriportTransport:
    def __init__(self, key):
        v.require(isinstance(key, str) and re.fullmatch(r'[A-Za-z0-9_-]{16,256}', key),
                  'Missing or malformed operator key')
        self.key = key
        self.opener = urllib.request.build_opener(intake.NoRedirect())

    def __call__(self, operation):
        v.require(operation in intake.plan(), 'Unapproved logical operation')
        request = wire_plan()[operation['request']['id'] - 1]['request']
        req = urllib.request.Request(ENDPOINT, data=json.dumps(request).encode(),
            headers={'Content-Type': 'application/json', 'x-token': self.key})
        try:
            with self.opener.open(req, timeout=30) as response:
                raw = response.read(MAX_RESPONSE + 1)
        except urllib.error.HTTPError as exc:
            raise v.ValidationError('HTTP ' + str(exc.code) + '; no retry') from None
        except (urllib.error.URLError, TimeoutError):
            raise v.ValidationError('Transport unavailable; no retry') from None
        v.require(len(raw) <= MAX_RESPONSE, 'Response byte limit')
        parsed = json.loads(raw, object_pairs_hook=v.no_duplicate_keys)
        intake.envelope(parsed, request['id'])
        return parsed


def collect(key, out):
    transport = TriportTransport(key)
    # execute validates each response before proceeding, preserving NQC037's
    # root bindings and closed gates. REQUESTS.json is its logical request plan.
    report = intake.execute(transport, out)
    intake.save(out / 'TRANSPORT.json', specification())
    intake.save(out / 'WIRE_REQUESTS.json', wire_plan())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['plan', 'collect'])
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'plan':
        v.require(not args.out.exists(), 'Fresh output file required')
        args.out.parent.mkdir(parents=True, exist_ok=True)
        intake.save(args.out, specification())
        print('OFFLINE_PLAN_ONLY: 8 fixed read requests')
        return
    key = os.environ.get('NQC_TRIPORT_API_KEY', '')
    v.require(key, 'NQC_TRIPORT_API_KEY is not configured')
    report = collect(key, args.out)
    print(json.dumps({'status': report['status'], 'commercial_admission': False}))
    if report['status'] == 'BLOCKED_OR_REJECTED':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
