"""Authenticate completion, then publish owned results without rerunning models."""
import json
import hashlib
import os
from pathlib import Path
import re
import sys
import time

from bound_review import bind_completed_review, bind_owned_execution
from completion_contract import verify_dispatch
from review_contract import require, review_body
import runtime


def authenticate():
    binding, workload, github = runtime.context('preloop-review-publish.yml')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    if os.environ['GITHUB_EVENT_NAME'] == 'repository_dispatch':
        completion = verify_dispatch(event, os.environ['PRELOOP_CALLBACK_SECRET'], binding,
                                     int(time.time()), binding['callback_tolerance_seconds'])
        wake = {'completion': completion, 'authenticated_run_id': os.environ['GITHUB_RUN_ID'],
                'workflow_sha': workload['workflow_sha']}
    else:
        require(os.environ['GITHUB_EVENT_NAME'] == 'workflow_dispatch', 'Wrong publication event')
        eid, previous = event['inputs']['execution_id'], event['inputs']['authenticated_run_id']
        require(re.fullmatch('[0-9a-f-]{36}', eid) and previous.isdigit(), 'Invalid recovery inputs')
        # The original authentication job must have succeeded under the signed
        # trusted source. No old signature is silently treated as fresh.
        wake = runtime.artifact(github, binding, 'preloop-wake-' + eid,
                                'preloop-review-publish.yml', allow_failed=True, run_id=previous)
        completion = wake['completion']
        require(completion['execution_id'] == eid and
                str(wake['authenticated_run_id']) == previous, 'Wrong recovery wake')
    runtime.write_receipt(Path(os.environ['RUNNER_TEMP']) / 'preloop-wake', wake)
    runtime.output(execution_id=completion['execution_id'], pr_number=completion['pr_number'])


def no_supersession(binding, token, completion):
    rows = runtime.executions(binding, token)
    selected = [row for row in rows if row['id'] == completion['execution_id']]
    require(len(selected) == 1 and selected[0].get('start_time'), 'Missing owned execution history')
    own_start = selected[0]['start_time']
    for row in rows:
        if row['pr_number'] == completion['pr_number'] and row['id'] != completion['execution_id']:
            require(row.get('start_time') and row['start_time'] < own_start,
                    'A newer or ambiguously ordered review supersedes this result')


def owned_receipts(github, binding, eid):
    """The error path must prove the same durable ownership as review publication."""
    require(re.fullmatch('[0-9a-f-]{36}', eid), 'Invalid execution ID')
    wake = runtime.artifact(github, binding, 'preloop-wake-' + eid,
                            'preloop-review-publish.yml', run_id=os.environ['GITHUB_RUN_ID'],
                            allow_current=True)
    completion = wake['completion']
    require(completion['execution_id'] == eid, 'Wrong authenticated wake')
    receipt = runtime.artifact(github, binding, 'preloop-trigger-' + eid,
                               'preloop-review-trigger.yml')
    # Applies to BOTH review publication and the error-status fallback. A
    # diagnostic cannot overwrite the PR gate, even if its model claims pass.
    require('diagnostic_rerun' not in receipt,
            'Diagnostic reproduction is not eligible for PR review/status publication')
    name = 'preloop-intent-' + str(receipt['pr_number']) + '-' + receipt['head_sha'] + '-' + receipt['base_sha']
    intent = runtime.artifact(github, binding, name, 'preloop-review-trigger.yml',
                              run_id=receipt['trigger_run_id'])
    require(receipt['model_id'] == binding['model_id'] and
            receipt['flow_config_sha256'] == binding['native_ci_contract']['flow_config_sha256'],
            'Native model/configuration differs from signed policy')
    return completion, intent, receipt


