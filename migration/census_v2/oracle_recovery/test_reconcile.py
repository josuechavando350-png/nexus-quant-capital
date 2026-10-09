"""Real captured prices and adversarial tests of material admission boundaries."""
import copy
import gzip
import json
import os
from pathlib import Path
import unittest
import zipfile

import reconcile as r
from collect import canon, calldata, sha


class Checks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.primary = Path(os.environ['NQC_ORACLE_PRIMARY_ARCHIVE'])
        cls.d08 = Path(os.environ['NQC_ORACLE_D08'])
        cls.pilot = Path(os.environ['NQC_ORACLE_PILOT'])
        cls.partial = Path(os.environ['NQC_ORACLE_PARTIAL'])
        cls.data = calldata(json.loads((cls.pilot / 'assets.json').read_bytes()))
        path = cls.pilot / 'capture-25880316-25881315.jsonl.gz'
        cls.record = json.loads(gzip.decompress(path.read_bytes()).splitlines()[0])
        with zipfile.ZipFile(cls.primary) as z:
            rows = r.observations(json.loads(z.read('drpc/chunk-25880316-25880365.json')))
        cls.expected = {a['block_number']: (b['parent_hash'], a['prices']) for a, b in zip(rows, rows[1:])}

    def modified(self, field, change):
        record = copy.deepcopy(self.record)
        document = json.loads(record[field + '_body'])
        change(document)
        record[field + '_body'] = json.dumps(document, separators=(',', ':'))
        record[field + '_sha256'] = sha(record[field + '_body'].encode())
        return record

    def rejected(self, record, reason):
        with self.assertRaisesRegex(ValueError, reason):
            r.validate_record(record, self.expected, self.data, set())

    def test_actual_complete_pilot_and_partial_stop(self):
        report = r.reconcile(self.primary, self.d08, [self.pilot, self.partial])
        self.assertEqual(report['new_direct_observed_blocks'], 2080)
        self.assertEqual(report['matched_new_price_values'], 139360)
        self.assertEqual(report['secondary_union_blocks'], 5170)
        self.assertEqual(report['secondary_missing_blocks'], 209866)
        self.assertEqual(len(report['failed_requests']), 1)
        for field in ['full_secondary_price_coverage', 'full_requested_acquisition_complete',
                      'historical_decision_time_observation', 'census_certified', 'gas_spent']:
            self.assertIs(report[field], False)
        self.assertEqual(report['preflight_diagnostics']['header_basefee_wei'], 38880936)

    def test_missing_response(self):
        self.rejected(self.modified('response', lambda d: d.pop()), 'batch cardinality')

    def test_duplicate_response(self):
        self.rejected(self.modified('response', lambda d: d.__setitem__(0, d[1])), 'identity/duplicate')

    def test_boolean_identity(self):
        self.rejected(self.modified('response', lambda d: d[0].__setitem__('id', True)), 'identity/duplicate')

    def test_changed_price(self):
        def change(d):
            v = d[0]['result']
            d[0]['result'] = v[:-64] + f'{int(v[-64:], 16) + 1:064x}'
        self.rejected(self.modified('response', change), 'price vector mismatch')

    def test_incomplete_price_vector(self):
        self.rejected(self.modified('response', lambda d: d[0].__setitem__('result', d[0]['result'][:-64])), 'ABI shape')

    def test_noncanonical_request(self):
        self.rejected(self.modified('request', lambda d: d[0]['params'][1].__setitem__('requireCanonical', False)), 'canonicality')

    def test_substituted_hash(self):
        self.rejected(self.modified('request', lambda d: d[0]['params'][1].__setitem__('blockHash', '0x' + '00' * 32)), 'canonicality')

    def test_substituted_calldata(self):
        self.rejected(self.modified('request', lambda d: d[0]['params'][0].__setitem__('data', '0x')), 'calldata')

    def test_reordered_request_sequence(self):
        self.rejected(self.modified('request', lambda d: d.reverse()), 'request sequence')

    def test_unknown_response_block(self):
        self.rejected(self.modified('response', lambda d: d[0].__setitem__('id', 1)), 'block identity')

    def test_future_send_time(self):
        record = copy.deepcopy(self.record)
        record['sent_at'] = '2026-10-10T00:00:00+00:00'
        self.rejected(record, 'chronology')

    def test_body_changed_without_new_digest(self):
        record = copy.deepcopy(self.record)
        record['response_body'] += ' '
        self.rejected(record, 'body commitment')

    def test_rate_error_not_admitted_as_prices(self):
        record = copy.deepcopy(self.record)
        record['http_status'] = 429
        record['transport_error'] = 'HTTP Error 429: Too Many Requests'
        self.rejected(record, 'unsuccessful transport')

    def test_already_observed_block(self):
        with self.assertRaisesRegex(ValueError, 'duplicate requested block'):
            r.validate_record(self.record, self.expected, self.data, {25880316})


if __name__ == '__main__':
    unittest.main()
