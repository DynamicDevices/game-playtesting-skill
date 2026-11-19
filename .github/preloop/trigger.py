"""Trigger an admitted native review once, from trusted default-branch code."""
import json
import datetime as dt
import os
from pathlib import Path
import re
import secrets
import sys
import urllib.parse

import runtime
from review_contract import TERMINAL, require


def diagnostic_permit(binding, event, number, head, base):
    """Only exact hardware-signed service policy may admit a duplicate test.

    The operator input selects a permit, never creates one. Normal triggers
    ignore an unused signed permit and retain their original duplicate gates.
    """
    source = event.get('inputs', {}).get('diagnostic_execution_id', '')
    if not source:
        return None
    require(os.environ['GITHUB_EVENT_NAME'] == 'workflow_dispatch',
            'Diagnostic reruns must be selected manually')
    permit = binding['native_ci_contract'].get('diagnostic_rerun')
    fields = {'source_execution_id', 'nonce', 'expires_at', 'pr_number',
              'head_sha', 'base_sha', 'diff_sha256', 'model_id', 'flow_config_sha256'}
    require(type(permit) is dict and set(permit) == fields,
            'Missing exact signed diagnostic permit')
    require(type(source) is str and re.fullmatch('[0-9a-f-]{36}', source) and
            permit['source_execution_id'] == source, 'Wrong diagnostic predecessor')
    require(type(permit['nonce']) is str and re.fullmatch('[0-9a-f]{48}', permit['nonce']),
            'Invalid diagnostic nonce')
    require(type(permit['expires_at']) is str, 'Missing diagnostic expiry')
    try:
        expiry = dt.datetime.fromisoformat(permit['expires_at'].replace('Z', '+00:00'))
    except ValueError:
        require(False, 'Invalid diagnostic expiry')
    require(expiry.tzinfo is not None and dt.datetime.now(dt.timezone.utc) < expiry,
            'Diagnostic permit expired')
    expected = dict(pr_number=number, head_sha=head, base_sha=base,
                    model_id=binding['model_id'],
                    flow_config_sha256=binding['native_ci_contract']['flow_config_sha256'])
    require(all(permit[key] == value for key, value in expected.items()),
            'Diagnostic target, model or configuration changed')
    require(type(permit['diff_sha256']) is str and
            re.fullmatch('[0-9a-f]{64}', permit['diff_sha256']), 'Invalid diagnostic diff')
    return permit


def diagnostic_history(binding, rows, permit):
    """A second same-revision execution or running same-PR work blocks launch."""
    same = [row for row in rows if row['pr_number'] == permit['pr_number'] and
            row['head_sha'] == permit['head_sha'] and row.get('base_sha') == permit['base_sha']]
    require(len(same) == 1 and same[0]['id'] == permit['source_execution_id'],
            'Diagnostic source missing or another same-revision run exists')
    source = same[0]
    require(source.get('status') in TERMINAL and
            all(source.get(key) == value for key, value in dict(
                flow_id=binding['flow_id'], project_id=binding['project_id'],
                repository_identifier=str(binding['repository_id'])).items()),
            'Diagnostic predecessor is not a terminal owned execution')
    require(not any(row['pr_number'] == permit['pr_number'] and row['status'] not in TERMINAL
                    for row in rows), 'Another same-PR execution is running')


def intent_name(intent):
    if 'diagnostic_rerun' in intent:
        return 'preloop-diagnostic-' + intent['diagnostic_rerun']['nonce']
    return 'preloop-intent-' + str(intent['pr_number']) + '-' + intent['head_sha'] + '-' + intent['base_sha']


def prepare():
    binding, workload, github = runtime.context('preloop-review-trigger.yml')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    number = (int(event['inputs']['pr_number']) if os.environ['GITHUB_EVENT_NAME'] == 'workflow_dispatch'
              else event['number'])
    pr = runtime.current_pr(github, binding, number)
    head, base = pr['head']['sha'], pr['base']['sha']
    permit = diagnostic_permit(binding, event, number, head, base)
    token = os.environ['PRELOOP_CI_TRIGGER_TOKEN']
    rows = runtime.executions(binding, token)
    exact = [row for row in rows if row['pr_number'] == number and row['head_sha'] == head and
             row.get('base_sha') == base]
    if permit is None:
        require(not exact, 'An owned review already exists: recover its publication or explicitly reconcile it')
    else:
        diagnostic_history(binding, rows, permit)
    name = ('preloop-diagnostic-' + permit['nonce']) if permit else (
        'preloop-intent-' + str(number) + '-' + head + '-' + base)
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
    if permit is not None:
        require(intent['diff_sha256'] == permit['diff_sha256'], 'Diagnostic diff changed')
        intent['diagnostic_rerun'] = permit
    runtime.current_pr(github, binding, number, head, base)
    runtime.write_receipt(Path(os.environ['RUNNER_TEMP']) / 'preloop-intent', intent)
    runtime.output(intent_name=name, pr_number=number, head_sha=head)


