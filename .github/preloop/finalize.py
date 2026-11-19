"""Release native gates only after the original publisher completed. Assisted-by: Briar."""
import json
import os
from pathlib import Path
import re
import sys

import publisher
from review_contract import require
import runtime

WORKFLOW = 'preloop-review-finalize.yml'


def producer(github, binding):
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    require(os.environ['GITHUB_EVENT_NAME'] == 'workflow_run' and event.get('action') == 'completed' and
            event.get('repository', {}).get('id') == binding['repository_id'], 'Wrong finalizer event')
    hinted = event.get('workflow_run', {})
    run_id = hinted.get('id')
    require(type(run_id) is int and run_id > 0 and
            hinted.get('path', '').split('@')[0] == '.github/workflows/preloop-review-publish.yml',
            'Wrong publisher completion hint')
    rows = runtime.github_pages(github, '/repos/' + binding['repository'] +
                                '/actions/runs/' + str(run_id) + '/artifacts', 'artifacts')
    publications = [row for row in rows if re.fullmatch('preloop-publication-[0-9a-f-]{36}', row.get('name', ''))]
    require(len(publications) == 1 and not publications[0].get('expired'),
            'Missing unique durable publication receipt')
    eid = publications[0]['name'].removeprefix('preloop-publication-')
    receipt = runtime.artifact(github, binding, publications[0]['name'],
        'preloop-review-publish.yml', allow_failed=True, run_id=str(run_id))
    wake = runtime.artifact(github, binding, 'preloop-wake-' + eid,
        'preloop-review-publish.yml', allow_failed=True, run_id=str(run_id))
    completion = wake['completion']
    require(receipt.get('execution_id') == eid and
            all(receipt.get(k) == completion.get(k) for k in
                ['execution_id', 'head_sha', 'base_sha', 'result_sha256']) and
            completion.get('status') == 'SUCCEEDED' and completion.get('result_ready') is True,
            'Publication and authenticated completion differ')
    trigger = runtime.artifact(github, binding, 'preloop-trigger-' + eid,
                               'preloop-review-trigger.yml')
    require(all(trigger.get(k) == completion.get(k) for k in
                ['execution_id', 'pr_number', 'head_sha', 'base_sha']) and
            trigger.get('execution_id') == eid,
            'Successful trigger and publication differ')
    number, head, base = completion['pr_number'], completion['head_sha'], completion['base_sha']
    evidence = runtime.completed_publication(github, binding, str(run_id), eid, number, head, base, pending=True)
    require(evidence['publication_receipt'] == receipt, 'Producer receipt changed')
    publisher.no_supersession(binding, os.environ['PRELOOP_CI_TOKEN'], completion)
    return str(run_id), receipt, completion


def intent_name(run_id, receipt):
    return 'preloop-finalize-' + receipt['execution_id'] + '-' + run_id


def cleanup_failed_release(github, binding, receipt, completion, run_id, marker, run_url):
    """Failure-only correction after durable ownership was verified by release.

    A wrong owner, changed PR or superseding execution denies all cleanup writes.
    Once ownership is established, a failed check PATCH must not prevent the
    independent error-status attempt. Every write still passes runtime's live gate.
    """
    outcome = dict(check='not_attempted', status='not_attempted')
    root = '/repos/' + binding['repository']
    check_path = root + '/check-runs/' + str(receipt['check_id'])
    head, base, number = completion['head_sha'], completion['base_sha'], completion['pr_number']
    try:
        runtime.current_pr(github, binding, number, head, base)
        publisher.no_supersession(binding, os.environ['PRELOOP_CI_TOKEN'], completion)
        actual = github(check_path)
        text = actual.get('output', {}).get('text')
        original_marker = marker.split('\n')[0]
        require(actual.get('id') == receipt['check_id'] and actual.get('head_sha') == head and
                actual.get('name') == 'Preloop review' and
                actual.get('external_id') == 'briar-preloop:' + receipt['claim_sha256'] and
                text in [original_marker, marker], 'Failed-release check ownership differs')
        owner_url = (run_url if text == marker else 'https://github.com/' +
                     binding['repository'] + '/actions/runs/' + run_id)
        runtime.verify_check_url(actual, binding, owner_url)
    except Exception as failure:
        outcome['ownership_error'] = type(failure).__name__
        return outcome
    try:
        github(check_path, 'PATCH', {'status': 'completed', 'conclusion': 'failure',
            'output': {'title': 'Finalization failed; delivery is not accepted',
                'summary': 'Partial release requires explicit reconciliation. Actions: ' + run_url,
                'text': text}})
        corrected = github(check_path)
        require(corrected.get('id') == receipt['check_id'] and corrected.get('head_sha') == head and
                corrected.get('external_id') == 'briar-preloop:' + receipt['claim_sha256'] and
                corrected.get('output', {}).get('text') == text and
                corrected.get('status') == 'completed' and corrected.get('conclusion') == 'failure',
                'Failed-release check cleanup readback differs')
        runtime.verify_check_url(corrected, binding, owner_url)
        outcome['check'] = 'failure_confirmed'
    except Exception as failure:
        outcome.update(check='unconfirmed', check_error=type(failure).__name__)
    try:
        runtime.current_pr(github, binding, number, head, base)
        publisher.no_supersession(binding, os.environ['PRELOOP_CI_TOKEN'], completion)
        runtime.commit_status(github, binding, head, 'error', run_url,
                              'Finalization failed; partial release requires reconciliation.')
        outcome['status'] = 'error_confirmed'
    except Exception as failure:
        outcome.update(status='unconfirmed', status_error=type(failure).__name__)
    return outcome


