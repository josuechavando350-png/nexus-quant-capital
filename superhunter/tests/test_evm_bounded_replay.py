"""Independent bounded EVM stack/PC replay: synthetic owned traces only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import evm_bounded_replay as r
from superhunter import evm_forensic_binding as b
from superhunter import journal_ingest as j
from superhunter.safe_io import canonical, strict_json


def geth_fixture(code: str, pcs: list[int]) -> bytes:
    names = {0x00:'STOP',0x01:'ADD',0x02:'MUL',0x03:'SUB',0x10:'LT',0x11:'GT',
             0x14:'EQ',0x15:'ISZERO',0x16:'AND',0x17:'OR',0x18:'XOR',0x19:'NOT',
             0x1b:'SHL',0x1c:'SHR',0x50:'POP',0x54:'SLOAD',0x56:'JUMP',
             0x57:'JUMPI',0x5b:'JUMPDEST',0x5f:'PUSH0',0x80:'DUP1',0x90:'SWAP1'}
    raw=bytes.fromhex(code)
    events=[]
    for i,pc in enumerate(pcs):
        op=raw[pc]
        name=(f'PUSH{op-0x5f}' if 0x60<=op<=0x7f else
              f'DUP{op-0x7f}' if 0x80<=op<=0x8f else
              f'SWAP{op-0x8f}' if 0x90<=op<=0x9f else names[op])
        row={'pc':pc,'op':op,'gas':hex(1000-i*7),'gasCost':'0x3',
             'memSize':0,'stack':None,'depth':1,'refund':0,'opName':name}
        events.append(json.dumps(row).encode()+b'\n')
    events.append(b'{"output":"","gasUsed":"0x20"}\n')
    return b''.join(events)


class BoundedReplayTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.dir=Path(t.name)
        self.log=self.dir/'events.jsonl'
        self.trace=self.dir/'trace.jsonl'
        self.context=self.dir/'context.json'
        self.journal=self.dir/'journal'
        self.parent=self.dir/'parent'
        self.out=self.dir/'replay'
        self.secret='SECRET_PRIVACY_OWNED_ONLY'
        self.prepare()

    def prepare(self, code='600160075760005b00', pcs=None):
        pcs=[0,2,4,7,8] if pcs is None else pcs
        self.trace.write_bytes(geth_fixture(code,pcs))
        digest=hashlib.sha256(self.trace.read_bytes()).hexdigest()
        rows=[{'__REALTIME_TIMESTAMP':'1793984400123456','__CURSOR':'lab-cursor',
               'MESSAGE':self.secret, b.ANCHOR_FIELD:digest}]
        self.log.write_bytes(b''.join(json.dumps(x).encode()+b'\n' for x in rows))
        if self.journal.exists():
            import shutil
            shutil.rmtree(self.journal)
        if self.parent.exists():
            import shutil
            shutil.rmtree(self.parent)
        j.ingest(self.log,'owned-lab',5,self.journal)
        projection=strict_json((self.journal/'normalized.json').read_bytes())
        self.context.write_bytes(canonical({
            'schema_version':1,'profile':b.PROFILE,'bytecode_hex':code,
            'gas_budget':b.op.evm.GAS,'observed':{'return_data':'0x','error':None},
            'journal_event_id':projection['events'][0]['event_id']}))
        b.review(self.journal,self.trace,self.context,self.parent)

    def _res(self):
        result=r.review(self.parent,self.out)
        self.assertEqual(result,r.verify(self.out))
        return strict_json((self.out/'semantic.json').read_bytes())

    def _reseal(self, filename, raw):
        (self.out/filename).write_bytes(raw)
        marker=strict_json((self.out/'COMPLETE.json').read_bytes())
        marker['sha256'][filename]=r.sha(raw)
        (self.out/'COMPLETE.json').write_bytes(canonical(marker))

    def test_cli_separate_processes(self):
        cmd=[sys.executable,'-B','-m','superhunter']
        a=subprocess.run(cmd+['replay-evm-forensic','--bundle',str(self.parent),
                              '--out',str(self.out)],capture_output=True,text=True)
        self.assertEqual(a.returncode,0,a.stderr)
        bproc=subprocess.run(cmd+['verify-evm-replay','--bundle',str(self.out)],
                             capture_output=True,text=True)
        self.assertEqual(bproc.returncode,0,bproc.stderr)
        self.assertEqual(json.loads(a.stdout),json.loads(bproc.stdout))
        self.assertNotIn(self.secret,a.stdout+a.stderr+bproc.stdout+bproc.stderr)

    def test_taken_branch_and_every_pc_real_operand(self):
        result=self._res()
        self.assertEqual(result['status'],'BOUNDED_STACK_PC_REPLAY_MATCH')
        self.assertEqual(result['step_count'],5)
        self.assertEqual(result['computed_jump_edges'],[
            {'at_pc':4,'next_pc':7,'taken':True}])
        self.assertEqual(result['opcode_counts']['PUSH'],2)
        self.assertTrue(result['claims']['bounded_stack_pc_semantics_replayed'])
        for key in ['full_evm_execution_replayed','native_evm_engine_invoked',
                    'gas_costs_replayed','source_and_trace_producer_authenticated',
                    'vulnerability_confirmed','incident_confirmed']:
            self.assertFalse(result['claims'][key])

    def test_false_branch(self):
        self.prepare('600060075760005b00',[0,2,4,5,7,8])
        self.assertEqual(self._res()['computed_jump_edges'],[
            {'at_pc':4,'next_pc':5,'taken':False}])

    def test_fake_taken_branch_rejected(self):
        self.prepare('600060075760005b00',[0,2,4,7,8])
        with self.assertRaisesRegex(r.ReplayError,'SEMANTIC_PC_MISMATCH'):
            r.review(self.parent,self.out)
        self.assertFalse(self.out.exists())

    def test_fake_fallthrough_rejected(self):
        self.prepare('600160075760005b00',[0,2,4,5,7,8])
        with self.assertRaisesRegex(r.ReplayError,'SEMANTIC_PC_MISMATCH'):
            r.review(self.parent,self.out)

    def test_wrong_stack_jump_target_even_when_reported_pc_valid(self):
        self.prepare('600160085760005b00',[0,2,4,7,8])
        with self.assertRaisesRegex(r.ReplayError,'INVALID_JUMPDEST'):
            r.review(self.parent,self.out)

    def test_unconditional_jump(self):
        self.prepare('6005565b005b00',[0,2,5,6])
        self.assertEqual(self._res()['computed_jump_edges'],[
            {'at_pc':2,'next_pc':5,'taken':True}])

    def test_stops_immediately(self):
        self.prepare('00',[0])
        self.assertEqual(self._res()['step_count'],1)

    def test_arithmetic_stack_replay(self):
        self.prepare('600260030100',[0,2,4,5])
        self.assertEqual(self._res()['opcode_counts']['ADD'],1)

    def test_multiplication_and_subtraction(self):
        # (2*3) then 4-6, well-defined two-operand stack arithmetic.
        self.prepare('600260030260040300',[0,2,4,5,7,8])
        result=self._res()
        self.assertEqual(result['opcode_counts']['MUL'],1)
        self.assertEqual(result['opcode_counts']['SUB'],1)

    def test_comparisons_and_bitwise(self):
        self.prepare('600160011400',[0,2,4,5])
        self.assertEqual(self._res()['opcode_counts']['EQ'],1)

    def test_push0_is_handled(self):
        self.prepare('5f5000',[0,1,2])
        self.assertEqual(self._res()['opcode_counts']['PUSH0'],1)

    def test_dup_and_swap(self):
        self.prepare('600180145000',[0,2,3,4,5])
        self.assertEqual(self._res()['opcode_counts']['DUP'],1)
        self.out.rename(self.dir/'completed')
        self.prepare('600160029000',[0,2,4,5])
        self.assertEqual(self._res()['opcode_counts']['SWAP'],1)

    def test_stack_underflow(self):
        self.prepare('5700',[0,1])
        with self.assertRaisesRegex(r.ReplayError,'STACK_UNDERFLOW'):
            r.review(self.parent,self.out)

    def test_unsupported_opcode_refused(self):
        self.prepare('5400',[0,1])
        with self.assertRaisesRegex(r.ReplayError,'UNSUPPORTED_OPCODE'):
            r.review(self.parent,self.out)

    def test_non_terminating_trace_rejected(self):
        self.prepare('6001',[0])
        with self.assertRaisesRegex(r.ReplayError,'TRACE_DID_NOT_REACH_STOP'):
            r.review(self.parent,self.out)

    def test_truncated_push_rejected(self):
        context=strict_json(self.context.read_bytes())
        context['bytecode_hex']='60'
        with self.assertRaisesRegex(r.ReplayError,'TRUNCATED_PUSH'):
            r.replay(geth_fixture('600100',[0,2]),canonical(context))

    def test_resealed_false_semantic_verdict_rejected(self):
        self._res()
        false=strict_json((self.out/'semantic.json').read_bytes())
        false['claims']['full_evm_execution_replayed']=True
        self._reseal('semantic.json',canonical(false))
        with self.assertRaisesRegex(r.ReplayError,'REPLAY_RESULT_MISMATCH'):
            r.verify(self.out)

    def test_resealed_false_receipt_rejected(self):
        self._res()
        v=strict_json((self.out/'replay-receipt.json').read_bytes())
        v['semantic_sha256']='0'*64
        self._reseal('replay-receipt.json',canonical(v))
        with self.assertRaisesRegex(r.ReplayError,'REPLAY_RESULT_MISMATCH'):
            r.verify(self.out)

    def test_parent_capture_tamper_rejected_after_resealing(self):
        self._res()
        original=(self.out/'journal.jsonl').read_bytes()
        self._reseal('journal.jsonl',original.replace(self.secret.encode(),b'X'*len(self.secret)))
        with self.assertRaisesRegex(r.ReplayError,'PARENT_BYTES_TAMPERED'):
            r.verify(self.out)

    def test_parent_manifest_not_replaceable(self):
        self._res()
        v=strict_json((self.out/'parent-complete.json').read_bytes())
        v['sha256']['trace.jsonl']='0'*64
        self._reseal('parent-complete.json',canonical(v))
        with self.assertRaisesRegex(r.ReplayError,'PARENT_BYTES_TAMPERED'):
            r.verify(self.out)

    def test_report_reseal_rejected(self):
        self._res()
        self._reseal('REPLAY.md',b'A certified real-world vulnerability\n')
        with self.assertRaisesRegex(r.ReplayError,'REPLAY_REPORT_MISMATCH'):
            r.verify(self.out)

    def test_external_pin_rejects_resealed_bundle(self):
        self._res()
        pin=r.sha((self.out/'COMPLETE.json').read_bytes())
        self.assertEqual(r.verify(self.out,pin)['step_count'],5)
        with self.assertRaisesRegex(r.ReplayError,'EXTERNAL_SHA_MISMATCH'):
            r.verify(self.out,'0'*64)

    def test_extra_file_rejected(self):
        self._res()
        (self.out/'evil.txt').write_text('payload')
        with self.assertRaisesRegex(r.ReplayError,'BUNDLE_MANIFEST'):
            r.verify(self.out)

    def test_private_output_permissions(self):
        self._res()
        self.assertEqual(self.out.stat().st_mode & 0o777,0o700)
        self.assertNotIn(self.secret,(self.out/'REPLAY.md').read_text())
        self.assertNotIn(self.secret,(self.out/'semantic.json').read_text())
        self.assertIn(self.secret,(self.out/'journal.jsonl').read_text())

    def test_source_change_rejects_verification(self):
        self._res()
        with patch.object(r,'snapshot',return_value={'modified':'1'}):
            with self.assertRaisesRegex(r.ReplayError,'SOURCE_CHANGED'):
                r.verify(self.out)

    def test_bool_pc_not_accepted(self):
        ctx=self.context.read_bytes()
        fake=geth_fixture('00',[0]).replace(b'"pc": 0',b'"pc": true')
        with self.assertRaisesRegex(r.ReplayError,'TRACE_PC_OP'):
            r.replay(fake,ctx)

    def test_quality_contract_connected(self):
        from superhunter import quality
        c=quality.COMPONENTS['evm_bounded_replay']
        self.assertIn('evm_forensic_binding',c['depends'])
        self.assertIn('test_evm_bounded_replay.',c['tests'])
        self.assertIn('evm_bounded_replay',quality.COMPONENTS['entrypoints']['depends'])

    def test_qa_partition_keeps_previous_tests_and_new_test_module(self):
        from superhunter.quality_worker import partition_ids
        ids=['test_evm_forensic_binding.Test.test_a','test_journal_correlation.Test.test_b',
             'test_evm_bounded_replay.Test.test_c','test_holdout_protocol.Test.test_d']
        groups=partition_ids(ids,8)
        self.assertEqual(len([x for g in groups for x in g]),len(ids))
        self.assertEqual([x for g in groups for x in g if x.startswith('test_evm_bounded_replay')],
                         ['test_evm_bounded_replay.Test.test_c'])

if __name__ == '__main__':
    unittest.main()
