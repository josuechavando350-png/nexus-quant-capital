"""Synthetic unit evidence is explicit; native acceptance runs separately."""
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import owned_quota_cases as cases, owned_quota_review as review, quality
from superhunter import owned_quota_execution as quota_execution
from superhunter.safe_io import canonical, write_new_bundle

DIGEST = 'a'*64


def synthetic_execution():
    """Known hand-written fixture simulator, never represented as an EVM run."""
    builds,rows = [],[]
    for variant in cases.VARIANTS:
        for codegen in cases.CODEGEN:
            builds.append({'variant':variant,'codegen':codegen,'initial_state':dict(cases.INITIAL),
                'source_sha256':cases.sha(cases.owned_source(variant).encode()),
                'input_sha256':cases.sha(canonical(cases.compile_input(variant,codegen))),
                'output_sha256':'b'*64,'creation_sha256':'c'*64,'runtime_sha256':'d'*64})
            for scenario,sequence in enumerate(cases.SEQUENCES):
                state = dict(cases.INITIAL)
                for step,(amount,gas) in enumerate(sequence):
                    before = dict(state)
                    allowed = amount <= state['quota'] and amount <= state['remaining']
                    if variant == 'strict_boundary': allowed &= amount < state['quota']
                    status = 'OUT_OF_GAS' if gas == 1 else 'COMMITTED' if allowed else 'REVERTED'
                    if status == 'COMMITTED':
                        if variant != 'quota_not_charged': state['quota'] -= amount
                        state['remaining'] -= amount * (2 if variant == 'double_debit' else 1)
                        state['distributed'] += amount + (1 if variant == 'extra_credit' else 0)
                    rows.append({'variant':variant,'codegen':codegen,'scenario':scenario,'step':step,
                        'observation':{'before':before,'after':dict(state),'amount':amount,'gas':gas,
                                       'status':status,'return_data':'0x'},
                        'state_root':'e'*64,'stdout_sha256':'f'*64})
    return {'schema_version':1,'profile':review.PROFILE,'source_digest':DIGEST,'fork':'Cancun',
        'solc_sha256':'1'*64,'geth_sha256':'2'*64,'builds':builds,'rows':rows,
        'constructor_executions':12,'runtime_calls':228}


class QuotaReviewTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.execution = synthetic_execution()

    def call(self, variant='correct', index=1):
        return deepcopy([r['observation'] for r in self.execution['rows']
                         if r['variant'] == variant and r['codegen'] == 'legacy'][index])

    def test_six_known_cases_are_not_228_samples(self):
        report = review.analyze(self.execution,DIGEST)
        self.assertEqual(report['case_count'],6)
        self.assertEqual(report['runtime_calls'],228)
        self.assertEqual(report['metrics']['full']['counts'],
            {'tp':4,'fp':0,'tn':2,'fn':0,'abstain_positive':0,'abstain_negative':0,
             'error_positive':0,'error_negative':0})
        for key in ('blind_benchmark','generalization_established','vulnerability_confirmed',
                    'native_execution_regenerated_here','detector_uses_variant_or_truth'):
            self.assertIs(report[key],False)

    def test_ablations_measure_real_omissions(self):
        metrics = review.analyze(self.execution,DIGEST)['metrics']
        self.assertEqual((metrics['status_only']['counts']['tp'],metrics['status_only']['counts']['fn']),(1,3))
        self.assertEqual((metrics['state_only']['counts']['tp'],metrics['state_only']['counts']['fn']),(3,1))
        self.assertEqual(metrics['full']['recall_all_positives']['numerator'],4)

    def test_detector_cannot_read_variant_truth_or_claimed_flags(self):
        call = self.call()
        for field in ('variant','truth','is_positive'):
            changed = deepcopy(call); changed[field] = 'positive'
            with self.assertRaisesRegex(ValueError,'QUOTA_OBSERVATION'): review.detect(changed)

    def test_each_seeded_effect_is_observed(self):
        wanted = {'quota_not_charged':'QUOTA_DEBIT_MISMATCH','strict_boundary':'VALID_REQUEST_REJECTED',
                  'double_debit':'BALANCE_DEBIT_MISMATCH','extra_credit':'DISTRIBUTION_CREDIT_MISMATCH'}
        for variant,reason in wanted.items():
            calls = [r['observation'] for r in self.execution['rows'] if r['variant'] == variant]
            self.assertTrue(any(reason in review.detect(c)['reasons'] for c in calls),variant)

    def test_zero_amount_exact_limit_revert_and_out_of_gas_controls(self):
        calls = [r['observation'] for r in self.execution['rows'] if r['variant'] == 'correct']
        self.assertTrue(any(c['amount'] == 0 for c in calls))
        self.assertTrue(any(c['amount'] == c['before']['quota'] == 5 for c in calls))
        self.assertEqual({c['status'] for c in calls},{'COMMITTED','REVERTED','OUT_OF_GAS'})
        self.assertTrue(all(review.detect(c)['decision'] == 'negative' for c in calls))

    def test_failing_detector_is_scored_not_promoted_to_pass(self):
        with patch.object(review,'detect',return_value={'decision':'negative','reasons':[]}):
            report = review.analyze(self.execution,DIGEST)
        self.assertEqual(report['metrics']['full']['counts']['fn'],4)
        self.assertEqual(report['metrics']['full']['counts']['tp'],0)

    def test_false_alarms_remain_false_positives(self):
        with patch.object(review,'detect',return_value={'decision':'positive','reasons':['CONTROL']}):
            report = review.analyze(self.execution,DIGEST)
        self.assertEqual(report['metrics']['full']['counts']['fp'],2)

    def test_failed_call_with_persistent_change_is_invalid_evidence(self):
        call = self.call(); call['status'] = 'REVERTED'
        with self.assertRaisesRegex(ValueError,'QUOTA_FAILED_CALL_CHANGED_STATE'): review.detect(call)

    def test_noncanonical_integer_and_extra_state_rejected(self):
        for location,key,value in [('call','amount',True),('call','gas',True),
                ('before','remaining',False),('after','quota',-1),('after','quota',65536)]:
            call = self.call(); (call if location == 'call' else call[location])[key] = value
            with self.assertRaises(ValueError): review.detect(call)
        call = self.call(); call['after']['extra'] = 1
        with self.assertRaises(ValueError): review.detect(call)

    def test_unknown_policy_and_return_data_rejected(self):
        with self.assertRaises(ValueError): review.detect(self.call(),'private-policy')
        call = self.call(); call['return_data'] = '0x1234'
        with self.assertRaises(ValueError): review.detect(call)

    def test_missing_duplicate_and_reordered_calls_rejected(self):
        for edit in ('missing','duplicate','reorder'):
            data = deepcopy(self.execution)
            if edit == 'missing': data['rows'].pop()
            elif edit == 'duplicate': data['rows'][1] = data['rows'][0]
            else: data['rows'][0],data['rows'][1] = data['rows'][1],data['rows'][0]
            with self.assertRaises(ValueError): review.analyze(data,DIGEST)

    def test_boolean_counts_and_wrong_fork_rejected(self):
        for key,value in [('constructor_executions',True),('runtime_calls',True),
                          ('schema_version',True),('fork','unreviewed')]:
            data = deepcopy(self.execution); data[key] = value
            with self.assertRaises(ValueError): review.analyze(data,DIGEST)

    def test_source_and_compilation_identity_are_bound(self):
        with self.assertRaises(ValueError): review.analyze(self.execution,'b'*64)
        for key in ('source_sha256','input_sha256'):
            data = deepcopy(self.execution); data['builds'][0][key] = '0'*64
            with self.assertRaises(ValueError): review.analyze(data,DIGEST)

    def test_compiler_disagreement_rejected(self):
        data = deepcopy(self.execution)
        row = next(r for r in data['rows'] if r['variant'] == 'correct' and
                   r['codegen'] == 'ir_optimized' and r['scenario'] == 5 and r['step'] == 2)
        row['observation']['after']['distributed'] += 1
        with self.assertRaisesRegex(ValueError,'QUOTA_CODEGEN_DISAGREEMENT'): review.analyze(data,DIGEST)

    def test_disconnected_state_and_altered_fixed_input_rejected(self):
        for field in ('before','amount'):
            data = deepcopy(self.execution); call = data['rows'][1]['observation']
            if field == 'before': call['before']['quota'] += 1
            else: call['amount'] = 2
            with self.assertRaises(ValueError): review.analyze(data,DIGEST)

    def test_inputs_are_not_mutated(self):
        before = canonical(self.execution)
        review.analyze(self.execution,DIGEST)
        self.assertEqual(canonical(self.execution),before)

    def test_source_and_codegen_are_closed(self):
        for value in ('untrusted',True,None):
            with self.assertRaises(ValueError): cases.owned_source(value)
            with self.assertRaises(ValueError): cases.compile_input('correct',value)
        self.assertEqual(len({cases.owned_source(v) for v in cases.VARIANTS}),6)

    def test_compilation_requests_the_ast_required_by_native_classifier(self):
        for variant in cases.VARIANTS:
            for codegen in cases.CODEGEN:
                selected = cases.compile_input(variant,codegen)['settings']['outputSelection']['*']
                self.assertIn('ast',selected[''])

    def test_storage_decoder_rejects_extra_slots_or_bits(self):
        contract = {'evm':{'deployedBytecode':{'object':'00'}}}
        alloc = {review.evm.RECEIVER:{'code':'0x00','storage':{review.evm.SLOT:hex(20+(5<<32))}}}
        self.assertEqual(cases.decode(alloc,contract),cases.INITIAL)
        for storage in ({review.evm.SLOT:hex(1<<48)}, {'other':'0x0'}):
            alloc[review.evm.RECEIVER]['storage'] = storage
            with self.assertRaises(ValueError): cases.decode(alloc,contract)

    def test_wrong_source_blocks_before_tools(self):
        with patch.object(review.compiler,'read_pinned_binary',side_effect=AssertionError('Must not run')):
            with self.assertRaisesRegex(ValueError,'QUOTA_SOURCE_CHANGED'):
                review.execute_native(self.root/'solc',self.root/'evm',DIGEST)

    def bundle_files(self):
        return {'execution.json':canonical(self.execution),
                'evaluation.json':canonical(review.analyze(self.execution,DIGEST)),
                'REVIEW.md':b'synthetic unit test bundle; not native acceptance\n'}

    def test_verifier_reexecutes_and_rejects_resealed_false_score(self):
        files = self.bundle_files(); out = self.root/'bundle'
        write_new_bundle(out,files)
        with patch.object(review,'_execute',return_value=files) as replay:
            self.assertEqual(review.verify(out,self.root/'s',self.root/'e',DIGEST)['status'],
                             'OWNED_QUOTA_REPLAY_VERIFIED')
            replay.assert_called_once()
        changed = dict(files); report = json.loads(changed['evaluation.json'])
        report['metrics']['full']['counts']['tp'] = 100
        changed['evaluation.json'] = canonical(report)
        other = self.root/'resealed'; write_new_bundle(other,changed)
        with patch.object(review,'_execute',return_value=files):
            with self.assertRaisesRegex(ValueError,'QUOTA_REPLAY_MISMATCH'):
                review.verify(other,self.root/'s',self.root/'e',DIGEST)

    def test_bundle_tamper_extra_file_symlink_and_wrong_reference_rejected(self):
        for mode in ('tamper','extra','symlink','reference'):
            out = self.root/mode; write_new_bundle(out,self.bundle_files())
            if mode == 'tamper': (out/'REVIEW.md').write_bytes(b'altered')
            elif mode == 'extra': (out/'private.txt').write_text('do not export')
            elif mode == 'symlink':
                original = out/'execution.json'; moved = self.root/'moved.json'
                original.rename(moved); original.symlink_to(moved)
            with patch.object(review,'_execute',side_effect=AssertionError('Must not execute')):
                with self.assertRaises((ValueError,OSError)):
                    review.verify(out,self.root/'s',self.root/'e','0'*64 if mode == 'reference' else DIGEST)

    def test_outputs_cannot_overwrite_or_enter_source_tree(self):
        with patch.object(review,'_execute',side_effect=AssertionError('Must not execute')):
            for out in (self.root,review.ROOT/'private-bundle'):
                with self.assertRaises(ValueError): review.create(out,self.root/'s',self.root/'e',DIGEST)

    def test_cli_does_not_echo_private_errors_or_accept_targets(self):
        output = io.StringIO()
        with patch.object(review,'create',side_effect=ValueError('/private-error')),redirect_stdout(output):
            self.assertEqual(review.main(['evaluate-owned-quota','--solc','/private-solc',
                '--evm','/private-evm','--source-digest',DIGEST,'--out',str(self.root/'out')]),2)
        self.assertNotIn('private',output.getvalue())
        errors = io.StringIO()
        with redirect_stderr(errors),self.assertRaises(SystemExit):
            review.main(['evaluate-owned-quota','--target','private-target'])
        self.assertNotIn('private-target',errors.getvalue())

    def test_component_is_reachable_from_cli_and_has_required_tests(self):
        component = quality.COMPONENTS['owned_quota_review']
        self.assertIn('owned_quota_review',''.join(quality.COMPONENTS['entrypoints']['depends']))
        self.assertIn('owned_quota_worker.py',component['files'])
        self.assertTrue(any('test_owned_quota_review.' in test for test in quality.REQUIRED_TESTS))

    def test_geth_worker_does_not_raise_inherited_two_gib_limit(self):
        import subprocess,sys
        # Real child resource calls under the same inherited hard limit. Replace
        # only execve so this unit check cannot execute native contracts.
        script = '''
import os,resource,sys
from unittest.mock import patch
from superhunter import owned_quota_evm_worker as evm_worker
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
fd=os.open('/dev/null',os.O_RDONLY)
try:
    with patch.object(sys,'argv',['worker','create',str(fd),'-','2000000']), \\
         patch.object(os,'execve'):
        evm_worker.main()
    assert resource.getrlimit(resource.RLIMIT_AS)==(2*1024**3,2*1024**3)
finally:
    os.close(fd)
'''
        result = subprocess.run([sys.executable,'-B','-c',script],cwd=review.ROOT.parent,
                                capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr.decode())

    def test_sealed_image_reuse_checks_bytes_and_does_not_close_caller_fd(self):
        import os
        image = b'owned immutable descriptor unit fixture'
        with review.compiler._sealed_executable(image) as fd:
            with quota_execution._execution_image(image,fd) as actual:
                self.assertEqual(actual,fd)
            self.assertEqual(os.pread(fd,len(image),0),image)
            with self.assertRaisesRegex(ValueError,'EVM_SEALED_IMAGE_MISMATCH'):
                with quota_execution._execution_image(b'x'*len(image),fd): pass

    def test_unsealed_or_wrong_size_descriptor_is_rejected(self):
        import os
        fd = os.memfd_create('owned-unit',os.MFD_ALLOW_SEALING)
        try:
            os.write(fd,b'unit')
            with self.assertRaisesRegex(ValueError,'EVM_IMAGE_NOT_SEALED'):
                with quota_execution._execution_image(b'unit',fd): pass
        finally:
            os.close(fd)
        with review.compiler._sealed_executable(b'unit') as fd:
            with self.assertRaisesRegex(ValueError,'EVM_IMAGE_NOT_SEALED'):
                with quota_execution._execution_image(b'other-size',fd): pass
        for bad in (True,-1,'1'):
            with self.assertRaises(ValueError):
                with quota_execution._execution_image(b'unit',bad): pass


if __name__ == '__main__':
    unittest.main()
