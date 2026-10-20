"""NQC067 -- finite, read-only, non-trading Morpho Blue public-indexer Shadow sampler.

One optional public POST per *explicit* --fetch invocation. No RPC, signing, keys,
orders, simulations, execution, retries, paid endpoints, or background service.
A hash and observed_at are provenance of the INDEXER RESPONSE, never consensus.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation

API_URL = 'https://api.morpho.org/graphql'
CHAIN_ID = 1
WAD = 10**18
REQUIRED_SECONDS_BETWEEN_FETCHES = 3600
MAX_BYTES = 512_000
EVENT_LIMIT = 20
POSITION_LIMIT = 25
MARKET_RE = re.compile(r'0x[0-9a-fA-F]{64}\Z')
ADDRESS_RE = re.compile(r'0x[0-9a-fA-F]{40}\Z')
TX_RE = re.compile(r'0x[0-9a-fA-F]{64}\Z')
UINT_RE = re.compile(r'(0|[1-9][0-9]*)\Z')


class ShadowBoundaryError(ValueError):
    pass


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso8601(t: dt.datetime) -> str:
    if t.tzinfo is None or t.utcoffset() is None:
        raise ShadowBoundaryError('timestamp must be UTC-aware')
    return t.astimezone(dt.timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def canonical_json(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False) + '\n').encode('utf-8')


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def check_markets(markets: list[str]) -> list[str]:
    if not 1 <= len(markets) <= 3:
        raise ShadowBoundaryError('Exactly 1 to 3 explicit Ethereum markets required')
    result = []
    for market in markets:
        if not isinstance(market, str) or not MARKET_RE.fullmatch(market):
            raise ShadowBoundaryError('market identifier must be 32-byte hex')
        if market.lower() not in result:
            result.append(market.lower())
    return sorted(result)


def build_query(markets: list[str]) -> str:
    items = ' '.join('"' + m + '"' for m in check_markets(markets))
    # Both selections derive from official Morpho Blue GraphQL examples.
    return '''query NQCShadow067 {
      marketPositions(first: 25, orderBy: BorrowShares, orderDirection: Desc,
        where: {marketUniqueKey_in: [%s]}) {
        items {
          market { marketId lltv loanAsset { address decimals } collateralAsset { address decimals } }
          user { address }
          state { borrowAssets collateral borrowAssetsUsd collateralUsd }
        }
      }
      marketTransactions(first: 20, orderBy: Timestamp, orderDirection: Desc,
        where: {marketUniqueKey_in: [%s], type_in: [Liquidation]}) {
        items {
          blockNumber txHash timestamp logIndex type
          market { marketId }
          user { address }
          data { ... on MarketTransactionLiquidationData {
            seizedAssets repaidAssets badDebtAssets liquidator
          } }
        }
      }
    }''' % (items, items)


def decimal_str(value, label: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value,float) or not isinstance(value, (str, int, Decimal)):
        raise ShadowBoundaryError(f'{label} must be fixed-decimal or integer-valued')
    s = format(value, 'f') if isinstance(value, Decimal) else str(value)
    if 'e' in s.lower():
        raise ShadowBoundaryError(f'{label} must be fixed decimal')
    try:
        d = Decimal(s)
    except InvalidOperation as e:
        raise ShadowBoundaryError(f'{label} invalid') from e
    if not d.is_finite() or d < 0:
        raise ShadowBoundaryError(f'{label} must be finite nonnegative')
    return d


def uint(value, label: str) -> int:
    if not isinstance(value, str) or not UINT_RE.fullmatch(value):
        raise ShadowBoundaryError(f'{label}: expected base-10 integer string')
    return int(value)


def assess_indexed_position(record: dict, markets: set[str]) -> dict:
    market = record['market']
    market_id = market['marketId'].lower()
    user = record['user']['address'].lower()
    if market_id not in markets or not MARKET_RE.fullmatch(market_id):
        raise ShadowBoundaryError('market ID is not in watchlist')
    if not ADDRESS_RE.fullmatch(user):
        raise ShadowBoundaryError('invalid borrower address')
    state = record['state']
    borrow_raw = uint(state['borrowAssets'], 'borrowAssets')
    collateral_raw = uint(state['collateral'], 'collateral')
    lltv_wad = uint(str(market['lltv']), 'lltv')
    if lltv_wad > WAD:
        raise ShadowBoundaryError('LLTV > 1e18')
    debt_usd = state.get('borrowAssetsUsd')
    collateral_usd = state.get('collateralUsd')
    hf = None
    evidence_status = 'INDEXER_AMOUNTS_ONLY'
    if debt_usd is not None and collateral_usd is not None and borrow_raw > 0:
        debt = decimal_str(debt_usd, 'borrowAssetsUsd')
        collateral = decimal_str(collateral_usd, 'collateralUsd')
        if debt > 0:
            # Approximate THIRD-PARTY MARK-TO-MARKET ONLY. No live oracles, no EVM proof.
            health = collateral * Decimal(lltv_wad) / Decimal(WAD) / debt
            hf = str(health.quantize(Decimal('0.000001')))
            evidence_status = ('INDEXER_ESTIMATE_NEAR_OR_BELOW_1_NOT_CANONICAL'
                               if health <= Decimal('1.02')
                               else 'INDEXER_ESTIMATE_ABOVE_1')
    return {
        'chain_id': CHAIN_ID,
        'market_id': market_id,
        'borrower': user,
        'borrow_assets_raw': str(borrow_raw),
        'collateral_assets_raw': str(collateral_raw),
        'lltv_wad': str(lltv_wad),
        'indexed_estimated_health_factor': hf,
        'screen_status': evidence_status,
        'profitability': None,
        'competitive_capture_probability': None,
        'can_liquidate_onchain': None,
    }


def assess_indexed_liquidation(record: dict, markets: set[str]) -> dict:
    if record.get('type') != 'Liquidation':
        raise ShadowBoundaryError('not a liquidation event')
    m = record['market']['marketId'].lower()
    h = record['txHash'].lower()
    if m not in markets or not MARKET_RE.fullmatch(m) or not TX_RE.fullmatch(h):
        raise ShadowBoundaryError('unrecognized event identity')
    idx = record['logIndex']
    if isinstance(idx, bool) or isinstance(idx, float) or not str(idx).isdigit():
        raise ShadowBoundaryError('invalid log index')
    block = record['blockNumber']
    if isinstance(block, bool) or isinstance(block, float) or not str(block).isdigit():
        raise ShadowBoundaryError('invalid block')
    timestamp = record.get('timestamp')
    if timestamp is not None and (isinstance(timestamp, bool) or isinstance(timestamp, float) or not str(timestamp).isdigit()):
        raise ShadowBoundaryError('invalid timestamp')
    data = record['data']
    seized = uint(str(data['seizedAssets']), 'seizedAssets')
    repaid = uint(str(data['repaidAssets']), 'repaidAssets')
    bad = uint(str(data['badDebtAssets']), 'badDebtAssets')
    liquidator = data['liquidator'].lower()
    if not ADDRESS_RE.fullmatch(liquidator):
        raise ShadowBoundaryError('invalid liquidator')
    return {
        'event_id': f'1:{m}:{h}:{int(idx)}',
        'market_id': m,
        'block_reported_by_indexer': str(block),
        'tx_hash': h,
        'log_index': int(idx),
        'timestamp_reported_by_indexer': str(timestamp) if timestamp is not None else None,
        'liquidator': liquidator,
        'seized_assets_raw': str(seized),
        'repaid_assets_raw': str(repaid),
        'bad_debt_assets_raw': str(bad),
        'canonical_proof': False,
        'event_was_ex_ante_capturable': None,
        'net_NQC_profit': None,
    }


def normalize(payload: dict, markets: list[str], observed_at: str, raw_sha256: str) -> dict:
    if not isinstance(payload, dict) or payload.get('errors'):
        raise ShadowBoundaryError('GraphQL response errors or wrong envelope')
    data = payload.get('data')
    if not isinstance(data, dict):
        raise ShadowBoundaryError('GraphQL data missing')
    if not isinstance(data.get('marketPositions'), dict) or not isinstance(data.get('marketTransactions'), dict):
        raise ShadowBoundaryError('Both collections must be present (no partial success)')
    positions = data['marketPositions'].get('items')
    liquidations = data['marketTransactions'].get('items')
    if not isinstance(positions, list) or not isinstance(liquidations, list):
        raise ShadowBoundaryError('Items must be arrays')
    if len(positions) > POSITION_LIMIT or len(liquidations) > EVENT_LIMIT:
        raise ShadowBoundaryError('Exceeded requested page limits')
    watch = set(check_markets(markets))
    seen_pos = set()
    rows_pos = []
    for p in positions:
        item = assess_indexed_position(p, watch)
        key=(item['market_id'],item['borrower'])
        if key in seen_pos:
            raise ShadowBoundaryError('Duplicate borrower in same market page')
        seen_pos.add(key)
        rows_pos.append(item)
    seen_events = set()
    rows_ev = []
    for e in liquidations:
        item = assess_indexed_liquidation(e, watch)
        if item['event_id'] in seen_events:
            raise ShadowBoundaryError('Duplicate event')
        seen_events.add(item['event_id'])
        rows_ev.append(item)
    return {
        'schema': 'nqc067-indexer-shadow-v1',
        'chain_id': CHAIN_ID,
        'observation_time_utc': observed_at,
        'provider': 'Morpho official public GraphQL API, not canonical node',
        'endpoint': API_URL,
        'raw_body_sha256': raw_sha256,
        'watchlisted_markets': sorted(watch),
        'observed_positions_count': len(rows_pos),
        'observed_liquidation_events_count': len(rows_ev),
        'position_page_at_limit': len(rows_pos) == POSITION_LIMIT,
        'liquidation_page_at_limit': len(rows_ev) == EVENT_LIMIT,
        'events': sorted(rows_ev, key=lambda r:r['event_id']),
        'positions': sorted(rows_pos, key=lambda r:(r['market_id'],r['borrower'])),
        'coverage_complete': False,
        'onchain_authenticated': False,
        'actual_NQC_profit': None,
        'candidate_realized_profit': None,
        'commercial_admission': False,
        'canary_enabled': False,
        'wallet_funds': 0,
        'gas_sponsor_accepted': False,
    }


def first_seen_deltas(previous: dict | None, current: dict) -> dict:
    if previous is None:
        return {
            'snapshot_kind': 'BASELINE_ONLY',
            'new_indexer_event_ids': [],
            'newly_seen_near_threshold_positions': [],
            'can_infer_ex_ante_capture': False,
            'reason': 'First snapshot cannot establish new events or ex-ante position availability.'
        }
    if previous.get('watchlisted_markets') != current.get('watchlisted_markets'):
        raise ShadowBoundaryError('Different watchlists cannot be differenced')
    old_events={x['event_id'] for x in previous['events']}
    old_near={(x['market_id'],x['borrower']) for x in previous['positions']
              if x['screen_status']=='INDEXER_ESTIMATE_NEAR_OR_BELOW_1_NOT_CANONICAL'}
    return {
        'snapshot_kind': 'AFTER_BASELINE',
        'new_indexer_event_ids': sorted(x['event_id'] for x in current['events'] if x['event_id'] not in old_events),
        'newly_seen_near_threshold_positions': [
            {'market_id':x['market_id'],'borrower':x['borrower']}
            for x in current['positions']
            if x['screen_status']=='INDEXER_ESTIMATE_NEAR_OR_BELOW_1_NOT_CANONICAL'
            and (x['market_id'],x['borrower']) not in old_near
        ],
        'can_infer_ex_ante_capture': False,
        'reason': 'Indexed first-seen does not prove event creation time, market eligibility or opportunity capture.'
    }


def save_new(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd=os.open(path, os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        try:path.unlink()
        except FileNotFoundError:pass
        raise


def last_snapshot(directory: Path) -> dict | None:
    files=sorted(x for x in directory.glob('observation_*.json') if not x.name.endswith('.raw.json'))
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding='utf-8'))


def ingest_body(body: bytes, markets: list[str], directory: Path, observation_time: dt.datetime):
    if len(body)>MAX_BYTES:
        raise ShadowBoundaryError('Body too large')
    payload=json.loads(body.decode('utf-8'), parse_float=Decimal)
    iso=iso8601(observation_time)
    normalized=normalize(payload,markets,iso,sha256(body))
    previous=last_snapshot(directory)
    diff=first_seen_deltas(previous,normalized)
    normalized['delta_from_previous']=diff
    stamp=observation_time.strftime('%Y%m%dT%H%M%S.%fZ')
    # At most one snapshot per exact timestamp with O_EXCL; raw response retained byte for byte.
    stem='observation_'+stamp+'_'+sha256(body)[:12]
    save_new(directory/(stem+'.raw.json'),body)
    save_new(directory/(stem+'.json'),canonical_json(normalized))
    return normalized


def fetch_public_once(query: str, timeout: int=10) -> bytes:
    request=urllib.request.Request(API_URL,data=canonical_json({'query':query}),
        method='POST',headers={'Content-Type':'application/json','Accept':'application/json',
                                'User-Agent':'NQC067-Shadow-ReadOnly/0.1'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise ShadowBoundaryError('Provider HTTP status '+str(response.status))
            raw=response.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:
                raise ShadowBoundaryError('Provider response exceeds cap')
            return raw
    except urllib.error.HTTPError as e:
        # No retries on 403, 429, 5xx, or any other response.
        raise ShadowBoundaryError(f'Provider returned HTTP {e.code}; no retry or alternative route') from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ShadowBoundaryError('Public API network unavailable; no retry: '+str(e)) from e


def run_cli(argv: list[str] | None=None) -> int:
    parser=argparse.ArgumentParser(description='NQC067 finite one-shot Morpho Blue indexer Shadow')
    parser.add_argument('--market-id',action='append',required=True,help='1 to 3 known chain 1 market IDs')
    parser.add_argument('--out',type=Path,default=Path('shadow_snapshots'))
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--print-query',action='store_true')
    group.add_argument('--ingest-file',type=Path,help='OFFLINE archived official GraphQL JSON')
    group.add_argument('--fetch-public-once',action='store_true',help='One direct public POST, no retry')
    parser.add_argument('--explicit-read-approval',action='store_true',help='Required for public read')
    args=parser.parse_args(argv)
    try:
        markets=check_markets(args.market_id)
        query=build_query(markets)
        if args.print_query:
            print(query)
            return 0
        if args.fetch_public_once:
            if (args.out/'MANUAL_REVIEW_REQUIRED').exists():
                raise ShadowBoundaryError('Previous provider failure; manual review required before another attempt')
            if not args.explicit_read_approval:
                raise ShadowBoundaryError('explicit-read-approval required for network activity')
            # Per-path local throttle, NOT a globally safe distributed request counter.
            guard=args.out/'last_attempt.txt'
            if guard.exists():
                previous=dt.datetime.fromisoformat(guard.read_text().strip().replace('Z','+00:00'))
                if (utc_now()-previous).total_seconds()<REQUIRED_SECONDS_BETWEEN_FETCHES:
                    raise ShadowBoundaryError('Local 1-hour cooldown; no request sent')
            # O_EXCL sentinel: no automatic re-attempt on crash or ambiguity; manual audit required.
            save_new(args.out/('attempt_'+utc_now().strftime('%Y%m%dT%H%M%S%fZ')+'.lock'),b'attempted\n')
            save_new(guard,iso8601(utc_now()).encode('ascii')) if not guard.exists() else guard.write_text(iso8601(utc_now()))
            try:
                body=fetch_public_once(query)
            except ShadowBoundaryError as exc:
                # Fail closed. No automatic retry, no fallback provider or proxy.
                save_new(args.out/'MANUAL_REVIEW_REQUIRED', str(exc).encode('utf-8'))
                raise
        else:
            body=args.ingest_file.read_bytes()
        result=ingest_body(body,markets,args.out,utc_now())
        print(json.dumps({'observation_time_utc':result['observation_time_utc'],
            'positions':result['observed_positions_count'],
            'liquidations':result['observed_liquidation_events_count'],
            'delta':result['delta_from_previous'],
            'realized_NQC_profit':None, 'commercial_admission':False},ensure_ascii=False,indent=2))
        return 0
    except (OSError,ShadowBoundaryError,ValueError,KeyError,TypeError,json.JSONDecodeError) as e:
        print('NQC067 CLOSED: '+str(e),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(run_cli())
