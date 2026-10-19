"""Offline regressions. All transports and all full-eight responses are synthetic."""
import copy
import json
import multiprocessing
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import session as s

KEY = 'synthetic_testing_key_never_a_real_credential'


def valid_prefix(operation):
    number = operation['request']['id']
    results = {1: '0x1237',
               2: s.t.v.read_json(s.t.v.ROOT / 'inputs/parent-header.json')['result'],
               3: {'address': s.t.v.PRIORITY_ADDRESS, 'nonce': '0x0',
                   'balance': '0x0', 'storageProof': []}}
    return {'jsonrpc': '2.0', 'id': number, 'result': results[number]}


def hold_lock(directory, pipe):
    with s.locked(Path(directory)):
        pipe.send('locked')
        pipe.recv()


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.directory = s.initialize(self.base / 'session')

    def journal(self):
        return s.t.v.read_json(self.directory / 'SESSION.json')

    def rewrite(self, journal):
        s.atomic_bytes(self.directory / 'SESSION.json', s.encoded(journal))

    def test_original_fresh_directories_can_repeat_more_than_eight_attempts(self):
        # Demonstrates a per-invocation limit, not a provider exploit or real RPC.
        fake = Mock(side_effect=s.t.v.ValidationError('HTTP 429; no retry'))
        for index in range(9):
            s.t.intake.execute(fake, self.base / f'old-run-{index}')
        self.assertEqual(fake.call_count, 9)
        self.assertEqual([call.args[0]['request']['id'] for call in fake.call_args_list], [1] * 9)

    def test_restart_after_failure_never_retries(self):
        fetch = Mock(side_effect=s.t.v.ValidationError('HTTP 429; no retry'))
        for _ in range(9):
            result = s.run(self.directory, fetch, secret=KEY, max_new_requests=8)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(result['status'], 'BLOCKED_REJECTED_STEP')
        self.assertEqual(result['attempt_slots_reserved'], 1)
        self.assertFalse(result['gates']['commercial_admission'])

    def test_real_adapter_integration_uses_fixed_wire_plan_and_stops_at_bad_proof(self):
        replies = []
        for operation in s.t.intake.plan()[:3]:
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = s.encoded(valid_prefix(operation))
            replies.append(response)
        opener = Mock()
        opener.open.side_effect = replies
        with patch.object(s.t.urllib.request, 'build_opener', return_value=opener):
            first = s.collect(KEY, self.directory)
            second = s.collect(KEY, self.directory)
        self.assertEqual(first, second)
        self.assertEqual(first['responses_verified'], 2)
        self.assertEqual(opener.open.call_count, 3)
        actual = [json.loads(call.args[0].data) for call in opener.open.call_args_list]
        self.assertEqual(actual, [op['request'] for op in s.t.wire_plan()[:3]])
        self.assertTrue(all(call.args[0].get_header('X-token') == KEY for call in opener.open.call_args_list))
        self.assertNotIn(KEY.encode(), b''.join(p.read_bytes() for p in self.directory.iterdir()))

    def test_incremental_runs_reuse_verified_prefix_without_network_repeats(self):
        fetch = Mock(side_effect=valid_prefix)
        first = s.run(self.directory, fetch, secret=KEY, max_new_requests=1)
        second = s.run(self.directory, fetch, secret=KEY, max_new_requests=1)
        third = s.run(self.directory, fetch, secret=KEY, max_new_requests=8)
        again = s.run(self.directory, fetch, secret=KEY, max_new_requests=8)
        self.assertEqual([call.args[0]['request']['id'] for call in fetch.call_args_list], [1, 2, 3])
        self.assertEqual(first['responses_verified'], 1)
        self.assertEqual(second['responses_verified'], 2)
        self.assertEqual(third['responses_verified'], 2)
        self.assertEqual(again, third)
        self.assertTrue((self.directory / '03-priority_proof.json').exists())
        self.assertEqual(self.journal()['entries'][-1]['status'], 'rejected')

    def test_reservation_is_on_disk_before_fetch_and_crash_is_ambiguous(self):
        def interrupted(operation):
            self.assertEqual(self.journal()['entries'], [{'id': 1, 'status': 'reserved'}])
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            s.run(self.directory, interrupted, secret=KEY, max_new_requests=8)
        fetch = Mock()
        result = s.run(self.directory, fetch, secret=KEY, max_new_requests=8)
        fetch.assert_not_called()
        self.assertEqual(result['status'], 'BLOCKED_AMBIGUOUS_ATTEMPT')
        self.assertEqual(result['attempt_slots_reserved'], 1)

    def test_received_response_survives_interruption_and_is_revalidated_offline(self):
        with patch.object(s.t.intake, 'validate_step', side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            s.run(self.directory, valid_prefix, secret=KEY, max_new_requests=1)
        self.assertEqual(self.journal()['entries'][0]['status'], 'received')
        fetch = Mock()
        result = s.run(self.directory, fetch)
        fetch.assert_not_called()
        self.assertEqual(result['responses_verified'], 1)
        self.assertEqual(self.journal()['entries'][0]['status'], 'verified')

    def test_response_saved_before_journal_commit_never_triggers_retry(self):
        original = s.atomic_bytes
        def stop_before_received(path, raw):
            if path.name == 'SESSION.json' and b'"status":"received"' in raw:
                raise KeyboardInterrupt
            original(path, raw)
        with patch.object(s, 'atomic_bytes', side_effect=stop_before_received), self.assertRaises(KeyboardInterrupt):
            s.run(self.directory, valid_prefix, secret=KEY, max_new_requests=1)
        self.assertTrue((self.directory / '01-chain.json').exists())
        fetch = Mock()
        result = s.run(self.directory, fetch, secret=KEY, max_new_requests=8)
        fetch.assert_not_called()
        self.assertEqual(result['status'], 'BLOCKED_AMBIGUOUS_ATTEMPT')

    def test_failed_durable_reservation_prevents_transport(self):
        fetch = Mock()
        with patch.object(s, 'atomic_bytes', side_effect=OSError('synthetic disk failure')), self.assertRaises(OSError):
            s.run(self.directory, fetch, secret=KEY, max_new_requests=8)
        fetch.assert_not_called()
        self.assertEqual(self.journal()['entries'], [])

    def test_changed_or_missing_saved_response_stops_before_any_new_request(self):
        s.run(self.directory, valid_prefix, secret=KEY, max_new_requests=1)
        path = self.directory / '01-chain.json'
        for raw in [b'{"jsonrpc":"2.0","id":1,"result":"0x1"}', None]:
            if raw is None:
                path.unlink()
            else:
                path.write_bytes(raw)
            fetch = Mock()
            with self.assertRaises(s.t.v.ValidationError):
                s.run(self.directory, fetch, secret=KEY, max_new_requests=8)
            fetch.assert_not_called()

    def test_self_consistent_response_digest_does_not_bypass_actual_validation(self):
        s.run(self.directory, valid_prefix, secret=KEY, max_new_requests=1)
        raw = s.encoded({'jsonrpc': '2.0', 'id': 1, 'result': '0x1'})
        (self.directory / '01-chain.json').write_bytes(raw)
        journal = self.journal()
        journal['entries'][0]['response_sha256'] = s.digest(raw)
        self.rewrite(journal)
        fetch = Mock()
        report = s.run(self.directory, fetch, secret=KEY, max_new_requests=8)
        self.assertEqual(report['status'], 'BLOCKED_REJECTED_STEP')
        fetch.assert_not_called()

    def test_code_binding_or_plan_change_blocks_before_fetch(self):
        for field in ['files', 'specification_sha256']:
            original = self.journal()
            changed = copy.deepcopy(original)
            changed['binding'][field] = {} if field == 'files' else '0' * 64
            self.rewrite(changed)
            fetch = Mock()
            with self.assertRaisesRegex(s.t.v.ValidationError, 'binding mismatch'):
                s.run(self.directory, fetch, secret=KEY, max_new_requests=8)
            fetch.assert_not_called()
            self.rewrite(original)

    def test_missing_journal_is_not_reinitialized(self):
        (self.directory / 'SESSION.json').unlink()
        fetch = Mock()
        with self.assertRaises(s.t.v.ValidationError):
            s.run(self.directory, fetch, secret=KEY, max_new_requests=8)
        with self.assertRaises(FileExistsError):
            s.initialize(self.directory)
        fetch.assert_not_called()
        self.assertFalse((self.directory / 'SESSION.json').exists())

    def test_second_process_cannot_use_locked_session(self):
        context = multiprocessing.get_context('fork')
        parent, child = context.Pipe()
        process = context.Process(target=hold_lock, args=(str(self.directory), child))
        process.start()
        try:
            self.assertTrue(parent.poll(5))
            self.assertEqual(parent.recv(), 'locked')
            fetch = Mock()
            with self.assertRaisesRegex(s.t.v.ValidationError, 'already in use'):
                s.run(self.directory, fetch, secret=KEY, max_new_requests=8)
            fetch.assert_not_called()
        finally:
            parent.send('release')
            process.join(5)
            if process.is_alive():
                process.terminate()
                process.join()
            parent.close()
            child.close()
        self.assertEqual(process.exitcode, 0)

    def test_secret_echo_and_error_message_never_reach_disk(self):
        fetch = Mock(return_value={'jsonrpc': '2.0', 'id': 1, 'result': '0x1237', 'extra': KEY})
        result = s.run(self.directory, fetch, secret=KEY, max_new_requests=8)
        self.assertEqual(result['status'], 'BLOCKED_REJECTED_STEP')
        self.assertFalse((self.directory / '01-chain.json').exists())
        self.assertNotIn(KEY.encode(), b''.join(p.read_bytes() for p in self.directory.iterdir()))
        other = s.initialize(self.base / 'error-session')
        throwing = Mock(side_effect=RuntimeError(KEY))
        s.run(other, throwing, secret=KEY, max_new_requests=8)
        self.assertNotIn(KEY.encode(), b''.join(p.read_bytes() for p in other.iterdir()))

    def test_eight_attempt_limit_and_no_ninth_after_completion_control_only(self):
        # Validator/report mocks isolate accounting; these are NOT synthetic proofs
        # accepted by the real verifier, and this test asserts no historical claim.
        fetch = Mock(side_effect=lambda op: {'jsonrpc': '2.0', 'id': op['request']['id'], 'result': {}})
        fake_report = {'status': 'SYNTHETIC_CONTROL_FLOW_ONLY', 'gates': s.t.v.closed_gates()}
        with patch.object(s.t.intake, 'validate_step'), patch.object(s.t.intake, 'result_report', return_value=fake_report):
            for _ in range(10):
                report = s.run(self.directory, fetch, secret=KEY, max_new_requests=1)
        self.assertEqual(fetch.call_count, 8)
        self.assertEqual(report['session']['attempt_slots_reserved'], 8)
        self.assertEqual(report['session']['remaining_attempt_slots'], 0)
        self.assertFalse(report['gates']['commercial_admission'])

    def test_invalid_budget_and_journal_are_rejected_before_fetch(self):
        fetch = Mock()
        for value in [-1, 9, True, '8']:
            with self.assertRaises(s.t.v.ValidationError):
                s.run(self.directory, fetch, secret=KEY, max_new_requests=value)
        journal = self.journal()
        journal['entries'] = [{'id': 1, 'status': 'reserved'}, {'id': 2, 'status': 'reserved'}]
        self.rewrite(journal)
        with self.assertRaises(s.t.v.ValidationError):
            s.run(self.directory, fetch, secret=KEY, max_new_requests=8)
        fetch.assert_not_called()

    def test_default_is_offline_and_does_not_create_a_session(self):
        fetch = Mock()
        report = s.run(self.directory, fetch)
        self.assertEqual(report['attempt_slots_reserved'], 0)
        fetch.assert_not_called()
        missing = self.base / 'missing-session'
        with self.assertRaises(s.t.v.ValidationError):
            s.run(missing)
        self.assertFalse(missing.exists())


if __name__ == '__main__':
    unittest.main()
