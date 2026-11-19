"""Privilege allowlist and artifact-provenance regression tests."""
import os
import hashlib
import json
from pathlib import Path
import tempfile
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


class TriggerEventTests(unittest.TestCase):
    def test_records_exact_opened_event_and_denies_mismatched_pr(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            intent = dict(pr_number=7, head_sha='a' * 40, base_sha='b' * 40,
                          trigger_run_id='10', workflow_sha='b' * 40)
            runtime.write_receipt(root / 'preloop-intent', intent)
            event = dict(number=7, action='opened', pull_request=dict(
                head={'sha': 'a' * 40}, base={'sha': 'b' * 40}))
            event_path = root / 'event.json'
            event_path.write_text(json.dumps(event))
            with patch.dict(os.environ, RUNNER_TEMP=folder, GITHUB_EVENT_PATH=str(event_path),
                            GITHUB_EVENT_NAME='pull_request_target'):
                runtime.record_trigger_event()
                receipt = json.loads((root / 'preloop-event/receipt.json').read_text())
                self.assertEqual(receipt, dict(intent, event_name='pull_request_target',
                                               event_action='opened'))
                event['number'] = 8
                event_path.write_text(json.dumps(event))
                with self.assertRaises(InvalidReview): runtime.record_trigger_event()


class CheckURLTests(unittest.TestCase):
    def test_exact_run_or_own_canonical_check_url_only(self):
        binding = {'repository': 'example/repository'}
        root = 'https://github.com/example/repository'
        run_url = root + '/actions/runs/12'
        check = dict(id=11, app={'id': 15368, 'slug': 'github-actions'})
        for url in (run_url, root + '/runs/11'):
            runtime.verify_check_url(dict(check, details_url=url), binding, run_url)
        for url in (root + '/runs/12', root + '/actions/runs/99',
                    root + '/runs/11?x=1', root + '/runs/11/',
                    'https://github.com/other/repository/runs/11',
                    'https://attacker.example/example/repository/runs/11',
                    'http://github.com/example/repository/runs/11', None):
            with self.subTest(url=url), self.assertRaises(InvalidReview):
                runtime.verify_check_url(dict(check, details_url=url), binding, run_url)
        for update in ({'id': True}, {'id': 11.0}, {'id': '11'}, {'id': 0},
                       {'app': {'id': 15368, 'slug': 'other'}},
                       {'app': {'id': 15369, 'slug': 'github-actions'}},
                       {'app': {'id': 15368.0, 'slug': 'github-actions'}}):
            with self.subTest(update=update), self.assertRaises(InvalidReview):
                runtime.verify_check_url(dict(check, details_url=run_url, **update), binding, run_url)


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
                          conclusion='success', details_url=self.url, app={'id': 15368, 'slug': 'github-actions'},
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

    def test_canonical_check_url_does_not_replace_completed_producer_proof(self):
        self.check['details_url'] = 'https://github.com/example/repository/runs/11'
        self.assertTrue(self.accept()['delivery_verified'])
        self.run['status'] = 'in_progress'
        with self.assertRaises(InvalidReview): self.accept()

    def test_completed_recovery_requires_exact_signed_existing_publication(self):
        existing = dict(review_id=22, check_id=11, claim_sha256='c' * 64,
                        body_sha256=self.receipt['review_body_sha256'])
        self.binding['publication_recovery'] = {'existing_publication': existing}
        self.assertTrue(self.accept()['delivery_verified'])
        for key, value in [('review_id', 23), ('check_id', 12), ('claim_sha256', 'e' * 64),
                           ('body_sha256', 'f' * 64)]:
            saved = existing[key]
            existing[key] = value
            with self.subTest(key=key), self.assertRaises(InvalidReview): self.accept()
            existing[key] = saved

    def test_pending_phase_requires_real_completion_but_is_not_delivery(self):
        self.check.update(status='in_progress', conclusion=None)
        self.statuses[0]['state'] = 'pending'
        with patch.object(runtime, 'artifact', return_value=self.receipt), patch.object(runtime, 'current_pr'):
            result = runtime.completed_publication(self.github, self.binding, 12, self.eid,
                                                   7, self.head, self.base, pending=True)
            self.assertFalse(result['delivery_verified'])
            self.assertFalse(result['review_approved'])
            self.run['status'] = 'in_progress'
            with self.assertRaises(InvalidReview):
                runtime.completed_publication(self.github, self.binding, 12, self.eid,
                                               7, self.head, self.base, pending=True)

    def test_final_gate_requires_authenticated_matching_finalizer_intent(self):
        self.binding['publication_finalizer'] = {'explicit_posture_approval': True}
        final_url = 'https://github.com/example/repository/actions/runs/13'
        self.check.update(details_url=final_url, output={'text':
            '<!-- briar-preloop-finalized:12:13:' + 'c' * 64 + ' -->'})
        self.statuses[0].update(id=34, target_url=final_url)
        intent = dict(publisher_run_id='12', finalizer_run_id='13', publication_receipt=self.receipt)
        def artifact(*args, **kwargs):
            return intent if args[3] == 'preloop-review-finalize.yml' else self.receipt
        with patch.object(runtime, 'artifact', side_effect=artifact), patch.object(runtime, 'current_pr'):
            self.assertTrue(runtime.completed_publication(self.github, self.binding, 12, self.eid,
                                                         7, self.head, self.base)['delivery_verified'])
            intent['publisher_run_id'] = '99'
            with self.assertRaises(InvalidReview):
                runtime.completed_publication(self.github, self.binding, 12, self.eid, 7, self.head, self.base)

    def configure_retained_pending(self):
        self.receipt.update(result_sha256='d' * 64, pending_check_mode='retained_failure',
                            historical_target_sha='f' * 40)
        self.binding['publication_recovery'] = dict(execution_id=self.eid, pr_number=7,
            head_sha=self.head, base_sha=self.base, result_sha256='d' * 64,
            failed_before_check_creation=True, original_publisher_run_id='9', trigger_run_id='10',
            current_target_sha='f' * 40, existing_publication=dict(review_id=22, check_id=11,
                claim_sha256='c' * 64, body_sha256=self.receipt['review_body_sha256'],
                original_target_sha='e' * 40, preserve_failed_check=True))
        self.binding['publication_finalizer'] = dict(explicit_posture_approval=True,
            workflow_path='.github/workflows/preloop-review-finalize.yml', event='workflow_run',
            producer_path='.github/workflows/preloop-review-publish.yml')
        self.check.update(conclusion='failure', details_url='https://github.com/example/repository/runs/11',
            output={'text': '<!-- briar-preloop:' + self.eid + ':' + 'c' * 64 + ' -->'})
        self.statuses[0]['state'] = 'pending'

    def retained_pending_accept(self):
        with patch.object(runtime, 'artifact', return_value=self.receipt), patch.object(runtime, 'current_pr'):
            return runtime.completed_publication(self.github, self.binding, 12, self.eid,
                                                 7, self.head, self.base, pending=True)

    def test_retained_failure_is_only_intermediate_proof_not_delivery_or_approval(self):
        self.configure_retained_pending()
        result = self.retained_pending_accept()
        self.assertFalse(result['delivery_verified'])
        self.assertFalse(result['actions_check_verified'])
        self.assertFalse(result['review_approved'])
        for key, value in [('status', 'in_progress'), ('conclusion', 'failure')]:
            saved = self.run[key];self.run[key] = value
            with self.subTest(key=key), self.assertRaises(InvalidReview): self.retained_pending_accept()
            self.run[key] = saved

    def test_retained_pending_requires_exact_mode_tuple_and_failed_check(self):
        self.configure_retained_pending()
        self.receipt['pending_check_mode'] = 'in_progress'
        with self.assertRaises(InvalidReview): self.retained_pending_accept()
        self.receipt['pending_check_mode'] = 'retained_failure'
        for key, value in [('conclusion', 'success'), ('status', 'in_progress'),
                           ('output', {'text': 'substituted'}), ('head_sha', '0' * 40)]:
            saved = self.check[key];self.check[key] = value
            with self.subTest(key=key), self.assertRaises(InvalidReview): self.retained_pending_accept()
            self.check[key] = saved
        self.binding['publication_recovery']['result_sha256'] = '0' * 64
        with self.assertRaises(InvalidReview): self.retained_pending_accept()

    def test_retained_final_acceptance_requires_real_success_and_finalizer_intent(self):
        self.configure_retained_pending()
        final_url = 'https://github.com/example/repository/actions/runs/13'
        self.statuses[0].update(id=34, state='success', target_url=final_url)
        self.check['output']['text'] += '\n<!-- briar-preloop-finalized:12:13:' + 'c' * 64 + ' -->'
        intent = dict(publisher_run_id='12', finalizer_run_id='13', publication_receipt=self.receipt)
        def artifact(*args, **kwargs):
            return intent if args[3] == 'preloop-review-finalize.yml' else self.receipt
        with patch.object(runtime, 'artifact', side_effect=artifact), patch.object(runtime, 'current_pr'):
            with self.assertRaises(InvalidReview):
                runtime.completed_publication(self.github, self.binding, 12, self.eid, 7, self.head, self.base)
            self.check['conclusion'] = 'success'
            result = runtime.completed_publication(self.github, self.binding, 12, self.eid, 7, self.head, self.base)
            self.assertTrue(result['delivery_verified'])
            self.assertFalse(result['review_approved'])
            intent['publisher_run_id'] = '99'
            with self.assertRaises(InvalidReview):
                runtime.completed_publication(self.github, self.binding, 12, self.eid, 7, self.head, self.base)

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
