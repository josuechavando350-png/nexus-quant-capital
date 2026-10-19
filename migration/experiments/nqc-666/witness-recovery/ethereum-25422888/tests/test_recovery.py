import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recover import recover, Rejected, MAX_CAPSULE, NQC
from state_evidence import ProofDecoder as ReferenceDecoder, Policy, Anchor, HEADER_FIELDS
from state_evidence_fast import verify as full_R5_verify
from eth_hash.auto import keccak
import rlp


class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = (ROOT / 'reference/morphoBorrower.capsule.json').read_bytes()
        cls.runtime = (ROOT / 'reference/Morpho.ethereum.hex').read_bytes()
        cls.case_raw = (ROOT / 'CASE.json').read_bytes()
        cls.capsule = json.loads(cls.raw)
        cls.case = json.loads(cls.case_raw)

    def check(self, capsule=None, case=None, runtime=None):
        return recover(self.raw if capsule is None else json.dumps(capsule).encode(),
                       self.runtime if runtime is None else runtime,
                       self.case_raw if case is None else json.dumps(case).encode())

    def test_published_proof_and_independent_R3_traversal(self):
        result, account = self.check()
        reference = ReferenceDecoder(shared=False)
        root = bytes.fromhex(result['state_root_claim'][2:])
        address = bytes.fromhex(account['address'][2:])
        leaf = reference.prove(root, keccak(address), account['accountProof'])
        nonce, balance, storage, codehash = rlp.decode(leaf, strict=True)
        self.assertEqual(int.from_bytes(nonce, 'big'), 1)
        self.assertEqual(balance, b'')
        self.assertEqual(codehash.hex(), self.case['code_hash'][2:])
        row = account['storageProof'][0]
        encoded = reference.prove(storage, keccak(bytes.fromhex(row['key'][2:])), row['proof'])
        self.assertEqual(int.from_bytes(rlp.decode(encoded, strict=True), 'big'), int(row['value'], 16))
        self.assertEqual(result['runtime_bytes'], 15623)
        self.assertEqual(len(account['accountProof']), 8)
        self.assertEqual(len(row['proof']), 6)

    def test_partial_result_never_claims_full_authentication(self):
        result, _ = self.check()
        self.assertEqual(result['storage_slots_verified'], 1)
        self.assertEqual(len(result['missing_slots']), 8)
        self.assertEqual(result['canonicality'], 'UNKNOWN')
        for key in ('header_verified', 'layout_attested', 'full_R5_packet_ready',
                    'authentic_witness_integrated', 'whole_bot_stabilized', 'commercial_admission'):
            self.assertIs(result[key], False, key)
        for key in ('block_hash', 'oracle_price', 'observed_eligibility'):
            self.assertIsNone(result[key], key)

    def test_full_R5_rejects_partial_storage_even_under_a_test_root(self):
        # TEST ONLY: an explicitly synthetic header lets this adversarial case
        # reach R5's coverage guard. It is never emitted as historical evidence.
        _, account = self.check()
        packet = json.loads((NQC / 'r3-state-evidence/fixtures/synthetic-00.json').read_bytes())
        header = packet['header']
        header['stateRoot'] = self.case['state_root_claim']
        fields = [int(header[name], 16) if width is None else bytes.fromhex(header[name][2:])
                  for name, width in HEADER_FIELDS]
        digest = keccak(rlp.encode(fields))
        header['hash'] = packet['blockHash'] = '0x' + digest.hex()
        packet['account'] = account
        packet['code'] = self.runtime.decode().replace('\n', '')
        anchor = Anchor(1, int(header['number'], 16), digest,
                        int(header['timestamp'], 16), 'synthetic_fixture')
        policy = Policy(anchor, bytes.fromhex(self.case['address'][2:]),
                        bytes.fromhex(self.case['code_hash'][2:]),
                        bytes.fromhex(self.case['market_id'][2:]),
                        bytes.fromhex(self.case['borrower'][2:]))
        with self.assertRaisesRegex(Rejected, '^storage proof coverage$'):
            full_R5_verify(json.dumps(packet).encode(), policy, anchor.timestamp)

    def test_block_number_is_only_a_claim_without_a_header(self):
        capsule, case = copy.deepcopy(self.capsule), copy.deepcopy(self.case)
        capsule['block_number'] = str(int(capsule['block_number']) + 1)
        case['block_number_claim'] += 1
        result, _ = self.check(capsule, case)
        self.assertIs(result['header_verified'], False)
        self.assertEqual(result['canonicality'], 'UNKNOWN')
        self.assertIs(result['commercial_admission'], False)

    def test_every_active_branch_rejects_a_changed_child(self):
        for kind in ('account', 'storage'):
            for index in range(int(self.capsule[kind + '_node_length'])):
                with self.subTest(kind=kind, index=index):
                    capsule = copy.deepcopy(self.capsule)
                    node = capsule[kind + '_nodes'][index]
                    row = node['row_exist'].index(True)
                    node['rows'][row][0] = str(int(node['rows'][row][0]) ^ 1)
                    with self.assertRaises(Rejected): self.check(capsule)

    def test_wrong_account_value_or_root_rejected(self):
        for field in ('nonce', 'storage_hash', 'code_hash', 'address'):
            with self.subTest(field=field):
                capsule = copy.deepcopy(self.capsule)
                capsule['account'][field][0] = str(int(capsule['account'][field][0]) ^ 1)
                with self.assertRaises(Rejected): self.check(capsule)
        capsule = copy.deepcopy(self.capsule)
        capsule['root'][0] = str(int(capsule['root'][0]) ^ 1)
        with self.assertRaises(Rejected): self.check(capsule)

    def test_wrong_position_or_runtime_rejected(self):
        capsule = copy.deepcopy(self.capsule)
        capsule['slot']['value'][0] = str(int(capsule['slot']['value'][0]) ^ 1)
        with self.assertRaises(Rejected): self.check(capsule)
        runtime = bytearray(self.runtime)
        runtime[10] = ord('0') if runtime[10] != ord('0') else ord('1')
        with self.assertRaises(Rejected): self.check(runtime=bytes(runtime))

    def test_runtime_LF_wrapping_preserves_bytes_but_spaces_are_rejected(self):
        result, _ = self.check(runtime=self.runtime.replace(b'\n', b''))
        self.assertEqual(result['runtime_sha256'],
                         'fd5aa16eea01735e0e33e51e913a27f7d5ed998adc0cec2bf1f9ea368d9e1bdf')
        with self.assertRaises(Rejected): self.check(runtime=self.runtime + b' ')

    def test_other_market_borrower_or_chain_rejected(self):
        for field, value in [('market_id', '0x' + '11' * 32),
                             ('borrower', '0x' + '11' * 20), ('chain_id_claim', 4663),
                             ('chain_id_claim', True), ('block_number_claim', True),
                             ('authority', 'AUTHENTICATED')]:
            with self.subTest(field=field, value=value):
                case = {**self.case, field: value}
                with self.assertRaises(Rejected): self.check(case=case)

    def test_padding_and_absent_rows_cannot_hide_data(self):
        for kind in ('account', 'storage'):
            capsule = copy.deepcopy(self.capsule)
            capsule[kind + '_nodes'][-1]['rows'][0][0] = '1'
            with self.assertRaises(Rejected): self.check(capsule)
        capsule = copy.deepcopy(self.capsule)
        last = capsule['storage_nodes'][4]
        row = last['row_exist'].index(False)
        last['rows'][row][0] = '1'
        with self.assertRaises(Rejected): self.check(capsule)

    def test_numeric_and_presence_encodings_are_strict(self):
        for value in (True, 1, '-1', '01', ' 1', str(2**64)):
            with self.subTest(value=value):
                capsule = copy.deepcopy(self.capsule)
                capsule['account_nodes'][0]['rows'][0][0] = value
                with self.assertRaises(Rejected): self.check(capsule)
        capsule = copy.deepcopy(self.capsule)
        capsule['account_nodes'][0]['row_exist'][0] = 1
        with self.assertRaises(Rejected): self.check(capsule)

    def test_nonminimal_integer_and_truncated_path_rejected(self):
        for field, value in [('nonce_length', '2'), ('nonce_length', '9')]:
            capsule = copy.deepcopy(self.capsule)
            capsule['account'][field] = value
            with self.assertRaises(Rejected): self.check(capsule)
        for value in ('6', '16'):
            capsule = copy.deepcopy(self.capsule)
            capsule['account_node_length'] = value
            with self.assertRaises(Rejected): self.check(capsule)

    def test_unsupported_extension_and_extra_authority_rejected(self):
        capsule = copy.deepcopy(self.capsule)
        capsule['account_nodes'][0]['node_type'] = '1'
        with self.assertRaises(Rejected): self.check(capsule)
        capsule = copy.deepcopy(self.capsule)
        capsule['authenticated'] = True
        with self.assertRaises(Rejected): self.check(capsule)

    def test_duplicate_keys_and_oversize_inputs_rejected(self):
        for raw in (b'{"root":[],"root":[]}', self.raw + b' ' * MAX_CAPSULE):
            with self.assertRaises(Rejected): recover(raw, self.runtime, self.case_raw)
        with self.assertRaises(Rejected): self.check(runtime=b'0x' + b'00' * 24577)

    def test_cli_emits_no_partial_facts_on_failure_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            bad = directory / 'bad.json'; bad.write_text('{"authenticated":true}')
            out = directory / 'result'
            cmd = [sys.executable, '-B', str(ROOT / 'recover.py'), '--capsule', str(bad),
                   '--runtime', str(ROOT / 'reference/Morpho.ethereum.hex'),
                   '--case', str(ROOT / 'CASE.json'), '--out', str(out)]
            process = subprocess.run(cmd, capture_output=True)
            self.assertEqual(process.returncode, 2)
            self.assertEqual({p.name for p in out.iterdir()}, {'result.json'})
            original = (out / 'result.json').read_bytes()
            self.assertEqual(json.loads(original)['status'], 'REJECTED')
            process = subprocess.run(cmd, capture_output=True)
            self.assertNotEqual(process.returncode, 0)
            self.assertEqual((out / 'result.json').read_bytes(), original)


if __name__ == '__main__': unittest.main()
