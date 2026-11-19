"""Offline API-contract/provenance checks. Never contact GitHub or Preloop."""
import base64
import copy
import hashlib
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import runtime
import trust
from review_contract import InvalidReview


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.binding = dict(repository='example/repository', repository_id=42, default_branch='main')

    def historical_fixture(self):
        path = '.github/preloop/runtime.py'
        scope = dict(execution_id='487d988a-53ad-4f5d-8b84-d77bb733676f',
                     pr_number=7, head_sha='a' * 40, base_sha='b' * 40,
                     result_sha256='c' * 64)
        history = dict(workflow_sha='b' * 40, files={path: 'e' * 64},
                       git_blobs={path: 'e' * 40})
        permit = dict(scope, original_publisher_run_id='11', trigger_run_id='10',
                      failed_before_check_creation=True, historical_sources=history)
        binding = dict(self.binding, approved_files={path: 'f' * 64},
                       approved_blobs={path: 'f' * 40}, publication_recovery=permit)
        run = dict(id=11, repository={'id': 42}, status='completed',
                   conclusion='failure', run_attempt=1)
        wake = dict(completion=scope, authenticated_run_id='11', workflow_sha='b' * 40)
        return binding, run, wake

    def test_historical_target_is_exact_and_does_not_rebind_other_prs(self):
        binding, _, wake = self.historical_fixture()
        permit = binding['publication_recovery']
        permit['current_target_sha'] = 'd' * 40
        pr = dict(state='open', draft=False, author_association='OWNER', labels=[],
                  user={'login': 'owner'}, head={'sha': 'a' * 40, 'repo': {'id': 42}},
                  base={'sha': 'd' * 40, 'ref': 'main', 'repo': {'id': 42}})
        self.assertIs(runtime.current_pr(lambda _: pr, binding, 7, 'a' * 40, 'b' * 40), pr)
        for number, head, base in [(8, 'a' * 40, 'b' * 40),
                                   (7, 'e' * 40, 'b' * 40), (7, 'a' * 40, 'e' * 40)]:
            with self.subTest(number=number, head=head, base=base), self.assertRaises(InvalidReview):
                runtime.current_pr(lambda _: pr, binding, number, head, base)
        pr['base']['sha'] = 'e' * 40
        with self.assertRaises(InvalidReview):
            runtime.current_pr(lambda _: pr, binding, 7, 'a' * 40, 'b' * 40)

    def test_historical_delivery_is_never_current_base_approval(self):
        from test_runtime_boundaries import CompletedPublicationTests
        case = CompletedPublicationTests('test_real_completed_jobs_accept_distinct_trusted_code_and_reviewed_heads')
        case.setUp()
        case.binding['publication_recovery'] = dict(pr_number=7, head_sha=case.head,
            base_sha=case.base, current_target_sha=case.code)
        case.receipt['historical_target_sha'] = case.code
        result = case.accept()
        self.assertTrue(result['delivery_verified'])
        self.assertFalse(result['review_approved'])
        case.receipt['historical_target_sha'] = 'f' * 40
        with self.assertRaises(InvalidReview): case.accept()

    def test_historical_completion_uses_complete_signed_old_manifest(self):
        binding, run, wake = self.historical_fixture()
        source = runtime.receipt_source_binding(binding, run, 'b' * 40, wake,
            'preloop-wake-' + wake['completion']['execution_id'], 'preloop-review-publish.yml')
        self.assertEqual(source['approved_files'], binding['publication_recovery']['historical_sources']['files'])
        self.assertNotEqual(source['approved_files'], binding['approved_files'])
        self.assertIs(runtime.receipt_source_binding(binding, dict(run, id=12),
            'd' * 40, wake, 'preloop-wake-x', 'preloop-review-publish.yml'), binding)

    def test_historical_trigger_scope_and_names_are_exact(self):
        binding, run, wake = self.historical_fixture()
        scope = wake['completion']
        value = dict(scope, trigger_run_id='10', workflow_sha='b' * 40)
        del value['result_sha256']
        run.update(id=10, conclusion='success')
        for name in ('preloop-trigger-' + scope['execution_id'], 'preloop-event-10',
                     'preloop-intent-7-' + 'a' * 40 + '-' + 'b' * 40):
            selected = runtime.receipt_source_binding(binding, run, 'b' * 40, value,
                                                       name, 'preloop-review-trigger.yml')
            self.assertNotEqual(selected['approved_files'], binding['approved_files'])
        with self.assertRaises(InvalidReview):
            runtime.receipt_source_binding(binding, run, 'b' * 40, value,
                                           'preloop-event-9', 'preloop-review-trigger.yml')

    def test_historical_source_denies_mismatch_missing_scope_and_partial_manifest(self):
        original, original_run, original_wake = self.historical_fixture()
        cases = [('run', 'run_attempt', 2), ('run', 'repository', {'id': 9}),
                 ('run', 'conclusion', 'success'), ('run', 'status', 'in_progress'),
                 ('wake', 'authenticated_run_id', '12'), ('wake', 'workflow_sha', 'd' * 40),
                 ('scope', 'head_sha', 'd' * 40), ('scope', 'result_sha256', 'd' * 64),
                 ('history', 'workflow_sha', 'd' * 40), ('history', 'files', {}),
                 ('history', 'git_blobs', {}), ('permit', 'failed_before_check_creation', False)]
        for section, key, value in cases:
            binding, run, wake = copy.deepcopy((original, original_run, original_wake))
            targets = dict(run=run, wake=wake, scope=wake['completion'],
                           permit=binding['publication_recovery'],
                           history=binding['publication_recovery']['historical_sources'])
            targets[section][key] = value
            with self.subTest(section=section, key=key), self.assertRaises(InvalidReview):
                runtime.receipt_source_binding(binding, run, 'b' * 40, wake,
                    'preloop-wake-' + original_wake['completion']['execution_id'],
                    'preloop-review-publish.yml')

    def test_status_uses_real_combined_sha_not_nonexistent_status_sha(self):
        status = dict(id=9, context='Preloop review', state='success', target_url='https://github.com/example/repository/actions/runs/12',
                      creator={'login': 'github-actions[bot]'})
        calls = []
        def github(path, method='GET', body=None):
            calls.append((path, method))
            if method == 'POST':
                return status
            if path.endswith('/statuses?per_page=100'):
                return [status]
            combined_status = {key: value for key, value in status.items() if key != 'creator'}
            return {'sha': 'a' * 40, 'statuses': [combined_status]}
        with patch.dict(os.environ, GITHUB_RUN_ID='12'):
            self.assertEqual(runtime.commit_status(github, self.binding, 'a' * 40, 'success', status['target_url'], 'Reviewed')['id'], 9)
        self.assertEqual(len(calls), 3)
        self.assertTrue(calls[-1][0].endswith('/statuses?per_page=100'))

    def test_status_readback_rejects_wrong_actor_state_or_commit(self):
        for field, value in [('sha', 'b' * 40), ('state', 'pending'), ('actor', 'someone')]:
            status = dict(id=9, context='Preloop review', state='success', target_url='https://github.com/example/repository/actions/runs/12',
                          creator={'login': 'github-actions[bot]'})
            combined = {'sha': 'a' * 40, 'statuses': [{key: value for key, value in status.items() if key != 'creator'}]}
            observed = [dict(status)]
            if field == 'sha':
                combined['sha'] = value
            elif field == 'actor':
                observed[0]['creator'] = {'login': value}
            else:
                combined['statuses'][0][field] = value
            with patch.dict(os.environ, GITHUB_RUN_ID='12'):
                with self.assertRaises(InvalidReview):
                    runtime.commit_status(lambda _p, method='GET', body=None: status if method == 'POST' else
                                          (observed if _p.endswith('/statuses?per_page=100') else combined),
                                          self.binding, 'a' * 40, 'success', status['target_url'], 'Reviewed')

    def test_status_readback_rejects_missing_actor_and_mismatched_list_record(self):
        for field, value in [('creator', None), ('id', 10), ('state', 'pending'), ('target_url', 'https://example.invalid')]:
            status = dict(id=9, context='Preloop review', state='success',
                          target_url='https://github.com/example/repository/actions/runs/12')
            listed = dict(status, creator={'login': 'github-actions[bot]'})
            listed[field] = value
            combined = {'sha': 'a' * 40, 'statuses': [status]}
            def github(path, method='GET', body=None):
                return status if method == 'POST' else ([listed] if path.endswith('/statuses?per_page=100') else combined)
            with patch.dict(os.environ, GITHUB_RUN_ID='12'):
                with self.assertRaises(InvalidReview):
                    runtime.commit_status(github, self.binding, 'a' * 40, 'success', status['target_url'], 'Reviewed')

    def test_status_mismatch_names_failed_gate_without_dumping_records_or_reposting(self):
        for changed, expected in [('commit', 'combined_commit'), ('combined_id', 'combined_status_id'),
                                  ('combined_state', 'combined_state'), ('combined_url', 'combined_target_url'),
                                  ('listed_id', 'listed_status_id'), ('listed_state', 'listed_state'),
                                  ('listed_url', 'listed_target_url'), ('actor', 'listed_actor')]:
            with self.subTest(changed=changed):
                url = 'https://github.com/example/repository/actions/runs/12'
                status = dict(id=9, context='Preloop review', state='success', target_url=url)
                combined = {'sha': 'a' * 40, 'statuses': [dict(status)]}
                listed = [dict(status, creator={'login': 'github-actions[bot]'})]
                if changed == 'commit':
                    combined['sha'] = 'b' * 40
                elif changed == 'actor':
                    listed[0]['creator'] = {'login': 'untrusted-sensitive-value'}
                else:
                    target, field = changed.split('_')
                    row = combined['statuses'][0] if target == 'combined' else listed[0]
                    row[{'id': 'id', 'state': 'state', 'url': 'target_url'}[field]] = (
                        10 if field == 'id' else 'untrusted-sensitive-value')
                calls = []
                def github(path, method='GET', body=None):
                    calls.append(method)
                    return status if method == 'POST' else (
                        listed if path.endswith('/statuses?per_page=100') else combined)
                with patch.dict(os.environ, GITHUB_RUN_ID='12'):
                    with self.assertRaises(InvalidReview) as caught:
                        runtime.commit_status(github, self.binding, 'a' * 40, 'success', url, 'Reviewed')
                self.assertEqual(str(caught.exception), 'Commit status readback mismatch: ' + expected)
                self.assertEqual(calls, ['POST'] + ['GET'] * (4 if changed == 'listed_id' else 2))
                self.assertNotIn('untrusted-sensitive-value', str(caught.exception))

    def test_status_reconciles_missing_or_stale_list_without_reposting(self):
        url = 'https://github.com/example/repository/actions/runs/12'
        status = dict(id=9, context='Preloop review', state='pending', target_url=url,
                      creator={'login': 'github-actions[bot]'})
        combined = dict(sha='a' * 40, statuses=[{k: v for k, v in status.items() if k != 'creator'}])
        for stale in [[], [dict(status, id=8, state='error')], [dict(context='unrelated')]]:
            for state in ['pending', 'success', 'failure', 'error']:
                with self.subTest(stale=stale, state=state):
                    expected = dict(status, state=state)
                    exact = dict(combined, statuses=[dict(combined['statuses'][0], state=state)])
                    responses = iter([expected, exact, stale, [expected], exact])
                    calls = []
                    def github(path, method='GET', body=None):
                        calls.append((path, method))
                        return next(responses)
                    with patch.dict(os.environ, GITHUB_RUN_ID='12'):
                        self.assertEqual(runtime.commit_status(github, self.binding, 'a' * 40,
                                         state, url, 'Reviewed'), expected)
                    self.assertEqual([m for _, m in calls], ['POST', 'GET', 'GET', 'GET', 'GET'])
                    self.assertTrue(calls[-2][0].endswith('/statuses?per_page=100'))
                    self.assertTrue(calls[-1][0].endswith('/status'))

    def test_status_reconciliation_never_accepts_divergent_or_persistently_missing_evidence(self):
        url = 'https://github.com/example/repository/actions/runs/12'
        status = dict(id=9, context='Preloop review', state='success', target_url=url,
                      creator={'login': 'github-actions[bot]'})
        combined = dict(sha='a' * 40, statuses=[dict(status)])
        cases = [([], combined), ([dict(status, id=8)], combined),
                 ([dict(status, creator={'login': 'other'})], combined),
                 ([dict(status, state='pending')], combined),
                 ([dict(status, target_url='https://example.invalid')], combined),
                 ([status], dict(combined, sha='b' * 40)),
                 ([status], dict(combined, statuses=[dict(status, id=10)])),
                 ({'malformed': True}, combined)]
        for listed, final in cases:
            with self.subTest(listed=listed, final=final):
                responses = iter([status, combined, [], listed, final])
                calls = []
                def github(_path, method='GET', body=None):
                    calls.append(method)
                    return next(responses)
                with patch.dict(os.environ, GITHUB_RUN_ID='12'), self.assertRaises(InvalidReview):
                    runtime.commit_status(github, self.binding, 'a' * 40, 'success', url, 'Reviewed')
                self.assertEqual(calls.count('POST'), 1)
                self.assertLessEqual(len(calls), 5)

    def test_status_reconciliation_does_not_retry_wrong_actor_or_same_record_conflicts(self):
        url = 'https://github.com/example/repository/actions/runs/12'
        status = dict(id=9, context='Preloop review', state='success', target_url=url,
                      creator={'login': 'github-actions[bot]'})
        combined = dict(sha='a' * 40, statuses=[dict(status)])
        for wrong in [dict(status, id=8, creator={'login': 'other'}),
                      dict(status, state='pending'), dict(status, creator=None)]:
            calls = []
            responses = iter([status, combined, [wrong]])
            def github(_path, method='GET', body=None):
                calls.append(method)
                return next(responses)
            with self.subTest(wrong=wrong), patch.dict(os.environ, GITHUB_RUN_ID='12'), self.assertRaises(InvalidReview):
                runtime.commit_status(github, self.binding, 'a' * 40, 'success', url, 'Reviewed')
            self.assertEqual(calls, ['POST', 'GET', 'GET'])

    def test_pull_request_target_revision_is_trusted_base(self):
        # Actual failed run43750543323: REST head differs from OIDC/base.
        head = '609ff63aedb19779d318fe955cccb1964494866e'
        base = '26da264cd5de50b045c768f5a0c87eec433a1329'
        pr = dict(number=11, head=dict(sha=head, repo={'id': 42}),
                  base=dict(sha=base, ref='main', repo={'id': 42}))
        run = dict(event='pull_request_target', head_sha=head, repository={'id': 42},
                   pull_requests=[pr])
        receipt = dict(workflow_sha=base, pr_number=11, head_sha=head, base_sha=base)
        self.assertEqual(trust.trigger_workflow_sha(run, receipt, self.binding, head), base)
        with self.assertRaises(InvalidReview):
            trust.trigger_workflow_sha(run, dict(receipt, workflow_sha=head), self.binding, head)
        for field, value in [('pr_number', 12), ('head_sha', base), ('base_sha', head)]:
            with self.subTest(field=field), self.assertRaises(InvalidReview):
                trust.trigger_workflow_sha(run, dict(receipt, **{field: value}), self.binding, head)
        for prs in [None, [], [pr, pr], [dict(pr, number=12)],
                    [dict(pr, head=dict(sha=base, repo={'id': 42}))],
                    [dict(pr, head=dict(sha=head, repo={'id': 99}))],
                    [dict(pr, base=dict(sha=base, ref='feature', repo={'id': 42}))],
                    [dict(pr, base=dict(sha=base, ref='main', repo={'id': 99}))]]:
            with self.subTest(prs=prs), self.assertRaises(InvalidReview):
                trust.trigger_workflow_sha(dict(run, pull_requests=prs), receipt, self.binding, head)
        with self.assertRaises(InvalidReview):
            trust.trigger_workflow_sha(dict(run, head_sha=base), receipt, self.binding, head)

    def test_manual_trigger_keeps_default_branch_workflow_identity(self):
        run = dict(event='workflow_dispatch', head_sha='b' * 40, head_branch='main',
                   repository={'id': 42})
        receipt = dict(workflow_sha='b' * 40, head_sha='a' * 40)
        self.assertEqual(trust.trigger_workflow_sha(run, receipt, self.binding, 'a' * 40), 'b' * 40)
        for changes in [dict(head_branch='feature'), dict(head_sha='a' * 40),
                        dict(repository={'id': 99}), dict(event='pull_request')]:
            with self.subTest(changes=changes), self.assertRaises(InvalidReview):
                trust.trigger_workflow_sha(dict(run, **changes), receipt, self.binding, 'a' * 40)

    def test_completed_pr_target_artifact_verifies_sources_at_base_not_head(self):
        head = '609ff63aedb19779d318fe955cccb1964494866e'
        base = '26da264cd5de50b045c768f5a0c87eec433a1329'
        binding = dict(self.binding, approved_files={'.github/preloop/runtime.py': 'f' * 64})
        receipt = dict(workflow_sha=base, head_sha=head, base_sha=base,
                       pr_number=11, trigger_run_id='10')
        pr = dict(number=11, head=dict(sha=head, repo={'id': 42}),
                  base=dict(sha=base, ref='main', repo={'id': 42}))
        run = dict(id=10, event='pull_request_target', head_sha=head,
                   path='.github/workflows/preloop-review-trigger.yml',
                   repository={'id': 42}, pull_requests=[pr],
                   status='completed', conclusion='success')
        row = dict(id=1, name='preloop-trigger-execution', expired=False,
                   workflow_run={'id': 10})
        jobs = [dict(name='trigger', conclusion='success', steps=[
            dict(name='Validate native startup once', conclusion='success')])]
        def pages(_github, _path, field):
            return jobs if field == 'jobs' else [row]
        with patch.object(runtime, 'github_pages', side_effect=pages), \
             patch.object(trust, 'download_trigger_artifact', return_value=receipt), \
             patch.object(trust, 'verify_sources') as sources, \
             patch.dict(os.environ, GH_TOKEN='fixture'):
            github = lambda path: run
            self.assertEqual(runtime.artifact(github, binding, row['name'],
                                             'preloop-review-trigger.yml'), receipt)
            sources.assert_called_once_with(github, binding, base, list(binding['approved_files']))
            receipt['workflow_sha'] = head
            with self.assertRaises(InvalidReview):
                runtime.artifact(github, binding, row['name'], 'preloop-review-trigger.yml')

    def test_trigger_artifact_requires_completed_success_and_successful_startup_step(self):
        row = dict(id=1, name='preloop-trigger-execution', expired=False, workflow_run={'id': 10})
        run = dict(id=10, path='.github/workflows/preloop-review-trigger.yml',
                   status='completed', conclusion='success')
        receipt = dict(trigger_run_id='10', head_sha='a' * 40)
        job = dict(name='trigger', conclusion='success', steps=[
            dict(name='Validate native startup once', conclusion='success')])
        jobs = [job]
        def pages(_github, _path, field):
            return jobs if field == 'jobs' else [row]
        with patch.object(runtime, 'github_pages', side_effect=pages), \
             patch.object(trust, 'download_trigger_artifact', return_value=receipt), \
             patch.object(trust, 'trigger_workflow_sha', return_value='b' * 40), \
             patch.object(runtime, 'receipt_source_binding', return_value=dict(self.binding, approved_files={})), \
             patch.object(trust, 'verify_sources'), patch.dict(os.environ, GH_TOKEN='fixture'):
            def read(**kwargs):
                return runtime.artifact(lambda _path: run, self.binding, row['name'],
                                        'preloop-review-trigger.yml', **kwargs)
            self.assertEqual(read(), receipt)
            for state, conclusion in [('in_progress', None), ('queued', None),
                                      ('completed', 'failure'), ('completed', 'cancelled'),
                                      ('completed', 'timed_out'), ('completed', 'skipped'),
                                      ('completed', None)]:
                with self.subTest(state=state, conclusion=conclusion):
                    run.update(status=state, conclusion=conclusion)
                    with self.assertRaisesRegex(InvalidReview, 'not completed successfully'):
                        read()
            # The explicit cleanup-only caller may still establish ownership
            # for failed/in-progress runs. It does not publish a review/pass.
            for state in ['completed', 'in_progress']:
                run.update(status=state, conclusion='failure' if state == 'completed' else None)
                self.assertEqual(read(allow_failed=True), receipt)
            run.update(status='completed', conclusion='success')
            bad_jobs = [[], [dict(job, conclusion='failure')],
                        [dict(job, name='another job')], [dict(job, steps=[])], [job, job]]
            bad_jobs += [[dict(job, steps=[dict(name='Validate native startup once', conclusion=value)])]
                         for value in ['failure', 'cancelled', 'skipped', None]]
            for jobs in bad_jobs:
                with self.subTest(jobs=jobs), self.assertRaisesRegex(InvalidReview, 'startup validation'):
                    read()

    def test_source_manifest_batched_tree_and_exact_content_fallback(self):
        source = b'fixed trusted code\n'
        path = '.github/preloop/trigger.py'
        blob = hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source).hexdigest()
        binding = dict(self.binding, approved_files={path: hashlib.sha256(source).hexdigest()}, approved_blobs={path: blob})
        calls = []
        def fast(url):
            calls.append(url)
            return {'truncated': False, 'tree': [{'path': path, 'type': 'blob', 'sha': blob}]}
        trust.verify_sources(fast, binding, 'a' * 40, [path])
        self.assertEqual(len(calls), 1)
        def fallback(url):
            return {'truncated': True} if '/git/trees/' in url else {'encoding': 'base64', 'content': base64.b64encode(source).decode()}
        trust.verify_sources(fallback, binding, 'a' * 40, [path])
        with self.assertRaises(InvalidReview):
            trust.verify_sources(lambda _url: {'truncated': False, 'tree': []}, binding, 'a' * 40, [path])

    def test_owned_execution_pagination_does_not_drop_later_records(self):
        pages = [[{'id': str(i)} for i in range(100)], [{'id': 'later'}]]
        with patch.object(runtime, 'preloop', side_effect=pages) as mocked:
            rows = runtime.executions({'flow_id': 'flow'}, 'ci_fixture')
        self.assertEqual(rows[-1]['id'], 'later')
        self.assertIn('skip=100', mocked.call_args.args[0])

    def test_execution_pagination_drift_refused(self):
        page = [{'id': str(i)} for i in range(100)]
        with patch.object(runtime, 'preloop', side_effect=[page, [{'id': '0'}]]):
            with self.assertRaises(InvalidReview):
                runtime.executions({'flow_id': 'flow'}, 'ci_fixture')

    def test_privileged_workflows_use_their_immutable_trusted_revision(self):
        folder = Path(__file__).resolve().parents[1] / 'workflows'
        for name in ['preloop-review-trigger.yml', 'preloop-review-publish.yml']:
            text = (folder / name).read_text()
            self.assertIn('ref: ${{ github.workflow_sha }}', text)
            self.assertNotIn('ref: ${{ github.event.pull_request.head', text)
            self.assertNotIn('contents: write', text)
            self.assertIn('persist-credentials: false', text)
        self.assertIn('test_*.py', (folder / 'preloop-contract-tests.yml').read_text())


if __name__ == '__main__':
    unittest.main()