def initial_check_attempt(github, binding, completion, receipt):
    """Use the pre-existing durable authenticated wake as a once-only intent.

    The native per-PR job concurrency serializes publishers. Its authentication
    job uploads this receipt BEFORE this job can run. A later run or attempt may
    reuse a discovered check, but must never infer permission for another POST
    merely from an empty check listing after an interrupted creation.
    """
    require(os.environ.get('GITHUB_RUN_ATTEMPT', '1') == '1',
            'Check creation on a repeated run requires explicit reconciliation')
    eid = completion['execution_id']
    name = 'preloop-wake-' + eid
    rows = runtime.github_pages(github, '/repos/' + binding['repository'] +
        '/actions/artifacts?name=' + name, 'artifacts')
    current = os.environ['GITHUB_RUN_ID']
    valid = all(row.get('name') == name and not row.get('expired') for row in rows)
    runs = [str(row.get('workflow_run', {}).get('id')) for row in rows]
    if valid and runs == [current] and os.environ.get('GITHUB_EVENT_NAME') != 'workflow_dispatch':
        return
    require(valid and len(rows) == 2 and len(set(runs)) == 2 and current in runs,
            'Earlier or missing durable publication intent; reconcile before check creation')
    require(type(binding.get('publication_recovery')) is dict,
            'Earlier durable publication intent requires signed reconciliation')
    permit = runtime.recovery_scope(binding, completion)
    previous = permit['original_publisher_run_id']
    require(set(runs) == {previous, current} and previous != current and
            str(receipt.get('trigger_run_id')) == permit['trigger_run_id'],
            'Durable publication intents differ from the signed reconciliation')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    require(os.environ.get('GITHUB_EVENT_NAME') == 'workflow_dispatch' and
            event.get('inputs') == dict(execution_id=eid, authenticated_run_id=previous),
            'First-check recovery requires the exact publish-only dispatch')
    wake = runtime.artifact(github, binding, name, 'preloop-review-publish.yml',
                            allow_failed=True, run_id=previous)
    require(wake.get('completion') == completion and
            str(wake.get('authenticated_run_id')) == previous,
            'Reconciled completion wake changed')


