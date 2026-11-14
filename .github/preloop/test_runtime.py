"""Offline API-contract/provenance checks. Never contact GitHub or Preloop."""
import base64
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

    def test_pull_request_target_revision_is_trusted_base(self):
        run = dict(event='pull_request_target', head_sha='b' * 40, repository={'id': 42})
        self.assertEqual(trust.trigger_workflow_sha(run, {'workflow_sha': 'b' * 40}, self.binding, 'a' * 40), 'b' * 40)
        with self.assertRaises(InvalidReview):
            trust.trigger_workflow_sha(run, {'workflow_sha': 'a' * 40}, self.binding, 'a' * 40)

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
