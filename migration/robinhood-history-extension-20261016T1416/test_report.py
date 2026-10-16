"""Independent arithmetic and conservation checks on preserved real evidence."""
from decimal import Decimal
import hashlib,json,unittest
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent;CAPTURE=HERE/'evidence/pilot'

class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary=json.loads((HERE/'evidence/summary.json').read_text())
        cls.rows=json.loads((CAPTURE/'requests.json').read_text())
        cls.journal=[json.loads(s) for s in (CAPTURE/'journal.jsonl').read_text().splitlines()]
        cls.observations=[j['data'] for j in cls.journal if j['kind']=='observation_completed']
        cls.source=json.loads((CAPTURE/'source-registry.json').read_text())['state']
        cls.current=json.loads((CAPTURE/'registry.json').read_text())['state']
    def test_registration_and_terminal_counts(self):
        self.assertEqual(self.journal[0]['data']['registration_commit'],'1d7a779b4d21921bc2f446b6e3fc34bf98132187')
        self.assertEqual(self.journal[-1]['kind'],self.summary['status'])
        self.assertEqual((self.summary['status'],len(self.rows),len(self.observations)),('stopped',145,0))
        self.assertEqual(self.summary['terminal']['reason'],'REGISTRY_CAPACITY_NO_TRIMMING')
        self.assertFalse(self.summary['current_coverage_measured'])
        self.assertFalse(self.summary['current_candidates_measured'])
        self.assertEqual(len(self.summary['new_accounts_in_unmerged_history']),2)
        self.assertEqual(len(self.rows),self.summary['rpc_calls'])
        self.assertLessEqual(len(self.rows),512)
        self.assertEqual(len(self.observations),self.summary['completed_observations'])
        self.assertEqual(sum('exception' in r for r in self.rows),self.summary['errors'])
        self.assertEqual(sum(self.summary['rpc_calls_by_phase'].values()),len(self.rows))
        self.assertFalse(self.summary['profitability_measured']);self.assertIsNone(self.summary['realized_profit'])
        if self.summary['status']=='completed':self.assertEqual(len(self.observations),3)
    def test_latency_retains_all_rounds_and_includes_admission(self):
        for obs in self.observations:
            head=next(r for r in self.rows if r['label']==f"observe-r{obs['round']}-head")
            check=next(r for r in self.rows if r['label']==f"observe-r{obs['round']}-canonical")
            self.assertEqual(obs['admission_to_verified_ms'],(check['verified_ns']-head['admission_requested_ns'])/1e6)
            self.assertEqual(obs['request_to_verified_ms'],(check['verified_ns']-head['started_ns'])/1e6)
            self.assertGreaterEqual(obs['admission_to_verified_ms'],obs['request_to_verified_ms'])
        values=[r['admission_to_verified_ms'] for r in self.observations]
        expected=dict(n=len(values),min=min(values),median=median(values),max=max(values)) if values else None
        self.assertEqual(self.summary['persistent_after_indexing']['admission_to_verified_ms'],expected)
        self.assertEqual(self.summary['within_assumed_1000ms'],sum(v<=1000 for v in values))
        self.assertEqual([r['round'] for r in self.summary['observations']],list(range(len(values))))
        self.assertFalse(self.summary['cold_acquisition_measured'])
    def test_global_gate_and_single_epoch(self):
        gaps=[(b['started_ns']-a['started_ns'])/1e6 for a,b in zip(self.rows,self.rows[1:])]
        self.assertGreaterEqual(min(gaps),350)
        self.assertEqual(min(gaps),self.summary['minimum_start_gap_ms'])
        self.assertEqual({r['connection_epoch'] for r in self.rows},{0})
        self.assertEqual(sum((r['started_ns']-r['admission_requested_ns'])/1e6 for r in self.rows),self.summary['admission_wait_ms'])
    def test_cadence_from_raw_requests(self):
        heads=[r for r in self.rows if r['label'].startswith('observe-r') and r['label'].endswith('-head')]
        dispatch=[(b['started_ns']-a['started_ns'])/1e6 for a,b in zip(heads,heads[1:])]
        admission=[(b['admission_requested_ns']-a['admission_requested_ns'])/1e6 for a,b in zip(heads,heads[1:])]
        self.assertEqual(dispatch,self.summary['header_dispatch_intervals_all_ms'])
        if len(heads)==len(self.observations):self.assertEqual(admission,self.summary['cadence_intervals_all_ms'])
        if dispatch:self.assertGreaterEqual(min(dispatch),1050)
    def test_source_payload_conservation_and_contiguous_new_window(self):
        offset=next(i for i,s in enumerate(self.current['segments']) if s['first']==self.source['from_block'])
        previous_segments=self.current['segments'][offset:offset+len(self.source['segments'])]
        strip=lambda s:{k:v for k,v in s.items() if k!='previous_segment_sha256'}
        self.assertEqual([strip(s) for s in previous_segments],[strip(s) for s in self.source['segments']])
        previous=self.current['from_block']-1
        for segment in self.current['segments']:
            self.assertEqual((segment['first'],segment['start']['number']),(previous+1,previous))
            previous=segment['end']['number']
        self.assertEqual(previous,self.current['through_block'])
        self.assertEqual(self.current['through_block']-self.current['from_block']+1,self.summary['registry']['blocks'])
        if self.summary['backfill_merged']:
            self.assertEqual(self.current['from_block'],87446281)
            self.assertEqual(self.summary['registry']['added_history_blocks'],400000)
    def test_account_partition_and_same_hash_coverage(self):
        before={e['borrower'] for s in self.source['segments'] for e in s['events']}
        after={e['borrower'] for s in self.current['segments'] for e in s['events']}
        historical=set(self.summary['new_historical_accounts']);tail=set(self.summary['new_tail_accounts'])
        self.assertEqual(len(before),52)
        self.assertFalse(before&historical or before&tail or historical&tail)
        self.assertEqual(before|historical|tail,after)
        self.assertEqual(len(after),self.summary['validated_prefix_accounts'])
        for raw,report in zip(self.observations,self.summary['observations']):
            state=raw['state'];total=state['coverage']['total_borrow_shares']
            self.assertEqual({p['borrower'] for p in state['positions']},after)
            shares=lambda group:sum(p['position'][1] for p in state['positions'] if p['borrower'] in group)
            pct=lambda n:str(Decimal(n)*100/Decimal(total))
            self.assertEqual(shares(after),state['coverage']['observed_borrow_shares'])
            self.assertEqual(shares(after)+state['coverage']['missing_borrow_shares'],total)
            self.assertEqual(pct(shares(after)),report['coverage_percent'])
            self.assertEqual(pct(shares(before)),report['prior_cohort_coverage_percent_same_block'])
            self.assertEqual(pct(shares(historical)),report['new_historical_accounts_coverage_percentage_points'])
            self.assertEqual(pct(shares(tail)),report['new_tail_accounts_coverage_percentage_points'])
            self.assertEqual(sum(p['position'][1]>0 for p in state['positions']),report['positive_debt_accounts'])
            self.assertEqual(state['screen_candidate_count'],report['candidates'])
            for group,key in ((historical,'new_historical_positive_debt_accounts'),(tail,'new_tail_positive_debt_accounts')):
                self.assertEqual(sum(p['position'][1]>0 for p in state['positions'] if p['borrower'] in group),report[key])
    def test_registered_sources_and_source_bytes_unchanged(self):
        lock=json.loads((HERE/'registration-sources.json').read_text())
        for filename,expected in lock['files'].items():self.assertEqual(hashlib.sha256((HERE/filename).read_bytes()).hexdigest(),expected,filename)
        self.assertEqual(hashlib.sha256((CAPTURE/'registry.json').read_bytes()).hexdigest(),self.summary['registry_file_sha256'])
        self.assertEqual(hashlib.sha256((CAPTURE/'source-registry.json').read_bytes()).hexdigest(),'915da8d32ebea82d9999f23a827a934faa6daef0c105eeeaceb6208fbd58ba5f')

if __name__=='__main__':unittest.main()
