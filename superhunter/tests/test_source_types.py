"""Own benign source/AST/layout consistency fixtures; NOT compiler output.

The source parser, AST walker and storage walker are exercised with independent
expected structures. No compile, EVM execution, external contracts or exploits.
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

import test_compiler_layout as old
from superhunter import compiler_layout as cl, source_types as st
from superhunter.safe_io import canonical, strict_json


def single(type_text='uint256', *, ast_name=None, layout_name=None, width=None, ast_factory=None,
           descriptor=None, modifiers=''):
    # All field positions are computed from this explicitly synthetic source.
    text='// Local synthetic type fixture; not compiled.\npragma solidity ^0.8.30;\ncontract Ledger {\n'
    decl=type_text+' '+(modifiers+' ' if modifiers else '')+'balance;'
    text+=decl+'\n}\n'; raw=text.encode()
    pos=raw.index(decl.encode()); name=raw.index(b'balance;',pos); cs=raw.index(b'contract Ledger')
    name_ast=ast_name or type_text
    tnode={'nodeType':'ElementaryTypeName','id':20,'name':name_ast.removesuffix(' payable'),
           'stateMutability':'payable' if name_ast.endswith(' payable') else 'nonpayable',
           'src':f'{pos}:{len(type_text.encode())}:0'}
    if ast_factory is not None:tnode=ast_factory(pos)
    var={'nodeType':'VariableDeclaration','id':10,'name':'balance','stateVariable':True,
         'constant':False,'mutability':'mutable','storageLocation':'default',
         'src':f'{pos}:{len(decl.encode())}:0','nameLocation':f'{name}:7:0','typeName':tnode}
    contract={'nodeType':'ContractDefinition','id':1,'name':'Ledger','nodes':[var],
              'src':f'{cs}:{raw.rfind(b"}")+1-cs}:0','baseContracts':[],'linearizedBaseContracts':[1]}
    ast={'nodeType':'SourceUnit','id':0,'absolutePath':'Local.sol','nodes':[contract],'src':f'0:{len(raw)}:0'}
    label=layout_name or type_text
    if width is None and descriptor is None:
        if label in ('address','address payable'):width=20
        elif label=='bool':width=1
        elif label.startswith('uint'):width=int(label[4:] or '256')//8
        elif label.startswith('int'):width=int(label[3:] or '256')//8
        elif label.startswith('bytes') and label!='bytes':width=int(label[5:])
        else:width=32
    types=descriptor or {'t':{'encoding':'bytes' if label in ('bytes','string') else 'inplace',
                             'label':label,'numberOfBytes':str(width)}}
    inp={'language':'Solidity','sources':{'Local.sol':{'content':text}},
         'settings':{'outputSelection':{'*':{'':['ast'],'*':['storageLayout']}}}}
    out={'sources':{'Local.sol':{'id':0,'ast':ast}},'contracts':{'Local.sol':{'Ledger':{'storageLayout':{
        'storage':[{'astId':10,'contract':'Local.sol:Ledger','label':'balance','slot':'0','offset':0,'type':'t'}],
        'types':types}}}}}
    return inp,out


def elem(name,start,identifier=21):
    return {'nodeType':'ElementaryTypeName','id':identifier,'name':name,
            'src':f'{start}:{len(name)}:0'}


def array(base='uint128',length='3'):
    expression=base+'['+length+']'
    def make(pos):
        return {'nodeType':'ArrayTypeName','id':20,'src':f'{pos}:{len(expression)}:0',
                'baseType':elem(base,pos), 'length':None if not length else {
                    'nodeType':'Literal','id':22,'kind':'number','value':length,
                    'src':f'{pos+len(base)+1}:{len(length)}:0'}}
    size=32 if not length else ((int(length.replace('_',''))+1)//2)*32
    desc={'t':{'encoding':'dynamic_array' if not length else 'inplace','label':expression.replace('_',''),
               'numberOfBytes':str(size),'base':'b'},
          'b':{'encoding':'inplace','label':base,'numberOfBytes':'16'}}
    return single(expression,ast_factory=make,descriptor=desc)


def mapping():
    text='mapping(address owner => uint128 amount)'
    def make(pos):
        return {'nodeType':'Mapping','id':20,'src':f'{pos}:{len(text)}:0',
                'keyType':elem('address',pos+text.index('address'),21),
                'valueType':elem('uint128',pos+text.index('uint128'),22),
                'keyName':'owner','valueName':'amount'}
    desc={'t':{'encoding':'mapping','label':'mapping(address => uint128)','numberOfBytes':'32',
               'key':'k','value':'v'},
          'k':{'encoding':'inplace','label':'address','numberOfBytes':'20'},
          'v':{'encoding':'inplace','label':'uint128','numberOfBytes':'16'}}
    return single(text,ast_factory=make,descriptor=desc)


def pair(before,after=None,version=2):
    manifest,raw=old.pair(before,after)
    manifest['schema_version']=version
    return manifest,raw


class SourceTypeParserTests(unittest.TestCase):
    def test_elementary_expected_shapes(self):
        for source,canonical_name in [('uint','uint256'),('int','int256'),('uint8','uint8'),
            ('int128','int128'),('address','address'),('address payable','address payable'),
            ('bool','bool'),('bytes1','bytes1'),('bytes32','bytes32'),('bytes','bytes'),('string','string')]:
            with self.subTest(source=source):self.assertEqual(st.source_shape(source.encode()),('elementary',canonical_name))

    def test_nested_array_expected_shape(self):
        self.assertEqual(st.source_shape(b'uint128[3][]'),('array',None,('array',3,('elementary','uint128'))))

    def test_named_mapping_and_nested_mapping(self):
        expected=('mapping',('elementary','address'),('mapping',('elementary','uint256'),('array',None,('elementary','bytes32'))))
        self.assertEqual(st.source_shape(b'mapping(address person => mapping(uint key => bytes32[] values) table)'),expected)

    def test_comments_are_lexical_not_type_content(self):
        self.assertEqual(st.source_shape('uint128 /* comentario ó */ [ /*3*/ 4 ]'.encode()),
                         ('array',4,('elementary','uint128')))

    def test_split_identifier_not_rejoined(self):
        with self.assertRaises(st.TypeBindingError):st.source_shape(b'uint /* comment */ 128')

    def test_unterminated_comment_rejected(self):
        with self.assertRaisesRegex(st.TypeBindingError,'COMMENT'):st.source_shape(b'uint128 /* missing end')

    def test_integer_and_bytes_width_limits(self):
        for bad in (b'uint7',b'uint264',b'int0',b'bytes0',b'bytes33'):
            with self.subTest(bad=bad),self.assertRaises(st.TypeBindingError):st.source_shape(bad)

    def test_array_zero_and_too_large_rejected(self):
        for length in ('0',str(2**256)):
            with self.assertRaises(st.TypeBindingError):st.source_shape(('uint8['+length+']').encode())

    def test_length_expression_is_not_evaluated(self):
        for value in (b'uint128[N]',b'uint128[1+2]',b'uint128[0x10]'):
            with self.subTest(value=value),self.assertRaises(st.TypeNeedsReview):st.source_shape(value)

    def test_custom_and_function_types_need_review(self):
        for value in (b'Record',b'Ledger.Record',b'function(uint) external'):
            with self.subTest(value=value),self.assertRaises(st.TypeNeedsReview):st.source_shape(value)

    def test_extra_tokens_not_ignored(self):
        with self.assertRaises(st.TypeBindingError):st.source_shape(b'uint128 uint256')

    def test_budgets_are_enforced(self):
        with patch.object(st,'MAX_TOKENS',2),self.assertRaises(st.TypeBindingError):st.source_shape(b'uint128[2]')
        with patch.object(st,'MAX_DEPTH',1),self.assertRaises(st.TypeNeedsReview):st.source_shape(b'uint128[][][]')
        with patch.object(st,'MAX_FRAGMENT',2),self.assertRaises(st.TypeBindingError):st.source_shape(b'uint128')

    def test_type_id_renaming_does_not_change_storage_shape(self):
        before={'x':{'encoding':'dynamic_array','label':'uint128[]','numberOfBytes':'32','base':'y'},
                'y':{'encoding':'inplace','label':'uint128','numberOfBytes':'16'}}
        after={'a':{**before['x'],'base':'b'},'b':before['y']}
        self.assertEqual(st.storage_shape('x',before),st.storage_shape('a',after))

    def test_recursive_storage_type_is_review_not_loop(self):
        with self.assertRaisesRegex(st.TypeNeedsReview,'RECURSIVE'):
            st.storage_shape('t',{'t':{'encoding':'dynamic_array','label':'recursive[]','numberOfBytes':'32','base':'t'}})

    def test_missing_storage_reference_rejected(self):
        with self.assertRaisesRegex(st.TypeBindingError,'REFERENCE'):st.storage_shape('missing',{})


class TypedBindingTests(unittest.TestCase):
    def setUp(self):
        self.work=tempfile.TemporaryDirectory();self.addCleanup(self.work.cleanup);self.root=Path(self.work.name)
        self.before=single();self.after=single();self.out=self.root/'bundle'

    def var(self):return self.after[1]['sources']['Local.sol']['ast']['nodes'][0]['nodes'][0]
    def types(self):return self.after[1]['contracts']['Local.sol']['Ledger']['storageLayout']['types']
    def go(self):return cl.evaluate(*pair(self.before,self.after))[0]

    def write_inputs(self):
        m,raw=pair(self.before,self.after)
        (self.root/'expected.json').write_bytes(canonical(m))
        for n,v in raw.items():(self.root/n).write_bytes(v)
        return m,raw

    def create(self):
        self.write_inputs()
        return cl.create(self.root/'expected.json',*[self.root/n for n in cl.RAW_NAMES],self.out)

    def verify(self):return cl.verify(self.out,self.root/'expected.json')

    def reseal(self,name,edit):
        p=self.out/name;data=strict_json(p.read_bytes());edit(data);raw=canonical(data);p.write_bytes(raw)
        marker=strict_json((self.out/'COMPLETE.json').read_bytes());marker['sha256'][name]=cl.layout.sha(raw)
        (self.out/'COMPLETE.json').write_bytes(canonical(marker))

    def test_v1_missing_type_check_reproduced_and_v2_rejects(self):
        self.after=single('uint128',layout_name='uint256')
        legacy=cl.evaluate(*pair(self.before,self.after,version=1))[0]
        self.assertEqual(legacy['status'],'SOURCE_LAYOUT_PRESERVED_IN_PROFILE')
        with self.assertRaisesRegex(st.TypeBindingError,'AST_STORAGE_TYPE_MISMATCH'):self.go()

    def test_typed_profile_valid_but_not_compiler_execution(self):
        r=self.go()
        self.assertTrue(r['all_declared_types_checked'])
        self.assertEqual(r['profile'],'solc-standard-json-typed-binding-v2')
        self.assertEqual(r['bindings']['before']['type_correspondence']['checked'],1)
        for flag in ('compiler_executed_here','compiler_output_authenticated','deployed_state_verified','upgrade_authorized','vulnerability_confirmed'):
            self.assertIs(r[flag],False)

    def test_layout_type_changed_consistently_is_reported(self):
        self.after=single('uint128')
        self.assertEqual(self.go()['status'],'SOURCE_LAYOUT_CHANGE_DETECTED')

    def test_signedness_mismatch_at_same_width_rejected(self):
        self.after=single('int256',layout_name='uint256')
        with self.assertRaisesRegex(st.TypeBindingError,'AST_STORAGE_TYPE_MISMATCH'):self.go()

    def test_ast_type_mismatch_against_source_rejected(self):
        self.after=single('uint128',ast_name='uint256',layout_name='uint256')
        with self.assertRaisesRegex(st.TypeBindingError,'SOURCE_AST_TYPE_MISMATCH'):self.go()

    def test_alias_uint_matches_uint256(self):
        self.after=single('uint',ast_name='uint256',layout_name='uint256')
        self.assertTrue(self.go()['all_declared_types_checked'])
        self.assertEqual(self.go()['status'],'SOURCE_LAYOUT_PRESERVED_IN_PROFILE')

    def test_payable_difference_not_erased(self):
        self.before=single('address payable');self.after=single('address payable',layout_name='address')
        with self.assertRaisesRegex(st.TypeBindingError,'AST_STORAGE_TYPE_MISMATCH'):self.go()

    def test_bytes_and_string_not_same_type(self):
        self.before=single('bytes');self.after=single('bytes',layout_name='string')
        with self.assertRaisesRegex(st.TypeBindingError,'AST_STORAGE_TYPE_MISMATCH'):self.go()

    def test_missing_type_ast_rejected_only_in_v2(self):
        self.var().pop('typeName')
        self.assertEqual(cl.evaluate(*pair(self.before,self.after,version=1))[0]['status'],'SOURCE_LAYOUT_PRESERVED_IN_PROFILE')
        with self.assertRaisesRegex(st.TypeBindingError,'TYPE_AST_REQUIRED'):self.go()

    def test_partial_type_span_cannot_hide_real_width(self):
        self.after=single('uint128',ast_name='uint',layout_name='uint256')
        start,_,fileid=self.var()['typeName']['src'].split(':')
        self.var()['typeName']['src']=start+':4:'+fileid
        with self.assertRaisesRegex(st.TypeBindingError,'TYPE_SUFFIX'):self.go()

    def test_type_cannot_be_selected_from_comment_in_declaration(self):
        self.after=single('uint128 /* uint256 */',ast_name='uint256',layout_name='uint256')
        start,_,_=self.var()['typeName']['src'].split(':')
        self.var()['typeName']['src']=f'{int(start)+11}:7:0'
        with self.assertRaises(st.TypeBindingError):self.go()

    def test_type_span_outside_declaration_rejected(self):
        self.var()['typeName']['src']='0:7:0'
        with self.assertRaisesRegex(st.TypeBindingError,'TYPE_NOT_BEFORE'):self.go()

    def test_wrong_source_id_rejected(self):
        self.var()['typeName']['src']=self.var()['typeName']['src'][:-1]+'1'
        with self.assertRaisesRegex(st.TypeBindingError,'TYPE_SOURCE_RANGE'):self.go()

    def test_visibility_modifiers_supported(self):
        for modifier in ('public','private','internal'):
            with self.subTest(modifier=modifier):
                self.after=single(modifiers=modifier);self.assertTrue(self.go()['all_declared_types_checked'])

    def test_mapping_children_verified(self):
        self.before=mapping();self.after=mapping();self.assertTrue(self.go()['all_declared_types_checked'])
        self.types()['v'].update(label='uint256',numberOfBytes='32')
        with self.assertRaisesRegex(st.TypeBindingError,'AST_STORAGE_TYPE_MISMATCH'):self.go()

    def test_mapping_child_source_name_cannot_lie(self):
        self.before=mapping();self.after=mapping();self.var()['typeName']['valueType']['name']='uint256'
        with self.assertRaisesRegex(st.TypeBindingError,'SOURCE_AST_TYPE_MISMATCH'):self.go()

    def test_dynamic_and_fixed_arrays_verified(self):
        for length in ('','3','1_000'):
            with self.subTest(length=length):
                self.before=array(length=length);self.after=deepcopy(self.before)
                self.assertTrue(self.go()['all_declared_types_checked'])

    def test_array_length_disagreement_rejected(self):
        self.before=array();self.after=array();self.var()['typeName']['length']['value']='4'
        with self.assertRaisesRegex(st.TypeBindingError,'ARRAY_LENGTH_SOURCE_MISMATCH'):self.go()

    def test_array_element_type_disagreement_rejected(self):
        self.before=array();self.after=array();self.types()['b'].update(label='int128')
        with self.assertRaisesRegex(st.TypeBindingError,'AST_STORAGE_TYPE_MISMATCH'):self.go()

    def test_unsupported_shape_cannot_be_marked_preserved(self):
        def node(pos):return {'nodeType':'UserDefinedTypeName','id':20,'namePath':'Record','src':f'{pos}:6:0'}
        desc={'t':{'encoding':'inplace','label':'struct Ledger.Record','numberOfBytes':'32',
                   'members':[{'astId':30,'contract':'Local.sol:Ledger','label':'x','slot':'0','offset':0,'type':'u'}]},
              'u':{'encoding':'inplace','label':'uint256','numberOfBytes':'32'}}
        self.before=single('Record',ast_factory=node,descriptor=desc);self.after=deepcopy(self.before)
        r=self.go();self.assertEqual(r['status'],'SOURCE_LAYOUT_REVIEW_REQUIRED');self.assertFalse(r['all_declared_types_checked'])
        self.assertEqual(r['bindings']['after']['type_correspondence']['review_required'],1)

    def test_literal_expression_is_review_not_success(self):
        self.before=array();self.after=array()
        self.var()['typeName']['length'].update(nodeType='Identifier',name='THREE')
        self.assertEqual(self.go()['status'],'SOURCE_LAYOUT_REVIEW_REQUIRED')

    def test_empty_contract_has_explicit_zero_coverage(self):
        self.before=old.fixture(());self.after=old.fixture(())
        r=self.go();self.assertTrue(r['all_declared_types_checked']);self.assertEqual(r['bindings']['after']['type_correspondence']['checked'],0)

    def test_seeded_widths_match_independent_expected(self):
        randomizer=random.Random(20261104)
        for _ in range(64):
            width=randomizer.choice(range(8,257,8));sign=randomizer.choice(('int','uint'));name=sign+str(width)
            self.before=single(name);self.after=single(name)
            r=self.go();self.assertTrue(r['all_declared_types_checked'])
            self.types()['t']['label']=('uint' if sign=='int' else 'int')+str(width)
            with self.assertRaisesRegex(st.TypeBindingError,'AST_STORAGE_TYPE_MISMATCH'):self.go()

    def test_all_three_parsers_really_called(self):
        with patch.object(st,'source_shape',wraps=st.source_shape) as a,patch.object(st,'ast_shape',wraps=st.ast_shape) as b,patch.object(st,'storage_shape',wraps=st.storage_shape) as c:
            self.go()
        self.assertEqual((a.call_count,b.call_count,c.call_count),(2,2,2))

    def test_no_source_execution_or_network(self):
        with patch('subprocess.run',side_effect=AssertionError),patch('socket.socket',side_effect=AssertionError):self.create();self.verify()

    def test_external_reference_prevents_profile_downgrade(self):
        self.create();self.reseal('manifest.json',lambda m:m.update(schema_version=1))
        with self.assertRaisesRegex(cl.BindingError,'EXTERNAL_REFERENCE_MISMATCH'):self.verify()

    def test_resealed_type_claim_rejected(self):
        self.create();self.reseal('result.json',lambda r:r['bindings']['after']['type_correspondence'].update(checked=999))
        with self.assertRaisesRegex(cl.BindingError,'RECOMPUTATION_MISMATCH'):self.verify()

    def test_originals_not_modified_and_private_output(self):
        _,originals=self.write_inputs();self.create()
        for name,value in originals.items():self.assertEqual((self.root/name).read_bytes(),value)
        self.assertEqual(self.out.stat().st_mode & 0o777,0o700)
        for p in self.out.iterdir():self.assertEqual(p.stat().st_mode & 0o777,0o600)

    def test_code_identity_includes_type_validator(self):
        self.create();a=strict_json((self.out/'audit.json').read_bytes())
        self.assertIn('source_types.py',a['engine']['sources'])

    def test_cli_real_separate_processes(self):
        self.write_inputs();base=Path(__file__).resolve().parents[2]
        create=['review-compiler-layout','--expected',str(self.root/'expected.json'),'--out',str(self.out)]
        for name in cl.RAW_NAMES:create.extend(['--'+name.removesuffix('.json'),str(self.root/name)])
        verify=['verify-compiler-layout','--bundle',str(self.out),'--expected',str(self.root/'expected.json')]
        for args in (create,verify):
            p=subprocess.run([sys.executable,'-B','-m','superhunter',*args],cwd=base,capture_output=True,text=True,timeout=30)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            self.assertFalse(json.loads(p.stdout)['compiler_executed_here'])

    def test_inputs_not_mutated(self):
        before=deepcopy((self.before,self.after));self.go();self.assertEqual((self.before,self.after),before)


if __name__=='__main__':unittest.main()