def publish():
    binding, _workload, github = runtime.context('preloop-review-publish.yml')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    eid = os.environ['PRELOOP_EXECUTION_ID']
    completion, intent, receipt = owned_receipts(github, binding, eid)
    token = os.environ['PRELOOP_CI_TOKEN']
    detail = runtime.preloop('/flows/executions/' + eid, token)
    bind_owned_execution(completion, intent, receipt, detail)
    require(completion.get('result_ready') is True,
            'Signed completion has no result; require a new authenticated ready completion')
    # Fetch a ready result even on FAILED so genuine findings are not discarded.
    artifact = runtime.preloop('/flows/executions/' + eid + '/result', token)
    digest = runtime.full_diff_sha256(binding['repository'], receipt['base_sha'], receipt['head_sha'],
                                     os.environ['GH_TOKEN'])
    proof = bind_completed_review(completion, intent, receipt, detail, artifact, digest)
    no_supersession(binding, token, completion)
    number, head, base = receipt['pr_number'], receipt['head_sha'], receipt['base_sha']
    runtime.current_pr(github, binding, number, head, base)
    root = '/repos/' + binding['repository']
    path = root + '/pulls/' + str(number)
    run_url = 'https://github.com/' + binding['repository'] + '/actions/runs/' + os.environ['GITHUB_RUN_ID']
    marker = '<!-- briar-preloop:' + eid + ':' + proof['claim_sha256'] + ' -->'
    body = review_body(proof['result']) + '\nExecution: https://preloop.ai/console/flows/executions/' + eid
    historical = runtime.historical_target(binding, number, head, base)
    if historical:
        body += ('\n\nHistorical review recovery. Reviewed head: ' + head +
                 '\nOriginal reviewed base: ' + base + '\nCurrent target: ' + historical +
                 '\nThis publishes the original review, not approval against the advanced target.')
    body += '\n\nResult: ' + proof['state'] + '\n\nPosted by Briar on Alex\'s behalf.\n' + marker
    reviews = runtime.github_pages(github, path + '/reviews')
    execution_marker = '<!-- briar-preloop:' + eid + ':'
    owned = [review for review in reviews if execution_marker in (review.get('body') or '') and
             review.get('user', {}).get('login') == 'github-actions[bot]']
    require(all(marker in (review.get('body') or '') and review.get('commit_id') == head
                for review in owned), 'Execution already has a different publication claim; reconcile')
    matching = [review for review in owned if marker in (review.get('body') or '') and
                review.get('commit_id') == head and review.get('user', {}).get('login') == 'github-actions[bot]']
    require(len(matching) <= 1, 'Duplicate review publication')
    checks = runtime.github_pages(github, root + '/commits/' + head +
                                  '/check-runs?check_name=Preloop%20review&filter=all', 'check_runs')
    owned_checks = [check for check in checks if
                    execution_marker in (check.get('output', {}).get('text') or '') and
                    check.get('app', {}).get('slug') == 'github-actions']
    require(all(check.get('external_id') == 'briar-preloop:' + proof['claim_sha256']
                for check in owned_checks),
            'Execution already has a different check claim; reconcile')
    intents = [check for check in checks if check.get('external_id') == 'briar-preloop:' + proof['claim_sha256']]
    require(len(intents) <= 1, 'Duplicate check intent; reconcile before recovery')
    if intents:
        require(intents[0].get('head_sha') == head and intents[0].get('name') == 'Preloop review' and
                intents[0].get('app', {}).get('slug') == 'github-actions', 'Wrong existing check intent')
    require(matching or not intents, 'Ambiguous earlier review send; reconcile before replay')
    # This genuine check is created by the actual trusted Actions publisher,
    # tied to the reviewed SHA and workflow run, never by a desktop status script.
    if not intents:
        initial_check_attempt(github, binding, completion, receipt)
    check = intents[0] if intents else github(root + '/check-runs', 'POST', {
        'name': 'Preloop review', 'head_sha': head, 'status': 'in_progress', 'details_url': run_url,
        'external_id': 'briar-preloop:' + proof['claim_sha256'],
        'output': {'title': 'Validated Preloop result; publication pending', 'summary': 'Review intent recorded.',
                   'text': marker}})
    try:
        runtime.current_pr(github, binding, number, head, base)
        no_supersession(binding, token, completion)
        review = matching[0] if matching else github(path + '/reviews', 'POST', {
            'event': 'COMMENT', 'commit_id': head, 'body': body})
        readback = github(path + '/reviews/' + str(review['id']))
        require(readback.get('body') == body and readback.get('commit_id') == head and
                readback.get('state') == 'COMMENTED' and readback.get('submitted_at') and
                readback.get('user', {}).get('login') == 'github-actions[bot]', 'Review readback mismatch')
        runtime.current_pr(github, binding, number, head, base)
        no_supersession(binding, token, completion)
        conclusion = 'success' if proof['state'] == 'success' else 'failure'
        pending = bool(binding.get('publication_finalizer'))
        update = {'status': 'in_progress' if pending else 'completed', 'details_url': run_url,
            'output': {'title': 'Review published; awaiting completed Actions' if pending else
                       'Preloop review published', 'summary': readback['html_url'], 'text': marker}}
        if not pending:
            update['conclusion'] = conclusion
        github(root + '/check-runs/' + str(check['id']), 'PATCH', update)
        actual_check = github(root + '/check-runs/' + str(check['id']))
        require(actual_check['head_sha'] == head and
                actual_check.get('conclusion') == (None if pending else conclusion) and
                actual_check['status'] == ('in_progress' if pending else 'completed') and
                actual_check['external_id'] == check['external_id'],
                'Review check readback mismatch')
        require(actual_check['name'] == 'Preloop review' and
                actual_check.get('app', {}).get('slug') == 'github-actions' and
                actual_check.get('details_url') == run_url, 'Wrong review check actor or run link')
        runtime.current_pr(github, binding, number, head, base)
        no_supersession(binding, token, completion)
        status = runtime.commit_status(github, binding, head, 'pending' if pending else proof['state'], run_url,
                                        'Awaiting completed publisher and durable evidence.' if pending else
                                        'Complete review and genuine check independently read back.')
        runtime.write_receipt(Path(os.environ['RUNNER_TEMP']) / 'preloop-publication', {
            'execution_id': eid, 'head_sha': head, 'base_sha': base, 'claim_sha256': proof['claim_sha256'],
            'review_id': review['id'], 'review_url': readback['html_url'], 'check_id': check['id'],
            'review_body_sha256': hashlib.sha256(body.encode('utf-8')).hexdigest(),
            'publication_run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT', '1'),
            'status_id': status['id'], 'state': proof['state'], 'actions_run_url': run_url,
            'result_sha256': completion['result_sha256'],
            'native_completion_status': proof['native_completion_status'],
            'execution_status': detail['status'], 'review_verdict': proof['result']['verdict'],
            'controller_metadata': proof['controller_metadata'],
            'historical_target_sha': historical})
        return 0 if proof['state'] == 'success' else 1
    except Exception:
        try:
            github(root + '/check-runs/' + str(check['id']), 'PATCH', {
                'status': 'completed', 'conclusion': 'failure',
                'output': {'title': 'Publication failed', 'summary': 'Reconcile saved intent before any resend.',
                           'text': marker}})
        except Exception as secondary:
            print('Publication failure check was not confirmed: ' + type(secondary).__name__,
                  file=sys.stderr)
        raise


