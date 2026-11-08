"""Storage compatibility tests; artifacts are explicit synthetic compiler-format fixtures.

No compiler, target contract, deployment or exploit is executed. Expected changes
are independently constructed from bounded slot/type examples.
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

from superhunter import storage_layout as sl
from superhunter.safe_io import canonical, strict_json


def var(label, typ='u256', slot=0, offset=0, ast_id=1):
    return {'astId': ast_id, 'contract': 'Local.sol:Vault', 'label': label,
            'offset': offset, 'slot': str(slot), 'type': typ}


def types():
    return {'u256': {'encoding': 'inplace', 'label': 'uint256', 'numberOfBytes': '32'},
            'u128': {'encoding': 'inplace', 'label': 'uint128', 'numberOfBytes': '16'},
            'i256': {'encoding': 'inplace', 'label': 'int256', 'numberOfBytes': '32'},
            'addr': {'encoding': 'inplace', 'label': 'address', 'numberOfBytes': '20'},
            'bool': {'encoding': 'inplace', 'label': 'bool', 'numberOfBytes': '1'},
            'u8': {'encoding': 'inplace', 'label': 'uint8', 'numberOfBytes': '1'}}


def artifact(commit, rows=None):
    return {'schema_version': 1,
            'target': {'repo': 'example/local-layout', 'commit': commit, 'contract': 'Local.sol:Vault'},
            'compiler_version': '0.8.30',
            'storage_layout': {'storage': rows if rows is not None else [var('counter')], 'types': types()}}


def pair(before=None, after=None):
    before = artifact('a'*40) if before is None else before
    after = deepcopy(before) if after is None else after
    before['target']['commit']='a'*40;after['target']['commit']='b'*40
    b,a=canonical(before),canonical(after)
    m={'schema_version':1,'repo':'example/local-layout','contract':'Local.sol:Vault',
       'before':{'commit':'a'*40,'sha256':sl.sha(b)},'after':{'commit':'b'*40,'sha256':sl.sha(a)}}
    return m,b,a


class StorageLayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.before=artifact('a'*40)
        self.after=artifact('b'*40)
        self.out=self.root/'review'

    def run_compare(self):
        return sl.compare(*pair(self.before,self.after))

    def prepare(self):
        m,b,a=pair(self.before,self.after)
        for name,raw in (('manifest.json',canonical(m)),('before.json',b),('after.json',a)):
            (self.root/name).write_bytes(raw)
        return m

    def create(self):
        self.prepare()
        return sl.create(self.root/'manifest.json',self.root/'before.json',self.root/'after.json',self.out)

    def verify(self):
        return sl.verify(self.out,self.root/'manifest.json')

    def reseal(self,name,edit):
        p=self.out/name;value=strict_json(p.read_bytes());edit(value)
        raw=canonical(value);p.write_bytes(raw)
        marker=strict_json((self.out/'COMPLETE.json').read_bytes());marker['sha256'][name]=sl.sha(raw)
        (self.out/'COMPLETE.json').write_bytes(canonical(marker))

    def test_identical_shape_has_no_execution_or_upgrade_claim(self):
        r=self.run_compare()
        self.assertEqual(r['status'],'LAYOUT_PRESERVED_IN_PROFILE')
        for k in ('compiler_executed','source_or_bytecode_authenticated','deployed_storage_verified',
                  'upgrade_authorized','vulnerability_confirmed'):
            self.assertIs(r[k],False)
        self.assertTrue(r['manual_review_required'])

    def test_append_preserves_existing_layout(self):
        self.after['storage_layout']['storage'].append(var('next',slot=1))
        r=self.run_compare();self.assertEqual(r['status'],'LAYOUT_PRESERVED_IN_PROFILE')
        self.assertEqual(r['added_declarations'],1)

    def test_append_into_remaining_packed_bytes(self):
        self.before['storage_layout']['storage']=[var('a','u128')]
        self.after=deepcopy(self.before)
        self.after['storage_layout']['storage'].append(var('b','u128',offset=16))
        self.assertEqual(self.run_compare()['status'],'LAYOUT_PRESERVED_IN_PROFILE')

    def test_variable_slot_move_is_detected(self):
        self.after['storage_layout']['storage'][0]['slot']='1'
        self.assertEqual(self.run_compare()['changes'][0]['code'],'DECLARATION_MOVED')

    def test_reordered_variables_not_hidden_by_same_total_size(self):
        self.before['storage_layout']['storage']=[var('left',slot=0),var('right',slot=1)]
        self.after['storage_layout']['storage']=[var('right',slot=0),var('left',slot=1)]
        r=self.run_compare();self.assertEqual(r['status'],'LAYOUT_CHANGE_DETECTED')
        self.assertEqual(len(r['changes']),2)

    def test_packed_offset_change_is_detected(self):
        self.before['storage_layout']['storage']=[var('a','u128')]
        self.after['storage_layout']['storage']=[var('a','u128',offset=16)]
        self.assertEqual(self.run_compare()['status'],'LAYOUT_CHANGE_DETECTED')

    def test_same_size_signedness_change_detected(self):
        self.after['storage_layout']['storage'][0]['type']='i256'
        self.assertEqual(self.run_compare()['changes'][0]['code'],'TYPE_SHAPE_CHANGED')

    def test_type_ids_and_ast_ids_not_semantic_identity(self):
        desc=self.after['storage_layout']['types'].pop('u256')
        self.after['storage_layout']['types']['compiler-id-991']=desc
        row=self.after['storage_layout']['storage'][0];row['type']='compiler-id-991';row['astId']=994
        self.assertEqual(self.run_compare()['status'],'LAYOUT_PRESERVED_IN_PROFILE')

    def test_input_list_order_not_storage_order(self):
        self.before['storage_layout']['storage']=[var('a',slot=0),var('b',slot=1)]
        self.after=deepcopy(self.before);self.after['storage_layout']['storage'].reverse()
        self.assertEqual(self.run_compare()['status'],'LAYOUT_PRESERVED_IN_PROFILE')

    def test_rename_requires_review_not_confirmed_corruption(self):
        self.after['storage_layout']['storage'][0]['label']='renamed'
        r=self.run_compare();self.assertEqual(r['status'],'LAYOUT_REVIEW_REQUIRED')
        self.assertEqual(r['changes'],[])

    def test_removed_variable_requires_review(self):
        self.after['storage_layout']['storage']=[]
        r=self.run_compare();self.assertEqual(r['status'],'LAYOUT_REVIEW_REQUIRED')
        self.assertIn('REMOVED_OR_RENAMED',[x['code'] for x in r['review_notes']])

    def test_insertion_before_old_footprint_requires_review(self):
        self.before['storage_layout']['storage'][0]['slot']='5'
        self.after=deepcopy(self.before);self.after['storage_layout']['storage'].append(var('added',slot=0))
        self.assertEqual(self.run_compare()['status'],'LAYOUT_REVIEW_REQUIRED')

    def test_compiler_change_requires_review(self):
        self.after['compiler_version']='0.8.29'
        self.assertEqual(self.run_compare()['status'],'LAYOUT_REVIEW_REQUIRED')

    def add_mapping(self):
        for a in (self.before,self.after):
            a['storage_layout']['types']['map']={'encoding':'mapping','label':'mapping(uint256 => uint256)',
                'numberOfBytes':'32','key':'u256','value':'u256'}
            a['storage_layout']['storage'][0]['type']='map'

    def test_mapping_key_change_detected_without_head_movement(self):
        self.add_mapping();self.after['storage_layout']['types']['map']['key']='addr'
        self.assertEqual(self.run_compare()['status'],'LAYOUT_CHANGE_DETECTED')

    def test_mapping_value_change_detected_without_head_movement(self):
        self.add_mapping();self.after['storage_layout']['types']['map']['value']='i256'
        self.assertEqual(self.run_compare()['status'],'LAYOUT_CHANGE_DETECTED')

    def test_nested_mapping_unchanged(self):
        self.add_mapping()
        for a in (self.before,self.after):
            a['storage_layout']['types']['outer']={'encoding':'mapping','label':'mapping(uint256 => mapping(uint256 => uint256))',
                'numberOfBytes':'32','key':'u256','value':'map'}
            a['storage_layout']['storage'][0]['type']='outer'
        self.assertEqual(self.run_compare()['status'],'LAYOUT_PRESERVED_IN_PROFILE')

    def test_dynamic_array_base_changed(self):
        for a in (self.before,self.after):
            a['storage_layout']['types']['arr']={'encoding':'dynamic_array','label':'uint256[]','numberOfBytes':'32','base':'u256'}
            a['storage_layout']['storage'][0]['type']='arr'
        self.after['storage_layout']['types']['arr']['base']='u128'
        self.assertEqual(self.run_compare()['status'],'LAYOUT_CHANGE_DETECTED')

    def test_fixed_array_length_not_just_rounded_byte_count(self):
        for a in (self.before,self.after):
            a['storage_layout']['types']['arr']={'encoding':'inplace','label':'uint8[2]','numberOfBytes':'32','base':'u8'}
            a['storage_layout']['storage'][0]['type']='arr'
        self.after['storage_layout']['types']['arr']['label']='uint8[3]'
        self.assertEqual(self.run_compare()['status'],'LAYOUT_CHANGE_DETECTED')

    def test_fixed_array_packing_size_is_checked(self):
        self.after['storage_layout']['types']['arr']={'encoding':'inplace','label':'uint128[3]','numberOfBytes':'48','base':'u128'}
        self.after['storage_layout']['storage'][0]['type']='arr'
        with self.assertRaisesRegex(sl.LayoutError,'ARRAY_SIZE_MISMATCH'):self.run_compare()

    def add_struct(self):
        for a in (self.before,self.after):
            a['storage_layout']['types']['struct']={'encoding':'inplace','label':'struct Vault.Pair','numberOfBytes':'32',
                'members':[var('a','u128'),var('b','u128',offset=16)]}
            a['storage_layout']['storage'][0]['type']='struct'

    def test_nested_struct_change_detected(self):
        self.add_struct();self.add_mapping()
        for a in (self.before,self.after):a['storage_layout']['types']['map']['value']='struct'
        s=self.after['storage_layout']['types']['struct']['members'];s[0]['offset']=16;s[1]['offset']=0
        self.assertEqual(self.run_compare()['status'],'LAYOUT_CHANGE_DETECTED')

    def test_struct_type_label_rename_ignores_unstable_type_name(self):
        self.add_struct();self.after['storage_layout']['types']['struct']['label']='struct NewVault.Pair'
        self.assertEqual(self.run_compare()['status'],'LAYOUT_PRESERVED_IN_PROFILE')

    def test_struct_footprint_size_checked(self):
        self.add_struct();self.after['storage_layout']['types']['struct']['numberOfBytes']='64'
        with self.assertRaisesRegex(sl.LayoutError,'STRUCT_SIZE_MISMATCH'):self.run_compare()

    def test_recursive_types_require_review(self):
        self.add_struct();self.add_mapping()
        for a in (self.before,self.after):
            a['storage_layout']['types']['struct']['members']=[var('children','map')]
            a['storage_layout']['types']['map']['value']='struct'
        r=self.run_compare();self.assertEqual(r['status'],'LAYOUT_REVIEW_REQUIRED')
        self.assertEqual(r['unsupported'][0]['reason'],'RECURSIVE_TYPE_REVIEW')

    def test_gap_consumption_not_automatically_approved(self):
        self.before['storage_layout']['types']['gap']={'encoding':'inplace','label':'uint256[3]','numberOfBytes':'96','base':'u256'}
        self.before['storage_layout']['storage'].append(var('__gap','gap',slot=1))
        self.after=deepcopy(self.before)
        self.after['storage_layout']['types']['gap'].update(label='uint256[2]',numberOfBytes='64')
        self.after['storage_layout']['storage'][1]['slot']='2'
        self.after['storage_layout']['storage'].append(var('added',slot=1))
        r=self.run_compare();self.assertEqual(r['status'],'LAYOUT_REVIEW_REQUIRED');self.assertEqual(r['changes'],[])

    def test_bytes_to_string_change_requires_review_signal(self):
        for a in (self.before,self.after):
            a['storage_layout']['types']['blob']={'encoding':'bytes','label':'bytes','numberOfBytes':'32'}
            a['storage_layout']['storage'][0]['type']='blob'
        self.after['storage_layout']['types']['blob']['label']='string'
        self.assertEqual(self.run_compare()['status'],'LAYOUT_CHANGE_DETECTED')

    def test_unsupported_custom_type_cannot_pass(self):
        self.after['storage_layout']['types']['u256']['label']='Vault.Amount'
        r=self.run_compare();self.assertEqual(r['status'],'LAYOUT_REVIEW_REQUIRED')
        self.assertFalse(r['upgrade_authorized'])

    def test_empty_state_is_not_complete_coverage(self):
        self.before['storage_layout']={'storage':[],'types':None}
        self.assertEqual(self.run_compare()['status'],'LAYOUT_REVIEW_REQUIRED')

    def test_duplicate_labels_not_guessed(self):
        self.after['storage_layout']['storage'].append(var('counter',slot=1,ast_id=2))
        r=self.run_compare();self.assertEqual(r['unsupported'][0]['reason'],'AMBIGUOUS_DECLARATION_LABEL')

    def test_overlap_rejected(self):
        self.after['storage_layout']['storage'].append(var('b','bool',slot=0))
        with self.assertRaisesRegex(sl.LayoutError,'OVERLAPPING_ALLOCATION'):self.run_compare()

    def test_primitive_size_cannot_be_forged(self):
        self.after['storage_layout']['types']['u256']['numberOfBytes']='16'
        with self.assertRaisesRegex(sl.LayoutError,'PRIMITIVE_SIZE_MISMATCH'):self.run_compare()

    def test_packed_field_crossing_slot_rejected(self):
        self.after['storage_layout']['storage']=[var('x','u128',offset=20)]
        with self.assertRaisesRegex(sl.LayoutError,'TYPE_ALIGNMENT'):self.run_compare()

    def test_aggregate_nonzero_offset_rejected(self):
        self.add_mapping();self.after['storage_layout']['storage'][0]['offset']=1
        with self.assertRaisesRegex(sl.LayoutError,'TYPE_ALIGNMENT'):self.run_compare()

    def test_boolean_schema_and_offset_not_integers(self):
        self.after['schema_version']=True
        with self.assertRaises(sl.LayoutError):self.run_compare()
        self.after['schema_version']=1;self.after['storage_layout']['storage'][0]['offset']=False
        with self.assertRaises(sl.LayoutError):self.run_compare()

    def test_noncanonical_slots_rejected(self):
        for v in ('01','-1','0x0','1e1','²',1):
            self.after['storage_layout']['storage'][0]['slot']=v
            with self.subTest(v=v),self.assertRaises(sl.LayoutError):self.run_compare()

    def test_high_slots_not_float_rounded(self):
        self.before['storage_layout']['storage'][0]['slot']=str((1<<240)+13)
        self.after['storage_layout']['storage'][0]['slot']=str((1<<240)+14)
        r=self.run_compare();self.assertEqual(r['status'],'LAYOUT_CHANGE_DETECTED')
        self.assertEqual(r['changes'][0]['before']['slot'],str((1<<240)+13))

    def test_storage_wrap_rejected(self):
        self.add_struct();self.after['storage_layout']['types']['struct']['members'].append(var('c',slot=1))
        self.after['storage_layout']['types']['struct']['numberOfBytes']='64'
        self.after['storage_layout']['storage'][0]['slot']=str((1<<256)-1)
        with self.assertRaisesRegex(sl.LayoutError,'STORAGE_ADDRESS_WRAP'):self.run_compare()

    def test_unexpected_layout_extension_not_silently_ignored(self):
        self.after['storage_layout']['namespaces']={}
        with self.assertRaisesRegex(sl.LayoutError,'LAYOUT_SCHEMA'):self.run_compare()

    def test_missing_type_rejected(self):
        self.after['storage_layout']['storage'][0]['type']='absent'
        with self.assertRaisesRegex(sl.LayoutError,'MISSING_TYPE'):self.run_compare()

    def test_budget_not_truncated(self):
        with patch.object(sl,'MAX_ENTRIES',0),self.assertRaisesRegex(sl.LayoutError,'ENTRY_BUDGET'):self.run_compare()
        with patch.object(sl,'MAX_TYPES',0),self.assertRaisesRegex(sl.LayoutError,'TYPE_BUDGET'):self.run_compare()

    def test_input_not_modified(self):
        m,b,a=pair(self.before,self.after);saved=canonical(m)
        sl.compare(m,b,a);self.assertEqual(canonical(m),saved)

    def test_manifest_binds_artifact_and_target(self):
        m,b,a=pair(self.before,self.after)
        with self.assertRaisesRegex(sl.LayoutError,'ARTIFACT_HASH_MISMATCH'):sl.compare(m,b,a+b' ')
        m['contract']='Other:Vault'
        with self.assertRaisesRegex(sl.LayoutError,'TARGET_BINDING_MISMATCH'):sl.compare(m,b,a)

    def test_roundtrip_calls_native_audit_and_preserves_originals(self):
        m=self.prepare();original={n:(self.root/n).read_bytes() for n in ('before.json','after.json','manifest.json')}
        native=sl.load_components()
        with patch.object(native.audit.AuditLog,'append',autospec=True,side_effect=native.audit.AuditLog.append) as record:
            r=sl.create(self.root/'manifest.json',self.root/'before.json',self.root/'after.json',self.out)
        self.assertGreaterEqual(record.call_count,4)
        self.assertEqual(self.verify(),r)
        for n,b in original.items():self.assertEqual((self.root/n).read_bytes(),b)

    def test_private_permissions_and_no_overwrite(self):
        self.create();self.assertEqual(self.out.stat().st_mode&0o777,0o700)
        for p in self.out.iterdir():self.assertEqual(p.stat().st_mode&0o777,0o600)
        with self.assertRaisesRegex(sl.LayoutError,'NEW_OUTPUT_REQUIRED'):self.create()

    def test_no_network_or_process_execution(self):
        with patch('socket.socket',side_effect=AssertionError),patch('subprocess.run',side_effect=AssertionError):
            self.create();self.verify()

    def test_embedded_manifest_cannot_be_external_trust(self):
        self.create()
        with self.assertRaisesRegex(sl.LayoutError,'EXTERNAL_MANIFEST_REQUIRED'):
            sl.verify(self.out,self.out/'manifest.json')

    def test_changed_external_reference_rejected(self):
        self.create();m=strict_json((self.root/'manifest.json').read_bytes());m['after']['sha256']='0'*64
        (self.root/'manifest.json').write_bytes(canonical(m))
        with self.assertRaisesRegex(sl.LayoutError,'EXTERNAL_REFERENCE_MISMATCH'):self.verify()

    def test_resealed_approval_cannot_replace_result(self):
        self.after['storage_layout']['storage'][0]['slot']='1';self.create()
        self.reseal('result.json',lambda d:d.update(status='LAYOUT_PRESERVED_IN_PROFILE',changes=[]))
        with self.assertRaisesRegex(sl.LayoutError,'RECOMPUTATION_MISMATCH'):self.verify()

    def test_resealed_audit_cannot_change_claim(self):
        self.create();self.reseal('audit.json',lambda d:d['entries'][0]['data'].update(manifest_sha256='0'*64))
        with self.assertRaisesRegex(sl.LayoutError,'RECOMPUTATION_MISMATCH'):self.verify()

    def test_extra_files_and_symlinks_rejected(self):
        self.create();(self.out/'extra.txt').write_text('unexpected')
        with self.assertRaisesRegex(sl.LayoutError,'BUNDLE_FILE_SET'):self.verify()
        (self.out/'extra.txt').unlink();p=self.out/'REVIEW.md';raw=p.read_bytes();p.unlink()
        (self.root/'other.txt').write_bytes(raw);p.symlink_to(self.root/'other.txt')
        with self.assertRaises((OSError,ValueError)):self.verify()

    def test_source_change_blocks_verification(self):
        self.create()
        with patch.object(sl,'_engine',return_value={'changed':True}),self.assertRaises(sl.LayoutError):self.verify()

    def test_console_and_report_omit_private_names(self):
        self.before['storage_layout']['storage'][0]['label']='PRIVATE_VALUE'
        self.after['storage_layout']['storage'][0]['label']='PRIVATE_VALUE'
        r=self.create();self.assertNotIn(b'PRIVATE_VALUE',sl.render(r))
        with redirect_stdout(io.StringIO()) as out:
            code=sl.main(['verify-layout','--bundle',str(self.out),'--expected',str(self.root/'manifest.json')])
        self.assertEqual(code,0);self.assertNotIn('PRIVATE_VALUE',out.getvalue())

    def test_cli_roundtrip_separate_processes(self):
        self.prepare()
        commands=[['review-layout','--manifest',str(self.root/'manifest.json'),'--before',str(self.root/'before.json'),
                   '--after',str(self.root/'after.json'),'--out',str(self.out)],
                  ['verify-layout','--bundle',str(self.out),'--expected',str(self.root/'manifest.json')]]
        for command in commands:
            proc=subprocess.run([sys.executable,'-B','-m','superhunter',*command],cwd=sl.ROOT.parent,
                                capture_output=True,text=True,timeout=25)
            self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
            self.assertFalse(json.loads(proc.stdout)['compiler_executed'])

    def test_cli_errors_do_not_echo_values(self):
        with patch('sys.stderr',new_callable=io.StringIO) as out,self.assertRaises(SystemExit):
            sl.main(['verify-layout','--bundle','PRIVATE_VALUE','--expected','expected','--unexpected','SECRET'])
        self.assertNotIn('PRIVATE_VALUE',out.getvalue());self.assertNotIn('SECRET',out.getvalue())
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(sl.main(['verify-layout','--bundle','PRIVATE_VALUE','--expected','expected']),2)
        self.assertNotIn('PRIVATE_VALUE',out.getvalue())

    def test_seeded_primitive_cases_match_independent_reference(self):
        rng=random.Random(20261104)
        for i in range(128):
            count=rng.randint(1,8)
            self.before['storage_layout']['storage']=[var(f'v{j}',slot=j) for j in range(count)]
            self.after=deepcopy(self.before)
            if i%2:
                self.after['storage_layout']['storage'].append(var('added',slot=count))
                expected='LAYOUT_PRESERVED_IN_PROFILE'
            else:
                j=rng.randrange(count)
                self.after['storage_layout']['storage'][j]['slot']=str(count+rng.randint(1,10))
                expected='LAYOUT_CHANGE_DETECTED'
            with self.subTest(i=i):self.assertEqual(self.run_compare()['status'],expected)

    def test_quality_registration_and_mandatory_negative_checks(self):
        from superhunter import quality
        self.assertIn('storage_layout',quality.COMPONENTS)
        self.assertIn('storage_layout',quality.COMPONENTS['quality']['depends'])
        self.assertIn('storage_layout',quality.COMPONENTS['entrypoints']['depends'])
        self.assertIn('test_storage_layout.StorageLayoutTests.test_resealed_approval_cannot_replace_result',quality.REQUIRED_TESTS)
        self.assertEqual(quality.validate_components(quality.source_snapshot()),[])


if __name__=='__main__':
    unittest.main()
