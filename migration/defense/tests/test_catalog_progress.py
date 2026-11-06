import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.check_operational_catalog import validate


class CatalogProgressTests(unittest.TestCase):
    def setUp(self):
        package = Path(__file__).resolve().parents[1]
        self.value = json.loads((package/'docs/operational_catalog_100.json').read_text())
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for item in self.value['components']:
            if item['implementation']:
                destination = self.root/item['implementation']; destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(package/item['implementation'],destination)
        self.register = {'schema':'nqc-completion-register-v1','acceptances':[]}

    def reference(self,name,data):
        path = self.root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)
        return {'path':name,'sha256':hashlib.sha256(data).hexdigest()}

    def acceptance_fixture(self,identifier):
        item = next(x for x in self.value['components']+self.value['disciplines'] if x['id']==identifier)
        evidence = self.reference('docs/check.json',b'{"test_fixture":true}')
        report = {'schema':'nqc-catalog-acceptance-v1','id':identifier,
                  'catalog_requirement':item.get('acceptance',item.get('competency_check')),
                  'full_scope_accepted':True,'checks':[evidence]}
        ref = self.reference('docs/accepted.json',json.dumps(report).encode())
        self.register['acceptances'].append({'id':identifier,'report':ref})
        return item,report

    def test_partials_do_not_become_completion_or_effort_estimate(self):
        result = validate(self.value,self.root,self.register)
        self.assertEqual(result['progress']['completion_percent'],0)
        self.assertEqual(result['progress']['not_closed_percent'],100)
        self.assertEqual(result['progress']['components_with_implementation_percent'],result['bounded_partial_components'])

    def test_complete_status_requires_recorded_acceptance(self):
        item = next(x for x in self.value['components'] if x['status']=='bounded_partial'); item['status']='complete'
        with self.assertRaisesRegex(ValueError,'completion_status_disagrees'):
            validate(self.value,self.root,self.register)

    def test_acceptance_cannot_close_component_still_marked_partial(self):
        self.acceptance_fixture('C041')
        with self.assertRaisesRegex(ValueError,'completion_status_disagrees'):
            validate(self.value,self.root,self.register)

    def test_accepted_component_count_is_computed_from_consistent_evidence(self):
        item,_ = self.acceptance_fixture('C041'); item['status']='complete'; self.value['fully_completed_components']=1
        result = validate(self.value,self.root,self.register)
        self.assertEqual(result['progress']['closed_items'],1)
        self.assertEqual(result['progress']['completion_percent'],0.5)

    def test_discipline_specification_does_not_equal_recorded_acceptance(self):
        self.acceptance_fixture('D041')
        result = validate(self.value,self.root,self.register)
        self.assertEqual(result['fully_completed_disciplines'],1)
        self.assertEqual(result['progress']['discipline_completion_percent'],1)
        self.assertEqual(result['progress']['disciplines_specified_percent'],100)

    def test_changed_evidence_invalidates_completion_count(self):
        self.acceptance_fixture('D041'); (self.root/'docs/check.json').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'acceptance_digest'):
            validate(self.value,self.root,self.register)

    def test_duplicate_and_unknown_acceptances_rejected(self):
        self.acceptance_fixture('D041'); self.register['acceptances'] *= 2
        with self.assertRaisesRegex(ValueError,'completion_duplicate'):
            validate(self.value,self.root,self.register)
        self.register['acceptances'] = [{'id':'D999','report':{}}]
        with self.assertRaisesRegex(ValueError,'completion_id'):
            validate(self.value,self.root,self.register)

    def test_unrelated_requirement_cannot_be_counted_as_acceptance(self):
        _,report = self.acceptance_fixture('D041'); report['catalog_requirement']='unrelated'
        self.register['acceptances'][0]['report'] = self.reference('docs/accepted.json',json.dumps(report).encode())
        with self.assertRaisesRegex(ValueError,'completion_scope'):
            validate(self.value,self.root,self.register)

    def test_completion_reference_cannot_escape_package(self):
        self.register['acceptances'] = [{'id':'D041','report':{'path':'../outside','sha256':'0'*64}}]
        with self.assertRaisesRegex(ValueError,'acceptance_path'):
            validate(self.value,self.root,self.register)


if __name__ == '__main__':
    unittest.main()