def publish_error_status():
    """An error needs authenticated target/ownership, never an invented clean review."""
    binding, _workload, github = runtime.context('preloop-review-publish.yml')
    eid = os.environ['PRELOOP_EXECUTION_ID']
    completion, intent, receipt = owned_receipts(github, binding, eid)
    detail = runtime.preloop('/flows/executions/' + eid, os.environ['PRELOOP_CI_TOKEN'])
    bind_owned_execution(completion, intent, receipt, detail)
    no_supersession(binding, os.environ['PRELOOP_CI_TOKEN'], completion)
    runtime.current_pr(github, binding, completion['pr_number'], completion['head_sha'], completion['base_sha'])
    local = Path(os.environ['RUNNER_TEMP']) / 'preloop-publication/receipt.json'
    if local.exists():
        recorded = json.loads(local.read_text())
        claim = recorded.get('claim_sha256')
        require(all(recorded.get(k) == completion[k] for k in
                    ['execution_id', 'head_sha', 'base_sha', 'result_sha256']) and
                type(claim) is str and re.fullmatch('[0-9a-f]{64}', claim),
                'Late-failure publication receipt differs')
        root = '/repos/' + binding['repository']
        check_path = root + '/check-runs/' + str(recorded['check_id'])
        check = github(check_path)
        require(check.get('head_sha') == completion['head_sha'] and
                check.get('name') == 'Preloop review' and
                check.get('external_id') == 'briar-preloop:' + claim and
                check.get('app', {}).get('slug') == 'github-actions' and
                check.get('details_url') == 'https://github.com/' + binding['repository'] +
                    '/actions/runs/' + os.environ['GITHUB_RUN_ID'] and
                '<!-- briar-preloop:' + eid + ':' + claim + ' -->' in
                    (check.get('output', {}).get('text') or ''),
                'Late-failure check ownership differs')
        if (recorded.get('state') == 'failure' and
                recorded.get('execution_status') == 'SUCCEEDED' and
                recorded.get('review_verdict') == 'changes_requested' and
                ((check.get('status') == 'completed' and check.get('conclusion') == 'failure') or
                 (binding.get('publication_finalizer') and check.get('status') == 'in_progress' and
                  check.get('conclusion') is None)) and
                os.environ.get('PRELOOP_PUBLISH_OUTCOME') == 'failure' and
                os.environ.get('PRELOOP_PUBLICATION_UPLOAD_OUTCOME') == 'success'):
            # A delivered blocking judgement is not a delivery/service failure.
            return
        github(check_path, 'PATCH', {'status': 'completed', 'conclusion': 'failure',
            'output': {'title': 'Publisher workflow failed after review publication',
                       'summary': 'No completed delivery acceptance; reconcile durable evidence.',
                       'text': check['output']['text']}})
    run_url = 'https://github.com/' + binding['repository'] + '/actions/runs/' + os.environ['GITHUB_RUN_ID']
    runtime.commit_status(github, binding, completion['head_sha'], 'error', run_url,
                          'Review validation or publication failed; no accepted review gate.')


def run_publication():
    """Preserve failure without masking it if the error-status gate also refuses."""
    try:
        return publish()
    except Exception as failure:
        posted = False
        try:
            publish_error_status()
            posted = True
        except Exception:
            # Unknown ownership, stale target or unavailable API must not write.
            print('Error status was not confirmed; reconcile the saved run.', file=sys.stderr)
        try:
            runtime.write_receipt(Path(os.environ['RUNNER_TEMP']) / 'preloop-failure', {
                'state': 'error', 'execution_id': os.environ['PRELOOP_EXECUTION_ID'],
                'publication_run_id': os.environ['GITHUB_RUN_ID'],
                'failure_type': type(failure).__name__, 'error_status_confirmed': posted,
                'recovery': 'Reconcile this run, correct the failed phase, then recover the owned result; never rerun inference for publication.'})
        except Exception as secondary:
            print('Publication failure receipt was not saved: ' + type(secondary).__name__,
                  file=sys.stderr)
        raise


if __name__ == '__main__':
    if sys.argv[1] == 'authenticate':
        authenticate()
    elif sys.argv[1] == 'late-failure':
        publish_error_status()
    else:
        raise SystemExit(run_publication())
