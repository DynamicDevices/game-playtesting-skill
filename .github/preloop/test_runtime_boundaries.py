"""Privilege allowlist and artifact-provenance regression tests."""
import os
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


if __name__ == '__main__':
    unittest.main()
