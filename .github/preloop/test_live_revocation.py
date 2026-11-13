"""Online write-boundary suspension checks; no real API or credential use."""
import copy
import os
import unittest
from unittest.mock import patch

from review_contract import InvalidReview
import runtime


class LiveRevocationTests(unittest.TestCase):
    def setUp(self):
        self.names = {'preloop-review-trigger.yml': 100, 'preloop-review-publish.yml': 101}
        self.binding = dict(repository='example/repository', repository_id=42, default_branch='main',
                            live_revocation=dict(mechanism='github-actions-workflow-and-run-v1',
                                                 explicit_posture_approval=True,
                                                 workflow_ids=self.names))
        self.workload = dict(workflow_sha='a' * 40, event_name='repository_dispatch', run_attempt='1')
        self.workflows = {str(value): dict(id=value, state='active', path='.github/workflows/' + name)
                          for name, value in self.names.items()}
        self.run = dict(id=12, repository={'id': 42}, workflow_id=101, head_sha='a' * 40,
                        head_branch='main', event='repository_dispatch', run_attempt=1,
                        status='in_progress', conclusion=None)
        self.calls = []
        for item in [patch.dict(os.environ, GITHUB_RUN_ID='12', GH_TOKEN='fixture'),
                     patch.object(runtime.trust, 'load_authority', return_value=self.binding),
                     patch.object(runtime.trust, 'request', side_effect=self.request)]:
            item.start()
            self.addCleanup(item.stop)

    def request(self, origin, path, token):
        self.assertEqual(origin, 'https://api.github.com')
        self.assertEqual(token, 'fixture')
        self.calls.append(path)
        if '/actions/workflows/' in path:
            return self.workflows[path.rsplit('/', 1)[1]]
        self.assertEqual(path, '/repos/example/repository/actions/runs/12')
        return self.run

    def verify(self):
        runtime.verify_live_service(self.binding, self.workload, 'preloop-review-publish.yml')

    def test_active_exact_workflow_and_attempt_are_checked_afresh(self):
        self.verify()
        self.assertEqual(len(self.calls), 3)
        self.run['status'] = 'completed'
        with self.assertRaises(InvalidReview):
            self.verify()
        self.assertEqual(len(self.calls), 6)

    def test_disabling_either_workflow_suspends_publication(self):
        for key in self.workflows:
            self.workflows[key]['state'] = 'disabled_manually'
            with self.subTest(workflow=key), self.assertRaises(InvalidReview):
                self.verify()
            self.workflows[key]['state'] = 'active'

    def test_pr_target_uses_signed_base_workload_not_api_branch_label(self):
        self.workload['event_name'] = 'pull_request_target'
        self.run.update(event='pull_request_target', workflow_id=100, head_branch='feature')
        runtime.verify_live_service(self.binding, self.workload, 'preloop-review-trigger.yml')
        self.assertEqual(len(self.calls), 3)

    def test_cancelled_or_retried_workload_is_not_old_attempt(self):
        for changes in [dict(status='completed', conclusion='cancelled'),
                        dict(status='queued'), dict(conclusion='cancelled'),
                        dict(run_attempt=2), dict(run_attempt=None)]:
            original = copy.deepcopy(self.run)
            self.run.update(changes)
            with self.subTest(changes=changes), self.assertRaises(InvalidReview):
                self.verify()
            self.run = original

    def test_substituted_workflow_repository_revision_or_event_is_denied(self):
        for key, value in [('id', 99), ('repository', {'id': 43}), ('workflow_id', 100),
                           ('head_sha', 'b' * 40), ('head_branch', 'other'), ('event', 'push')]:
            original = copy.deepcopy(self.run)
            self.run[key] = value
            with self.subTest(field=key), self.assertRaises(InvalidReview):
                self.verify()
            self.run = original
        self.workflows['101']['path'] = '.github/workflows/other.yml'
        with self.assertRaises(InvalidReview):
            self.verify()

    def test_unsigned_or_incomplete_opt_in_is_denied_before_api_read(self):
        original = copy.deepcopy(self.binding['live_revocation'])
        for value in [None, {}, dict(original, explicit_posture_approval=False),
                      dict(original, workflow_ids={'preloop-review-publish.yml': 101}),
                      dict(original, workflow_ids={**self.names, 'preloop-review-trigger.yml': True})]:
            self.binding['live_revocation'] = value
            with self.subTest(value=value), self.assertRaises(InvalidReview):
                self.verify()
        self.assertEqual(self.calls, [])

    def test_unavailable_online_control_fails_closed(self):
        with patch.object(runtime.trust, 'request', side_effect=OSError('fixture unavailable')):
            with self.assertRaises(OSError):
                self.verify()

    def test_changed_or_expired_signature_fails_before_api_read(self):
        with patch.object(runtime.trust, 'load_authority', return_value={}):
            with self.assertRaises(InvalidReview):
                self.verify()
        with patch.object(runtime.trust, 'load_authority', side_effect=InvalidReview('expired')):
            with self.assertRaises(InvalidReview):
                self.verify()
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
