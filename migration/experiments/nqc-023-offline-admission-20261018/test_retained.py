"""Synthetic unit controls of the receipt auditor, not Ethereum transactions."""
import copy,json,unittest
from audit_retained import audit_case,digest,unique_json,unpack

class RetainedTests(unittest.TestCase):
 def fixture(self):
  init={'op':{'ETH':0},'builder':{'ETH':100}};balances=copy.deepcopy(init);txs=[];ops=[]
  for i,(label,sender,to,value) in enumerate([('one_prepended_advance','builder','op',20),('nqc_adapter','op','contract',0),('nqc_executor','op','contract',0),('liquidate','op','contract',0)]):
   req={'from':sender,'to':to,'value':hex(value),'gas':'0x2','maxFeePerGas':'0x2','maxPriorityFeePerGas':'0x1'}
   before=copy.deepcopy(balances);balances[sender]['ETH']-=2+value;balances['builder']['ETH']+=1
   if value:balances[to]['ETH']+=value
   tx={'label':label,'request':req,'receipt':{'transactionHash':hex(i+1),'blockHash':'block','blockNumber':'0x1','transactionIndex':hex(i),'gasUsed':'0x1','effectiveGasPrice':'0x2','status':'0x1'},'block':{'hash':'block','number':'0x1','baseFeePerGas':'0x1','miner':'builder'},'trace':{'type':'CALL','from':sender,'to':to,'value':hex(value)},'before':before,'after':copy.deepcopy(balances)}
   txs.append(tx)
   if sender=='op':ops.append({'label':label,'request':req})
  h=digest(json.dumps(ops,sort_keys=True,separators=(',',':')).encode())
  plan={'revertingTxHashes':[],'droppingTxHashes':[],'signatures_created':0,'real_rpc_payload':False,'operator_requests':ops,'operator_sha256':h}
  r={'actors':{'nqc_sender_and_beneficiary':'op','simulated_builder':'builder'},'initial':{'balances':init},'final':{'balances':balances},'transactions':txs}
  s={'case':'SYNTHETIC_UNIT_ONLY','provider_advance_wei':20,'receipt_count':4,'gas_total':4,'builder_cash_after_observed_payout':-18,'residual_financing':14,'operator_sha256':h}
  return r,plan,s
 def test_fixture_native_conservation(self):
  r,p,s=self.fixture();a=audit_case(r,p,s);self.assertEqual(a['receipts'],4);self.assertTrue(a['mandatory_operator_success_observed'])
 def test_wrong_block(self):
  r,p,s=self.fixture();r['transactions'][0]['block']['hash']='other'
  with self.assertRaises(ValueError):audit_case(r,p,s)
 def test_duplicate_receipt(self):
  r,p,s=self.fixture();r['transactions'][1]['receipt']['transactionHash']='0x1'
  with self.assertRaises(ValueError):audit_case(r,p,s)
 def test_corrupt_balance(self):
  r,p,s=self.fixture();r['final']['balances']['op']['ETH']+=1
  with self.assertRaises(ValueError):audit_case(r,p,s)
 def test_corrupt_operator_identity(self):
  r,p,s=self.fixture();p['operator_sha256']='not-the-digest'
  with self.assertRaises(ValueError):audit_case(r,p,s)
 def test_invalid_prefix_reserve(self):
  r,p,s=self.fixture();r['transactions'][1]['request']['gas']='0xffff'
  with self.assertRaises(ValueError):audit_case(r,p,s)
 def test_reverted_nested_call_ignored(self):
  r,p,s=self.fixture();r['transactions'][-1]['trace']['calls']=[{'type':'CALL','error':'execution reverted','from':'op','to':'builder','value':'0x100'}]
  self.assertEqual(audit_case(r,p,s)['receipts'],4)
 def test_unknown_export_is_not_valid(self):
  with self.assertRaises(ValueError):unpack('NQC021_EXPORT_META {}\nNQC021_EXPORT_END\n')
 def test_ambiguous_file_suffix_rejected(self):
  with self.assertRaises(ValueError):unique_json({'a/test.json':b'{}','b/test.json':b'{}'},'test.json')
if __name__=='__main__':unittest.main(verbosity=2)
