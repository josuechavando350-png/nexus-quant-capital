"""Conditional four-outcome economics, not a forecast or spending/admission policy.

The funder pays all specified costs. Founder receives the remainder of gross
surplus AFTER debt repayment. A real no-recourse agreement is a separate gate.
All values must be explicit, including zero. Missing costs never default to zero.
"""
from decimal import Decimal, localcontext

OUTCOMES = ('success', 'userop_failure', 'bundle_revert', 'preinclusion_rejection')
FIELDS = {'probability', 'network_fee_wei', 'sponsor_charge_wei', 'external_invoice_wei',
          'offchain_cost_usdg', 'conversion_cost_usdg'}


def decimal(value):
    if not isinstance(value, str):
        raise ValueError('explicit decimal string required; unknown is not zero')
    result = Decimal(value)
    if not result.is_finite() or result < 0:
        raise ValueError('nonnegative finite value required')
    return result


def wei(value):
    result = decimal(value)
    if result != result.to_integral_value():
        raise ValueError('wei must be integral')
    return result


def evaluate(*, boundary, success_surplus_usdg, eth_usdg, funder_share_bps,
             fixed_cost_usdg_per_attempt, outcomes):
    """boundary integrated includes the bundler/beneficiary; external excludes it.

    external_invoice_wei is ADDITIONAL to sponsor charge (e.g. a contracted
    failed-bundle recharge). Integrated case requires zero external invoice.
    Fixed costs include allocated deployment, infra, stake/capital and labor;
    caller must supply allocation even when success probability is zero.
    """
    if boundary not in ('integrated', 'external_bundler') or set(outcomes) != set(OUTCOMES):
        raise ValueError('explicit boundary and all four mutually exclusive outcomes required')
    with localcontext() as ctx:
        ctx.prec = 60
        gross, price, bps, fixed = map(decimal, (success_surplus_usdg, eth_usdg, funder_share_bps,
                                               fixed_cost_usdg_per_attempt))
        if price == 0 or bps > 10000:
            raise ValueError('positive ETH/USDG quote and share <= 10000 bps required')
        share = bps / 10000
        probability = cost = Decimal(0)
        rows = {}
        for name in OUTCOMES:
            source = outcomes[name]
            if set(source) != FIELDS:
                raise ValueError('all costs must be explicit; no unknown/extra fields')
            p = decimal(source['probability'])
            network, charge, invoice = map(wei, (source['network_fee_wei'], source['sponsor_charge_wei'],
                                                source['external_invoice_wei']))
            offchain, conversion = map(decimal, (source['offchain_cost_usdg'], source['conversion_cost_usdg']))
            if p > 1 or (name in ('bundle_revert', 'preinclusion_rejection') and charge != 0):
                raise ValueError('invalid probability or sponsor debit on rejected bundle')
            if name == 'preinclusion_rejection' and network != 0:
                raise ValueError('no submitted transaction in preinclusion outcome')
            if boundary == 'integrated' and invoice != 0:
                raise ValueError('integrated entity cannot invoice itself')
            native = network if boundary == 'integrated' else charge + invoice
            expense = native * price / 10**18 + offchain + conversion
            probability += p
            cost += p * expense
            rows[name] = {'funder_cost_usdg': str(expense), 'probability': str(p)}
        if probability != 1:
            raise ValueError('probabilities must sum exactly to one')
        cost += fixed
        success_p = decimal(outcomes['success']['probability'])
        expected_surplus = success_p * gross
        denominator = success_p * share
        return {'status': 'CONDITIONAL_MODEL_ONLY', 'boundary': boundary,
                'expected_funder_cost_usdg': str(cost),
                'expected_funder_net_usdg': str(expected_surplus * share - cost),
                'expected_founder_distribution_usdg': str(expected_surplus * (1 - share)),
                'success_surplus_break_even_usdg': str(cost / denominator) if denominator else None,
                'break_even_is_equality_not_positive_profit': True, 'outcomes': rows,
                'bootstrap_funding_proven': False, 'commercial_admission_proven': False,
                'probabilities_and_terms_are_inputs_not_estimates': True}
