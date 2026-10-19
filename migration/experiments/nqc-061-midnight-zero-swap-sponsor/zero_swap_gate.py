"""NQC061: documentary gate for potential swap-free Midnight liquidations.

STRICTLY OFFLINE. No network, live trading, signing, key management or quote.
Never claims a real candidate, lender, sponsor, profit or inclusion. The published
Morpho bot is a source of MECHANISM semantics, not of verified NQC cashflows.
"""
from __future__ import annotations

import re
from typing import Any

ADDRESS_RE = re.compile(r"0x[a-fA-F0-9]{40}\Z")
MARKET_RE = re.compile(r"0x[a-fA-F0-9]{64}\Z")
UINT_RE = re.compile(r"(?:0|[1-9][0-9]*)\Z")
ETHEREUM_WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"


def raw(v: Any, field: str) -> int | None:
    if v is None:
        return None
    if not isinstance(v, str) or UINT_RE.fullmatch(v) is None:
        raise ValueError(f"{field} needs an exact nonnegative decimal integer string")
    return int(v)


def address(v: Any, field: str) -> str:
    if not isinstance(v, str) or ADDRESS_RE.fullmatch(v) is None:
        raise ValueError(f"{field}: Ethereum 20-byte address required")
    return v.lower()


def amount_interval(raw_rec: dict, name: str) -> tuple[int | None, int | None]:
    pair = raw_rec.get(name)
    if not isinstance(pair, dict):
        raise ValueError(f"{name} needs interval dict")
    lo, hi = raw(pair.get('min'), f'{name}.min'), raw(pair.get('max'), f'{name}.max')
    if lo is not None and hi is not None and lo > hi:
        raise ValueError(f'{name}: lower > upper')
    return lo, hi


def structural_gate(candidate: dict) -> dict:
    if candidate.get('strategy') != 'MORPHO_MIDNIGHT_POST_MATURITY_SAME_LOAN_AS_COLLATERAL':
        raise ValueError('Unrecognized strategy')
    if not isinstance(candidate.get('chain_id'), int) or isinstance(candidate['chain_id'], bool):
        raise ValueError('chain_id must be int')
    if not isinstance(candidate.get('market_id'), str) or not MARKET_RE.fullmatch(candidate['market_id']):
        raise ValueError('market_id must be bytes32')
    for fld in ('borrower', 'loan_token', 'collateral_token'):
        address(candidate.get(fld), fld)
    same = address(candidate['loan_token'], 'loan_token') == address(candidate['collateral_token'], 'collateral_token')
    mat = raw(candidate.get('maturity_timestamp'), 'maturity_timestamp')
    block_time = raw(candidate.get('canonical_block_timestamp'), 'canonical_block_timestamp')
    debt = raw(candidate.get('borrower_debt_units'), 'borrower_debt_units')
    gate = candidate.get('liquidator_gate')
    if gate not in ('OPEN', 'RESTRICTED', 'UNKNOWN'):
        raise ValueError('liquidator_gate OPEN/RESTRICTED/UNKNOWN required')
    verified = all(candidate.get(v) is True for v in (
        'canonical_market_proven', 'canonical_position_proven', 'block_membership_proven'
    ))
    if candidate['chain_id'] != 1:
        status = 'NOT_ETHEREUM_MAINNET'
    elif not same:
        status = 'REQUIRES_COLLATERAL_SALE_NOT_SWAP_FREE'
    elif gate == 'RESTRICTED' and candidate.get('gate_permission_proven') is not True:
        status = 'LIQUIDATOR_GATE_BLOCKED'
    elif gate == 'UNKNOWN':
        status = 'LIQUIDATOR_GATE_UNKNOWN'
    elif mat is None or block_time is None or debt is None:
        status = 'MISSING_TIMESTAMP_OR_POSITION'
    elif block_time <= mat:
        status = 'NOT_STRICTLY_POST_MATURITY'
    elif debt == 0:
        status = 'NO_BORROWER_DEBT'
    elif not verified:
        status = 'MISSING_CANONICAL_PROOFS'
    else:
        status = 'MECHANISM_ELIGIBILITY_ONLY'
    return {
        'result': status, 'same_erc20_contract': same,
        'onchain_identity_and_position_verified': verified,
        'market_gate': gate,
        'strictly_post_maturity': None if mat is None or block_time is None else block_time > mat,
        'gas_prefunding_obviated': False,
        'competition_captured': False,
        'source_note': 'Same-asset equality removes the DEX collateral conversion only. No profit, gas, permission, or inclusion implied.',
    }


