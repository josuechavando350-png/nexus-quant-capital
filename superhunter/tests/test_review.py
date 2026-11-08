"""Review orchestration unit tests. QA receipts here are explicitly fixtures.

The release check executes the complete suite separately; a unit fixture does
not establish that tests were run or authenticate any producer.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import quality, review
from superhunter.local_lab import execute_local
from superhunter.fuzz_lab import execute as execute_fuzz
from superhunter.safe_io import canonical, strict_json, write_new_bundle


class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lab_files = execute_local()
        cls.fuzz_files = execute_fuzz(seed=42, cases=2)

    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.qa,self.lab,self.fuzz=(self.root/n for n in ('qa','lab','fuzz'))
        self.snapshot=quality.source_snapshot()
        names=set(quality.REQUIRED_TESTS)
        for item in review.milestones()['items']:
            names.update(item['tests'])
        from superhunter.platform import _test_inventory
        names=sorted(set(_test_inventory()) | names)
        self.receipt={'schema_version':1,'sources_before':self.snapshot,'sources_after':self.snapshot,
                      'discovered':names,'tests':[{'id':n,'outcome':'PASS'} for n in names],
                      'tests_run':len(names),'failures':0,'errors':0,'skipped':0,
                      'expected_failures':0,'unexpected_successes':0}
        self._write_qa()
        write_new_bundle(self.lab,self.lab_files)
        write_new_bundle(self.fuzz,self.fuzz_files)
        self.out=self.root/'review'

    def _write_qa(self):
        result=quality.assess(self.receipt,self.snapshot)
        write_new_bundle(self.qa,{'receipt.json':canonical(self.receipt),'quality.json':canonical(result),
            'source-snapshot.json':canonical(self.snapshot),
            'CHECKLIST.md':quality.checklist(quality.catalog(),result).encode(),
            'tests.log':b'UNIT TEST FIXTURE ONLY. NOT AN EXECUTION LOG.\n'})

    def make(self):
        return review.create_review(self.qa,self.lab,self.fuzz,self.out)

    def alter(self,root,name,fn):
        obj=strict_json((root/name).read_bytes());fn(obj)
        raw=canonical(obj);(root/name).write_bytes(raw)
        marker=strict_json((root/'COMPLETE.json').read_bytes())
        marker['sha256'][name]=hashlib.sha256(raw).hexdigest()
        (root/'COMPLETE.json').write_bytes(canonical(marker))

    def test_review_recalculates_three_sections(self):
        result=self.make()
        self.assertEqual(result['status'],'LOCAL_REVIEW_PASS')
        self.assertEqual(result['synthetic_cases'],{'fixed':5,'fuzz':2})
        self.assertEqual(result['milestones'],{'bounded':12,'partial':3,'pending':12})
        self.assertEqual(result['capabilities_complete'],0)
        self.assertFalse(result['producer_authenticated'])
        self.assertFalse(result['vulnerability_confirmed'])

    def test_self_contained_verification(self):
        result=self.make()
        # Verification must not need the original input directories.
        import shutil
        for p in (self.qa,self.lab,self.fuzz):shutil.rmtree(p)
        self.assertEqual(review.verify_review(self.out),result)

    def test_all_77_ids_preserved(self):
        self.make()
        plan=strict_json((self.out/'milestones.json').read_bytes())
        caps=strict_json((self.out/'capabilities.json').read_bytes())
        self.assertEqual([i['id'] for i in plan['items']],[f'B{i:02d}' for i in range(1,28)])
        self.assertEqual([i['id'] for i in caps['items']],list(range(1,51)))

    def test_resealed_report_cannot_claim_production(self):
        self.make()
        self.alter(self.out,'review.json',lambda v:v.update(production_certified=True))
        with self.assertRaisesRegex(ValueError,'recomputed facts'):
            review.verify_review(self.out)

    def test_resealed_test_count_rejected(self):
        self.make()
        self.alter(self.out,'review.json',lambda v:v.update(unit_tests=99999))
        with self.assertRaisesRegex(ValueError,'recomputed facts'):
            review.verify_review(self.out)

    def test_resealed_evidence_mismatch_rejected(self):
        self.make()
        self.alter(self.out,'lab--lab-result.json',lambda v:v.update(cases_passed=99))
        with self.assertRaises(ValueError):review.verify_review(self.out)

    def test_missing_milestone_test_blocks_review(self):
        plan=review.milestones()
        plan['items'][0]['tests']=['test_unknown.not_executed']
        with patch('superhunter.review.milestones',return_value=plan),self.assertRaisesRegex(ValueError,'lacks an executed'):
            self.make()
        self.assertFalse(self.out.exists())

    def test_missing_evidence_section_rejected(self):
        (self.fuzz/'COMPLETE.json').unlink()
        with self.assertRaises(OSError):self.make()
        self.assertFalse(self.out.exists())

    def test_stale_qa_source_rejected(self):
        self.alter(self.qa,'source-snapshot.json',lambda v:v.update({'old.py':'0'*64}))
        with self.assertRaisesRegex(ValueError,'current package'):self.make()
        self.assertFalse(self.out.exists())

    def test_failed_qa_rejected(self):
        import shutil
        shutil.rmtree(self.qa)
        self.receipt['tests'][0]['outcome']='FAIL';self.receipt['failures']=1
        self._write_qa()
        with self.assertRaisesRegex(ValueError,'QA has not passed'):self.make()
        self.assertFalse(self.out.exists())

    def test_tampered_graph_rejected(self):
        self.alter(self.lab,'proof-graph.json',lambda v:v.update(production_finding=True))
        with self.assertRaisesRegex(ValueError,'causal graph'):self.make()

    def test_corrupt_output_digest_rejected(self):
        self.make();(self.out/'REVIEW.md').write_text('different')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):review.verify_review(self.out)

    def test_resealed_html_rejected(self):
        self.make();raw=b'<script>not allowed</script>'
        (self.out/'index.html').write_bytes(raw)
        marker=strict_json((self.out/'COMPLETE.json').read_bytes())
        marker['sha256']['index.html']=hashlib.sha256(raw).hexdigest()
        (self.out/'COMPLETE.json').write_bytes(canonical(marker))
        with self.assertRaisesRegex(ValueError,'rendered report'):review.verify_review(self.out)

    def test_html_escapes_all_untrusted_markup(self):
        raw=review.render_html('<script>alert(1)</script><img src="https://x.invalid">')
        self.assertIn(b'&lt;script&gt;',raw)
        self.assertNotIn(b'<script>',raw)
        self.assertNotIn(b'<img ',raw)
        self.assertIn(b"default-src 'none'",raw)

    def test_existing_output_never_overwritten(self):
        self.make();before=(self.out/'COMPLETE.json').read_bytes()
        with self.assertRaises(FileExistsError):self.make()
        self.assertEqual((self.out/'COMPLETE.json').read_bytes(),before)

    def test_private_output_permissions(self):
        self.make()
        self.assertEqual(self.out.stat().st_mode & 0o777,0o700)
        for p in self.out.iterdir():self.assertEqual(p.stat().st_mode & 0o777,0o600)

    def test_missing_completion_blocks_verification(self):
        self.make();(self.out/'COMPLETE.json').unlink()
        with self.assertRaises(OSError):review.verify_review(self.out)

    def test_resealed_context_change_rejected(self):
        self.make()
        self.alter(self.out,'milestones.json',lambda v:v['items'][3].update(status='BOUNDED_IMPLEMENTED'))
        with self.assertRaisesRegex(ValueError,'context differs'):review.verify_review(self.out)

    def test_milestone_removal_rejected(self):
        data=review.milestones();data['items'].pop()
        with patch('superhunter.review.read_artifact',return_value=canonical(data)),self.assertRaises(ValueError):
            review.milestones()

    def test_undocumented_milestone_completion_rejected(self):
        data=review.milestones();data['items'][0]['status']='COMPLETE'
        with patch('superhunter.review.read_artifact',return_value=canonical(data)),self.assertRaises(ValueError):
            review.milestones()

    def test_passing_unit_test_without_evidence_ref_is_not_completion(self):
        data=review.milestones();data['items'][0]['tests']=[]
        with patch('superhunter.review.read_artifact',return_value=canonical(data)),self.assertRaises(ValueError):
            review.milestones()

    def test_boolean_count_not_integer(self):
        self.make();self.alter(self.out,'review.json',lambda v:v.update(unit_tests=True))
        with self.assertRaises(ValueError):review.verify_review(self.out)

    def test_no_network_or_process_execution(self):
        with patch('socket.socket',side_effect=AssertionError('no network')), \
             patch('subprocess.run',side_effect=AssertionError('no child process')):
            self.assertEqual(self.make()['status'],'LOCAL_REVIEW_PASS')

    def test_cli_creates_and_verifies_review(self):
        # Direct CLI entrypoint: actual file IO and all three verifier functions.
        args=['review','--qa',str(self.qa),'--lab',str(self.lab),'--fuzz',str(self.fuzz),'--out',str(self.out)]
        with patch('sys.stdout',new_callable=io.StringIO) as stream:
            self.assertEqual(review.main(args),0)
        self.assertFalse(json.loads(stream.getvalue())['vulnerability_confirmed'])
        with patch('sys.stdout',new_callable=io.StringIO):
            self.assertEqual(review.main(['verify-review','--bundle',str(self.out)]),0)

    def test_cli_missing_bundle_returns_error(self):
        with patch('sys.stdout',new_callable=io.StringIO) as stream:
            self.assertEqual(review.main(['verify-review','--bundle',str(self.root/'absent')]),2)
        self.assertEqual(json.loads(stream.getvalue())['status'],'LOCAL_REVIEW_ERROR')

    def test_evidence_output_inside_repository_rejected(self):
        self.out=review.ROOT/'not-publishable'
        with self.assertRaisesRegex(ValueError,'outside the source checkout'):self.make()
        self.assertFalse(self.out.exists())

    def test_source_change_during_review_aborts(self):
        old=quality.source_snapshot
        calls=0
        def changing():
            nonlocal calls
            calls+=1
            v=old()
            if calls>2:v={**v,'modified.py':'0'*64}
            return v
        with patch('superhunter.quality.source_snapshot',side_effect=changing),self.assertRaisesRegex(ValueError,'source changed'):
            self.make()
        self.assertFalse(self.out.exists())


if __name__=='__main__':unittest.main()
