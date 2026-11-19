"""Finalizer entry-point regressions with synthetic isolated APIs."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import finalize
from review_contract import InvalidReview


class FinalizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.binding = dict(repository='example/repository', repository_id=42)
        self.receipt = dict(execution_id='487d988a-53ad-4f5d-8b84-d77bb733676f',
            head_sha='a' * 40, base_sha='b' * 40, result_sha256='c' * 64,
            claim_sha256='d' * 64, state='success', check_id=11,
            review_url='https://github.com/example/repository/pull/7#review-22')
        self.completion = dict(self.receipt, pr_number=7, status='SUCCEEDED', result_ready=True)
        self.rows, self.calls = [], []
        self.status_effect = None
        self.pr_effect = None
        self.supersession_effect = None
        self.lose_release_response = False
        self.fail_cleanup_patch = False
        self.fail_readback = False
        self.check = dict(id=11, name='Preloop review', head_sha='a' * 40,
            external_id='briar-preloop:' + 'd' * 64, app={'id': 15368, 'slug': 'github-actions'},
            details_url='https://github.com/example/repository/actions/runs/12',
            status='in_progress', conclusion=None,
            output={'text': '<!-- briar-preloop:' + self.receipt['execution_id'] + ':' + 'd' * 64 + ' -->'})
        self.normalize_check_url = False
        self.intent = dict(publisher_run_id='12', finalizer_run_id='13',
                           publication_receipt=self.receipt, completion=self.completion)
        self.event = Path(self.temp.name) / 'event.json'
        self.event.write_text(json.dumps(dict(action='completed', repository={'id': 42},
            workflow_run={'id': 12, 'path': '.github/workflows/preloop-review-publish.yml'})))
        env = patch.dict(os.environ, GITHUB_EVENT_PATH=str(self.event), GITHUB_EVENT_NAME='workflow_run',
                         GITHUB_RUN_ID='13', GITHUB_RUN_ATTEMPT='1', RUNNER_TEMP=self.temp.name,
                         PRELOOP_CI_TOKEN='synthetic-not-a-key')
        env.start()
        self.addCleanup(env.stop)

    def github(self, path, method='GET', body=None):
        self.calls.append((path, method, body))
        if method == 'PATCH':
            if self.fail_cleanup_patch and body['conclusion'] == 'failure':
                raise OSError('Synthetic cleanup PATCH failure')
            self.check.update(body)
            if self.lose_release_response:
                self.lose_release_response = False
                raise OSError('Synthetic lost release response')
            return self.check
        if self.fail_readback:
            self.fail_readback = False
            raise OSError('Synthetic check readback failure')
        if self.normalize_check_url:
            return dict(self.check, details_url='https://github.com/example/repository/runs/11')
        return self.check

    def run_phase(self, entry):
        with patch.object(finalize.runtime, 'context', return_value=(self.binding, {}, self.github)), \
             patch.object(finalize, 'producer', return_value=('12', self.receipt, self.completion)), \
             patch.object(finalize.runtime, 'github_pages', return_value=self.rows), \
             patch.object(finalize.runtime, 'artifact', return_value=self.intent), \
             patch.object(finalize.runtime, 'current_pr', side_effect=self.pr_effect), \
             patch.object(finalize.publisher, 'no_supersession', side_effect=self.supersession_effect), \
             patch.object(finalize.runtime, 'commit_status', side_effect=self.status_effect) as status, \
             patch.object(finalize.runtime, 'output'):
            entry()
            return status

    def admit_release(self):
        self.rows = [dict(name=finalize.intent_name('12', self.receipt),
                          expired=False, workflow_run={'id': 13})]

    def failure_receipt(self):
        return json.loads((Path(os.environ['RUNNER_TEMP']) / 'preloop-finalize-failure/receipt.json').read_text())

    def test_status_failure_downgrades_check_and_posts_error_without_hiding_original(self):
        self.admit_release()
        states = []
        original = OSError('Synthetic original status failure')
        def status(_github, _binding, _head, state, *_args):
            states.append(state)
            if state == 'success':
                raise original
        self.status_effect = status
        with self.assertRaises(OSError) as caught:
            self.run_phase(finalize.release)
        self.assertIs(caught.exception, original)
        self.assertEqual(states, ['success', 'error'])
        self.assertEqual(self.check['conclusion'], 'failure')
        report = self.failure_receipt()
        self.assertEqual(report['cleanup'], dict(check='failure_confirmed', status='error_confirmed'))
        self.assertEqual(report['failure_type'], 'OSError')
        self.assertNotIn(str(original), json.dumps(report))

    def test_ambiguous_release_and_transient_readback_failures_are_cleaned_up(self):
        for fault in ['lose_release_response', 'fail_readback']:
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as folder, \
                 patch.dict(os.environ, RUNNER_TEMP=folder):
                self.admit_release()
                setattr(self, fault, True)
                self.status_effect = None
                with self.assertRaises(OSError):
                    self.run_phase(finalize.release)
                self.assertEqual(self.check['conclusion'], 'failure')
                report = json.loads((Path(folder) / 'preloop-finalize-failure/receipt.json').read_text())
                self.assertEqual(report['cleanup']['status'], 'error_confirmed')

    def test_check_cleanup_failure_still_attempts_error_status_and_preserves_original(self):
        self.admit_release()
        self.fail_cleanup_patch = True
        states = []
        original = OSError('Synthetic original failure')
        def status(_github, _binding, _head, state, *_args):
            states.append(state)
            raise original if state == 'success' else RuntimeError('Synthetic error-status failure')
        self.status_effect = status
        with self.assertRaises(OSError) as caught:
            self.run_phase(finalize.release)
        self.assertIs(caught.exception, original)
        self.assertEqual(states, ['success', 'error'])
        self.assertEqual(self.check['conclusion'], 'success')  # Honest API-failure limit.
        report = self.failure_receipt()
        self.assertEqual(report['cleanup']['check'], 'unconfirmed')
        self.assertEqual(report['cleanup']['status'], 'unconfirmed')

    def test_cleanup_denies_changed_owner_claim_revision_and_other_finalizer(self):
        mutations = [dict(head_sha='f' * 40), dict(id=99), dict(name='other'),
                     dict(external_id='other'), dict(app={'id': 99, 'slug': 'other'}),
                     dict(details_url='https://github.com/example/repository/actions/runs/99'),
                     dict(output={'text': 'another finalizer claim'})]
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder, \
                 patch.dict(os.environ, RUNNER_TEMP=folder):
                self.admit_release()
                states = []
                def status(_github, _binding, _head, state, *_args):
                    states.append(state)
                    self.check.update(mutation)
                    raise OSError('Synthetic original status failure')
                self.status_effect = status
                with self.assertRaises(OSError):
                    self.run_phase(finalize.release)
                self.assertEqual(states, ['success'])
                self.assertEqual(self.failure_receipt()['cleanup']['ownership_error'], 'InvalidReview')
                # Restore fixture identity for the next subcase.
                self.check.update(id=11, name='Preloop review', head_sha='a' * 40,
                    external_id='briar-preloop:' + 'd' * 64, app={'id': 15368, 'slug': 'github-actions'})

    def test_changed_pr_or_supersession_after_release_denies_cleanup_writes(self):
        for field in ['pr_effect', 'supersession_effect']:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as folder, \
                 patch.dict(os.environ, RUNNER_TEMP=folder):
                self.admit_release()
                setattr(self, field, [None, InvalidReview('Synthetic changed target'),
                                      InvalidReview('Synthetic still changed target')])
                self.calls = []
                with self.assertRaises(InvalidReview):
                    self.run_phase(finalize.release)
                self.assertEqual(len([c for c in self.calls if c[1] == 'PATCH']), 1)
                self.assertEqual(self.failure_receipt()['cleanup']['ownership_error'], 'InvalidReview')
                setattr(self, field, None)

    def test_failure_evidence_is_uploaded_only_on_failed_release(self):
        text = (Path(__file__).resolve().parents[1] / 'workflows/preloop-review-finalize.yml').read_text()
        self.assertIn("if: always() && steps.release.outcome == 'failure'", text)
        self.assertIn('preloop-finalize-release/receipt.json', text)
        self.assertIn('preloop-finalize-failure/receipt.json', text)
        self.assertIn('id: release', text)

    def test_cleanup_receipt_and_log_errors_do_not_replace_original_exception(self):
        self.admit_release()
        original = OSError('Synthetic original release failure')
        self.status_effect = original
        write = finalize.runtime.write_receipt
        def evidence(folder, value):
            if Path(folder).name == 'preloop-finalize-failure':
                raise RuntimeError('Synthetic receipt failure')
            return write(folder, value)
        with patch.object(finalize, 'cleanup_failed_release', side_effect=ValueError('Synthetic cleanup error')), \
             patch.object(finalize.runtime, 'write_receipt', side_effect=evidence), \
             patch('builtins.print', side_effect=OSError('Synthetic log failure')):
            with self.assertRaises(OSError) as caught:
                self.run_phase(finalize.release)
        self.assertIs(caught.exception, original)

    def test_prepare_only_saves_intent_and_does_not_release_green(self):
        status = self.run_phase(finalize.prepare)
        self.assertFalse(self.calls)
        status.assert_not_called()
        saved = json.loads((Path(self.temp.name) / 'preloop-finalize/receipt.json').read_text())
        self.assertEqual(saved, self.intent)

    def test_release_requires_own_unique_durable_intent(self):
        name = finalize.intent_name('12', self.receipt)
        self.rows = [dict(name=name, expired=False, workflow_run={'id': 13})]
        status = self.run_phase(finalize.release)
        status.assert_called_once()
        self.assertEqual(self.check['conclusion'], 'success')
        self.assertIn('briar-preloop-finalized:12:13:', self.check['output']['text'])
        self.assertTrue(all(method in ['GET', 'PATCH'] for _, method, _ in self.calls))
        self.assertTrue(all('/check-runs/11' in path for path, _, _ in self.calls))

    def test_normalized_get_still_requires_intent_before_release(self):
        self.normalize_check_url = True
        with self.assertRaises(InvalidReview): self.run_phase(finalize.release)
        self.assertFalse(self.calls)
        name = finalize.intent_name('12', self.receipt)
        self.rows = [dict(name=name, expired=False, workflow_run={'id': 13})]
        self.run_phase(finalize.release).assert_called_once()
        self.assertIn('/actions/runs/13', self.check['output']['summary'])

    def test_missing_extra_old_expired_or_mutated_intent_denies_all_writes(self):
        name = finalize.intent_name('12', self.receipt)
        row = dict(name=name, expired=False, workflow_run={'id': 13})
        for rows in ([], [row, row], [dict(row, expired=True)],
                     [dict(row, workflow_run={'id': 14})]):
            self.rows = rows
            with self.subTest(rows=rows), self.assertRaises(InvalidReview): self.run_phase(finalize.release)
        self.rows = [row]
        self.intent = copy.deepcopy(self.intent)
        self.intent['publication_receipt']['result_sha256'] = 'f' * 64
        with self.assertRaises(InvalidReview): self.run_phase(finalize.release)
        self.assertFalse(self.calls)

    def test_prior_intent_and_run_attempt_cannot_be_replayed(self):
        self.rows = [dict(name='preloop-finalize-old')]
        with self.assertRaises(InvalidReview): self.run_phase(finalize.prepare)
        self.rows = []
        with patch.dict(os.environ, GITHUB_RUN_ATTEMPT='2'):
            with self.assertRaises(InvalidReview): self.run_phase(finalize.prepare)
            with self.assertRaises(InvalidReview): self.run_phase(finalize.release)
        self.assertFalse(self.calls)

    def test_producer_requires_authoritative_completed_publication(self):
        name = 'preloop-publication-' + self.receipt['execution_id']
        def artifact(*args, **kwargs):
            if args[2].startswith('preloop-trigger-'):
                return self.completion
            return {'completion': self.completion} if args[2].startswith('preloop-wake-') else self.receipt
        with patch.object(finalize.runtime, 'github_pages', return_value=[dict(name=name, expired=False)]), \
             patch.object(finalize.runtime, 'artifact', side_effect=artifact), \
             patch.object(finalize.runtime, 'completed_publication', side_effect=InvalidReview('Actual run not complete')):
            with self.assertRaisesRegex(InvalidReview, 'not complete'):
                finalize.producer(self.github, self.binding)
        self.assertFalse(self.calls)

    def test_retained_receipt_still_requires_completed_publication_proof(self):
        self.receipt['pending_check_mode'] = 'retained_failure'
        name = 'preloop-publication-' + self.receipt['execution_id']
        def artifact(*args, **kwargs):
            if args[2].startswith('preloop-trigger-'):
                return self.completion
            return {'completion': self.completion} if args[2].startswith('preloop-wake-') else self.receipt
        with patch.object(finalize.runtime, 'github_pages', return_value=[dict(name=name, expired=False)]), \
             patch.object(finalize.runtime, 'artifact', side_effect=artifact), \
             patch.object(finalize.runtime, 'completed_publication', return_value={'publication_receipt': self.receipt}) as verify, \
             patch.object(finalize.publisher, 'no_supersession'):
            self.assertEqual(finalize.producer(self.github, self.binding)[0], '12')
            self.assertTrue(verify.call_args.kwargs['pending'])
            verify.side_effect = InvalidReview('Producer receipt or completion invalid')
            with self.assertRaises(InvalidReview): finalize.producer(self.github, self.binding)
        self.assertFalse(self.calls)

    def test_producer_rechecks_trigger_success_and_exact_publication_target(self):
        name = 'preloop-publication-' + self.receipt['execution_id']
        trigger = dict(self.completion)
        def artifact(*args, **kwargs):
            if args[2].startswith('preloop-trigger-'):
                self.assertFalse(kwargs.get('allow_failed', False))
                if trigger.get('failed'):
                    raise InvalidReview('Trigger startup validation did not succeed')
                return trigger
            return {'completion': self.completion} if args[2].startswith('preloop-wake-') else self.receipt
        with patch.object(finalize.runtime, 'github_pages', return_value=[dict(name=name, expired=False)]), \
             patch.object(finalize.runtime, 'artifact', side_effect=artifact), \
             patch.object(finalize.runtime, 'completed_publication', return_value={'publication_receipt': self.receipt}), \
             patch.object(finalize.publisher, 'no_supersession'):
            self.assertEqual(finalize.producer(self.github, self.binding)[0], '12')
            for key in ['execution_id', 'pr_number', 'head_sha', 'base_sha']:
                with self.subTest(key=key):
                    trigger = dict(self.completion, **{key: 'wrong'})
                    with self.assertRaisesRegex(InvalidReview, 'trigger and publication differ'):
                        finalize.producer(self.github, self.binding)
            trigger = dict(self.completion, failed=True)
            with self.assertRaisesRegex(InvalidReview, 'startup validation'):
                finalize.producer(self.github, self.binding)
        self.assertFalse(self.calls)

    def test_retained_mode_release_is_only_after_durable_own_intent(self):
        self.receipt['pending_check_mode'] = 'retained_failure'
        with self.assertRaises(InvalidReview): self.run_phase(finalize.release)
        self.assertFalse(self.calls)
        name = finalize.intent_name('12', self.receipt)
        self.rows = [dict(name=name, expired=False, workflow_run={'id': 13})]
        self.run_phase(finalize.release).assert_called_once()
        self.assertEqual(self.check['conclusion'], 'success')
        self.assertTrue(all(method in ['GET', 'PATCH'] for _, method, _ in self.calls))


if __name__ == '__main__':
    unittest.main()
