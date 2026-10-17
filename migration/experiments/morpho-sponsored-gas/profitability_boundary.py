"""Exact output/cost boundaries, not an opportunity finder or sponsorship proof.

Amounts are raw token units. ETH/WETH comparisons below apply only to this
18-decimal, 1:1 unwrap fixture. No floats, network calls, state overrides or trades.
The original pair fee is 3/1000; reserves and all post-swap balances fit uint112.
"""
import argparse
import gzip
import json
import re
from fractions import Fraction
from pathlib import Path

from morpho_liquidation_math import PostAccrualWitness, calculate

WAD = 10**18
MAX_RESERVE = 2**112 - 1
ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / 'fixtures/profitability_boundary.hex'


def positive(value: int) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError('positive integer units required')
    return value


def ceil_div(n: int, d: int) -> int:
    return (n + d - 1) // d


def amount_out(amount: int, x: int, y: int) -> int:
    for value in (amount, x, y):
        positive(value)
    if x + amount > MAX_RESERVE or y > MAX_RESERVE:
        raise ValueError('Uniswap V2 reserve/balance uint112 overflow')
    return 997 * amount * y // (1000 * x + 997 * amount)


def minimum_depth(amount: int, required_out: int, price: Fraction) -> dict:
    """Exact minimum on the fixed-price lattice x=den*k, y=num*k.

    floor(997*s*num*k / (1000*den*k+997*s)) >= T iff
    k*(997*s*num-1000*den*T) >= 997*s*T.
    Increasing arbitrary x with floor(price*x) is NOT necessarily monotone.
    Integer k preserves the exact rational spot price and is monotone.
    """
    positive(amount); positive(required_out)
    if type(price) is not Fraction or price <= 0:
        raise ValueError('positive exact rational price required')
    num, den = price.numerator, price.denominator
    delta = 997 * amount * num - 1000 * den * required_out
    if delta <= 0:
        return {'possible': False, 'reason': 'TARGET_AT_OR_ABOVE_INFINITE_DEPTH_LIMIT'}
    k = ceil_div(997 * amount * required_out, delta)
    x, y = den * k, num * k
    if x + amount > MAX_RESERVE or y > MAX_RESERVE:
        return {'possible': False, 'reason': 'REQUIRED_DEPTH_EXCEEDS_PAIR_UINT112'}
    return {'possible': True, 'scale': k, 'collateral_reserve': x, 'loan_reserve': y,
            'out_at_boundary': amount_out(amount, x, y),
            'out_previous_scale': amount_out(amount, x-den, y-num) if k > 1 else 0}


def minimum_loan_reserve(amount: int, x: int, required_out: int) -> int | None:
    """Fixed x: smallest y that pays T, including swap fee/impact/rounding."""
    positive(amount); positive(x); positive(required_out)
    if x + amount > MAX_RESERVE:
        raise ValueError('Uniswap V2 post-swap collateral overflow')
    y = ceil_div(required_out * (1000*x + 997*amount), 997*amount)
    return y if y <= MAX_RESERVE else None


def liquidation(repaid_assets=8*WAD, lltv=86*10**16):
    # Zero-cash fixture totals. With zero interest, every swept cash level has
    # the same exact assets/shares ratio, including the 8-WETH-cash EVM boundary.
    witness = PostAccrualWitness(100*WAD, 100*WAD*10**6, 8*WAD*10**6,
                                10*WAD, 9*10**35, lltv)
    return calculate(witness, repaid_assets*10**6)


def ratio(value: Fraction) -> dict:
    return {'numerator': value.numerator, 'denominator': value.denominator}


