"""Local disclosure regressions. All markers are synthetic, never real secrets."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import test_bridge as fixtures
from superhunter.bridge import evaluate, render_report
from superhunter.privacy import (MAX_BYTES, POLICY_ID, REPLACEMENT, redact_record,
                                 redact_text, text_export)
from superhunter.safe_io import canonical, strict_json

CANARY = "SYNTHETIC_DO_NOT_USE_SECRET_7319"


class PrivacyTests(unittest.TestCase):
    def setUp(self):
        fixtures.BridgeTests.setUp(self)

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', '-m', 'superhunter', *map(str, args)],
                              cwd=Path(__file__).resolve().parents[2], capture_output=True,
                              text=True, timeout=30)

    def save(self, name, value):
        path = self.root / name
        path.write_bytes(canonical(value))
        return path

    def assert_concealed(self, text, needle=CANARY):
        result = redact_text(text)
        self.assertNotIn(needle, result.text)
        self.assertTrue(result.counts)
        self.assertNotIn(needle, json.dumps(result.summary()))
        self.assertNotIn(hashlib.sha256(needle.encode()).hexdigest(), json.dumps(result.summary()))
        self.assertTrue(result.summary()['manual_review_required'])
        self.assertIs(result.summary()['all_secrets_detected'], False)
        return result

    def test_fuzz_unknown_arguments_are_not_echoed(self):
        result = self.cli('fuzz-lab', '--out', self.root/'fuzz', '--unknown', 'private_key='+CANARY)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(CANARY, result.stdout + result.stderr)

    def test_fuzz_invalid_seed_is_not_echoed(self):
        result = self.cli('fuzz-lab', '--out', self.root/'fuzz', '--seed', 'private_key='+CANARY)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(CANARY, result.stdout + result.stderr)

    def test_sensitive_assignments(self):
        for key in ('api_key', 'API-KEY', 'access_token', 'refresh-token', 'password',
                    'privateKey', 'client_secret', 'secret', 'token'):
            with self.subTest(key=key):
                self.assert_concealed(f'{key}={CANARY}')

    def test_quoted_values_include_spaces_and_escapes(self):
        for raw in (f'"password": "{CANARY} with spaces"',
                    f"password='{CANARY} with spaces'", f'password="{CANARY} \\"escaped\\""'):
            with self.subTest(raw=raw):
                self.assert_concealed(raw)

    def test_bearer_and_basic_headers(self):
        for raw in (f'Authorization: Bearer {CANARY}', f'Proxy-Authorization: Basic {CANARY}',
                    f'diagnostic bearer {CANARY}'):
            with self.subTest(raw=raw): self.assert_concealed(raw)

    def test_session_cookies(self):
        for key in ('Cookie', 'Set-Cookie'):
            self.assert_concealed(f'{key}: sid={CANARY}; Secure; HttpOnly')

    def test_url_credentials_and_query(self):
        result = self.assert_concealed(f'https://alice:{CANARY}@host.invalid/log?api_key={CANARY}&page=2')
        self.assertIn('host.invalid/log?', result.text)
        self.assertIn('page=2', result.text)
        self.assertNotIn('alice', result.text)

    def test_multiple_protocol_userinfo(self):
        for protocol in ('postgresql', 'redis', 'mysql', 'mongodb', 'https'):
            with self.subTest(protocol=protocol):
                self.assert_concealed(f'{protocol}://operator:{CANARY}@host.invalid/db')

    def test_pem_private_blocks(self):
        for label in ('PRIVATE KEY', 'RSA PRIVATE KEY', 'EC PRIVATE KEY', 'OPENSSH PRIVATE KEY', 'ENCRYPTED PRIVATE KEY'):
            with self.subTest(label=label):
                result = self.assert_concealed(f'prefix\n-----BEGIN {label}-----\n{CANARY}\n-----END {label}-----\nsuffix')
                self.assertIn('suffix', result.text)
                self.assertNotIn('BEGIN', result.text)

    def test_truncated_private_key_block_is_not_ignored(self):
        self.assert_concealed(f'-----BEGIN PRIVATE KEY-----\n{CANARY}')

    def test_public_certificate_not_treated_as_private_key(self):
        raw = '-----BEGIN CERTIFICATE-----\nsynthetic-public-data\n-----END CERTIFICATE-----'
        self.assertEqual(redact_text(raw).text, raw)

    def test_recovery_phrase_multword(self):
        for key in ('mnemonic', 'seed phrase', 'recovery_phrase'):
            with self.subTest(key=key):
                self.assert_concealed(f'{key}: alpha beta {CANARY} other synthetic words')

    def test_jwt_shape_without_remote_validation(self):
        token = 'eyJzeW50aGV0aWMiOnRydWV9.c3ludGhldGlj.bm90YXNpZ25hdHVyZQ'
        result = self.assert_concealed('session ' + token, token)
        self.assertEqual(result.counts, {'jwt-shaped': 1})

    def test_redaction_is_idempotent(self):
        for raw in (f'api_key={CANARY}', f'"password": "{CANARY}"',
                    f'Authorization: Bearer {CANARY}', f'https://user:{CANARY}@host.invalid',
                    f'mnemonic: alpha beta {CANARY}', f'Set-Cookie: sid={CANARY}'):
            with self.subTest(raw=raw):
                first = redact_text(raw)
                second = redact_text(first.text)
                self.assertEqual(first.text, second.text)
                self.assertFalse(second.counts)

    def test_overlapping_rules_do_not_leave_secret_fragments(self):
        raw = f'Authorization: Bearer {CANARY} api_key={CANARY}'
        result = self.assert_concealed(raw)
        self.assertEqual(result.text, 'Authorization: ' + REPLACEMENT)

    def test_empty_and_ordinary_text_unchanged(self):
        for raw in ('', 'balance=12; commit=abcdef; INFO: computation completed'):
            self.assertEqual(redact_text(raw).text, raw)
            self.assertFalse(redact_text(raw).counts)

    def test_raw_hash_and_address_preserved(self):
        raw = 'block_hash=0x' + 'a'*64 + '\ntarget=0x' + 'b'*40
        self.assertEqual(redact_text(raw).text, raw)

    def test_unlabelled_secret_is_explicitly_not_guaranteed(self):
        result = redact_text(CANARY)
        self.assertEqual(result.text, CANARY)
        self.assertIs(result.summary()['all_secrets_detected'], False)
        self.assertTrue(result.summary()['manual_review_required'])

    def test_utf8_and_line_endings_preserved(self):
        raw = f'Estado español\r\npassword={CANARY}\r\n結果 completo\r\n'
        result = self.assert_concealed(raw)
        self.assertTrue(result.text.endswith('結果 completo\r\n'))

    def test_oversized_and_invalid_text_rejected(self):
        for raw in ('x'*(MAX_BYTES+1), b'bytes', None, 123):
            with self.subTest(kind=type(raw)), self.assertRaises(ValueError):
                redact_text(raw)

    def test_nested_record_sensitive_fields_and_notes(self):
        original = {'password': {'private': CANARY}, 'nested': [{'notes': f'api_key={CANARY}'}]}
        saved = deepcopy(original)
        clean, summary = redact_record(original)
        self.assertNotIn(CANARY, json.dumps(clean))
        self.assertEqual(original, saved)
        self.assertTrue(summary['redactions_present'])

    def test_public_token_address_not_confused_with_access_token(self):
        source = {'funds_at_risk': {'token': self.token, 'amount_wei': '1000', 'usd': 2}, 'access_token': CANARY}
        clean, _ = redact_record(source)
        self.assertEqual(clean['funds_at_risk'], source['funds_at_risk'])
        self.assertEqual(clean['access_token'], REPLACEMENT)

    def test_record_key_collisions_fail_instead_of_overwriting(self):
        with self.assertRaisesRegex(ValueError, 'collide'):
            redact_record({'api_key=AAA': 1, 'api_key=BBB': 2})

    def test_record_limits_and_types(self):
        deep = 'leaf'
        for _ in range(42): deep = [deep]
        for value in (deep, {1: 'bad key'}, {'value': float('nan')}):
            with self.subTest(value_type=type(value)), self.assertRaises((ValueError, TypeError)):
                redact_record(value)

    def test_export_never_contains_original_values_or_secret_fingerprints(self):
        raw = f'password={CANARY}\n'.encode()
        files = text_export(raw)
        self.assertEqual(set(files), {'redacted.txt', 'redaction.json'})
        receipt = strict_json(files['redaction.json'])
        self.assertFalse(receipt['original_evidence_included'])
        self.assertEqual(receipt['redacted_sha256'], hashlib.sha256(files['redacted.txt']).hexdigest())
        for value in files.values():
            self.assertNotIn(CANARY.encode(), value)
            self.assertNotIn(hashlib.sha256(CANARY.encode()).hexdigest().encode(), value)

    def test_non_utf8_log_rejected_without_lossy_decoding(self):
        with self.assertRaises(ValueError): text_export(b'\xff\xfe\x00')

    def test_report_renderer_filters_notes_and_is_a_review_derivative(self):
        result = evaluate(self.c, self.r, self.a, evidence_root=self.root, report_path='review.md')
        draft = result['draft']
        draft['notes'] = f'Authorization: Bearer {CANARY}'
        report = render_report(draft)
        self.assertNotIn(CANARY, report)
        self.assertIn('Review derivative', report)
        self.assertIn(CANARY, draft['notes'])  # input is not mutated

    def test_cli_error_does_not_echo_unknown_fields(self):
        c = self.save('invalid.json', {'api_key='+CANARY: True})
        r = self.save('r.json', {})
        a = self.save('a.json', {})
        proc = self.cli(c, r, a, '--evidence-root', self.root, '--out', self.root/'reject')
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn(CANARY, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['error_code'], 'INVALID_CONTRACT_OR_ARTIFACT')

    def test_cli_argument_errors_do_not_echo_values(self):
        for args in (("--bad", CANARY), ('local-lab', '--out', self.root/'run', '--rpc', CANARY),
                     ('check', '--out', self.root/'qa', '--bad', CANARY),
                     ('redact-log', self.root/'missing', '--bad', CANARY)):
            with self.subTest(command=args[0]):
                proc = self.cli(*args)
                self.assertNotEqual(proc.returncode, 0)
                self.assertNotIn(CANARY, proc.stdout+proc.stderr)

    def test_cli_review_redacts_notes_without_changing_evidence(self):
        self.r['notes'] = f'password={CANARY}'
        raw = canonical(self.r)
        (self.root/'nqc.json').write_bytes(raw)
        self.a['nqc']['evidence_sha256'] = hashlib.sha256(raw).hexdigest()
        paths = [self.save(name+'.json', v) for name,v in (('c',self.c),('r',self.r),('a',self.a))]
        before = {n: (self.root/n).read_bytes() for n in ('nqc.json','forge.log','r.json')}
        proc = self.cli(*paths, '--evidence-root', self.root, '--out', self.root/'review')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn(CANARY, proc.stdout+proc.stderr)
        for item in (self.root/'review').iterdir(): self.assertNotIn(CANARY.encode(), item.read_bytes())
        decision = strict_json((self.root/'review/decision.json').read_bytes())
        self.assertEqual(decision['status'], 'REVIEW_REQUIRED')
        self.assertTrue(decision['privacy']['redactions_present'])
        self.assertFalse(decision['execution_verified'])
        for name, data in before.items(): self.assertEqual((self.root/name).read_bytes(), data)

    def test_cli_log_export_and_private_permissions(self):
        path = self.root/'input.txt'; raw = f'api_key={CANARY}'.encode(); path.write_bytes(raw)
        out = self.root/'redacted'
        proc = self.cli('redact-log', path, '--out', out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(path.read_bytes(), raw)
        self.assertNotIn(CANARY, proc.stdout+proc.stderr)
        self.assertEqual(out.stat().st_mode & 0o777, 0o700)
        for item in out.iterdir():
            self.assertEqual(item.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(CANARY.encode(), item.read_bytes())
        self.assertTrue(json.loads(proc.stdout)['manual_review_required'])

    def test_cli_log_export_never_overwrites_output(self):
        path = self.root/'input.txt';path.write_text(f'password={CANARY}')
        out = self.root/'output'
        self.assertEqual(self.cli('redact-log',path,'--out',out).returncode, 0)
        marker = (out/'COMPLETE.json').read_bytes()
        self.assertEqual(self.cli('redact-log',path,'--out',out).returncode, 2)
        self.assertEqual((out/'COMPLETE.json').read_bytes(), marker)

    def test_cli_rejects_symlink_input(self):
        (self.root/'raw.txt').write_text(CANARY)
        (self.root/'link.txt').symlink_to(self.root/'raw.txt')
        proc=self.cli('redact-log',self.root/'link.txt','--out',self.root/'symlink')
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn(CANARY, proc.stdout+proc.stderr)
        self.assertFalse((self.root/'symlink').exists())

    def test_cli_errors_hide_sensitive_filenames(self):
        proc = self.cli('redact-log', self.root/CANARY, '--out', self.root/'failure')
        self.assertEqual(proc.returncode, 2)
        self.assertNotIn(CANARY, proc.stdout+proc.stderr)

    def test_redactor_needs_no_network_or_process(self):
        with patch('socket.socket',side_effect=AssertionError('network')), \
             patch('subprocess.run',side_effect=AssertionError('child')):
            result=text_export(f'password={CANARY}'.encode())
            self.assertNotIn(CANARY.encode(), result['redacted.txt'])

    def test_worker_failure_log_is_redacted_without_becoming_pass(self):
        out = self.root/'failed-worker'
        script = """
