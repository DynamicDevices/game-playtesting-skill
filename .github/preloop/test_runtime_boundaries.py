"""Privilege allowlist and artifact-provenance regression tests."""
import os
import hashlib
import unittest
from unittest.mock import patch

from review_contract import InvalidReview
import runtime


class RuntimeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.binding = dict(repository='example/repository', publication_enabled=True,
                            native_ci_contract={'explicit_posture_approval': True},
                            approved_files={}, default_branch='main')
        env = patch.dict(os.environ, GITHUB_REPOSITORY='example/repository', GH_TOKEN='fixture',
                         GITHUB_RUN_ID='12')
        env.start()
        self.addCleanup(env.stop)

    def test_write_allowlist_rejects_source_and_unrelated_operations(self):
        with patch.object(runtime.trust, 'load_authority', return_value=self.binding), \
             patch.object(runtime.trust, 'verify_workload', return_value={'workflow_sha': 'a' * 40}), \
             patch.object(runtime.trust, 'verify_sources'), \
             patch.object(runtime, 'verify_live_service') as live, \
             patch.object(runtime.trust, 'request') as request:
            _, _, github = runtime.context('preloop-review-publish.yml')
            for path, method in [('contents/file.py', 'PUT'), ('pulls/7', 'PATCH'),
                                 ('pulls/7/merge', 'PUT'), ('git/refs', 'POST'),
                                 ('issues/7/comments', 'POST'), ('check-runs/1', 'DELETE')]:
                with self.subTest(path=path), self.assertRaises(InvalidReview):
                    github('/repos/example/repository/' + path, method, {})
            with self.assertRaises(InvalidReview):
                github('/repos/other/repository/statuses/' + 'a' * 40, 'POST', {})
            request.assert_not_called()
            live.assert_not_called()
            github('/repos/example/repository/pulls/7/reviews', 'POST', {})
            live.assert_called_once()
            self.assertEqual(request.call_count, 1)

    def test_trigger_cannot_use_publisher_privileges(self):
        with patch.object(runtime.trust, 'load_authority', return_value=self.binding), \
             patch.object(runtime.trust, 'verify_workload', return_value={'workflow_sha': 'a' * 40}), \
             patch.object(runtime.trust, 'verify_sources'), \
             patch.object(runtime.trust, 'request') as request:
            _, _, github = runtime.context('preloop-review-trigger.yml')
            with self.assertRaises(InvalidReview):
                github('/repos/example/repository/pulls/7/reviews', 'POST', {})
            request.assert_not_called()

    def test_failed_live_gate_cannot_transmit_an_allowed_write(self):
        with patch.object(runtime.trust, 'load_authority', return_value=self.binding), \
             patch.object(runtime.trust, 'verify_workload', return_value={'workflow_sha': 'a' * 40}), \
             patch.object(runtime.trust, 'verify_sources'), \
             patch.object(runtime, 'verify_live_service', side_effect=InvalidReview('suspended')), \
             patch.object(runtime.trust, 'request') as request:
            _, _, github = runtime.context('preloop-review-publish.yml')
            with self.assertRaisesRegex(InvalidReview, 'suspended'):
                github('/repos/example/repository/pulls/7/reviews', 'POST', {})
            request.assert_not_called()

    def artifact(self, auth_success=True, branch='main', event='repository_dispatch', expired=False):
        row = dict(id=1, name='preloop-wake-execution', expired=expired, workflow_run={'id': 10})
        run = dict(id=10, path='.github/workflows/preloop-review-publish.yml',
                   status='completed', conclusion='failure', event=event,
                   head_branch=branch, head_sha='a' * 40)
        def pages(_api, path, field):
            if field == 'artifacts':
                return [row]
            return [dict(name='Authenticate completion', conclusion='success' if auth_success else 'failure')]
        with patch.object(runtime, 'github_pages', side_effect=pages), \
             patch.object(runtime.trust, 'download_trigger_artifact', return_value={'safe': True}), \
             patch.object(runtime.trust, 'verify_sources') as source:
            result = runtime.artifact(lambda _: run, self.binding, row['name'],
                                      'preloop-review-publish.yml', allow_failed=True, run_id='10')
            source.assert_called_once()
            return result

    def test_recovery_accepts_failed_publish_only_after_successful_auth_job(self):
        self.assertEqual(self.artifact(), {'safe': True})
        with self.assertRaises(InvalidReview):
            self.artifact(auth_success=False)

    def test_recovery_rejects_wrong_branch_event_or_expired_artifact(self):
        for kwargs in [dict(branch='untrusted'), dict(event='pull_request'), dict(expired=True)]:
            with self.subTest(kwargs=kwargs), self.assertRaises(InvalidReview):
                self.artifact(**kwargs)


