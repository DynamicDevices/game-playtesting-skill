"""Finalizer entry-point regressions with synthetic isolated APIs."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import finalize
from review_contract import InvalidReview


class FinalizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.binding = dict(repository='example/repository', repository_id=42)
        self.receipt = dict(execution_id='487d988a-53ad-4f5d-8b84-d77bb733676f',
            head_sha='a' * 40, base_sha='b' * 40, result_sha256='c' * 64,
            claim_sha256='d' * 64, state='success', check_id=11,
            review_url='https://github.com/example/repository/pull/7#review-22')
        self.completion = dict(self.receipt, pr_number=7, status='SUCCEEDED', result_ready=True)
        self.rows, self.calls = [], []
        self.intent = dict(publisher_run_id='12', finalizer_run_id='13',
                           publication_receipt=self.receipt, completion=self.completion)
        self.event = Path(self.temp.name) / 'event.json'
        self.event.write_text(json.dumps(dict(action='completed', repository={'id': 42},
            workflow_run={'id': 12, 'path': '.github/workflows/preloop-review-publish.yml'})))
        env = patch.dict(os.environ, GITHUB_EVENT_PATH=str(self.event), GITHUB_EVENT_NAME='workflow_run',
                         GITHUB_RUN_ID='13', GITHUB_RUN_ATTEMPT='1', RUNNER_TEMP=self.temp.name,
                         PRELOOP_CI_TOKEN='synthetic-not-a-key')
        env.start()
        self.addCleanup(env.stop)

    def github(self, path, method='GET', body=None):
        self.calls.append((path, method, body))
        if method == 'PATCH':
            self.check = dict(body, head_sha='a' * 40, external_id='briar-preloop:' + 'd' * 64,
                              app={'slug': 'github-actions'})
            return self.check
        return self.check

    def run_phase(self, entry):
        with patch.object(finalize.runtime, 'context', return_value=(self.binding, {}, self.github)), \
             patch.object(finalize, 'producer', return_value=('12', self.receipt, self.completion)), \
             patch.object(finalize.runtime, 'github_pages', return_value=self.rows), \
             patch.object(finalize.runtime, 'artifact', return_value=self.intent), \
             patch.object(finalize.runtime, 'current_pr'), \
             patch.object(finalize.publisher, 'no_supersession'), \
             patch.object(finalize.runtime, 'commit_status') as status, \
             patch.object(finalize.runtime, 'output'):
            entry()
            return status

    def test_prepare_only_saves_intent_and_does_not_release_green(self):
        status = self.run_phase(finalize.prepare)
        self.assertFalse(self.calls)
        status.assert_not_called()
        saved = json.loads((Path(self.temp.name) / 'preloop-finalize/receipt.json').read_text())
        self.assertEqual(saved, self.intent)

    def test_release_requires_own_unique_durable_intent(self):
        name = finalize.intent_name('12', self.receipt)
        self.rows = [dict(name=name, expired=False, workflow_run={'id': 13})]
        status = self.run_phase(finalize.release)
        status.assert_called_once()
        self.assertEqual(self.check['conclusion'], 'success')
        self.assertIn('briar-preloop-finalized:12:13:', self.check['output']['text'])
        self.assertTrue(all(method in ['GET', 'PATCH'] for _, method, _ in self.calls))
        self.assertTrue(all('/check-runs/11' in path for path, _, _ in self.calls))

    def test_missing_extra_old_expired_or_mutated_intent_denies_all_writes(self):
        name = finalize.intent_name('12', self.receipt)
        row = dict(name=name, expired=False, workflow_run={'id': 13})
        for rows in ([], [row, row], [dict(row, expired=True)],
                     [dict(row, workflow_run={'id': 14})]):
            self.rows = rows
            with self.subTest(rows=rows), self.assertRaises(InvalidReview): self.run_phase(finalize.release)
        self.rows = [row]
        self.intent = copy.deepcopy(self.intent)
        self.intent['publication_receipt']['result_sha256'] = 'f' * 64
        with self.assertRaises(InvalidReview): self.run_phase(finalize.release)
        self.assertFalse(self.calls)

    def test_prior_intent_and_run_attempt_cannot_be_replayed(self):
        self.rows = [dict(name='preloop-finalize-old')]
        with self.assertRaises(InvalidReview): self.run_phase(finalize.prepare)
        self.rows = []
        with patch.dict(os.environ, GITHUB_RUN_ATTEMPT='2'):
            with self.assertRaises(InvalidReview): self.run_phase(finalize.prepare)
            with self.assertRaises(InvalidReview): self.run_phase(finalize.release)
        self.assertFalse(self.calls)

    def test_producer_requires_authoritative_completed_publication(self):
        name = 'preloop-publication-' + self.receipt['execution_id']
        def artifact(*args, **kwargs):
            return {'completion': self.completion} if args[2].startswith('preloop-wake-') else self.receipt
        with patch.object(finalize.runtime, 'github_pages', return_value=[dict(name=name, expired=False)]), \
             patch.object(finalize.runtime, 'artifact', side_effect=artifact), \
             patch.object(finalize.runtime, 'completed_publication', side_effect=InvalidReview('Actual run not complete')):
            with self.assertRaisesRegex(InvalidReview, 'not complete'):
                finalize.producer(self.github, self.binding)
        self.assertFalse(self.calls)


if __name__ == '__main__':
    unittest.main()
