import copy
from fractions import Fraction
import gzip
import io
import json
import unittest
import zipfile
import check_evidence as check
import corpus_scan


class ChangedSource:
    def __init__(self,source,name,data):self.source,self.name,self.data=source,name,data;self.manifest=source.manifest
    def json(self,name):return copy.deepcopy(self.data) if name==self.name else self.source.json(name)
    def __getattr__(self,name):return getattr(self.source,name)


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=check.core.Sources(check.MANIFEST);cls.result=check.analyze(cls.s)

    def test_same_provider_and_historical_derivatives_do_not_authenticate_index(self):
        r=self.result
        self.assertEqual(r['provenance']['same_event_provider_count'],1)
        self.assertTrue(r['provenance']['earlier_selection_uses_identical_page_hashes'])
        self.assertIsNone(r['authentication']['authenticated_index'])
        self.assertEqual(r['classification'],'EVIDENCIA_INSUFICIENTE')

    def test_reverse_conflict_is_not_hidden_by_duplicate_merge(self):
        value=self.s.json('reverse');value['response']['data']['marketTransactions']['items'][51]['data']['repaidAssets']='1'
        with self.assertRaisesRegex(ValueError,'observation conflict'):
            check.analyze(ChangedSource(self.s,'reverse',value))

    def test_other_chain_cannot_supply_missing_identity(self):
        row=self.s.json('forward')['response']['data']['marketTransactions']['items'][91]
        row['chain']['id']=4663
        with self.assertRaisesRegex(ValueError,'chain'):check.facts(row)

    def test_null_receipt_supplies_no_zero_gas(self):
        self.assertIsNone(self.result['economics']['gas_used'])
        self.assertIsNone(self.result['economics']['inclusion_payment'])
        self.assertIsNone(self.result['authentication']['raw_receipt'])

    def test_new_receipt_cannot_be_silently_ignored(self):
        value=self.s.json('receipt');value['response']['result']={'status':'0x1','transactionHash':check.TX}
        with self.assertRaisesRegex(ValueError,'new primary evidence'):
            check.analyze(ChangedSource(self.s,'receipt',value))

    def test_necessary_sale_threshold_is_not_a_price_or_profit(self):
        e=self.result['economics'];condition=e['necessary_sale_condition']
        self.assertEqual(condition['strict_positive_output_min_raw_before_other_costs'],'590976235877976339')
        self.assertEqual(Fraction(condition['debt_cover_average_WETH_per_pufETH_fraction']),Fraction(590976235877976338,569144086683595914))
        self.assertIsNone(condition['observed_or_executable_price'])
        self.assertIsNone(e['net_upper_bound']);self.assertIsNone(e['net_capturable_by_NQC'])
        self.assertFalse(condition['sufficient_for_net_profit'])

    def test_source_call_order_does_not_bind_historical_runtime(self):
        semantics=self.result['financing_semantics']
        self.assertTrue(semantics['collateral_then_optional_callback_then_repayment'])
        self.assertFalse(semantics['candidate_runtime_bound_to_source'])
        raw=self.s.raw('morpho_source').decode()
        statements=semantics['source_statements']
        raw=raw.replace(statements[0],'PLACEHOLDER').replace(statements[2],statements[0]).replace('PLACEHOLDER',statements[2])
        with self.assertRaisesRegex(ValueError,'settlement order'):check.source_order(raw)

    def test_nested_container_and_binary_identifiers_are_searched(self):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as z:z.writestr('sample.gz',gzip.compress(check.TX.encode()+bytes.fromhex(check.TX[2:])+(26104570).to_bytes(4,'big')))
        hits=[];skipped=[];stats={'objects_or_members_scanned':0}
        corpus_scan.scan_bytes(buffer.getvalue(),'TEST_ONLY.zip',hits,skipped,stats)
        self.assertFalse(skipped)
        self.assertTrue(any('transaction_binary' in h['matches'] and 'block_binary' in h['matches'] for h in hits))

    def test_unreviewed_corpus_hit_blocks_absence_conclusion(self):
        corpus=json.loads((check.HERE/'evidence/corpus.json').read_text())
        reviews=json.loads((check.HERE/'HIT_REVIEW.json').read_text())['hits']
        reviews.pop()
        with self.assertRaisesRegex(ValueError,'unreviewed'):
            check.review_corpus(corpus,reviews,self.s)


if __name__=='__main__':unittest.main()