class CompletedPublicationTests(unittest.TestCase):
    def setUp(self):
        self.eid = '487d988a-53ad-4f5d-8b84-d77bb733676f'
        self.head, self.base, self.code = 'a' * 40, 'b' * 40, 'e' * 40
        self.binding = {'repository': 'example/repository', 'repository_id': 42,
                        'default_branch': 'main'}
        self.url = 'https://github.com/example/repository/actions/runs/12'
        self.body = 'Complete review.\n<!-- briar-preloop:' + self.eid + ':' + 'c' * 64 + ' -->'
        self.run = dict(id=12, html_url=self.url, repository={'id': 42}, head_branch='main',
                        path='.github/workflows/preloop-review-publish.yml', head_sha=self.code,
                        event='repository_dispatch', status='completed', conclusion='success', run_attempt=1)
        self.receipt = dict(execution_id=self.eid, head_sha=self.head, base_sha=self.base,
                            execution_status='SUCCEEDED', review_verdict='pass',
                            state='success', actions_run_url=self.url, publication_run_attempt='1',
                            review_id=22, check_id=11, status_id=33, claim_sha256='c' * 64,
                            review_url='https://github.com/example/repository/pull/7#review-22',
                            review_body_sha256=hashlib.sha256(self.body.encode()).hexdigest())
        self.jobs = [dict(id=n, name=name, run_id=12, head_sha=self.code,
                          status='completed', conclusion='success') for n, name in
                     [(1, 'Authenticate completion'), (2, 'Preloop review')]]
        self.jobs[1]['steps'] = [dict(name=name, status='completed', conclusion='success') for name in
            ['Validate, publish and independently read back', 'Preserve actual publication receipt']]
        self.review = dict(id=22, commit_id=self.head, state='COMMENTED', submitted_at='now',
                           user={'login': 'github-actions[bot]'}, body=self.body,
                           html_url=self.receipt['review_url'])
        self.check = dict(id=11, name='Preloop review', head_sha=self.head, status='completed',
                          conclusion='success', details_url=self.url, app={'slug': 'github-actions'},
                          external_id='briar-preloop:' + 'c' * 64)
        self.statuses = [dict(id=33, context='Preloop review', state='success', target_url=self.url,
                              creator={'login': 'github-actions[bot]'})]

    def github(self, path):
        if path.endswith('/actions/runs/12'): return self.run
        if '/jobs?' in path: return {'jobs': self.jobs}
        if '/reviews/' in path: return self.review
        if '/check-runs/' in path: return self.check
        if '/statuses?' in path: return self.statuses
        raise AssertionError('Unexpected acceptance read: ' + path)

    def accept(self):
        with patch.object(runtime, 'artifact', return_value=self.receipt) as artifact, \
             patch.object(runtime, 'current_pr') as current:
            result = runtime.completed_publication(self.github, self.binding, 12, self.eid,
                                                   7, self.head, self.base)
            self.assertEqual(current.call_count, 2)
            self.assertTrue(artifact.call_args.kwargs['allow_failed'])
            return result

    def test_real_completed_jobs_accept_distinct_trusted_code_and_reviewed_heads(self):
        self.assertNotEqual(self.code, self.head)
        self.assertTrue(self.accept()['actions_check_verified'])

    def test_green_custom_check_cannot_hide_running_or_failed_actual_run(self):
        for key, value in [('status', 'in_progress'), ('conclusion', 'failure')]:
            saved = self.run[key]
            self.run[key] = value
            with self.subTest(key=key), self.assertRaises(InvalidReview): self.accept()
            self.run[key] = saved

    def test_changes_requested_is_delivered_but_not_approved(self):
        self.run['conclusion'] = self.jobs[1]['conclusion'] = 'failure'
        self.jobs[1]['steps'][0]['conclusion'] = 'failure'
        self.receipt.update(state='failure', review_verdict='changes_requested')
        self.check['conclusion'] = self.statuses[0]['state'] = 'failure'
        result = self.accept()
        self.assertTrue(result['delivery_verified'])
        self.assertTrue(result['actions_run_verified'])
        self.assertFalse(result['review_approved'])
        self.assertFalse(result['actions_check_verified'])

    def test_changes_requested_cannot_hide_upload_or_other_step_failure(self):
        self.run['conclusion'] = self.jobs[1]['conclusion'] = 'failure'
        self.jobs[1]['steps'][0]['conclusion'] = 'failure'
        self.receipt.update(state='failure', review_verdict='changes_requested')
        self.check['conclusion'] = self.statuses[0]['state'] = 'failure'
        self.jobs[1]['steps'][1]['conclusion'] = 'failure'
        with self.assertRaises(InvalidReview): self.accept()

    def test_service_error_is_never_a_delivered_review(self):
        for key, value in [('execution_status', 'FAILED'), ('review_verdict', 'error'), ('state', 'error')]:
            saved = self.receipt[key]
            self.receipt[key] = value
            with self.subTest(key=key), self.assertRaises(InvalidReview): self.accept()
            self.receipt[key] = saved

    def test_missing_skipped_failed_or_foreign_job_refuses_acceptance(self):
        for key, value in [('conclusion', 'skipped'), ('conclusion', 'failure'),
                           ('status', 'in_progress'), ('run_id', 13), ('head_sha', self.head)]:
            saved = self.jobs[1][key]
            self.jobs[1][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(InvalidReview): self.accept()
            self.jobs[1][key] = saved
        self.jobs.pop()
        with self.assertRaises(InvalidReview): self.accept()

    def test_old_attempt_receipt_or_stale_binding_refuses_acceptance(self):
        for key, value in [('publication_run_attempt', '2'), ('head_sha', self.base),
                           ('execution_id', 'another'), ('state', 'failure')]:
            saved = self.receipt[key]
            self.receipt[key] = value
            with self.subTest(key=key), self.assertRaises(InvalidReview): self.accept()
            self.receipt[key] = saved

    def test_changed_review_body_check_actor_or_newer_error_status_refuses_acceptance(self):
        self.review['body'] += '\nChanged content'
        with self.assertRaises(InvalidReview): self.accept()
        self.review['body'] = self.body
        self.check['app']['slug'] = 'other'
        with self.assertRaises(InvalidReview): self.accept()
        self.check['app']['slug'] = 'github-actions'
        self.statuses.insert(0, dict(self.statuses[0], id=34, state='error'))
        with self.assertRaises(InvalidReview): self.accept()


if __name__ == '__main__':
    unittest.main()
