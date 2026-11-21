"""Exercise source and functional accounting on selective runs and published historical sessions."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from superhunter.product_batches import coverage
from superhunter.product_component_controls import validate_group
from superhunter.product_matrix import build
from superhunter.product_reasoning import EvidenceError
from superhunter.product_review import ROOT
from superhunter.safe_io import canonical
from superhunter.tools.verify_review_115 import negative_controls, response_keys, unpack, verify

SUPPLY = ROOT/'superhunter/product_supply'


def archive(number):
    return unpack((SUPPLY/f'review-{number}-session.json').read_bytes())


def documents(raw):
    return {k: json.loads(line) for k, line in zip(response_keys(raw), raw.splitlines(), strict=True)}


def indexed_report(active):
    docs = documents(archive(117))
    repos = {name.casefold(): r for name, r in docs.items() if isinstance(r, dict) and 'catalog_id' in r}
    index = SimpleNamespace(repos=repos, lookup=lambda name: repos[name.casefold()],
                            source_inventory=docs['source-inventory'], root_declarations=docs['root-declarations'],
                            owned_source_checks=docs['owned-source-checks'], census_header=docs['census-header'],
                            geth_header=docs['geth-census'], source_references=docs['source-references'],
                            score_comparison=docs['score-comparison'], fork_headers=docs['fork-headers'])
    # Replay stored supply results solely to exercise the selection/accounting boundary.
    observations = json.loads((SUPPLY/'trust-batch-receipt.json').read_bytes()) if active else {}
    if active:
        for name, receipt in validate_group('supply', observations).items():
            index.lookup(name)['component_control_receipt'] = receipt
    docs['integration-coverage'] = coverage(index)
    docs['integration-matrix'] = build(index)
    docs['component-controls'] = {'requested': ['supply'], 'blocked': {} if active else {'supply': 'test absence'},
                                 'observations': observations, 'digest_corroboration': {}}
    return docs


def transcript(docs):
    return b''.join(canonical(v) for v in docs.values())


class SourceAccounting(unittest.TestCase):
    def test_all_published_excerpts_survive_selective_and_blocked_domains(self):
        for active in (False, True):
            with self.subTest(active=active):
                docs = indexed_report(active)
                matrix = docs['integration-matrix']
                self.assertEqual([r['id'] for r in matrix['published_excerpts']], [1, 10, 169, 179, 191, 194, 195, 197])
                self.assertEqual(matrix['sources'], {'complete':153, 'excerpt':8, 'metadata':39})
                self.assertEqual(matrix['pending_by_source']['excerpt'], 6)
                for number in (1, 10, 169, 194, 195, 197):
                    row = matrix['rows'][number-1]
                    self.assertEqual((row['source'], row['session']), ('excerpt', 'pending'))
                self.assertEqual(verify(transcript(docs))['sources'], matrix['sources'])

    def test_published_legacy_acceptances_keep_their_historical_scope(self):
        for number, expected in ((115,58),(117,59)):
            raw = archive(number)
            self.assertEqual(verify(raw)['session'], expected)
            self.assertEqual(verify(raw)['sources'], {'complete':153, 'excerpt':2, 'metadata':45})
            self.assertEqual(len(negative_controls(raw)), 6)

    def test_rejects_profile_downgrade_and_swapped_excerpt_claim(self):
        docs = indexed_report(False)
        selected = docs['integration-matrix'].pop('published_excerpts')
        with self.assertRaisesRegex(EvidenceError, 'missing its published excerpt'):
            verify(transcript(docs))
        docs['integration-matrix']['published_excerpts'] = selected
        selected[0]['blob'] = selected[1]['blob']
        with self.assertRaisesRegex(EvidenceError, 'inventory differs'):
            verify(transcript(docs))

    def test_all_totals_are_checked_independently(self):
        docs = documents(archive(117))
        matrix = docs['integration-matrix']
        for key, value in matrix.items():
            if key == 'rows':
                continue
            with self.subTest(key=key):
                prior = matrix[key]
                matrix[key] = {'forged': 1} if isinstance(value, dict) else -1
                with self.assertRaisesRegex(EvidenceError, 'claimed totals'):
                    verify(transcript(docs))
                matrix[key] = prior

    def test_checked_out_scope_cannot_be_assigned_to_an_excerpt(self):
        docs = indexed_report(True)
        docs['integration-matrix']['rows'][0]['verification_scope'] = 'checked_out_contents'
        with self.assertRaisesRegex(EvidenceError, 'scope or inventory'):
            verify(transcript(docs))

    def test_refuses_forged_commercial_clearance(self):
        docs = indexed_report(True)
        docs['integration-matrix']['rows'][0]['commercial_review'] = 'approved'
        with self.assertRaisesRegex(EvidenceError, 'commercial license'):
            verify(transcript(docs))

    def test_selective_controls_check_only_real_selected_producers(self):
        for active in (True, False):
            with self.subTest(active=active):
                raw = transcript(indexed_report(active))
                controls = negative_controls(raw)
                self.assertEqual('changed_group_result' in controls, active)
                self.assertIn('erased_excerpt_inventory', controls)
                self.assertIn('changed_role_totals', controls)

    def test_complete_source_claim_cannot_override_the_pinned_inventory(self):
        docs = indexed_report(False)
        source = docs['usestrix/strix']['source_inventory']
        donor = docs['foundry-rs/foundry']['source_inventory']
        source['contents'] = donor['contents']
        source['evidence'] = 'local_git_tree'
        with self.assertRaisesRegex(EvidenceError, 'source revisions or checkout inventory'):
            verify(transcript(docs))
