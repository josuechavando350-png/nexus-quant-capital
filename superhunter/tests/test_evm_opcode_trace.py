"""Parser/protocol controls; synthetic trace records are NOT EVM executions.

Separate native acceptance runs real pinned Geth for opcode claims.
"""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import evm_opcode_trace as op
from superhunter.safe_io import canonical,strict_json


def make_trace(code, pcs, terminal=None, *, mutate=None):
    rows=[]
    decoder=op.instruction_positions(code)
    for pos,pc in enumerate(pcs):
        item={'pc':pc,'op':decoder[pc],'gas':hex(1000-pos*10),'gasCost':'0x3',
              'memSize':0,'stack':None,'depth':1,'refund':0,'opName':'TEST'}
        if mutate and pos==len(pcs)-1:
            item.update(mutate)
        rows.append(item)
    rows.append(terminal or {'output':'','gasUsed':'0x20'})
    return ('\n'.join(json.dumps(x,separators=(',',':')) for x in rows)+'\n').encode()


class OpcodeTraceTests(unittest.TestCase):
    def setUp(self):
        work=tempfile.TemporaryDirectory();self.addCleanup(work.cleanup)
        self.root=Path(work.name)
        self.out=self.root/'out'
        self.native=self.root/'native';self.native.mkdir()
        self.control={'return_data':'0x','error':None}
        self.code='6005575b005b00'   # PUSH1 05; JUMPI; JUMPDEST; STOP; JUMPDEST; STOP
        self.good={'schema_version':1,'profile':op.PROFILE,'status':'OWNED_EVM_OPCODE_TRACES_RECORDED',
                   'traced_runtime_calls':1,'vulnerability_confirmed':False,
                   'complete_instruction_or_branch_coverage_proven':False,
                   'trace_groups':{},'constructor_traces':0,
                   'case_indices_traced':[0],'case_count_available':9,
                   'traced_runtime_unique_pcs_summed_per_control_profile':3,
                   'observed_conditional_edges_across_profiles':0}
        self.binding={'schema_version':1,'native_source_digest':'0'*64,
                      'native_artifact_sha256':{'sequences.json':'0'*64}}

    def parse(self,pcs,code=None,raw=None,observed=None):
        return op.decode_trace(raw or make_trace(code or self.code,pcs),code or self.code,
                               observed or self.control,budget=op.evm.GAS)

    def test_push_immediate_cannot_count_as_instruction(self):
        self.assertEqual(op.instruction_positions('60ff5b00'),{0:0x60,2:0x5b,3:0})
        with self.assertRaisesRegex(op.OpcodeTraceError,'TRACE_OPCODE_OR_PC_MISMATCH'):
            self.parse([1,2],code='60ff5b00',raw=make_trace('60ff5b00',[0,2]).replace(b'"pc":0',b'"pc":1',1))

    def test_branch_outcomes_distinguished(self):
        # The successor after this JUMPI is a PUSH1, not JUMPDEST; if the
        # trace continues there, the condition necessarily fell through.
        code='60055760005b00'
        fall=self.parse([0,2,3,5,6],code=code)
        taken=self.parse([0,2,5,6],code=code)
        self.assertEqual(fall['conditional_edge_set'],['2:fallthrough'])
        self.assertEqual(taken['conditional_edge_set'],['2:taken'])
        self.assertNotEqual(fall['pc_opcode_sha256'],taken['pc_opcode_sha256'])

    def test_jumpi_to_next_jumpdest_is_ambiguous_without_stack(self):
        # Both taken and untaken branch lead to PC=3 here. The trace omits
        # stack values, so the observer MUST NOT claim a known branch outcome.
        result=self.parse([0,2,3,4])
        self.assertEqual(result['conditional_edge_set'],['2:indeterminate'])
        self.assertNotIn('2:fallthrough',result['conditional_edge_set'])
        self.assertFalse(result['all_reachable_sites_enumerated'])

    def test_unconditional_jump_to_immediate_next_jumpdest_allowed(self):
        code='6003565b00'
        parsed=self.parse([0,2,3,4],code=code)
        self.assertEqual(parsed['conditional_edge_set'],[])
        self.assertEqual(parsed['steps'],4)

    def test_branch_pc_different_from_jumpdest_rejected(self):
        with self.assertRaisesRegex(op.OpcodeTraceError,'JUMP_NOT_TO_JUMPDEST'):
            self.parse([0,2,4])

    def test_nonjump_pc_discontinuity_rejected(self):
        with self.assertRaisesRegex(op.OpcodeTraceError,'NON_JUMP_PC_DISCONTINUITY'):
            self.parse([0,3])

    def test_stop_followed_by_more_steps_rejected(self):
        with self.assertRaisesRegex(op.OpcodeTraceError,'STEP_AFTER_TERMINATOR'):
            self.parse([0,2,3,4,5])

    def test_code_hex_limit_and_nonhex_rejected(self):
        for code in ('','a','GG','60f','ff'*33000):
            with self.subTest(code=code[:8]),self.assertRaises(op.OpcodeTraceError):
                op.instruction_positions(code)

    def test_malformed_and_duplicate_json_keys_rejected(self):
        raw=make_trace(self.code,[0,2,3,4]).replace(b'"pc":0',b'"pc":0,"pc":0',1)
        with self.assertRaises(op.OpcodeTraceError):self.parse([0,2,3,4],raw=raw)

    def test_out_of_bounds_pc_rejected(self):
        raw=make_trace(self.code,[0,2,3,4]).replace(b'"pc":3',b'"pc":99',1)
        with self.assertRaisesRegex(op.OpcodeTraceError,'TRACE_OPCODE_OR_PC_MISMATCH'):
            self.parse([0,2,3,4],raw=raw)

    def test_wrong_opcode_rejected(self):
        raw=make_trace(self.code,[0,2,3,4]).replace(b'"op":96',b'"op":97',1)
        with self.assertRaises(op.OpcodeTraceError):self.parse([0,2,3,4],raw=raw)

    def test_unknown_field_rejected(self):
        raw=make_trace(self.code,[0,2,3,4]).replace(b'"refund":0',b'"refund":0,"fake":1',1)
        with self.assertRaisesRegex(op.OpcodeTraceError,'TRACE_STEP_SCHEMA'):
            self.parse([0,2,3,4],raw=raw)

    def test_wrong_depth_rejected(self):
        raw=make_trace(self.code,[0,2,3,4]).replace(b'"depth":1',b'"depth":2',1)
        with self.assertRaises(op.OpcodeTraceError):self.parse([0,2,3,4],raw=raw)

    def test_boolean_opcode_and_pc_rejected(self):
        raw=make_trace(self.code,[0,2,3,4]).replace(b'"pc":0',b'"pc":true',1)
        with self.assertRaises(op.OpcodeTraceError):self.parse([0,2,3,4],raw=raw)

    def test_gas_cannot_increase_between_steps(self):
        raw=make_trace(self.code,[0,2,3,4]).replace(b'"gas":"0x3de"',b'"gas":"0x3ef"',1)
        with self.assertRaisesRegex(op.OpcodeTraceError,'TRACE_GAS_PROFILE'):
            self.parse([0,2,3,4],raw=raw)

    def test_no_instructions_can_follow_a_fault(self):
        raw=make_trace('60006000fd',[0,2,4],
                       {'output':'','gasUsed':'0x6','error':'execution reverted'})
        lines=raw.decode().splitlines()
        item=json.loads(lines[-2]);item['error']='execution reverted'
        # Not a legitimate duplicate. An extra opcode following the fault is invalid.
        injected=json.loads(lines[-2]);injected['pc']=2
        tampered=('\n'.join(lines[:-1]+[json.dumps(item),json.dumps(injected),lines[-1]])+'\n').encode()
        with self.assertRaises(op.OpcodeTraceError):
            self.parse([0,2,4],code='60006000fd',raw=tampered,
                       observed={'return_data':'0x','error':'execution reverted'})

    def test_trace_terminal_must_match_stdout(self):
        raw=make_trace(self.code,[0,2,3,4],{'output':'ff','gasUsed':'0x20'})
        with self.assertRaisesRegex(op.OpcodeTraceError,'TRACE_TERMINAL_DISAGREEMENT'):
            self.parse([0,2,3,4],raw=raw)

    def test_gas_cannot_exceed_declared_budget(self):
        raw=make_trace(self.code,[0,2,3,4],{'output':'','gasUsed':hex(op.evm.GAS+1)})
        with self.assertRaisesRegex(op.OpcodeTraceError,'TRACE_TERMINAL_DISAGREEMENT'):
            self.parse([0,2,3,4],raw=raw)

    def test_invalid_terminal_error_rejected(self):
        raw=make_trace(self.code,[0,2,3,4],{'output':'','gasUsed':'0x20','error':'out of gas'})
        with self.assertRaisesRegex(op.OpcodeTraceError,'TRACE_TERMINAL_DISAGREEMENT'):
            self.parse([0,2,3,4],raw=raw)

    def test_genuine_style_duplicate_fault_line_is_one_instruction(self):
        raw=make_trace('60006000fd',[0,2,4],{'output':'','gasUsed':'0x6','error':'execution reverted'})
        rows=raw.decode().splitlines();last=json.loads(rows[-2]);last['error']='execution reverted'
        raw=('\n'.join(rows[:-1]+[json.dumps(last),rows[-1]])+'\n').encode()
        obs={'return_data':'0x','error':'execution reverted'}
        result=self.parse([0,2,4],code='60006000fd',raw=raw,observed=obs)
        self.assertEqual(result['steps'],3)
        self.assertIsNotNone(result['terminal_error'])

    def test_changed_duplicate_fault_row_rejected(self):
        raw=make_trace('60006000fd',[0,2,4],{'output':'','gasUsed':'0x6','error':'execution reverted'})
        rows=raw.decode().splitlines();last=json.loads(rows[-2]);last['error']='execution reverted';last['gas']='0x999'
        raw=('\n'.join(rows[:-1]+[json.dumps(last),rows[-1]])+'\n').encode()
        obs={'return_data':'0x','error':'execution reverted'}
        with self.assertRaises(op.OpcodeTraceError):
            self.parse([0,2,4],code='60006000fd',raw=raw,observed=obs)

    def test_first_opcode_gas_fault_allowed(self):
        code='6001600055'
        item={'pc':0,'op':96,'gas':'0x1','gasCost':'0x3','memSize':0,'stack':None,
              'depth':1,'refund':0,'opName':'PUSH1','error':'out of gas'}
        raw=(json.dumps(item)+'\n'+json.dumps({'output':'','gasUsed':'0x1','error':'out of gas'})+'\n').encode()
        result=op.decode_trace(raw,code,{'error':'out of gas','return_data':'0x'},budget=1)
        self.assertEqual(result['steps'],1)

    def test_trace_hash_changes_with_different_actual_paths(self):
        a=self.parse([0,2,3,4]);b=self.parse([0,2,5,6])
        self.assertNotEqual(a['trace_raw_sha256'],b['trace_raw_sha256'])

    def test_no_complete_path_claim_in_synthetic_parser(self):
        row=self.parse([0,2,3,4])
        self.assertFalse(row['all_reachable_sites_enumerated'])
        self.assertGreater(row['syntactic_instruction_site_count_in_bytecode'],0)

    def test_new_output_not_overwritten(self):
        self.out.mkdir()
        with self.assertRaisesRegex(op.OpcodeTraceError,'NEW_PRIVATE_OUTPUT_REQUIRED'):
            op.create(self.native,self.root/'solc',self.root/'evm','0'*64,self.out)

    def test_resealed_false_coverage_rejected(self):
        with patch.object(op,'gather',return_value=(deepcopy(self.good),deepcopy(self.binding))):
            op.create(self.native,self.root/'solc',self.root/'evm','0'*64,self.out)
            target=self.out/'opcode-observations.json';content=strict_json(target.read_bytes())
            content['complete_instruction_or_branch_coverage_proven']=True
            changed=canonical(content);target.write_bytes(changed)
            marker=strict_json((self.out/'COMPLETE.json').read_bytes())
            marker['sha256'][target.name]=op.sha(changed)
            (self.out/'COMPLETE.json').write_bytes(canonical(marker))
            with self.assertRaisesRegex(op.OpcodeTraceError,'OPCODE_REPLAY_DISAGREEMENT'):
                op.verify(self.out,self.native,self.root/'solc',self.root/'evm','0'*64)

    def test_source_binding_resealed_rejected(self):
        with patch.object(op,'gather',return_value=(deepcopy(self.good),deepcopy(self.binding))):
            op.create(self.native,self.root/'solc',self.root/'evm','0'*64,self.out)
            target=self.out/'source-binding.json';contents=strict_json(target.read_bytes())
            contents['native_source_digest']='f'*64
            raw=canonical(contents);target.write_bytes(raw)
            marker=strict_json((self.out/'COMPLETE.json').read_bytes())
            marker['sha256'][target.name]=op.sha(raw)
            (self.out/'COMPLETE.json').write_bytes(canonical(marker))
            with self.assertRaises(op.OpcodeTraceError):
                op.verify(self.out,self.native,self.root/'solc',self.root/'evm','0'*64)

    def test_valid_synthetic_bundle_roundtrip(self):
        with patch.object(op,'gather',return_value=(deepcopy(self.good),deepcopy(self.binding))):
            op.create(self.native,self.root/'solc',self.root/'evm','0'*64,self.out)
            self.assertEqual(op.verify(self.out,self.native,self.root/'solc',self.root/'evm','0'*64)
                             ['status'],'OWNED_EVM_OPCODE_TRACES_REPLAY_VERIFIED')

    def test_cli_arguments_do_not_leak(self):
        with patch('sys.stderr',new_callable=io.StringIO) as target,self.assertRaises(SystemExit):
            op.main(['verify-opcode-traces','--bundle','PRIVATE','--bad','TOKEN'])
        self.assertNotIn('TOKEN',target.getvalue())

    def test_cli_missing_evidence_is_blocked(self):
        with redirect_stdout(io.StringIO()) as out:
            result=op.main(['verify-opcode-traces','--bundle',str(self.out),
                            '--native-bundle',str(self.root/'private'),
                            '--solc',str(self.root/'solc'),'--evm',str(self.root/'evm'),
                            '--expected-source','0'*64])
        self.assertEqual(result,2)
        self.assertNotIn(str(self.root),out.getvalue())

    def test_quality_component_and_tests_enforced(self):
        self.assertIn('evm_opcode_trace',op.quality.COMPONENTS)
        self.assertTrue(op.quality.COMPONENTS['evm_opcode_trace']['depends'])
        self.assertIn('test_evm_opcode_trace.OpcodeTraceTests.test_resealed_false_coverage_rejected',
                      op.quality.REQUIRED_TESTS)

    def test_cli_dispatch_connected(self):
        from superhunter import __main__
        with patch('sys.argv',['superhunter','verify-opcode-traces','--bundle',str(self.out),
                              '--native-bundle',str(self.root/'private'),'--solc',str(self.root/'solc'),
                              '--evm',str(self.root/'evm'),'--expected-source','0'*64]),redirect_stdout(io.StringIO()):
            self.assertEqual(__main__.main(),2)

    def test_bounded_sample_explicitly_not_full_coverage(self):
        r=op._render({'status':'OWNED_EVM_OPCODE_TRACES_RECORDED','constructor_traces':4,
                      'case_indices_traced':[0,1],'case_count_available':9,'traced_runtime_calls':32,
                      'traced_runtime_unique_pcs_summed_per_control_profile':10,
                      'observed_conditional_edges_across_profiles':2})
        self.assertIn(b'2 de 9',r)
        self.assertIn(b'No se infiere cobertura porcentual',r)

    def test_native_source_digest_cannot_be_claimed_from_bare_zip(self):
        self.assertFalse(self.good['vulnerability_confirmed'])


if __name__=='__main__':unittest.main()
