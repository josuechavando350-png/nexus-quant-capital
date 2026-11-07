"""Owned fixtures and real importers; scanner doubles are explicitly synthetic.

Only the two network tests execute a real fixed child probe. Native Slither
acceptance is separate and never inferred from these synthetic scanner reports.
"""
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from superhunter import owned_slither_native as native
from superhunter import owned_slither_dependencies as deps, owned_slither_network as network
from superhunter import owned_slither_native_worker as worker
from superhunter import owned_process, static_review
from superhunter.owned_slither_cases import SOURCES, context
from superhunter.safe_io import canonical, strict_json
from superhunter.tests.test_slither_offline_endtoend import synthetic_slither_report

EMPTY_NATIVE = b'{\n  "success": true,\n  "error": null,\n  "results": {}\n}'


class ConversionTests(unittest.TestCase):
    def test_actual_repository_and_generated_source_provenance_are_distinct(self):
        proof=native.fixture_cases.fixture_provenance()
        self.assertEqual(proof['repository'],'josuechavando350-png/nexus-quant-capital')
        self.assertFalse(proof['generated_source_is_tracked_repository_file'])
        self.assertFalse(proof['repository_commit_membership_authenticated_at_runtime'])
        self.assertEqual(context('clean',native.sha(EMPTY_NATIVE))['repository']['repo'],proof['repository'])

    def test_changed_literal_cannot_keep_historical_source_identity(self):
        changed={**SOURCES,'clean':SOURCES['clean']+b'\n'}
        with patch.object(native.fixture_cases,'SOURCES',changed),self.assertRaisesRegex(ValueError,'ORIGINAL_LITERAL_CHANGED'):
            native.fixture_cases.fixture_provenance()

    def test_changed_container_cannot_keep_historical_commit_claim(self):
        with patch.object(native.fixture_cases,'read_artifact',return_value=b'OWNED CHANGED CONTAINER'),self.assertRaisesRegex(ValueError,'ORIGINAL_CONTAINER_CHANGED'):
            native.fixture_cases.fixture_provenance()

    def test_successful_empty_original_is_preserved_and_conversion_explicit(self):
        normalized,record = native.convert_original(EMPTY_NATIVE,'clean')
        self.assertEqual(strict_json(normalized)['results'],{'detectors':[]})
        self.assertEqual(record['original_sha256'],hashlib.sha256(EMPTY_NATIVE).hexdigest())
        self.assertNotEqual(record['original_sha256'],record['normalized_sha256'])
        self.assertTrue(record['original_bytes_preserved'])
        self.assertFalse(record['producer_authenticated'])

    def test_explicit_detector_report_bytes_are_not_rewritten(self):
        original = synthetic_slither_report('positive')
        converted,record = native.convert_original(original,'positive')
        self.assertEqual(converted,original)
        self.assertEqual(record['rule'],'explicit-detector-list-unchanged')

    def test_generic_importer_still_rejects_missing_detector_field(self):
        ctx = context('clean',native.sha(EMPTY_NATIVE))
        with self.assertRaisesRegex(ValueError,'DETECTOR_RESULTS_REQUIRED'):
            static_review.normalize(EMPTY_NATIVE,ctx,{'Owned.sol':SOURCES['clean']})

    def test_failed_or_ambiguous_reports_are_not_converted_to_clean(self):
        variants = [b'{}',canonical({'success':False,'error':None,'results':{}}),
                    canonical({'success':True,'error':'failed','results':{}}),
                    canonical({'success':1,'error':None,'results':{}}),
                    canonical({'success':True,'error':None,'results':{'other':[]}}),
                    canonical({'success':True,'error':None,'results':{'detectors':True}}),
                    b'{"success":true,"success":false,"error":null,"results":{}}']
        for raw in variants:
            with self.subTest(raw=raw),self.assertRaises(ValueError):
                native.convert_original(raw,'clean')

    def test_unknown_mode_and_large_or_nonbyte_report_are_rejected(self):
        for raw,mode in ((EMPTY_NATIVE,'external'),(b'x'*2_000_001,'clean'),('text','clean')):
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                native.convert_original(raw,mode)


class NativeEvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.out,self.solc = self.root/'result',self.root/'solc'
        self.image = b'OWNED UNIT COMPILER DOUBLE; NEVER EXECUTED\n';self.solc.write_bytes(self.image)
        self.digest = native.sha(canonical(native.quality.source_snapshot()))
        self.overrides = {};self.returncode=0;self.timeout=False;self.bad_admission=False
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch.object(native.dependencies,'verify_dependencies',return_value=deps.expected_identity()))
        stack.enter_context(patch.object(native.network,'library_bytes',return_value=b'OWNED UNIT LIBRARY DOUBLE'))
        stack.enter_context(patch.object(native.native_compile,'read_pinned_binary',side_effect=lambda path:Path(path).read_bytes()))
        self.run=stack.enter_context(patch.object(native.owned_process,'run',side_effect=self.fake_worker))

    def fake_worker(self,command,**kwargs):
        mode,digest=command[-2:];work=Path(kwargs['cwd'])
        raw=self.overrides.get(mode,synthetic_slither_report(mode) if mode=='positive' else EMPTY_NATIVE)
        (work/'slither.json').write_bytes(raw)
        admission=native._admission(mode,digest)
        if self.bad_admission:admission['network']['socket_controls_denied']=0
        (work/'admission.json').write_bytes(canonical(admission))
        kwargs['stdout'].write(b'OWNED SYNTHETIC WORKER; NO SCANNER EXECUTED\n')
        if self.timeout:raise subprocess.TimeoutExpired('fixed OWNED unit worker',90)
        return SimpleNamespace(returncode=self.returncode)

    def create(self):return native.create(self.out,self.solc,self.digest)
    def verify(self):return native.verify(self.out,self.solc,self.digest)

    def reseal(self,root):
        marker=strict_json((root/'COMPLETE.json').read_bytes())
        for name in marker['sha256']:marker['sha256'][name]=native.sha((root/name).read_bytes())
        (root/'COMPLETE.json').write_bytes(canonical(marker))

    def test_original_bytes_and_real_importer_chain_are_retained(self):
        result=self.create()
        self.assertEqual(result['counts'],{'tp':1,'tn':2,'fp':0,'fn':0})
        self.assertTrue(result['all_expected_control_results'])
        for mode in ('clean','comparison'):
            self.assertEqual((self.out/'cases'/mode/'capture/slither-original.json').read_bytes(),EMPTY_NATIVE)
            reviewed=static_review.verify_report(self.out/'cases'/mode/'imported')
            self.assertEqual(reviewed['unique_alert_count'],0)
            self.assertFalse(reviewed['scanner_execution_verified'])
        for name in ('producer_authenticated','independent_producers_proved','process_memory_integrity_proved',
                     'host_filesystem_isolated','generalization_established','platform_complete','vulnerability_confirmed'):
            self.assertIs(result[name],False)

    def test_false_positive_and_omission_are_measured_not_hidden(self):
        self.overrides['positive']=EMPTY_NATIVE
        source=SOURCES['clean'];start=source.index(b'require(');end=source.index(b';',start)+1
        self.overrides['clean']=canonical({'success':True,'error':None,'results':{'detectors':[{
            'check':'tx-origin','impact':'Medium','confidence':'Medium','description':'OWNED FALSE POSITIVE DOUBLE',
            'elements':[{'type':'node','name':'OWNED FALSE POSITIVE DOUBLE',
                'source_mapping':{'filename_relative':'Owned.sol','start':start,'length':end-start,
                                  'lines':[source[:start].count(b'\n')+1]}}]}]}})
        result=self.create()
        self.assertEqual(result['counts'],{'tp':0,'tn':1,'fp':1,'fn':1})
        self.assertEqual(result['false_positive_rate'],0.5)
        self.assertEqual(result['omission_rate'],1.0)
        self.assertFalse(result['all_expected_control_results'])

    def test_replay_must_execute_three_new_cases(self):
        self.create();self.assertEqual(self.run.call_count,3)
        checked=self.verify();self.assertEqual(self.run.call_count,6)
        self.assertEqual(checked['native_cases_reexecuted'],3)

    def test_native_replay_difference_is_rejected(self):
        self.create();self.overrides['positive']=EMPTY_NATIVE
        with self.assertRaisesRegex(ValueError,'NATIVE_REPLAY_DIFFERS'):self.verify()

    def test_wrong_source_digest_blocks_before_any_execution(self):
        with self.assertRaisesRegex(ValueError,'SOURCE_IDENTITY'):
            native.create(self.out,self.solc,'0'*64)
        self.run.assert_not_called();self.assertFalse(self.out.exists())

    def test_missing_dependency_blocks_before_output(self):
        with patch.object(native.dependencies,'verify_dependencies',side_effect=ValueError('OWNED MISSING')):
            with self.assertRaises(ValueError):self.create()
        self.run.assert_not_called();self.assertFalse(self.out.exists())

    def test_failed_native_exit_preserves_original_and_no_success_marker(self):
        self.returncode=1
        with self.assertRaisesRegex(ValueError,'WORKER_FAILED'):self.create()
        self.assertEqual((self.out/'cases/clean/capture/slither-original.json').read_bytes(),EMPTY_NATIVE)
        self.assertFalse((self.out/'review/COMPLETE.json').exists())

    def test_timeout_is_explicit_without_fabricated_exit_code(self):
        self.timeout=True
        with self.assertRaisesRegex(ValueError,'WORKER_FAILED'):self.create()
        record=strict_json((self.out/'cases/clean/capture/execution.json').read_bytes())
        self.assertIsNone(record['returncode']);self.assertIs(record['timed_out'],True)
        self.assertFalse((self.out/'review/COMPLETE.json').exists())

    def test_boolean_exit_code_cannot_claim_success(self):
        self.returncode=False
        with self.assertRaisesRegex(ValueError,'WORKER_FAILED'):self.create()

    def test_missing_network_admission_blocks_normalization(self):
        self.bad_admission=True
        with self.assertRaisesRegex(ValueError,'ADMISSION'):self.create()
        self.assertFalse((self.out/'cases/clean/conversion').exists())

    def test_resealed_conversion_lie_is_rejected(self):
        self.create();root=self.out/'cases/clean/conversion'
        record=strict_json((root/'conversion.json').read_bytes());record['original_sha256']='0'*64
        (root/'conversion.json').write_bytes(canonical(record));self.reseal(root)
        with self.assertRaisesRegex(ValueError,'CONVERSION_BINDING'):self.verify()

    def test_resealed_source_change_is_rejected(self):
        self.create();root=self.out/'cases/clean/capture'
        (root/'source.sol').write_bytes(SOURCES['clean']+b'\n');self.reseal(root)
        with self.assertRaisesRegex(ValueError,'SOURCE_BYTES'):self.verify()

    def test_resealed_omission_removal_cannot_change_measured_result(self):
        self.overrides['positive']=EMPTY_NATIVE;result=self.create()
        result['counts'].update(tp=1,fn=0);result['all_expected_control_results']=True
        for name,raw in native._documents(result).items():(self.out/'review'/name).write_bytes(raw)
        self.reseal(self.out/'review')
        with self.assertRaisesRegex(ValueError,'REVIEW_BINDING'):self.verify()

    def test_marker_change_during_replay_is_rejected(self):
        self.create();original=native.create
        def changed(*args):
            result=original(*args)
            p=self.out/'review/COMPLETE.json';p.write_bytes(p.read_bytes()+b' ')
            return result
        with patch.object(native,'create',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'CHANGED_DURING_REPLAY'):self.verify()

    def test_extra_file_or_symlink_is_not_hidden(self):
        self.create();extra=self.out/'extra';extra.write_bytes(b'OWNED')
        with self.assertRaisesRegex(ValueError,'STAGE_INVENTORY'):self.verify()
        extra.unlink();p=self.out/'cases/clean/capture/source.sol';raw=p.read_bytes();p.unlink()
        elsewhere=self.root/'other.sol';elsewhere.write_bytes(raw);p.symlink_to(elsewhere)
        with self.assertRaises((ValueError,OSError)):self.verify()

    def test_existing_output_is_never_overwritten(self):
        self.create();before=(self.out/'review/COMPLETE.json').read_bytes()
        with self.assertRaises(ValueError):self.create()
        self.assertEqual((self.out/'review/COMPLETE.json').read_bytes(),before)

    def test_cli_failure_does_not_reveal_private_paths(self):
        output=io.StringIO()
        with redirect_stdout(output):
            rc=native.main(['verify-owned-slither-native','--bundle',str(self.root/'PRIVATE_PATH'),
                            '--solc',str(self.solc),'--expected-source','invalid'])
        self.assertEqual(rc,2);self.assertNotIn('PRIVATE_PATH',output.getvalue())


class WorkerAdmissionTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        (self.root/'Owned.sol').write_bytes(SOURCES['clean'])
        (self.root/'solc').write_bytes(b'OWNED INVALID COMPILER; NEVER EXECUTED')
        self.digest=native.sha(canonical(native.quality.source_snapshot()))
        stack=ExitStack();self.addCleanup(stack.close)
        self.dependencies=stack.enter_context(patch.object(worker.dependencies,'verify_dependencies'))
        self.network=stack.enter_context(patch.object(worker.network,'install'))
        self.execute=stack.enter_context(patch.object(worker.os,'execv'))

    def rejected(self,args):
        self.assertEqual(worker.main(args),2)
        self.dependencies.assert_not_called();self.network.assert_not_called();self.execute.assert_not_called()
        self.assertFalse((self.root/'admission.json').exists())

    def test_source_outside_fixed_controls_never_reaches_scanner(self):
        (self.root/'Owned.sol').write_bytes(SOURCES['clean']+b'\n// OWNED changed input\n')
        self.rejected([str(self.root),'clean',self.digest])

    def test_unknown_mode_and_extra_arguments_never_reach_scanner(self):
        self.rejected([str(self.root),'external',self.digest])
        self.rejected([str(self.root),'clean',self.digest,'--arbitrary-source'])

    def test_stale_source_identity_never_reaches_scanner(self):
        self.rejected([str(self.root),'clean','0'*64])

    def test_unpinned_compiler_never_reaches_scanner(self):
        self.rejected([str(self.root),'clean',self.digest])


class DependencyTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.site=self.root/'lib/python3.12/site-packages';self.site.mkdir(parents=True)
        self.package=self.site/'owned_distributions/owned-unit';self.package.mkdir(parents=True)
        metadata='owned_unit-1.0.dist-info'
        contents={'owned_unit/__init__.py':b'OWNED = True\n',metadata+'/METADATA':b'Name: owned-unit\nVersion: 1.0\n',
                  metadata+'/entry_points.txt':b'[owned_example]\nfixed = owned_unit:OWNED\n'}
        for name,raw in contents.items():
            p=self.package/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        hashes={name:native.sha(raw) for name,raw in contents.items()}
        pin={'version':'1.0','wheel_sha256':'a'*64,'files':len(hashes),
             'inventory_sha256':native.sha(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()),
             'metadata_directory':metadata,'directory':'owned-unit'}
        stack=ExitStack();self.addCleanup(stack.close)
        stack.enter_context(patch.object(deps,'PINS',{'owned-unit':pin}))
        stack.enter_context(patch.object(deps.sys,'prefix',str(self.root)))
        self.dist=SimpleNamespace(version='1.0',locate_file=lambda name:self.package/name,
                                  metadata={'Name':'owned-unit'})
        stack.enter_context(patch.object(deps,'distribution',return_value=self.dist))
        self.visible=stack.enter_context(patch.object(deps,'distributions',return_value=[self.dist]))
        self.bootstrap=self.site/'superhunter_owned_distributions.pth';self.bootstrap.write_bytes(deps.bootstrap_bytes())
        self.metadata=metadata

    def test_exact_code_and_metadata_pass(self):
        self.assertEqual(deps.verify_dependencies(),deps.expected_identity())

    def test_extra_visible_location_is_rejected_before_reading_its_metadata(self):
        location=self.root/'outside'
        class OwnMetadataOnly:
            def locate_file(self,name):return location/name
            @property
            def metadata(self):raise AssertionError('foreign metadata must not be read')
        self.visible.return_value=[OwnMetadataOnly(),self.dist]
        with self.assertRaisesRegex(ValueError,'DEPENDENCY'):deps.verify_dependencies()

    def test_missing_visible_distribution_is_rejected(self):
        self.visible.return_value=[]
        with self.assertRaisesRegex(ValueError,'DEPENDENCY'):deps.verify_dependencies()

    def test_duplicate_visible_distribution_is_rejected(self):
        self.visible.return_value=[self.dist,self.dist]
        with self.assertRaisesRegex(ValueError,'DEPENDENCY'):deps.verify_dependencies()

    def test_visible_name_cannot_disagree_with_pinned_location(self):
        self.visible.return_value=[SimpleNamespace(version='1.0',metadata={'Name':'owned-other'},
                                                   locate_file=lambda name:self.package/name)]
        with self.assertRaisesRegex(ValueError,'DEPENDENCY'):deps.verify_dependencies()

    def test_visible_version_cannot_disagree_with_selected_distribution(self):
        self.visible.return_value=[SimpleNamespace(version='2.0',metadata={'Name':'owned-unit'},
                                                   locate_file=lambda name:self.package/name)]
        with self.assertRaisesRegex(ValueError,'DEPENDENCY'):deps.verify_dependencies()

    def test_malformed_visible_names_are_rejected(self):
        for name in (None,True,'x'*201,'owned unit'):
            self.visible.return_value=[SimpleNamespace(version='1.0',metadata={'Name':name},
                                                       locate_file=lambda item:self.package/item)]
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'DEPENDENCY'):
                deps.verify_dependencies()

    def test_visible_index_is_rechecked_after_file_inventory(self):
        foreign=SimpleNamespace(locate_file=lambda name:self.root/'outside'/name)
        self.visible.side_effect=[[self.dist],[foreign]]
        with self.assertRaisesRegex(ValueError,'DEPENDENCY'):deps.verify_dependencies()

    def test_distribution_name_normalization_preserves_valid_aliases(self):
        self.dist.metadata={'Name':'OWNED_unit'}
        self.assertEqual(deps.verify_dependencies(),deps.expected_identity())

    def test_entrypoint_metadata_change_is_rejected(self):
        (self.package/self.metadata/'entry_points.txt').write_bytes(b'OWNED CHANGED CONFIGURATION\n')
        with self.assertRaisesRegex(ValueError,'DEPENDENCY_BYTES'):deps.verify_dependencies()

    def test_unlisted_source_and_extra_distribution_are_rejected(self):
        p=self.package/'owned_unit/extra.py';p.write_bytes(b'OWNED = True\n')
        with self.assertRaisesRegex(ValueError,'DEPENDENCY_BYTES'):deps.verify_dependencies()
        p.unlink();(self.package.parent/'extra').mkdir()
        with self.assertRaisesRegex(ValueError,'DISTRIBUTION_INVENTORY'):deps.verify_dependencies()

    def test_bootstrap_cannot_add_executable_lines(self):
        self.bootstrap.write_bytes(deps.bootstrap_bytes()+b'import owned_unlisted\n')
        with self.assertRaisesRegex(ValueError,'DEPENDENCY_BOOTSTRAP'):deps.verify_dependencies()

    def test_symlinked_runtime_and_mixed_location_are_rejected(self):
        p=self.package/'owned_unit/__init__.py';p.unlink();p.symlink_to(self.bootstrap)
        with self.assertRaisesRegex(ValueError,'SYMLINK_OR_DEPTH'):deps.verify_dependencies()
        p.unlink();p.write_bytes(b'OWNED = True\n')
        self.dist.locate_file=lambda name:self.root/name
        with self.assertRaisesRegex(ValueError,'DEPENDENCY_IDENTITY'):deps.verify_dependencies()

    def test_entry_budget_is_enforced(self):
        with patch.object(deps,'MAX_ENTRIES',1):
            with self.assertRaisesRegex(ValueError,'ENTRY_BUDGET'):deps.verify_dependencies()


