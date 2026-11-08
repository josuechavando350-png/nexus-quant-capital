"""Supplied Standard JSON/AST fixtures, NOT claims of solc execution.

Sources are benign declarations. These tests check artifact relationships and
call the real existing layout analyzer; they do not reproduce vulnerabilities.
"""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from superhunter import compiler_layout as cl, storage_layout as sl
from superhunter.safe_io import canonical, strict_json


def fixture(names=('balance','total'), *, source='Local.sol', contract='Ledger',
            first_id=0, file_id=0, modes=None):
    modes = modes or {}
    header = '// Fixture sintética propia; solc NO ejecutado.\npragma solidity ^0.8.30;\n'
    parts=[]
    for name in names:
        mode=modes.get(name,'mutable')
        parts.append('uint256 '+('constant ' if mode=='constant' else 'immutable ' if mode=='immutable' else
                                'transient ' if mode=='transient' else '')+name+
                     (' = 1;' if mode in ('constant','immutable') else ';'))
    text=header+'contract '+contract+' {\n'+'\n'.join(parts)+'\n}\n'
    raw=text.encode()
    start=raw.index(('contract '+contract).encode())
    end=raw.rfind(b'}')+1
    nodes=[]; rows=[]; slot=0
    for i,(name,declaration) in enumerate(zip(names,parts)):
        mode=modes.get(name,'mutable')
        pos=raw.index(declaration.encode())
        node={'id':first_id+10+i,'nodeType':'VariableDeclaration','name':name,
              'stateVariable':True,'constant':mode=='constant',
              'mutability':mode if mode!='transient' else 'mutable',
              'storageLocation':'transient' if mode=='transient' else 'default',
              'src':f'{pos}:{len(declaration.encode())}:{file_id}',
              'nameLocation':f'{pos+declaration.index(name)}:{len(name)}:{file_id}'}
        nodes.append(node)
        if mode=='mutable':
            rows.append({'astId':node['id'],'contract':source+':'+contract,'label':name,
                         'slot':str(slot),'offset':0,'type':'t_uint256'});slot+=1
    c={'id':first_id+1,'nodeType':'ContractDefinition','name':contract,'nodes':nodes,
       'baseContracts':[],'linearizedBaseContracts':[first_id+1],'src':f'{start}:{end-start}:{file_id}'}
    ast={'id':first_id,'nodeType':'SourceUnit','absolutePath':source,'nodes':[c],
         'src':f'0:{len(raw)}:{file_id}'}
    inp={'language':'Solidity','sources':{source:{'content':text}},
         'settings':{'outputSelection':{'*':{'':['ast'],'*':['storageLayout']}}}}
    out={'sources':{source:{'id':file_id,'ast':ast}},'contracts':{source:{contract:{'storageLayout':{
        'storage':rows,'types':{'t_uint256':{'encoding':'inplace','label':'uint256','numberOfBytes':'32'}}}}}}}
    return inp,out


def pair(before=None,after=None):
    before=fixture() if before is None else before
    after=deepcopy(before) if after is None else after
    originals=dict(zip(cl.RAW_NAMES,(canonical(before[0]),canonical(before[1]),canonical(after[0]),canonical(after[1]))))
    manifest={'schema_version':1,'repo':'example/own-layout','source':'Local.sol','contract':'Ledger',
              **{s:{'commit':('a' if s=='before' else 'b')*40,'compiler_version':'0.8.30',
                    'input_sha256':sl.sha(originals[s+'-input.json']),
                    'output_sha256':sl.sha(originals[s+'-output.json'])} for s in ('before','after')}}
    return manifest,originals


class CompilerLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.out=self.root/'case'
        self.before=fixture();self.after=fixture()

    def run_review(self):
        return cl.evaluate(*pair(self.before,self.after))[0]

    def ast_contract(self, side=None):
        return (side or self.after)[1]['sources']['Local.sol']['ast']['nodes'][0]

    def storage(self,side=None):
        return (side or self.after)[1]['contracts']['Local.sol']['Ledger']['storageLayout']

    def prepare(self):
        m,raw=pair(self.before,self.after)
        (self.root/'expected.json').write_bytes(canonical(m))
        for n,v in raw.items():(self.root/n).write_bytes(v)
        return m,raw

    def create(self):
        self.prepare()
        return cl.create(self.root/'expected.json',*[self.root/n for n in cl.RAW_NAMES],self.out)

    def verify(self):return cl.verify(self.out,self.root/'expected.json')

    def reseal(self,name,mutate):
        p=self.out/name;v=strict_json(p.read_bytes());mutate(v);raw=canonical(v);p.write_bytes(raw)
        marker=strict_json((self.out/'COMPLETE.json').read_bytes());marker['sha256'][name]=sl.sha(raw)
        (self.out/'COMPLETE.json').write_bytes(canonical(marker))

    def test_actual_layout_analyzer_is_called(self):
        with patch.object(cl.layout,'compare',wraps=sl.compare) as call:
            r=self.run_review()
        self.assertEqual(call.call_count,1)
        self.assertEqual(r['status'],'SOURCE_LAYOUT_PRESERVED_IN_PROFILE')
        self.assertEqual(r['bindings']['before']['persistent_declarations'],2)
        for key in ('compiler_executed_here','compiler_output_authenticated','source_syntax_reparsed',
                    'deployed_state_verified','upgrade_authorized','vulnerability_confirmed'):
            self.assertIs(r[key],False)

    def test_source_declarations_bound_with_byte_spans(self):
        r=self.run_review();b=r['bindings']['after']['bound_declarations'][0]
        raw=self.after[0]['sources']['Local.sol']['content'].encode()
        self.assertEqual(raw[b['start_byte']:b['start_byte']+b['length_bytes']],b'uint256 balance;')
        self.assertEqual(b['span_sha256'],sl.sha(b'uint256 balance;'))

    def test_append_preserves_existing_layout(self):
        self.after=fixture(('balance','total','newCounter'))
        self.assertEqual(self.run_review()['status'],'SOURCE_LAYOUT_PRESERVED_IN_PROFILE')

    def test_reorder_detected_through_bound_pipeline(self):
        self.after=fixture(('total','balance'))
        r=self.run_review()
        self.assertEqual(r['status'],'SOURCE_LAYOUT_CHANGE_DETECTED')
        self.assertEqual(len(r['layout_review']['changes']),2)

    def test_error_json_cannot_be_used_as_success(self):
        self.after[1]['errors']=[{'severity':'error','message':'PRIVATE_ERROR'}]
        with self.assertRaisesRegex(cl.BindingError,'COMPILER_ERROR_IN_ARTIFACT'):self.run_review()

    def test_warnings_retained_not_printed(self):
        self.after[1]['errors']=[{'severity':'warning','message':'PRIVATE_WARNING'}]
        r=self.run_review()
        self.assertEqual(r['bindings']['after']['diagnostic_counts'],{'warning':1})
        self.assertNotIn('PRIVATE_WARNING',cl.render(r).decode())

    def test_unknown_diagnostic_severity_not_ignored(self):
        self.after[1]['errors']=[{'severity':'maybe-error'}]
        with self.assertRaisesRegex(cl.BindingError,'DIAGNOSTICS_SCHEMA'):self.run_review()

    def test_nonlist_diagnostics_rejected(self):
        self.after[1]['errors']={'severity':'error'}
        with self.assertRaises(cl.BindingError):self.run_review()

    def test_omitted_state_variable_rejected(self):
        self.storage()['storage'].pop()
        with self.assertRaisesRegex(cl.BindingError,'COVERAGE_MISMATCH'):self.run_review()

    def test_stale_ast_name_does_not_match_modified_source(self):
        original=self.after[0]['sources']['Local.sol']['content']
        self.after[0]['sources']['Local.sol']['content']=original.replace('balance','balancX')
        with self.assertRaisesRegex(cl.BindingError,'NAME_BYTES_MISMATCH'):self.run_review()

    def test_missing_name_location_not_guessed(self):
        self.ast_contract()['nodes'][0].pop('nameLocation')
        with self.assertRaisesRegex(cl.BindingError,'SOURCE_SPAN_FORMAT'):self.run_review()

    def test_name_location_outside_its_declaration_rejected(self):
        self.ast_contract()['nodes'][0]['nameLocation']=self.ast_contract()['nodes'][1]['nameLocation']
        with self.assertRaisesRegex(cl.BindingError,'NAME_BYTES_MISMATCH'):self.run_review()

    def test_trailing_source_whitespace_need_not_be_inside_root_span(self):
        info=self.after[1]['sources']['Local.sol'];raw=self.after[0]['sources']['Local.sol']['content'].encode()
        info['ast']['src']=f"0:{raw.rfind(b'}')+1}:0"
        self.assertEqual(self.run_review()['status'],'SOURCE_LAYOUT_PRESERVED_IN_PROFILE')

    def test_same_size_comment_change_not_claimed_to_be_semantic_analysis(self):
        text=self.after[0]['sources']['Local.sol']['content']
        self.after[0]['sources']['Local.sol']['content']=text.replace('propia','ajenaa')
        r=self.run_review()
        self.assertTrue(r['source_bytes_changed'])
        self.assertFalse(r['source_syntax_reparsed'])

    def test_wrong_ast_id_rejected(self):
        self.storage()['storage'][0]['astId']=999
        with self.assertRaisesRegex(cl.BindingError,'NOT_PERSISTENT'):self.run_review()

    def test_duplicated_layout_declaration_rejected(self):
        self.storage()['storage'][1]['astId']=self.storage()['storage'][0]['astId']
        with self.assertRaisesRegex(cl.BindingError,'LAYOUT_DECLARATION_ID'):self.run_review()

    def test_wrong_ast_label_rejected(self):
        self.storage()['storage'][0]['label']='different'
        with self.assertRaisesRegex(cl.BindingError,'LABEL_MISMATCH'):self.run_review()

    def test_foreign_row_contract_rejected_even_if_wrapper_matches(self):
        self.storage()['storage'][0]['contract']='Other.sol:Ledger'
        with self.assertRaisesRegex(cl.BindingError,'LAYOUT_CONTRACT_MISMATCH'):self.run_review()

    def test_missing_selected_contract_rejected(self):
        self.after[1]['contracts']['Local.sol']={}
        with self.assertRaisesRegex(cl.BindingError,'CONTRACT_OUTPUT_MISSING'):self.run_review()

    def test_same_contract_name_in_other_source_not_selected(self):
        self.after[1]['contracts']={'Other.sol':self.after[1]['contracts']['Local.sol']}
        with self.assertRaisesRegex(cl.BindingError,'CONTRACT_OUTPUT_MISSING'):self.run_review()

    def test_missing_ast_rejected(self):
        self.after[1]['sources']['Local.sol'].pop('ast')
        with self.assertRaisesRegex(cl.BindingError,'SOURCE_AST_REQUIRED'):self.run_review()

    def test_foreign_source_unit_name_rejected(self):
        self.after[1]['sources']['Local.sol']['ast']['absolutePath']='Other.sol'
        with self.assertRaisesRegex(cl.BindingError,'SOURCE_AST_REQUIRED'):self.run_review()

    def test_added_output_source_rejected(self):
        self.after[1]['sources']['Other.sol']={}
        with self.assertRaisesRegex(cl.BindingError,'INVENTORY_MISMATCH'):self.run_review()

    def test_missing_output_source_rejected(self):
        self.after[1]['sources']={}
        with self.assertRaisesRegex(cl.BindingError,'INVENTORY_MISMATCH'):self.run_review()

    def test_url_sources_never_fetched(self):
        self.after[0]['sources']['Local.sol']={'urls':['https://example.invalid/source.sol']}
        with patch('socket.socket',side_effect=AssertionError),self.assertRaisesRegex(cl.BindingError,'INLINE_SOURCE_REQUIRED'):
            self.run_review()

    def test_missing_requested_output_rejected(self):
        for key in ('','*'):
            with self.subTest(key=key):
                self.after=fixture();self.after[0]['settings']['outputSelection']['*'].pop(key)
                with self.assertRaisesRegex(cl.BindingError,'OUTPUT_NOT_REQUESTED'):self.run_review()

    def test_explicit_output_selection_works(self):
        self.after[0]['settings']['outputSelection']={'Local.sol':{'':['ast'],'Ledger':['storageLayout']}}
        r=self.run_review()
        self.assertEqual(r['status'],'SOURCE_LAYOUT_REVIEW_REQUIRED')
        self.assertTrue(r['compiler_settings_changed'])

    def test_optimizer_difference_requires_review(self):
        self.after[0]['settings']['optimizer']={'enabled':True,'runs':200}
        self.assertEqual(self.run_review()['status'],'SOURCE_LAYOUT_REVIEW_REQUIRED')

    def test_whole_source_span_must_match_bytes(self):
        ast=self.after[1]['sources']['Local.sol']['ast'];ast['src']='0:1:0'
        with self.assertRaisesRegex(cl.BindingError,'SOURCE_UNIT_SPAN'):self.run_review()

    def test_variable_span_file_id_mismatch_rejected(self):
        var=self.ast_contract()['nodes'][0];var['src']=var['src'].rsplit(':',1)[0]+':7'
        with self.assertRaisesRegex(cl.BindingError,'SOURCE_SPAN_FILE'):self.run_review()

    def test_out_of_bounds_span_rejected(self):
        self.ast_contract()['nodes'][0]['src']='99999:5:0'
        with self.assertRaisesRegex(cl.BindingError,'SOURCE_SPAN_BOUNDS'):self.run_review()

    def test_utf8_split_rejected(self):
        raw=self.after[0]['sources']['Local.sol']['content'].encode()
        self.ast_contract()['nodes'][0]['src']=f"{raw.index('é'.encode())+1}:1:0"
        with self.assertRaisesRegex(cl.BindingError,'SOURCE_SPAN_UTF8'):self.run_review()

    def test_declaration_outside_contract_rejected(self):
        self.ast_contract()['nodes'][0]['src']='0:5:0'
        with self.assertRaisesRegex(cl.BindingError,'DECLARATION_OUTSIDE_CONTRACT'):self.run_review()

    def test_duplicate_ast_id_rejected(self):
        self.ast_contract()['nodes'][1]['id']=self.ast_contract()['nodes'][0]['id']
        with self.assertRaisesRegex(cl.BindingError,'AST_NODE_ID'):self.run_review()

    def test_boolean_ids_not_integers(self):
        for section in ('source','ast','layout'):
            with self.subTest(section=section):
                self.after=fixture()
                if section=='source':self.after[1]['sources']['Local.sol']['id']=True
                elif section=='ast':self.ast_contract()['id']=True
                else:self.storage()['storage'][0]['astId']=True
                with self.assertRaises(cl.BindingError):self.run_review()

    def test_nonstate_declaration_cannot_be_storage(self):
        self.ast_contract()['nodes'][0]['stateVariable']=False
        with self.assertRaisesRegex(cl.BindingError,'TOP_LEVEL_STATE'):self.run_review()

    def test_constant_immutable_transient_not_counted_as_persistent(self):
        self.after=fixture(('balance','total','c','im','t'),modes={'c':'constant','im':'immutable','t':'transient'})
        r=self.run_review()
        self.assertEqual(r['bindings']['after']['excluded_declarations'],{'constant':1,'immutable':1,'transient':1})
        self.assertEqual(r['bindings']['after']['persistent_declarations'],2)

    def test_constant_cannot_be_inserted_into_persistent_layout(self):
        self.after=fixture(('balance','total'),modes={'total':'constant'})
        self.storage()['storage'].append({'astId':11,'label':'total','contract':'Local.sol:Ledger',
                                         'slot':'1','offset':0,'type':'t_uint256'})
        with self.assertRaisesRegex(cl.BindingError,'NOT_PERSISTENT'):self.run_review()

    def test_mutability_flags_must_agree(self):
        self.ast_contract()['nodes'][0]['constant']=True
        with self.assertRaisesRegex(cl.BindingError,'MUTABILITY_CONTRADICTION'):self.run_review()

    def test_inheritance_missing_ancestor_rejected(self):
        self.ast_contract()['linearizedBaseContracts']=[1,99]
        with self.assertRaisesRegex(cl.BindingError,'CLOSURE_MISMATCH'):self.run_review()

    def test_inheritance_references_unknown_contract_rejected(self):
        self.ast_contract()['baseContracts']=[{'baseName':{'referencedDeclaration':99}}]
        with self.assertRaisesRegex(cl.BindingError,'INHERITANCE_REFERENCE'):self.run_review()

    def test_inheritance_cycle_rejected(self):
        self.ast_contract()['baseContracts']=[{'baseName':{'referencedDeclaration':1}}]
        with self.assertRaisesRegex(cl.BindingError,'INHERITANCE_CYCLE'):self.run_review()

    def test_valid_inherited_state_in_another_source_is_bound(self):
        inherited=fixture(('baseCounter',),source='Base.sol',contract='Base',first_id=100,file_id=1)
        self.after[0]['sources'].update(inherited[0]['sources'])
        self.after[1]['sources'].update(inherited[1]['sources'])
        self.ast_contract()['baseContracts']=[{'baseName':{'referencedDeclaration':101}}]
        self.ast_contract()['linearizedBaseContracts']=[1,101]
        rows=self.storage()['storage']
        for r in rows:r['slot']=str(int(r['slot'])+1)
        rows.insert(0,{'astId':110,'label':'baseCounter','contract':'Local.sol:Ledger',
                       'slot':'0','offset':0,'type':'t_uint256'})
        r=self.run_review()
        self.assertEqual(r['bindings']['after']['contract_ancestry_count'],2)
        self.assertEqual(r['bindings']['after']['persistent_declarations'],3)
        self.assertEqual(r['status'],'SOURCE_LAYOUT_CHANGE_DETECTED')

    def test_source_bytes_changed_without_new_external_binding_rejected(self):
        m,raw=pair(self.before,self.after)
        changed=strict_json(raw['after-input.json']);changed['sources']['Local.sol']['content']+='// extra'
        raw['after-input.json']=canonical(changed)
        with self.assertRaisesRegex(cl.BindingError,'HASH_MISMATCH'):cl.evaluate(m,raw)

    def test_ast_size_budget_is_enforced(self):
        with patch.object(cl,'MAX_AST_OBJECTS',1),self.assertRaisesRegex(cl.BindingError,'AST_BUDGET'):
            self.run_review()

    def test_source_size_budget_is_enforced(self):
        with patch.object(cl,'MAX_SOURCE_BYTES',1),self.assertRaisesRegex(cl.BindingError,'SOURCE_BYTES_BUDGET'):
            self.run_review()

    def test_no_source_execution_or_external_access(self):
        with patch('socket.socket',side_effect=AssertionError),patch('subprocess.run',side_effect=AssertionError):
            self.create();self.verify()

    def test_native_audit_called_with_input_binding(self):
        native=cl.load_components()
        with patch.object(native.audit.AuditLog,'append',autospec=True,side_effect=native.audit.AuditLog.append) as append:
            self.create()
        self.assertGreaterEqual(append.call_count,4)
        event=next(c.args for c in append.call_args_list if c.args[1]=='compiler_layout.inputs')
        self.assertEqual(set(event[2]['inputs']),set(cl.RAW_NAMES))

    def test_originals_preserved_and_repeated_verification_deterministic(self):
        m,originals=self.prepare();self.create()
        for name,raw in originals.items():self.assertEqual((self.out/name).read_bytes(),raw)
        self.assertEqual(self.verify(),self.verify())

    def test_downstream_review_uses_real_derived_artifacts(self):
        self.after=fixture(('total','balance'));r=self.create()
        derived=sl.compare(strict_json((self.out/'layout-manifest.json').read_bytes()),
                           (self.out/'before-layout.json').read_bytes(),(self.out/'after-layout.json').read_bytes())
        self.assertEqual(derived,r['layout_review'])

    def test_external_reference_cannot_be_embedded(self):
        self.create()
        with self.assertRaisesRegex(cl.BindingError,'EXTERNAL_MANIFEST_REQUIRED'):
            cl.verify(self.out,self.out/'manifest.json')

    def test_wrong_external_manifest_rejected(self):
        self.create();p=self.root/'expected.json';m=strict_json(p.read_bytes());m['after']['commit']='c'*40;p.write_bytes(canonical(m))
        with self.assertRaisesRegex(cl.BindingError,'EXTERNAL_REFERENCE_MISMATCH'):self.verify()

    def test_resealed_confirmed_claim_rejected(self):
        self.create();self.reseal('result.json',lambda v:v.update(vulnerability_confirmed=True))
        with self.assertRaisesRegex(cl.BindingError,'RECOMPUTATION_MISMATCH'):self.verify()

    def test_resealed_derived_layout_rejected(self):
        self.create();self.reseal('after-layout.json',lambda v:v['storage_layout']['storage'][0].update(slot='9'))
        with self.assertRaisesRegex(cl.BindingError,'RECOMPUTATION_MISMATCH'):self.verify()

    def test_resealed_audit_cannot_change_binding(self):
        self.create();self.reseal('audit.json',lambda v:v['entries'][0]['data'].update(manifest_sha256='0'*64))
        with self.assertRaisesRegex(cl.BindingError,'RECOMPUTATION_MISMATCH'):self.verify()

    def test_extra_file_not_silently_included(self):
        self.create();(self.out/'secret').write_text('do not include')
        with self.assertRaisesRegex(cl.BindingError,'BUNDLE_FILES'):self.verify()

    def test_symlinks_not_read(self):
        self.create();p=self.out/'after-input.json';p.unlink();p.symlink_to(self.root/'after-input.json')
        with self.assertRaises((OSError,ValueError)):self.verify()

    def test_private_files_and_no_overwrite(self):
        self.create();before=(self.out/'COMPLETE.json').read_bytes()
        self.assertEqual(self.out.stat().st_mode&0o777,0o700)
        for p in self.out.iterdir():self.assertEqual(p.stat().st_mode&0o777,0o600)
        with self.assertRaisesRegex(cl.BindingError,'NEW_OUTPUT_REQUIRED'):self.create()
        self.assertEqual((self.out/'COMPLETE.json').read_bytes(),before)

    def test_input_change_during_capture_rejected(self):
        self.prepare();original=cl._documents
        def changed(*args):
            result=original(*args);(self.root/'after-input.json').write_bytes(b'{}');return result
        with patch.object(cl,'_documents',side_effect=changed),self.assertRaisesRegex(cl.BindingError,'INPUT_CHANGED'):
            cl.create(self.root/'expected.json',*[self.root/n for n in cl.RAW_NAMES],self.out)
        self.assertFalse((self.out/'COMPLETE.json').exists())

    def test_error_diagnostics_hide_private_paths(self):
        with redirect_stdout(io.StringIO()) as output:
            rc=cl.main(['verify-compiler-layout','--bundle',str(self.root/'PRIVATE_MARKER'),'--expected',str(self.root/'absent')])
        self.assertEqual(rc,2);self.assertNotIn('PRIVATE_MARKER',output.getvalue())

    def test_invalid_cli_arguments_not_echoed(self):
        with patch('sys.stderr',new_callable=io.StringIO) as stream,self.assertRaises(SystemExit):
            cl.main(['verify-compiler-layout','--bundle','x','--expected','y','--unexpected','PRIVATE_MARKER'])
        self.assertNotIn('PRIVATE_MARKER',stream.getvalue())

    def test_cli_create_verify_in_separate_processes(self):
        self.prepare()
        args=['review-compiler-layout','--expected',str(self.root/'expected.json'),'--out',str(self.out)]
        for name in cl.RAW_NAMES:args += ['--'+name.removesuffix('.json'),str(self.root/name)]
        for command in (args,['verify-compiler-layout','--bundle',str(self.out),'--expected',str(self.root/'expected.json')]):
            p=subprocess.run([sys.executable,'-B','-m','superhunter',*command],cwd=cl.ROOT.parent,
                             capture_output=True,text=True,timeout=30)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            self.assertFalse(json.loads(p.stdout)['compiler_executed_here'])

    def test_qa_component_and_mandatory_tests_registered(self):
        from superhunter import quality
        self.assertIn('compiler_layout',quality.COMPONENTS)
        self.assertIn('storage_layout',quality.COMPONENTS['compiler_layout']['depends'])
        self.assertIn('test_compiler_layout.CompilerLayoutTests.test_omitted_state_variable_rejected',quality.REQUIRED_TESTS)


if __name__ == '__main__':unittest.main()
