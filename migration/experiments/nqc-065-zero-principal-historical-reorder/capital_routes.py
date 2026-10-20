"""NQC065 offline exact base-unit accounting for a published historical 2025 Morpho liquidation.

No EVM replay, chain reading, price quote, builder sponsorship or capital validation.
Routes are *counterfactual* to the original externally prefunded transaction.
"""
from decimal import Decimal, ROUND_DOWN
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
Q18 = 10**18
Q6 = 10**6
WETH = '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2'


def to_units(value: str, decimals: int) -> int:
    if not isinstance(value, str) or not value or 'e' in value.lower():
        raise ValueError('requires explicit fixed decimal string')
    d = Decimal(value)
    if not d.is_finite() or d < 0 or d.as_tuple().exponent < -decimals:
        raise ValueError('negative, nonfinite, or subunit')
    raw = d * (10**decimals)
    if raw != raw.to_integral_exact():
        raise ValueError('amount is not integer base units')
    return int(raw)


def fixed(amount: int, decimals: int) -> str:
    prefix = '-' if amount < 0 else ''
    amount = abs(amount)
    if decimals == 0:
        return prefix + str(amount)
    s = str(amount).zfill(decimals+1)
    return prefix + s[:-decimals] + '.' + s[-decimals:]


def amount(case, name, decimals):
    return to_units(case[name], decimals)


