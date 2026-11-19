"""Completed-finalizer admission; all APIs are synthetic and isolated."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import finalize
import runtime
import trust
from review_contract import InvalidReview


class MergeGateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.event_path = Path(temp.name) / 'event.json'
        self.event = dict(action='completed', repository={'id': 42}, workflow_run={
            'id': 13, 'path': '.github/workflows/preloop-review-finalize.yml'})
        self.binding = dict(repository='example/repository', repository_id=42,
            default_branch='main', publication_merge_gate=copy.deepcopy(trust.MERGE_GATE))
        self.run = dict(id=13, repository={'id': 42},
            path='.github/workflows/preloop-review-finalize.yml', head_branch='main',
            event='workflow_run', status='completed', conclusion='success', run_attempt=1)
        self.completion = dict(execution_id='487d988a-53ad-4f5d-8b84-d77bb733676f', pr_number=7,
            head_sha='a' * 40, base_sha='b' * 40, result_sha256='c' * 64,
            status='SUCCEEDED', result_ready=True)
        self.receipt = dict(self.completion, state='success')
        self.intent = dict(publisher_run_id='12', finalizer_run_id='13',
            publication_receipt=self.receipt, completion=self.completion)
        self.rows = [dict(name=finalize.intent_name('12', self.receipt), expired=False)]
        self.proof = dict(delivery_verified=True, actions_run_verified=True,
            actions_check_verified=True, review_approved=True, review_state='success', finalizer_run_id='13')
        self.calls = []
        env = patch.dict(os.environ, GITHUB_EVENT_NAME='workflow_run',
            GITHUB_EVENT_PATH=str(self.event_path), GITHUB_RUN_ID='14', GITHUB_RUN_ATTEMPT='1',
            PRELOOP_CI_TOKEN='synthetic')
        env.start()
        self.addCleanup(env.stop)

    def execute(self, *, stale=False, artifact_failure=False):
        self.event_path.write_text(json.dumps(self.event))
        with patch.object(runtime, 'context', return_value=(self.binding, {}, lambda _: self.run)), \
             patch.object(runtime, 'github_pages', return_value=self.rows), \
             patch.object(runtime, 'artifact', side_effect=InvalidReview('Failed source/job proof') if artifact_failure else None,
                          return_value=self.intent), \
             patch.object(runtime, 'completed_publication', return_value=self.proof), \
             patch.object(finalize.publisher, 'no_supersession',
                          side_effect=InvalidReview('Newer execution') if stale else None), \
             patch.object(runtime, 'current_pr') as current, \
             patch.object(runtime, 'commit_status', side_effect=lambda *a, **kw: self.calls.append((a, kw))):
            finalize.accept()
            current.assert_called_once()

    def test_only_complete_success_releases_distinct_gate(self):
        self.execute()
        self.assertEqual(len(self.calls), 1)
        args, keywords = self.calls[0]
        self.assertEqual(args[3], 'success')
        self.assertEqual(keywords, {'context_name': 'Preloop merge gate'})
        self.assertEqual(args[2], 'a' * 40)

    def test_running_failed_cancelled_or_retried_finalizer_cannot_release(self):
        for field, value in [('status', 'in_progress'), ('conclusion', 'failure'),
                             ('conclusion', 'cancelled'), ('conclusion', None), ('run_attempt', 2),
                             ('head_branch', 'feature'), ('event', 'push'), ('id', 99),
                             ('repository', {'id': 99})]:
            before = copy.deepcopy(self.run)
            self.run[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(InvalidReview):
                self.execute()
            self.assertEqual(self.calls, [])
            self.run = before

    def test_partial_green_does_not_replace_actual_finalizer_completion(self):
        self.run.update(status='in_progress', conclusion=None)
        # The later acceptance reader could otherwise see old green records.
        self.proof.update(review_state='success', review_approved=True)
        with self.assertRaises(InvalidReview):
            self.execute()
        self.assertEqual(self.calls, [])

    def test_each_acceptance_flag_and_exact_finalizer_is_required(self):
        for field in ['delivery_verified', 'actions_run_verified', 'actions_check_verified', 'review_approved',
                      'finalizer_run_id', 'review_state']:
            previous = self.proof[field]
            self.proof[field] = False if type(previous) is bool else 'wrong'
            with self.subTest(field=field), self.assertRaises(InvalidReview):
                self.execute()
            self.assertEqual(self.calls, [])
            self.proof[field] = previous

    def test_supersession_and_failed_artifact_proof_deny_write(self):
        for kwargs in [dict(stale=True), dict(artifact_failure=True)]:
            with self.subTest(kwargs=kwargs), self.assertRaises(InvalidReview):
                self.execute(**kwargs)
            self.assertEqual(self.calls, [])

    def test_missing_duplicate_or_expired_intent_denies_write(self):
        for rows in [[], self.rows * 2, [dict(self.rows[0], expired=True)]]:
            with patch.object(self, 'rows', rows), self.assertRaises(InvalidReview):
                self.execute()
            self.assertEqual(self.calls, [])

    def test_changed_completion_or_wrong_event_denies_write(self):
        original = copy.deepcopy(self.intent)
        self.intent['completion'] = dict(self.completion, result_sha256='d' * 64)
        with self.assertRaises(InvalidReview):
            self.execute()
        self.intent = original
        self.event['workflow_run']['path'] = '.github/workflows/preloop-review-publish.yml'
        with self.assertRaises(InvalidReview):
            self.execute()
        self.assertEqual(self.calls, [])

    def test_merge_workload_requires_exact_signed_admission(self):
        binding = dict(publication_merge_gate=copy.deepcopy(trust.MERGE_GATE),
                       publication_finalizer=dict(explicit_posture_approval=True,
                           workflow_path='.github/workflows/preloop-review-finalize.yml',
                           event='workflow_run', producer_path='.github/workflows/preloop-review-publish.yml'))
        self.assertEqual(trust.workload_events(binding, 'preloop-review-merge.yml'), ['workflow_run'])
        for key in trust.MERGE_GATE:
            changed = copy.deepcopy(binding)
            changed['publication_merge_gate'][key] = 'wrong'
            with self.subTest(key=key), self.assertRaises(InvalidReview):
                trust.workload_events(changed, 'preloop-review-merge.yml')
        with self.assertRaises(InvalidReview):
            trust.workload_events({}, 'preloop-review-merge.yml')

    def test_unadmitted_status_context_cannot_write(self):
        with self.assertRaises(InvalidReview):
            runtime.commit_status(lambda *a: self.fail('Must deny before API'), {}, 'a' * 40,
                'success', 'url', 'description', context_name='Preloop merge gate')


if __name__ == '__main__':
    unittest.main()
