"""Synthetic unit records; actual two-engine acceptance is run separately."""
from copy import deepcopy
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import py_compile
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from superhunter import owned_cross_evm as cross, owned_cross_evm_worker as worker, quality
from superhunter import evm_pause_family as pause, evm_access_family as access
from superhunter.safe_io import canonical
from superhunter.tests.test_owned_mutation_evaluation import fake_native


class CrossEVMTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.digest = cross.sha(canonical(quality.source_snapshot()))
        self.p = fake_native('pause', self.digest)
        self.a = fake_native('access', self.digest)
        for family, module, result in (('pause', pause, self.p), ('access', access, self.a)):
            for variant in module.VARIANTS:
                for codegen in module.CODEGEN:
                    record = result['builds'][variant][codegen]
                    for key in ('input_sha256','output_sha256','creation_sha256'):
                        record[key] = cross.sha((family+variant+codegen+key).encode())
        rows, builds = cross._geth_rows(self.p, self.a)
        self.second = {'profile':worker.PROFILE,'source_digest':self.digest,
            'engine':'py-evm','fork':'Cancun','rows':deepcopy(rows),'builds':deepcopy(builds),
            'runtime_calls':144,'constructor_executions':8,
            'dependencies':{n:{k:p[k] for k in ('version','files','runtime_sha256')}
                            for n,p in cross.PINS.items()}}

    def assess(self):
        return cross.compare(self.p, self.a, self.second, self.digest)

    def run_create(self):
        with patch.object(cross.score, '_run_native', return_value=(self.p,self.a)), \
             patch.object(cross, '_run_python', return_value=self.second):
            return cross.create(self.root/'result', self.root/'solc', self.root/'evm', self.digest)

    def run_verify(self):
        with patch.object(cross.score, '_run_native', return_value=(self.p,self.a)), \
             patch.object(cross, '_run_python', return_value=self.second):
            return cross.verify(self.root/'result', self.root/'solc', self.root/'evm', self.digest)

    def reseal(self, filename, change):
        root = self.root/'result'
        path = root/filename
        obj = json.loads(path.read_bytes()); change(obj)
        raw = canonical(obj); path.write_bytes(raw)
        marker = json.loads((root/'COMPLETE.json').read_bytes())
        marker['sha256'][filename] = cross.sha(raw)
        (root/'COMPLETE.json').write_bytes(canonical(marker))

    def test_matching_known_cases_not_extra_samples(self):
        report = self.assess()
        self.assertEqual(report['known_cases'], 4)
        self.assertEqual(report['runtime_calls_per_engine'], 144)
        self.assertEqual(report['counts']['tp'], 2)
        self.assertEqual(report['counts']['tn'], 2)
        for key in ('blind_benchmark','generalization_established','vulnerability_confirmed',
                    'independent_producers_proved','gas_costs_compared','all_evm_semantics_certified'):
            self.assertIs(report[key], False)

    def test_any_single_call_change_rejected(self):
        original = deepcopy(self.second['rows'])
        for index in range(144):
            with self.subTest(call=index):
                self.second['rows'] = deepcopy(original)
                self.second['rows'][index]['after']['remaining'] += 1
                with self.assertRaisesRegex(ValueError, 'SEMANTICS_MISMATCH'):
                    self.assess()

    def test_reversion_cannot_be_relabelled_success(self):
        row = next(r for r in self.second['rows'] if r['status'] == 'REVERTED')
        row['status'] = 'COMMITTED'
        with self.assertRaisesRegex(ValueError, 'SEMANTICS_MISMATCH'): self.assess()

    def test_out_of_gas_cannot_be_relabelled_revert(self):
        row = next(r for r in self.second['rows'] if r['status'] == 'OUT_OF_GAS')
        row['status'] = 'REVERTED'
        with self.assertRaisesRegex(ValueError, 'SEMANTICS_MISMATCH'): self.assess()

    def test_drop_duplicate_and_reorder_calls_rejected(self):
        original = deepcopy(self.second['rows'])
        for rows in (original[:-1], original+[original[0]], list(reversed(original))):
            self.second['rows'] = rows
            with self.assertRaisesRegex(ValueError, 'SEMANTICS_MISMATCH'): self.assess()

    def test_bool_storage_does_not_equal_integer_storage(self):
        self.second['rows'][0]['before']['paused'] = False
        with self.assertRaisesRegex(ValueError, 'SEMANTICS_MISMATCH'): self.assess()

    def test_wrong_return_data_rejected(self):
        self.second['rows'][0]['return_data'] = '0x01'
        with self.assertRaisesRegex(ValueError, 'SEMANTICS_MISMATCH'): self.assess()

    def test_wrong_bytecode_or_constructor_state_rejected(self):
        original = deepcopy(self.second['builds'])
        for key, value in (('runtime_sha256','f'*64), ('initial_state',{})):
            self.second['builds'] = deepcopy(original)
            self.second['builds'][0][key] = value
            with self.assertRaisesRegex(ValueError, 'BUILD_MISMATCH'): self.assess()

    def test_engine_fork_source_and_dependency_identity_bound(self):
        original = deepcopy(self.second)
        for key, value in (('engine','geth'),('fork','Prague'),('source_digest','0'*64),
                           ('dependencies',{})):
            self.second = deepcopy(original); self.second[key] = value
            with self.assertRaisesRegex(ValueError, 'IDENTITY'): self.assess()

    def test_extra_claim_and_fractional_count_rejected(self):
        self.second['vulnerability_confirmed'] = True
        with self.assertRaisesRegex(ValueError, 'SCHEMA'): self.assess()
        del self.second['vulnerability_confirmed']
        self.second['runtime_calls'] = 144.0
        with self.assertRaisesRegex(ValueError, 'COVERAGE'): self.assess()

    def test_create_then_reexecute_both_producers(self):
        self.assertEqual(self.run_create()['status'], 'OWNED_CROSS_EVM_CREATED')
        with patch.object(cross.score, '_run_native', return_value=(self.p,self.a)) as geth, \
             patch.object(cross, '_run_python', return_value=self.second) as second:
            self.assertEqual(cross.verify(self.root/'result',self.root/'solc',self.root/'evm',
                self.digest)['status'], 'OWNED_CROSS_EVM_REPLAY_VERIFIED')
            geth.assert_called_once(); second.assert_called_once()

    def test_resealed_result_cannot_claim_success(self):
        self.run_create()
        self.reseal('comparison.json', lambda r:r.update(vulnerability_confirmed=True))
        with self.assertRaisesRegex(ValueError, 'REPLAY_MISMATCH'): self.run_verify()

    def test_resealed_saved_execution_changed_rejected(self):
        self.run_create()
        self.reseal('python.json', lambda r:r['rows'][0].update(return_data='0xff'))
        with self.assertRaisesRegex(ValueError, 'REPLAY_MISMATCH'): self.run_verify()

    def test_existing_output_preserved(self):
        self.run_create()
        original = (self.root/'result/COMPLETE.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'NEW_PRIVATE'): self.run_create()
        self.assertEqual((self.root/'result/COMPLETE.json').read_bytes(), original)

    def test_dependency_inventory_and_modified_same_version(self):
        path = self.root/'engine.py'; path.write_bytes(b'known package bytes')
        hashes = {'engine.py':hashlib.sha256(path.read_bytes()).hexdigest()}
        aggregate = hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        pin = {'fixture':{'version':'1','files':1,'runtime_sha256':aggregate}}
        dist = SimpleNamespace(version='1',files=[PurePosixPath('engine.py')],locate_file=lambda _:path)
        with patch.object(worker,'PINS',pin), patch.object(worker,'distribution',return_value=dist):
            self.assertEqual(worker.dependency_identity()['fixture']['files'], 1)
            path.write_bytes(b'changed package bytes')
            with self.assertRaisesRegex(ValueError,'DEPENDENCY_BYTES'): worker.dependency_identity()

    def test_modified_dependency_same_version_rejected(self):
        self.second['dependencies']['py-evm']['runtime_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'IDENTITY'): self.assess()

    def test_decode_packed_storage_and_reject_high_bits(self):
        self.assertEqual(worker.decode_word(5 | (10 << 16) | (1 << 32),'pause'),
                         {'remaining':5,'distributed':10,'paused':1})
        admin = int(access.evm.SENDER,16)
        self.assertEqual(worker.decode_word(admin | (7 << 160) | (3 << 176),'access'),
                         {'admin':access.evm.SENDER,'remaining':7,'distributed':3})
        for word, family in ((1 << 40,'pause'),(1 << 192,'access'),(-1,'pause'),(False,'pause')):
            with self.assertRaises(ValueError): worker.decode_word(word,family)

    def test_worker_timeout_kills_process_group(self):
        fake = SimpleNamespace(pid=12345,returncode=-9)
        calls = []
        def wait(timeout=None):
            calls.append(timeout)
            if timeout: raise subprocess.TimeoutExpired('fixed-worker',timeout)
        fake.wait = wait
        with patch.object(cross.subprocess,'Popen',return_value=fake), \
             patch.object(cross.os,'killpg') as kill:
            with self.assertRaisesRegex(ValueError,'SECOND_EVM_TIMEOUT'):
                cross._run_python(self.root/'solc',self.digest)
            kill.assert_called_once_with(fake.pid, cross.signal.SIGKILL)
        self.assertEqual(calls,[180,None])

    def test_fresh_cache_uses_verified_source_not_stale_bytecode(self):
        module = self.root/'owned_cache_fixture.py'
        module.write_text('VALUE = 2\n')
        os.utime(module,(1700000000,1700000000))
        py_compile.compile(str(module),doraise=True,
                           invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
        module.write_text('VALUE = 1\n')
        os.utime(module,(1700000000,1700000000))
        script = ('import sys; sys.path.insert(0,' + repr(str(self.root)) +
                  '); import owned_cache_fixture; print(owned_cache_fixture.VALUE)')
        # Control proves that -B alone accepts the existing stale bytecode.
        old = subprocess.check_output([cross.sys.executable,'-I','-B','-c',script],text=True)
        fresh = subprocess.check_output(cross._python_command(self.root/'fresh') +
                                        ['-c',script],text=True)
        self.assertEqual(old.strip(),'2')
        self.assertEqual(fresh.strip(),'1')

    def test_cli_failure_does_not_echo_private_path(self):
        output = io.StringIO()
        with redirect_stdout(output):
            result = cross.main(['compare-owned-evm-engines','--solc','/private-secret-solc',
                '--evm','/private-secret-evm','--source-digest','0'*64,
                '--out',str(self.root/'new')])
        self.assertEqual(result,2)
        self.assertNotIn('private-secret',output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['status'],'OWNED_CROSS_EVM_BLOCKED')


if __name__ == '__main__':
    unittest.main()