def prepare():
    binding, _, github = runtime.context(WORKFLOW)
    run_id, receipt, completion = producer(github, binding)
    require(os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'Finalization retry requires reconciliation')
    name = intent_name(run_id, receipt)
    previous = runtime.github_pages(github, '/repos/' + binding['repository'] +
                                   '/actions/artifacts?name=' + name, 'artifacts')
    require(not previous, 'Earlier finalization intent; reconcile before replay')
    runtime.write_receipt(Path(os.environ['RUNNER_TEMP']) / 'preloop-finalize', {
        'publisher_run_id': run_id, 'finalizer_run_id': os.environ['GITHUB_RUN_ID'],
        'publication_receipt': receipt, 'completion': completion})
    runtime.output(intent_name=name, execution_id=receipt['execution_id'], publisher_run_id=run_id)


def release():
    binding, _, github = runtime.context(WORKFLOW)
    require(os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'Finalization retry requires reconciliation')
    run_id, receipt, completion = producer(github, binding)
    name = intent_name(run_id, receipt)
    current = os.environ['GITHUB_RUN_ID']
    rows = runtime.github_pages(github, '/repos/' + binding['repository'] +
                               '/actions/artifacts?name=' + name, 'artifacts')
    require(len(rows) == 1 and rows[0].get('name') == name and not rows[0].get('expired') and
            str(rows[0].get('workflow_run', {}).get('id')) == current,
            'Ambiguous or earlier finalization intent')
    intent = runtime.artifact(github, binding, name, WORKFLOW, run_id=current, allow_current=True)
    require(intent == dict(publisher_run_id=run_id, finalizer_run_id=current,
                           publication_receipt=receipt, completion=completion),
            'Finalization intent changed')
    root = '/repos/' + binding['repository']
    number, head, base = completion['pr_number'], completion['head_sha'], completion['base_sha']
    run_url = 'https://github.com/' + binding['repository'] + '/actions/runs/' + current
    marker = '<!-- briar-preloop:' + receipt['execution_id'] + ':' + receipt['claim_sha256'] + ' -->'
    marker += '\n<!-- briar-preloop-finalized:' + run_id + ':' + current + ':' + receipt['claim_sha256'] + ' -->'
    check_path = root + '/check-runs/' + str(receipt['check_id'])
    runtime.current_pr(github, binding, number, head, base)
    publisher.no_supersession(binding, os.environ['PRELOOP_CI_TOKEN'], completion)
    # Record the exact attempt before a possibly ambiguous GitHub write. This
    # never authorizes a replay; the existing durable intent remains single-use.
    runtime.write_receipt(Path(os.environ['RUNNER_TEMP']) / 'preloop-finalize-release', intent)
    try:
        github(check_path, 'PATCH', {'status': 'completed', 'conclusion': receipt['state'],
            'details_url': run_url, 'output': {'title': 'Completed publisher and durable review verified',
            'summary': receipt['review_url'] + '\n\nActions: ' + run_url, 'text': marker}})
        actual = github(check_path)
        require(actual.get('status') == 'completed' and actual.get('conclusion') == receipt['state'] and
                actual.get('head_sha') == head and actual.get('id') == receipt['check_id'] and
                actual.get('external_id') == 'briar-preloop:' + receipt['claim_sha256'] and
                actual.get('app', {}).get('slug') == 'github-actions' and
                actual.get('output', {}).get('text') == marker, 'Finalized check readback mismatch')
        runtime.verify_check_url(actual, binding, run_url)
        runtime.current_pr(github, binding, number, head, base)
        publisher.no_supersession(binding, os.environ['PRELOOP_CI_TOKEN'], completion)
        runtime.commit_status(github, binding, head, receipt['state'], run_url,
                              'Original publisher completed; durable review independently verified.')
    except Exception as failure:
        # Never replace the original release exception with cleanup/evidence
        # errors, nor include arbitrary exception text that might contain secrets.
        report = dict(intent, failure_type=type(failure).__name__)
        try:
            report['cleanup'] = cleanup_failed_release(
                github, binding, receipt, completion, run_id, marker, run_url)
        except Exception as cleanup_failure:
            report['cleanup'] = dict(unconfirmed=type(cleanup_failure).__name__)
        try:
            runtime.write_receipt(Path(os.environ['RUNNER_TEMP']) / 'preloop-finalize-failure', report)
        except Exception as evidence_failure:
            report['evidence_error'] = type(evidence_failure).__name__
        try:
            print(json.dumps(report, sort_keys=True), file=sys.stderr)
        except Exception:
            pass  # A broken log stream must not replace the release failure.
        raise


if __name__ == '__main__':
    if sys.argv[1:] == ['prepare']:
        prepare()
    elif sys.argv[1:] == ['release']:
        release()
    else:
        raise SystemExit('Unknown finalization phase')