import sys, unittest
from unittest.mock import patch
from superhunter.quality_worker import main
class SyntheticFailure(unittest.TestCase):
    def runTest(self):
        self.fail('api_key=SYNTHETIC_DO_NOT_USE_SECRET_7319')
suite = unittest.TestSuite([SyntheticFailure()])
with patch('unittest.TestLoader.discover', return_value=suite):
    raise SystemExit(main())
"""
        proc = subprocess.run([sys.executable, '-B', '-c', script, str(out)],
                              cwd=Path(__file__).resolve().parents[2], capture_output=True,
                              text=True, timeout=30)
        self.assertEqual(proc.returncode, 1, proc.stdout+proc.stderr)
        self.assertNotIn(CANARY, proc.stdout+proc.stderr)
        receipt = strict_json((out/'receipt.json').read_bytes())
        log = (out/'tests.log').read_text()
        self.assertEqual(receipt['failures'], 1)
        self.assertEqual(receipt['tests'][0]['outcome'], 'FAIL')
        self.assertTrue(receipt['log_privacy']['redactions_present'])
        self.assertNotIn(CANARY, log)
        self.assertIn('FAILED', log)

    def test_export_metadata_does_not_claim_safe_to_publish(self):
        files = text_export(b'ordinary log without recognized credentials')
        receipt = strict_json(files['redaction.json'])
        self.assertEqual(receipt['status'], 'REDACTED_REVIEW_ONLY')
        self.assertFalse(receipt['redactions_present'])
        self.assertFalse(receipt['all_secrets_detected'])
        self.assertTrue(receipt['manual_review_required'])

    def test_qa_manifest_and_catalog_connect_privacy(self):
        from superhunter import quality
        self.assertEqual(quality.validate_components(quality.source_snapshot()), [])
        self.assertIn('privacy',quality.COMPONENTS['transport']['depends'])
        self.assertIn('privacy',quality.COMPONENTS['quality']['depends'])
        item=quality.catalog()['items'][28]
        self.assertEqual(item['status'],'PARTIAL')
        self.assertEqual(item['components'],['privacy'])


if __name__ == '__main__':
    unittest.main()
