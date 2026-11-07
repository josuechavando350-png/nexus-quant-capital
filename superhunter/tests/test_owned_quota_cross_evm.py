"""Explicit synthetic unit inputs; actual engine acceptance runs separately."""
from contextlib import redirect_stdout,redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
import random
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from superhunter import owned_quota_cross_evm as cross,owned_quota_spec_worker as worker,quality
from superhunter import owned_quota_cases as cases
from superhunter.safe_io import canonical
from superhunter.tests.test_owned_quota_review import synthetic_execution


class QuotaCrossEVMTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root = Path(temp.name)
        self.digest = cross.sha(canonical(quality.source_snapshot()))
        self.geth = synthetic_execution();self.geth.update(source_digest=self.digest,
            solc_sha256=cross.quota.compiler.PIN['sha256'],geth_sha256=cross.quota.evm.PIN['sha256'])
        self.eels = {'profile':worker.PROFILE,'source_digest':self.digest,'engine':'execution-specs',
            'fork':'Cancun','solc_sha256':self.geth['solc_sha256'],'constructor_executions':12,
            'runtime_calls':228,'builds':deepcopy(self.geth['builds']),
            'rows':[{k:deepcopy(v) for k,v in r.items() if k not in ('state_root','stdout_sha256')}
                    for r in self.geth['rows']],
            'dependencies':{n:{k:p[k] for k in ('version','files','runtime_sha256')}
                            for n,p in cross.PINS.items()}}

    def assess(self):return cross.compare(self.geth,self.eels,self.digest)

    def make(self):
        with patch.object(cross.quota,'_run_worker',return_value=self.geth), \
             patch.object(cross,'_run_eels',return_value=self.eels):
            return cross.create(self.root/'bundle',self.root/'solc',self.root/'geth',self.digest)

    def verify(self):
        with patch.object(cross.quota,'_run_worker',return_value=self.geth), \
             patch.object(cross,'_run_eels',return_value=self.eels):
            return cross.verify(self.root/'bundle',self.root/'solc',self.root/'geth',self.digest)

    def reseal(self,name,change):
        root = self.root/'bundle'; obj = json.loads((root/name).read_bytes());change(obj)
        raw = canonical(obj);(root/name).write_bytes(raw)
        marker = json.loads((root/'COMPLETE.json').read_bytes());marker['sha256'][name] = cross.sha(raw)
        (root/'COMPLETE.json').write_bytes(canonical(marker))

    def test_six_cases_not_twelve_or_456_independent_samples(self):
        r = self.assess();self.assertEqual(r['known_cases'],6)
        self.assertEqual(r['runtime_calls_per_engine'],228)
        self.assertEqual(r['constructor_executions_per_engine'],12)
        self.assertEqual((r['counts']['tp'],r['counts']['tn'],r['counts']['fp'],r['counts']['fn']),(4,2,0,0))
        self.assertEqual(r['ablation_metrics']['status_only']['counts']['fn'],3)
        self.assertEqual(r['ablation_metrics']['state_only']['counts']['fn'],1)
        for key in ('blind_benchmark','generalization_established','vulnerability_confirmed',
                    'independent_producers_proved','gas_costs_compared','all_evm_semantics_certified'):
            self.assertIs(r[key],False)

    def test_each_changed_call_rejected(self):
        original = deepcopy(self.eels['rows'])
        for index in range(228):
            with self.subTest(call=index):
                self.eels['rows'] = deepcopy(original)
                self.eels['rows'][index]['observation']['after']['quota'] += 1
                with self.assertRaisesRegex(ValueError,'SEMANTICS_MISMATCH'):self.assess()

    def test_missing_duplicate_and_reordered_calls_rejected(self):
        original = deepcopy(self.eels['rows'])
        for rows in (original[:-1],original+[original[0]],list(reversed(original))):
            self.eels['rows'] = rows
            with self.assertRaisesRegex(ValueError,'SEMANTICS_MISMATCH'):self.assess()

    def test_revert_and_out_of_gas_cannot_be_relabelled(self):
        original = deepcopy(self.eels['rows'])
        for status in ('REVERTED','OUT_OF_GAS'):
            self.eels['rows'] = deepcopy(original)
            row = next(r for r in self.eels['rows'] if r['observation']['status'] == status)
            row['observation']['status'] = 'COMMITTED'
            with self.assertRaisesRegex(ValueError,'SEMANTICS_MISMATCH'):self.assess()

    def test_return_bytes_and_boolean_state_rejected(self):
        original = deepcopy(self.eels['rows'])
        for field,value in (('return_data','0x01'),('before',{'remaining':20,'distributed':False,'quota':5})):
            self.eels['rows'] = deepcopy(original);self.eels['rows'][0]['observation'][field] = value
            with self.assertRaisesRegex(ValueError,'SEMANTICS_MISMATCH'):self.assess()

    def test_compiled_bytecode_and_constructor_storage_must_match(self):
        original = deepcopy(self.eels['builds'])
        for key,value in (('creation_sha256','0'*64),('runtime_sha256','0'*64),('initial_state',{})):
            self.eels['builds'] = deepcopy(original);self.eels['builds'][0][key] = value
            with self.assertRaisesRegex(ValueError,'BUILD_MISMATCH'):self.assess()

    def test_engine_fork_dependency_and_source_identity_bound(self):
        original = deepcopy(self.eels)
        for key,value in (('engine','geth'),('fork','Prague'),('dependencies',{}),
                          ('source_digest','0'*64),('solc_sha256','0'*64)):
            self.eels = deepcopy(original);self.eels[key] = value
            with self.assertRaisesRegex(ValueError,'IDENTITY'):self.assess()

    def test_unpinned_native_tools_rejected(self):
        original = deepcopy(self.geth)
        for key in ('solc_sha256','geth_sha256'):
            self.geth = deepcopy(original);self.geth[key] = '0'*64
            with self.assertRaisesRegex(ValueError,'TOOL_IDENTITY'):self.assess()

    def test_claimed_counts_and_extra_fields_rejected(self):
        original = deepcopy(self.eels)
        for key,value in (('runtime_calls',True),('runtime_calls',227),('constructor_executions',13)):
            self.eels = deepcopy(original);self.eels[key] = value
            with self.assertRaisesRegex(ValueError,'COVERAGE'):self.assess()
        self.eels = deepcopy(original);self.eels['unreviewed'] = True
        with self.assertRaisesRegex(ValueError,'SCHEMA'):self.assess()

    def test_bundle_replays_and_preserves_existing_output(self):
        self.make();before = (self.root/'bundle/COMPLETE.json').read_bytes()
        self.assertEqual(self.verify()['status'],'OWNED_QUOTA_CROSS_EVM_REPLAY_VERIFIED')
        with self.assertRaisesRegex(ValueError,'NEW_PRIVATE'):self.make()
        self.assertEqual((self.root/'bundle/COMPLETE.json').read_bytes(),before)

    def test_resealed_false_report_fails_regeneration(self):
        self.make();self.reseal('comparison.json',lambda r:r.update(vulnerability_confirmed=True))
        with self.assertRaisesRegex(ValueError,'REPLAY_MISMATCH'):self.verify()

    def test_wrong_external_source_rejected_before_execution(self):
        self.make()
        with patch.object(cross,'_execute',side_effect=AssertionError('must not execute')):
            with self.assertRaisesRegex(ValueError,'EXTERNAL_SOURCE'):
                cross.verify(self.root/'bundle',self.root/'solc',self.root/'geth','0'*64)

    def test_raw_tamper_and_extra_artifact_rejected(self):
        self.make();p=self.root/'bundle/geth.json';original=p.read_bytes();p.write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'BUNDLE_HASH'):self.verify()
        p.write_bytes(original);(self.root/'bundle/extra').write_bytes(b'owned')
        with self.assertRaisesRegex(ValueError,'MANIFEST'):self.verify()

    def test_worker_rejects_source_before_loading_optional_dependencies(self):
        with patch.object(worker,'dependency_identity',side_effect=AssertionError('must not import')):
            with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):
                worker.execute_fixed(self.root/'solc','0'*64)

    def test_storage_decoder_matches_independent_integer_fields(self):
        rng = random.Random(194063)
        for _ in range(1000):
            values = [rng.randrange(65536) for _ in range(3)]
            word = values[0] | (values[1]<<16) | (values[2]<<32)
            self.assertEqual(worker.decode_word(word),dict(zip(('remaining','distributed','quota'),values)))
        for word in (-1,1<<48,True,1.0,'1'):
            with self.assertRaises(ValueError):worker.decode_word(word)

    def test_timeout_kills_process_group(self):
        from unittest.mock import MagicMock
        import signal
        from superhunter import owned_process
        proc=MagicMock();proc.pid=12345;proc.returncode=-9
        with patch.object(owned_process.subprocess,'Popen',return_value=proc), \
             patch.object(owned_process.os,'waitid',return_value=None), \
             patch.object(owned_process.os,'getpgid',return_value=12345), \
             patch.object(owned_process.os,'getsid',return_value=12345), \
             patch.object(owned_process.time,'monotonic',side_effect=[0,181]), \
             patch.object(owned_process.os,'killpg') as kill:
            with self.assertRaisesRegex(ValueError,'TIMEOUT'):cross._run_eels(self.root/'solc',self.digest)
            kill.assert_called_once_with(proc.pid,signal.SIGKILL)
        proc.wait.assert_called_once_with()

    def test_cli_cannot_accept_a_target_or_disclose_private_path(self):
        output=io.StringIO()
        with redirect_stderr(output):
            with self.assertRaises(SystemExit) as stopped:
                cross.main(['compare-owned-quota-engines','--solc','owned','--evm','owned',
                    '--source-digest',self.digest,'--out',str(self.root/'out'),'--target','private-target'])
        self.assertEqual(stopped.exception.code,2);self.assertNotIn('private-target',output.getvalue())
        output=io.StringIO()
        with redirect_stdout(output):
            result=cross.main(['compare-owned-quota-engines','--solc','/private-solc',
                '--evm','/private-geth','--source-digest','0'*64,'--out',str(self.root/'out')])
        self.assertEqual(result,2);self.assertNotIn('/private-',output.getvalue())


if __name__ == '__main__':
    unittest.main()
