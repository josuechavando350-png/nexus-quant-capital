"""NQC059 bounded arithmetic for a *reported* Aave liquidation payout.

No blockchain calls, wallets, keys, floats, or implied token conversions.
It cannot authenticate transaction receipts, participant ownership, or returns.
"""
from decimal import Decimal, localcontext
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ZERO = Decimal('0')


def decimal_amount(value: str) -> Decimal:
    if not isinstance(value, str) or not value or 'e' in value.lower():
        raise ValueError('Explicit fixed-point string required')
    d = Decimal(value)
    if not d.is_finite() or d < ZERO:
        raise ValueError('Positive finite monetary amount required')
    return d


def money_as_str(value: Decimal) -> str:
    return format(value, 'f')


def payout_allocation(case: dict) -> dict:
    """Same-asset payout math only; distributions are SOURCE-REPORTED, not canonical."""
    if case.get('denomination') != 'WETH':
        raise ValueError('Only source-recorded homogeneous WETH supported')
    bid = decimal_amount(case['coinbase_payout_WETH'])
    other = decimal_amount(case['second_address_payout_WETH'])
    total = bid + other
    if total <= ZERO:
        raise ValueError('Cannot compute meaningful share of zero payouts')
    return {
        'coinbase_WETH': money_as_str(bid),
        'second_address_WETH': money_as_str(other),
        'observed_source_reported_payout_total_WETH': money_as_str(total),
        'coinbase_share_of_payouts_pct': money_as_str(bid / total * 100),
        'other_share_of_payouts_pct': money_as_str(other / total * 100),
        'coinbase_is_builder_proven': False,
        'source_reported_executor_retained_WETH': case['source_reported_executor_retained_WETH'],
        'independent_onchain_authentication': False,
    }


def decimal_display_interval(value: str, places: int, interpretation: str):
    """[low, high) interval if printed value was rounded or truncated.

    WETH denomination is kept as WETH; there is no implicit ETH conversion.
    """
    d = decimal_amount(value)
    if places < 0 or places > 18 or int(places) != places:
        raise ValueError('Invalid decimal places')
    quantum = Decimal(1).scaleb(-places)
    if d.as_tuple().exponent != -places:
        raise ValueError('Precision does not match displayed places')
    if interpretation == 'nearest':
        return d - quantum / 2, d + quantum / 2
    if interpretation == 'truncated':
        return d, d + quantum
    raise ValueError('Unsupported display interpretation')


def bounded_residual(case: dict, interpretation: str) -> dict:
    allocation = payout_allocation(case)
    source_ex = case['post_exit_display_WETH']
    places = int(case['post_exit_display_places'])
    low, high = decimal_display_interval(source_ex, places, interpretation)
    payout = Decimal(allocation['observed_source_reported_payout_total_WETH'])
    # Do not claim an exact residual from the source's rounded withdrawal.
    # A solvent exact same-asset allocation requires exit >= total paid.
    lower = max(ZERO, low - payout)
    upper = high - payout
    return {
        'case_id': case['case_id'],
        'interpretation': interpretation,
        'source_printed_post_exit_WETH': source_ex,
        'post_exit_interval_WETH': [money_as_str(low), money_as_str(high)],
        'post_exit_interval_right_open': True,
        'total_reported_payouts_WETH': money_as_str(payout),
        'solvent_reported_allocation_possible': upper > ZERO,
        'residual_conditional_lower_WETH': money_as_str(lower) if upper > ZERO else None,
        'residual_conditional_upper_exclusive_WETH': money_as_str(upper) if upper > ZERO else None,
        'extra_sponsor_ETH_can_be_inferred': False,
        'profit_realized_by_NQC': None,
        'caveat': 'Requires exact token transfers, no hidden inflow/outflow, payout attribution, fees, and block authenticity; the source figure is rounded.',
    }


def run() -> dict:
    case = json.loads((HERE / 'reported_case.json').read_text(encoding='utf-8'))
    return {
        'case_id': case['case_id'],
        'classification': 'PRACTITIONER_REPORTED_ZERO_RETENTION_NOT_CANONICAL_PROOF',
        'allocation': payout_allocation(case),
        'conditional_rounding_bounds': {
            x: bounded_residual(case, x) for x in ('nearest', 'truncated')
        },
        'gas_price': None,
        'sponsor_terms': None,
        'outcome_for_NQC': 'UNKNOWN',
        'commercial_admission': False,
        'full_replay': 'NOT_ATTEMPTED',
    }


if __name__ == '__main__':
    print(json.dumps(run(), indent=2, sort_keys=True, ensure_ascii=False))
