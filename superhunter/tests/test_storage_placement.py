"""Own arithmetic/AST fixtures, NOT solc output or exploit demonstrations."""
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

import test_source_types as previous
from superhunter import compiler_layout as cl, source_types as st, storage_placement as sp
from superhunter.safe_io import canonical, strict_json


def synthetic(types=('uint128','uint128'), positions=((0,0),(0,16)), *, header='contract Ledger {'):
    """Hand-specified allocation expected separately from implementation under test."""
    text='// OWN SYNTHETIC FIXTURE. NOT COMPILED.\npragma solidity ^0.8.30;\n'+header+'\n'
    declarations=[f'{typ} item{i};' for i,typ in enumerate(types)]
    text+='\n'.join(declarations)+'\n}\n'; raw=text.encode()
    start=raw.index(header.encode()); nodes=[];rows=[];descs={}
    for i,(typ,decl,(slot,offset)) in enumerate(zip(types,declarations,positions)):
        at=raw.index(decl.encode());name=f'item{i}';namepos=raw.index(name.encode(),at)
        node={'id':10+i,'nodeType':'VariableDeclaration','name':name,'stateVariable':True,
              'constant':False,'mutability':'mutable','storageLocation':'default',
              'src':f'{at}:{len(decl)}:0','nameLocation':f'{namepos}:{len(name)}:0',
              'typeName':{'id':100+i,'nodeType':'ElementaryTypeName','name':typ,
                          'src':f'{at}:{len(typ)}:0'}}
        width=(int(typ[4:])//8 if typ.startswith('uint') else
               int(typ[3:])//8 if typ.startswith('int') else
               int(typ[5:]) if typ.startswith('bytes') and typ!='bytes' else
               {'bool':1,'address':20,'bytes':32,'string':32}[typ])
        descs['t'+str(i)]={'label':typ,'numberOfBytes':str(width),
                          'encoding':'bytes' if typ in ('bytes','string') else 'inplace'}
        rows.append({'astId':10+i,'contract':'Local.sol:Ledger','label':name,
                     'slot':str(slot),'offset':offset,'type':'t'+str(i)})
        nodes.append(node)
    contract={'id':1,'nodeType':'ContractDefinition','name':'Ledger','nodes':nodes,
              'baseContracts':[],'linearizedBaseContracts':[1],
              'src':f'{start}:{raw.rfind(b"}")+1-start}:0'}
    ast={'id':0,'nodeType':'SourceUnit','absolutePath':'Local.sol','nodes':[contract],
         'src':f'0:{len(raw)}:0'}
    inp={'language':'Solidity','sources':{'Local.sol':{'content':text}},
         'settings':{'outputSelection':{'*':{'':['ast'],'*':['storageLayout']}}}}
    out={'sources':{'Local.sol':{'id':0,'ast':ast}},'contracts':{'Local.sol':{'Ledger':{
         'storageLayout':{'storage':rows,'types':descs}}}}}
    return inp,out


def pair(before,after=None,version=3):
    return previous.pair(before,after,version=version)


