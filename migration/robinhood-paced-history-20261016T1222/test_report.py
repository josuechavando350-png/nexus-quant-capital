"""Independent arithmetic on the preserved real capture; no network."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from statistics import median
import unittest

HERE=Path(__file__).resolve().parent
CAPTURE=HERE/'evidence/pilot'

class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary=json.loads((HERE/'evidence/summary.json').read_text())
        cls.rows=json.loads((CAPTURE/'requests.json').read_text())
        cls.journal=[json.loads(s) for s in (CAPTURE/'journal.jsonl').read_text().splitlines()]
        cls.observations=[j['data'] for j in cls.journal if j['kind']=='observation_completed']
        cls.source=json.loads((CAPTURE/'source-registry.json').read_text())['state']
        cls.current=json.loads((CAPTURE/'registry.json').read_text())['state']

    def test_registration_and_counts(self):
        self.assertEqual(self.journal[0]['data']['registration_commit'],'91b61a95541e5950772a7c919060df3a477d6821')
        self.assertEqual(self.journal[-1]['kind'],'completed')
        self.assertEqual((len(self.rows),len(self.observations)),(194,3))
        self.assertFalse(any('exception' in r for r in self.rows))
        self.assertEqual(self.summary['errors'],0)
        self.assertFalse(self.summary['profitability_measured'])
        self.assertIsNone(self.summary['realized_profit'])
        self.assertEqual(self.summary['rpc_calls_by_phase'],dict(verify=4,history=152,catchup=25,authenticate=4,observe=9))

    def test_latency_includes_admission_and_retains_every_round(self):
        for obs in self.observations:
            head=next(r for r in self.rows if r['label']==f"observe-r{obs['round']}-head")
            check=next(r for r in self.rows if r['label']==f"observe-r{obs['round']}-canonical")
            self.assertEqual(obs['admission_to_verified_ms'],(check['verified_ns']-head['admission_requested_ns'])/1e6)
            self.assertEqual(obs['request_to_verified_ms'],(check['verified_ns']-head['started_ns'])/1e6)
            self.assertGreater(obs['admission_to_verified_ms'],obs['request_to_verified_ms'])
        values=[r['admission_to_verified_ms'] for r in self.observations]
        self.assertEqual(self.summary['persistent_after_indexing']['admission_to_verified_ms'],dict(n=3,min=min(values),median=median(values),max=max(values)))
        self.assertEqual(self.summary['within_assumed_1000ms'],sum(v<=1000 for v in values))
        self.assertFalse(self.summary['cold_acquisition_measured'])
        self.assertEqual([r['round'] for r in self.summary['observations']],[0,1,2])

    def test_one_global_gate_and_session_across_all_phases(self):
        gaps=[(b['started_ns']-a['started_ns'])/1e6 for a,b in zip(self.rows,self.rows[1:])]
        self.assertGreaterEqual(min(gaps),350)
        self.assertEqual(min(gaps),self.summary['minimum_start_gap_ms'])
        self.assertEqual({r['connection_epoch'] for r in self.rows},{0})
        self.assertEqual({r['transport']['client_socket_tag'] for r in self.rows},{1})
        self.assertTrue(all(r['transport']['client_socket_reused'] for r in self.rows[1:]))

    def test_cadence_and_total_wait_recomputed(self):
        heads=[r for r in self.rows if r['label'].startswith('observe-r') and r['label'].endswith('-head')]
        dispatch=[(b['started_ns']-a['started_ns'])/1e6 for a,b in zip(heads,heads[1:])]
        admission=[(b['admission_requested_ns']-a['admission_requested_ns'])/1e6 for a,b in zip(heads,heads[1:])]
        self.assertEqual(dispatch,self.summary['header_dispatch_intervals_all_ms'])
        self.assertEqual(admission,self.summary['cadence_intervals_all_ms'])
        self.assertGreaterEqual(min(dispatch),1050)
        self.assertEqual(sum((r['started_ns']-r['admission_requested_ns'])/1e6 for r in self.rows),self.summary['admission_wait_ms'])

    def test_conservation_and_contiguous_windows(self):
        older=json.loads((CAPTURE/'older-registry.json').read_text())['state']
        joined=json.loads((CAPTURE/'merged-before-catchup.json').read_text())['state']
        self.assertEqual((older['from_block'],older['through_block']),(88246281,88646280))
        self.assertEqual(joined['through_block'],self.source['through_block'])
        old_segments=self.current['segments'][len(older['segments']):len(older['segments'])+len(self.source['segments'])]
        strip=lambda s:{k:v for k,v in s.items() if k!='previous_segment_sha256'}
        self.assertEqual([strip(s) for s in old_segments],[strip(s) for s in self.source['segments']])
        previous=self.current['from_block']-1
        for segment in self.current['segments']:
            self.assertEqual(segment['first'],previous+1)
            self.assertEqual(segment['start']['number'],previous)
            previous=segment['end']['number']
        self.assertEqual(previous,90080877)
        self.assertEqual(self.summary['registry']['blocks'],1834597)
        self.assertEqual(self.summary['registry']['events'],97)
        self.assertEqual(self.summary['older_registry']['events'],30)
        self.assertEqual(self.summary['registry']['added_events']-30,6)

    def test_disjoint_cohorts_and_same_block_coverage(self):
        before={e['borrower'] for s in self.source['segments'] for e in s['events']}
        historical=set(self.summary['new_historical_accounts']);tail=set(self.summary['new_tail_accounts'])
        after={e['borrower'] for s in self.current['segments'] for e in s['events']}
        self.assertEqual((len(before),len(historical),len(tail),len(after)),(31,13,2,46))
        self.assertFalse(before&historical or before&tail or historical&tail)
        self.assertEqual(before|historical|tail,after)
        for raw,report in zip(self.observations,self.summary['observations']):
            state=raw['state'];total=state['coverage']['total_borrow_shares']
            self.assertEqual({p['borrower'] for p in state['positions']},after)
            shares=lambda group:sum(p['position'][1] for p in state['positions'] if p['borrower'] in group)
            pct=lambda n:str(Decimal(n)*100/Decimal(total))
            self.assertEqual(shares(after),state['coverage']['observed_borrow_shares'])
            self.assertEqual(pct(shares(after)),report['coverage_percent'])
            self.assertEqual(pct(shares(before)),report['prior_cohort_coverage_percent_same_block'])
            self.assertEqual(pct(shares(historical)),report['new_historical_accounts_coverage_percentage_points'])
            self.assertEqual(pct(shares(tail)),report['new_tail_accounts_coverage_percentage_points'])
            self.assertEqual((report['positive_debt_accounts'],report['candidates'],report['unhealthy']),(39,0,0))

    def test_all_registered_sources_and_registry_hash_unchanged(self):
        lock=json.loads((HERE/'registration-sources.json').read_text())
        for filename,expected in lock['files'].items():
            self.assertEqual(hashlib.sha256((HERE/filename).read_bytes()).hexdigest(),expected,filename)
        self.assertEqual(hashlib.sha256((CAPTURE/'registry.json').read_bytes()).hexdigest(),self.summary['registry_file_sha256'])

if __name__=='__main__':unittest.main()
