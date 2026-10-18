import copy, sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'source'))
import diagnose_identity as d
import read_fluid as r
class Identity(unittest.TestCase):
    def setUp(self):
        self.head={'number':hex(r.NUMBER+100),'timestamp':hex(1791983495),'hash':'0x'+'1'*64}
        self.parent={'number':hex(r.NUMBER),'timestamp':hex(1791983483),'hash':r.PARENT}
        self.receipt={'transactionHash':r.TX1,'blockHash':r.BLOCK,'blockNumber':hex(r.NUMBER+1),'transactionIndex':'0x1'}
    def test_complete_identity_is_not_profit(self):
        x=d.assess(self.head,self.parent,self.receipt)
        self.assertEqual(x['status'],'IDENTITIES_MATCH_VIA_NUMBER_AND_RECEIPT_NO_QUOTE')
        self.assertFalse(x['commercial_admission']);self.assertFalse(x['new_nqc_profit_proven'])
    def test_lower_head_is_not_proof_history_nonexistent(self):
        self.head['number']=hex(r.NUMBER-100)
        self.assertEqual(d.assess(self.head,None,None)['status'],'PROVIDER_REPORTED_HEAD_BELOW_REQUESTED_HISTORY')
    def test_nulls_with_sufficient_head_are_unavailable(self):
        self.assertEqual(d.assess(self.head,None,None)['status'],'HISTORICAL_IDENTITY_STILL_UNAVAILABLE_OR_PARTIAL')
    def test_conflicting_parent_is_not_silently_replaced(self):
        self.parent['hash']='0x'+'a'*64
        x=d.assess(self.head,self.parent,self.receipt)
        self.assertEqual(x['status'],'CONFLICT_WITH_SAVED_IDENTIFIERS_SINGLE_PROVIDER')
        self.assertEqual(x['saved_parent_hash'],r.PARENT);self.assertFalse(x['historical_state_substituted'])
    def test_wrong_requested_number_rejected(self):
        self.parent['number']=hex(r.NUMBER-1)
        with self.assertRaises(r.StopRead): d.assess(self.head,self.parent,self.receipt)
    def test_foreign_receipt_rejected(self):
        self.receipt['transactionHash']='0x'+'b'*64
        with self.assertRaises(r.StopRead): d.assess(self.head,self.parent,self.receipt)
