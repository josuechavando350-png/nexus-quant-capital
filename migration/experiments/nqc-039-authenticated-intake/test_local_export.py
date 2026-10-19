"""Ensure local export never persists a reflected API credential."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_export import public_response_fetch


class ExportTests(unittest.TestCase):
    def test_credential_echo_is_rejected_before_persistence(self):
        secret = 'synthetic_testing_credential'
        fetch = public_response_fetch(lambda _: {'result': {'extra': secret}}, secret, ValueError)
        with self.assertRaisesRegex(ValueError, 'not persisted'):
            fetch({})

    def test_public_response_is_unchanged(self):
        response = {'jsonrpc': '2.0', 'id': 1, 'result': '0x1237'}
        fetch = public_response_fetch(lambda _: response, 'synthetic_testing_credential', ValueError)
        self.assertIs(fetch({}), response)


if __name__ == '__main__':
    unittest.main()
