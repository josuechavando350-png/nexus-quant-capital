"""Exact, per-asset theoretical settlement. No quote, inclusion or profit authority.

Swap outputs must already include venue fees and price impact. Never count the
same fee again. Flash borrowing is a financing inflow and a repayment outflow;
liquidation debt must not be counted twice as an economic expense.
"""
from dataclasses import dataclass
from fractions import Fraction
from preflight import unsigned


@dataclass(frozen=True)
class Settlement:
    executable_sale_loan_units: int
    flash_received_loan_units: int
    liquidation_repaid_loan_units: int
    flash_returned_loan_units: int
    finance_fee_loan_units: int
    other_loan_costs_units: int
    converted_loan_units: int
    executable_native_out_wei: int
    sponsor_payment_wei: int
    coinbase_payment_wei: int
    sponsor_advance_wei: int
    advance_returned_wei: int
    sponsor_topup_actual_gas_wei: int
    builder_other_verified_receipts_wei: int
    builder_proposer_payment_wei: int
    builder_other_costs_wei: int


def evaluate(s: Settlement) -> dict:
    if not isinstance(s, Settlement):
        raise ValueError("typed settlement required")
    for name, value in vars(s).items():
        if type(value) is not int:
            raise ValueError(f"{name}: integer units required")
        unsigned(value, name)
    if s.flash_received_loan_units != s.flash_returned_loan_units:
        raise ValueError("flash principal not fully repaid; fees are a separate field")
    if s.advance_returned_wei > s.sponsor_advance_wei:
        raise ValueError("returned funding exceeds the advance")
    operator_loan = (s.executable_sale_loan_units + s.flash_received_loan_units
                     - s.liquidation_repaid_loan_units - s.flash_returned_loan_units
                     - s.finance_fee_loan_units - s.other_loan_costs_units - s.converted_loan_units)
    operator_native = s.executable_native_out_wei - s.sponsor_payment_wei - s.coinbase_payment_wei
    sponsor = (s.sponsor_payment_wei + s.advance_returned_wei + s.builder_other_verified_receipts_wei
               - s.sponsor_advance_wei - s.sponsor_topup_actual_gas_wei
               - s.builder_proposer_payment_wei - s.builder_other_costs_wei)
    return {"status":"THEORETICAL_SETTLEMENT_ONLY", "operator_loan_units":operator_loan,
            "operator_native_wei":operator_native, "sponsor_margin_wei":sponsor,
            "balanced_positive_model":operator_loan>0 and operator_native>=0 and sponsor>0,
            "certified":False, "live_executable":False, "realized_profit":None,
            "limitations":["Each input needs independent execution evidence",
                           "Loan tokens and ETH are not added without an executable conversion",
                           "Gas paid by the EOA from the advance is not charged twice to the sponsor",
                           "Unused sponsor funding is not operator trading profit",
                           "Separate transactions do not share an EVM rollback boundary"]}


def expected_sponsor_margin(success_margin: int, failure_loss: int,
                            success_probability: Fraction, included_failure_probability: Fraction) -> Fraction:
    """Sensitivity only: remaining probability is not-included, with no onchain cost.

    No probability is inferred. Included failure losses must cover any unrepaid
    advance, funding-transfer gas and other costs without double counting.
    """
    if type(success_margin) is not int or type(failure_loss) is not int or failure_loss<0:
        raise ValueError("integer outcome costs required")
    if type(success_probability) is not Fraction or type(included_failure_probability) is not Fraction:
        raise ValueError("explicit exact probabilities required")
    if min(success_probability,included_failure_probability)<0 or success_probability+included_failure_probability>1:
        raise ValueError("invalid probability mass")
    return success_probability*success_margin-included_failure_probability*failure_loss
