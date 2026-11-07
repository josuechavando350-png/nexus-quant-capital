"""Synthetic adapter checks; separate native runs establish actual EELS use."""
from contextlib import ExitStack,redirect_stderr
from copy import deepcopy
import hashlib
from importlib.metadata import PackageNotFoundError
import io
import json
from pathlib import Path,PurePosixPath
import random
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from superhunter import owned_cross_evm as cross,owned_spec_evm_worker as spec
from superhunter import owned_cross_evm_worker as previous,native_doctor as doctor,quality
from superhunter import evm_pause_family as pause,evm_access_family as access
from superhunter.safe_io import canonical
from superhunter.tests.test_owned_mutation_evaluation import fake_native


class SpecEVMTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.digest = cross.sha(canonical(quality.source_snapshot()))
        self.p,self.a = fake_native('pause',self.digest),fake_native('access',self.digest)
        for family,module,record in (('pause',pause,self.p),('access',access,self.a)):
            for variant in module.VARIANTS:
                for codegen in module.CODEGEN:
                    for key in ('input_sha256','output_sha256','creation_sha256'):
                        record['builds'][variant][codegen][key] = cross.sha((family+variant+codegen+key).encode())
        rows,builds = cross._geth_rows(self.p,self.a)
        self.second = {'profile':spec.PROFILE,'source_digest':self.digest,
            'engine':'execution-specs','fork':'Cancun','rows':deepcopy(rows),
            'builds':deepcopy(builds),'runtime_calls':144,'constructor_executions':8,
            'dependencies':{name:{k:pin[k] for k in ('version','files','runtime_sha256')}
                            for name,pin in spec.PINS.items()}}

    def assess(self):
        return cross.compare(self.p,self.a,self.second,self.digest,'execution-specs')

    def make(self):
        with patch.object(cross.score,'_run_native',return_value=(self.p,self.a)), \
             patch.object(cross,'_run_python',return_value=self.second):
            return cross.create(self.root/'bundle',self.root/'solc',self.root/'evm',
                                self.digest,'execution-specs')

    def test_fixed_eels_cases_are_not_extra_samples(self):
        r = self.assess()
        self.assertEqual(r['second_evm'],'execution-specs')
        self.assertEqual(r['known_cases'],4)
        self.assertEqual(r['implementation_count'],2)
        self.assertEqual((r['counts']['tp'],r['counts']['tn'],r['counts']['fp'],r['counts']['fn']),
                         (2,2,0,0))
        self.assertFalse(r['blind_benchmark'])
        self.assertFalse(r['vulnerability_confirmed'])

    def test_other_engine_label_and_dependency_lock_rejected(self):
        original = deepcopy(self.second)
        self.second['engine'] = 'py-evm'
        with self.assertRaisesRegex(ValueError,'IDENTITY'): self.assess()
        self.second = deepcopy(original)
        self.second['dependencies'] = {name:{k:p[k] for k in ('version','files','runtime_sha256')}
                                       for name,p in cross.PINS.items()}
        with self.assertRaisesRegex(ValueError,'IDENTITY'): self.assess()

    def test_semantic_drift_or_incomplete_execution_rejected(self):
        self.second['rows'][0]['after']['remaining'] += 1
        with self.assertRaisesRegex(ValueError,'SEMANTICS_MISMATCH'): self.assess()
        self.second['rows'].pop()
        with self.assertRaisesRegex(ValueError,'SEMANTICS_MISMATCH'): self.assess()

    def test_wrong_selected_engine_rejected_before_execution(self):
        self.make()
        with patch.object(cross,'_execute',side_effect=AssertionError('Must not execute')):
            with self.assertRaisesRegex(ValueError,'WRONG_SECOND_EVM_REFERENCE'):
                cross.verify(self.root/'bundle',self.root/'solc',self.root/'evm',self.digest)

    def test_verifier_routes_to_exact_selected_engine(self):
        self.make()
        with patch.object(cross.score,'_run_native',return_value=(self.p,self.a)), \
             patch.object(cross,'_run_python',return_value=self.second) as run:
            r = cross.verify(self.root/'bundle',self.root/'solc',self.root/'evm',
                             self.digest,'execution-specs')
        self.assertEqual(r['status'],'OWNED_CROSS_EVM_REPLAY_VERIFIED')
        run.assert_called_once_with(self.root/'solc',self.digest,'execution-specs')

    def test_unknown_backend_cannot_launch_worker(self):
        with patch.object(cross.subprocess,'Popen',side_effect=AssertionError('Must not launch')):
            with self.assertRaisesRegex(ValueError,'UNKNOWN_SECOND_EVM'):
                cross._run_python(self.root/'solc',self.digest,'unreviewed-backend')

    def test_wrong_source_rejected_before_dependency_import(self):
        with patch.object(spec,'dependency_identity',side_effect=AssertionError('Must not import')):
            with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):
                spec.execute_fixed(self.root/'solc','0'*64)

    def test_installed_dependency_bytes_are_checked(self):
        path = self.root/'spec_fixture.py'; path.write_bytes(b'own package fixture')
        hashes = {'spec_fixture.py':hashlib.sha256(path.read_bytes()).hexdigest()}
        digest = hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        pins = {'fixture':{'version':'1','files':1,'runtime_sha256':digest}}
        dist = SimpleNamespace(version='1',files=[PurePosixPath('spec_fixture.py')],locate_file=lambda _:path)
        with patch.object(spec,'PINS',pins),patch.object(spec,'distribution',return_value=dist):
            self.assertEqual(spec.dependency_identity()['fixture']['runtime_sha256'],digest)
            path.write_bytes(b'modified package fixture')
            with self.assertRaisesRegex(ValueError,'DEPENDENCY_BYTES'): spec.dependency_identity()

    def test_missing_dependency_remains_blocked(self):
        with patch.object(spec,'distribution',side_effect=PackageNotFoundError('owned-fixture')):
            with self.assertRaises(PackageNotFoundError): spec.dependency_identity()
            self.assertEqual(doctor._second_evm_packages('execution-specs')['status'],'BLOCKED')

    def test_independent_storage_decoders_agree(self):
        rng = random.Random(73017)
        for _ in range(1000):
            for family,width in (('pause',40),('access',192)):
                word = rng.getrandbits(width)
                self.assertEqual(spec.decode_word(word,family),previous.decode_word(word,family))

    def test_storage_decoder_rejects_high_bits_and_wrong_types(self):
        for word,family in ((1<<40,'pause'),(1<<192,'access'),(-1,'pause'),(False,'pause'),
                            (1.0,'access'),(0,'unreviewed-family')):
            with self.assertRaises(ValueError): spec.decode_word(word,family)

    def test_selected_profile_does_not_require_other_environment(self):
        with ExitStack() as stack:
            for name in doctor.CHECKS:
                if name in ('solc','geth'): continue
                stack.enter_context(patch.object(doctor,'_'+name,
                    return_value=doctor.result(name != 'qa_packages','CONTROL')))
            stack.enter_context(patch.object(doctor,'_tool',return_value=doctor.result(True,'CONTROL')))
            chosen = doctor.diagnose(self.root/'solc',self.root/'evm',
                profile='owned_cross_evm',second_engine='execution-specs')
            every = doctor.diagnose(self.root/'solc',self.root/'evm',second_engine='execution-specs')
        self.assertEqual(chosen['status'],'LAB_PREREQUISITES_READY')
        self.assertFalse(chosen['prerequisites']['qa'])
        self.assertEqual(chosen['second_evm'],'execution-specs')
        self.assertEqual(every['status'],'LAB_PREREQUISITES_BLOCKED')

    def test_unreviewed_profile_rejected(self):
        with self.assertRaisesRegex(ValueError,'UNKNOWN_LAB_PROFILE'):
            doctor.diagnose(self.root/'solc',self.root/'evm',profile='external-target')

    def test_cli_rejects_unreviewed_engine_without_echo(self):
        output = io.StringIO()
        with redirect_stderr(output):
            with self.assertRaises(SystemExit) as stopped:
                cross.main(['compare-owned-evm-engines','--second-engine','/private-plugin',
                    '--solc','owned-solc','--evm','owned-evm','--source-digest',self.digest,
                    '--out',str(self.root/'output')])
        self.assertEqual(stopped.exception.code,2)
        self.assertNotIn('/private-plugin',output.getvalue())


if __name__ == '__main__':
    unittest.main()
