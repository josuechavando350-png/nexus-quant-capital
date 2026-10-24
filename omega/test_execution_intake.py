import copy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from evidence_store import admit, audit_store, create, export_store, read_batch, restore_store, revoke
from execution_intake import (BINDING_NAME, CATEGORIES, EVIDENCE, REPORT_NAME, ROOT,
    SOURCE_NAMES, build_execution_report, exercise_fields, load_execution_sources,
    query_execution_report, reconstruct_gas, seal, store_execution_report,
    verify_execution_report, verify_replay)
from integrity import canonical, digest, strict_json
from temporal_intake import build_temporal_report


def reseal(report):
    report.pop('report_commitment_sha256', None); return seal(report)


def synthetic_replay(network):
    # Only the namespace IDs are synthetic. This is never remote CI evidence.
    with tempfile.TemporaryDirectory() as tmp: report = exercise_fields(tmp)
    report['network'] = network; return seal(report)


class ExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = build_execution_report()
        cls.base = build_temporal_report()
        cls.sources, cls.members, cls.provenance, cls.original = load_execution_sources()

    def test_real_source_identity_and_unique_join(self):
        self.assertEqual(self.provenance['fork']['artifact_id'], 11534051574)
        self.assertEqual(self.provenance['gas']['artifact_id'], 11533854519)
        self.assertEqual([r['transaction_hash'] for r in self.report['records']],
                         [r['transaction_hash'] for r in self.base['records']])
        self.assertEqual(self.report['summary']['retained_execution_diagnostics'], 1)

    def test_eight_unsimulated_cases_stay_unknown(self):
        for row in self.report['records'][1:]:
            self.assertIsNone(row['execution_witness'])
            self.assertEqual(row['execution_status'], 'UNOBSERVED')
        self.assertEqual(self.report['summary']['unobserved_execution_count'], 8)

    def test_fork_flash_fee_is_separate_from_paid_cost(self):
        w = self.report['records'][0]['execution_witness']
        self.assertEqual(w['flash_principal_weth_wei'], '10684013854557827871')
        self.assertEqual(w['surplus_after_fork_flash_fee_weth_wei'], '90814117763741536')
        self.assertEqual(w['costs']['CAPITAL_FEE']['simulated_amount_wei'], '5342006927278914')
        self.assertIsNone(w['costs']['CAPITAL_FEE']['paid_amount_wei'])

    def test_measured_gas_is_not_receipt_gas(self):
        gas = self.report['records'][0]['execution_witness']['costs']['GAS']
        self.assertEqual(gas['measured_call_gas_units'], 562357)
        self.assertIsNone(gas['measured_transaction_gas_units'])
        self.assertIsNone(gas['paid_amount_wei'])

    def test_sensitivity_arithmetic_independently_recomputed(self):
        cases = self.report['records'][0]['execution_witness']['modeled_gas_sensitivities']
        for c, overhead, tip in zip(cases, (0,50000,100000,200000,300000), (0,1,2,5,10)):
            units = 562357 + 21000 + overhead; cost = units * (59451728 + tip*10**9)
            remaining = 90814117763741536 - cost
            self.assertEqual(c['modeled_native_eth_gas_cost_wei'], str(cost))
            self.assertEqual(c['remaining_weth_equivalent_at_1_to_1_eth_weth_before_all_other_costs_wei'], str(remaining))
            self.assertEqual(c['remaining_usd_wad_using_prior_block_oracle'], str(remaining*250480170000//10**8))
        self.assertEqual(cases[-1]['modeled_native_eth_gas_cost_wei'], '8886087100090896')

    def test_full_taxonomy_preserves_unknown_incidence_and_paid_amounts(self):
        costs = self.report['records'][0]['execution_witness']['costs']
        self.assertEqual(set(costs), set(CATEGORIES)); self.assertEqual(len(costs), 14)
        for cost in costs.values():
            self.assertIsNone(cost['paid_amount_wei']); self.assertEqual(cost['incidence'], 'UNKNOWN')
        self.assertEqual(costs['BUILDER_PAYMENT']['status'], 'UNKNOWN')

    def test_titan_replaces_budget_without_manufacturing_coverage(self):
        policy = self.report['gas_funding_policy']
        self.assertEqual(policy['payer'], 'TITAN'); self.assertEqual(policy['operator_gas_cap_mxn'], 0)
        self.assertIs(policy['operator_prefund_allowed'], False)
        self.assertIs(policy['own_gas_fallback_allowed'], False)
        self.assertIs(policy['execution_coverage_proven'], False)
        self.assertEqual(self.report['summary']['titan_covered_executions'], 0)
        w = self.report['records'][0]['execution_witness']
        for k in ('titan_execution_coverage_evidence', 'titan_repayment_wei', 'titan_net_balance_increase_wei'):
            self.assertIsNone(w[k])

    def test_no_profit_capture_or_authority_from_five_positive_budgets(self):
        w = self.report['records'][0]['execution_witness']
        self.assertTrue(all(c['budget_case_positive_after_this_gas_only'] for c in w['modeled_gas_sensitivities']))
        self.assertIsNone(w['complete_net_profit_wei']); self.assertIsNone(w['capture_probability'])
        self.assertTrue(all(v is False for v in self.report['authorities'].values()))
        self.assertTrue(all(r['executable_candidate'] is False for r in self.report['records']))
        self.assertEqual(self.report['summary']['complete_paid_cost_rows'], 0)

    def test_no_new_chain_or_titan_request_during_reproduction(self):
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            self.assertEqual(verify_execution_report(self.report), self.report)
        self.assertFalse(self.report['new_evm_execution_performed'])
        self.assertFalse(self.report['titan_request_performed'])

    def test_pin_archives_metadata_and_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for name in SOURCE_NAMES: shutil.copyfile(EVIDENCE/name, d/name)
            for name in SOURCE_NAMES:
                p = d/name; raw = p.read_bytes(); p.write_bytes(raw+b' ')
                with self.subTest(name=name), self.assertRaises(ValueError): load_execution_sources(d)
                p.unlink(); p.symlink_to(EVIDENCE/name)
                with self.assertRaises(ValueError): load_execution_sources(d)
                p.unlink(); p.write_bytes(raw)

    def test_original_validator_and_dependencies_are_frozen(self):
        pin = strict_json((EVIDENCE/'execution-pin.json').read_bytes())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in pin['source_files']:
                (root/name).parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT/name, root/name)
            for name in pin['source_files']:
                raw=(root/name).read_bytes(); (root/name).write_bytes(raw+b'\n')
                with self.subTest(path=name), self.assertRaisesRegex(ValueError, 'original_source_changed'):
                    load_execution_sources(root=root)
                (root/name).write_bytes(raw)

    def test_operator_disagreement_is_rejected(self):
        gas = copy.deepcopy(self.sources['gas'])
        gas['historical_source_operator_observations'][1]['winner_base_fee_per_gas_wei'] = '59451729'
        with self.assertRaisesRegex(ValueError, 'disagree'):
            reconstruct_gas(gas, self.members, EVIDENCE, self.original)

    def test_forged_gas_units_and_missing_pass_log_are_rejected(self):
        gas = copy.deepcopy(self.sources['gas']); gas['physical_flash_liquidation_call_gas_units'] += 1
        with self.assertRaises(ValueError): reconstruct_gas(gas, self.members, EVIDENCE, self.original)
        m = copy.deepcopy(self.members); m['gas']['physical-fork-gas-test.txt'] = b''
        with self.assertRaises(ValueError): reconstruct_gas(self.sources['gas'], m, EVIDENCE, self.original)

    def test_wrong_predecessor_or_principal_join_is_rejected(self):
        for field, value in [('weth_debt_wei','1'), ('block_hash','0x'+'0'*64)]:
            base = copy.deepcopy(self.base); base['records'][0][field] = value
            with patch('execution_intake.build_temporal_report', return_value=base), self.assertRaises(ValueError):
                build_execution_report()

    def test_duplicate_retrospective_winner_is_rejected(self):
        base = copy.deepcopy(self.base); base['records'].append(copy.deepcopy(base['records'][0]))
        with patch('execution_intake.build_temporal_report', return_value=base), self.assertRaisesRegex(ValueError,'winner_join'):
            build_execution_report()

    def test_resealed_paid_costs_and_profit_cannot_be_invented(self):
        for key, value in [('native_gas_paid_wei','0'),('complete_net_profit_wei','1'),
                           ('titan_execution_coverage_evidence','fake'),('capture_probability',1)]:
            r = copy.deepcopy(self.report); r['records'][0]['execution_witness'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): verify_execution_report(reseal(r))

    def test_resealed_titan_policy_cannot_enable_operator_fallback(self):
        for k,v in [('payer','OPERATOR'),('operator_gas_cap_mxn',2000),('execution_coverage_proven',True)]:
            r=copy.deepcopy(self.report);r['gas_funding_policy'][k]=v
            r['gas_policy_sha256']=digest(canonical(r['gas_funding_policy']))
            with self.assertRaises(ValueError):verify_execution_report(reseal(r))

    def test_store_query_and_restore_preserve_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=create(Path(tmp)/'a.sqlite');r=store_execution_report(path)
            self.assertEqual(query_execution_report(path,r['batch']),self.report)
            restore_store(Path(tmp)/'b.sqlite',export_store(path))
            self.assertEqual(query_execution_report(Path(tmp)/'b.sqlite',r['batch']),self.report)
            self.assertEqual(audit_store(path)['dependencies'][r['batch']],[r['parents']['temporal']])

    def test_admission_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=create(Path(tmp)/'a.sqlite');r=store_execution_report(path);before=export_store(path)
            self.assertEqual(store_execution_report(path),r);self.assertEqual(export_store(path),before)

    def test_missing_declared_parent_rejected_despite_identical_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=create(Path(tmp)/'a.sqlite');r=store_execution_report(path)
            detached=admit(path,read_batch(path,r['batch']),parents=[])
            with self.assertRaisesRegex(ValueError,'missing_declared_parent'):query_execution_report(path,detached)

    def test_inherited_object_changes_cannot_hide_in_resealed_batch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=create(Path(tmp)/'a.sqlite');r=store_execution_report(path)
            objects=read_batch(path,r['batch']);objects['temporal-report.json']+=b' '
            bad=admit(path,objects,parents=[r['parents']['temporal']])
            with self.assertRaisesRegex(ValueError,'inherited_bytes_changed'):query_execution_report(path,bad)

    def test_revoked_parent_blocks_economics_and_readmission(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=create(Path(tmp)/'a.sqlite');r=store_execution_report(path);before=read_batch(path,r['batch'])
            revoke(path,r['parents']['temporal'],'TEST_ONLY',b'test')
            with self.assertRaisesRegex(ValueError,'batch_inactive_or_missing'):query_execution_report(path,r['batch'])
            with self.assertRaises(ValueError):store_execution_report(path)
            self.assertEqual(read_batch(path,r['batch'],include_revoked=True),before)

    def test_worker_recovery_invalidates_all_six_batches(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=exercise_fields(tmp);self.assertEqual(r['blocked_batches'],6)
            self.assertTrue(r['revoked_query_rejected']);self.assertTrue(r['restore_byte_identical'])
            self.assertFalse(r['rust_transport_performed'])

    def test_forged_replay_summary_and_network_are_rejected(self):
        network={'interfaces':['lo'],'routable_network':False,
                 'network_namespace':'net:[2]','parent_network_namespace':'net:[1]'}
        report=synthetic_replay(network);self.assertEqual(verify_replay(report),report)
        bad=copy.deepcopy(report);bad['blocked_batches']=5
        with self.assertRaises(ValueError):verify_replay(reseal(bad))
        bad=copy.deepcopy(report);bad['network']['routable_network']=True
        with self.assertRaises(ValueError):verify_replay(reseal(bad))


if __name__ == '__main__': unittest.main()
