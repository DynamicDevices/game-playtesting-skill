"""Completion authentication/recovery entry points without live service access."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from review_contract import InvalidReview
import publisher


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.eid = '487d988a-53ad-4f5d-8b84-d77bb733676f'
        self.completion = dict(execution_id=self.eid, pr_number=7)
        self.wake = dict(completion=self.completion, authenticated_run_id='10', workflow_sha='a' * 40)
        self.event = Path(self.temp.name) / 'event.json'
        self.event.write_text('{}')
        self.binding = {'callback_tolerance_seconds': 300}
        env = patch.dict(os.environ, RUNNER_TEMP=self.temp.name, GITHUB_EVENT_PATH=str(self.event),
                         GITHUB_EVENT_NAME='repository_dispatch', GITHUB_RUN_ID='12',
                         PRELOOP_CALLBACK_SECRET='synthetic-only')
        env.start()
        self.addCleanup(env.stop)
        for name, kwargs in [
            ('context', {'return_value': (self.binding, {'workflow_sha': 'b' * 40}, 'fake-api')}),
            ('artifact', {'return_value': self.wake}), ('output', {})]:
            item = patch.object(publisher.runtime, name, **kwargs)
            setattr(self, name, item.start())
            self.addCleanup(item.stop)

    def recover(self, previous='10'):
        os.environ['GITHUB_EVENT_NAME'] = 'workflow_dispatch'
        self.event.write_text(json.dumps({'inputs': dict(
            execution_id=self.eid, authenticated_run_id=previous)}))
        publisher.authenticate()

    def test_dispatch_authenticates_before_persisting(self):
        with patch.object(publisher, 'verify_dispatch', return_value=self.completion) as verify:
            publisher.authenticate()
        self.assertEqual(verify.call_count, 1)
        saved = json.loads((Path(self.temp.name) / 'preloop-wake/receipt.json').read_text())
        self.assertEqual(saved['authenticated_run_id'], '12')
        self.assertEqual(saved['workflow_sha'], 'b' * 40)
        self.artifact.assert_not_called()

    def test_bad_signature_never_creates_wake(self):
        with patch.object(publisher, 'verify_dispatch', side_effect=InvalidReview('bad signature')):
            with self.assertRaises(InvalidReview):
                publisher.authenticate()
        self.assertFalse((Path(self.temp.name) / 'preloop-wake').exists())
        self.output.assert_not_called()

    def test_recovery_uses_original_authenticated_run_not_expired_hmac(self):
        with patch.object(publisher, 'verify_dispatch') as verify:
            self.recover()
        verify.assert_not_called()
        self.artifact.assert_called_once_with('fake-api', self.binding, 'preloop-wake-' + self.eid,
                                             'preloop-review-publish.yml', allow_failed=True, run_id='10')
        saved = json.loads((Path(self.temp.name) / 'preloop-wake/receipt.json').read_text())
        self.assertEqual(saved, self.wake)

    def test_recovery_rejects_run_or_execution_substitution(self):
        for field, value in [('authenticated_run_id', '99'), ('completion', {'execution_id': 'wrong'})]:
            original = self.wake[field]
            self.wake[field] = value
            with self.subTest(field=field), self.assertRaises(InvalidReview):
                self.recover()
            self.wake[field] = original
        self.output.assert_not_called()

    def test_recovery_rejects_malformed_reference_without_fetch(self):
        with self.assertRaises(InvalidReview):
            self.recover('../other-run')
        self.artifact.assert_not_called()

    def test_unexpected_event_never_fetches_or_persists(self):
        os.environ['GITHUB_EVENT_NAME'] = 'pull_request'
        with self.assertRaises(InvalidReview):
            publisher.authenticate()
        self.artifact.assert_not_called()
        self.output.assert_not_called()


if __name__ == '__main__':
    unittest.main()
