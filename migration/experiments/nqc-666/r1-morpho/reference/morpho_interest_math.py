"""Exact Morpho interest arithmetic from a supplied rate; not an IRM simulator.

The rate must be the output of borrowRate at the correct state/time. Supplying
a rate from the future is invalid research even if the integer math agrees.
Reference: morpho-blue@9cf6d5b844625ba108e36d1cf911f5d2faf7c136.
"""
from dataclasses import dataclass, replace
from morpho_liquidation_math import U128, WAD, checked, mul_div, to_shares


@dataclass(frozen=True)
class MarketState:
    total_supply_assets: int
    total_supply_shares: int
    total_borrow_assets: int
    total_borrow_shares: int
    last_update: int
    fee: int


@dataclass(frozen=True)
class Accrual:
    market: MarketState
    elapsed: int
    interest: int
    fee_shares: int


def taylor_compounded(rate: int, elapsed: int) -> int:
    checked(rate, "rate"); checked(elapsed, "elapsed")
    first = checked(rate * elapsed, "rate*time")
    second = mul_div(first, first, 2 * WAD)
    third = mul_div(second, first, 3 * WAD)
    return checked(first + second + third, "Taylor sum")


def accrue(market: MarketState, timestamp: int, borrow_rate: int | None) -> Accrual:
    """None explicitly means zero IRM; 0 means a real IRM returning zero.

    Checks Morpho's uint128 market totals. The fee recipient's personal uint256
    supplyShares is outside this model; its overflow must be checked by the EVM.
    Timestamp is conservatively limited to uint128, unlike the unchecked cast
    in original Morpho. No current Ethereum timestamp is excluded by this limit.
    """
    if not isinstance(market, MarketState):
        raise ValueError("typed market required")
    for name, value in vars(market).items():
        checked(value, name, U128)
    checked(timestamp, "timestamp", U128)
    if market.last_update == 0 or timestamp < market.last_update:
        raise ValueError("market absent or timestamp precedes last accrual")
    if market.fee > WAD // 4:
        raise ValueError("fee exceeds Morpho MAX_FEE")
    if borrow_rate is not None:
        checked(borrow_rate, "borrow_rate")
    elapsed = timestamp - market.last_update
    interest = 0 if borrow_rate is None else mul_div(
        market.total_borrow_assets, taylor_compounded(borrow_rate, elapsed), WAD)
    borrow = checked(market.total_borrow_assets + interest, "accrued borrow assets", U128)
    supply = checked(market.total_supply_assets + interest, "accrued supply assets", U128)
    fee_amount = mul_div(interest, market.fee, WAD)
    fee_shares = to_shares(fee_amount, supply - fee_amount, market.total_supply_shares, up=False)
    checked(fee_shares, "fee shares", U128)
    shares = checked(market.total_supply_shares + fee_shares, "accrued supply shares", U128)
    return Accrual(replace(market, total_supply_assets=supply, total_supply_shares=shares,
                          total_borrow_assets=borrow, last_update=timestamp), elapsed, interest, fee_shares)
