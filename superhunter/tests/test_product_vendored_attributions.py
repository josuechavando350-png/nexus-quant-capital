"""Check the decision surface of the pinned vendored-notice reviewer."""
from copy import deepcopy
import unittest

from superhunter import product_vendored_attributions as d


TREE = ('040000', 'tree', '3' * 40)
FILE = ('100644', 'blob', 'a' * 40)
LINK = ('120000', 'blob', 'b' * 40)
DOC = b'# BSD\n* The `Library A` library located under `thirdparty/a/`.\n# MIT\n* The `B` library located under `extra/b/`.\n'


class VendoredAttributionTests(unittest.TestCase):
    def test_heading_applies_to_following_packages(self):
        groups = d.declarations(DOC)
        self.assertEqual(groups, {'thirdparty/a': {'name': 'Library A', 'declared_group': 'BSD'},
                                  'extra/b': {'name': 'B', 'declared_group': 'MIT'}})
        self.assertEqual(d.declarations(DOC.replace(b'# MIT', b'# PSF'))['extra/b']['declared_group'], 'PSF')

    def test_duplicates_escapes_and_orphan_groups_are_rejected(self):
        for raw in (DOC.replace(b'extra/b/', b'thirdparty/a/'), DOC.replace(b'`B`', b'`library a`'),
                    DOC.replace(b'extra/b/', b'extra/../b/'), DOC + b'# BSD\n', DOC + b'# PSF\n',
                    DOC.replace(b'under `extra/b/`', b'under ?????'), DOC.replace(b'# BSD\n', b'')):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                d.declarations(raw)

    def test_unlisted_vendored_directory_is_actionable_other_files_are_not(self):
        roots = {'thirdparty/a': TREE, 'extra/b': TREE, 'extra/owned': TREE,
                 'thirdparty/added': TREE, 'thirdparty/package_init.py': FILE}
        result = d.review_packages(d.declarations(DOC), roots, {})
        self.assertEqual(result['bundled_roots_without_declaration'], ['thirdparty/added'])
        self.assertEqual(result['disposition_counts'], {'global_declaration_only_no_named_root_notice': 2})

    def test_missing_file_symlink_do_not_receive_tree_credit(self):
        for invalid in (None, FILE, LINK, ('160000', 'commit', 'c' * 40)):
            roots = {'extra/b': TREE}
            if invalid:
                roots['thirdparty/a'] = invalid
            row = d.review_packages(d.declarations(DOC), roots, {})['package_evidence']['thirdparty/a']
            self.assertEqual(row['disposition'], 'declared_directory_missing_or_wrong_mode')
            self.assertIsNone(row['tree'])

    def test_conflicting_or_unrecognized_notice_stays_open(self):
        groups = d.declarations(DOC)
        roots = {'thirdparty/a': TREE, 'extra/b': TREE}
        notes = {'thirdparty/a': [{'text_group': 'BSD'}], 'extra/b': [{'text_group': 'MIT'}]}
        result = d.review_packages(groups, roots, notes)
        self.assertEqual(result['disposition_counts'], {'named_notice_text_consistent_with_group': 2})
        for label in ('undetermined', 'BSD'):
            changed = deepcopy(notes)
            changed['extra/b'].append({'text_group': label})
            self.assertEqual(d.review_packages(groups, roots, changed)['package_evidence']['extra/b']['disposition'],
                             'independent_notice_review_required')

    def test_consistency_requires_both_reviewed_text_phrases(self):
        self.assertEqual(d.text_group(b'Permission is hereby granted, free of charge.'), 'undetermined')
        self.assertEqual(d.text_group(b'BSD OR MIT'), 'undetermined')
        self.assertEqual(d.text_group(b'Redistribution and use in source and binary forms. This software is provided.'), 'BSD')
