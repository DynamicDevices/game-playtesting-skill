"""Exercise the actual publisher entry point with isolated fake APIs."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from completion_contract import canonical_digest
from review_contract import InvalidReview
import publisher


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.binding = dict(repository='example/repository', repository_id=42, default_branch='main',
                            flow_id='flow', project_id='project', model_id='model',
                            native_ci_contract={'flow_config_sha256': 'f' * 64})
        self.intent = dict(flow_id='flow', project_id='project', repository_identifier='42',
                           pr_number=7, head_sha='a' * 40, base_sha='b' * 40,
                           diff_sha256='c' * 64, challenge='d' * 48,
                           trigger_run_id='10', model_id='model', flow_config_sha256='f' * 64)
        self.eid = '487d988a-53ad-4f5d-8b84-d77bb733676f'
        self.receipt = dict(self.intent, execution_id=self.eid)
        self.result = dict(success=True, verdict='pass', review='Complete review, no actionable defects.',
                           head_sha='a' * 40, base_sha='b' * 40, findings=[])
        self.detail = dict(self.intent, id=self.eid, status='SUCCEEDED', start_time='2026-11-13T15:00:00Z',
                           startup_receipt=dict(version=1, executor='hosted', checkout_verified=True,
                                                setup_completed=True, commit='a' * 40,
                                                agent_started_at='2026-11-13T15:00:01Z'))
        self.completion = dict(self.intent, execution_id=self.eid, status='SUCCEEDED', result_ready=True,
                               event_id='73db8ab4-33db-4359-a135-9f20edc61ff8',
                               result_sha256=canonical_digest(self.result))
        self.reviews, self.checks, self.statuses, self.calls = [], [], [], []
        self.fail_review = False
        self.readback_actor = 'github-actions[bot]'
        self.event = Path(self.temp.name) / 'event.json'
        self.event.write_text('{}')
        env = patch.dict(os.environ, GITHUB_REPOSITORY='example/repository', GH_TOKEN='fixture',
                         PRELOOP_CI_TOKEN='ci_fixture', PRELOOP_EXECUTION_ID=self.eid,
                         GITHUB_RUN_ID='12', GITHUB_EVENT_PATH=str(self.event), RUNNER_TEMP=self.temp.name)
        env.start()
        self.addCleanup(env.stop)

    def github(self, path, method='GET', body=None):
        self.calls.append((path, method, body))
        if path.endswith('/check-runs') and method == 'POST':
            value = dict(body, id=11 + len(self.checks), app={'slug': 'github-actions'})
            self.checks.append(value)
            return value
        if '/check-runs/' in path:
            value = next(row for row in self.checks if row['id'] == int(path.rsplit('/', 1)[1]))
            if method == 'PATCH':
                value.update(body)
            return value
        if path.endswith('/reviews') and method == 'POST':
            if self.fail_review:
                raise InvalidReview('Synthetic ambiguous send')
            value = dict(body, id=22, commit_id=body['commit_id'], state='COMMENTED', submitted_at='now',
                         user={'login': self.readback_actor}, html_url='https://github.com/example/repository/pull/7#review-22')
            self.reviews.append(value)
            return value
        if '/reviews/' in path:
            return self.reviews[0]
        if '/statuses/' in path and method == 'POST':
            value = dict(body, id=33 + len(self.statuses), creator={'login': 'github-actions[bot]'})
            self.statuses.insert(0, value)
            return value
        if path.endswith('/status'):
            return {'sha': 'a' * 40, 'statuses': self.statuses}
        raise AssertionError('Unexpected fake API route: ' + path)

    def artifacts(self, _github, _binding, name, _workflow, **_kwargs):
        if name.startswith('preloop-wake-'):
            return {'completion': self.completion}
        return self.receipt if name.startswith('preloop-trigger-') else self.intent

    def preloop(self, path, _token, method='GET', body=None):
        self.assertEqual(method, 'GET', 'Publisher must never trigger another review')
        if path.endswith('/result'):
            return dict(execution_id=self.eid, status=self.detail['status'], result=self.result)
        return self.detail

    def pages(self, _github, path, field=None):
        return list(self.reviews) if path.endswith('/reviews') else list(self.checks)

    def run_publisher(self, stale=False):
        self.completion['result_sha256'] = canonical_digest(self.result)
        patches = [patch.object(publisher.runtime, 'context', return_value=(self.binding, {}, self.github)),
                   patch.object(publisher.runtime, 'artifact', side_effect=self.artifacts),
                   patch.object(publisher.runtime, 'preloop', side_effect=self.preloop),
                   patch.object(publisher.runtime, 'full_diff_sha256', return_value='c' * 64),
                   patch.object(publisher.runtime, 'executions', return_value=[self.detail]),
                   patch.object(publisher.runtime, 'github_pages', side_effect=self.pages),
                   patch.object(publisher.runtime, 'current_pr', side_effect=InvalidReview('Stale PR') if stale else None)]
        for item in patches:
            item.start()
        try:
            return publisher.publish()
        finally:
            for item in reversed(patches):
                item.stop()

    def test_clean_result_publishes_review_status_check_and_receipt(self):
        self.assertEqual(self.run_publisher(), 0)
        self.assertEqual(self.statuses[0]['state'], 'success')
        self.assertEqual(self.checks[0]['conclusion'], 'success')
        self.assertIn(self.eid, self.reviews[0]['body'])
        self.assertTrue((Path(self.temp.name) / 'preloop-publication/receipt.json').exists())

    def test_blocking_result_remains_readable_and_fails(self):
        self.result.update(success=False, verdict='changes_requested', findings=[dict(
            severity='HIGH', location='file.py:1', problem='Problem', evidence='Evidence', fix='Fix')])
        self.assertEqual(self.run_publisher(), 1)
        self.assertEqual(self.statuses[0]['state'], 'failure')
        self.assertIn('🔴 High', self.reviews[0]['body'])

    def test_failed_execution_keeps_findings_without_green(self):
        self.detail['status'] = self.completion['status'] = 'FAILED'
        self.result.update(success=False, verdict='error', findings=[dict(
            severity='LOW', location='file.py:1', problem='Problem', evidence='Evidence', fix='Fix')])
        self.assertEqual(self.run_publisher(), 1)
        self.assertEqual(self.statuses[0]['state'], 'error')
        self.assertIn('🟡 Low', self.reviews[0]['body'])

    def test_stale_pr_cannot_publish(self):
        with self.assertRaises(InvalidReview):
            self.run_publisher(stale=True)
        self.assertEqual(self.calls, [])

    def test_wrong_review_actor_cannot_get_success_status(self):
        self.readback_actor = 'other'
        with self.assertRaises(InvalidReview):
            self.run_publisher()
        self.assertEqual(self.statuses, [])
        self.assertEqual(self.checks[0]['conclusion'], 'failure')

    def test_ambiguous_send_is_not_repeated(self):
        self.fail_review = True
        with self.assertRaises(InvalidReview):
            self.run_publisher()
        attempts = len([call for call in self.calls if call[0].endswith('/reviews') and call[1] == 'POST'])
        self.fail_review = False
        with self.assertRaises(InvalidReview):
            self.run_publisher()
        self.assertEqual(len([call for call in self.calls if call[0].endswith('/reviews') and call[1] == 'POST']), attempts)

    def test_owned_completed_publication_can_be_reconciled_without_second_review_post(self):
        self.run_publisher()
        # A fresh publisher job has a new workspace; keep only the fake remote records.
        (Path(self.temp.name) / 'preloop-publication/receipt.json').unlink()
        self.assertEqual(self.run_publisher(), 0)
        self.assertEqual(len(self.reviews), 1)

    def test_result_substitution_refused_before_writes(self):
        self.receipt['execution_id'] = 'different'
        with self.assertRaises(InvalidReview):
            self.run_publisher()
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
