import copy,unittest
from funding_matrix import gate,max_advance,validate_operator,cases,uint,OP_LABELS
class Tests(unittest.TestCase):
 def test_positive_cash_never_commercial(self):
  r=gate(True,15,30,1);self.assertTrue(r['cash_positive_candidate']);self.assertFalse(r['commercial_admission'])
 def test_residual_never_profit(self):self.assertEqual(gate(True,100,1,1)['distributable_residual_eth_wei'],0)
 def test_zero_residual_not_legal_proof(self):self.assertFalse(gate(True,0,1,1)['no_recourse_verified'])
 def test_loss(self):self.assertFalse(gate(True,0,-1,1)['cash_positive_candidate'])
 def test_zero_margin(self):self.assertFalse(gate(True,0,0,1)['cash_positive_candidate'])
 def test_partial(self):self.assertFalse(gate(False,5,20,1)['cash_positive_candidate'])
 def test_no_operator_weth(self):self.assertFalse(gate(True,0,20,0)['cash_positive_candidate'])
 def test_unknown_cost(self):self.assertIsNone(max_advance(90,2,1,40,None))
 def test_strict_boundary(self):self.assertEqual(max_advance(90,2,1,40,0),50)
 def test_external_cost(self):self.assertEqual(max_advance(90,2,1,40,5),45)
 def test_unknown_amount(self):
  with self.assertRaises(ValueError):uint(None)
 def test_bool(self):
  with self.assertRaises(ValueError):uint(True)
 def test_overflow(self):
  with self.assertRaises(ValueError):uint(2**256)
 def test_negative(self):
  with self.assertRaises(ValueError):uint(-1)
 def test_exact_twelve(self):self.assertEqual(len(cases()),12)
 def test_unique_cases(self):self.assertEqual(len(set(c[0] for c in cases())),12)
 def ops(self):return [{'label':l,'request':{'from':'operator','value':'0x0','gas':'0x1'}} for l in OP_LABELS]
 def test_freeze(self):self.assertEqual(validate_operator(self.ops(),'operator'),validate_operator(copy.deepcopy(self.ops()),'operator'))
 def test_no_return_hidden(self):
  ops=self.ops()+[{'label':'return_unused_advance'}]
  with self.assertRaises(ValueError):validate_operator(ops,'operator')
 def test_no_provider_instructions(self):
  ops=self.ops();ops[0]['request']['from']='provider'
  with self.assertRaises(ValueError):validate_operator(ops,'operator')
 def test_no_value(self):
  ops=self.ops();ops[0]['request']['value']='0x1'
  with self.assertRaises(ValueError):validate_operator(ops,'operator')
 def test_unknown_margin(self):
  with self.assertRaises(ValueError):gate(True,0,None,1)
if __name__=='__main__':unittest.main()
