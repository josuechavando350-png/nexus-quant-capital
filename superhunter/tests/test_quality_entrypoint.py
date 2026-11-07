"""Entry-point parity using fabricated unit receipts, never execution evidence."""
from pathlib import Path
import json,subprocess,sys,tempfile,unittest
from superhunter import quality
from superhunter.safe_io import canonical,write_new_bundle


class QualityEntrypointTests(unittest.TestCase):
    def bundle(self,root,missing=False):
        snapshot=quality.source_snapshot();ids=list(quality.REQUIRED_TESTS)
        if missing:
            ids.remove('test_owned_slither_native.NativeEvidenceTests.test_replay_must_execute_three_new_cases')
        receipt={'schema_version':1,'sources_before':snapshot,'sources_after':snapshot,
            'discovered':ids,'tests':[{'id':i,'outcome':'PASS'} for i in ids],
            'tests_run':len(ids),'failures':0,'errors':0,'skipped':0,'expected_failures':0,'unexpected_successes':0}
        result=quality.assess(receipt,snapshot)
        write_new_bundle(root,{'receipt.json':canonical(receipt),'quality.json':canonical(result),
            'source-snapshot.json':canonical(snapshot),
            'CHECKLIST.md':quality.checklist(quality.catalog(),result).encode(),
            'tests.log':b'FABRICATED UNIT RECEIPT; NO QA EXECUTION OR AUTHENTICATION\n'})
        return result

    def entrypoints(self,root):
        rows=[]
        for module in ('superhunter.quality','superhunter'):
            result=subprocess.run([sys.executable,'-B','-m',module,'verify-check','--bundle',str(root)],
                cwd=quality.ROOT.parent,env={'LANG':'C.UTF-8','LC_ALL':'C.UTF-8'},
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
            self.assertEqual(result.stderr,b'')
            rows.append((result.returncode,json.loads(result.stdout)))
        return rows

    def test_direct_and_package_entrypoints_accept_the_same_unit_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'unit';expected=self.bundle(root)
            self.assertEqual(expected['status'],'LOCAL_QA_PASS')
            rows=self.entrypoints(root)
            self.assertEqual(rows[0],rows[1]);self.assertEqual(rows[0][0],0)
            self.assertEqual(rows[0][1]['source_digest'],expected['source_digest'])
            self.assertFalse(rows[0][1]['vulnerability_confirmed'])

    def test_missing_late_required_test_is_blocked_by_both_entrypoints(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'unit';expected=self.bundle(root,missing=True)
            self.assertEqual(expected['status'],'LOCAL_QA_BLOCKED')
            rows=self.entrypoints(root)
            self.assertEqual(rows[0],rows[1]);self.assertEqual(rows[0][0],1)
            self.assertEqual(rows[0][1]['status'],'LOCAL_QA_BLOCKED')
