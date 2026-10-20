"""Finite global Morpho indexer discovery. No trades, quotes, keys or RPC.

Reuses the exact NQC067 immutable-write and hashing utilities. Risk filtering
is requested server-side; returned IDs alone do not verify health or profit.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
LEGACY = HERE.parent / 'nqc-067-shadow-blue-public-indexer' / 'shadow.py'
LEGACY_SHA = 'dfb67d4783fa29a92d4da013d51d48ee80b7cc8e'
raw = LEGACY.read_bytes()
if hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() != LEGACY_SHA:
    raise RuntimeError('NQC067 dependency does not match its pinned Git blob')
spec = importlib.util.spec_from_file_location('nqc067_pinned', LEGACY)
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
QUERY = (HERE / 'QUERY.graphql').read_text(encoding='utf-8')
if hashlib.sha256(QUERY.encode()).hexdigest() != '15b755ddae09e69b27c89aaf64f301e941589473131849645a8f41589ea08b23':
    raise RuntimeError('GraphQL query does not match approved read-only scope')
API = 'https://api.morpho.org/graphql'
MAX_BODY = 2_000_000
HOLD = HERE / 'ACCESS_HOLD.json'
HEX32 = re.compile(r'0x[0-9a-fA-F]{64}\Z')
HEX20 = re.compile(r'0x[0-9a-fA-F]{40}\Z')


class BatchError(ValueError):
    pass


def check_integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise BatchError(label)
    return value


def request_body(skip=0, first=1000):
    check_integer(skip, 0, 10_000, 'invalid skip')
    check_integer(first, 1, 1000, 'invalid page size')
    return legacy.canonical_json({'query': QUERY, 'variables': {
        'chainIds': [1], 'hfLte': 1.02, 'first': first, 'skip': skip}})


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise BatchError('duplicate JSON key')
        obj[key] = value
    return obj


def decode_page(body, first):
    if type(body) is not bytes or len(body) > MAX_BODY:
        raise BatchError('response byte cap or type')
    doc = json.loads(body, object_pairs_hook=unique_object,
                     parse_constant=lambda value: (_ for _ in ()).throw(BatchError(value)))
    if not isinstance(doc, dict) or doc.get('errors'):
        raise BatchError('GraphQL error or invalid envelope')
    data = doc.get('data')
    if not isinstance(data, dict):
        raise BatchError('missing data object')
    page = data.get('marketPositions')
    if not isinstance(page, dict) or not isinstance(page.get('items'), list):
        raise BatchError('missing items')
    items, info = page['items'], page.get('pageInfo')
    if len(items) > first:
        raise BatchError('server exceeded requested page size')
    if not isinstance(info, dict):
        raise BatchError('missing pageInfo')
    count = check_integer(info.get('count'), 0, first, 'invalid count')
    if count != len(items):
        raise BatchError('count does not match items')
    total = info.get('countTotal')
    if total is not None:
        check_integer(total, 0, 10**12, 'invalid countTotal')
    return items, total


def identity(row):
    if not isinstance(row, dict):
        raise BatchError('invalid row')
    market, user = row.get('market'), row.get('user')
    if not isinstance(market, dict) or not isinstance(user, dict):
        raise BatchError('missing identity')
    mid, address = market.get('marketId'), user.get('address')
    if not isinstance(mid, str) or not HEX32.fullmatch(mid):
        raise BatchError('invalid market ID')
    if not isinstance(address, str) or not HEX20.fullmatch(address):
        raise BatchError('invalid borrower')
    return mid.lower(), address.lower()


def collect(fetch_page, *, first=1000, max_pages=10, evidence_kind='OFFLINE_TEST'):
    """Process a bounded global result set, never one query per market."""
    check_integer(first, 1, 1000, 'invalid first')
    check_integer(max_pages, 1, 10, 'invalid max_pages')
    rows, seen, digests, totals = [], set(), set(), []
    raw_rows = duplicates = malformed = attempted = received = skip = 0
    reason, error, exhausted = 'PAGE_CAP', None, False
    for _ in range(max_pages):
        attempted += 1
        try:
            body = fetch_page(skip, first)
            items, total = decode_page(body, first)
            digest = legacy.sha256(body)
            if digest in digests:
                raise BatchError('repeated page; pagination did not advance')
            digests.add(digest)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            reason, error = 'READ_OR_SCHEMA_FAILURE', str(exc)
            break
        received += 1
        totals.append(total)
        raw_rows += len(items)
        for index, item in enumerate(items):
            try:
                key = identity(item)
            except BatchError:
                malformed += 1
                continue
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            rows.append({'chain_id_requested': 1, 'market_id': key[0],
                         'borrower': key[1], 'source_offset': skip + index,
                         'onchain_eligible': None, 'net_profit': None})
        skip += len(items)
        if total is not None and skip > total:
            reason = 'COUNT_TOTAL_INCONSISTENT'
            break
        if total is not None and skip == total:
            reason, exhausted = 'REPORTED_TOTAL_REACHED', True
            break
        if len(items) < first:
            if total is not None:
                reason = 'SHORT_PAGE_BEFORE_REPORTED_TOTAL'
            else:
                reason, exhausted = 'PARTIAL_PAGE_WITHOUT_TOTAL', True
            break
    changing = len(set(totals)) > 1
    groups = {}
    for row in rows:
        groups.setdefault(row['market_id'], []).append(row['borrower'])
    return {
        'schema': 'nqc-global-listed-risk-discovery-v1',
        'evidence_kind': evidence_kind, 'endpoint': API,
        'scope': {'chain_id': 1, 'listed_only': True,
                  'health_factor_lte_requested': '1.02', 'manual_market_list': False},
        'pages_attempted': attempted, 'pages_validated': received,
        'raw_rows': raw_rows, 'unique_pairs': len(rows),
        'duplicate_pairs': duplicates, 'malformed_rows': malformed,
        'markets_with_returned_candidates': len(groups),
        'total_markets_on_ethereum': None,
        'source_totals': totals, 'source_total_changed': changing,
        'reported_pagination_exhausted': exhausted,
        'enumeration_without_detected_anomaly': bool(exhausted and not changing
                                                     and not duplicates and not malformed),
        'point_in_time_complete': False,
        'coverage_caveat': 'Live offset pagination can omit rows even with stable totals; '
                           'listed and HF-filtered scope is not all Ethereum markets.',
        'stop_reason': reason, 'error': error,
        'candidates': rows, 'market_groups': groups,
        'economic_stage': 'NEEDS_STATE_SALE_PRICE_COSTS_AND_FINANCING',
        'nqc_realized_profit': None, 'commercial_admission': False,
        'canary_enabled': False, 'rpc_requests': 0,
    }


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BatchError('redirect not allowed')


def live_fetcher(out):
    """A per-checkout hold prevents retry after denial, failure or ambiguity."""
    if HOLD.exists():
        raise BatchError('MANUAL_REVIEW_REQUIRED; no network request made')
    out.mkdir(parents=True, exist_ok=False)
    # Exclusive hold is acquired before any request. Never automatically cleared.
    legacy.save_new(HOLD, legacy.canonical_json({'reason': 'RUN_CLAIMED_REVIEW_BEFORE_NEXT_RUN'}))
    opener, state = urllib.request.build_opener(NoRedirect()), {'count': 0, 'last': 0.0}

    def fetch(skip, first):
        if state['count'] >= 10:
            raise BatchError('request budget exhausted')
        time.sleep(max(0.0, 2.0 - (time.monotonic() - state['last'])))
        number = state['count']
        state['count'] += 1
        state['last'] = time.monotonic()
        body = request_body(skip, first)
        stem = out / f'page-{number:03d}'
        legacy.save_new(stem.with_suffix('.request.json'), body)
        meta = {'started_utc': legacy.iso8601(legacy.utc_now()), 'skip': skip,
                'first': first, 'status': None, 'retries': 0}
        try:
            req = urllib.request.Request(API, data=body, method='POST', headers={
                'Content-Type': 'application/json', 'Accept': 'application/json',
                'User-Agent': 'NQC-ReadOnly-Batch/1.0'})
            with opener.open(req, timeout=12) as response:
                meta['status'] = response.status
                if response.status != 200:
                    raise BatchError('unexpected HTTP status')
                body = response.read(MAX_BODY + 1)
            if len(body) > MAX_BODY:
                raise BatchError('response byte cap exceeded')
            legacy.save_new(stem.with_suffix('.response.json'), body)
            meta.update(response_bytes=len(body), sha256=legacy.sha256(body))
            return body
        except Exception as exc:
            meta.update(error_type=type(exc).__name__, error=str(exc))
            raise BatchError(f'public source read failed: {exc}') from exc
        finally:
            meta['finished_utc'] = legacy.iso8601(legacy.utc_now())
            legacy.save_new(stem.with_suffix('.meta.json'), legacy.canonical_json(meta))
    return fetch


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--plan', action='store_true')
    modes.add_argument('--offline-pages', type=Path)
    modes.add_argument('--fetch-approved-once', action='store_true')
    parser.add_argument('--page-size', type=int, default=1000)
    parser.add_argument('--max-pages', type=int, default=10)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    try:
        check_integer(args.page_size, 1, 1000, 'page size')
        check_integer(args.max_pages, 1, 10, 'max pages')
        if args.plan:
            print(request_body(first=args.page_size).decode(), end='')
            return 0
        if not args.out:
            raise BatchError('--out required')
        if args.fetch_approved_once:
            fetch = live_fetcher(args.out)
            kind = 'PUBLIC_INDEXER_OBSERVATION'
        else:
            args.out.mkdir(parents=True, exist_ok=False)
            counter = iter(sorted(args.offline_pages.glob('page-*.response.json')))
            def fetch(skip, first):
                try:
                    return next(counter).read_bytes()
                except StopIteration as exc:
                    raise BatchError('missing next archived page') from exc
            kind = 'OFFLINE_IMPORT_NOT_CURRENT_MARKET_DATA'
        result = collect(fetch, first=args.page_size, max_pages=args.max_pages,
                         evidence_kind=kind)
        legacy.save_new(args.out / 'RESULTS.json', legacy.canonical_json(result))
        print(json.dumps({k: v for k, v in result.items()
                          if k not in ('candidates', 'market_groups')}, indent=2))
        return 0 if result['enumeration_without_detected_anomaly'] else 2
    except (OSError, ValueError) as exc:
        print('NQC BATCH CLOSED: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
