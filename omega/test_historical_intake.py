"""Real retained artifacts plus hostile mutations; no simulated market evidence."""
import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from unittest.mock import patch

from historical_intake import (AUTHORITIES, EVIDENCE, GAS_TOTAL, MAX_ARCHIVE,
    MAX_MEMBER, PINS, ROOT, SOURCE_BLOBS, UNKNOWN_FIELDS, build_ledger,
    load_sources, original_validator, unpack, verify_ledger, verify_metadata)
from integrity import canonical, digest


class IntakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = build_ledger()
        cls.pin = json.loads((EVIDENCE / 'historical-intake-pin.json').read_bytes())

    def test_real_artifacts_conserve_all_events_receipts_and_gas(self):
        value = verify_ledger(self.ledger)
        self.assertEqual(len(value['records']), 127)
        self.assertEqual(sum(len(r['events']) for r in value['records']), 139)
        self.assertEqual(sum(int(r['receipt']['total_gas_paid_wei']) for r in value['records']), GAS_TOTAL)
        self.assertEqual(value['summary']['gas_paid_wei'], str(GAS_TOTAL))

    def test_multievent_transactions_never_double_charge_gas(self):
        rows = self.ledger['records']
        self.assertTrue(any(len(r['events']) > 1 for r in rows))
        wrong = sum(int(r['receipt']['total_gas_paid_wei']) * len(r['events']) for r in rows)
        self.assertGreater(wrong, GAS_TOTAL)
        self.assertNotEqual(str(wrong), self.ledger['summary']['gas_paid_wei'])

    def test_real_139_legs_bind_to_exact_events_and_keep_token_units(self):
        self.assertEqual(self.ledger['summary']['decoded_liquidation_leg_count'],139)
        self.assertEqual(self.ledger['summary']['distinct_asset_pair_count'],53)
        for row in self.ledger['records']:
            self.assertEqual(len(row['liquidation_legs']),len(row['events']))
            events={e['log_index']:e for e in row['events']}
            for leg in row['liquidation_legs']:
                self.assertEqual(leg['original_event_commitment_sha256'],
                                 events[leg['log_index']]['event_commitment_sha256'])
            equal=[l for l in row['liquidation_legs'] if l['debt_asset']==l['collateral_asset']]
            self.assertEqual(len(row['same_asset_gross_deltas']),len(equal))
            for delta,leg in zip(row['same_asset_gross_deltas'],equal):
                self.assertEqual(delta['collateral_minus_debt_raw'],
                    str(int(leg['collateral_liquidated_raw'])-int(leg['debt_to_cover_raw'])))
                self.assertEqual(delta['unit'],'TOKEN_BASE_UNITS_NOT_USD_NOT_NET_PROFIT')

    def test_resealed_token_amount_and_fingerprint_substitution_rejected(self):
        for key,val in [('debt_to_cover_raw','1'),('borrower_identity_sha256','0'*64),
                        ('liquidator_identity_sha256','0'*64)]:
            self.reject_resealed(lambda d: d['records'][0]['liquidation_legs'][0].__setitem__(key,val))

    def test_unknown_fields_stay_null_in_every_record(self):
        for row in self.ledger['records']:
            for key in UNKNOWN_FIELDS:
                self.assertIsNone(row[key])
            self.assertIs(row['observed_costs_complete'], False)
            self.assertIs(row['nqc_execution'], False)

    def test_failed_parent_is_preserved_not_promoted_by_complete_drpc_stage(self):
        self.assertEqual(self.ledger['source_provenance']['receipts']['workflow_conclusion'], 'failure')
        self.assertTrue(all(r['receipt_operator'] == 'dRPC' and
                            r['receipt_parity_complete'] is False for r in self.ledger['records']))

    def test_deterministic_replay_uses_no_network(self):
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            self.assertEqual(canonical(build_ledger()), canonical(self.ledger))

    def test_no_authority_or_current_market_claim(self):
        self.assertEqual(self.ledger['authorities'], AUTHORITIES)
        self.assertTrue(all(v is False for v in AUTHORITIES.values()))
        self.assertFalse(self.ledger['new_acquisition_performed'])

    def reject_resealed(self, mutate):
        ledger = copy.deepcopy(self.ledger)
        mutate(ledger)
        for row in ledger['records']:
            row['record_commitment_sha256'] = digest(canonical({k:v for k,v in row.items()
                                                    if k != 'record_commitment_sha256'}))
        ledger['ledger_commitment_sha256'] = digest(canonical({k:v for k,v in ledger.items()
                                                    if k != 'ledger_commitment_sha256'}))
        with self.assertRaisesRegex(ValueError, 'differs_from_authenticated_sources'):
            verify_ledger(ledger)

    def test_rehashing_cannot_supply_a_winner_or_oracle_link(self):
        for key, val in [('winner_address', '0x'+'1'*40), ('oracle_update_block', 25880316),
                         ('subject_id', '1'*64), ('blocks_from_oracle_to_winner', 0)]:
            with self.subTest(key=key):
                self.reject_resealed(lambda d: d['records'][0].__setitem__(key, val))

    def test_rehashing_cannot_turn_unknown_cost_into_zero(self):
        for key in ('builder_payment_usd_wad', 'liquidation_bonus_usd_wad',
                    'winner_gas_usd_wad', 'observed_winner_net_margin_usd_wad'):
            with self.subTest(key=key):
                self.reject_resealed(lambda d: d['records'][0].__setitem__(key, '0'))

    def test_missing_duplicate_reordered_records_rejected(self):
        for mutate in (lambda d: d['records'].pop(),
                       lambda d: d['records'].append(d['records'][0]),
                       lambda d: d['records'].reverse()):
            self.reject_resealed(mutate)

    def test_missing_or_changed_event_receipt_join_rejected(self):
        for mutate in (lambda d: d['records'][0]['events'].clear(),
                       lambda d: d['records'][0]['receipt'].__setitem__('block_hash', '0x'+'0'*64),
                       lambda d: d['records'][0]['receipt'].__setitem__('total_gas_paid_wei', '0')):
            self.reject_resealed(mutate)

    def test_authority_scope_count_and_boolean_substitution_rejected(self):
        for mutate in (lambda d: d['authorities'].__setitem__('can_sign', True),
                       lambda d: d.__setitem__('scope', 'CERTIFIED'),
                       lambda d: d['summary'].__setitem__('event_count', 139.0),
                       lambda d: d['records'][0].__setitem__('chain_id', True),
                       lambda d: d['source_provenance']['receipts'].__setitem__('workflow_conclusion','success')):
            self.reject_resealed(mutate)

    def copied(self, directory):
        for p in EVIDENCE.glob('rmc016-*'):
            shutil.copyfile(p, directory / p.name)
        shutil.copyfile(EVIDENCE/'historical-intake-pin.json', directory/'historical-intake-pin.json')

    def test_changed_archive_and_pin_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            self.copied(path)
            (path/'rmc016-events.zip').write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError, 'source_archive_changed'):
                build_ledger(path)
            self.copied(path)
            (path/'historical-intake-pin.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'intake_pin_changed'):
                build_ledger(path)

    def test_changed_metadata_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            self.copied(path)
            (path/'rmc016-receipts-metadata.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError, 'source_metadata_changed'):
                build_ledger(path)

    def test_symlink_input_and_symlink_parent_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path/'link').symlink_to(EVIDENCE, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlink_input'):
                build_ledger(path/'link')
            self.copied(path)
            p = path/'rmc016-events.zip'
            p.unlink(); p.symlink_to(EVIDENCE/p.name)
            with self.assertRaisesRegex(ValueError, 'symlink_input'):
                build_ledger(path)

    def test_all_transitive_original_sources_pinned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dst = root/'ci/nqc-census'; dst.mkdir(parents=True)
            for name in SOURCE_BLOBS:
                for n in SOURCE_BLOBS:
                    shutil.copyfile(ROOT/'ci/nqc-census'/(n+'.py'), dst/(n+'.py'))
                (dst/(name+'.py')).write_text('raise AssertionError("must not execute")')
                with self.assertRaisesRegex(ValueError, 'original_source_changed'):
                    original_validator(root)

    def test_original_loader_does_not_replace_global_modules(self):
        before = {n: sys.modules.get(n) for n in SOURCE_BLOBS}
        original_validator()
        self.assertEqual({n: sys.modules.get(n) for n in SOURCE_BLOBS}, before)

    def reject_metadata(self, mutate, name='receipts'):
        meta = json.loads((EVIDENCE/f'rmc016-{name}-metadata.json').read_bytes())
        mutate(meta)
        with self.assertRaises((ValueError, TypeError, KeyError)):
            verify_metadata(meta, name, self.pin['sources'][name])

    def test_cross_repository_run_commit_and_tree_substitution_rejected(self):
        for mutate in (lambda m: m['run']['repository'].__setitem__('id', 1411047452),
                       lambda m: m['run'].__setitem__('id', 1),
                       lambda m: m['run'].__setitem__('run_attempt', True),
                       lambda m: m['run'].__setitem__('head_sha', '0'*40),
                       lambda m: m['commit']['tree'].__setitem__('sha', '0'*40),
                       lambda m: m['artifact']['workflow_run'].__setitem__('head_sha', '0'*40)):
            self.reject_metadata(mutate)

    def test_promoting_failed_run_or_artifact_identity_rejected(self):
        for mutate in (lambda m: m['run'].__setitem__('conclusion', 'success'),
                       lambda m: m['artifact'].__setitem__('id', 1),
                       lambda m: m['artifact'].__setitem__('digest', 'sha256:'+'0'*64),
                       lambda m: m['artifact'].__setitem__('expired', True)):
            self.reject_metadata(mutate)

    def test_capture_before_completion_or_after_expiry_rejected(self):
        for time in ('2020-01-01T00:00:00Z', '2030-01-01T00:00:00Z', 'not-time'):
            self.reject_metadata(lambda m: m.__setitem__('retrieved_at', time))

    def repack(self, mutate):
        entries=[]
        with zipfile.ZipFile(EVIDENCE/'rmc016-events.zip') as z:
            for i in z.infolist(): entries.append([copy.copy(i), z.read(i)])
        mutate(entries)
        out=io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
                for i,b in entries:
                    i.compress_type=zipfile.ZIP_DEFLATED;z.writestr(i,b)
        return out.getvalue()

    def test_duplicate_missing_unknown_and_traversal_zip_members_rejected(self):
        for mutate in (lambda e: e.append(e[0]), lambda e: e.pop(),
                       lambda e: setattr(e[0][0], 'filename', '../archive.sha256'),
                       lambda e: setattr(e[0][0], 'filename', 'unknown')):
            with self.assertRaises(ValueError):
                unpack(self.repack(mutate), self.pin['sources']['events']['members'])

    def test_zip_symlinks_special_files_and_oversized_members_rejected(self):
        for mutate in (lambda e: setattr(e[0][0], 'external_attr', 0o120777<<16),
                       lambda e: setattr(e[0][0], 'external_attr', 0o060600<<16),
                       lambda e: e[0].__setitem__(1, b'0'*(MAX_MEMBER+1))):
            with self.assertRaises(ValueError):
                unpack(self.repack(mutate), self.pin['sources']['events']['members'])
        with self.assertRaisesRegex(ValueError, 'archive_size_limit'):
            unpack(b'0'*(MAX_ARCHIVE+1), {})

    def test_zip_content_hash_rejects_changed_member(self):
        with self.assertRaisesRegex(ValueError, 'member_digest'):
            unpack(self.repack(lambda e: e[0].__setitem__(1, b'wrong')),
                   self.pin['sources']['events']['members'])

    def test_cli_roundtrip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'ledger.json'
            cmd=[sys.executable, '-B', str(ROOT/'omega/historical_intake.py'), '--output', str(out)]
            result=subprocess.run(cmd,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr+result.stdout)
            self.assertEqual(out.read_bytes(),canonical(self.ledger))
            result=subprocess.run(cmd,capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(out.read_bytes(),canonical(self.ledger))
            result=subprocess.run(cmd[:-2]+['--ledger',str(out)],capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr+result.stdout)


if __name__ == '__main__':
    unittest.main()
