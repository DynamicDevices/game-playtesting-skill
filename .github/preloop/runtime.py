"""Trusted GitHub/Preloop plumbing. Never execute code from the reviewed PR."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.parse

import trust
from review_contract import require
from completion_contract import strict_json


def verify_live_service(binding, workload, workflow):
    """Fail-closed online suspension gate; no cached allow or signing-key claims.

    Alex must approve this exact mechanism in the repository's signed binding.
    Disabling either workflow suspends writes; cancel the affected runs as well
    for durable revocation before any later workflow re-enable. This API check
    cannot make a GitHub read and subsequent write atomic.
    """
    fresh = trust.load_authority('.github', binding['repository'])
    require(fresh == binding, 'Publication authority changed during the run')
    policy = binding.get('live_revocation')
    require(type(policy) is dict and
            policy.get('mechanism') == 'github-actions-workflow-and-run-v1' and
            policy.get('explicit_posture_approval') is True,
            'Missing accepted live service-revocation mechanism')
    names = {'preloop-review-trigger.yml', 'preloop-review-publish.yml'}
    identities = policy.get('workflow_ids')
    require(type(identities) is dict and set(identities) == names and workflow in names and
            all(type(value) is int and value > 0 for value in identities.values()),
            'Missing immutable workflow identities')
    root = '/repos/' + binding['repository']
    for name in sorted(names):
        observed = trust.request('https://api.github.com',
                                 root + '/actions/workflows/' + str(identities[name]),
                                 os.environ['GH_TOKEN'])
        require(observed.get('id') == identities[name] and
                observed.get('path') == '.github/workflows/' + name and
                observed.get('state') == 'active', 'Review workflow suspended or substituted')
    run_id = os.environ['GITHUB_RUN_ID']
    require(run_id.isdigit(), 'Malformed live workload run')
    run = trust.request('https://api.github.com', root + '/actions/runs/' + run_id,
                        os.environ['GH_TOKEN'])
    require(str(run.get('id')) == run_id and
            run.get('repository', {}).get('id') == binding['repository_id'] and
            run.get('workflow_id') == identities[workflow] and
            run.get('head_sha') == workload.get('workflow_sha') and
            (workload.get('event_name') == 'pull_request_target' or
             run.get('head_branch') == binding['default_branch']) and
            run.get('event') == workload.get('event_name') and
            str(run.get('run_attempt')) == str(workload.get('run_attempt')) and
            str(run.get('run_attempt', '')).isdigit() and
            run.get('status') == 'in_progress' and run.get('conclusion') is None,
            'Workload is cancelled, stopped, substituted or from another attempt')


def context(workflow):
    repository = os.environ['GITHUB_REPOSITORY']
    binding = trust.load_authority('.github', repository)
    require(binding.get('publication_enabled') is True, 'Signed service policy is not active')
    require(binding.get('native_ci_contract', {}).get('explicit_posture_approval') is True,
            'Native execution contract not approved')
    workload = trust.verify_workload(binding, repository, workflow=workflow)
    def github(path, method='GET', body=None):
        require(path.startswith('/repos/' + repository + '/'), 'GitHub target outside this repository')
        if method != 'GET':
            relative = path.removeprefix('/repos/' + repository + '/')
            allowed = ((method == 'POST' and re.fullmatch('statuses/[0-9a-f]{40}', relative)) or
                       (workflow == 'preloop-review-publish.yml' and
                        ((method == 'POST' and re.fullmatch('pulls/[1-9][0-9]*/reviews', relative)) or
                         (method == 'POST' and relative == 'check-runs') or
                         (method == 'PATCH' and re.fullmatch('check-runs/[1-9][0-9]*', relative)))))
            require(allowed, 'GitHub operation outside review/status publication')
            verify_live_service(binding, workload, workflow)
        return trust.request('https://api.github.com', path, os.environ['GH_TOKEN'], method, body)
    trust.verify_sources(github, binding, workload['workflow_sha'], list(binding['approved_files']))
    return binding, workload, github


def commit_status(github, binding, head, state, run_url, description):
    require(state in ['pending', 'success', 'failure', 'error'], 'Invalid commit status state')
    require(re.fullmatch('[0-9a-f]{40}', head), 'Invalid status commit')
    expected_url = 'https://github.com/' + binding['repository'] + '/actions/runs/' + os.environ['GITHUB_RUN_ID']
    require(run_url == expected_url, 'Status must link this actual Actions run')
    root = '/repos/' + binding['repository']
    status = github(root + '/statuses/' + head, 'POST', {
        'state': state, 'context': 'Preloop review', 'target_url': run_url, 'description': description})
    # Individual status records have no sha field. Bind through the combined
    # exact-commit endpoint and independently check the newest matching record.
    combined = github(root + '/commits/' + head + '/status')
    current = next((row for row in combined['statuses'] if row['context'] == 'Preloop review'), None)
    require(combined['sha'] == head and current and current['id'] == status['id'] and
            current['state'] == state and current['target_url'] == run_url and
            current['creator']['login'] == 'github-actions[bot]', 'Commit status readback mismatch')
    return status


def preloop(path, token, method='GET', body=None):
    require(token.startswith('ci_'), 'A repository-bound CI credential is required')
    return trust.request('https://preloop.ai', '/api/v1' + path, token, method, body)


def executions(binding, token):
    rows, seen, skip = [], set(), 0
    while True:
        query = urllib.parse.urlencode(dict(flow_id=binding['flow_id'], limit=100, skip=skip))
        page = preloop('/flows/executions?' + query, token)
        require(type(page) is list, 'Invalid owned execution page')
        for row in page:
            require(row['id'] not in seen, 'Execution history changed during pagination')
            seen.add(row['id'])
            rows.append(row)
        if len(page) < 100:
            return rows
        skip += len(page)


def github_pages(github, path, field=None):
    rows, seen = [], set()
    page_number = 1
    while True:
        separator = '&' if '?' in path else '?'
        response = github(path + separator + 'per_page=100&page=' + str(page_number))
        page = response if field is None else response[field]
        require(type(page) is list, 'Invalid GitHub page')
        for row in page:
            require(row['id'] not in seen, 'GitHub history changed during pagination')
            seen.add(row['id'])
            rows.append(row)
        if len(page) < 100:
            return rows
        page_number += 1


def current_pr(github, binding, number, head=None, base=None):
    require(type(number) is int and number > 0, 'Invalid PR number')
    pr = github('/repos/' + binding['repository'] + '/pulls/' + str(number))
    require(pr['state'] == 'open' and not pr['draft'], 'PR is closed or draft')
    require(pr['head']['repo']['id'] == binding['repository_id'] and
            pr['base']['repo']['id'] == binding['repository_id'] and
            pr['base']['ref'] == binding['default_branch'], 'Wrong PR repository/base')
    require(pr['author_association'] in ['OWNER', 'MEMBER', 'COLLABORATOR'] and
            pr['user']['login'] != 'dependabot[bot]' and
            'preloop-skip-review' not in [label['name'] for label in pr['labels']],
            'PR is not eligible for review')
    for sha in [pr['head']['sha'], pr['base']['sha']]:
        require(re.fullmatch('[0-9a-f]{40}', sha), 'Invalid GitHub commit')
    require(head is None or pr['head']['sha'] == head, 'PR head changed')
    require(base is None or pr['base']['sha'] == base, 'PR base changed')
    return pr


def full_diff_sha256(repository, base, head, github_token):
    require(re.fullmatch('[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository), 'Invalid repository')
    require(all(re.fullmatch('[0-9a-f]{40}', sha) for sha in [base, head]), 'Invalid revision')
    # Object storage only. No checkout, hooks, attributes, textconv or PR scripts.
    with tempfile.TemporaryDirectory() as temp:
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null',
                   GIT_NO_REPLACE_OBJECTS='1', GIT_TERMINAL_PROMPT='0')
        for key in list(env):
            if key.startswith('GIT_CONFIG_') and key not in ['GIT_CONFIG_NOSYSTEM', 'GIT_CONFIG_GLOBAL']:
                del env[key]
        def git(*args, output=None):
            completed = subprocess.run(['git', '-C', temp, '-c', 'core.hooksPath=/dev/null', *args],
                                       env=env, stdout=output if output else subprocess.PIPE,
                                       stderr=subprocess.PIPE, timeout=90)
            require(completed.returncode == 0, 'Canonical Git operation failed')
            return completed.stdout
        git('init', '--bare', '--quiet')
        auth = base64.b64encode(('x-access-token:' + github_token).encode()).decode()
        env.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='http.https://github.com/.extraheader',
                   GIT_CONFIG_VALUE_0='AUTHORIZATION: basic ' + auth)
        git('fetch', '--quiet', '--no-tags', 'https://github.com/' + repository + '.git', base, head)
        env.pop('GIT_CONFIG_VALUE_0')
        env['GIT_CONFIG_COUNT'] = '0'
        merge_base = git('merge-base', base, head).decode().strip()
        with tempfile.TemporaryFile() as diff:
            git(*trust.DIFF_ARGS, merge_base, head, '--', output=diff)
            diff.seek(0)
            return hashlib.file_digest(diff, 'sha256').hexdigest()


def artifact(github, binding, name, workflow, allow_failed=False, run_id=None, allow_current=False):
    path = '/repos/' + binding['repository']
    items = github_pages(github, path + '/actions/artifacts?name=' + urllib.parse.quote(name), 'artifacts')
    matches = []
    for item in items:
        if item['name'] != name or (run_id and str(item['workflow_run']['id']) != str(run_id)):
            continue
        require(not item['expired'], 'Required durable artifact expired')
        run = github(path + '/actions/runs/' + str(item['workflow_run']['id']))
        require(run['path'].split('@')[0] == '.github/workflows/' + workflow,
                'Artifact came from another workflow')
        current = allow_current and str(run['id']) == os.environ['GITHUB_RUN_ID']
        trigger = workflow == 'preloop-review-trigger.yml'
        require(current or (trigger and run['status'] in ['in_progress', 'completed']) or
                (run['status'] == 'completed' and (allow_failed or run['conclusion'] == 'success')),
                'Artifact workflow has not completed successfully')
        value = trust.download_trigger_artifact(binding['repository'], item['id'], os.environ['GH_TOKEN'])
        if workflow == 'preloop-review-trigger.yml':
            revision = trust.trigger_workflow_sha(run, value, binding, value['head_sha'])
            require(str(value['trigger_run_id']) == str(run['id']), 'Trigger artifact run mismatch')
        else:
            require(run['event'] in ['repository_dispatch', 'workflow_dispatch'] and
                    run['head_branch'] == binding['default_branch'], 'Untrusted completion run')
            revision = run['head_sha']
            jobs = github_pages(github, path + '/actions/runs/' + str(run['id']) + '/jobs', 'jobs')
            auth = [job for job in jobs if job['name'] == 'Authenticate completion' and
                    job['conclusion'] == 'success']
            require(len(auth) == 1, 'Completion authentication job did not succeed')
        trust.verify_sources(github, binding, revision, list(binding['approved_files']))
        matches.append(value)
    require(matches and all(value == matches[0] for value in matches), 'Missing or conflicting receipt')
    return matches[0]


def write_receipt(folder, value):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'receipt.json'
    with path.open('x') as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def output(**values):
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:
        for key, value in values.items():
            require('\n' not in str(value) and '\r' not in str(value), 'Invalid Actions output')
            stream.write(key + '=' + str(value) + '\n')
