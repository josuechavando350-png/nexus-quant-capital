import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import audit_native as a


class AuditTests(unittest.TestCase):
    def test_actual_complete_capture(self):
        report=a.audit(a.HERE/'evidence/pilot')
        self.assertEqual((report['completed_controls'],report['positive_validations'],report['expected_rejections']),(6,3,3))
        self.assertFalse(report['full_bundler_admission_proven'])
        self.assertFalse(report['funding_available_proven'])
        self.assertEqual(report['window_seconds'],[31,31,1])

    def test_rejects_report_admission_overclaim(self):
        original=a.read
        def modified(path):
            x=original(path)
            if path.name=='report.json':x['full_bundler_executed']=True
            return x
        with patch.object(a,'read',side_effect=modified):
            with self.assertRaisesRegex(ValueError,'overclaim'):a.audit(a.HERE/'evidence/pilot')

    def test_rejects_request_signature_change(self):
        original=a.read
        def modified(path):
            x=original(path)
            if path.name=='requests.json':x[3]['request']['params'][0]['data']='0x'
            return x
        with patch.object(a,'read',side_effect=modified):
            with self.assertRaisesRegex(ValueError,'transaction/hash'):a.audit(a.HERE/'evidence/pilot')

    def test_rejects_hash_change(self):
        original=a.read
        def modified(path):
            x=original(path)
            if path.name=='requests.json':x[4]['response_sha256']='0'*64
            return x
        with patch.object(a,'read',side_effect=modified):
            with self.assertRaisesRegex(ValueError,'hash mismatch'):a.audit(a.HERE/'evidence/pilot')

    def test_strict_negative_error_decoding(self):
        p=a.HERE/'evidence/pilot'
        pairs=[('08-debug_traceCall.json',a.decode_deposit_error),('09-debug_traceCall.json',a.decode_budget_error)]
        for filename,decoder in pairs:
            raw=a.read(p/filename)['result']['calls'][-1]['data']
            for bad in ('0x00000000'+raw[10:],raw[:-2],raw+'00'):
                with self.assertRaises(ValueError):decoder(bad)


if __name__=='__main__':unittest.main()
