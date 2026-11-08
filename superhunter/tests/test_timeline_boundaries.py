"""Authored temporal boundary controls; no incident or authentic clock claims."""
import json
import unittest
from superhunter import forensic_timeline as t,journal_ingest as j


def case(times,uncertainty):
    return {'schema_version':1,'profile':'normalized-evidence-timeline-v1',
        'sources':[{'source_id':'boundary-control','clock_uncertainty_ms':uncertainty}],
        'events':[{'event_id':f'e{i}','source_id':'boundary-control','sequence':i,'timestamp':ts,
                   'kind':'application','parent_event_id':None,'artifact_sha256':'a'*64}
                  for i,ts in enumerate(times)]}


class TimelineBoundaryTests(unittest.TestCase):
    def test_maximum_time_with_uncertainty_is_inconclusive(self):
        r=t.analyze(case(['9999-12-31T23:59:59.999998+00:00','9999-12-31T23:59:59.999999+00:00'],1))
        self.assertEqual(r['status'],'INCONCLUSIVE_ORDER');self.assertEqual(len(r['uncertain_edges']),1)

    def test_minimum_time_with_uncertainty_is_inconclusive(self):
        r=t.analyze(case(['0001-01-01T00:00:00+00:00','0001-01-01T00:00:00.000001+00:00'],1))
        self.assertEqual(r['status'],'INCONCLUSIVE_ORDER')

    def test_one_microsecond_difference_without_uncertainty_is_consistent(self):
        r=t.analyze(case(['9999-12-31T23:59:59.999998+00:00','9999-12-31T23:59:59.999999+00:00'],0))
        self.assertEqual(r['status'],'DECLARED_ORDER_CONSISTENT')

    def test_full_supported_range_has_consistent_declared_order(self):
        r=t.analyze(case(['0001-01-01T00:00:00+00:00','9999-12-31T23:59:59.999999+00:00'],86400000))
        self.assertEqual(r['status'],'DECLARED_ORDER_CONSISTENT')

    def test_reversed_full_range_remains_contradictory(self):
        r=t.analyze(case(['9999-12-31T23:59:59.999999+00:00','0001-01-01T00:00:00+00:00'],86400000))
        self.assertEqual(r['status'],'DECLARED_CONSTRAINT_CONTRADICTION')

    def test_touching_intervals_remain_inconclusive(self):
        r=t.analyze(case(['2026-01-01T00:00:00+00:00','2026-01-01T00:00:00.002000+00:00'],1))
        self.assertEqual(r['status'],'INCONCLUSIVE_ORDER')

    def test_one_microsecond_gap_between_intervals_is_consistent(self):
        r=t.analyze(case(['2026-01-01T00:00:00+00:00','2026-01-01T00:00:00.002001+00:00'],1))
        self.assertEqual(r['status'],'DECLARED_ORDER_CONSISTENT')

    def test_valid_max_journal_timestamp_builds_without_clipping(self):
        raw=b''.join((json.dumps({'__REALTIME_TIMESTAMP':str(n)})+'\n').encode() for n in (j.MAX_US-1,j.MAX_US))
        obj,result,lines,_=j.build(raw,j.metadata('boundary-control',1))
        self.assertEqual(result['status'],'INCONCLUSIVE_ORDER')
        self.assertEqual(obj['sources'][0]['clock_uncertainty_ms'],1)
        self.assertEqual(len(lines),2)
        self.assertEqual(obj['events'][-1]['timestamp'],'9999-12-31T23:59:59.999999+00:00')

    def test_timezone_conversion_outside_utc_range_rejected_with_fixed_code(self):
        for value in ('0001-01-01T00:00:00+01:00','9999-12-31T23:59:59.999999-01:00'):
            with self.subTest(value=value),self.assertRaisesRegex(t.TimelineError,'TIMESTAMP_UTC_RANGE'):
                t.when(value)

    def test_uncertainty_is_not_clipped_at_datetime_maximum(self):
        r=t.analyze(case(['9999-12-30T23:59:59.999999+00:00','9999-12-31T23:59:59.999999+00:00'],86400000))
        self.assertEqual(r['status'],'INCONCLUSIVE_ORDER');self.assertEqual(r['contradictions'],[])


if __name__=='__main__':unittest.main()
