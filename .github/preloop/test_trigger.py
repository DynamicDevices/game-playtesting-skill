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
    def test_automatic_draft_events_skip_before_privileged_trigger_work(self):
        workflow = (Path(__file__).resolve().parents[1] / 'workflows/preloop-review-trigger.yml').read_text()
        self.assertIn("  trigger:\n    if: github.event_name != 'pull_request_target' || "
                      "github.event.pull_request.draft == false\n    runs-on:", workflow)
        self.assertIn('types: [opened, synchronize, reopened, ready_for_review]', workflow)
        # Manual dispatch retains runtime.current_pr's draft denial; it cannot
        # use this skip to misrepresent an invalid selection as a review.
        for event, draft, should_run in [('pull_request_target', True, False),
                                         ('pull_request_target', False, True),
                                         ('workflow_dispatch', None, True)]:
            with self.subTest(event=event, draft=draft):
                self.assertEqual(event != 'pull_request_target' or draft is False, should_run)

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
        self.detail = dict(self.intent, id='execution', status='RUNNING', startup_receipt=dict(
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
                   patch.object(runtime, 'verify_live_service'),
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

    def test_accepted_execution_remains_observable_after_pending_status_failure(self):
        self.store_intent()
        with patch.object(runtime, 'commit_status', side_effect=OSError('Synthetic status failure')):
            with self.assertRaises(OSError):
                trigger.start()
        runtime.output.assert_called_with(execution_id='execution')
        trigger.startup()
        self.assertEqual(self.calls, [('/flows/flow/trigger', 'POST',
                                     {'pr_number': 7, 'head_sha': 'a' * 40}),
                                    ('/flows/executions/execution', 'GET', None)])

    def test_workflow_observes_startup_even_when_launch_step_failed_after_acceptance(self):
        workflow = Path(__file__).resolve().parents[1] / 'workflows/preloop-review-trigger.yml'
        self.assertIn("      - name: Validate native startup once\n"
                      "        if: always() && steps.start.outputs.execution_id != ''\n",
                      workflow.read_text())

    def test_prepare_refuses_prior_intent(self):
        self.journal['total_count'] = 1
        with self.assertRaises(InvalidReview):
            trigger.prepare()

    def diagnostic(self):
        source = '487d988a-53ad-4f5d-8b84-d77bb733676f'
        self.permit = dict(source_execution_id=source, nonce='1' * 48,
                           expires_at='2099-01-01T00:00:00Z', pr_number=7,
                           head_sha='a' * 40, base_sha='b' * 40,
                           diff_sha256='c' * 64, model_id='model', flow_config_sha256='f' * 64)
        self.binding['native_ci_contract']['diagnostic_rerun'] = self.permit
        self.rows = [dict(self.detail, id=source, status='SUCCEEDED')]
        os.environ['GITHUB_EVENT_NAME'] = 'workflow_dispatch'
        self.event.write_text(json.dumps({'inputs': {
            'pr_number': '7', 'diagnostic_execution_id': source}}))

    def prepare_diagnostic(self):
        self.diagnostic()
        trigger.prepare()
        self.intent = json.loads((Path(self.temp.name) / 'preloop-intent/receipt.json').read_text())
        self.journal = dict(total_count=1, artifacts=[dict(expired=False, workflow_run={'id': 10})])

    def test_diagnostic_explicit_permit_preserves_original_and_posts_no_status(self):
        self.prepare_diagnostic()
        before = copy.deepcopy(self.rows)
        self.assertEqual(trigger.intent_name(self.intent), 'preloop-diagnostic-' + '1' * 48)
        trigger.start()
        self.assertEqual(self.calls, [('/flows/flow/trigger', 'POST',
                                       {'pr_number': 7, 'head_sha': 'a' * 40})])
        runtime.commit_status.assert_not_called()
        self.assertEqual(before, self.rows)
        saved = json.loads((Path(self.temp.name) / 'preloop-trigger/receipt.json').read_text())
        self.assertEqual(saved['diagnostic_rerun'], self.permit)

    def test_diagnostic_needs_exact_signed_permit(self):
        for field, value in [('source_execution_id', 'f' * 36), ('head_sha', '9' * 40),
                             ('base_sha', '9' * 40), ('pr_number', 8),
                             ('model_id', 'other'), ('flow_config_sha256', '9' * 64),
                             ('diff_sha256', '9' * 64), ('nonce', 'bad'),
                             ('expires_at', '2000-01-01T00:00:00Z'),
                             ('expires_at', '2099-01-01T00:00:00'),
                             ('expires_at', 'invalid')]:
            with self.subTest(field=field, value=value):
                self.diagnostic()
                self.permit[field] = value
                with self.assertRaises(InvalidReview):
                    trigger.prepare()
        self.assertEqual(self.calls, [])

    def test_diagnostic_missing_or_extra_policy_is_denied(self):
        self.diagnostic()
        del self.binding['native_ci_contract']['diagnostic_rerun']
        with self.assertRaises(InvalidReview):
            trigger.prepare()
        self.diagnostic()
        self.permit['arbitrary_override'] = True
        with self.assertRaises(InvalidReview):
            trigger.prepare()

    def test_diagnostic_cannot_be_selected_by_automatic_event(self):
        self.diagnostic()
        os.environ['GITHUB_EVENT_NAME'] = 'pull_request_target'
        data = json.loads(self.event.read_text())
        data['number'] = 7
        self.event.write_text(json.dumps(data))
        with self.assertRaises(InvalidReview):
            trigger.prepare()

    def test_diagnostic_cannot_reuse_expired_or_existing_nonce_artifact(self):
        self.diagnostic()
        self.journal = dict(total_count=1, artifacts=[dict(expired=True)])
        with self.assertRaises(InvalidReview):
            trigger.prepare()

    def test_diagnostic_rejects_missing_wrong_or_nonterminal_source(self):
        for change in ('missing', 'flow_id', 'project_id', 'repository_identifier',
                       'status', 'additional', 'running-pr'):
            with self.subTest(change=change):
                self.diagnostic()
                if change == 'missing':
                    self.rows = []
                elif change == 'additional':
                    self.rows.append(dict(self.rows[0], id='another'))
                elif change == 'running-pr':
                    self.rows.append(dict(self.rows[0], id='another', head_sha='9' * 40,
                                          status='RUNNING'))
                else:
                    self.rows[0][change] = 'RUNNING' if change == 'status' else 'wrong'
                with self.assertRaises(InvalidReview):
                    trigger.prepare()
        self.assertEqual(self.calls, [])

    def test_diagnostic_rechecks_permit_and_history_before_launch(self):
        self.prepare_diagnostic()
        self.rows.append(dict(self.rows[0], id='another'))
        with self.assertRaises(InvalidReview):
            trigger.start()
        self.assertEqual(self.calls, [])

    def test_diagnostic_changed_operator_input_is_denied_before_launch(self):
        self.prepare_diagnostic()
        self.event.write_text(json.dumps({'inputs': {'pr_number': '7'}}))
        with self.assertRaises(InvalidReview):
            trigger.start()
        self.assertEqual(self.calls, [])

    def test_diagnostic_cannot_treat_original_execution_as_a_new_launch(self):
        self.prepare_diagnostic()
        self.detail['id'] = self.permit['source_execution_id']
        with self.assertRaises(InvalidReview):
            trigger.start()
        runtime.commit_status.assert_not_called()

    def test_unused_diagnostic_permit_does_not_relax_normal_duplicate_gate(self):
        self.diagnostic()
        self.event.write_text(json.dumps({'inputs': {'pr_number': '7'}}))
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

    def test_native_terminal_executions_are_not_stopped_again(self):
        self.store_intent()
        self.rows = [dict(self.detail, id='old-stopped', head_sha='f' * 40, status='STOPPED'),
                     dict(self.detail, id='old-timeout', head_sha='e' * 40, status='TIMEOUT')]
        trigger.start()
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(self.calls[0][0].endswith('/trigger'))

    def test_start_refuses_controller_substitution(self):
        self.store_intent()
        self.detail['base_sha'] = '9' * 40
        with self.assertRaises(InvalidReview):
            trigger.start()
        self.mocks[-2].assert_not_called()  # No pending status for an unbound execution.

    def test_live_revocation_prevents_native_trigger(self):
        self.store_intent()
        with patch.object(runtime, 'verify_live_service', side_effect=InvalidReview('suspended')):
            with self.assertRaisesRegex(InvalidReview, 'suspended'):
                trigger.start()
        self.assertEqual(self.calls, [])

    def test_live_revocation_rechecked_between_stop_and_start(self):
        self.store_intent()
        self.rows = [dict(self.detail, id='old', head_sha='f' * 40)]
        with patch.object(runtime, 'verify_live_service', side_effect=[None, InvalidReview('suspended')]):
            with self.assertRaisesRegex(InvalidReview, 'suspended'):
                trigger.start()
        self.assertEqual(len(self.calls), 1)
        self.assertIn('/old/command', self.calls[0][0])

    def test_startup_one_observation(self):
        self.store_receipt()
        trigger.startup()
        self.assertEqual(len(self.calls), 1)
        saved = json.loads((Path(self.temp.name) / 'preloop-startup/receipt.json').read_text())
        self.assertEqual(saved['status'], 'RUNNING')
        self.assertEqual(saved['startup_receipt']['commit'], self.intent['head_sha'])

    def test_queued_and_failed_launches_are_saved_but_not_accepted(self):
        self.store_receipt()
        for state in ['PENDING', 'FAILED', 'CANCELLED', 'TIMED_OUT']:
            self.detail['status'] = state
            with self.subTest(state=state), self.assertRaises(InvalidReview):
                trigger.startup()
            saved = Path(self.temp.name) / 'preloop-startup/receipt.json'
            self.assertEqual(json.loads(saved.read_text())['status'], state)
            saved.unlink()
        self.assertEqual(len(self.calls), 4)  # One request per explicit invocation, no retry.

    def test_pending_startup_is_deferred_not_verified_without_polling(self):
        self.store_receipt()
        self.detail.update(startup_receipt=None, startup_receipt_status='pending')
        with patch.object(runtime, 'output') as output, patch('builtins.print') as log:
            trigger.startup()
        self.assertEqual(len(self.calls), 1)
        output.assert_called_once_with(startup_verified='false', startup_receipt_status='pending')
        self.assertIn('proof pending', log.call_args.args[0])
        saved = json.loads((Path(self.temp.name) / 'preloop-startup/receipt.json').read_text())
        self.assertIsNone(saved['startup_receipt'])
        self.assertEqual(saved['startup_receipt_status'], 'pending')

    def test_pending_cannot_hide_terminal_or_contradictory_receipts(self):
        self.store_receipt()
        original = copy.deepcopy(self.detail['startup_receipt'])
        for state, proof in [('SUCCEEDED', None), ('FAILED', None), ('PENDING', None),
                             ('RUNNING', {}), ('RUNNING', original), ('RUNNING', False)]:
            self.detail.update(status=state, startup_receipt=proof, startup_receipt_status='pending')
            with self.subTest(state=state, proof=proof), self.assertRaises(InvalidReview):
                trigger.startup()
            (Path(self.temp.name) / 'preloop-startup/receipt.json').unlink()

    def test_startup_state_does_not_replace_or_override_proof(self):
        self.store_receipt()
        original = copy.deepcopy(self.detail['startup_receipt'])
        for state, proof in [('failed', original), ('unknown', original),
                             ('recorded', None), (None, None)]:
            self.detail.update(startup_receipt=proof, startup_receipt_status=state)
            with self.subTest(state=state), self.assertRaises(InvalidReview):
                trigger.startup()
            (Path(self.temp.name) / 'preloop-startup/receipt.json').unlink()

    def test_recorded_startup_requires_full_proof(self):
        self.store_receipt()
        self.detail['startup_receipt_status'] = 'recorded'
        with patch.object(runtime, 'output') as output:
            trigger.startup()
        output.assert_called_once_with(startup_verified='true', startup_receipt_status='recorded')
        self.assertEqual(len(self.calls), 1)

    def test_startup_rejects_wrong_execution(self):
        self.store_receipt()
        self.detail['project_id'] = 'unowned'
        with self.assertRaises(InvalidReview):
            trigger.startup()
        self.assertEqual(len(self.calls), 1)

    def test_startup_version_requires_an_integer_not_an_equal_boolean_or_float(self):
        self.store_receipt()
        for value in (True, 1.0, "1", None):
            with self.subTest(version=value):
                self.detail['startup_receipt']['version'] = value
                with self.assertRaises(InvalidReview):
                    trigger.startup()
                (Path(self.temp.name) / 'preloop-startup/receipt.json').unlink()
        self.detail['startup_receipt']['version'] = 1
        trigger.startup()
        self.assertEqual(len(self.calls), 5)

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
                (Path(self.temp.name) / 'preloop-startup/receipt.json').unlink()

    def test_completed_startup_requires_confirmed_cleanup(self):
        self.store_receipt()
        self.detail['status'] = 'SUCCEEDED'
        for value in [None, False, 1]:
            with self.subTest(value=value):
                self.detail['startup_receipt']['lease_revoked'] = value
                with self.assertRaises(InvalidReview):
                    trigger.startup()
                (Path(self.temp.name) / 'preloop-startup/receipt.json').unlink()
        self.detail['startup_receipt']['lease_revoked'] = True
        trigger.startup()

    def test_running_startup_rejects_already_revoked_lease(self):
        self.store_receipt()
        self.detail['startup_receipt']['lease_revoked'] = True
        with self.assertRaises(InvalidReview):
            trigger.startup()


if __name__ == '__main__':
    unittest.main()
