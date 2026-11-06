"""Boundary and linkage tests. Recorded native bytes are used as fixture data.

The captured output came from pinned solc 0.8.30 in this delivery. Some tests
replace the replay call to isolate orchestration; they are NOT native-compiler
acceptance evidence. The separate acceptance script re-runs the real binary.
"""
from copy import deepcopy
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import native_compile as nc, native_layout as nl
from superhunter.safe_io import canonical, strict_json, write_new_bundle

RECORDED_INPUT = b'{"language":"Solidity","settings":{"evmVersion":"cancun","modelChecker":{"engine":"none"},"optimizer":{"enabled":false},"outputSelection":{"*":{"":["ast"],"*":["storageLayout"]}}},"sources":{"Counter.sol":{"content":"// SPDX-License-Identifier: MIT\\npragma solidity 0.8.30;\\ncontract Counter { uint128 public balance; uint128 public total; }\\n"}}}\n'
RECORDED_OUTPUT = b'{"contracts":{"Counter.sol":{"Counter":{"storageLayout":{"storage":[{"astId":3,"contract":"Counter.sol:Counter","label":"balance","offset":0,"slot":"0","type":"t_uint128"},{"astId":5,"contract":"Counter.sol:Counter","label":"total","offset":16,"slot":"0","type":"t_uint128"}],"types":{"t_uint128":{"encoding":"inplace","label":"uint128","numberOfBytes":"16"}}}}}},"sources":{"Counter.sol":{"ast":{"absolutePath":"Counter.sol","exportedSymbols":{"Counter":[6]},"id":7,"license":"MIT","nodeType":"SourceUnit","nodes":[{"id":1,"literals":["solidity","0.8",".30"],"nodeType":"PragmaDirective","src":"32:23:0"},{"abstract":false,"baseContracts":[],"canonicalName":"Counter","contractDependencies":[],"contractKind":"contract","fullyImplemented":true,"id":6,"linearizedBaseContracts":[6],"name":"Counter","nameLocation":"65:7:0","nodeType":"ContractDefinition","nodes":[{"constant":false,"functionSelector":"b69ef8a8","id":3,"mutability":"mutable","name":"balance","nameLocation":"90:7:0","nodeType":"VariableDeclaration","scope":6,"src":"75:22:0","stateVariable":true,"storageLocation":"default","typeDescriptions":{"typeIdentifier":"t_uint128","typeString":"uint128"},"typeName":{"id":2,"name":"uint128","nodeType":"ElementaryTypeName","src":"75:7:0","typeDescriptions":{"typeIdentifier":"t_uint128","typeString":"uint128"}},"visibility":"public"},{"constant":false,"functionSelector":"2ddbd13a","id":5,"mutability":"mutable","name":"total","nameLocation":"114:5:0","nodeType":"VariableDeclaration","scope":6,"src":"99:20:0","stateVariable":true,"storageLocation":"default","typeDescriptions":{"typeIdentifier":"t_uint128","typeString":"uint128"},"typeName":{"id":4,"name":"uint128","nodeType":"ElementaryTypeName","src":"99:7:0","typeDescriptions":{"typeIdentifier":"t_uint128","typeString":"uint128"}},"visibility":"public"}],"scope":7,"src":"56:66:0","usedErrors":[],"usedEvents":[]}],"src":"32:91:0"},"id":0}}}\n'
RECORDED_VERSION = b'solc, the solidity compiler commandline interface\nVersion: 0.8.30+commit.73712a01.Linux.g++\n'

class NativeLayoutTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.out = self.root/'out'; self.binary = self.root/'absent-solc'
        self.reference = {'schema_version':1,'repo':'local/benign-lab','source':'Counter.sol','contract':'Counter',
                          **{s:{'commit':('a' if s=='before' else 'b')*40,
                                'input_sha256':nc.sha(RECORDED_INPUT)} for s in nl.SIDES}}
        self.refpath = self.root/'reference.json'; self.refpath.write_bytes(canonical(self.reference))
        self.input = self.root/'input.json'; self.input.write_bytes(RECORDED_INPUT)
        receipt = nc._receipt(RECORDED_INPUT, RECORDED_OUTPUT, RECORDED_VERSION, b'',
                              produced_at='1970-01-01T00:00:00+00:00')
        # New metadata over recorded native output is a UNIT FIXTURE, not a new compile.
        files = {'input.json':RECORDED_INPUT,'output.json':RECORDED_OUTPUT,'version.txt':RECORDED_VERSION,
                 'stderr.txt':b'','receipt.json':canonical(receipt),'audit.json':canonical(nc._audit(receipt)),
                 'REVIEW.md':nc._review(receipt)}
        self.compiled = self.root/'recorded-unit-fixture'; write_new_bundle(self.compiled, files)
        capture = nl._capture(self.compiled,nc.sha(RECORDED_INPUT))
        self.packed = {s+'--'+n:raw for s in nl.SIDES for n,raw in capture.items()}

    def replay_stub(self, root, binary, *, expected_input_sha256):
        nc._read_bundle(root, expected_input_sha256=expected_input_sha256)
        return {'status':'COMPILATION_REPLAY_MATCH','compilation_status':'SOLC_COMPILATION_COMPLETED',
                'same_compiler_reexecuted':True,'independent_compiler':False,
                'vulnerability_confirmed':False,'input_sha256':expected_input_sha256,
                'compiler_sha256':nc.PIN['sha256']}

    def unit_documents(self):
        with patch.object(nc,'replay_bundle',side_effect=self.replay_stub):
            return nl._documents(canonical(self.reference),self.packed,self.binary)

    def test_reference_exact_fields_and_no_version_override(self):
        for key,value in (('compiler_version','latest'),('profile',1),('output_sha256','0'*64)):
            with self.subTest(key=key), self.assertRaises(nl.NativeLayoutError):
                nl.validate_expected({**self.reference,key:value})

    def test_reference_version_not_boolean_or_weaker_profile(self):
        for value in (True,False,0,2,4,'1'):
            with self.subTest(value=value), self.assertRaises(nl.NativeLayoutError):
                nl.validate_expected({**self.reference,'schema_version':value})

    def test_external_input_hash_required(self):
        r=deepcopy(self.reference);r['before']['input_sha256']='invalid'
        with self.assertRaises(ValueError):nl.validate_expected(r)

    def test_reference_source_path_restricted(self):
        for name in ('/tmp/Counter.sol','../Counter.sol','Counter.txt'):
            with self.subTest(name=name),self.assertRaises(ValueError):
                nl.validate_expected({**self.reference,'source':name})

    def test_reference_not_mutated(self):
        old=deepcopy(self.reference);copy=nl.validate_expected(self.reference)
        copy['before']['commit']='c'*40
        self.assertEqual(self.reference,old)

    def test_missing_binary_blocks_without_output(self):
        with self.assertRaises(nc.CompilerUnavailable):
            nl.create(self.refpath,self.input,self.input,self.binary,self.out)
        self.assertFalse(self.out.exists())

    def test_wrong_input_rejected_before_any_compiler_call(self):
        self.input.write_bytes(RECORDED_INPUT+b' ')
        with patch.object(nc,'read_pinned_binary',side_effect=AssertionError),self.assertRaisesRegex(ValueError,'EXTERNAL_INPUT_MISMATCH'):
            nl.create(self.refpath,self.input,self.input,self.binary,self.out)

    def test_existing_output_not_overwritten(self):
        self.out.mkdir();(self.out/'keep').write_bytes(b'x')
        with self.assertRaisesRegex(nl.NativeLayoutError,'NEW_OUTPUT_REQUIRED'):
            nl.create(self.refpath,self.input,self.input,self.binary,self.out)
        self.assertEqual((self.out/'keep').read_bytes(),b'x')

    def test_external_reference_must_not_be_inside_bundle(self):
        with self.assertRaisesRegex(nl.NativeLayoutError,'EXTERNAL_REFERENCE_REQUIRED'):
            nl._reference(self.out/'expected.json',self.out)

    def test_both_native_replays_are_required(self):
        with patch.object(nc,'replay_bundle',side_effect=self.replay_stub) as replay, \
             patch.object(nl.binding,'_documents',wraps=nl.binding._documents) as bound:
            docs=nl._documents(canonical(self.reference),self.packed,self.binary)
        self.assertEqual(replay.call_count,2);self.assertEqual(bound.call_count,1)
        result=strict_json(docs['result.json'])
        self.assertEqual(result['status'],'NATIVE_LAYOUT_PRESERVED_IN_PROFILE')
        for field in ('independent_compiler','upgrade_authorized','vulnerability_confirmed',
                      'executed_contracts','repository_commits_authenticated','remote_producer_authenticated'):
            self.assertIs(result[field],False)
        self.assertEqual(set(docs),nl.OUTPUT_FILES)

    def test_replay_disagreement_prevents_review(self):
        with patch.object(nc,'replay_bundle',side_effect=nc.CompileError('COMPILER_REPLAY_MISMATCH')), \
             patch.object(nl.binding,'_documents',side_effect=AssertionError),self.assertRaises(nc.CompileError):
            nl._documents(canonical(self.reference),self.packed,self.binary)

    def test_replay_cannot_claim_other_binary_or_skipped_execution(self):
        for key,value in (('same_compiler_reexecuted',False),('independent_compiler',True),
                          ('compiler_sha256','0'*64),('input_sha256','0'*64),
                          ('compilation_status','SOLC_COMPILATION_FAILED')):
            with self.subTest(key=key):
                def invalid(root,binary,*,expected_input_sha256):
                    r=self.replay_stub(root,binary,expected_input_sha256=expected_input_sha256)
                    r[key]=value;return r
                with patch.object(nc,'replay_bundle',side_effect=invalid), self.assertRaisesRegex(ValueError,'SUCCESSFUL_REPLAY_REQUIRED'):
                    nl._documents(canonical(self.reference),self.packed,self.binary)

    def test_missing_compilation_artifact_blocks(self):
        self.packed.pop('before--output.json')
        with self.assertRaisesRegex(ValueError,'COMPILATION_FILE_SET'):
            nl._documents(canonical(self.reference),self.packed,self.binary)

    def test_unknown_compilation_artifact_blocks(self):
        self.packed['secret.txt']=b'x'
        with self.assertRaisesRegex(ValueError,'COMPILATION_FILE_SET'):
            nl._documents(canonical(self.reference),self.packed,self.binary)

    def test_original_compilation_bytes_preserved(self):
        docs=self.unit_documents()
        for name,raw in self.packed.items():self.assertEqual(docs[name],raw)

    def test_verifier_cannot_accept_bundle_without_compiler(self):
        write_new_bundle(self.out,self.unit_documents())
        with self.assertRaises(nc.CompilerUnavailable):nl.verify(self.out,self.refpath,self.binary)

    def test_verification_replays_again_and_checks_expected_reference(self):
        docs=self.unit_documents();write_new_bundle(self.out,docs)
        with patch.object(nc,'replay_bundle',side_effect=self.replay_stub) as replay:
            nl.verify(self.out,self.refpath,self.binary)
        self.assertEqual(replay.call_count,2)
        changed=deepcopy(self.reference);changed['after']['commit']='d'*40
        self.refpath.write_bytes(canonical(changed))
        with self.assertRaisesRegex(ValueError,'EXTERNAL_REFERENCE_MISMATCH'):
            nl.verify(self.out,self.refpath,self.binary)

    def test_resealed_confirmation_claim_cannot_override_recomputed_result(self):
        docs=self.unit_documents();r=strict_json(docs['result.json']);r['vulnerability_confirmed']=True
        docs['result.json']=canonical(r);write_new_bundle(self.out,docs)
        with patch.object(nc,'replay_bundle',side_effect=self.replay_stub),self.assertRaisesRegex(ValueError,'NATIVE_REVIEW_MISMATCH'):
            nl.verify(self.out,self.refpath,self.binary)

    def test_private_permissions_and_exact_inventory(self):
        write_new_bundle(self.out,self.unit_documents())
        self.assertEqual(self.out.stat().st_mode&0o777,0o700)
        for p in self.out.iterdir():self.assertEqual(p.stat().st_mode&0o777,0o600)
        (self.out/'unexpected').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError,'BUNDLE_INVENTORY'):nl.verify(self.out,self.refpath,self.binary)

    def test_error_diagnostics_do_not_echo_path(self):
        with redirect_stdout(io.StringIO()) as stream:
            code=nl.main(['verify-native-layout','--bundle',str(self.root/'PRIVATE_VALUE'),
                         '--expected',str(self.refpath),'--binary',str(self.binary)])
        self.assertEqual(code,2);self.assertNotIn('PRIVATE_VALUE',stream.getvalue())

    def test_package_entrypoint_routes_blocked_binary(self):
        from superhunter import __main__
        args=['superhunter','review-native-layout','--expected',str(self.refpath),
              '--before-input',str(self.input),'--after-input',str(self.input),
              '--binary',str(self.binary),'--out',str(self.out)]
        with patch('sys.argv',args),redirect_stdout(io.StringIO()) as out:self.assertEqual(__main__.main(),3)
        self.assertIn('NATIVE_LAYOUT_BLOCKED',out.getvalue())

    def test_diagnostics_invalid_options_are_private(self):
        with patch('sys.stderr',new_callable=io.StringIO) as stream,self.assertRaises(SystemExit):
            nl.main(['verify-native-layout','--bundle','missing','--expected','missing',
                     '--binary','missing','--unexpected','PRIVATE_VALUE'])
        self.assertNotIn('PRIVATE_VALUE',stream.getvalue())

    def test_engine_drift_aborts_document_creation(self):
        old=nl._engine()
        with patch.object(nc,'replay_bundle',side_effect=self.replay_stub), \
             patch.object(nl,'_engine',side_effect=[old,{'changed':True}]),self.assertRaisesRegex(ValueError,'ENGINE_CHANGED'):
            nl._documents(canonical(self.reference),self.packed,self.binary)

    def test_compile_failure_cannot_produce_review(self):
        with patch.object(nc,'read_pinned_binary',return_value=b'UNIT_TEST_ONLY'), \
             patch.object(nc,'compile_bundle',return_value={'status':'SOLC_COMPILATION_FAILED'}), \
             self.assertRaisesRegex(ValueError,'COMPILATION_UNSUCCESSFUL'):
            nl.create(self.refpath,self.input,self.input,self.binary,self.out)
        self.assertFalse(self.out.exists())

    def test_summary_contains_no_source_or_external_identifier(self):
        docs=self.unit_documents()
        self.assertNotIn(b'Counter.sol',docs['REVIEW.md'])
        self.assertNotIn(b'local/benign-lab',docs['REVIEW.md'])
        self.assertIn(b'no dos compiladores independientes',docs['REVIEW.md'])


if __name__ == '__main__':
    unittest.main()
