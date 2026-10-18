"""Three read-only identity diagnostics after a null historical-hash response.

Latest is observed solely to classify the provider's reported height; it NEVER
replaces the pinned historical state. No quote, trading, replay or profitability.
"""
from __future__ import annotations
import sys
from pathlib import Path
import read_fluid as r


def assess(latest, parent, receipt):
    result = {'diagnostic_only': True, 'historical_state_substituted': False,
              'saved_parent_number': r.NUMBER, 'saved_parent_hash': r.PARENT,
              'saved_target_hash': r.BLOCK, 'saved_transaction': r.TX1,
              'receipt_identity_matches': None, 'parent_identity_matches': None,
              'commercial_admission': False, 'new_nqc_profit_proven': False}
    if isinstance(latest, dict):
        result['provider_latest_number'] = r.uint(latest['number'])
        result['provider_latest_timestamp'] = r.uint(latest['timestamp'])
        result['provider_latest_hash'] = latest['hash']
    if isinstance(parent, dict):
        if r.uint(parent['number']) != r.NUMBER:
            raise r.StopRead('Provider returned wrong number for exact-number diagnostic')
        result['provider_parent_hash'] = parent['hash']
        result['provider_parent_timestamp'] = r.uint(parent['timestamp'])
        result['parent_identity_matches'] = parent['hash'].lower() == r.PARENT
    if isinstance(receipt, dict):
        if receipt.get('transactionHash', '').lower() != r.TX1:
            raise r.StopRead('Provider returned wrong transaction receipt')
        result['provider_receipt_block_hash'] = receipt.get('blockHash')
        result['provider_receipt_block_number'] = r.uint(receipt['blockNumber'])
        result['provider_receipt_index'] = r.uint(receipt['transactionIndex'])
        result['receipt_identity_matches'] = (receipt.get('blockHash', '').lower() == r.BLOCK
            and r.uint(receipt['blockNumber']) == r.NUMBER + 1
            and r.uint(receipt['transactionIndex']) == 1)
    if result['parent_identity_matches'] is False or result['receipt_identity_matches'] is False:
        result['status'] = 'CONFLICT_WITH_SAVED_IDENTIFIERS_SINGLE_PROVIDER'
    elif result['parent_identity_matches'] and result['receipt_identity_matches']:
        result['status'] = 'IDENTITIES_MATCH_VIA_NUMBER_AND_RECEIPT_NO_QUOTE'
    elif result.get('provider_latest_number', r.NUMBER) < r.NUMBER:
        result['status'] = 'PROVIDER_REPORTED_HEAD_BELOW_REQUESTED_HISTORY'
    else:
        result['status'] = 'HISTORICAL_IDENTITY_STILL_UNAVAILABLE_OR_PARTIAL'
    return result


def execute(client):
    values = []
    result = {'status': 'NOT_RUN', 'public_transactions': 0, 'signatures': 0,
              'endpoint': r.URL, 'new_nqc_profit_proven': False,
              'commercial_admission': False, 'historical_quote': None,
              'nqc_replay': False, 'original_replay': False,
              'scope': 'THREE_IDENTITY_READS_NOT_HISTORICAL_STATE_SUBSTITUTION'}
    queries = [('diagnostic_latest', 'eth_getBlockByNumber', ['latest', False]),
               ('parent_by_number', 'eth_getBlockByNumber', [hex(r.NUMBER), False]),
               ('receipt_b', 'eth_getTransactionReceipt', [r.TX1])]
    try:
        for label, method, params in queries:
            response = client.call(label, method, params)
            if 'error' in response:
                raise r.StopRead('Diagnostic RPC error; no retry: ' + str(response['error']))
            values.append(response.get('result'))
        result.update(assess(*values))
    except (r.StopRead, KeyError, TypeError) as exc:
        result['status'] = 'DIAGNOSTIC_BLOCKED_OR_INVALID'; result['error'] = str(exc)
    result['reads_attempted'] = len(client.index)
    return result


if __name__ == '__main__':
    if len(sys.argv) != 2: raise SystemExit('Output directory required')
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=False)
    client = r.Client(out); result = execute(client); r.export(out, result, client)
    # Diagnostic execution success is NOT historical identity validation or profit.
    raise SystemExit(2 if result['status'] == 'DIAGNOSTIC_BLOCKED_OR_INVALID' else 0)
