"""Exact-integer, fail-closed Morpho Blue liquidation *math* for post-accrual state.

Reference semantics: Morpho.sol#liquidate and Morpho libraries MathLib,
SharesMathLib and ConstantsLib. This module CANNOT certify an on-chain
opportunity, simulate swaps, fund gas, or prove that NQC wins an auction.
All inputs must be independently witnessed at the decision-time block/state;
interest must already have accrued exactly as Morpho would accrue it.
No networking, signing, oracle queries or floating-point operations.
"""
from __future__ import annotations

from dataclasses import dataclass

U256 = 2**256 - 1
U128 = 2**128 - 1
WAD = 10**18
ORACLE_PRICE_SCALE = 10**36
VIRTUAL_SHARES = 10**6
VIRTUAL_ASSETS = 1
LIQUIDATION_CURSOR = 3 * 10**17
MAX_LIQUIDATION_INCENTIVE = 115 * 10**16


def checked(n: object, label: str, maximum: int = U256) -> int:
    if type(n) is not int or n < 0 or n > maximum:
        raise ValueError(f"{label}: expected unsigned integer <= {maximum}")
    return n


def mul_div(x: int, y: int, denominator: int, *, up: bool = False) -> int:
    checked(x, "mul_div.x"); checked(y, "mul_div.y"); checked(denominator, "mul_div.denominator")
    if denominator == 0:
        raise ValueError("division by zero")
    product = x * y
    if product > U256:
        raise ValueError("uint256 multiplication overflow")
    if up:
        # Equivalent to Solidity (x*y + (d-1))/d under uint256 checking.
        if product + denominator - 1 > U256:
            raise ValueError("uint256 rounded multiplication overflow")
        return (product + denominator - 1) // denominator
    return product // denominator


def to_assets(shares: int, total_assets: int, total_shares: int, *, up: bool) -> int:
    checked(shares, "shares", U128)
    checked(total_assets, "total_assets", U128)
    checked(total_shares, "total_shares", U128)
    return mul_div(shares, total_assets + VIRTUAL_ASSETS, total_shares + VIRTUAL_SHARES, up=up)


def to_shares(assets: int, total_assets: int, total_shares: int, *, up: bool) -> int:
    checked(assets, "assets")
    checked(total_assets, "total_assets", U128)
    checked(total_shares, "total_shares", U128)
    return mul_div(assets, total_shares + VIRTUAL_SHARES, total_assets + VIRTUAL_ASSETS, up=up)


def incentive_factor(lltv: int) -> int:
    checked(lltv, "lltv")
    if not 0 < lltv < WAD:
        raise ValueError("invalid lltv: requires 0 < lltv < WAD")
    penalty = mul_div(LIQUIDATION_CURSOR, WAD - lltv, WAD)
    return min(MAX_LIQUIDATION_INCENTIVE, mul_div(WAD, WAD, WAD - penalty))


@dataclass(frozen=True)
class PostAccrualWitness:
    """Values read *after* accrueInterest, at one independently proved state."""
    total_borrow_assets: int
    total_borrow_shares: int
    borrower_borrow_shares: int
    borrower_collateral: int
    oracle_price: int
    lltv: int


@dataclass(frozen=True)
class LiquidationQuote:
    repaid_shares: int
    repaid_assets: int
    seized_assets: int
    liquidation_incentive_factor: int
    borrower_debt_assets_rounded_up: int
    max_safe_borrow_assets: int
    prestate_liquidatable: bool
    status: str = "MATH_ONLY_NOT_AN_EXECUTABLE_OPPORTUNITY"
    certified: bool = False
    live_executable: bool = False


def calculate(w: PostAccrualWitness, repaid_shares: int) -> LiquidationQuote:
    if not isinstance(w, PostAccrualWitness):
        raise ValueError("typed post-accrual witness required")
    checked(w.total_borrow_assets, "total_borrow_assets", U128)
    checked(w.total_borrow_shares, "total_borrow_shares", U128)
    checked(w.borrower_borrow_shares, "borrower_borrow_shares", U128)
    checked(w.borrower_collateral, "borrower_collateral", U128)
    checked(w.oracle_price, "oracle_price")
    checked(repaid_shares, "repaid_shares", U128)
    lif = incentive_factor(w.lltv)
    if w.oracle_price == 0 or w.total_borrow_assets == 0 or w.total_borrow_shares == 0:
        raise ValueError("empty oracle/market is inadmissible")
    if not 0 < w.borrower_borrow_shares <= w.total_borrow_shares:
        raise ValueError("borrower has no valid debt")
    if not 0 < repaid_shares <= w.borrower_borrow_shares:
        raise ValueError("liquidation shares outside borrower's debt")
    borrower_debt = to_assets(w.borrower_borrow_shares, w.total_borrow_assets, w.total_borrow_shares, up=True)
    collateral_value = mul_div(w.borrower_collateral, w.oracle_price, ORACLE_PRICE_SCALE)
    maximum_borrow = mul_div(collateral_value, w.lltv, WAD)
    if borrower_debt <= maximum_borrow:
        raise ValueError("HEALTHY_POSITION: no permissible liquidation")
    repaid_assets = to_assets(repaid_shares, w.total_borrow_assets, w.total_borrow_shares, up=True)
    seized_quoted = to_assets(repaid_shares, w.total_borrow_assets, w.total_borrow_shares, up=False)
    seized_value = mul_div(seized_quoted, lif, WAD)
    seized_assets = mul_div(seized_value, ORACLE_PRICE_SCALE, w.oracle_price)
    if seized_assets > w.borrower_collateral:
        raise ValueError("seized collateral exceeds borrower collateral")
    if seized_assets == 0 or repaid_assets == 0:
        raise ValueError("rounding to zero: no executable liquidation")
    return LiquidationQuote(repaid_shares=repaid_shares, repaid_assets=repaid_assets,
                            seized_assets=seized_assets, liquidation_incentive_factor=lif,
                            borrower_debt_assets_rounded_up=borrower_debt,
                            max_safe_borrow_assets=maximum_borrow,
                            prestate_liquidatable=True)
