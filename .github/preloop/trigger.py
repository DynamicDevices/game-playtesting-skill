"""Trigger an admitted native review once, from trusted default-branch code."""
import json
import os
from pathlib import Path
import secrets
import sys
import urllib.parse

import runtime
from review_contract import TERMINAL, require


def prepare():
    binding, workload, github = runtime.context('preloop-review-trigger.yml')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    number = (int(event['inputs']['pr_number']) if os.environ['GITHUB_EVENT_NAME'] == 'workflow_dispatch'
              else event['number'])
    pr = runtime.current_pr(github, binding, number)
    head, base = pr['head']['sha'], pr['base']['sha']
    token = os.environ['PRELOOP_CI_TRIGGER_TOKEN']
    rows = runtime.executions(binding, token)
    exact = [row for row in rows if row['pr_number'] == number and row['head_sha'] == head and
             row.get('base_sha') == base]
    require(not exact, 'An owned review already exists: recover its publication or explicitly reconcile it')
    name = 'preloop-intent-' + str(number) + '-' + head + '-' + base
    journal = github('/repos/' + binding['repository'] + '/actions/artifacts?name=' +
                     urllib.parse.quote(name) + '&per_page=1')
    require(journal['total_count'] == 0, 'Prior durable intent exists; do not blindly repeat a trigger')
    intent = dict(flow_id=binding['flow_id'], project_id=binding['project_id'],
                  repository_identifier=str(binding['repository_id']), pr_number=number,
                  head_sha=head, base_sha=base, challenge=secrets.token_hex(24),
                  diff_sha256=runtime.full_diff_sha256(binding['repository'], base, head, os.environ['GH_TOKEN']),
                  model_id=binding['model_id'],
                  flow_config_sha256=binding['native_ci_contract']['flow_config_sha256'],
                  trigger_run_id=os.environ['GITHUB_RUN_ID'], workflow_sha=workload['workflow_sha'])
    runtime.current_pr(github, binding, number, head, base)
    runtime.write_receipt(Path(os.environ['RUNNER_TEMP']) / 'preloop-intent', intent)
    runtime.output(intent_name=name, pr_number=number, head_sha=head)


def start():
    binding, workload, github = runtime.context('preloop-review-trigger.yml')
    intent = json.loads((Path(os.environ['RUNNER_TEMP']) / 'preloop-intent/receipt.json').read_text())
    number, head, base = intent['pr_number'], intent['head_sha'], intent['base_sha']
    require(intent['trigger_run_id'] == os.environ['GITHUB_RUN_ID'], 'Intent belongs to another run')
    name = 'preloop-intent-' + str(number) + '-' + head + '-' + base
    journal = github('/repos/' + binding['repository'] + '/actions/artifacts?name=' + name + '&per_page=100')
    require(journal['total_count'] == 1 and not journal['artifacts'][0]['expired'] and
            str(journal['artifacts'][0]['workflow_run']['id']) == os.environ['GITHUB_RUN_ID'],
            'Intent was not durably stored by this run')
    token = os.environ['PRELOOP_CI_TRIGGER_TOKEN']
    rows = runtime.executions(binding, token)
    require(not any(row['pr_number'] == number and row['head_sha'] == head and
                    row.get('base_sha') == base for row in rows), 'Review appeared after preparation')
    # Cancel only superseded owned executions for this PR, never other PRs.
    for row in rows:
        if row['pr_number'] == number and row['status'] not in TERMINAL:
            runtime.verify_live_service(binding, workload, 'preloop-review-trigger.yml')
            runtime.preloop('/flows/executions/' + row['id'] + '/command', token,
                            'POST', {'command': 'stop', 'payload': None})
    runtime.current_pr(github, binding, number, head, base)
    runtime.verify_live_service(binding, workload, 'preloop-review-trigger.yml')
    execution = runtime.preloop('/flows/' + binding['flow_id'] + '/trigger', token,
                                'POST', {'pr_number': number, 'head_sha': head})
    require(all(execution.get(key) == intent[key] for key in
                ['flow_id', 'project_id', 'repository_identifier', 'pr_number', 'head_sha', 'base_sha']),
            'Native controller accepted a different review')
    receipt = {**intent, 'execution_id': execution['id']}
    runtime.write_receipt(Path(os.environ['RUNNER_TEMP']) / 'preloop-trigger', receipt)
    runtime.output(execution_id=execution['id'])
    runtime.current_pr(github, binding, number, head, base)
    run_url = 'https://github.com/' + binding['repository'] + '/actions/runs/' + os.environ['GITHUB_RUN_ID']
    runtime.commit_status(github, binding, head, 'pending', run_url,
                          'Native review accepted; awaiting authenticated completion.')


def startup():
    """One immediate observation only. Do not poll or pretend acceptance means startup."""
    binding, _workload, _github = runtime.context('preloop-review-trigger.yml')
    receipt = json.loads((Path(os.environ['RUNNER_TEMP']) / 'preloop-trigger/receipt.json').read_text())
    detail = runtime.preloop('/flows/executions/' + receipt['execution_id'],
                             os.environ['PRELOOP_CI_TRIGGER_TOKEN'])
    require(detail.get('id') == receipt['execution_id'] and
            all(detail.get(key) == receipt[key] for key in
                ['flow_id', 'project_id', 'repository_identifier', 'pr_number', 'head_sha', 'base_sha']),
            'Startup belongs to another execution or revision')
    startup = detail.get('startup_receipt') or {}
    runtime.write_receipt(Path(os.environ['RUNNER_TEMP']) / 'preloop-startup', {
        'execution_id': receipt['execution_id'], 'status': detail.get('status'),
        'head_sha': receipt['head_sha'], 'base_sha': receipt['base_sha'],
        'startup_receipt': {key: startup.get(key) for key in
            ['version', 'executor', 'lease_revoked', 'commit', 'checkout_verified',
             'setup_completed', 'agent_started_at']} if type(startup) is dict else None})
    require(detail.get('status') in ['RUNNING', 'SUCCEEDED'],
            'Native workload is queued or failed, not a verified running launch')
    require(type(startup) is dict, 'Malformed native startup receipt')
    require(startup.get('version') == 1 and startup.get('executor') == 'hosted' and
            startup.get('lease_revoked') is None and
            startup.get('commit') == receipt['head_sha'] and
            startup.get('checkout_verified') is True and startup.get('setup_completed') is True and
            type(startup.get('agent_started_at')) is str and startup['agent_started_at'],
            'Native startup has not been proved; inspect the saved execution')
    print('Native checkout, setup and agent startup verified for ' + receipt['execution_id'])


if __name__ == '__main__':
    {'prepare': prepare, 'start': start, 'startup': startup}[sys.argv[1]]()
