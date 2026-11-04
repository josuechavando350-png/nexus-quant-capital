"""Tests of input normalization, not proof of running a Solidity analyzer.

All Slither-shaped records below are synthetic and explicitly described as such.
No vulnerable contract, exploitation sequence, RPC or external target is used.
"""
from copy import deepcopy
import io
import json
import hashlib
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from superhunter import static_intake as si
from superhunter.safe_io import canonical, strict_json


class StaticIntakeTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.src = self.root/'sources'
        (self.src/'contracts').mkdir(parents=True)
        self.path = 'contracts/Counter.sol'
        self.raw = ('// Fixture propio; no se ejecutó Slither.\npragma solidity ^0.8.20;\n'
                    'contract Counter { uint256 public VALUE; }\n').encode()
        (self.src/self.path).write_bytes(self.raw)
        self.sources = {self.path: self.raw}
        start = self.raw.index(b'VALUE')
        self.record = {'check':'naming-convention','impact':'Informational','confidence':'High',
                       'description':'SYNTHETIC FORMAT FIXTURE: constant-style variable name.',
                       'elements':[{'type':'variable','name':'Counter.VALUE','source_mapping':{
                           'start':start,'length':5,'filename_relative':self.path,'lines':[3]}}]}
        self.report = {'success':True,'error':None,'results':{'detectors':[self.record]}}
        self.manifest = {'schema_version':1,'scope_id':'local-fixture-only',
                         'target':{'repo':'local/fixtures','commit':'1'*40},
                         'tool':{'name':'slither','version':'synthetic-format-fixture',
                                 'report_sha256':'0'*64,'detectors':['naming-convention']},
                         'sources':[{'path':self.path,'sha256':si.digest(self.raw)}]}

    def input(self):
        raw = canonical(self.report)
        self.manifest['tool']['report_sha256'] = si.digest(raw)
        return raw

    def go(self):
        return si.normalize(self.manifest, self.input(), self.sources)

    def create(self):
        raw = self.input()
        (self.root/'manifest.json').write_bytes(canonical(self.manifest))
        (self.root/'slither.json').write_bytes(raw)
        return si.create_intake(self.root/'manifest.json', self.root/'slither.json', self.src, self.root/'out')

    def reseal(self, name, change):
        root = self.root/'out'
        data = strict_json((root/name).read_bytes())
        change(data)
        raw = canonical(data); (root/name).write_bytes(raw)
        marker = strict_json((root/'COMPLETE.json').read_bytes())
        marker['sha256'][name] = si.digest(raw)
        (root/'COMPLETE.json').write_bytes(canonical(marker))

    def test_expected_source_span_and_rule(self):
        r = self.go(); g = r['observations'][0]
        self.assertEqual(r['status'],'STATIC_REVIEW_REQUIRED')
        self.assertEqual(g['check'],'naming-convention')
        self.assertEqual(g['locations'][0]['span_sha256'], si.digest(b'VALUE'))
        self.assertEqual(g['locations'][0]['lines'],[3])
        for k in ('tool_executed_here','execution_authenticated','scope_authorization_verified',
                  'target_commit_authenticated','vulnerability_confirmed','absence_of_vulnerabilities_proven'):
            self.assertIs(r[k],False)

    def test_repeated_records_preserved(self):
        self.report['results']['detectors'].append(deepcopy(self.record))
        r = self.go()
        self.assertEqual((r['diagnostics_received'],r['observation_groups']),(2,1))
        self.assertEqual([x['input_index'] for x in r['observations'][0]['records']],[0,1])
        self.assertFalse(r['grouping_is_bounty_duplicate_check'])

    def test_conflicting_labels_not_erased(self):
        other=deepcopy(self.record);other['impact']='High'
        self.report['results']['detectors'].append(other)
        r=self.go();g=r['observations'][0]
        self.assertTrue(g['conflicting_labels'])
        self.assertEqual(r['impact_counts_as_reported'],{'High':1,'Informational':1})
        self.assertNotIn('final_severity',g)

    def test_group_id_stable_across_text_changes(self):
        first=self.go()['observations'][0]['observation_id']
        self.record['description']='Different descriptive text retained in raw record'
        self.assertEqual(first,self.go()['observations'][0]['observation_id'])

    def test_new_commit_changes_identity(self):
        first=self.go()['observations'][0]['observation_id']
        self.manifest['target']['commit']='2'*40
        self.assertNotEqual(first,self.go()['observations'][0]['observation_id'])

    def test_new_source_bytes_change_identity(self):
        first=self.go()['observations'][0]['observation_id']
        raw=self.raw+b'// appended\n';self.sources[self.path]=raw
        self.manifest['sources'][0]['sha256']=si.digest(raw)
        self.assertNotEqual(first,self.go()['observations'][0]['observation_id'])

    def test_manifest_not_mutated(self):
        raw=self.input();before=deepcopy(self.manifest)
        si.normalize(self.manifest,raw,self.sources)
        self.assertEqual(before,self.manifest)

    def test_unknown_detector_not_silent(self):
        self.record['check']='unlisted-rule'
        with self.assertRaisesRegex(si.IntakeError,'UNDECLARED_DETECTOR'):self.go()

    def test_unsupported_impact_not_silent(self):
        self.record['impact']='Critical'
        with self.assertRaisesRegex(si.IntakeError,'UNSUPPORTED_IMPACT'):self.go()

    def test_boolean_not_schema_version(self):
        self.manifest['schema_version']=True
        with self.assertRaises(si.IntakeError):self.go()

    def test_boolean_not_success(self):
        self.report['success']=1
        with self.assertRaises(si.IntakeError):self.go()

    def test_boolean_not_offset(self):
        self.record['elements'][0]['source_mapping']['start']=True
        with self.assertRaisesRegex(si.IntakeError,'SOURCE_RANGE_TYPE'):self.go()

    def test_unbound_source_rejected(self):
        self.record['elements'][0]['source_mapping']['filename_relative']='contracts/Other.sol'
        with self.assertRaisesRegex(si.IntakeError,'UNDECLARED_SOURCE'):self.go()

    def test_unsafe_paths_rejected(self):
        for path in ('../outside.sol','/tmp/a.sol','a//b.sol','a/./b.sol','a\\b.sol','https://x/a.sol'):
            with self.subTest(path=path), self.assertRaises(si.IntakeError):si.source_path(path)

    def test_hash_mismatch_rejected(self):
        raw=self.input();self.manifest['tool']['report_sha256']='3'*64
        with self.assertRaisesRegex(si.IntakeError,'REPORT_HASH_MISMATCH'):
            si.normalize(self.manifest,raw,self.sources)

    def test_source_hash_mismatch_rejected(self):
        self.sources[self.path]+=b'// changed'
        with self.assertRaisesRegex(si.IntakeError,'SOURCE_HASH_MISMATCH'):self.go()

    def test_source_line_mismatch_rejected(self):
        self.record['elements'][0]['source_mapping']['lines']=[2]
        with self.assertRaisesRegex(si.IntakeError,'SOURCE_LINES_MISMATCH'):self.go()

    def test_utf8_char_offset_cannot_replace_byte_offset(self):
        self.record['elements'][0]['source_mapping']['start']=self.raw.decode().index('VALUE')
        # This is another legitimate in-bounds span; we cannot infer intended text.
        # It gets a DIFFERENT span hash rather than falsely binding it to VALUE.
        r=self.go()
        self.assertNotEqual(r['observations'][0]['locations'][0]['span_sha256'],si.digest(b'VALUE'))

    def test_split_utf8_character_rejected(self):
        m=self.record['elements'][0]['source_mapping'];m['start']=self.raw.index('ó'.encode())+1;m['length']=1;m['lines']=[1]
        with self.assertRaisesRegex(si.IntakeError,'UTF8_BOUNDARY'):self.go()

    def test_exclusive_end_line_matches_slither_convention(self):
        m=self.record['elements'][0]['source_mapping'];m['start']=0;m['length']=self.raw.index(b'\n')+1;m['lines']=[1,2]
        self.assertEqual(self.go()['observations'][0]['locations'][0]['lines'],[1,2])

    def test_out_of_bounds_rejected(self):
        self.record['elements'][0]['source_mapping']['length']=len(self.raw)
        with self.assertRaisesRegex(si.IntakeError,'SOURCE_RANGE_BOUNDS'):self.go()

    def test_zero_length_unsupported_explicitly(self):
        self.record['elements'][0]['source_mapping']['length']=0
        with self.assertRaisesRegex(si.IntakeError,'SOURCE_RANGE_TYPE'):self.go()

    def test_missing_location_not_silently_discarded(self):
        self.record['elements'][0].pop('source_mapping')
        with self.assertRaisesRegex(si.IntakeError,'MISSING_SOURCE_MAPPING'):self.go()

    def test_missing_detector_key_is_unknown_not_clean(self):
        self.report['results']={}
        r=self.go();self.assertEqual(r['status'],'STATIC_COVERAGE_UNKNOWN')
        self.assertFalse(r['absence_of_vulnerabilities_proven'])

    def test_empty_list_not_security_certificate(self):
        self.report['results']['detectors']=[]
        r=self.go();self.assertEqual(r['status'],'STATIC_NO_DIAGNOSTICS')
        self.assertFalse(r['absence_of_vulnerabilities_proven'])

    def test_tool_error_not_clean(self):
        self.report={'success':False,'error':'compiler failed secret=PRIVATE_MARKER','results':{}}
        self.assertEqual(self.go()['status'],'STATIC_TOOL_ERROR')

    def test_contradictory_error_rejected(self):
        self.report['error']='error with success true'
        with self.assertRaises(si.IntakeError):self.go()

    def test_failure_cannot_contain_findings(self):
        self.report['success']=False;self.report['error']='failed'
        with self.assertRaisesRegex(si.IntakeError,'FAILED_RUN_WITH_RESULTS'):self.go()

    def test_duplicates_in_manifest_rejected(self):
        self.manifest['sources']*=2
        with self.assertRaisesRegex(si.IntakeError,'DUPLICATE_SOURCE'):self.go()

    def test_duplicate_detector_inventory_rejected(self):
        self.manifest['tool']['detectors']*=2
        with self.assertRaises(si.IntakeError):self.go()

    def test_elements_limit(self):
        self.record['elements']*=si.MAX_ELEMENTS+1
        with self.assertRaises(si.IntakeError):self.go()

    def test_reports_limit(self):
        self.report['results']['detectors']=[self.record]*(si.MAX_DIAGNOSTICS+1)
        with self.assertRaises(si.IntakeError):self.go()

    def test_no_network_no_process_execution(self):
        with patch('socket.socket',side_effect=AssertionError),patch('subprocess.run',side_effect=AssertionError):
            self.create();si.verify_intake(self.root/'out')

    def test_complete_self_contained_roundtrip(self):
        first=self.create()
        import shutil
        shutil.rmtree(self.src)
        self.assertEqual(si.verify_intake(self.root/'out'),first)

    def test_original_bytes_preserved(self):
        raw=self.input();self.create()
        self.assertEqual((self.root/'out/slither.json').read_bytes(),raw)
        self.assertEqual((self.root/'out/source-000.sol').read_bytes(),self.raw)
        self.assertEqual((self.src/self.path).read_bytes(),self.raw)

    def test_private_permissions(self):
        self.create();out=self.root/'out'
        self.assertEqual(out.stat().st_mode & 0o777,0o700)
        for p in out.iterdir():self.assertEqual(p.stat().st_mode & 0o777,0o600)

    def test_existing_output_not_overwritten(self):
        self.create();before=(self.root/'out/COMPLETE.json').read_bytes()
        with self.assertRaises(si.IntakeError):self.create()
        self.assertEqual(before,(self.root/'out/COMPLETE.json').read_bytes())

    def test_undeclared_bundle_file_rejected(self):
        self.create();(self.root/'out/extra.txt').write_text('untracked')
        with self.assertRaises(si.IntakeError):si.verify_intake(self.root/'out')

    def test_tampered_output_rejected(self):
        self.create();(self.root/'out/observations.json').write_bytes(b'{}')
        with self.assertRaisesRegex(si.IntakeError,'HASH_MISMATCH'):si.verify_intake(self.root/'out')

    def test_resealed_confirmed_claim_rejected(self):
        self.create();self.reseal('observations.json',lambda x:x.update(vulnerability_confirmed=True))
        with self.assertRaisesRegex(si.IntakeError,'DIFFER_FROM_INPUT'):si.verify_intake(self.root/'out')

    def test_resealed_source_rejected(self):
        self.create();p=self.root/'out/source-000.sol';p.write_bytes(b'changed')
        marker=strict_json((p.parent/'COMPLETE.json').read_bytes());marker['sha256'][p.name]=si.digest(p.read_bytes())
        (p.parent/'COMPLETE.json').write_bytes(canonical(marker))
        with self.assertRaisesRegex(si.IntakeError,'SOURCE_HASH_MISMATCH'):si.verify_intake(p.parent)

    def test_symlink_source_rejected(self):
        p=self.src/self.path;p.unlink();p.symlink_to(self.root/'external.sol');(self.root/'external.sol').write_bytes(self.raw)
        with self.assertRaises((ValueError,OSError)):self.create()

    def test_manifest_file_does_not_allow_duplicate_keys(self):
        self.create();(self.root/'manifest.json').write_bytes(b'{"schema_version":1,"schema_version":2}')
        with self.assertRaises(ValueError):
            si.create_intake(self.root/'manifest.json',self.root/'slither.json',self.src,self.root/'second')

    def test_review_does_not_echo_description_or_error(self):
        self.record['description']='password=PRIVATE_MARKER'
        r=self.go();self.assertNotIn(b'PRIVATE_MARKER',si.render_review(r))
        self.assertIn('PRIVATE_MARKER',r['observations'][0]['records'][0]['description'])

    def test_cli_roundtrip(self):
        self.input();(self.root/'manifest.json').write_bytes(canonical(self.manifest));(self.root/'slither.json').write_bytes(self.input())
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(si.main(['import-static','--manifest',str(self.root/'manifest.json'),
                '--report',str(self.root/'slither.json'),'--sources',str(self.src),'--out',str(self.root/'out')]),0)
        self.assertFalse(json.loads(output.getvalue())['vulnerability_confirmed'])
        with redirect_stdout(io.StringIO()):self.assertEqual(si.main(['verify-static','--bundle',str(self.root/'out')]),0)

    def test_cli_missing_file_no_path_echo(self):
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(si.main(['verify-static','--bundle',str(self.root/'PRIVATE_MARKER')]),2)
        self.assertNotIn('PRIVATE_MARKER',output.getvalue())

    def test_cli_invalid_argument_no_value_echo(self):
        with patch('sys.stderr',new_callable=io.StringIO) as stream,self.assertRaises(SystemExit):
            si.main(['verify-static','--bundle',str(self.root/'out'),'--unexpected','PRIVATE_MARKER'])
        self.assertNotIn('PRIVATE_MARKER',stream.getvalue())


if __name__=='__main__':unittest.main()
