"""Independent arithmetic checks on the real preserved capture; no network."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from statistics import median
import unittest

HERE=Path(__file__).resolve().parent
CAPTURE=HERE.parent/'robinhood-paced-acquisition-20261016T1024/evidence/pilot'


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary=json.loads((HERE/'evidence/summary.json').read_text())
        cls.rows=json.loads((CAPTURE/'requests.json').read_text())
        cls.journal=[json.loads(s) for s in (CAPTURE/'journal.jsonl').read_text().splitlines()]
        cls.observations=[j['data'] for j in cls.journal if j['kind']=='observation_completed']

    def test_registered_identity_complete_counts_and_no_hidden_errors(self):
        self.assertEqual(self.journal[0]['data']['registration_commit'],'f82249cd9844d686b13e637b5d22a7eca88985d1')
        self.assertEqual(self.journal[-1]['kind'],'completed')
        self.assertEqual(len(self.rows),89)
        self.assertEqual(len(self.observations),12)
        self.assertFalse(any('exception' in row for row in self.rows))
        self.assertEqual(self.summary['errors'],0)
        self.assertFalse(self.summary['profitability_measured'])
        self.assertIsNone(self.summary['realized_profit'])

    def test_inclusive_latency_recomputed_from_every_raw_triplet(self):
        for obs in self.observations:
            triplet={r['label']:r for r in self.rows if r['label'].startswith('r'+str(obs['round'])+'-')}
            head=triplet[f"r{obs['round']}-head"]
            check=triplet[f"r{obs['round']}-canonical"]
            self.assertEqual(obs['admission_to_verified_ms'],(check['verified_ns']-head['admission_requested_ns'])/1e6)
            self.assertEqual(obs['request_to_verified_ms'],(check['verified_ns']-head['started_ns'])/1e6)
            self.assertGreaterEqual(obs['admission_to_verified_ms'],obs['request_to_verified_ms'])
            self.assertEqual(obs['within_assumed_1000ms'],obs['admission_to_verified_ms']<=1000)
        values=[r['admission_to_verified_ms'] for r in self.observations[1:]]
        self.assertEqual(self.summary['later']['admission_to_verified_ms'],dict(n=11,min=min(values),median=median(values),max=max(values)))
        self.assertEqual(sum(r['within_assumed_1000ms'] for r in self.observations),2)

    def test_global_gap_survives_cold_rotation(self):
        gaps=[(b['started_ns']-a['started_ns'])/1e6 for a,b in zip(self.rows,self.rows[1:])]
        self.assertGreaterEqual(min(gaps),350)
        self.assertEqual(min(gaps),self.summary['minimum_start_gap_ms'])
        boundary=next(i for i,r in enumerate(self.rows) if r['connection_epoch']==1)
        self.assertEqual(boundary,53)
        self.assertGreaterEqual(gaps[boundary-1],350)

    def test_admission_cadence_is_not_dispatch_cadence(self):
        heads=[r for r in self.rows if r['label'].startswith('r') and r['label'].endswith('-head')]
        dispatch=[(b['started_ns']-a['started_ns'])/1e6 for a,b in zip(heads,heads[1:])]
        admission=[(b['admission_requested_ns']-a['admission_requested_ns'])/1e6 for a,b in zip(heads,heads[1:])]
        self.assertEqual(dispatch,self.summary['header_dispatch_intervals_all_ms'])
        self.assertEqual(admission,self.summary['cadence_intervals_all_ms'])
        self.assertGreaterEqual(min(dispatch),1050)
        self.assertLess(min(admission),1000)  # Variable final-response time; not a rate-limit violation.
        self.assertGreater(sum(admission[1:])/len(admission[1:]),1050)

    def test_coverage_and_account_conservation_same_block(self):
        prior=json.loads((CAPTURE/'source-registry.json').read_text())['state']
        current=json.loads((CAPTURE/'registry.json').read_text())['state']
        before={e['borrower'] for s in prior['segments'] for e in s['events']}
        after={e['borrower'] for s in current['segments'] for e in s['events']}
        self.assertEqual(current['segments'][:len(prior['segments'])],prior['segments'])
        self.assertEqual((len(before),len(after)),(30,31))
        self.assertEqual(after-before,set(self.summary['new_accounts']))
        for original,reported in zip(self.observations,self.summary['observations']):
            state=original['state'];total=state['coverage']['total_borrow_shares']
            observed=sum(p['position'][1] for p in state['positions'])
            old=sum(p['position'][1] for p in state['positions'] if p['borrower'] in before)
            self.assertEqual(str(Decimal(observed)*100/Decimal(total)),reported['coverage_percent'])
            self.assertEqual(str(Decimal(observed-old)*100/Decimal(total)),reported['new_accounts_coverage_percentage_points'])
            self.assertEqual(reported['positive_debt_accounts'],25)
            self.assertEqual(reported['candidates'],0)

    def test_registry_hash_and_no_gap_or_discarded_round(self):
        raw=(CAPTURE/'registry.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),self.summary['registry_file_sha256'])
        state=json.loads(raw)['state'];previous=None
        for segment in state['segments']:
            if previous is not None:
                self.assertEqual(segment['first'],previous+1)
                self.assertEqual(segment['start']['number'],previous)
            previous=segment['end']['number']
        self.assertEqual(previous,90037169)
        self.assertEqual([r['round'] for r in self.summary['observations']],list(range(12)))


if __name__=='__main__':unittest.main()