def analyze(case: dict) -> dict:
    if case.get('chain_id') != 1 or case.get('protocol') != 'Morpho Blue':
        raise ValueError('must analyze pinned Ethereum Morpho Blue case')
    if case.get('weth_token', '').lower() != WETH:
        raise ValueError('WETH identity mismatch')
    if case.get('NQC_executed') or case.get('flash_loan_verified') or case.get('builder_advance_verified'):
        raise ValueError('unsupported assertion of realized NQC financing/capture')
    first_weth = amount(case,'weth_sent_to_uniswap_v2',18)
    final_weth = amount(case,'weth_received_from_uniswap_v3',18)
    coinbase_weth = amount(case,'weth_withdrawal',18)
    transfer_eth = amount(case,'eth_transfer_to_beaverbuild',18)
    gas_eth = amount(case,'effective_gas_paid_eth',18)
    gas_units = int(case['gas_used'])
    gas_price = amount(case,'effective_gas_price_gwei',9) # converts gwei -> wei
    if coinbase_weth != transfer_eth:
        raise ValueError('builder payout not matched by WETH unwrap')
    if gas_units * gas_price != gas_eth:
        raise ValueError('gas receipt mismatch')
    usdc_in = amount(case,'usdc_received_from_uniswap_v2',6)
    usdc_due = amount(case,'usdc_repaid_to_morpho',6)
    seized_uni = amount(case,'uni_seized_from_morpho',18)
    sold_uni = amount(case,'uni_sold_to_uniswap_v3',18)
    if seized_uni != sold_uni or usdc_due > usdc_in:
        raise ValueError('unsatisfied sale/repay leg')
    gross = final_weth-first_weth
    after_builder_weth = gross - coinbase_weth
    after_gas_weth_equiv = after_builder_weth - gas_eth
    if after_gas_weth_equiv < 0:
        raise ValueError('historical conditional margin is not positive')
    # Rearranged callback-first route:
    # 1) receive UNI 2) UNI -> WETH (V3) 3) spend same WETH (V2) -> USDC
    # 4) repay Morpho USDC 5) optionally unwrap WETH to pay builder.
    # This validates quantities ONLY IF fills & oracle eligibility survive the reorder.
    c1_weth_pre_repay_buffer = final_weth-first_weth
    if c1_weth_pre_repay_buffer < coinbase_weth:
        raise ValueError('insufficient WETH to cover historic bid after callback')
    # Aave loan initial 5bp is illustrative and can change; don't claim available premium.
    indicative_aave_5bp_fee = first_weth * 5 // 10000
    haircuts = {}
    for bp in [0, 25, 50, 60, 63, 65, 68, 70, 75, 100]:
        # If UNI exit yields bp less WETH, other legs remain identical.
        loss = final_weth * bp // 10000
        haircuts[str(bp)] = {
            'exit_proceeds_reduction_WETH':fixed(loss,18),
            'after_original_bid_gas_conditional_ETH_equivalent':fixed(after_gas_weth_equiv-loss,18),
            'after_illustrative_5bp_premium_ETH_equivalent':fixed(after_gas_weth_equiv-loss-indicative_aave_5bp_fee,18)
        }
    threshold_no_flash = Decimal(after_gas_weth_equiv)*Decimal(10000)/Decimal(final_weth)
    threshold_5bp = Decimal(after_gas_weth_equiv-indicative_aave_5bp_fee)*Decimal(10000)/Decimal(final_weth)
    out = {
        'classification':'TWO_ATOMIC_CAPITAL_FREE_HYPOTHESES_NOT_REPLAYED',
        'source_case':'NQC064 source: Etherscan transcription, not independently canonical',
        'historical_tx_hash':case['tx_hash'],
        'historical_chain':1,
        'original_prefunded_WETH_leg':fixed(first_weth,18),
        'UNI_received_prior_to_repay_in_Morpho_callback':'DOCUMENTED_BY_PINNED_UPSTREAM_SOURCE_ONLY',
        'observed_UNI_exit_WETH':fixed(final_weth,18),
        'observed_USDC_purchased':fixed(usdc_in,6),
        'observed_USDC_due':fixed(usdc_due,6),
        'observed_USDC_dust':fixed(usdc_in-usdc_due,6),
        'historical_WETH_spread':fixed(gross,18),
        'historical_WETH_reserved_for_beaverbuild_ETH_transfer':fixed(coinbase_weth,18),
        'conditional_same_economic_owner_post_historical_gas_ETH_equiv':fixed(after_gas_weth_equiv,18),
        'hypothesis_C1_collateral_first': {
            'first_WETH_from_reordered_sale_if_same_V3_fill':fixed(final_weth,18),
            'WETH_required_to_copy_original_USDC_swap_if_same_V2_state':fixed(first_weth,18),
            'WETH_remaining_before_builder_gas_if_same_fills':fixed(c1_weth_pre_repay_buffer,18),
            'USDC_cover_at_same_V2_swap_fill':usdc_in>=usdc_due,
            'initial_WETH_inventory_needed_IF_exact_replay_succeeds': '0',
            'proof_of_executable_historical_reorder':False,
            'critical_unknowns':['V2 reserves and resulting exact swap output after reorder', 'V3 state at point of UNI sale','Morpho oracle and eligibility dependence on initial V2 swap', 'callback gas cost and bytecode', 'fee/payout and exact Titan sponsor terms', 'ex-ante capture and failed attempts'],
        },
        'hypothesis_Morpho_zero_fee_flash_WETH': {
            'principal_WETH':fixed(first_weth,18),
            'protocol_flash_premium_as_documented':'0',
            'cash_balance_requirement_WETH_at_historical_prestate':fixed(first_weth,18),
            'contract_balance_at_historical_prestate_verified':False,
            'callback_nested_liquidate_EVM_replay_passed':False,
            'remaining_margin_before_incremental_flash_gas_sponsor':fixed(after_gas_weth_equiv,18),
        },
        'illustrative_Aave_initial_5bp_premium_only': fixed(indicative_aave_5bp_fee,18),
        'margin_with_illustrative_Aave_5bp_before_incremental_costs':fixed(after_gas_weth_equiv-indicative_aave_5bp_fee,18),
        'max_synthetic_UNI_exit_haircut_bp_if_all_else_unchanged_no_flash': format(threshold_no_flash.quantize(Decimal('0.000001'),rounding=ROUND_DOWN),'f'),
        'max_synthetic_UNI_exit_haircut_bp_after_5bp_premium':format(threshold_5bp.quantize(Decimal('0.000001'),rounding=ROUND_DOWN),'f'),
        'haircut_sensitivity_bp':haircuts,
        'ETH_to_WETH_bridge_1_to_1_is_explained':True,
        'compensation_to_a_different_builder_unpriced':True,
        'additional_gas_sponsor_failure_cost_unpriced':True,
        'NQC_realized_profit':None,
        'financier_committed':False,
        'personal_no_recourse_proven':False,
        'commercial_admission':False,
        'canary_enabled':False,
        'safe_next_action':'Obtain authorized archive state/oracle/pool reserves+callbacks for block 21762897, replay collateral-first path; or Morpho contract WETH liquidity at parent block for zero-fee flash. Then establish specific Titan sponsor and out-of-sample capture.'
    }
    return out


def run():
    case=json.loads((HERE/'case.json').read_text(encoding='utf-8'))
    return analyze(case)

if __name__=='__main__':
    print(json.dumps(run(),indent=2,sort_keys=True))
