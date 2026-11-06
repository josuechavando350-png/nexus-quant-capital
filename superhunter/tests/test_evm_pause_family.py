"""Bounded local fixture tests. Mocks below test packaging; native CLI acceptance is separate."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from superhunter import evm_pause_family as lab
from superhunter.safe_io import canonical, strict_json

SOURCE = 'a' * 64
INITIAL = {'remaining':15,'distributed':0,'paused':0}


def synthetic_report():
    # This is not evidence of compilation or EVM execution; ONLY a stub for
    # serialization/CLI rejection tests. Native acceptance uses real bins.
    fake={'case':0,'calls':[{'step':0,'status':'COMMITTED','before':INITIAL,
                              'after':INITIAL,'paused_release_persisted':False}]}
    return {'source_digest':SOURCE,'total_native_runtime_calls':80,'case_count':5,
            'solc_sha256':'b'*64,'evm_sha256':'c'*64,
            'cases':{variant:{profile:[deepcopy(fake)] for profile in lab.CODEGEN}
                    for variant in lab.VARIANTS},
            'paused_release_violations_in_known_fixture':{'guarded':0,'guard_missing':1}}


class PauseFamilyTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.out=self.root/'sealed'
        self.solc=self.root/'unused-solc';self.evm=self.root/'unused-evm'

    def reference(self, variant, commands):
        state=dict(INITIAL);rows=[]
        for op,amount,gas in commands:
            before=dict(state)
            expected=lab.reference(variant,state,op,amount,gas)
            state=expected['state'];rows.append((before,expected,
                lab.unauthorized_effect(before,state,op,amount,expected['status'])))
        return rows

    def sealed(self):
        with patch.object(lab,'execute',return_value=synthetic_report()):
            lab.create(self.out,self.solc,self.evm,SOURCE)

    def reseal(self,name,fn):
        target=self.out/name;data=strict_json(target.read_bytes());fn(data)
        raw=canonical(data);target.write_bytes(raw)
        manifest=strict_json((self.out/'COMPLETE.json').read_bytes())
        manifest['sha256'][name]=lab.sha(raw)
        (self.out/'COMPLETE.json').write_bytes(canonical(manifest))

    def test_guard_rejects_paused_release(self):
        calls=self.reference('guarded',lab.SEQUENCES[0]);
        self.assertEqual(calls[1][1]['status'],'REVERTED')
        self.assertEqual(calls[1][1]['state'],{'remaining':15,'distributed':0,'paused':1})
        self.assertFalse(calls[1][2])

    def test_mutant_commits_forbidden_release_in_reference(self):
        calls=self.reference('guard_missing',lab.SEQUENCES[0])
        self.assertEqual(calls[1][1]['status'],'COMMITTED')
        self.assertEqual(calls[1][1]['state'],{'remaining':13,'distributed':2,'paused':1})
        self.assertTrue(calls[1][2])

    def test_only_guard_line_differs_between_sources(self):
        good=lab.owned_source('guarded');bad=lab.owned_source('guard_missing')
        self.assertEqual(good.replace(lab.GUARD,''),bad)
        self.assertEqual(good.count('require(paused == 0);'),1)
        self.assertNotIn('require(paused == 0);',bad)

    def test_constructed_scenarios_fixed_and_distinct(self):
        self.assertEqual(len(lab.SEQUENCES),5)
        self.assertEqual(len({canonical(c) for c in lab.SEQUENCES}),5)
        self.assertTrue(all(len(c)==4 for c in lab.SEQUENCES))
        self.assertTrue(all(gas in (1,lab.evm.GAS) for seq in lab.SEQUENCES for _,_,gas in seq))

    def test_other_family_than_arithmetic_counters(self):
        self.assertIn('setPaused(uint8 state)',lab.compile_input('guarded','legacy')['sources'][lab.SOURCE_FILE]['content'])
        self.assertIn('release(uint8 amount)',lab.compile_input('guarded','legacy')['sources'][lab.SOURCE_FILE]['content'])

    def test_same_owned_sources_between_codegen_profiles(self):
        for variant in lab.VARIANTS:
            one=lab.compile_input(variant,'legacy')
            two=lab.compile_input(variant,'ir_optimized')
            self.assertEqual(one['sources'],two['sources'])
            self.assertFalse(one['settings']['optimizer']['enabled'])
            self.assertTrue(two['settings']['viaIR'])

    def test_compiler_input_has_no_external_urls_or_remappings(self):
        inp=lab.compile_input('guarded','legacy')
        self.assertEqual(set(inp),{'language','sources','settings'})
        self.assertEqual(set(inp['sources'][lab.SOURCE_FILE]),{'content'})

    def test_unlisted_variant_rejected(self):
        for bad in ('', 'production','../bad',True,None):
            with self.subTest(bad=bad),self.assertRaises(lab.PauseLabError):lab.owned_source(bad)

    def test_unlisted_optimizer_rejected(self):
        for bad in ('bad','legacy_optimized',False,123):
            with self.subTest(bad=bad),self.assertRaises(lab.PauseLabError):
                lab.compile_input('guarded',bad)

    def test_pause_requires_boolean_mode_not_two(self):
        r=lab.reference('guarded',INITIAL,'pause',2,lab.evm.GAS)
        self.assertEqual(r['status'],'REVERTED')
        self.assertEqual(r['state'],INITIAL)

    def test_pause_toggle_and_release_after_resume(self):
        rows=self.reference('guarded',lab.SEQUENCES[0])
        self.assertEqual([x[1]['status'] for x in rows],['COMMITTED','REVERTED','COMMITTED','COMMITTED'])
        self.assertEqual(rows[-1][1]['state'],{'remaining':12,'distributed':3,'paused':0})

    def test_out_of_gas_does_not_apply(self):
        value=lab.reference('guard_missing',{'remaining':15,'distributed':0,'paused':1},'release',4,1)
        self.assertEqual(value['status'],'OUT_OF_GAS');self.assertEqual(value['state'],{'remaining':15,'distributed':0,'paused':1})

    def test_release_cannot_exceed_remaining(self):
        for variant in lab.VARIANTS:
            x=lab.reference(variant,INITIAL,'release',16,lab.evm.GAS)
            self.assertEqual(x['status'],'REVERTED');self.assertEqual(x['state'],INITIAL)

    def test_mutant_does_not_inflate_total(self):
        for seq in lab.SEQUENCES:
            for variant in lab.VARIANTS:
                for _,row,_ in self.reference(variant,seq):
                    after=row['state'];self.assertEqual(after['remaining']+after['distributed'],15)

    def test_paused_zero_release_not_classified_as_effect(self):
        before={'remaining':15,'distributed':0,'paused':1}
        self.assertFalse(lab.unauthorized_effect(before,before,'release',0,'COMMITTED'))

    def test_reverted_paused_operation_not_classified_as_effect(self):
        before={'remaining':15,'distributed':0,'paused':1}
        after={'remaining':13,'distributed':2,'paused':1}
        self.assertFalse(lab.unauthorized_effect(before,after,'release',2,'REVERTED'))

    def test_normal_active_distribution_not_classified_as_pause_violation(self):
        before={'remaining':15,'distributed':0,'paused':0}
        after={'remaining':13,'distributed':2,'paused':0}
        self.assertFalse(lab.unauthorized_effect(before,after,'release',2,'COMMITTED'))

    def test_reference_rejects_boolean_amount(self):
        with self.assertRaises(lab.PauseLabError):lab.reference('guarded',INITIAL,'release',True,lab.evm.GAS)

    def test_reference_rejects_unknown_op_or_gas(self):
        for op,gas in [('transfer',lab.evm.GAS),('release',10),('pause',False)]:
            with self.subTest(op=op,gas=gas),self.assertRaises(lab.PauseLabError):
                lab.reference('guarded',INITIAL,op,1,gas)

    def test_reference_does_not_mutate_input(self):
        original=deepcopy(INITIAL)
        lab.reference('guarded',INITIAL,'release',1,lab.evm.GAS)
        self.assertEqual(original,INITIAL)

    def test_known_cases_have_more_than_one_guard_violation(self):
        good=bad=0
        for scenario in lab.SEQUENCES:
            good+=sum(c for _,_,c in self.reference('guarded',scenario))
            bad+=sum(c for _,_,c in self.reference('guard_missing',scenario))
        self.assertEqual(good,0);self.assertGreater(bad,1)

    def test_native_replay_rejects_resealed_false_verdict(self):
        self.sealed()
        self.reseal('execution.json',lambda r:r.update(vulnerability_confirmed=True))
        with patch.object(lab,'execute',return_value=synthetic_report()),self.assertRaisesRegex(lab.PauseLabError,'REPLAY_DISAGREEMENT'):
            lab.replay(self.out,self.solc,self.evm,SOURCE)

    def test_original_package_passes_mocked_replay_and_is_not_native_claim(self):
        self.sealed()
        with patch.object(lab,'execute',return_value=synthetic_report()):
            r=lab.replay(self.out,self.solc,self.evm,SOURCE)
        self.assertEqual(r['status'],'OWNED_PAUSE_EVM_REPLAY_VERIFIED')
        # Mock explicitly *is not* independent native execution; this validates serialization only.

    def test_external_source_digest_required(self):
        self.sealed()
        with self.assertRaisesRegex(lab.PauseLabError,'EXTERNAL_CODE_MISMATCH'):
            lab.replay(self.out,self.solc,self.evm,'b'*64)

    def test_tampered_audit_resealed_rejected(self):
        self.sealed()
        self.reseal('audit.json',lambda a:a['entries'][0]['data'].update(source_digest='z'*64))
        with patch.object(lab,'execute',return_value=synthetic_report()),self.assertRaisesRegex(lab.PauseLabError,'AUDIT_OR_REVIEW_MISMATCH'):
            lab.replay(self.out,self.solc,self.evm,SOURCE)

    def test_extra_file_rejected(self):
        self.sealed();(self.out/'extra.json').write_text('{}')
        with self.assertRaisesRegex(lab.PauseLabError,'BUNDLE_FILES'):
            lab.replay(self.out,self.solc,self.evm,SOURCE)

    def test_no_overwrite(self):
        self.sealed()
        with self.assertRaisesRegex(lab.PauseLabError,'NEW_PRIVATE_OUTPUT'):
            lab.create(self.out,self.solc,self.evm,SOURCE)

    def test_cli_rejects_arbitrary_paths_without_echoing(self):
        with redirect_stdout(io.StringIO()) as captured:
            code=lab.main(['verify-owned-pause-lab','--bundle',str(self.root/'SECRET') ,
                           '--solc',str(self.solc),'--evm',str(self.evm),'--source-digest',SOURCE])
        self.assertEqual(code,2)
        self.assertNotIn('SECRET',captured.getvalue())

    def test_no_network_or_child_process_when_mocked(self):
        self.sealed()
        with patch('socket.socket',side_effect=AssertionError),patch('subprocess.run',side_effect=AssertionError),\
             patch.object(lab,'execute',return_value=synthetic_report()):
            self.assertEqual(lab.replay(self.out,self.solc,self.evm,SOURCE)['native_calls'],80)

    def test_compiler_wrong_layout_rejected(self):
        from superhunter import evm_pause_family as m
        contract={'evm':{'deployedBytecode':{'object':'abcd'}},
                  'storageLayout':{'storage':[{'label':'remaining','slot':'4','offset':0,'type':'t_uint16'}],
                                   'types':{'t_uint16':{'label':'uint16'}}}}
        with self.assertRaisesRegex(lab.PauseLabError,'OWNED_LAYOUT_CHANGED'):
            m.decode({m.evm.RECEIVER:{'code':'0xabcd','storage':{}}},contract)


if __name__=='__main__':unittest.main()
