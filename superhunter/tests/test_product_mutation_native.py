"""Controlled receipt corruptions; native generation and replay are recorded separately."""
import copy
from pathlib import Path
import unittest

from superhunter import product_mutation_native as mutation
from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import sha
from superhunter.safe_io import canonical


SOURCE = b'int credited(int balance, int deposit) {\n    return balance + deposit;\n}\n'
TARGET = Path('/owned/arithmetic.cpp')


def sample(profile):
    offset = SOURCE.index(b'+')
    results = []
    for number, operator in enumerate(('%', '*', '-', '/'), 1):
        survived = profile == 'weak' and operator == '*'
        changed = SOURCE[:offset] + operator.encode() + SOURCE[offset+1:]
        proof = canonical({'compiled': True, 'exit_code': 0 if survived else 1,
                           'source_sha256': sha(changed)}).decode()
        results.append({'mutant': {'id': number, 'target_id': 1, 'mutation_slug': 'AOS',
                        'byte_offset': offset, 'line_offset': 1, 'old_text': '+', 'new_text': operator},
                        'target': {'id': 1, 'path': TARGET.name, 'file_hash': sha(SOURCE), 'language': 'cpp'},
                        'outcome': {'mutant_id': number, 'status': 'Uncaught' if survived else 'TestFail',
                                    'output': 'STDOUT:\n'+proof+'\n\nSTDERR:\n',
                                    'time': '2026-11-21T00:00:00Z', 'duration_ms': 5}})
    return {'results': results}


class MutationNativeControls(unittest.TestCase):
    def validate(self, record, profile='strong'):
        return mutation.normalized_campaign(record, SOURCE, TARGET, profile)

    def test_strong_assertions_kill_four_but_weak_assertions_retain_multiplication(self):
        strong = self.validate(sample('strong'))
        weak = self.validate(sample('weak'), 'weak')
        self.assertEqual((strong['generated'], strong['killed'], strong['survivors']), (4, 4, []))
        self.assertEqual((weak['generated'], weak['killed'], weak['survivors']), (4, 3, ['*']))

    def test_erased_weak_survivor_is_rejected(self):
        report = sample('weak')
        report['results'][1]['outcome']['status'] = 'TestFail'
        with self.assertRaises(EvidenceError):
            self.validate(report, 'weak')

    def test_compile_errors_cannot_be_counted_as_killed_mutants(self):
        for payload in ({'compiled': False}, {'compiled': True, 'exit_code': 70, 'source_sha256': '0'*64}):
            report = sample('strong')
            report['results'][0]['outcome']['output'] = 'STDOUT:\n'+canonical(payload).decode()+'\n\nSTDERR:\n'
            with self.subTest(payload=payload), self.assertRaises(EvidenceError):
                self.validate(report)

    def test_timeouts_and_skips_are_not_successful_assertion_failures(self):
        for status in ('Timeout', 'Skipped'):
            report = sample('strong')
            report['results'][0]['outcome']['status'] = status
            with self.subTest(status=status), self.assertRaises(EvidenceError):
                self.validate(report)

    def test_mutation_must_name_the_checked_source_location_and_hash(self):
        alterations = [('mutant', 'byte_offset', 0), ('mutant', 'old_text', '*'),
                       ('target', 'file_hash', '0'*64), ('target', 'path', '/different/arithmetic.cpp'),
                       ('target', 'language', 'rust'), ('outcome', 'mutant_id', 100)]
        for section, field, replacement in alterations:
            report = sample('strong')
            report['results'][0][section][field] = replacement
            with self.subTest(field=field), self.assertRaises(EvidenceError):
                self.validate(report)

    def test_generated_replacements_cannot_be_missing_or_duplicated(self):
        original = sample('strong')
        missing = copy.deepcopy(original)
        missing['results'].pop()
        duplicated = copy.deepcopy(original)
        duplicated['results'][-1] = copy.deepcopy(duplicated['results'][0])
        for report in (missing, duplicated):
            with self.assertRaises(EvidenceError):
                self.validate(report)

    def test_compilation_and_assertion_flags_require_exact_json_types(self):
        for payload in ({'compiled': 1, 'exit_code': 0, 'source_sha256': sha(SOURCE)},
                        {'compiled': True, 'exit_code': False, 'source_sha256': sha(SOURCE)}):
            with self.assertRaises(EvidenceError):
                mutation.worker_result(canonical(payload), SOURCE, 0)

    def test_mutant_replay_must_match_the_actual_mutated_bytes(self):
        report = sample('strong')
        report['results'][0]['outcome']['output'] = 'STDOUT:\n'+canonical(
            {'compiled': True, 'exit_code': 1, 'source_sha256': sha(SOURCE)}).decode()+'\n\nSTDERR:\n'
        with self.assertRaises(EvidenceError):
            self.validate(report)

    def test_compiler_diagnostics_cannot_hide_in_native_stdout_wrapper(self):
        report = sample('strong')
        report['results'][0]['outcome']['output'] += 'compiler error\n'
        with self.assertRaises(EvidenceError):
            self.validate(report)


if __name__ == '__main__':
    unittest.main()
