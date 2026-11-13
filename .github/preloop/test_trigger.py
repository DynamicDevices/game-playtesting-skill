"""Trigger entry-point tests: no network, credentials or paid executions."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from review_contract import InvalidReview
import runtime
import trigger


class TriggerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.binding = dict(repository='example/repository', repository_id=42,
                            flow_id='flow', project_id='project', model_id='model',
                            native_ci_contract={'flow_config_sha256': 'f' * 64})
        self.intent = dict(flow_id='flow', project_id='project', repository_identifier='42',
                           pr_number=7, head_sha='a' * 40, base_sha='b' * 40,
                           trigger_run_id='10', workflow_sha='e' * 40, model_id='model',
                           flow_config_sha256='f' * 64, challenge='d' * 48,
                           diff_sha256='c' * 64)
        self.detail = dict(self.intent, id='execution', startup_receipt=dict(
            version=1, executor='hosted', commit='a' * 40, checkout_verified=True,
            setup_completed=True, agent_started_at='2026-11-13T15:00:01Z', lease_revoked=None))
        self.rows, self.calls = [], []
        self.journal = {'total_count': 0, 'artifacts': []}
        self.event = Path(self.temp.name) / 'event.json'
        self.event.write_text(json.dumps({'number': 7}))
        patches = [patch.dict(os.environ, GITHUB_EVENT_PATH=str(self.event),
                              GITHUB_EVENT_NAME='pull_request_target', GITHUB_RUN_ID='10',
                              RUNNER_TEMP=self.temp.name, GH_TOKEN='fixture',
                              PRELOOP_CI_TRIGGER_TOKEN='ci_fixture'),
                   patch.object(runtime, 'context', return_value=(
                       self.binding, {'workflow_sha': 'e' * 40}, self.github)),
                   patch.object(runtime, 'current_pr', return_value={
                       'head': {'sha': 'a' * 40}, 'base': {'sha': 'b' * 40}}),
                   patch.object(runtime, 'executions', side_effect=lambda *_: self.rows),
                   patch.object(runtime, 'full_diff_sha256', return_value='c' * 64),
                   patch.object(runtime, 'output'),
                   patch.object(runtime, 'commit_status'),
                   patch.object(runtime, 'preloop', side_effect=self.preloop)]
        self.mocks = []
        for item in patches:
            self.mocks.append(item.start())
            self.addCleanup(item.stop)

    def github(self, path, method='GET', body=None):
        self.assertEqual(method, 'GET')
        self.assertIn('/actions/artifacts?', path)
        return self.journal

    def preloop(self, path, token, method='GET', body=None):
        self.calls.append((path, method, body))
        return copy.deepcopy(self.detail)

    def store_intent(self):
        runtime.write_receipt(Path(self.temp.name) / 'preloop-intent', self.intent)
        self.journal = dict(total_count=1, artifacts=[dict(expired=False, workflow_run={'id': 10})])

    def store_receipt(self):
        runtime.write_receipt(Path(self.temp.name) / 'preloop-trigger',
                              dict(self.intent, execution_id='execution'))

    def test_prepare_binds_full_diff_and_external_challenge(self):
        trigger.prepare()
        saved = json.loads((Path(self.temp.name) / 'preloop-intent/receipt.json').read_text())
        self.assertEqual(saved['diff_sha256'], 'c' * 64)
        self.assertRegex(saved['challenge'], '^[0-9a-f]{48}$')
        self.assertEqual(saved['workflow_sha'], 'e' * 40)
        self.assertEqual(self.calls, [])

    def test_prepare_refuses_existing_execution(self):
        self.rows = [dict(self.detail)]
        with self.assertRaises(InvalidReview):
            trigger.prepare()
        self.assertEqual(self.calls, [])

    def test_prepare_refuses_prior_intent(self):
        self.journal['total_count'] = 1
        with self.assertRaises(InvalidReview):
            trigger.prepare()

    def test_start_requires_durable_intent_before_spend(self):
        self.store_intent()
        self.journal['artifacts'][0]['workflow_run']['id'] = 11
        with self.assertRaises(InvalidReview):
            trigger.start()
        self.assertEqual(self.calls, [])

    def test_start_stops_only_superseded_same_pr(self):
        self.store_intent()
        self.rows = [dict(self.detail, id='old', head_sha='9' * 40, status='RUNNING'),
                     dict(self.detail, id='other-pr', pr_number=8, status='RUNNING'),
                     dict(self.detail, id='done', head_sha='8' * 40, status='SUCCEEDED')]
        trigger.start()
        self.assertEqual(self.calls, [
            ('/flows/executions/old/command', 'POST', {'command': 'stop', 'payload': None}),
            ('/flows/flow/trigger', 'POST', {'pr_number': 7, 'head_sha': 'a' * 40})])
        saved = json.loads((Path(self.temp.name) / 'preloop-trigger/receipt.json').read_text())
        self.assertEqual(saved['challenge'], self.intent['challenge'])
        self.assertEqual(saved['execution_id'], 'execution')

    def test_start_refuses_execution_appearing_after_prepare(self):
        self.store_intent()
        self.rows = [dict(self.detail)]
        with self.assertRaises(InvalidReview):
            trigger.start()
        self.assertEqual(self.calls, [])

    def test_start_refuses_controller_substitution(self):
        self.store_intent()
        self.detail['base_sha'] = '9' * 40
        with self.assertRaises(InvalidReview):
            trigger.start()
        self.mocks[-2].assert_not_called()  # No pending status for an unbound execution.

    def test_startup_one_observation(self):
        self.store_receipt()
        trigger.startup()
        self.assertEqual(len(self.calls), 1)

    def test_startup_rejects_wrong_execution(self):
        self.store_receipt()
        self.detail['project_id'] = 'unowned'
        with self.assertRaises(InvalidReview):
            trigger.startup()
        self.assertEqual(len(self.calls), 1)

    def test_startup_rejects_missing_or_revoked_proof(self):
        self.store_receipt()
        original = copy.deepcopy(self.detail['startup_receipt'])
        for key, value in [('executor', 'unknown'), ('version', 2),
                           ('lease_revoked', '2026-11-13T15:01:00Z'),
                           ('agent_started_at', True), ('setup_completed', False)]:
            with self.subTest(key=key):
                self.detail['startup_receipt'] = dict(original, **{key: value})
                with self.assertRaises(InvalidReview):
                    trigger.startup()


if __name__ == '__main__':
    unittest.main()
