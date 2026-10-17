"""Deterministic selection, before NEW candidate economics; no network or USD ranking."""
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'morpho-sponsored-gas'
sys.path.insert(0, str(OLD))
import monthly_census as census


def select():
    lock = json.loads((HERE / 'CANDIDATE_SELECTION_LOCK.json').read_text())
    root = OLD / 'evidence/2026-10-17-monthly'
    for name, digest in lock['input_sha256'].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError('frozen input changed: ' + name)
    read = lambda n: json.loads((root / n).read_text())
    rows = census.validate_pages([read(f'page-{i:03}.json') for i in range(3)],
        [read(f'reverse-{i:03}.json') for i in range(2)], read('seven-day.json'), read('selection.json'))
    by_tx = defaultdict(list)
    for row in rows:
        by_tx[row['txHash']].append(row)
    clean = {tx: rr for tx, rr in by_tx.items() if not any(r['badDebtAssets'] or r['badDebtShares'] for r in rr)}
    # Different loan assets cannot be added. Mixed-asset transactions are not ranked.
    single = {tx: rr for tx, rr in clean.items() if len({r['loanAsset']['address'] for r in rr}) == 1}
    counts = Counter(rr[0]['loanAsset']['address'] for rr in single.values())
    weth = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'
    other = sorted((a for a in counts if a != weth), key=lambda a: (-counts[a], a))[0]
    selected = []
    def add(tx, group):
        selected.append({'tx_hash': tx, 'group': group, 'events': by_tx[tx],
            'classification': 'UNRATED_MISSING_WITNESS', 'net_profit': None})
    for asset, group in [(weth, 'WETH_no_reported_bad_debt'), (other, 'largest_principal_same_asset')]:
        candidates = [tx for tx, rr in single.items() if rr[0]['loanAsset']['address'] == asset]
        for tx in sorted(candidates, key=lambda t: (-sum(r['repaidAssets'] for r in single[t]), t))[:4]:
            add(tx, group)
    # One earliest transaction per remaining debt asset, then earliest across those assets.
    first = {}
    for tx, rr in single.items():
        asset = rr[0]['loanAsset']['address']
        if asset in (weth, other):
            continue
        key = (rr[0]['blockNumber'], rr[0]['txIndex'], tx)
        if asset not in first or key < first[asset]:
            first[asset] = key
    for _, _, tx in sorted(first.values())[:4]:
        add(tx, 'other_asset_earliest_diversity')
    assert len({r['tx_hash'] for r in selected}) == len(selected) <= 12
    receipts = census.audit()['diagnostic_receipts']
    for row in selected:
        row['receipt_evidence'] = receipts.get(row['tx_hash'], {'status': 'NOT_REQUESTED'})
        row['funnel'] = {'api_observed': True,
            'receipt_crosschecked': row['receipt_evidence']['status'] == 'RPC_API_EVENT_CROSSCHECK',
            **{k: None for k in ('position_oracle_irm', 'authentic_prestate', 'dex_at_tx_index',
                'original_pnl_complete', 'nqc_counterfactual', 'external_funding', 'sensitivity', 'capture_window')}}
    return {'source': 'existing API census; not chain-complete', 'events': len(rows),
        'transactions': len(by_tx), 'transactions_without_any_reported_bad_debt': len(clean),
        'nominal_ranking_asset': other, 'substitutions': [], 'candidates': selected}


if __name__ == '__main__':
    print(json.dumps(select(), indent=2))
