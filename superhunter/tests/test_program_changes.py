"""Policy-change controls using explicit synthetic programs, never real targets."""
from copy import deepcopy
from datetime import timedelta
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from superhunter import program_registry as pr, program_changes as changes
from superhunter.safe_io import canonical, strict_json
from test_program_registry import example, NOW

AFTER = NOW + timedelta(minutes=1)


class ProgramChangeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        p, doc, case = example()
        self.old = {'schema_version': 1, 'programs': [p]}
        self.new = deepcopy(self.old)
        self.docs = {p['document']['file']: doc}
        self.requests = {'schema_version': 1, 'cases': [case]}
        self.before_time, self.after_time = NOW, AFTER

    def approve(self, program):
        program['review']['reviewed_at'] = self.after_time.isoformat()
        program['review']['expires_at'] = (self.after_time + timedelta(hours=2)).isoformat()
        program['review']['revision_sha256'] = pr.revision(program)

    def save(self, label, policy, requests, docs, at):
        folder = self.root / (label+'-inputs')
        folder.mkdir()
        (folder/'registry.json').write_bytes(canonical(policy))
        (folder/'requests.json').write_bytes(canonical(requests))
        documents = folder/'docs'; documents.mkdir()
        for n, raw in docs.items():
            (documents/n).write_bytes(raw)
        out = self.root/label
        pr.create(folder/'registry.json', folder/'requests.json', documents, out, now=at)
        return out

    def pair(self, *, new_requests=None, new_docs=None):
        a = self.save('before', self.old, self.requests, self.docs, self.before_time)
        b = self.save('after', self.new, self.requests if new_requests is None else new_requests,
                      self.docs if new_docs is None else new_docs, self.after_time)
        return a, b

    def run_comparison(self, **kwargs):
        a, b = self.pair(**kwargs)
        return changes.compare(changes.capture(a), changes.capture(b), now=max(self.before_time,self.after_time))

    def bundle(self):
        a, b = self.pair()
        out = self.root/'comparison'
        changes.create(a,b,out,now=AFTER)
        return out

    def alter(self, root, name, fn):
        value = strict_json((root/name).read_bytes()); fn(value)
        raw = canonical(value); (root/name).write_bytes(raw)
        marker = strict_json((root/'COMPLETE.json').read_bytes())
        marker['sha256'][name] = hashlib.sha256(raw).hexdigest()
        (root/'COMPLETE.json').write_bytes(canonical(marker))

    def test_unchanged_snapshot_does_not_invent_changes(self):
        r, _ = self.run_comparison()
        self.assertEqual(r['transition_counts'], {'STILL_ELIGIBLE_LOCAL_REVIEW':1})
        self.assertEqual(r['program_changes'], [])
        self.assertFalse(r['live_testing_authorized'])

    def test_exclusion_identifies_exact_affected_case(self):
        p=self.new['programs'][0]; p['excluded']=[deepcopy(self.requests['cases'][0]['asset'])]
        self.approve(p)
        r,_=self.run_comparison()
        self.assertEqual(r['transition_counts'],{'LOST_LOCAL_ELIGIBILITY':1})
        self.assertIn('EXPLICITLY_EXCLUDED',r['case_effects'][0]['after_reasons'])
        self.assertEqual(len(r['program_changes'][0]['exclusions_added_sha256']),1)

    def test_asset_removed_even_with_fresh_review(self):
        p=self.new['programs'][0];p['assets'].pop(0);self.approve(p)
        r,_=self.run_comparison()
        self.assertIn('ASSET_NOT_EXPLICITLY_LISTED',r['case_effects'][0]['after_reasons'])
        self.assertEqual(len(r['program_changes'][0]['assets_removed_sha256']),1)

    def test_stale_human_review_is_not_carried_forward(self):
        self.new['programs'][0]['rules']['allowed_actions'].remove('offline_source_review')
        r,_=self.run_comparison()
        self.assertIn('POLICY_CHANGED_SINCE_REVIEW',r['case_effects'][0]['after_reasons'])

    def test_participation_revocation_invalidates_local_eligibility(self):
        p=self.new['programs'][0];p['participation']='revoked';self.approve(p)
        r,_=self.run_comparison()
        self.assertEqual(r['transition_counts'],{'LOST_LOCAL_ELIGIBILITY':1})
        self.assertIn('PARTICIPATION_NOT_ACCEPTED',r['case_effects'][0]['after_reasons'])

    def test_paused_program_not_eligible(self):
        p=self.new['programs'][0];p['status']='paused';self.approve(p)
        r,_=self.run_comparison()
        self.assertIn('PROGRAM_NOT_ACTIVE',r['case_effects'][0]['after_reasons'])

    def test_expiry_is_separated_from_policy_mutation(self):
        self.after_time=NOW+timedelta(hours=3)
        r,_=self.run_comparison()
        self.assertEqual(r['program_changes'],[])
        e=r['case_effects'][0]
        self.assertTrue(e['clock_changes_decision'])
        self.assertFalse(e['snapshot_changes_decision'])
        self.assertEqual(e['transition'],'LOST_LOCAL_ELIGIBILITY')

    def test_expired_snapshot_cannot_be_used_for_current_permission(self):
        out=self.bundle()
        r=changes.verify(out,now=NOW+timedelta(hours=3))
        self.assertEqual(r['transition_counts'],{'STILL_ELIGIBLE_LOCAL_REVIEW':1})
        self.assertEqual(r['current_after_counts'],{'BLOCKED':1})
        self.assertFalse(r['live_testing_authorized'])

    def test_mixed_clock_and_policy_changes_both_retained(self):
        self.after_time=NOW+timedelta(hours=3)
        p=self.new['programs'][0];p['excluded']=[deepcopy(p['assets'][0])];self.approve(p)
        r,_=self.run_comparison();e=r['case_effects'][0]
        self.assertTrue(e['clock_changes_decision']);self.assertTrue(e['snapshot_changes_decision'])

    def test_gained_eligibility_is_only_local_and_manual(self):
        self.old['programs'][0]['review']['status']='pending'
        r,_=self.run_comparison();e=r['case_effects'][0]
        self.assertEqual(e['transition'],'GAINED_LOCAL_ELIGIBILITY')
        self.assertTrue(e['human_review_required'])
        for k in ('live_testing_authorized','submission_enabled','authorization_authenticated',
                  'latest_remote_policy_verified','source_order_authenticated','vulnerability_confirmed'):
            self.assertIs(r[k],False)

    def test_two_platforms_same_slug_never_share_authorization(self):
        p=self.new['programs'][0];p['platform']='hackerone';self.approve(p)
        r,_=self.run_comparison()
        self.assertIn('PROGRAM_NOT_REGISTERED',r['case_effects'][0]['after_reasons'])
        self.assertEqual(len(r['program_changes']),2)

    def test_removed_program_reported_not_silently_dropped(self):
        p,d,_=example('cantina',2)
        self.old['programs'].append(p);self.new['programs']=[deepcopy(p)]
        self.docs[p['document']['file']]=d
        # Old capture has both docs; new capture has only documents for remaining programs.
        r,_=self.run_comparison(new_docs={p['document']['file']:d})
        self.assertEqual(r['transition_counts'],{'LOST_LOCAL_ELIGIBILITY':1})

    def test_new_program_reported_without_active_access(self):
        p,d,c=example('sherlock',2)
        self.new['programs'].append(p)
        self.requests['cases'].append(c)
        r,_=self.run_comparison(new_docs={**self.docs,p['document']['file']:d})
        self.assertEqual(r['transition_counts']['GAINED_LOCAL_ELIGIBILITY'],1)
        self.assertTrue(any('PROGRAM_ADDED' in x['changed_fields'] for x in r['program_changes']))

    def test_document_content_change_is_explicit(self):
        p=self.new['programs'][0];raw=b'SYNTHETIC changed document.'
        p['document']['sha256']=hashlib.sha256(raw).hexdigest();self.approve(p)
        r,_=self.run_comparison(new_docs={p['document']['file']:raw})
        self.assertTrue(r['program_changes'][0]['document_bytes_changed'])

    def test_document_tampering_is_not_silently_treated_as_new_approval(self):
        raw=b'SYNTHETIC unexpected change without digest update.'
        r,_=self.run_comparison(new_docs={next(iter(self.docs)):raw})
        self.assertIn('POLICY_DOCUMENT_CHANGED',r['case_effects'][0]['after_reasons'])

    def test_case_removal_cannot_improve_result(self):
        c=deepcopy(self.requests['cases'][0]);c['id']='second';self.requests['cases'].append(c)
        with self.assertRaisesRegex(ValueError,'CASE_IDENTITY_SET_CHANGED'):
            self.run_comparison(new_requests={'schema_version':1,'cases':[c]})

    def test_changed_case_asset_rejected(self):
        req=deepcopy(self.requests);req['cases'][0]['asset']['commit']='c'*40
        with self.assertRaisesRegex(ValueError,'CASE_IDENTITY_SET_CHANGED'):
            self.run_comparison(new_requests=req)

    def test_changed_case_action_rejected(self):
        req=deepcopy(self.requests);req['cases'][0]['action']='offline_source_review'
        with self.assertRaisesRegex(ValueError,'CASE_IDENTITY_SET_CHANGED'):
            self.run_comparison(new_requests=req)

    def test_request_reordering_allowed_but_none_disappears(self):
        c=deepcopy(self.requests['cases'][0]);c['id']='second';self.requests['cases'].append(c)
        req=deepcopy(self.requests);req['cases'].reverse()
        r,_=self.run_comparison(new_requests=req)
        self.assertEqual(r['case_count'],2)

    def test_reversed_snapshot_dates_rejected(self):
        self.before_time,self.after_time=AFTER,NOW
        with self.assertRaisesRegex(ValueError,'SNAPSHOT_ORDER'):
            self.run_comparison()

    def test_naive_comparison_time_rejected(self):
        a,b=self.pair()
        with self.assertRaisesRegex(ValueError,'AWARE_TIME_REQUIRED'):
            changes.compare(changes.capture(a),changes.capture(b),now=NOW.replace(tzinfo=None))

    def test_future_comparison_rejected(self):
        out=self.bundle()
        with self.assertRaisesRegex(ValueError,'FUTURE_COMPARISON'):
            changes.verify(out,now=NOW)

    def test_audit_binds_exact_results(self):
        r,a=self.run_comparison()
        self.assertEqual(a['entries'][-1]['data']['result_sha256'],pr.digest(r))
        self.assertEqual(a['entries'][1]['data'],r['case_effects'][0])

    def test_self_contained_after_inputs_deleted(self):
        import shutil
        out=self.bundle()
        shutil.rmtree(self.root/'before');shutil.rmtree(self.root/'after')
        self.assertEqual(changes.verify(out,now=AFTER)['case_count'],1)

    def test_hashed_file_tampering_rejected(self):
        out=self.bundle();(out/'comparison.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'BUNDLE_HASH'):
            changes.verify(out,now=AFTER)

    def test_resealed_approval_claim_rejected(self):
        out=self.bundle();self.alter(out,'comparison.json',lambda d:d.update(live_testing_authorized=True))
        with self.assertRaisesRegex(ValueError,'REPLAY_DISAGREEMENT'):
            changes.verify(out,now=AFTER)

    def test_resealed_count_rejected(self):
        out=self.bundle();self.alter(out,'comparison.json',lambda d:d.update(case_count=1000))
        with self.assertRaisesRegex(ValueError,'REPLAY_DISAGREEMENT'):
            changes.verify(out,now=AFTER)

    def test_resealed_audit_rejected(self):
        out=self.bundle();self.alter(out,'audit.json',lambda d:d['entries'].pop())
        with self.assertRaisesRegex(ValueError,'REPLAY_DISAGREEMENT'):
            changes.verify(out,now=AFTER)

    def test_boolean_schema_rejected(self):
        out=self.bundle();p=out/'COMPLETE.json';d=strict_json(p.read_bytes());d['schema_version']=True;p.write_bytes(canonical(d))
        with self.assertRaisesRegex(ValueError,'MANIFEST_SCHEMA'):
            changes.verify(out,now=AFTER)

    def test_symlink_input_rejected(self):
        a,b=self.pair();alias=self.root/'alias';alias.symlink_to(a,target_is_directory=True)
        with self.assertRaises(ValueError):changes.create(alias,b,self.root/'out',now=AFTER)

    def test_new_output_and_private_permissions(self):
        out=self.bundle();self.assertEqual(out.stat().st_mode&0o777,0o700)
        self.assertTrue(all(p.stat().st_mode&0o777==0o600 for p in out.iterdir()))
        with self.assertRaises(ValueError):changes.create(self.root/'before',self.root/'after',out,now=AFTER)

    def test_untracked_file_rejected(self):
        out=self.bundle();(out/'untracked.txt').write_text('not evidence')
        with self.assertRaisesRegex(ValueError,'BUNDLE_FILE_SET'):
            changes.verify(out,now=AFTER)

    def test_capture_size_budget(self):
        a,_=self.pair()
        with patch.object(changes,'MAX_SNAPSHOT_BYTES',1),self.assertRaises(ValueError):
            changes.capture(a)

    def test_no_network_or_process_execution(self):
        with patch('socket.socket',side_effect=AssertionError('network')),patch('subprocess.run',side_effect=AssertionError('child')):
            self.assertEqual(changes.verify(self.bundle(),now=AFTER)['case_count'],1)

    def test_input_mutation_blocks_publication(self):
        a,b=self.pair();real=changes.capture;count=0
        def altered(root):
            nonlocal count
            count+=1;value=real(root)
            if count==3:value['REVIEW.md']+=b'changed'
            return value
        with patch.object(changes,'capture',side_effect=altered),self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):
            changes.create(a,b,self.root/'not-complete',now=AFTER)
        self.assertFalse((self.root/'not-complete').exists())

    def test_summary_does_not_echo_policy_content_or_names(self):
        r,_=self.run_comparison();text=changes.render(r)
        self.assertNotIn(b'own/example',text);self.assertNotIn(b'fixture-1',text)
        self.assertNotIn(b'SYNTHETIC POLICY',text)

    def test_cli_dispatch_and_current_time(self):
        from superhunter import __main__,quality
        a,b=self.pair();out=self.root/'cli'
        with patch.object(pr,'clock',return_value=AFTER),patch('sys.argv',['sh','compare-programs','--before',str(a),'--after',str(b),'--out',str(out)]),redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(__main__.main(),0)
        self.assertFalse(json.loads(stdout.getvalue())['live_testing_authorized'])
        self.assertIn('program_changes',quality.COMPONENTS)
        with patch.object(pr,'clock',return_value=AFTER),redirect_stdout(io.StringIO()):
            self.assertEqual(changes.main(['verify-program-changes','--bundle',str(out)]),0)

    def test_cli_blocked_snapshot_returns_nonzero(self):
        self.new['programs'][0]['review']['status']='revoked';a,b=self.pair()
        with patch.object(pr,'clock',return_value=AFTER),redirect_stdout(io.StringIO()):
            self.assertEqual(changes.main(['compare-programs','--before',str(a),'--after',str(b),'--out',str(self.root/'out')]),1)

    def test_cli_errors_do_not_echo_values(self):
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(changes.main(['verify-program-changes','--bundle',str(self.root/'SECRET')]),2)
        self.assertNotIn('SECRET',stdout.getvalue())
        with patch('sys.stderr',new_callable=io.StringIO) as stderr,self.assertRaises(SystemExit):
            changes.main(['verify-program-changes','--bundle','missing','--token','SECRET'])
        self.assertNotIn('SECRET',stderr.getvalue())

    def test_engine_change_during_comparison_rejected(self):
        a,b=self.pair()
        old,new=changes.capture(a),changes.capture(b)
        with patch.object(changes,'_engine',side_effect=[{'snapshot':'old'},{'snapshot':'new'}]), self.assertRaisesRegex(ValueError,'ENGINE_CHANGED'):
            changes.compare(old,new,now=AFTER)

    def test_verifier_enforces_capture_budget_before_replay(self):
        out=self.bundle()
        with patch.object(changes,'MAX_SNAPSHOT_BYTES',1), self.assertRaisesRegex(ValueError,'SIZE_LIMIT'):
            changes.verify(out,now=AFTER)

    def test_changed_document_without_metadata_is_reported(self):
        raw=b'SYNTHETIC changed bytes, same metadata.'
        r,_=self.run_comparison(new_docs={next(iter(self.docs)):raw})
        self.assertEqual(len(r['program_changes']),1)
        self.assertTrue(r['program_changes'][0]['document_bytes_changed'])
        self.assertIn('DOCUMENT_BYTES_CHANGED_WITHOUT_METADATA',r['program_changes'][0]['changed_fields'])


if __name__=='__main__':unittest.main()