def economic_gate(candidate: dict) -> dict:
    """Reject with upper bound ONLY when exact same-denomination minima are explicit.

    Maximum upfront gas RESERVE is separately enforced as a sponsor cap gate;
    reserve is not charged again as realized gas. Unknown amounts remain unknown.
    No ETH/USDC conversion. WETH/ETH native coverage requires a separately proven
    unwrap and disjoint gas/bid/sponsor obligations.
    """
    ledger = candidate.get('ledger')
    if not isinstance(ledger, dict):
        raise ValueError('Missing ledger')
    if ledger.get('asset_address', '').lower() != candidate['loan_token'].lower():
        raise ValueError('Ledger must use the exact loan ERC20 address')
    if ledger.get('cash_buckets_disjoint') is not True:
        raise ValueError('Separate repayment/loan fee/token bid costs must be nonoverlapping')
    if ledger.get('seized_amount_is_received_in_callback') is not True:
        raise ValueError('Requires seized collateral received by the executor pre-repay')
    cats = ['seized_raw', 'repaid_raw', 'loan_fee_raw', 'token_bid_raw']
    amounts = {x: amount_interval(ledger, x) for x in cats}
    upper = (amounts['seized_raw'][1] - amounts['repaid_raw'][0]
             - amounts['loan_fee_raw'][0] - amounts['token_bid_raw'][0]) if all(
                 amounts[x][1 if x == 'seized_raw' else 0] is not None for x in cats) else None
    lower = (amounts['seized_raw'][0] - amounts['repaid_raw'][1]
             - amounts['loan_fee_raw'][1] - amounts['token_bid_raw'][1]) if all(
                 amounts[x][0 if x == 'seized_raw' else 1] is not None for x in cats) else None

    native = candidate.get('native', {})
    if not isinstance(native, dict):
        raise ValueError('native must be an object')
    gas = amount_interval(native, 'gas_actual_wei') if 'gas_actual_wei' in native else (None, None)
    sponsor_margin = amount_interval(native, 'sponsor_remuneration_wei') if 'sponsor_remuneration_wei' in native else (None, None)
    separate_bid = amount_interval(native, 'separate_inclusion_bid_wei') if 'separate_inclusion_bid_wei' in native else (None, None)
    if native.get('native_cost_buckets_disjoint') is not True:
        raise ValueError('Base-fee and priority-fee are in gas; extra bid must not duplicate gas or token bid')

    native_pricing_proven = (
        candidate['chain_id'] == 1 and
        address(candidate['loan_token'], 'loan_token') == ETHEREUM_WETH and
        native.get('explicit_WETH_unwrap_and_ownership_proven') is True
    )
    paid_upper = None
    paid_lower = None
    if native_pricing_proven and upper is not None and all(z is not None for z in (gas[0], sponsor_margin[0], separate_bid[0])):
        paid_upper = upper - gas[0] - sponsor_margin[0] - separate_bid[0]
    if native_pricing_proven and lower is not None and all(z is not None for z in (gas[1], sponsor_margin[1], separate_bid[1])):
        paid_lower = lower - gas[1] - sponsor_margin[1] - separate_bid[1]
    prefunding_cap = raw(native.get('sponsor_advance_cap_wei'), 'sponsor_advance_cap_wei')
    prefix_reserve = raw(native.get('max_gas_reserve_at_signed_prefix_wei'), 'max_gas_reserve_at_signed_prefix_wei')
    if prefunding_cap is not None and prefix_reserve is not None:
        prefund = 'CAP_INSUFFICIENT' if prefunding_cap < prefix_reserve else 'CAP_COVERS_DECLARED_PREFIX_ONLY'
    else:
        prefund = 'UNKNOWN'

    if upper is not None and upper <= 0:
        result = 'REJECT_LOAN_ASSET_UPPER_NONPOSITIVE'
    elif paid_upper is not None and paid_upper <= 0:
        result = 'REJECT_AFTER_NATIVE_MINIMUM_UPPER_NONPOSITIVE'
    elif prefund == 'CAP_INSUFFICIENT':
        result = 'REJECT_SPONSOR_CAP_BELOW_PREFIX_RESERVE'
    elif upper is None:
        result = 'INCOMPLETE_LOAN_LEDGER'
    elif not native_pricing_proven:
        result = 'NATIVE_GAS_BRIDGE_UNVERIFIED'
    elif paid_upper is None:
        result = 'NATIVE_COSTS_UNKNOWN'
    elif prefund == 'UNKNOWN':
        result = 'SPONSOR_PREFUNDING_CAP_UNKNOWN'
    else:
        result = 'CONDITIONAL_POSSIBLE_MARGIN_NOT_PROFIT'
    return {
        'result': result,
        'loan_asset_upper_raw': str(upper) if upper is not None else None,
        'loan_asset_lower_raw': str(lower) if lower is not None else None,
        'post_native_conditional_upper_wei': str(paid_upper) if paid_upper is not None else None,
        'post_native_conditional_lower_wei': str(paid_lower) if paid_lower is not None else None,
        'native_bridge_proven': native_pricing_proven,
        'prefunding_vs_max_gas_reserve': prefund,
        'gas_reserve_deducted_from_profit': False,
        'actual_gas_cost_can_be_replaced_with_zero': False,
        'unknown_builder_bid_assumed_zero': False,
        'real_NQC_profit': None,
        'explanation': 'Gas actual is an economic cost. Max reserve is an upfront solvency constraint and is NOT subtracted a second time. Positive upper is not sufficient.'
    }


def evaluate(candidate: dict) -> dict:
    struct = structural_gate(candidate)
    econ = economic_gate(candidate)
    precedence = ('NOT_ETHEREUM_MAINNET', 'REQUIRES_COLLATERAL_SALE_NOT_SWAP_FREE',
                  'LIQUIDATOR_GATE_BLOCKED', 'LIQUIDATOR_GATE_UNKNOWN',
                  'MISSING_TIMESTAMP_OR_POSITION', 'NOT_STRICTLY_POST_MATURITY',
                  'NO_BORROWER_DEBT', 'MISSING_CANONICAL_PROOFS')
    status = struct['result'] if struct['result'] in precedence else econ['result']
    return {
        'strategy': candidate['strategy'],
        'source_evidence_kind': candidate.get('source_evidence_kind', 'UNVERIFIED'),
        'fixture_only': candidate.get('fixture_only') is True,
        'structural': struct,
        'economic': econ,
        'final_decision': status,
        'profit_authenticated': False,
        'sponsor_committed': False,
        'competition_win_proven': False,
        'no_personal_recourse_proven': False,
        'commercial_admission': False,
    }