class PlacementMathTests(unittest.TestCase):
    def check(self,texts,expected):
        shapes=[st.source_shape(s.encode()) for s in texts]
        a=sp.allocate_primary(shapes);b=sp.allocate_reference(shapes)
        self.assertEqual(a,b)
        self.assertEqual([(int(x['slot']),x['offset']) for x in a],expected)
        return a

    def test_packed_uint128_pair(self):
        self.check(['uint128','uint128','uint256'],[(0,0),(0,16),(1,0)])

    def test_holes_not_backfilled_across_variables(self):
        self.check(['uint248','uint16','uint8'],[(0,0),(1,0),(1,2)])

    def test_address_bool_bytes_packing(self):
        self.check(['address','bool','bytes11','bool'],[(0,0),(0,20),(0,21),(1,0)])

    def test_array_aligns_and_next_starts_new_word(self):
        a=self.check(['bool','uint128[3]','uint8'],[(0,0),(1,0),(3,0)])
        self.assertEqual(a[1]['head_bytes'],'64')

    def test_nondivisor_array_size(self):
        a=self.check(['uint24[11]','bool'],[(0,0),(2,0)])
        self.assertEqual(a[0]['head_bytes'],'64')

    def test_nested_fixed_arrays_have_separate_element_regions(self):
        a=self.check(['uint128[3][2]','bool'],[(0,0),(4,0)])
        self.assertEqual(a[0]['head_bytes'],'128')

    def test_dynamic_heads_not_payload_lengths(self):
        a=self.check(['bool','uint128[]','mapping(address=>uint256)','bytes','string','uint8'],
                     [(0,0),(1,0),(2,0),(3,0),(4,0),(5,0)])
        self.assertTrue(all(r['head_bytes']=='32' for r in a[1:5]))

    def test_array_of_dynamic_heads(self):
        self.check(['uint8[][3]','bytes[2]','uint16'],[(0,0),(3,0),(5,0)])

    def test_empty_allocation(self):
        self.assertEqual(sp.allocate_primary([]),[])
        self.assertEqual(sp.allocate_reference([]),[])

    def test_uint256_address_boundary_without_expansion(self):
        big=('array',sp.SLOTS-1,('elementary','uint256'))
        for method in (sp.allocate_primary,sp.allocate_reference):
            self.assertEqual(method([big,('elementary','uint256')])[-1]['slot'],str(sp.SLOTS-1))
            with self.assertRaisesRegex(sp.PlacementError,'OVERFLOW'):
                method([big,('elementary','uint256'),('elementary','bool')])

    def test_nested_region_overflow(self):
        shape=('array',sp.SLOTS-1,('array',2,('elementary','uint256')))
        for method in (sp.allocate_primary,sp.allocate_reference):
            with self.assertRaisesRegex(sp.PlacementError,'OVERFLOW'):method([shape])

    def test_invalid_shape_types_rejected(self):
        for shape in (('array',True,('elementary','bool')),('array',0,('elementary','bool')),
                      ('elementary','uint7'),('elementary','bytes33'),['elementary','bool'],
                      ('mapping',('array',1,('elementary','bool')),('elementary','uint256'))):
            with self.subTest(shape=shape),self.assertRaises(sp.PlacementError):sp.allocate_primary([shape])

    def test_budget_rejected_without_partial_result(self):
        with patch.object(sp,'MAX_DECLARATIONS',1),self.assertRaises(sp.PlacementError):
            sp.allocate_primary([('elementary','bool')]*2)
        with patch.object(sp,'MAX_DEPTH',0),self.assertRaises(sp.PlacementError):
            sp.allocate_primary([('array',1,('elementary','bool'))])

    def test_reference_does_not_call_primary(self):
        with patch.object(sp,'allocate_primary',side_effect=AssertionError),\
             patch.object(sp,'_footprint',side_effect=AssertionError):
            self.assertEqual(sp.allocate_reference([('elementary','uint128')]*2)[1]['offset'],16)

    def test_seeded_scalar_allocations_match_byte_occupancy_oracle(self):
        rng=random.Random(20261105)
        for _ in range(256):
            widths=[rng.randint(1,32) for _ in range(rng.randint(1,40))]
            # Independent discrete word occupancy, not either cursor algorithm.
            words=[[]];expected=[]
            for width in widths:
                if len(words[-1])+width>32:words.append([])
                expected.append((len(words)-1,len(words[-1])))
                words[-1].extend([True]*width)
            a=sp.allocate_primary([('elementary','uint'+str(w*8)) for w in widths])
            b=sp.allocate_reference([('elementary','uint'+str(w*8)) for w in widths])
            self.assertEqual(a,b)
            self.assertEqual([(int(r['slot']),r['offset']) for r in a],expected)

    def test_documented_packing_examples(self):
        self.check(['uint128','uint256','uint128'],[(0,0),(1,0),(2,0)])
        self.check(['uint8[10]','bytes5[8]','bytes5'],[(0,0),(1,0),(3,0)])


class PlacementBindingTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.before=synthetic();self.after=deepcopy(self.before)

    def go(self,version=3):return cl.evaluate(*pair(self.before,self.after,version))[0]

    def store(self,side=None):
        return (side or self.after)[1]['contracts']['Local.sol']['Ledger']['storageLayout']

    def contract(self,side=None):return (side or self.after)[1]['sources']['Local.sol']['ast']['nodes'][0]

    def prepare(self):
        m,raw=pair(self.before,self.after)
        (self.root/'expected.json').write_bytes(canonical(m))
        for n,v in raw.items():(self.root/n).write_bytes(v)
        return m,raw

    def create(self):
        self.prepare()
        return cl.create(self.root/'expected.json',*[self.root/n for n in cl.RAW_NAMES],self.root/'case')

    def test_coherent_wrong_origin_passes_v2_but_v3_rejects(self):
        self.before=previous.single('uint128')
        self.store(self.before)['storage'][0]['slot']='7'
        self.after=deepcopy(self.before)
        old=self.go(2)
        self.assertEqual(old['status'],'SOURCE_LAYOUT_PRESERVED_IN_PROFILE')
        with self.assertRaisesRegex(sp.PlacementError,'DECLARED_PLACEMENT_MISMATCH'):self.go()

    def test_exact_packing_reconstructed(self):
        r=self.go();b=r['bindings']['before']['storage_head_placement']
        self.assertEqual(r['profile'],'solc-standard-json-placement-v3')
        self.assertTrue(r['all_declared_storage_heads_checked'])
        self.assertEqual([(x['slot'],x['offset']) for x in b['records']],[('0',0),('0',16)])
        self.assertFalse(r['compiler_executed_here'])
        self.assertFalse(b['dynamic_payloads_checked'])
        self.assertFalse(b['source_inventory_complete_proven'])

    def test_nonoverlapping_unnecessary_gap_rejected(self):
        self.store()['storage'][1].update(slot='1',offset=0)
        with self.assertRaisesRegex(sp.PlacementError,'PLACEMENT_MISMATCH'):self.go()

    def test_incorrect_offset_rejected(self):
        self.before=synthetic(('uint64','uint64'),((0,0),(0,8)))
        self.after=deepcopy(self.before);self.store()['storage'][1]['offset']=16
        with self.assertRaisesRegex(sp.PlacementError,'PLACEMENT_MISMATCH'):self.go()

    def test_ast_array_order_is_not_declaration_order(self):
        self.contract()['nodes'].reverse()
        self.assertTrue(self.go()['all_declared_storage_heads_checked'])

    def test_layout_array_order_is_not_declaration_order(self):
        self.store()['storage'].reverse()
        self.assertTrue(self.go()['all_declared_storage_heads_checked'])

    def test_swapped_ids_and_ast_order_do_not_override_source(self):
        self.contract()['nodes'].reverse()
        self.store()['storage'][0].update(slot='0',offset=16)
        self.store()['storage'][1].update(slot='0',offset=0)
        with self.assertRaisesRegex(sp.PlacementError,'PLACEMENT_MISMATCH'):self.go()

    def test_custom_base_requires_review(self):
        self.before=synthetic(header='contract Ledger layout at 7 {',positions=((7,0),(7,16)))
        self.after=deepcopy(self.before)
        r=self.go();self.assertEqual(r['status'],'SOURCE_LAYOUT_REVIEW_REQUIRED')
        self.assertFalse(r['all_declared_storage_heads_checked'])
        self.assertEqual(r['bindings']['after']['storage_head_placement']['reason'],'CUSTOM_OR_UNSUPPORTED_CONTRACT_HEADER')

    def test_header_comment_cannot_introduce_fake_custom_base(self):
        self.before=synthetic(header='contract /* layout at 7 { */ Ledger {')
        self.after=deepcopy(self.before)
        self.assertTrue(self.go()['all_declared_storage_heads_checked'])

    def test_custom_storage_ast_even_default_header_requires_review(self):
        self.contract()['storageLayout']={'baseSlot':{'nodeType':'Literal','value':'7'}}
        self.assertFalse(self.go()['all_declared_storage_heads_checked'])

    def test_abstract_default_header(self):
        self.before=synthetic(header='abstract contract Ledger {');self.after=deepcopy(self.before)
        self.assertTrue(self.go()['all_declared_storage_heads_checked'])

    def test_other_version_not_silently_assumed_compatible(self):
        m,raw=pair(self.before,self.after);m['after']['compiler_version']='0.8.31'
        r=cl.evaluate(m,raw)[0]
        self.assertFalse(r['all_declared_storage_heads_checked'])
        self.assertEqual(r['bindings']['after']['storage_head_placement']['reason'],'COMPILER_VERSION_OUTSIDE_PLACEMENT_PROFILE')

    def test_inheritance_has_no_fake_zero_base_claim(self):
        r=sp.verify_heads(contract={},lineage=[1,2],persistent={},storage={},source=b'',file_id=0,
                          compiler_version='0.8.30',typed=[])
        self.assertEqual(r['reason'],'INHERITANCE_ORDER_NOT_RECONSTRUCTED')
        self.assertFalse(r['all_declared_heads_checked'])

    def test_mapping_and_array_heads_supported(self):
        for f in (previous.mapping(),previous.array(),previous.array(length=''),previous.single('bytes')):
            with self.subTest(kind=f[0]):
                self.before=f;self.after=deepcopy(f)
                self.assertTrue(self.go()['all_declared_storage_heads_checked'])

    def test_unchecked_type_cannot_count_as_placement_verified(self):
        self.contract()['nodes'][0]['typeName']['nodeType']='UserDefinedTypeName'
        r=self.go();self.assertFalse(r['all_declared_storage_heads_checked'])
        self.assertEqual(r['bindings']['after']['storage_head_placement']['reason'],'TYPE_COVERAGE_INCOMPLETE')

    def test_two_algorithms_must_agree(self):
        with patch.object(sp,'allocate_reference',return_value=[]),self.assertRaisesRegex(sp.PlacementError,'ALGORITHMS_DISAGREE'):
            self.go()

    def test_valid_layout_change_remains_a_change(self):
        self.after=synthetic(('uint128','uint256'),((0,0),(1,0)))
        r=self.go();self.assertTrue(r['all_declared_storage_heads_checked'])
        self.assertEqual(r['status'],'SOURCE_LAYOUT_CHANGE_DETECTED')

    def test_empty_contract_has_zero_heads(self):
        self.before=synthetic((),());self.after=deepcopy(self.before)
        r=self.go();self.assertTrue(r['all_declared_storage_heads_checked'])
        self.assertEqual(r['bindings']['after']['storage_head_placement']['checked'],0)

    def test_inputs_are_not_mutated(self):
        old=deepcopy((self.before,self.after));self.go();self.assertEqual((self.before,self.after),old)

    def test_no_network_or_target_execution(self):
        with patch('socket.socket',side_effect=AssertionError),patch('subprocess.run',side_effect=AssertionError):
            self.create();cl.verify(self.root/'case',self.root/'expected.json')

    def test_no_output_on_placement_mismatch(self):
        self.store()['storage'][0]['slot']='8'
        with self.assertRaises(sp.PlacementError):self.create()
        self.assertFalse((self.root/'case').exists())

    def test_external_profile_cannot_be_downgraded(self):
        self.create();p=self.root/'case/manifest.json';m=strict_json(p.read_bytes());m['schema_version']=2
        p.write_bytes(canonical(m));marker=strict_json((p.parent/'COMPLETE.json').read_bytes())
        marker['sha256'][p.name]=cl.layout.sha(p.read_bytes());(p.parent/'COMPLETE.json').write_bytes(canonical(marker))
        with self.assertRaisesRegex(ValueError,'EXTERNAL_REFERENCE_MISMATCH'):
            cl.verify(p.parent,self.root/'expected.json')

    def test_resealed_result_rejected(self):
        self.create();p=self.root/'case/result.json';r=strict_json(p.read_bytes());r['compiler_executed_here']=True
        p.write_bytes(canonical(r));marker=strict_json((p.parent/'COMPLETE.json').read_bytes())
        marker['sha256'][p.name]=cl.layout.sha(p.read_bytes());(p.parent/'COMPLETE.json').write_bytes(canonical(marker))
        with self.assertRaisesRegex(ValueError,'RECOMPUTATION_MISMATCH'):
            cl.verify(p.parent,self.root/'expected.json')

    def test_private_permissions_and_external_verification(self):
        self.create();bundle=self.root/'case'
        self.assertEqual(bundle.stat().st_mode & 0o777,0o700)
        self.assertTrue(all(p.stat().st_mode & 0o777==0o600 for p in bundle.iterdir()))
        self.assertEqual(cl.verify(bundle,self.root/'expected.json')['status'],'SOURCE_LAYOUT_PRESERVED_IN_PROFILE')

    def test_cli_runs_full_profile_in_separate_process(self):
        self.prepare()
        command=[sys.executable,'-B','-m','superhunter','review-compiler-layout','--expected',str(self.root/'expected.json')]
        for name in cl.RAW_NAMES:command += ['--'+name[:-5],str(self.root/name)]
        command+=['--out',str(self.root/'case')]
        first=subprocess.run(command,cwd=cl.ROOT.parent,capture_output=True,text=True,timeout=30)
        self.assertEqual(first.returncode,0,first.stderr+first.stdout)
        second=subprocess.run([sys.executable,'-B','-m','superhunter','verify-compiler-layout',
                               '--bundle',str(self.root/'case'),'--expected',str(self.root/'expected.json')],
                               cwd=cl.ROOT.parent,capture_output=True,text=True,timeout=30)
        self.assertEqual(second.returncode,0,second.stderr+second.stdout)
        self.assertFalse(json.loads(second.stdout)['compiler_executed_here'])

    def test_original_profiles_do_not_claim_placement(self):
        for version in (1,2):
            r=self.go(version)
            self.assertNotIn('all_declared_storage_heads_checked',r)
            self.assertNotIn('storage_head_placement',r['bindings']['after'])

    def test_engine_identity_contains_the_new_code(self):
        self.assertIn('storage_placement.py',cl._engine()['sources'])

    def test_qa_registration_and_mandatory_checks(self):
        from superhunter import quality
        self.assertIn('storage_placement',quality.COMPONENTS['compiler_layout']['depends'])
        self.assertIn('storage_placement.py',quality.COMPONENTS['storage_placement']['files'])
        self.assertIn('test_storage_placement.PlacementBindingTests.test_custom_base_requires_review',quality.REQUIRED_TESTS)


if __name__=='__main__':unittest.main()
