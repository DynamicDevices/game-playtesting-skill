"""Exercise the actual publisher entry point with isolated fake APIs."""
import copy
import json
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
        self.result = dict(status='success', success=True, verdict='pass', review='Complete review, no actionable defects.',
                           head_sha='a' * 40, base_sha='b' * 40, findings=[])
        self.result_envelope = dict(result_withheld_paths=[],
                                    schema_validation=dict(valid=True, error_count=0, errors=[]))
        self.detail = dict(self.intent, id=self.eid, status='SUCCEEDED', start_time='2026-11-13T15:00:00Z',
                           startup_receipt=dict(version=1, executor='hosted', checkout_verified=True,
                                                setup_completed=True, commit='a' * 40,
                                                agent_started_at='2026-11-13T15:00:01Z', lease_revoked=True))
        self.completion = dict(self.intent, execution_id=self.eid, status='SUCCEEDED', result_ready=True,
                               event_id='73db8ab4-33db-4359-a135-9f20edc61ff8',
                               result_sha256=canonical_digest(self.result))
        self.reviews, self.checks, self.statuses, self.calls = [], [], [], []
        self.preloop_calls = []
        self.result_failure = None
        self.history = [self.detail]
        self.fail_review = False
        self.readback_actor = 'github-actions[bot]'
        self.check_actor = 'github-actions'
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
            value = dict(body, id=11 + len(self.checks), app={'slug': self.check_actor})
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
            return {'sha': 'a' * 40, 'statuses': [
                {key: value for key, value in row.items() if key != 'creator'} for row in self.statuses]}
        if path.endswith('/statuses?per_page=100'):
            return self.statuses
        raise AssertionError('Unexpected fake API route: ' + path)

    def artifacts(self, _github, _binding, name, _workflow, **_kwargs):
        if name.startswith('preloop-wake-'):
            return {'completion': self.completion}
        return self.receipt if name.startswith('preloop-trigger-') else self.intent

    def preloop(self, path, _token, method='GET', body=None):
        self.assertEqual(method, 'GET', 'Publisher must never trigger another review')
        self.preloop_calls.append(path)
        if path.endswith('/result'):
            if self.result_failure:
                raise self.result_failure
            return dict(execution_id=self.eid, status=self.detail['status'], result=self.result,
                        **self.result_envelope)
        return self.detail

    def pages(self, _github, path, field=None):
        return list(self.reviews) if path.endswith('/reviews') else list(self.checks)

    def run_publisher(self, stale=False, entry=None):
        self.completion['result_sha256'] = canonical_digest(self.result)
        patches = [patch.object(publisher.runtime, 'context', return_value=(self.binding, {}, self.github)),
                   patch.object(publisher.runtime, 'artifact', side_effect=self.artifacts),
                   patch.object(publisher.runtime, 'preloop', side_effect=self.preloop),
                   patch.object(publisher.runtime, 'full_diff_sha256', return_value='c' * 64),
                   patch.object(publisher.runtime, 'executions', return_value=self.history),
                   patch.object(publisher.runtime, 'github_pages', side_effect=self.pages),
                   patch.object(publisher.runtime, 'current_pr', side_effect=InvalidReview('Stale PR') if stale else None)]
        for item in patches:
            item.start()
        try:
            return (entry or publisher.publish)()
        finally:
            for item in reversed(patches):
                item.stop()

    def test_clean_result_publishes_review_status_check_and_receipt(self):
        self.assertEqual(self.run_publisher(), 0)
        self.assertEqual(self.statuses[0]['state'], 'success')
        self.assertEqual(self.checks[0]['conclusion'], 'success')
        self.assertIn(self.eid, self.reviews[0]['body'])
        self.assertTrue((Path(self.temp.name) / 'preloop-publication/receipt.json').exists())

    def failure_receipt(self):
        return json.loads((Path(self.temp.name) / 'preloop-failure/receipt.json').read_text())

    def test_not_ready_never_fetches_result_or_creates_review(self):
        self.completion.update(result_ready=False, result_sha256=None, status='FAILED')
        self.detail['status'] = 'FAILED'
        with self.assertRaisesRegex(InvalidReview, 'no result'):
            self.run_publisher(entry=publisher.run_publication)
        self.assertFalse(any(path.endswith('/result') for path in self.preloop_calls))
        self.assertFalse(self.reviews or self.checks)
        self.assertEqual(self.statuses[0]['state'], 'error')
        self.assertTrue(self.failure_receipt()['error_status_confirmed'])

    def test_result_race_is_one_fetch_then_publication_only_recovery(self):
        self.result_failure = OSError('fixture result not yet available')
        with self.assertRaises(OSError):
            self.run_publisher(entry=publisher.run_publication)
        self.assertEqual(sum(path.endswith('/result') for path in self.preloop_calls), 1)
        self.assertFalse(self.reviews or self.checks)
        self.assertEqual(self.statuses[0]['state'], 'error')
        self.assertEqual(self.failure_receipt()['failure_type'], 'OSError')
        # A later explicitly invoked recovery uses this same owned completion.
        self.result_failure = None
        self.assertEqual(self.run_publisher(entry=publisher.run_publication), 0)
        self.assertEqual(len(self.reviews), 1)
        self.assertEqual(self.statuses[0]['state'], 'success')

    def test_http_200_error_cannot_become_review_or_success(self):
        self.result_envelope['error'] = {'code': 'result_unavailable'}
        with self.assertRaises(InvalidReview):
            self.run_publisher(entry=publisher.run_publication)
        self.assertFalse(self.reviews or self.checks)
        self.assertEqual(self.statuses[0]['state'], 'error')
        self.assertTrue(self.failure_receipt()['error_status_confirmed'])

    def test_error_status_denies_unowned_trigger_receipt(self):
        self.receipt['challenge'] = 'e' * 48
        with self.assertRaisesRegex(InvalidReview, 'Trigger receipt changed'):
            self.run_publisher(entry=publisher.run_publication)
        self.assertFalse(self.calls)
        self.assertFalse(self.failure_receipt()['error_status_confirmed'])

    def test_error_status_denies_superseded_execution(self):
        self.result_failure = OSError('fixture unavailable')
        self.history.append(dict(self.detail, id='newer', start_time='2026-11-13T15:01:00Z'))
        with self.assertRaises(OSError):
            self.run_publisher(entry=publisher.run_publication)
        self.assertFalse(self.calls)
        self.assertFalse(self.failure_receipt()['error_status_confirmed'])

    def test_error_status_denies_stale_pr_and_preserves_original_failure(self):
        self.result_failure = OSError('fixture unavailable')
        with self.assertRaises(OSError):
            self.run_publisher(stale=True, entry=publisher.run_publication)
        self.assertFalse(self.calls)
        self.assertEqual(self.failure_receipt()['failure_type'], 'OSError')
        self.assertFalse(self.failure_receipt()['error_status_confirmed'])

    def test_documented_metadata_is_kept_in_receipt_not_posted_as_findings(self):
        self.result['container_termination'] = {'reason': 'completed', 'exit_code': 0}
        self.assertEqual(self.run_publisher(), 0)
        import json
        receipt = json.loads((Path(self.temp.name) / 'preloop-publication/receipt.json').read_text())
        self.assertEqual(receipt['controller_metadata'],
                         {'container_termination': self.result['container_termination']})
        self.assertEqual(receipt['result_sha256'], canonical_digest(self.result))
        self.assertEqual(receipt['native_completion_status'], 'success')
        self.assertNotIn('container_termination', self.reviews[0]['body'])

    def test_bad_schema_or_withheld_findings_cannot_write_anything(self):
        for envelope in (dict(result_withheld_paths=[], schema_validation=None),
                         dict(result_withheld_paths=['/findings/0/evidence'],
                              schema_validation=dict(valid=True, error_count=0, errors=[])),
                         dict(result_withheld_paths=[],
                              schema_validation=dict(valid=False, error_count=1, errors=['invalid'])),
                         dict(self.result_envelope, error={'code': 'missing_result'})):
            self.result_envelope = envelope
            with self.subTest(envelope=envelope), self.assertRaises(InvalidReview):
                self.run_publisher()
            self.assertEqual(self.calls, [])

    def test_missing_marker_or_error_result_cannot_write_anything(self):
        results = [dict(self.result, status='FAILED'), {'error': 'review missing'},
                   {key: value for key, value in self.result.items() if key != 'status'}]
        for result in results:
            self.result = result
            with self.subTest(result=result), self.assertRaises(InvalidReview):
                self.run_publisher()
            self.assertEqual(self.calls, [])

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

    def test_native_stopped_and_timeout_results_are_errors_never_green(self):
        for state in ['STOPPED', 'TIMEOUT']:
            with self.subTest(state=state):
                self.detail['status'] = self.completion['status'] = state
                self.assertEqual(self.run_publisher(), 1)
                self.assertEqual(self.statuses[0]['state'], 'error')
                self.assertEqual(self.checks[0]['conclusion'], 'failure')
                (Path(self.temp.name) / 'preloop-publication/receipt.json').unlink()

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

    def test_check_readback_must_pass_before_success_status(self):
        self.check_actor = 'other'
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
        self.assertEqual(len(self.checks), 1)

    def test_duplicate_or_substituted_check_intent_blocks_recovery(self):
        self.run_publisher()
        prior = copy.deepcopy(self.checks[0])
        self.checks.append(copy.deepcopy(prior))
        writes = len(self.calls)
        with self.assertRaisesRegex(InvalidReview, 'Duplicate check'):
            self.run_publisher()
        self.assertEqual(len(self.calls), writes)
        self.checks.pop()
        self.checks[0]['app'] = {'slug': 'other'}
        with self.assertRaisesRegex(InvalidReview, 'Wrong existing check'):
            self.run_publisher()
        self.assertEqual(len(self.calls), writes)

    def test_result_substitution_refused_before_writes(self):
        self.receipt['execution_id'] = 'different'
        with self.assertRaises(InvalidReview):
            self.run_publisher()
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
