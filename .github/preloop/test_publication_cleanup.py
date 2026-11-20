"""Failure cleanup must retain exact revision and check ownership."""
import copy
import unittest
from unittest.mock import patch

import publisher
from review_contract import InvalidReview


class PublicationCleanupTests(unittest.TestCase):
    def setUp(self):
        self.binding = {'repository': 'example/repo'}
        self.completion = {'pr_number': 7, 'head_sha': 'a' * 40, 'base_sha': 'b' * 40}
        self.claim = 'c' * 64
        self.marker = '<!-- briar-preloop:execution:' + self.claim + ' -->'
        self.check = dict(id=11, head_sha='a' * 40, name='Preloop review',
            app={'slug': 'github-actions'}, external_id='briar-preloop:' + self.claim,
            output={'text': self.marker})
        self.writes = []
        self.fail_patch = False
        self.bad_readback = False

    def github(self, path, method='GET', body=None):
        if method == 'PATCH':
            self.writes.append((path, body))
            if self.fail_patch:
                raise OSError('synthetic patch failure')
            self.check.update(body)
        actual = copy.deepcopy(self.check)
        if self.bad_readback and self.writes:
            actual['external_id'] = 'another-owner'
        return actual

    def run_cleanup(self, stale=False, superseded=False):
        with patch.object(publisher.runtime, 'current_pr',
                          side_effect=InvalidReview('stale') if stale else None), \
             patch.object(publisher, 'no_supersession',
                          side_effect=InvalidReview('superseded') if superseded else None), \
             patch.object(publisher.runtime, 'verify_check_url'):
            return publisher.cleanup_failed_publication(self.github, self.binding,
                'synthetic-token', self.completion, 11, self.claim, self.marker,
                'https://github.com/example/repo/actions/runs/12')

    def test_current_owned_check_is_corrected_and_read_back(self):
        self.assertEqual(self.run_cleanup(), {'check': 'failure_confirmed'})
        self.assertEqual(len(self.writes), 1)

    def test_changed_revision_or_newer_execution_denies_writes(self):
        for params in [{'stale': True}, {'superseded': True}]:
            with self.subTest(params=params):
                self.assertEqual(self.run_cleanup(**params)['check'], 'not_attempted')
                self.assertEqual(self.writes, [])

    def test_wrong_check_identity_denies_writes(self):
        original = copy.deepcopy(self.check)
        for field, value in [('id', 99), ('head_sha', 'd' * 40),
                ('name', 'other'), ('app', {'slug': 'other'}),
                ('external_id', 'other'), ('output', {'text': 'other'})]:
            with self.subTest(field=field):
                self.check = copy.deepcopy(original)
                self.check[field] = value
                self.assertEqual(self.run_cleanup()['check'], 'not_attempted')
                self.assertEqual(self.writes, [])

    def test_patch_failure_is_unconfirmed_not_success(self):
        self.fail_patch = True
        self.assertEqual(self.run_cleanup(), {'check': 'unconfirmed', 'check_error': 'OSError'})

    def test_changed_readback_is_unconfirmed(self):
        self.bad_readback = True
        self.assertEqual(self.run_cleanup()['check'], 'unconfirmed')


if __name__ == '__main__':
    unittest.main()
