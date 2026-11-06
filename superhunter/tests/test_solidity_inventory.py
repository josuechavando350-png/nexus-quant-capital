"""Direct source reads and adversarial artifact checks; AST fixtures are synthetic.

No compiler was invoked to produce these ASTs. The parser examines full source
bytes, including comments and opaque bodies, independently of AST inventories.
"""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_storage_placement as previous
import test_source_types as typed
from superhunter import compiler_layout as cl, solidity_inventory as si, quality
from superhunter.safe_io import canonical, strict_json


def parse(body, prefix='pragma solidity ^0.8.30;\n'):
    return si.parse_source((prefix+'contract Ledger {\n'+body+'\n}\n').encode(),'Ledger')


def add_member(pair, text):
    inp,out=pair
    source=inp['sources']['Local.sol']['content']
    at=source.rfind('}')
    source=source[:at]+text+'\n'+source[at:]
    inp['sources']['Local.sol']['content']=source
    raw=source.encode()
    ast=out['sources']['Local.sol']['ast'];c=ast['nodes'][0]
    start=int(c['src'].split(':')[0])
    ast['src']=f'0:{len(raw)}:0';c['src']=f'{start}:{raw.rfind(b"}")+1-start}:0'


class SourceInventoryParserTests(unittest.TestCase):
    def test_two_declarations_obtained_from_source(self):
        r=parse('uint128 first;\nuint128 second;')
        self.assertEqual([d['name'] for d in r['declarations']],['first','second'])
        self.assertEqual([d['shape'] for d in r['declarations']],[('elementary','uint128')]*2)

    def test_utf8_comments_preserve_byte_offsets(self):
        raw='// áéí\ncontract Ledger { uint128 café; }'.encode()
        with self.assertRaises(si.InventoryNeedsReview):si.parse_source(raw,'Ledger')
        raw='// áéí\ncontract Ledger { /* ñ */ uint128 amount; }'.encode()
        d=si.parse_source(raw,'Ledger')['declarations'][0]
        self.assertEqual(raw[d['name_start']:d['name_end']],b'amount')
        self.assertEqual(d['name_start'],raw.index(b'amount'))

    def test_comments_do_not_create_phantom_variables(self):
        r=parse('// uint256 fake; }\n uint128 live; /* uint256 fake2; { */')
        self.assertEqual([d['name'] for d in r['declarations']],['live'])

    def test_comments_inside_type_and_qualifiers(self):
        d=parse('uint128/* one */public/* two */balance;')['declarations'][0]
        self.assertEqual(d['visibility'],'public');self.assertEqual(d['shape'],('elementary','uint128'))

    def test_crlf_line_comments(self):
        self.assertEqual(len(parse('// } bad;\r\nuint x;')['declarations']),1)

    def test_balanced_functions_do_not_add_state_variables(self):
        r=parse('uint a; function f(uint x) public returns(uint) { uint b = x; if(x>0){return b;} return 0; } uint c;')
        self.assertEqual([d['name'] for d in r['declarations']],['a','c'])
        self.assertEqual(r['opaque_members'],{'function':1})

    def test_string_delimiters_inside_body_are_opaque(self):
        r=parse('uint a; function f() public { string memory x = unicode"} ; uint fake; ñ"; string memory y = "\\\"{/*"; } uint b;')
        self.assertEqual([d['name'] for d in r['declarations']],['a','b'])

    def test_events_errors_structs_enum_members_not_state(self):
        r=parse('event Changed(uint value); error Problem(uint reason); struct S {uint inner;} enum E {A,B} uint outer;')
        self.assertEqual([d['name'] for d in r['declarations']],['outer'])
        self.assertEqual(r['opaque_members'],{'enum':1,'error':1,'event':1,'struct':1})

    def test_constructor_modifier_receive_fallback_are_opaque(self):
        r=parse('constructor() {} modifier only() { _; } receive() external payable {} fallback() external {} uint a;')
        self.assertEqual(len(r['declarations']),1)
        self.assertEqual(sum(r['opaque_members'].values()),4)

    def test_named_mapping_and_nested_literal_array(self):
        r=parse('mapping(address who => uint128[2] amount) balances; uint8[2][3] grid;')
        self.assertEqual([d['name'] for d in r['declarations']],['balances','grid'])
        self.assertEqual(r['declarations'][1]['shape'],('array',3,('array',2,('elementary','uint8'))))

    def test_visibility_nonpersistent_and_initializer_classification(self):
        r=parse('uint public a; uint private constant limit = 7; uint immutable ownerId; uint transient tick;')
        self.assertEqual([(d['visibility'],d['mutability'],d['storage']) for d in r['declarations']],
                         [('public','mutable','default'),('private','constant','default'),
                          ('internal','immutable','default'),('internal','mutable','transient')])

    def test_simple_literal_initializers_only(self):
        r=parse('int n = -7; bool enabled=true; string text="; uint fake;"; bytes data=hex"00";')
        self.assertEqual(len(r['declarations']),4)
        self.assertTrue(all(d['initializer_present'] for d in r['declarations']))
        with self.assertRaises(si.InventoryNeedsReview):parse('uint x = 2 + 3;')

    def test_function_typed_variable_never_skipped_as_function(self):
        with self.assertRaisesRegex(si.InventoryNeedsReview,'FUNCTION_TYPE_STATE_REVIEW'):
            parse('function(uint) external callback;')

    def test_user_type_and_expression_array_require_review(self):
        for body in ('Record a;','uint[N] a;','uint[1+2] a;','uint[0x10] a;'):
            with self.subTest(body=body),self.assertRaises((si.InventoryNeedsReview,si.InventoryError,typed.st.TypeNeedsReview)):
                parse(body)

    def test_multiple_contracts_import_and_custom_headers_outside_profile(self):
        for raw in (b'import "Other.sol"; contract Ledger {}',b'contract Ledger {} contract Extra {}',
                    b'contract Ledger is Parent {}',b'contract Ledger layout at 7 {}'):
            with self.subTest(raw=raw),self.assertRaises(si.InventoryNeedsReview):si.parse_source(raw,'Ledger')

    def test_abstract_and_comment_only_empty_contract(self):
        r=si.parse_source(b'abstract /* note */ contract Ledger { /*none*/ }','Ledger')
        self.assertEqual(r['declarations'],[])

    def test_unknown_member_not_silently_skipped(self):
        for member in ('using Lib for uint;', 'type Amount is uint256;','assembly {}'):
            with self.subTest(member=member),self.assertRaises((si.InventoryNeedsReview,si.InventoryError)):
                parse(member)

    def test_duplicate_names_and_qualifiers_rejected(self):
        for body in ('uint a; uint a;', 'uint public private a;', 'uint constant immutable a = 1;', 'uint transient constant a = 1;'):
            with self.subTest(body=body),self.assertRaises(si.InventoryError):parse(body)

    def test_unterminated_comment_string_or_contract_rejected(self):
        for raw in (b'contract Ledger { /*',b'contract Ledger { string a="bad;',b'contract Ledger { uint x;'):
            with self.subTest(raw=raw),self.assertRaises(si.InventoryError):si.parse_source(raw,'Ledger')

    def test_unbalanced_opaque_body_rejected(self):
        with self.assertRaisesRegex(si.InventoryError,'UNBALANCED_SOURCE_DELIMITER'):
            parse('function f() public { if (true] {} }')

    def test_empty_constant_initializer_missing_rejected(self):
        with self.assertRaisesRegex(si.InventoryError,'CONSTANT_INITIALIZER_REQUIRED'):parse('uint constant x;')

    def test_declaration_token_and_nesting_budgets(self):
        with patch.object(si,'MAX_DECLARATIONS',1),self.assertRaises(si.InventoryError):parse('uint a;uint b;')
        with patch.object(si,'MAX_TOKENS',2),self.assertRaises(si.InventoryError):parse('uint a;')
        with patch.object(si,'MAX_DEPTH',2),self.assertRaises(si.InventoryError):parse('function f() public {{{{}}}}')
        with patch.object(si,'MAX_BYTES',2),self.assertRaises(si.InventoryError):parse('uint a;')

    def test_deterministic_generated_inventory_128_sources(self):
        rng=random.Random(20261105)
        for _ in range(128):
            n=rng.randint(1,24); names=[f'v{i}' for i in range(n)]
            lines=[]
            for name in names:
                typ=rng.choice(['uint8','int128','uint256','address','bool','bytes32'])
                lines.append(typ+' /* { ignored uint bad; } */ '+name+';')
                if rng.randrange(3)==0:lines.append('function f'+name+'() public { string memory s="} ;"; }')
            result=parse('\n'.join(lines))
            self.assertEqual([d['name'] for d in result['declarations']],names)

    def test_source_analysis_never_runs_code_or_network(self):
        with patch('subprocess.run',side_effect=AssertionError),patch('socket.socket',side_effect=AssertionError):
            self.assertEqual(parse('uint x;')['declarations'][0]['name'],'x')


class InventoryBindingTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
        self.before=previous.synthetic();self.after=deepcopy(self.before)

    def contract(self,side):return side[1]['sources']['Local.sol']['ast']['nodes'][0]
    def storage(self,side):return side[1]['contracts']['Local.sol']['Ledger']['storageLayout']
    def go(self,v=4):return cl.evaluate(*previous.pair(self.before,self.after,version=v))[0]
    def drop_last(self,side):
        self.contract(side)['nodes'].pop();self.storage(side)['storage'].pop()

    def prepare(self,v=4):
        m,raw=previous.pair(self.before,self.after,version=v)
        (self.root/'expected.json').write_bytes(canonical(m))
        for n,b in raw.items():(self.root/n).write_bytes(b)
        return m,raw

    def create(self):
        self.prepare()
        return cl.create(self.root/'expected.json',*[self.root/n for n in cl.RAW_NAMES],self.root/'case')

    def test_shared_omission_passes_v3_but_is_rejected_v4(self):
        for side in (self.before,self.after):self.drop_last(side)
        self.assertEqual(self.go(3)['status'],'SOURCE_LAYOUT_PRESERVED_IN_PROFILE')
        with self.assertRaisesRegex(si.InventoryError,'DECLARATION_SET_MISMATCH'):self.go(4)

    def test_matching_inventory_has_bounded_explicit_claims(self):
        r=self.go();self.assertTrue(r['all_source_state_declarations_matched'])
        self.assertEqual(r['profile'],'solc-standard-json-source-inventory-v4')
        b=r['bindings']['before']['source_declaration_inventory']
        self.assertEqual(b['source_declarations'],2)
        self.assertFalse(b['full_solidity_syntax_checked']);self.assertFalse(b['function_bodies_analyzed'])
        self.assertFalse(r['compiler_executed_here']);self.assertFalse(r['vulnerability_confirmed'])

    def test_first_omission_with_forged_position_also_rejected(self):
        for side in (self.before,self.after):
            self.contract(side)['nodes'].pop(0);self.storage(side)['storage'].pop(0)
            self.storage(side)['storage'][0]['offset']=0
        self.assertEqual(self.go(3)['status'],'SOURCE_LAYOUT_PRESERVED_IN_PROFILE')
        with self.assertRaisesRegex(si.InventoryError,'DECLARATION_SET_MISMATCH'):self.go()

    def test_mutable_cannot_masquerade_as_constant(self):
        for side in (self.before,self.after):
            self.contract(side)['nodes'][-1].update(mutability='constant',constant=True)
            self.storage(side)['storage'].pop()
        self.assertEqual(self.go(3)['status'],'SOURCE_LAYOUT_PRESERVED_IN_PROFILE')
        with self.assertRaisesRegex(si.InventoryError,'STATE_QUALIFIER_MISMATCH'):self.go()

    def test_mutable_cannot_masquerade_as_transient(self):
        for side in (self.before,self.after):
            self.contract(side)['nodes'][-1]['storageLocation']='transient';self.storage(side)['storage'].pop()
        with self.assertRaisesRegex(si.InventoryError,'STATE_QUALIFIER_MISMATCH'):self.go()

    def test_contract_span_cannot_hide_trailing_declaration(self):
        for side in (self.before,self.after):
            self.drop_last(side);c=self.contract(side)
            start=int(c['src'].split(':')[0]);end=int(c['nodes'][0]['src'].split(':')[0])+len('uint128 item0;')
            c['src']=f'{start}:{end-start}:0'
        with self.assertRaisesRegex(si.InventoryError,'CONTRACT_SOURCE_BOUNDARY_MISMATCH'):self.go()

    def test_same_name_twice_in_ast_not_completeness(self):
        for side in (self.before,self.after):
            nodes=self.contract(side)['nodes'];nodes[-1]['name']='item0';nodes[-1]['nameLocation']=nodes[0]['nameLocation']
            # Forge declaration start/range and type span too; v4 sees duplicate physical name.
            nodes[-1]['src']=nodes[0]['src'];nodes[-1]['typeName']['src']=nodes[0]['typeName']['src']
            self.storage(side)['storage'][-1]['label']='item0'
        with self.assertRaises(ValueError):self.go()

    def test_comments_are_not_required_ast_declarations(self):
        for side in (self.before,self.after):add_member(side,'/* uint256 hidden; */ // uint256 alsoHidden;')
        self.assertTrue(self.go()['all_source_state_declarations_matched'])

    def test_opaque_function_locals_do_not_inflate_state_inventory(self):
        for side in (self.before,self.after):add_member(side,'function f() public { uint256 localVar=7; string memory s="};"; }')
        r=self.go();self.assertTrue(r['all_source_state_declarations_matched'])
        self.assertEqual(r['bindings']['before']['source_declaration_inventory']['opaque_members'],{'function':1})

    def test_appended_real_source_variable_without_ast_rejected(self):
        for side in (self.before,self.after):add_member(side,'uint256 hidden;')
        with self.assertRaisesRegex(si.InventoryError,'DECLARATION_SET_MISMATCH'):self.go()

    def test_variable_ast_cannot_be_relabelled_function_to_hide_it(self):
        for side in (self.before,self.after):
            self.contract(side)['nodes'][-1]['nodeType']='FunctionDefinition';self.storage(side)['storage'].pop()
        with self.assertRaisesRegex(si.InventoryError,'DECLARATION_SET_MISMATCH'):self.go()

    def test_ast_node_and_layout_order_do_not_control_source_order(self):
        self.contract(self.after)['nodes'].reverse();self.storage(self.after)['storage'].reverse()
        self.assertTrue(self.go()['all_source_state_declarations_matched'])

    def test_source_visibility_not_fabricated(self):
        self.contract(self.after)['nodes'][0]['visibility']='public'
        with self.assertRaisesRegex(si.InventoryError,'VISIBILITY_MISMATCH'):self.go()

    def test_unsupported_initializer_cannot_claim_inventory_complete(self):
        self.before=typed.single('uint256');self.after=deepcopy(self.before)
        # Add an unsupported member so the entire inventory is explicitly incomplete.
        for side in (self.before,self.after):add_member(side,'uint256 uncheckedByProfile = compute();')
        r=self.go();self.assertEqual(r['status'],'SOURCE_LAYOUT_REVIEW_REQUIRED')
        self.assertFalse(r['all_source_state_declarations_matched'])

    def test_other_compiler_version_cannot_claim_complete(self):
        m,raw=previous.pair(self.before,self.after,version=4)
        m['before']['compiler_version']=m['after']['compiler_version']='0.8.29'
        r=cl.evaluate(m,raw)[0]
        self.assertEqual(r['status'],'SOURCE_LAYOUT_REVIEW_REQUIRED')
        self.assertFalse(r['all_source_state_declarations_matched'])

    def test_older_profiles_do_not_gain_new_guarantee(self):
        for v in (1,2,3):
            r=self.go(v);self.assertNotIn('all_source_state_declarations_matched',r)

    def test_audit_and_code_identity_include_inventory(self):
        self.create();audit=strict_json((self.root/'case/audit.json').read_bytes())
        self.assertIn('solidity_inventory.py',audit['engine']['sources'])
        self.assertEqual(len(audit['entries']),4)
        self.assertIn('solidity_inventory',quality.COMPONENTS['compiler_layout']['depends'])

    def test_existing_layout_engine_really_called(self):
        with patch.object(cl.layout,'compare',wraps=cl.layout.compare) as comparator:
            self.go()
        self.assertEqual(comparator.call_count,1)

    def test_manifest_downgrade_rejected(self):
        self.create();case=self.root/'case'
        m=strict_json((case/'manifest.json').read_bytes());m['schema_version']=3
        raw=canonical(m);(case/'manifest.json').write_bytes(raw)
        marker=strict_json((case/'COMPLETE.json').read_bytes());marker['sha256']['manifest.json']=cl.layout.sha(raw)
        (case/'COMPLETE.json').write_bytes(canonical(marker))
        with self.assertRaisesRegex(cl.BindingError,'EXTERNAL_REFERENCE_MISMATCH'):
            cl.verify(case,self.root/'expected.json')

    def test_resealed_inventory_statement_rejected(self):
        self.create();case=self.root/'case'
        r=strict_json((case/'result.json').read_bytes())
        r['bindings']['before']['source_declaration_inventory']['source_declarations']=999
        raw=canonical(r);(case/'result.json').write_bytes(raw)
        marker=strict_json((case/'COMPLETE.json').read_bytes());marker['sha256']['result.json']=cl.layout.sha(raw)
        (case/'COMPLETE.json').write_bytes(canonical(marker))
        with self.assertRaisesRegex(cl.BindingError,'RECOMPUTATION_MISMATCH'):
            cl.verify(case,self.root/'expected.json')

    def test_cli_create_and_verify_separate_processes(self):
        self.prepare();base=Path(__file__).resolve().parents[2]
        args=['review-compiler-layout','--expected',str(self.root/'expected.json')]
        for name in cl.RAW_NAMES:args+=['--'+name.removesuffix('.json'),str(self.root/name)]
        args+=['--out',str(self.root/'case')]
        for cmd in (args,['verify-compiler-layout','--bundle',str(self.root/'case'),'--expected',str(self.root/'expected.json')]):
            r=subprocess.run([sys.executable,'-B','-m','superhunter',*cmd],cwd=base,capture_output=True,text=True,timeout=30)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertTrue(cl.verify(self.root/'case',self.root/'expected.json')['all_source_state_declarations_matched'])

    def test_original_sources_never_mutated(self):
        _,raw=self.prepare();before=deepcopy(raw);self.create()
        self.assertEqual({n:(self.root/n).read_bytes() for n in cl.RAW_NAMES},before)

    def test_empty_declaration_inventory_is_explicit_not_universal_security(self):
        self.before=previous.synthetic((),());self.after=deepcopy(self.before)
        r=self.go();self.assertTrue(r['all_source_state_declarations_matched'])
        self.assertEqual(r['bindings']['before']['source_declaration_inventory']['source_declarations'],0)
        self.assertFalse(r['vulnerability_confirmed'])

    def test_error_console_does_not_echo_source(self):
        for side in (self.before,self.after):add_member(side,'uint256 PRIVATE_SOURCE_MARKER;')
        self.prepare();args=['review-compiler-layout','--expected',str(self.root/'expected.json')]
        for name in cl.RAW_NAMES:args+=['--'+name.removesuffix('.json'),str(self.root/name)]
        args+=['--out',str(self.root/'case')]
        with redirect_stdout(io.StringIO()) as stream:self.assertEqual(cl.main(args),2)
        self.assertNotIn('PRIVATE_SOURCE_MARKER',stream.getvalue())

    def test_no_network_or_execution_during_binding(self):
        with patch('socket.socket',side_effect=AssertionError),patch('subprocess.run',side_effect=AssertionError):
            self.assertTrue(self.go()['all_source_state_declarations_matched'])


if __name__=='__main__':unittest.main()