class NetworkFilterTests(unittest.TestCase):
    def child(self,code,pass_fds=()):
        with tempfile.TemporaryDirectory() as directory:
            with tempfile.TemporaryFile() as output,tempfile.TemporaryFile() as errors:
                script='import sys;sys.path.insert(0,'+repr(str(native.ROOT.parent))+');'+code
                result=owned_process.run([sys.executable,'-I','-B','-X','pycache_prefix='+directory+'/cache',
                    '-c',script],cwd=directory,env={'LANG':'C.UTF-8'},timeout=10,
                    stdout=output,stderr=errors,pass_fds=pass_fds)
                output.seek(0);errors.seek(0);return result.returncode,output.read(),errors.read()

    def test_sealed_filter_is_inherited_by_exec_child(self):
        code=("from superhunter.owned_slither_network import install;import json,subprocess;"
              "proof=install();child=subprocess.run([sys.executable,'-I','-B','-c',"
              "\"import socket,errno\\ntry: socket.socket()\\nexcept OSError as e: assert e.errno==errno.EPERM\\nelse: raise AssertionError('filter absent')\"],capture_output=True,timeout=5);"
              "assert child.returncode==0 and not child.stdout and not child.stderr;print(json.dumps(proof))")
        rc,raw,errors=self.child(code)
        self.assertEqual((rc,errors),(0,b''));self.assertEqual(json.loads(raw),network.expected_proof())

    def test_inherited_socket_prevents_scanner_filter_admission(self):
        first,second=socket.socketpair();self.addCleanup(first.close);self.addCleanup(second.close)
        code=("from superhunter.owned_slither_network import install\n"
              "try: install()\n"
              "except ValueError as e: assert str(e)=='OWNED_NETWORK_INHERITED_SOCKET'\n"
              "else: raise AssertionError('inherited socket admitted')")
        rc,raw,errors=self.child(code,(first.fileno(),))
        self.assertEqual((rc,raw,errors),(0,b'',b''))


if __name__=='__main__':
    unittest.main()