def fixture_bytes() -> str:
    s = liquidation().seized_assets
    b = minimum_depth(s, 811*WAD//100, Fraction(9, 10))
    fields = (s, b['collateral_reserve'], b['loan_reserve'],
              b['out_previous_scale'], b['out_at_boundary'])
    # Foundry parseBytes rejects a trailing newline; existing ABI fixtures agree.
    return '0x' + ''.join(format(v, '064x') for v in fields)


def reconcile_trace(text: str) -> dict:
    text = re.sub(r' \[[^]\n]*\]', '', text)
    s = liquidation().seized_assets
    b = minimum_depth(s, 811*WAD//100, Fraction(9, 10))
    rows = re.findall(r'emit ExactBoundary\(flashRoute: (true|false), collateralReserve: (\d+), loanReserve: (\d+), dexOut: (\d+), success: (true|false)\)', text)
    expected = {(flash, str(b['collateral_reserve']-dx), str(b['loan_reserve']-dy),
                 str(b[key]), ok) for flash in ('false', 'true')
                for dx, dy, key, ok in ((10, 9, 'out_previous_scale', 'false'),
                                         (0, 0, 'out_at_boundary', 'true'))}
    if len(rows) != 4 or set(rows) != expected:
        raise ValueError('original-code EVM boundary mismatch')
    gas = {}
    for label, flash in (('CallbackAtSameCash', 'false'), ('FlashAtBoundary', 'true')):
        section = text.split('[PASS] testTrace'+label+'()', 1)
        if len(section) != 2:
            raise ValueError('missing independent gas trace')
        section = section[1].split('[PASS]', 1)[0]
        values = re.findall(r'emit LocalCallGas\(flashRoute: '+flash+r', grossCallGas: (\d+), success: true\)', section)
        if len(values) != 1:
            raise ValueError('ambiguous gas trace')
        gas['flash' if flash == 'true' else 'callback'] = int(values[0])
    return {'boundary_rows_matched': len(rows), 'local_gross_call_gas': gas,
            'callback_minus_flash_gross_gas': gas['callback']-gas['flash'],
            'gas_scope': 'Warm fixture call frame; excludes encoding, intrinsic gas, refunds, creation and funding',
            'production_gas': None}


def report() -> dict:
    liq = liquidation(); s, debt = liq.seized_assets, liq.repaid_assets
    price = Fraction(9, 10)
    limit = Fraction(997*s, 1000) * price
    # Strictly below the rational limit at any finite positive reserve.
    upper_output = ceil_div(limit.numerator, limit.denominator) - 1
    max_scale = min((MAX_RESERVE-s)//price.denominator, MAX_RESERVE//price.numerator)
    maximum_pair_output = amount_out(s, price.denominator*max_scale, price.numerator*max_scale)
    depths = []
    for whole in (20, 100, 1000, 10000):
        x = whole*WAD; y = x*9//10; out = amount_out(s, x, y)
        spot = s*y//x; no_fee = s*y//(x+s)
        depths.append({'collateral_reserve': x, 'loan_reserve': y,
                       'spot_value': spot, 'impact_without_fee': spot-no_fee,
                       'additional_fee_effect': no_fee-out, 'executable_out': out,
                       'surplus_before_external_costs': out-debt,
                       'max_external_cost_for_positive_one_wei_profit': out-debt-1,
                       'measured_external_costs': None})
    thresholds = []
    for label, required in (('debt_only', debt),
                            ('positive_before_external_costs', debt+1),
                            ('current_allocation_and_token_floor', debt+11*WAD//100),
                            ('old_half_eth_allocation_only', debt+WAD//2),
                            ('old_allocation_and_token_floor', debt+6*WAD//10)):
        thresholds.append({'condition': label, 'required_output': required,
                           **minimum_depth(s, required, price)})
    price_thresholds = []
    for required in (debt, debt+11*WAD//100, debt+WAD//2, debt+6*WAD//10):
        x = 1000*WAD
        y = minimum_loan_reserve(s, x, required)
        price_thresholds.append({'required_output': required, 'collateral_reserve': x,
                                 'minimum_loan_reserve': y,
                                 'minimum_spot_relative_to_oracle': ratio(Fraction(y, x)/price)})
    sizes = []
    for whole in (1, 2, 4, 8):
        q = liquidation(whole*WAD)
        for depth in (100, 1000):
            out = amount_out(q.seized_assets, depth*WAD, depth*9*WAD//10)
            sizes.append({'repaid_shares': q.repaid_shares, 'debt': q.repaid_assets,
                          'seized': q.seized_assets, 'pool_collateral': depth*WAD,
                          'surplus_before_external_costs': out-q.repaid_assets})
    incentives = []
    for lltv in (80*10**16, 86*10**16, 90*10**16, 945*10**15):
        try:
            q = liquidation(lltv=lltv)
            row = {'protocol_math_permits': True, 'incentive_wad': q.liquidation_incentive_factor,
                   'seized': q.seized_assets, 'surplus_before_external_costs':
                   amount_out(q.seized_assets, 1000*WAD, 900*WAD)-q.repaid_assets}
        except ValueError as exc:
            row = {'protocol_math_permits': False, 'reason': str(exc)}
        incentives.append({'counterfactual_lltv': lltv, **row})
    return {'classification': 'EXACT_SYNTHETIC_ECONOMIC_BOUNDARIES',
            'debt': debt, 'seized': s, 'incentive_wad': liq.liquidation_incentive_factor,
            'spot_price': ratio(price), 'fee_adjusted_infinite_depth_limit': ratio(limit),
            'strict_finite_depth_surplus_upper_bound': upper_output-debt,
            'maximum_surplus_with_uint112_capacity': maximum_pair_output-debt,
            'depths': depths, 'fixed_price_thresholds': thresholds,
            'fixed_depth_price_thresholds': price_thresholds,
            'size_sensitivity_same_position': sizes, 'counterfactual_incentive_sensitivity': incentives,
            'current_allocation': {'unwrap': WAD//10, 'test_sponsor': WAD//20,
                                   'coinbase': WAD//25, 'operator_native': WAD//100,
                                   'minimum_operator_weth': WAD//100},
            'actual_gas_cost': None, 'actual_sponsor_requirement': None,
            'historical_state_verified': False, 'sponsorship_accepted': False,
            'economically_admitted_operations': 0, 'certified': False,
            'limits': ['Output inequalities are sufficient only for the stated swap arithmetic',
                       'Protocol health, collateral, route permissions and gas funding remain separate gates',
                       'The native operator distribution is an asset transfer, not an external expense',
                       'Do not subtract DEX fee/impact a second time from executable output',
                       'Counterfactual prices and LLTVs are sensitivity, not observed opportunities']}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-fixture', action='store_true')
    parser.add_argument('--check-fixture', action='store_true')
    parser.add_argument('--trace', type=Path, help='gzip original-code boundary traces to reconcile')
    args = parser.parse_args()
    if args.write_fixture:
        FIXTURE.write_text(fixture_bytes())
    if args.check_fixture:
        if FIXTURE.read_text() != fixture_bytes():
            raise ValueError('stale profitability boundary fixture')
        print('Exact boundary fixture matches Python model')
        return 0
    result = report()
    if args.trace:
        result['evm_comparison'] = reconcile_trace(gzip.decompress(args.trace.read_bytes()).decode())
    print(json.dumps(result, indent=2))
    return 2  # Never promotes a synthetic calculation to economic admission.


if __name__ == '__main__':
    raise SystemExit(main())
