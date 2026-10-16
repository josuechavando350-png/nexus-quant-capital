#!/usr/bin/env python3
"""Decimal-only sensitivity model. Parameters are assumptions, never forecasts.

USDG is the unit of account, not a promise of dollar parity. The captured route
already includes its DEX fee, transfer tax and observed price impact. A haircut
is additional deterioration. Sponsor reimbursement and native network fees are
alternative accounting boundaries, not additive fees.
"""
from decimal import Decimal, ROUND_FLOOR

D = Decimal


def decimal(value):
    if isinstance(value, (float, bool)):
        raise ValueError('use explicit decimal strings or integers')
    value = D(value)
    if not value.is_finite():
        raise ValueError('finite value required')
    return value


def evaluate(gross_usdg, success_fee_wei, failure_fee_wei, *, eth_usdg,
             capture_probability, surplus_haircut_bps, provider_markup_bps,
             rpc_per_attempt_usdg, fixed_period_usdg, deployment_period_usdg,
             capital_period_usdg, attempts, revenue_share_bps=10000):
    gross, price, p = map(decimal, (gross_usdg, eth_usdg, capture_probability))
    haircut, markup, share = map(decimal, (surplus_haircut_bps, provider_markup_bps, revenue_share_bps))
    overheads = list(map(decimal, (rpc_per_attempt_usdg, fixed_period_usdg,
                                   deployment_period_usdg, capital_period_usdg)))
    if (type(attempts) is not int or attempts <= 0 or price <= 0 or gross < 0 or
            not 0 <= p <= 1 or not 0 <= haircut <= 10000 or markup < 0 or
            not 0 <= share <= 10000 or any(x < 0 for x in overheads) or
            any(type(x) is not int or x < 0 for x in (success_fee_wei, failure_fee_wei))):
        raise ValueError('invalid economic assumptions')
    revenue = gross * (1 - haircut / 10000) * share / 10000
    factor = price / D(10**18) * (1 + markup / 10000)
    cs, cf = success_fee_wei * factor, failure_fee_wei * factor
    overhead = overheads[0] + sum(overheads[1:]) / attempts
    denominator = revenue - cs + cf
    threshold = (cf + overhead) / denominator if denominator > 0 else None
    ev = p * (revenue - cs) - (1 - p) * cf - overhead
    # A negative all-success result cannot be made profitable by raising capture.
    possible = revenue - cs - overhead > 0
    needed = None
    if denominator > 0:
        # Strictly positive period profit, including exact-integer break-even.
        needed = int((attempts * (cf + overhead) / denominator).to_integral_value(rounding=ROUND_FLOOR)) + 1
    return dict(revenue_per_success_usdg=revenue, success_fee_usdg=cs,
                failure_fee_usdg=cf, overhead_per_attempt_usdg=overhead,
                success_contribution_usdg=revenue - cs - overhead,
                capture_probability_assumed=p, break_even_probability=threshold,
                possible_at_100_percent_capture=possible,
                successes_for_strictly_positive_period=needed,
                expected_per_attempt_usdg=ev, expected_period_usdg=ev * attempts,
                capture_rate_measured=False, realized_revenue=False)


def stringify(value):
    if isinstance(value, D):
        return format(value, 'f')
    if isinstance(value, dict):
        return {k: stringify(v) for k, v in value.items()}
    if isinstance(value, list):
        return [stringify(x) for x in value]
    return value


def required_prefund(gas_limits, max_fee_wei):
    names = {'verification', 'call', 'paymaster_verification', 'paymaster_postop', 'pre_verification'}
    if set(gas_limits) != names or any(type(x) is not int or not 0 <= x < 2**120
                                     for x in [*gas_limits.values(), max_fee_wei]):
        raise ValueError('invalid v0.7 gas fields')
    return sum(gas_limits.values()) * max_fee_wei