def start():
    binding, workload, github = runtime.context('preloop-review-trigger.yml')
    intent = json.loads((Path(os.environ['RUNNER_TEMP']) / 'preloop-intent/receipt.json').read_text())
    number, head, base = intent['pr_number'], intent['head_sha'], intent['base_sha']
    require(intent['trigger_run_id'] == os.environ['GITHUB_RUN_ID'], 'Intent belongs to another run')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    permit = diagnostic_permit(binding, event, number, head, base)
    require(intent.get('diagnostic_rerun') == permit, 'Diagnostic intent/permit changed')
    require(permit is None or intent['diff_sha256'] == permit['diff_sha256'], 'Diagnostic diff changed')
    name = intent_name(intent)
    journal = github('/repos/' + binding['repository'] + '/actions/artifacts?name=' + name + '&per_page=100')
    require(journal['total_count'] == 1 and not journal['artifacts'][0]['expired'] and
            str(journal['artifacts'][0]['workflow_run']['id']) == os.environ['GITHUB_RUN_ID'],
            'Intent was not durably stored by this run')
    token = os.environ['PRELOOP_CI_TRIGGER_TOKEN']
    rows = runtime.executions(binding, token)
    if permit is not None:
        diagnostic_history(binding, rows, permit)
    else:
        require(not any(row['pr_number'] == number and row['head_sha'] == head and
                        row.get('base_sha') == base for row in rows), 'Review appeared after preparation')
    # Cancel only superseded owned executions for this PR, never other PRs.
    for row in rows:
        if permit is None and row['pr_number'] == number and row['status'] not in TERMINAL:
            runtime.verify_live_service(binding, workload, 'preloop-review-trigger.yml')
            runtime.preloop('/flows/executions/' + row['id'] + '/command', token,
                            'POST', {'command': 'stop', 'payload': None})
    runtime.current_pr(github, binding, number, head, base)
    runtime.verify_live_service(binding, workload, 'preloop-review-trigger.yml')
    run_url = 'https://github.com/' + binding['repository'] + '/actions/runs/' + os.environ['GITHUB_RUN_ID']
    if permit is None and binding.get('publication_merge_gate'):
        runtime.commit_status(github, binding, head, 'pending', run_url,
            'Awaiting completed finalizer and independently verified review.', context_name='Preloop merge gate')
    execution = runtime.preloop('/flows/' + binding['flow_id'] + '/trigger', token,
                                'POST', {'pr_number': number, 'head_sha': head})
    require(all(execution.get(key) == intent[key] for key in
                ['flow_id', 'project_id', 'repository_identifier', 'pr_number', 'head_sha', 'base_sha']),
            'Native controller accepted a different review')
    require(permit is None or execution.get('id') != permit['source_execution_id'],
            'Diagnostic trigger returned the original execution; do not retry blindly')
    receipt = {**intent, 'execution_id': execution['id']}
    runtime.write_receipt(Path(os.environ['RUNNER_TEMP']) / 'preloop-trigger', receipt)
    runtime.output(execution_id=execution['id'])
    runtime.current_pr(github, binding, number, head, base)
    run_url = 'https://github.com/' + binding['repository'] + '/actions/runs/' + os.environ['GITHUB_RUN_ID']
    if permit is None:
        runtime.commit_status(github, binding, head, 'pending', run_url,
                              'Native review accepted; awaiting authenticated completion.')
    else:
        print('Diagnostic only: no PR status or review publication is permitted.')


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
    startup = detail.get('startup_receipt')
    startup_state = detail.get('startup_receipt_status')
    # Older controllers omit the state but may still supply complete proof.
    # A missing receipt without an explicit pending state remains a failure.
    if startup_state is None and type(startup) is dict:
        startup_state = 'recorded'
    runtime.write_receipt(Path(os.environ['RUNNER_TEMP']) / 'preloop-startup', {
        'execution_id': receipt['execution_id'], 'status': detail.get('status'),
        'startup_receipt_status': startup_state,
        'head_sha': receipt['head_sha'], 'base_sha': receipt['base_sha'],
        'startup_receipt': {key: startup.get(key) for key in
            ['version', 'executor', 'lease_revoked', 'commit', 'checkout_verified',
             'setup_completed', 'agent_started_at']} if type(startup) is dict else None})
    require(detail.get('status') in ['RUNNING', 'SUCCEEDED'],
            'Native workload is queued or failed, not a verified running launch')
    require(startup_state in ['pending', 'recorded'],
            'Native startup receipt failed or has an unknown state')
    if startup_state == 'pending':
        require(detail['status'] == 'RUNNING' and startup is None,
                'Pending startup contradicts the execution or receipt')
        runtime.output(startup_verified='false', startup_receipt_status='pending')
        print('Container running; checkout/setup proof pending. '
              'Authenticated completion must verify the receipt before publication.')
        return
    require(type(startup) is dict, 'Malformed native startup receipt')
    require(type(startup.get('version')) is int and startup['version'] == 1 and
            startup.get('executor') == 'hosted' and
            ((detail['status'] == 'RUNNING' and startup.get('lease_revoked') is None) or
             (detail['status'] == 'SUCCEEDED' and startup.get('lease_revoked') is True)) and
            startup.get('commit') == receipt['head_sha'] and
            startup.get('checkout_verified') is True and startup.get('setup_completed') is True and
            type(startup.get('agent_started_at')) is str and startup['agent_started_at'],
            'Native startup has not been proved; inspect the saved execution')
    runtime.output(startup_verified='true', startup_receipt_status='recorded')
    print('Native checkout, setup and agent startup verified for ' + receipt['execution_id'])


if __name__ == '__main__':
    {'prepare': prepare, 'start': start, 'startup': startup}[sys.argv[1]]()
