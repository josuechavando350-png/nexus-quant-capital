"""Synthetic offline tests. Fixtures are not market or profitability evidence."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from support import HERE, canonical, header, encode, registry, Reader, Journal
from test_registry import A, B, event, raw_header, FakeChain
from backfill import merge
from run_experiment import run, PhaseReader
from audit_experiment import audit
import lens

POLICY = json.loads((HERE / 'policy.json').read_text())


def segment(first, last, logs, timestamp=1700000000):
    return registry.append(registry.new(first), first, header(raw_header(first-1, timestamp)),
                           header(raw_header(last, timestamp)), logs,
                           [header(raw_header(n, timestamp)) for n in sorted({int(e['blockNumber'], 16) for e in logs})], POLICY)


class LensChain(FakeChain):
    def answer(self, request):
        if request['method'] == 'eth_call' and 'to' not in request['params'][0]:
            tx = request['params'][0]; code = json.loads((HERE/'lens-build.json').read_text())['creation_bytecode']
            args = tx['data'][len(code):]
            numbers = [int(args[i:i+64], 16) for i in range(0, len(args), 64)]
            assert numbers[0] == 32 and numbers[1] == len(numbers)-2
            values = self.market + [10**36, 0] + [value for _ in numbers[2:] for value in [0, 1000000, 10**12]]
            return encode('0x', 32, len(values), *values)
        return super().answer(request)


def fixture(folder, chain=None):
    fake = chain or LensChain()
    source = segment(1000000, 1000005, [event(1000000, B)], fake.timestamp)
    source_bytes = canonical({'state': source, 'sha256': registry.digest(source)})
    policy = dict(POLICY, backfill_from_block=600000, backfill_through_block=999999,
                  source_registry_file_sha256=hashlib.sha256(source_bytes).hexdigest())
    reader = PhaseReader(folder, fake); journal = Journal(folder)
    with patch('builtins.print'):
        run(reader, journal, policy, '1'*40, source_bytes)
    return policy, reader


def rewrite_journal(folder, mutate):
    path = folder/'journal.jsonl'; rows = [json.loads(x) for x in path.read_text().splitlines()]
    mutate(rows); previous = '0'*64
    for row in rows:
        row['previous_sha256'] = previous; row.pop('sha256', None)
        row['sha256'] = hashlib.sha256(canonical(row)).hexdigest(); previous = row['sha256']
    path.write_bytes(b''.join(canonical(r) for r in rows))


class MergeTests(unittest.TestCase):
    def test_merge_preserves_sources_and_all_accounts(self):
        older = segment(10, 19, [event(12, A)]); source = segment(20, 29, [event(25, B)])
        before = canonical([older, source]); merged = merge(older, source, POLICY)
        self.assertEqual(canonical([older, source]), before)
        self.assertEqual(registry.freeze(merged, 29, POLICY)['addresses'], [A, B])
        for old, new in zip(source['segments'], merged['segments'][1:]):
            self.assertEqual({k: v for k, v in old.items() if k != 'previous_segment_sha256'},
                             {k: v for k, v in new.items() if k != 'previous_segment_sha256'})

    def test_gap_and_overlap_rejected(self):
        for first in [19, 21]:
            with self.subTest(first=first), self.assertRaisesRegex(ValueError, 'GAP_OR_OVERLAP'):
                merge(segment(10, 19, []), segment(first, 29, []), POLICY)

    def test_boundary_change_rejected(self):
        with self.assertRaisesRegex(ValueError, 'BOUNDARY_HASH'):
            merge(segment(10, 19, []), segment(20, 29, [], timestamp=1700000001), POLICY)

    def test_combined_capacity_never_trims(self):
        with self.assertRaises(ValueError):
            merge(segment(10, 19, [event(12, A)]), segment(20, 29, [event(25, B)]), dict(POLICY, max_borrowers=1))

    def test_invalidated_source_rejected(self):
        source = registry.invalidate(segment(20, 29, []), {'reason': 'fixture'})
        with self.assertRaises(ValueError): merge(segment(10, 19, []), source, POLICY)


class LensTests(unittest.TestCase):
    def test_wrong_order_duplicate_zero_or_overflow_rejected(self):
        cases = [[B,A], [A,A], ['0x'+'0'*40], ['0x'+f'{i:040x}' for i in range(1,66)]]
        for addresses in cases:
            with self.subTest(addresses=addresses[:2]), self.assertRaises(ValueError): lens.initcode(addresses)

    def test_abi_offset_length_and_trailing_data_rejected(self):
        block = header(raw_header(100))
        for output in [encode('0x', 64, 8, *([0]*8)), encode('0x', 32, 7, *([0]*8)), encode('0x', 32, 8, *([0]*9))]:
            with self.assertRaises(ValueError): lens.parse(block, [], output, POLICY)

    def test_fixed_call_has_only_data_gas_and_canonical_pin(self):
        block = header(raw_header(100)); tx, pin = lens.query(block, [A])
        self.assertEqual(set(tx), {'data','gas'}); self.assertEqual(tx['gas'], hex(POLICY['creation_call_gas_limit']))
        self.assertEqual(pin, {'blockHash': block['hash'], 'requireCanonical': True})

    def test_budget_is_shared_with_standard_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            reader = Reader(Path(tmp)/'run', LensChain(), max_requests=1)
            reader.call('eth_chainId', [], 'chain')
            with self.assertRaisesRegex(ValueError, 'BUDGET'): lens.call(reader, header(raw_header(100)), [], 'creation')
            self.assertEqual(reader.count, 1)

    def test_rpc_rejection_stops_without_retry(self):
        def reject(q): return canonical({'jsonrpc':'2.0','id':q['id'],'error':{'code':-32000,'message':'fixture rejection'}})
        with tempfile.TemporaryDirectory() as tmp:
            reader = Reader(Path(tmp)/'run', reject)
            with self.assertRaises(Exception): lens.call(reader, header(raw_header(100)), [], 'creation')
            self.assertTrue(reader.stopped)
            with self.assertRaises(ValueError): reader.call('eth_chainId', [], 'retry')
            self.assertEqual(reader.count, 1)


class EvidenceTests(unittest.TestCase):
    def test_synthetic_backfill_catchup_and_three_pairs_reconstruct(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run'; policy, reader=fixture(folder); result=audit(folder, policy)
            self.assertTrue(result['backfill_merged']); self.assertEqual(result['cohort']['addresses'], [A,B])
            self.assertEqual(len(result['comparisons']),3); self.assertEqual(len(result['snapshots']),6)
            self.assertEqual(result['snapshots'][0]['state']['coverage']['debt_share_coverage_bps_floor'],6666)
            self.assertIsNone(result['realized_profit']); self.assertLessEqual(reader.count,512)

    def test_raw_reply_corruption_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run'; policy, reader=fixture(folder)
            (folder/reader.records[0]['response_file']).write_text('{}')
            with self.assertRaisesRegex(ValueError,'RAW_RESPONSE_HASH'): audit(folder,policy)

    def test_arbitrary_creation_code_rejected_even_with_valid_reply(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run'; policy, reader=fixture(folder)
            records=json.loads((folder/'requests.json').read_text())
            next(r for r in records if r.get('kind') == 'fixed_creation_view')['payload']['params'][0]['data']='0x00'
            (folder/'requests.json').write_bytes(canonical(records))
            with self.assertRaisesRegex(ValueError,'EXACT_CREATION_QUERY'): audit(folder,policy)

    def test_rehashed_state_tampering_detected_by_raw_reconstruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run'; policy,_=fixture(folder)
            def mutate(rows): next(r for r in rows if r['kind']=='creation_completed')['data']['state']['market'][0]+=1
            rewrite_journal(folder,mutate)
            with self.assertRaisesRegex(ValueError,'CREATION_DERIVATION'): audit(folder,policy)

    def test_rehashed_timing_tampering_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run'; policy,_=fixture(folder)
            def mutate(rows): next(r for r in rows if r['kind']=='paired_comparison')['data']['head_to_first_inputs_ms']=0
            rewrite_journal(folder,mutate)
            with self.assertRaisesRegex(ValueError,'PAIR_METRICS'): audit(folder,policy)

    def test_provider_rejects_creation_preserves_completed_history(self):
        class RejectCreation(LensChain):
            def __call__(self,payload):
                if type(payload) is dict and payload['method']=='eth_call' and 'to' not in payload['params'][0]:
                    return canonical({'jsonrpc':'2.0','id':payload['id'],'error':{'code':-32000,'message':'unsupported fixture'}})
                return super().__call__(payload)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run'; fake=RejectCreation()
            source=segment(1000000,1000005,[event(1000000,B)],fake.timestamp)
            source_bytes=canonical({'state':source,'sha256':registry.digest(source)})
            policy=dict(POLICY,backfill_from_block=600000,backfill_through_block=999999,source_registry_file_sha256=hashlib.sha256(source_bytes).hexdigest())
            reader=PhaseReader(folder,fake);journal=Journal(folder)
            with patch('builtins.print'),self.assertRaises(Exception): run(reader,journal,policy,'1'*40,source_bytes)
            journal.append('stopped',{'rpc_calls':reader.count,'http_requests':len(reader.records),'realized_profit':None})
            result=audit(folder,policy)
            self.assertEqual(result['status'],'stopped');self.assertTrue(result['backfill_merged']);self.assertEqual(result['rpc_errors'],1)


if __name__=='__main__': unittest.main()
