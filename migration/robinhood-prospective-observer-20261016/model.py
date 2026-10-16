"""Integer screening arithmetic tied to pinned Morpho Blue; route trace is decisive."""
from read_rpc import need

WAD = 10**18
SCALE = 10**36
MARKET_PARAMS = [int(x, 16) for x in [
    '0x5fc5360d0400a0fd4f2af552add042d716f1d168',
    '0x63c12667638f2ae6fc6ae09b43d98ec84a8586ea',
    '0xcde9599059f8ae6d6b9f33a0af7877827ec75f16',
    '0x2bd3d5965b26b51814ac95127b2b80dd6ccc0fa1']] + [625000000000000000]


def encode(selector, *values):
    need(all(type(x) is int and 0 <= x < 2**256 for x in values), 'INVALID_ABI_INTEGER')
    return selector + ''.join(x.to_bytes(32, 'big').hex() for x in values)


def words(data, count):
    need(type(data) is str and data.startswith('0x') and len(data) == 2 + count * 64, 'INVALID_ABI_LENGTH')
    try:
        return [int.from_bytes(bytes.fromhex(data[2+i*64:2+(i+1)*64]), 'big') for i in range(count)]
    except ValueError as error:
        raise ValueError('INVALID_ABI_HEX') from error


def up(numerator, denominator):
    need(denominator > 0 and numerator >= 0, 'INVALID_DIVISION')
    return (numerator + denominator - 1) // denominator


def accrue(market, rate, timestamp):
    need(len(market) == 6 and all(type(x) is int and 0 <= x < 2**128 for x in market), 'INVALID_MARKET_ABI')
    supply_assets, supply_shares, assets, shares, updated, fee = market
    need(updated > 0 and updated <= timestamp and 0 <= rate <= 10**18 and fee <= WAD // 4, 'INVALID_ACCRUAL_INPUT')
    elapsed = timestamp - updated
    first = rate * elapsed
    second = first * first // (2 * WAD)
    third = second * first // (3 * WAD)
    interest = assets * (first + second + third) // WAD
    need(assets + interest < 2**128 and supply_assets + interest < 2**128, 'ACCRUAL_OVERFLOW')
    return assets + interest, shares


def screen(position, market, rate, price, timestamp, policy):
    need(len(position) == 3 and all(type(x) is int and 0 <= x < 2**256 for x in position), 'INVALID_POSITION')
    _, debt_shares, collateral = position
    need(debt_shares < 2**128 and collateral < 2**128 and type(price) is int and
         0 < price < 2**256 and collateral * price < 2**256, 'INVALID_POSITION_OR_PRICE')
    assets, shares = accrue(market, rate, timestamp)
    need(debt_shares <= shares, 'POSITION_SHARES_EXCEED_MARKET')
    debt = up(debt_shares * (assets + 1), shares + 10**6)
    maximum = (collateral * price // SCALE) * MARKET_PARAMS[4] // WAD
    signal = debt > 0 and maximum * 10000 <= debt * (10000 + policy['near_threshold_bps'])
    return {'debt_shares': debt_shares, 'collateral_raw': collateral,
            'accrued_total_borrow_assets': assets, 'total_borrow_shares': shares,
            'debt_usdg_raw': debt, 'maximum_healthy_debt_usdg_raw': maximum,
            'computed_unhealthy': debt > maximum, 'screen_candidate': signal,
            'health_margin_bps_floor': ((maximum - debt) * 10000 // debt) if debt else None}


def size(screened, price, policy):
    if screened['debt_shares'] == 0 or screened['collateral_raw'] == 0:
        return None
    assets, shares = screened['accrued_total_borrow_assets'], screened['total_borrow_shares']
    incentive = min(115 * WAD // 100, WAD * WAD // (WAD - (3 * WAD // 10) * (WAD - MARKET_PARAMS[4]) // WAD))
    cap = min(policy['max_repay_usdg_raw'], screened['debt_usdg_raw'])
    initial = min(screened['collateral_raw'] // policy['seize_collateral_divisor'],
                  (cap * incentive // WAD) * SCALE // price)
    # A fixed deterministic halving rule handles rounding at the debt-share cap.
    for _ in range(8):
        if initial <= 0: return None
        quoted = up(initial * price, SCALE)
        repayment_shares = up(up(quoted * WAD, incentive) * (shares + 10**6), assets + 1)
        repayment = up(repayment_shares * (assets + 1), shares + 10**6)
        if 0 < repayment_shares <= screened['debt_shares'] and 0 < repayment <= cap:
            return {'seize_raw': initial, 'max_repay_usdg_raw': cap,
                    'predicted_repay_usdg_raw': repayment, 'predicted_repaid_shares': repayment_shares}
        initial //= 2
    return None
