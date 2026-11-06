"""Exact internal-unit equations, with no fabricated token/chain provenance."""
from copy import deepcopy
from decimal import localcontext
from unittest.mock import patch
import random
import unittest

from superhunter import balance_reconciliation as b


class InternalUnitTests(unittest.TestCase):
    def setUp(self):
        self.before = {'debit':'15','credit':'0'}
        self.after = {'debit':'8','credit':'7'}
        self.flows = [{'id':'one','from':'debit','to':'credit','amount_units':'7'}]

    def go(self, **kw):
        return b.reconcile_internal_units(self.before, self.after, self.flows, **kw)

    def test_exact_internal_equations(self):
        r=self.go(); self.assertEqual(r['status'],'UNIT_BALANCES_RECONCILED')
        self.assertEqual(r['unexplained_cells'],0); self.assertEqual(r['total_delta_units'],'0')

    def test_one_unit_not_rounded_away(self):
        self.after['credit']='8'
        self.assertEqual(self.go()['unexplained_cells'],1)
        self.assertEqual(self.go()['total_delta_units'],'1')

    def test_offsetting_residuals_do_not_hide_mismatch(self):
        self.after={'debit':'7','credit':'8'}
        r=self.go(); self.assertEqual(r['total_delta_units'],'0')
        self.assertEqual(r['unexplained_cells'],2)
        self.assertEqual(r['status'],'UNIT_BALANCES_MISMATCH')

    def test_no_transfer_when_state_unchanged(self):
        self.after=deepcopy(self.before); self.flows=[]
        self.assertEqual(self.go()['status'],'UNIT_BALANCES_RECONCILED')

    def test_charging_reverted_intent_breaks_equations(self):
        self.after=deepcopy(self.before)
        self.assertEqual(self.go()['unexplained_cells'],2)

    def test_incomplete_never_certified_by_zero_residual(self):
        self.assertEqual(self.go(coverage='declared_incomplete')['status'],'UNIT_BALANCES_INCONCLUSIVE')

    def test_missing_balance_not_assumed_zero(self):
        del self.after['credit']
        with self.assertRaises(b.AccountingError): self.go()

    def test_bool_float_negative_noncanonical_amounts_rejected(self):
        for value in (True,0,7.0,'-1','01','1.0','１',str(2**256)):
            with self.subTest(value=value):
                self.flows[0]['amount_units']=value
                with self.assertRaises(b.AccountingError):self.go()

    def test_zero_transfer_is_not_an_accounting_event(self):
        self.flows[0]['amount_units']='0'
        with self.assertRaisesRegex(b.AccountingError,'ZERO_FLOW'):self.go()

    def test_duplicate_flow_ids_rejected(self):
        self.flows*=2
        with self.assertRaisesRegex(b.AccountingError,'DUPLICATE_FLOW'):self.go()

    def test_unknown_or_ambiguous_endpoints_rejected(self):
        for endpoint in (None,'missing','debit',[],True):
            with self.subTest(endpoint=endpoint):
                self.flows[0]['to']=endpoint
                with self.assertRaises(b.AccountingError):self.go()

    def test_unknown_coverage_rejected(self):
        with self.assertRaises(b.AccountingError):self.go(coverage='probably-complete')

    def test_integer_precision_above_float(self):
        n=2**255+123
        self.before={'debit':str(n),'credit':'0'};self.after={'debit':str(n-7),'credit':'7'}
        self.assertEqual(self.go()['status'],'UNIT_BALANCES_RECONCILED')

    def test_ambient_decimal_context_not_used(self):
        with localcontext() as ctx:
            ctx.prec=2
            self.assertEqual(self.go()['status'],'UNIT_BALANCES_RECONCILED')

    def test_two_existing_arithmetic_implementations_execute(self):
        with patch.object(b,'_primary',wraps=b._primary) as a,patch.object(b,'_reference',wraps=b._reference) as ref:
            self.go()
        self.assertEqual((a.call_count,ref.call_count),(1,1))

    def test_disagreement_blocks_result(self):
        with patch.object(b,'_reference',return_value={}),self.assertRaisesRegex(b.AccountingError,'ARITHMETIC_DISAGREEMENT'):
            self.go()

    def test_inputs_not_mutated(self):
        before=deepcopy((self.before,self.after,self.flows));self.go()
        self.assertEqual(before,(self.before,self.after,self.flows))

    def test_no_monetary_or_chain_claim_invented(self):
        r=self.go();self.assertIsNone(r['monetary_valuation_usd'])
        self.assertFalse(r['token_balances_measured']);self.assertFalse(r['execution_authenticated'])
        for field in ('token','commit','chain_id','anchor','price','profit'):
            self.assertNotIn(field,r)

    def test_seeded_exact_equations_and_mutations(self):
        rng=random.Random(20261105)
        for i in range(128):
            debit=rng.randrange(1,2**220);credit=rng.randrange(2**220);amount=rng.randrange(1,debit+1)
            self.before={'debit':str(debit),'credit':str(credit)}
            self.after={'debit':str(debit-amount),'credit':str(credit+amount)}
            self.flows[0]['amount_units']=str(amount)
            self.assertEqual(self.go()['status'],'UNIT_BALANCES_RECONCILED')
            self.after['credit']=str(credit+amount+1)
            self.assertEqual(self.go()['unexplained_cells'],1)


if __name__=='__main__': unittest.main()
