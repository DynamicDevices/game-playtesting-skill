"""Exercise the actual publisher entry point with isolated fake APIs."""
import copy
import hashlib
import io
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
        self.failed_trigger = False
        self.history = [self.detail]
        self.fail_review = False
        self.fail_check = False
        self.hide_checks = False
        self.wakes = [dict(name='preloop-wake-' + self.eid, expired=False, workflow_run={'id': 12})]
        self.readback_actor = 'github-actions[bot]'
        self.check_actor = 'github-actions'
        self.normalize_check_url = False
        self.preserve_old_conclusion = False
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
            value = dict(body, id=11 + len(self.checks), app={'id': 15368, 'slug': self.check_actor})
            self.checks.append(value)
            if self.fail_check:
                raise OSError('Synthetic lost check response')
            return value
        if '/check-runs/' in path:
            value = next(row for row in self.checks if row['id'] == int(path.rsplit('/', 1)[1]))
            if method == 'PATCH':
                if 'conclusion' in body and body['conclusion'] not in (
                        'action_required', 'cancelled', 'failure', 'neutral',
                        'success', 'skipped', 'stale', 'timed_out'):
                    raise InvalidReview('Synthetic HTTP422 invalid conclusion')
                value.update(body)
                if 'conclusion' in body:
                    value['status'] = 'completed'
                elif body.get('status') == 'in_progress' and not self.preserve_old_conclusion:
                    # Simulate an unfinished API response. The separate stale
                    # conclusion test ensures production never assumes this.
                    value['conclusion'] = None
            if method == 'GET' and self.normalize_check_url:
                return dict(value, details_url='https://github.com/example/repository/runs/' + str(value['id']))
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
        if _workflow == 'preloop-review-trigger.yml' and self.failed_trigger and not _kwargs.get('allow_failed'):
            raise InvalidReview('Artifact workflow has not completed successfully')
        if name.startswith('preloop-wake-'):
            return {'completion': self.completion,
                    'authenticated_run_id': _kwargs.get('run_id', os.environ['GITHUB_RUN_ID'])}
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
        if field == 'artifacts': return list(self.wakes)
        if self.hide_checks and '/check-runs?' in path: return []
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

    def test_failed_trigger_blocks_review_but_allows_owned_error_cleanup(self):
        # Even a complete, valid later controller result cannot erase a failed
        # startup workflow. Only the failure-status path admits its receipts.
        self.failed_trigger = True
        with self.assertRaisesRegex(InvalidReview, 'not completed successfully'):
            self.run_publisher()
        self.assertFalse(self.reviews)
        self.assertFalse(self.checks)
        self.assertFalse(self.preloop_calls)
        self.run_publisher(entry=publisher.publish_error_status)
        self.assertEqual([row['state'] for row in self.statuses], ['error'])
        self.assertFalse(self.reviews)
        self.assertFalse(self.checks)

    def test_github_normalized_get_reuses_review_and_check_after_readback_failure(self):
        self.normalize_check_url = True
        self.binding['publication_finalizer'] = {'explicit_posture_approval': True}
        self.assertEqual(self.run_publisher(), 0)
        self.checks[0].update(status='completed', conclusion='failure')
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, GITHUB_RUN_ID='13', RUNNER_TEMP=folder):
            self.assertEqual(self.run_publisher(), 0)
        self.assertEqual(len(self.reviews), 1)
        self.assertEqual(len(self.checks), 1)
        self.assertEqual(self.checks[0]['status'], 'in_progress')
        self.assertIsNone(self.checks[0].get('conclusion'))
        self.assertIn('/actions/runs/13', self.checks[0]['output']['summary'])

    def test_late_failure_accepts_normalized_url_but_not_another_producer_receipt(self):
        self.normalize_check_url = True
        self.assertEqual(self.run_publisher(), 0)
        with patch.dict(os.environ, GITHUB_RUN_ID='13'), self.assertRaises(InvalidReview):
            self.run_publisher(entry=publisher.publish_error_status)
        self.run_publisher(entry=publisher.publish_error_status)
        self.assertEqual(self.checks[0]['conclusion'], 'failure')
        self.assertEqual(self.statuses[0]['state'], 'error')
        self.assertTrue((Path(self.temp.name) / 'preloop-publication/receipt.json').exists())

    def test_failed_check_correction_still_attempts_owned_error_status(self):
        self.assertEqual(self.run_publisher(), 0)
        original = self.github
        def request(path, method='GET', body=None):
            if '/check-runs/' in path and method == 'PATCH':
                raise OSError('Synthetic check correction failure')
            return original(path, method, body)
        with patch.object(self, 'github', side_effect=request):
            with self.assertRaisesRegex(OSError, 'Synthetic check correction failure'):
                self.run_publisher(entry=publisher.publish_error_status)
        self.assertEqual(self.statuses[0]['state'], 'error')
        self.assertEqual(len(self.reviews), 1)

    def test_failed_check_correction_cannot_write_error_after_supersession(self):
        self.assertEqual(self.run_publisher(), 0)
        original = self.github
        def request(path, method='GET', body=None):
            if '/check-runs/' in path and method == 'PATCH':
                raise OSError('Synthetic check correction failure')
            return original(path, method, body)
        with patch.object(self, 'github', side_effect=request), \
             patch.object(publisher, 'no_supersession', side_effect=[None, InvalidReview('Superseded')]):
            with self.assertRaisesRegex(OSError, 'Synthetic check correction failure'):
                self.run_publisher(entry=publisher.publish_error_status)
        self.assertEqual(len(self.statuses), 1)

    def test_completion_enabled_publisher_never_releases_green_itself(self):
        self.binding['publication_finalizer'] = {'explicit_posture_approval': True}
        self.assertEqual(self.run_publisher(), 0)
        self.assertEqual(self.statuses[0]['state'], 'pending')
        self.assertEqual(self.checks[0]['status'], 'in_progress')
        self.assertIsNone(self.checks[0].get('conclusion'))
        self.assertEqual(len(self.reviews), 1)

    def test_pending_update_omits_conclusion_and_fake_rejects_invalid_enum(self):
        self.binding['publication_finalizer'] = {'explicit_posture_approval': True}
        self.assertEqual(self.run_publisher(), 0)
        updates = [body for path, method, body in self.calls
                   if '/check-runs/' in path and method == 'PATCH' and body.get('status') == 'in_progress']
        self.assertEqual(len(updates), 1)
        self.assertNotIn('conclusion', updates[0])
        for conclusion in (None, True, 1, 'pending', ''):
            with self.subTest(conclusion=conclusion), self.assertRaisesRegex(InvalidReview, 'HTTP422'):
                self.github('/check-runs/11', 'PATCH', {'status': 'in_progress', 'conclusion': conclusion})
        self.github('/check-runs/11', 'PATCH', {'status': 'in_progress', 'conclusion': 'failure'})
        self.assertEqual(self.checks[0]['status'], 'completed')

    def test_recovery_refuses_uncleared_old_conclusion_without_duplicate_post(self):
        self.binding['publication_finalizer'] = {'explicit_posture_approval': True}
        self.assertEqual(self.run_publisher(), 0)
        self.checks[0].update(status='completed', conclusion='failure')
        self.preserve_old_conclusion = True
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, GITHUB_RUN_ID='13', RUNNER_TEMP=folder):
            with self.assertRaisesRegex(InvalidReview, 'Review check readback mismatch'):
                self.run_publisher()
            self.assertFalse((Path(folder) / 'preloop-publication/receipt.json').exists())
        self.assertEqual(len(self.reviews), 1)
        self.assertEqual(len(self.checks), 1)
        self.assertEqual(self.checks[0]['conclusion'], 'failure')

    def test_lost_initial_check_response_cannot_recreate_on_empty_later_listing(self):
        self.fail_check = True
        with self.assertRaisesRegex(OSError, 'lost check response'): self.run_publisher()
        self.assertEqual(len(self.checks), 1)
        self.fail_check = False
        self.hide_checks = True
        self.wakes.append(dict(name='preloop-wake-' + self.eid, expired=False, workflow_run={'id': 13}))
        with patch.dict(os.environ, GITHUB_RUN_ID='13'), self.assertRaisesRegex(
                InvalidReview, 'durable publication intent'):
            self.run_publisher()
        self.assertEqual(len(self.checks), 1)
        self.assertFalse(self.reviews)

    def test_missing_wake_or_repeated_run_cannot_create_a_check(self):
        with patch.dict(os.environ, GITHUB_RUN_ATTEMPT='2'), self.assertRaisesRegex(
                InvalidReview, 'repeated run'):
            self.run_publisher()
        self.wakes.clear()
        with self.assertRaisesRegex(InvalidReview, 'durable publication intent'):
            self.run_publisher()
        self.assertFalse(self.checks or self.reviews)

    def test_diagnostic_cannot_publish_review_or_error_status(self):
        self.receipt['diagnostic_rerun'] = {'nonce': '1' * 48}
        for entry in (publisher.publish, publisher.publish_error_status):
            with self.subTest(entry=entry.__name__):
                with self.assertRaisesRegex(InvalidReview, 'Diagnostic reproduction'):
                    self.run_publisher(entry=entry)
        self.assertEqual(self.reviews, [])
        self.assertEqual(self.statuses, [])
        self.assertEqual(self.checks, [])
        self.assertEqual(self.preloop_calls, [])

    def configure_recovery(self):
        self.binding['publication_recovery'] = dict(
            execution_id=self.eid, pr_number=7, head_sha='a' * 40, base_sha='b' * 40,
            result_sha256=canonical_digest(self.result), original_publisher_run_id='11',
            trigger_run_id='10', failed_before_check_creation=True, current_target_sha='b' * 40)
        self.wakes.append(dict(name='preloop-wake-' + self.eid, expired=False,
                               workflow_run={'id': 11}))
        self.event.write_text(json.dumps(dict(inputs=dict(
            execution_id=self.eid, authenticated_run_id='11'))))

    def test_signed_publish_only_reconciliation_can_create_once(self):
        self.configure_recovery()
        self.result_envelope['result_withheld_paths'] = ['/container_termination']
        with patch.dict(os.environ, GITHUB_EVENT_NAME='workflow_dispatch'):
            self.assertEqual(self.run_publisher(), 0)
        self.assertEqual(len(self.checks), 1)
        self.assertEqual(len(self.reviews), 1)
        # A subsequent run cannot repeat creation after an ambiguous/lost check.
        self.hide_checks = True
        self.wakes.append(dict(name='preloop-wake-' + self.eid, expired=False,
                               workflow_run={'id': 13}))
        with patch.dict(os.environ, GITHUB_RUN_ID='13', GITHUB_EVENT_NAME='workflow_dispatch'):
            with self.assertRaises(InvalidReview): self.run_publisher()
        self.assertEqual(len(self.checks), 1)

    def configure_retained_check(self):
        self.configure_recovery()
        recovery = self.binding['publication_recovery']
        recovery['current_target_sha'] = 'e' * 40
        with patch.dict(os.environ, GITHUB_EVENT_NAME='workflow_dispatch'):
            self.assertEqual(self.run_publisher(), 0)
        recovery['existing_publication'] = dict(review_id=22, check_id=11,
            claim_sha256=self.checks[0]['external_id'].split(':', 1)[1],
            body_sha256=hashlib.sha256(self.reviews[0]['body'].encode()).hexdigest(),
            original_target_sha='e' * 40, preserve_failed_check=True)
        recovery['current_target_sha'] = 'f' * 40
        self.binding['publication_finalizer'] = dict(explicit_posture_approval=True,
            workflow_path='.github/workflows/preloop-review-finalize.yml', event='workflow_run',
            producer_path='.github/workflows/preloop-review-publish.yml')
        self.checks[0].update(status='completed', conclusion='failure',
                             details_url='https://github.com/example/repository/runs/11')
        self.preserve_old_conclusion = True
        self.calls.clear()

    def test_retained_check_has_zero_producer_check_writes_or_duplicate_posts(self):
        self.configure_retained_check()
        original_check = copy.deepcopy(self.checks[0])
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, GITHUB_RUN_ID='13', RUNNER_TEMP=folder):
            self.assertEqual(self.run_publisher(), 0)
            receipt = json.loads((Path(folder) / 'preloop-publication/receipt.json').read_text())
            self.assertEqual(receipt['pending_check_mode'], 'retained_failure')
            self.assertEqual(receipt['historical_target_sha'], 'f' * 40)
        self.assertEqual(self.checks[0], original_check)
        self.assertEqual(len(self.checks), 1)
        self.assertEqual(len(self.reviews), 1)
        self.assertEqual(self.statuses[0]['state'], 'pending')
        self.assertTrue(all(method == 'GET' or '/statuses/' in path for path, method, _ in self.calls))

    def test_retained_check_substitutions_and_invalid_optins_deny_all_writes(self):
        self.configure_retained_check()
        cases = [('status', 'in_progress'), ('conclusion', 'success'), ('head_sha', 'c' * 40),
                 ('id', 99), ('external_id', 'briar-preloop:' + '0' * 64),
                 ('app', {'id': 15369, 'slug': 'github-actions'}),
                 ('output', {'text': 'substituted'})]
        for key, value in cases:
            saved = self.checks[0][key];self.checks[0][key] = value;self.calls.clear()
            with self.subTest(key=key), self.assertRaises(InvalidReview): self.run_publisher()
            self.assertTrue(all(method == 'GET' for _, method, _ in self.calls))
            self.checks[0][key] = saved
        existing = self.binding['publication_recovery']['existing_publication']
        for value in (False, 'true', 1, None):
            existing['preserve_failed_check'] = value;self.calls.clear()
            with self.subTest(optin=value), self.assertRaises(InvalidReview): self.run_publisher()
            self.assertFalse(self.calls)
        existing['preserve_failed_check'] = True
        self.binding['publication_finalizer'] = {}
        with self.assertRaises(InvalidReview): self.run_publisher()

    def test_retained_late_failure_leaves_check_failed_and_sets_error_status(self):
        self.configure_retained_check()
        original_check = copy.deepcopy(self.checks[0])
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, GITHUB_RUN_ID='13', RUNNER_TEMP=folder):
            self.assertEqual(self.run_publisher(), 0)
            self.run_publisher(entry=publisher.publish_error_status)
        self.assertEqual(self.checks[0], original_check)
        self.assertEqual(self.statuses[0]['state'], 'error')
        self.assertTrue(all(method == 'GET' or '/statuses/' in path for path, method, _ in self.calls))

    def test_retained_receipt_failure_never_patches_check_in_exception_cleanup(self):
        self.configure_retained_check()
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, GITHUB_RUN_ID='13', RUNNER_TEMP=folder), \
             patch.object(publisher.runtime, 'write_receipt', side_effect=OSError('Synthetic disk failure')):
            with self.assertRaises(OSError): self.run_publisher()
        self.assertTrue(all(method == 'GET' or '/statuses/' in path for path, method, _ in self.calls))

    def test_reconciliation_denies_wrong_or_incomplete_signed_tuple(self):
        self.configure_recovery()
        original = copy.deepcopy(self.binding['publication_recovery'])
        mutations = dict(execution_id='0' * 36, pr_number=8, head_sha='e' * 40,
                         base_sha='e' * 40, result_sha256='e' * 64,
                         trigger_run_id='9', original_publisher_run_id='9',
                         failed_before_check_creation=False)
        for key, value in mutations.items():
            self.binding['publication_recovery'] = dict(original, **{key: value})
            with self.subTest(key=key), patch.dict(os.environ, GITHUB_EVENT_NAME='workflow_dispatch'):
                with self.assertRaises(InvalidReview): self.run_publisher()
            self.assertFalse(self.checks or self.reviews)
        self.binding.pop('publication_recovery')
        with self.assertRaises(InvalidReview): self.run_publisher()

    def test_reconciliation_denies_other_dispatch_and_wake_sets(self):
        self.configure_recovery()
        saved_event, saved_wakes = self.event.read_text(), copy.deepcopy(self.wakes)
        for event in ({}, {'inputs': {'execution_id': self.eid, 'authenticated_run_id': '9'}},
                      {'inputs': {'execution_id': self.eid, 'authenticated_run_id': '11', 'extra': 'x'}}):
            self.event.write_text(json.dumps(event))
            with patch.dict(os.environ, GITHUB_EVENT_NAME='workflow_dispatch'):
                with self.assertRaises(InvalidReview): self.run_publisher()
        self.event.write_text(saved_event)
        with patch.dict(os.environ, GITHUB_EVENT_NAME='repository_dispatch'):
            with self.assertRaises(InvalidReview): self.run_publisher()
        for rows in ([], saved_wakes[:1], saved_wakes[1:], [saved_wakes[0]] * 2,
                     saved_wakes + [saved_wakes[0]],
                     [dict(saved_wakes[0], expired=True), saved_wakes[1]]):
            self.wakes = rows
            with patch.dict(os.environ, GITHUB_EVENT_NAME='workflow_dispatch'):
                with self.assertRaises(InvalidReview): self.run_publisher()
        self.assertFalse(self.checks or self.reviews)

    def test_controller_redaction_never_hides_reviewer_fields(self):
        for paths in (['/findings'], ['/review'], ['/container_termination', '/findings']):
            self.result_envelope['result_withheld_paths'] = paths
            with self.assertRaises(InvalidReview): self.run_publisher()
        self.assertFalse(self.checks or self.reviews)

    def test_historical_review_identifies_original_base_and_current_target(self):
        self.configure_recovery()
        self.binding['publication_recovery']['current_target_sha'] = 'e' * 40
        with patch.dict(os.environ, GITHUB_EVENT_NAME='workflow_dispatch'):
            self.assertEqual(self.run_publisher(), 0)
        self.assertIn('Original reviewed base: ' + 'b' * 40, self.reviews[0]['body'])
        self.assertIn('not approval against the advanced target', self.reviews[0]['body'])
        receipt = json.loads((Path(self.temp.name) / 'preloop-publication/receipt.json').read_text())
        self.assertEqual(receipt['historical_target_sha'], 'e' * 40)

    def test_exact_existing_historical_body_survives_advanced_repair_target_without_post(self):
        self.configure_recovery()
        recovery = self.binding['publication_recovery']
        recovery['current_target_sha'] = 'e' * 40
        self.normalize_check_url = True
        with patch.dict(os.environ, GITHUB_EVENT_NAME='workflow_dispatch'):
            self.assertEqual(self.run_publisher(), 0)
        body = self.reviews[0]['body']
        self.checks[0].update(status='completed', conclusion='failure')
        recovery['current_target_sha'] = 'f' * 40
        recovery['existing_publication'] = dict(review_id=22, check_id=11,
            claim_sha256=self.checks[0]['external_id'].split(':', 1)[1],
            body_sha256=hashlib.sha256(body.encode()).hexdigest(), original_target_sha='e' * 40)
        self.binding['publication_finalizer'] = {'explicit_posture_approval': True}
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, GITHUB_RUN_ID='13', RUNNER_TEMP=folder):
            self.assertEqual(self.run_publisher(), 0)
            receipt = json.loads((Path(folder) / 'preloop-publication/receipt.json').read_text())
            self.assertEqual(receipt['historical_target_sha'], 'f' * 40)
            self.assertEqual(receipt['review_body_sha256'], recovery['existing_publication']['body_sha256'])
        self.assertEqual(self.reviews[0]['body'], body)
        self.assertEqual(len(self.reviews), 1)
        self.assertEqual(len(self.checks), 1)
        for key, value in [('body_sha256', '0' * 64), ('original_target_sha', 'a' * 40),
                           ('review_id', 23), ('check_id', 12), ('claim_sha256', '0' * 64)]:
            original = recovery['existing_publication'][key]
            recovery['existing_publication'][key] = value
            calls = len(self.calls)
            with self.subTest(key=key), self.assertRaises(InvalidReview): self.run_publisher()
            self.assertTrue(all(method == 'GET' for _, method, _ in self.calls[calls:]))
            recovery['existing_publication'][key] = original

    def test_late_upload_failure_replaces_preliminary_green_without_reposting(self):
        self.assertEqual(self.run_publisher(), 0)
        self.run_publisher(entry=publisher.publish_error_status)
        self.assertEqual(self.checks[0]['conclusion'], 'failure')
        self.assertEqual(self.statuses[0]['state'], 'error')
        self.assertEqual(len(self.reviews), 1)

    def test_delivered_blocking_review_survives_expected_failed_job_cleanup(self):
        self.result.update(success=False, verdict='changes_requested', findings=[dict(
            severity='HIGH', location='file.py:1', problem='Problem', evidence='Evidence', fix='Fix')])
        self.assertEqual(self.run_publisher(), 1)
        with patch.dict(os.environ, PRELOOP_PUBLISH_OUTCOME='failure',
                        PRELOOP_PUBLICATION_UPLOAD_OUTCOME='success'):
            self.run_publisher(entry=publisher.publish_error_status)
        self.assertEqual(self.statuses[0]['state'], 'failure')
        self.assertEqual(self.checks[0]['conclusion'], 'failure')
        self.assertEqual(len(self.statuses), 1)
        with patch.dict(os.environ, PRELOOP_PUBLISH_OUTCOME='failure',
                        PRELOOP_PUBLICATION_UPLOAD_OUTCOME='failure'):
            self.run_publisher(entry=publisher.publish_error_status)
        self.assertEqual(self.statuses[0]['state'], 'error')

    def test_late_failure_cannot_patch_another_runs_check(self):
        self.assertEqual(self.run_publisher(), 0)
        self.checks[0]['details_url'] = 'https://github.com/example/repository/actions/runs/99'
        with self.assertRaises(InvalidReview): self.run_publisher(entry=publisher.publish_error_status)
        self.assertEqual(self.checks[0]['conclusion'], 'success')

    def test_ambiguous_review_send_cannot_repost_using_an_existing_check(self):
        self.fail_review = True
        with self.assertRaises(InvalidReview): self.run_publisher()
        self.fail_review = False
        with self.assertRaisesRegex(InvalidReview, 'Ambiguous earlier review send'): self.run_publisher()
        self.assertFalse(self.reviews)

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

    def test_different_delivery_event_reuses_execution_publication(self):
        self.assertEqual(self.run_publisher(), 0)
        (Path(self.temp.name) / 'preloop-publication/receipt.json').unlink()
        self.completion['event_id'] = 'a34ad8f4-e998-4223-8d44-be3e30781216'
        os.environ['GITHUB_RUN_ID'] = '13'
        self.assertEqual(self.run_publisher(), 0)
        self.assertEqual(len(self.reviews), 1)
        self.assertEqual(len(self.checks), 1)
        self.assertEqual(sum(path.endswith('/reviews') and method == 'POST'
                             for path, method, _ in self.calls), 1)

    def test_changed_result_for_published_execution_refuses_all_writes(self):
        self.run_publisher()
        self.result['review'] = 'Complete revised review with a different result.'
        writes = len(self.calls)
        with self.assertRaisesRegex(InvalidReview, 'different publication claim'):
            self.run_publisher()
        self.assertEqual(len(self.calls), writes)
        self.assertEqual((len(self.reviews), len(self.checks)), (1, 1))

    def test_conflicting_check_claim_refuses_before_new_review(self):
        self.fail_review = True
        with self.assertRaises(InvalidReview):
            self.run_publisher()
        self.fail_review = False
        self.result['review'] = 'Complete revised review with a different result.'
        writes = len(self.calls)
        with self.assertRaisesRegex(InvalidReview, 'different check claim'):
            self.run_publisher()
        self.assertEqual(len(self.calls), writes)
        self.assertFalse(self.reviews)

    def test_failure_receipt_error_does_not_mask_primary_exception(self):
        primary = OSError('Synthetic result-fetch failure')
        self.result_failure = primary
        with patch.object(publisher.runtime, 'write_receipt', side_effect=PermissionError('secondary')), \
             patch('sys.stderr', new_callable=io.StringIO) as errors:
            with self.assertRaises(OSError) as raised:
                self.run_publisher(entry=publisher.run_publication)
        self.assertIs(raised.exception, primary)
        self.assertIn('failure receipt was not saved: PermissionError', errors.getvalue())

    def test_failure_check_error_does_not_mask_review_send_failure(self):
        original = self.github
        def fail_reporting(path, method='GET', body=None):
            if '/check-runs/' in path and method == 'PATCH':
                raise OSError('Synthetic reporting failure')
            return original(path, method, body)
        self.fail_review = True
        with patch.object(self, 'github', side_effect=fail_reporting), \
             patch('sys.stderr', new_callable=io.StringIO) as errors:
            with self.assertRaisesRegex(InvalidReview, 'Synthetic ambiguous send'):
                self.run_publisher(entry=publisher.run_publication)
        self.assertEqual(self.failure_receipt()['failure_type'], 'InvalidReview')
        self.assertIn('failure check was not confirmed: OSError', errors.getvalue())

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
