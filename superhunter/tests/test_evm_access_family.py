"""Own-contract access regression; mocked output is for I/O tests ONLY.

The independently executed Geth/solc acceptance is in the validation folder,
not represented by mocks or fake native tool calls in this unit suite.
"""
from __future__ import annotations

from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

from superhunter import evm_access_family as a, evm_execution as evm, evm_access_worker as guest_worker, evm_access_runner as guest_runner
from superhunter.safe_io import canonical, strict_json

ADMIN = evm.SENDER
GUEST = a.GUEST
BASE = {'admin':ADMIN,'remaining':10,'distributed':0}
SRC = 'a'*64


def synthetic_result():
    """In-memory serialization fixture. NOT native evidence or a vulnerability."""
    cases={v:{g:[] for g in a.CODEGEN} for v in a.VARIANTS}
    return {'source_digest':SRC,'native_constructor_calls':4,'native_runtime_calls':64,
            'known_unauthorized_persistent_effects_one_profile':{'protected':0,'missing_auth_guard':1},
            'cases':cases,'solc_sha256':'b'*64,'evm_sha256':'c'*64}


class AccessFamilyTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.base=Path(tmp.name)
        self.out=self.base/'result'
        self.solc=self.base/'placeholder-solc'
        self.evm=self.base/'placeholder-evm'

    def _given(self, variant, caller, amount=2, gas=evm.GAS, state=None):
        return a.reference(variant,deepcopy(state or BASE),caller,amount,gas)

    def _create_synthetic(self):
        with patch.object(a,'execute',return_value=synthetic_result()):
            return a.create(self.out,self.solc,self.evm,SRC)

    def _reseal(self, name, update):
        path=self.out/name
        if name.endswith('.json'):
            v=strict_json(path.read_bytes());update(v);raw=canonical(v)
        else:
            v=path.read_bytes();raw=update(v)
        path.write_bytes(raw)
        m=strict_json((self.out/'COMPLETE.json').read_bytes());m['sha256'][name]=a.sha(raw)
        (self.out/'COMPLETE.json').write_bytes(canonical(m))

    def test_guest_blocked_with_guard(self):
        r=self._given('protected',GUEST)
        self.assertEqual(r['status'],'REVERTED')
        self.assertEqual(r['state'],BASE)
        self.assertFalse(a.unauthorized_effect(GUEST,2,r['status'],BASE,r['state']))

    def test_mutant_guest_commits_known_effect(self):
        r=self._given('missing_auth_guard',GUEST)
        self.assertEqual(r['status'],'COMMITTED')
        self.assertEqual((r['state']['remaining'],r['state']['distributed']),(8,2))
        self.assertTrue(a.unauthorized_effect(GUEST,2,r['status'],BASE,r['state']))

    def test_authorized_caller_commits_in_both_variants(self):
        for variant in a.VARIANTS:
            with self.subTest(variant=variant):
                r=self._given(variant,ADMIN,3)
                self.assertEqual(r['state']['remaining'],7)
                self.assertEqual(r['status'],'COMMITTED')
                self.assertFalse(a.unauthorized_effect(ADMIN,3,r['status'],BASE,r['state']))

    def test_only_guard_line_differs(self):
        good=a.owned_source('protected')
        bad=a.owned_source('missing_auth_guard')
        self.assertEqual(good.replace(a.AUTH_GUARD,''),bad)
        self.assertIn('msg.sender == admin',good)
        self.assertNotIn('msg.sender == admin',bad)

    def test_fixed_two_callers_and_scenarios(self):
        self.assertEqual(len(a.SEQUENCES),4)
        self.assertEqual(len({canonical(s) for s in a.SEQUENCES}),4)
        self.assertTrue(all(len(s)==4 for s in a.SEQUENCES))
        self.assertEqual({c for seq in a.SEQUENCES for c,_,_ in seq},{ADMIN,GUEST})
        self.assertTrue(all(g in (1,evm.GAS) for seq in a.SEQUENCES for _,_,g in seq))

    def test_bad_amount_and_boolean_rejected(self):
        for n in (-1,256,True,'4',None,5.5):
            with self.subTest(value=n),self.assertRaises(a.AccessLabError):
                a.reference('protected',BASE,GUEST,n,evm.GAS)

    def test_wrong_caller_and_gas_rejected(self):
        for sender,gas in [('0x'+'33'*20,evm.GAS),(GUEST,0),(GUEST,True)]:
            with self.subTest(sender=sender,gas=gas),self.assertRaises(a.AccessLabError):
                a.reference('protected',BASE,sender,2,gas)

    def test_unknown_variant_and_codegen_rejected(self):
        for v in ('external',None,False,'../other'):
            with self.subTest(v=v),self.assertRaises(a.AccessLabError):a.owned_source(v)
        for g in ('unverified','new',True):
            with self.subTest(g=g),self.assertRaises(a.AccessLabError):a.compile_input('protected',g)

    def test_oog_does_not_commit_for_either_caller(self):
        for sender in (ADMIN,GUEST):
            for variant in a.VARIANTS:
                with self.subTest(sender=sender,variant=variant):
                    r=self._given(variant,sender,2,1)
                    self.assertEqual(r['status'],'OUT_OF_GAS')
                    self.assertEqual(r['state'],BASE)

    def test_overdraw_reverts_even_for_mutant(self):
        for sender in (ADMIN,GUEST):
            for variant in a.VARIANTS:
                r=self._given(variant,sender,11)
                self.assertEqual(r['status'],'REVERTED')
                self.assertEqual(r['state'],BASE)

    def test_zero_distribution_not_unauthorized_effect(self):
        self.assertFalse(a.unauthorized_effect(GUEST,0,'COMMITTED',BASE,BASE))

    def test_reverted_change_not_considered_committed(self):
        changed={**BASE,'remaining':8,'distributed':2}
        self.assertFalse(a.unauthorized_effect(GUEST,2,'REVERTED',BASE,changed))

    def test_missing_value_does_not_infer_effect(self):
        self.assertFalse(a.unauthorized_effect(GUEST,2,'COMMITTED',BASE,BASE))

    def test_reference_does_not_modify_input(self):
        s=deepcopy(BASE)
        self._given('missing_auth_guard',GUEST,state=s)
        self.assertEqual(s,BASE)

    def test_full_reference_never_breaks_unit_conservation(self):
        for variant in a.VARIANTS:
            for seq in a.SEQUENCES:
                current=dict(BASE)
                for sender,amount,gas in seq:
                    current=a.reference(variant,current,sender,amount,gas)['state']
                    self.assertEqual(current['remaining']+current['distributed'],10)

    def test_mutant_has_persistent_unauthorized_effects(self):
        effects={}
        for variant in a.VARIANTS:
            count=0
            for seq in a.SEQUENCES:
                state=dict(BASE)
                for caller,amount,gas in seq:
                    r=a.reference(variant,state,caller,amount,gas)
                    count+=a.unauthorized_effect(caller,amount,r['status'],state,r['state'])
                    state=r['state']
            effects[variant]=count
        self.assertEqual(effects['protected'],0)
        self.assertGreater(effects['missing_auth_guard'],0)

    def test_compiler_input_sandboxed(self):
        one=a.compile_input('protected','legacy')
        two=a.compile_input('protected','ir_optimized')
        self.assertEqual(one['sources'],two['sources'])
        self.assertEqual(set(one['sources']),{a.SOURCE_FILE})
        self.assertFalse(one['settings']['optimizer']['enabled'])
        self.assertTrue(two['settings']['viaIR'])
        self.assertNotIn('urls',one['sources'][a.SOURCE_FILE])

    def test_layout_decode_uses_packed_admin_address(self):
        # This simple packed word and contract dict are SYNTHETIC unit inputs.
        slots=[{'label':label,'slot':slot,'offset':offset,'type':typ}
               for label,slot,offset,typ in a.SLOT_STORAGE]
        types={r['type']:{'label':r['type']} for r in slots}
        contract={'storageLayout':{'storage':slots,'types':types},
                  'evm':{'deployedBytecode':{'object':'6000'}}}
        word=int(ADMIN,16)+(10<<160)+(0<<176)
        alloc={evm.RECEIVER:{'code':'0x6000','storage':{evm.SLOT:hex(word)}}}
        self.assertEqual(a.decode(alloc,contract),BASE)
        alloc[evm.RECEIVER]['storage'][evm.SLOT]=hex(word+1)
        with self.assertRaisesRegex(a.AccessLabError,'ADMIN_NOT_FROM_CONSTRUCTOR'):
            a.decode(alloc,contract)

    def test_overhigh_storage_bits_rejected(self):
        slots=[{'label':label,'slot':slot,'offset':offset,'type':typ}
               for label,slot,offset,typ in a.SLOT_STORAGE]
        c={'storageLayout':{'storage':slots,'types':{r['type']:{'label':r['type']} for r in slots}},
           'evm':{'deployedBytecode':{'object':'6000'}}}
        alloc={evm.RECEIVER:{'code':'0x6000','storage':{evm.SLOT:hex(int(ADMIN,16)+(10<<160)+(1<<200))}}}
        with self.assertRaisesRegex(a.AccessLabError,'ADMIN_NOT_FROM_CONSTRUCTOR'):
            a.decode(alloc,c)

    def test_guest_runner_denies_bad_calldata_without_process(self):
        with patch('subprocess.Popen',side_effect=AssertionError):
            with self.assertRaisesRegex(evm.EVMError,'GUEST_CALL_PROFILE'):
                guest_runner.run_guest(b'fake',prestate=evm.genesis(),calldata='bad',gas=evm.GAS)

    def test_guest_worker_denies_arbitrary_caller_argument(self):
        with patch('sys.argv',['worker','5','0'*72,str(evm.GAS),'0x'+'44'*20]):
            with self.assertRaisesRegex(ValueError,'FIXED_GUEST_WORKER_ARGUMENTS'):
                guest_worker.main()

    def test_guest_worker_denies_creation_syntax(self):
        with patch('sys.argv',['worker','5','-',str(evm.GAS)]):
            with self.assertRaisesRegex(ValueError,'FIXED_GUEST_WORKER_DATA'):
                guest_worker.main()

    def test_default_run_parser_still_rejects_guest_account(self):
        raw=b'{"root":"'+b'0'*64+b'","accounts":{"'+GUEST.encode()+b'":{"address":"'+GUEST.encode()+b'","balance":"0","nonce":1}}}'
        with self.assertRaisesRegex(evm.EVMError,'UNEXPECTED_EVM_ACCOUNT'):
            evm.parse_run(raw)
        self.assertEqual(guest_runner.GUEST,GUEST)

    def test_summary_never_promises_discovery(self):
        report=synthetic_result()
        self.assertIn('No hay hallazgo externo',a.render(report).decode())

    def test_output_is_private_and_not_overwritten(self):
        self._create_synthetic()
        self.assertEqual(self.out.stat().st_mode&0o777,0o700)
        for f in self.out.iterdir():self.assertEqual(f.stat().st_mode&0o777,0o600)
        with self.assertRaises(a.AccessLabError):self._create_synthetic()

    def test_synthetic_roundtrip_checks_all_originals(self):
        self._create_synthetic()
        with patch.object(a,'execute',return_value=synthetic_result()) as execute:
            checked=a.replay(self.out,self.solc,self.evm,SRC)
            self.assertEqual(checked['status'],'OWNED_ACCESS_EVM_REPLAY_VERIFIED')
            execute.assert_called_once_with(self.solc,self.evm,SRC)

    def test_forged_report_rejected_with_replay(self):
        self._create_synthetic()
        self._reseal('execution.json',lambda d:d['known_unauthorized_persistent_effects_one_profile'].update(protected=5))
        with patch.object(a,'execute',return_value=synthetic_result()):
            with self.assertRaisesRegex(a.AccessLabError,'NATIVE_REPLAY_DISAGREEMENT'):
                a.replay(self.out,self.solc,self.evm,SRC)

    def test_resealed_audit_rejected(self):
        self._create_synthetic()
        self._reseal('audit.json',lambda d:d.update(producer_authenticated=True))
        with patch.object(a,'execute',return_value=synthetic_result()):
            with self.assertRaisesRegex(a.AccessLabError,'AUDIT_OR_REPORT_MISMATCH'):
                a.replay(self.out,self.solc,self.evm,SRC)

    def test_external_source_digest_required(self):
        self._create_synthetic()
        with self.assertRaisesRegex(a.AccessLabError,'WRONG_EXTERNAL_CODE_REFERENCE'):
            a.replay(self.out,self.solc,self.evm,'0'*64)

    def test_extra_bundle_file_is_rejected(self):
        self._create_synthetic();(self.out/'extra.json').write_text('{}')
        with self.assertRaisesRegex(a.AccessLabError,'BUNDLE_FILES'):
            a.replay(self.out,self.solc,self.evm,SRC)

    def test_cli_rejects_missing_real_bins_with_no_false_claims(self):
        with redirect_stdout(io.StringIO()) as output:
            status=a.main(['run-owned-access-lab','--solc',str(self.solc),
                           '--evm',str(self.evm),'--source-digest',SRC,'--out',str(self.out)])
        self.assertEqual(status,2)
        self.assertFalse(json.loads(output.getvalue())['vulnerability_confirmed'])
        self.assertFalse(self.out.exists())

    def test_cli_forbids_network_parameters(self):
        with patch('sys.stderr',new_callable=io.StringIO) as errors,self.assertRaises(SystemExit):
            a.main(['run-owned-access-lab','--solc','/x','--evm','/y','--source-digest',SRC,
                    '--out',str(self.out),'--rpc','https://example.invalid'])
        self.assertNotIn('https://example.invalid',errors.getvalue())

    def test_package_entrypoint_dispatch(self):
        from superhunter import __main__
        with patch('sys.argv',['superhunter','run-owned-access-lab','--solc',str(self.solc),
                               '--evm',str(self.evm),'--source-digest',SRC,'--out',str(self.out)]),redirect_stdout(io.StringIO()) as output:
            status=__main__.main()
        self.assertEqual(status,2)
        self.assertEqual(json.loads(output.getvalue())['status'],'OWNED_ACCESS_EVM_BLOCKED')


if __name__ == '__main__':unittest.main()
