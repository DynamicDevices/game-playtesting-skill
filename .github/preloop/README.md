# Shared Preloop review publication — integration candidate

The DD integration has signed service authority and is activated. Automatic
triggering and hosted review have been observed, but end-to-end publication and
automatic merge are not yet accepted. Record a successful live PR pilot before
claiming that the full delivery route works. Configuration alone is not proof.
It uses the existing shared organisation flow, not a new flow per repository.

For explicitly admitted ordinary Briar PRs, the intended route is genuine
same-head Preloop review, completed-finalizer admission, required CI and signed
automatic-merge authority. GitHub must enforce `Preloop merge gate` and strict
up-to-date-base checks. Failed, incomplete, stale or placeholder reviews cannot
approve merging. Trust/security changes retain separate explicit approval.

## What runs where

The trusted `pull_request_target`/manual trigger checks out its immutable
`github.workflow_sha`, never PR-head code. It verifies signed service authority
and GitHub OIDC, then checks the open same-repository PR, current head/base and
complete canonical Git diff. A durable pre-spend intent contains the diff hash,
fresh challenge and expected flow/model configuration. Only then does it ask
the repository-bound Preloop CI controller to start a review. A second durable
receipt binds the actual execution ID. There is one startup observation; queued
or accepted is not proof that native clone, checkout, setup and the agent started.

Preloop owns source cloning and the six judgement fields plus the required
native completion marker `status: "success"`. The model does
not generate transport code, challenges, source digests or publication metadata.
The worker receives no GitHub publisher or completion-dispatch token.

A signed `repository_dispatch` completion wakes the authentication job. It
verifies the exact event bytes and fresh timestamp before storing a durable
authenticated wake. The separate publish job joins the native execution/result,
signed result digest, original intent and actual controller receipt. It
recomputes the complete diff and rejects changed head/base or supersession.
It publishes all findings as a readable COMMENT review, a genuine check and
the stable `Preloop review` commit status, then independently reads them back.
Blocking findings are failure; service/integrity failure is error, never success.
The actual publisher Actions run must also succeed for delivery acceptance.

## Native result compatibility

`native_result.py` owns the proposed native schema and its normalization boundary.
Print the schema for operator review with:

```sh
python3 -B .github/preloop/native_result.py
```

The seven required fields include `status: "success"` as the provider's documented
`no_confirmation` workaround. This marks output completion, not a passing review:
`success: false`, blocking findings or a FAILED execution cannot become green
because this marker is present. The model prompt must request this exact schema
without asking the model to run scripts or validate its own output.

The publisher first verifies the signed digest of the untouched public result
projection, including any `container_termination` object. It accepts only empty
`result_withheld_paths` or exactly `["/container_termination"]`; the latter requires
that object to be absent. Every reviewer-field omission, duplicate/subpath or
contradictory presence fails. Explicit successful `schema_validation` with no errors is required.
Only then does it separate the documented controller object and completion marker
from the strict reviewer judgement. Unknown fields, malformed telemetry, missing
schema proof and error responses fail closed. Telemetry and the original digest
are preserved in the publication receipt, not posted as review findings.

Privileged workflow entry points use `python3 -I -B` and a signature-verifying
bootstrap. It stages only the exact SHA256/Git-blob-approved files before
importing publisher/trigger modules; unlisted checkout modules and bytecode do
not enter the privileged import path.

The single historical pilot recovery requires a separately signed original
execution/result/revision tuple, original producer manifests and the exact
advanced target commit. It preserves the original reviewed base, identifies
that base and the current target in the review, and never counts as approval
against the advanced target. Other head/base changes remain stale. Both
workflows must be active for the live revocation check: restore only the recorded
gameplay trigger after reviewed-source/policy/preflight gates, recover without a
new PR event or inference, and pause it again on failure.

With the signed completion-gate policy, an ordinary publisher posts the validated
review but keeps its custom check and status pending. A repository-local `workflow_run`
finalizer independently verifies the completed ORIGINAL publisher, required
jobs/steps, durable publication receipt, authenticated completion and unchanged
review/claim/revisions. It saves its own unique durable intent before releasing
only the owned check/status. Failed/cancelled publishers or failed receipt uploads
cannot become green. The finalizer cannot post another review or run inference.
Its final status links its actual Actions run; the original publisher's identity
remains in the publication evidence. No job claims to observe its own future
completion. Finalizer-only ancillary logging is not added as a new dependency
after gate release. The acceptance caller reads the actual completed original
Actions run, finalizer intent and real review/check/status, and refuses historical
delivery as current-base approval. Ambiguous writes require reconciliation.

GitHub may normalize an Actions-app check's details URL to its own
`https://github.com/<repository>/runs/<check-id>` URL. Validation permits only
that exact check URL or the exact authenticated Actions-run URL, with GitHub
Actions app ID `15368` and slug `github-actions`. Neither URL alone establishes
producer ownership: the signed source, full claim/review, completed producer,
durable publication receipt and finalizer intent remain mandatory. Check output
also links the actual Actions run; commit statuses still require its exact URL.
Publish-only recovery reuses an exactly matching existing review/check rather
than posting another review. Pending updates omit `conclusion`: GitHub requires
a string enum when it is supplied, and supplying it forces completed status.
Ordinary readback must actually show `in_progress` with no conclusion before the pending
receipt is saved. A retained old failure conclusion stops recovery; it is never
silently accepted. No new inference is needed for publication recovery.
If another repair has advanced the target since an existing historical post,
the signed recovery policy must also pin that post's exact review/check IDs,
claim, body hash and original target. Its original body is preserved byte-for-byte;
the new receipt records the newer recovery target separately. Missing or changed
publication evidence refuses all resends and does not count as base approval.

There is one separately signed recovery opt-in for an already completed failed
check: `existing_publication.preserve_failed_check` must be literal `true`, with
the exact existing review/check/body/claim/target tuple and admitted finalizer.
The publisher reuses and verifies that exact `completed`/`failure` check without
any check PATCH or new review/check POST. It keeps native status pending and
saves `pending_check_mode: retained_failure` in its durable receipt. A failed
producer leaves the check failed and native status error. Normal runs and missing
opt-ins retain the ordinary unfinished-check rule; malformed/false opt-ins deny.

Only the finalizer, after actual completed producer, required steps, durable
receipt, authenticated completion, unchanged original review/check/claim and its
unique durable intent, may release the exact owned check's real verdict. Pending
validation of retained failure is never final delivery; final acceptance still
requires the real final verdict/check/status and authenticated finalizer evidence.
Historical recovery remains not approved against the advanced target.

Before live use, coordinate the flow's result_schema/prompt and new signed config
hash with this contract, and include native_result.py in the complete signed
source manifest. No live flow/schema/model or policy was changed by this source
update. Provider evidence is the 13 November 2026 reply and migration guide;
public result API documentation/source confirm the restricted response envelope,
but neither substitutes for the real hosted pilot on our binding.

Only the trusted GitHub publisher holds PR-review/check/status write permissions.
The completion PAT is single-repository Contents:write for dispatch and stays
encrypted in Preloop's subscription; it is not supplied to either job or reviewer.
No privileged job executes PR scripts or grants Contents:write.

## Recovery without another model run

Manual publisher dispatch takes an execution ID and the original authenticated
run ID. It requires that run's successful authentication job and approved source
before accepting its stored wake; it does not call an expired HMAC fresh.
An ambiguous review POST is not blindly retried. Recover only after reconciling
an exact matching prior review. Durable trigger intent prevents duplicate spend;
an interrupted/ambiguous launch needs explicit reconciliation, not another click.
Artifact expiry fails closed and requires a separately approved recovery route.

A signed completion with `result_ready: false` is a service error, not permission
to fetch repeatedly or accept a later unsigned result. It needs a new authenticated
ready completion with its own result digest. A ready completion permits one result
fetch per invocation. HTTP 200 error objects, unavailable results and failed schema
validation remain errors. Preserve the failure, correct or reconcile that phase,
then explicitly invoke publication-only recovery against the same authenticated
execution; do not start another model run to recover a post or an artifact.

Even error-status publication requires durable trigger intent/receipt ownership,
the signed model/configuration binding, matching execution/completion, a current
PR and no newer or ambiguously ordered execution. If any check fails, make no
status write. `preloop-failure-EXECUTION` records the failed publication run, error
class and whether an error status was confirmed, without raw exceptions, tokens
or service logs. Error-reporting failure must not hide the original failure.
Complete validated findings from FAILED executions remain visible but never green.
Recovery reuses the exact owned check rather than creating duplicate checks.
Multiple or substituted check intents require reconciliation. A success status
is sent only after both the complete review and the genuine Actions check have
been independently read back, including the current publication-run link.

## Signed policy and remaining acceptance work

The delivery target is a real PR event, an independent Preloop review, passing
required CI, and automatic merge for explicitly admitted ordinary Briar PRs.
Failed, incomplete, placeholder or stale reviews block merging; a skipped job
is not approval. Trust/security changes retain their specific approval. A
bootstrap exception must be separately explicit, not inferred from a red check.

Automatic merge requires the distinct `Preloop merge gate` context, not just
the preliminary `Preloop review` records. The trigger sets it pending before
launch. A trusted completion workflow releases it only after the actual finalizer
is completed/successful, its exact source and durable intent are authenticated,
the complete review/bot/check/status are independently read back, the PR remains
current and no newer execution supersedes it. Failed/cancelled/interrupted
finalizers cannot release it. The publisher job has a separate name,
`Publish validated Preloop review`, to avoid colliding with its custom check.
The merge-gate workflow receives status-write permission, not source-write or
merge permission. GitHub's native auto-merge still requires applicable CI.
Enable this route only with exact signed `publication_merge_gate` admission,
the fourth workflow in live-revocation bindings and actual required-check rules.

Commit-status publication performs one POST and independent combined/list
readbacks. If exactly one endpoint lacks the posted ID or shows an older ID,
while the other proves the exact write, it may perform one additional list then
combined observation. Wrong commit/actor, malformed IDs, same-ID conflicts and
visibly newer writes are not retryable. Final ID, commit, context, state, run
URL and actor agreement remains mandatory. There is no sleep, loop or rePOST.

`PRELOOP_PUBLICATION_AUTHORITY` and `PRELOOP_PUBLICATION_SIGNATURE` must preserve
exact signed bytes. `install_policy.py` writes them only to runner-local files.
The policy must bind repository/provider/project/principal, flow/model/config,
trusted workflows, complete source SHA-256/Git blob manifests, actor, OIDC,
allowed operations, callback tolerance, expiry and revocation. See `trust.py`
for the validation contract, not a transferable authority template.

Native execution detail does not independently attest the runtime model ID.
Acceptance therefore requires Alex's explicit fixed-flow configuration contract;
do not describe that exception as per-execution model attestation.

Before each GitHub write or native trigger/stop, the candidate rechecks the
signature, expiry and source bytes, then fetches the current states of both
repository review workflows and the exact running Actions attempt. The signed
repository binding must explicitly approve `live_revocation` with
`mechanism: github-actions-path-source-and-run-v1`, `explicit_posture_approval: true`
and `workflow_paths` mapping both `preloop-review-trigger.yml` and
`preloop-review-publish.yml` to their exact `.github/workflows/NAME` paths.
The same signed policy pins complete source hashes and OIDC workflow/ref identity.
At each write boundary, resolve each filename through GitHub, verify its path and
active state, and bind the current run to that live numeric workflow ID. Numeric
IDs need not exist before bootstrap installation. Re-registration of identical
approved source at the same path remains eligible only if all other signed
source, OIDC, run/attempt and live-state checks pass; this is path/source identity,
not a numeric incarnation pinned forever. Alex selected this design correction;
final exact hardware-signed policies and live acceptance remain mandatory.
Missing approval, API failure, disabled/substituted workflows, cancelled or
completed runs, changed revisions and old attempts deny the operation.

This is a proposed service-suspension mechanism, not accepted live proof or
automatic desktop signing-key revocation propagation. To revoke service operation,
disable either bound workflow, cancel every affected running attempt and reconcile
any operation already in flight. Cancel before re-enabling workflows so an old
attempt cannot resume. Re-enabling is not renewal of an expired signed policy.
The state read and subsequent write are not atomic; GitHub may accept a write
already in flight at cancellation. Preserve its receipts and reconcile effects.
The exact mechanism, identities and residual race require independent review,
Alex's final policy signature and a real cancellation/suspension pilot before
activation; fixtures do not prove GitHub runtime enforcement. A signing-key
revocation separately requires service suspension and policy/credential handling.

Startup makes one execution-detail read and saves the allowlisted controller
observation as `preloop-startup-EXECUTION` before interpreting startup proof.

The native receipt has a lifecycle: `lease_revoked` is null while running and
literal true after confirmed terminal read-lease cleanup. Running startup accepts
only null; already-successful startup and completed-result publication require
true. Missing/false/malformed cleanup proof refuses completed publication. The
exact admitted commit, controller-observed checkout/setup and agent-start checks
remain mandatory. An owner-account response omits this restricted-CI receipt;
inspect it with the repository-bound CI identity, not the owner schema.

Queued/failed executions do not count as running. No sleep loop, polling or
automatic re-trigger compensates for startup timing. A live queued observation
remains a failed startup gate requiring phase diagnosis, not successful delivery.

Review publication additionally requires the exact trigger workflow to have
completed successfully, including its `Validate native startup once` step.
A later valid controller result cannot erase a failed, cancelled, skipped or
unfinished trigger. The finalizer independently rechecks that trigger and its
execution/PR/head/base binding before releasing the review gate. Explicitly
pending startup remains permitted by the initial observation only when the
completed result later supplies the full startup and cleanup proof. If completion
arrives before the trigger finishes, publication fails closed; recover publication
against the existing result after diagnosis, without another inference run.
Only owned failure-status cleanup may read failed or still-running trigger
receipts; it cannot publish a review or a successful gate.

Finalization records its exact release attempt before touching GitHub. If any
release write, readback or final status fails, it preserves the original failure
and attempts to mark only its authenticated owned check as failed, then posts
an error status even if the check correction fails. Cleanup rechecks the current
PR, supersession, exact check/claim/revision/actor and original-or-current run
marker; changed ownership or target evidence denies cleanup writes. The workflow
preserves failure/attempt receipts after a failed release for explicit
reconciliation. It does not retry release or inference. API outages, revocation,
cancellation and runner loss can prevent cleanup or receipt upload; any partial
visible success is not accepted delivery and must be reconciled from the saved
intent, workflow outcome and available failure evidence.
Final delivery also requires the exact finalizer workflow, its bound job and
`Finalize owned review gate` step to have completed successfully. A failed
finalizer's durable intent and visible success records cannot satisfy acceptance,
even when API failures prevent cleanup. Failed receipts remain diagnostic only.

GitHub commit-status publication performs one POST and verifies both the
exact-commit combined status and the actor-bearing status list. If the combined
record already exactly matches the write but the list lacks it (or still shows
another GitHub Actions record), the helper makes one additional list read and
then a fresh combined read. It does not sleep, loop or repeat the POST. Both
final snapshots must agree on this write's exact ID, state, run URL and context;
the combined commit and list actor must also match. Wrong actors, conflicting
values on the same record, malformed evidence, combined mismatches and ongoing
inconsistency fail closed. This tolerates one inconsistent read pair; it does
not guarantee GitHub propagation or make failed historical triggers successful.

Automatic `pull_request_target` events for draft PRs skip the trigger job before
checkout, credentials or launch. Marking a PR ready still triggers normal review.
A skipped job is not a passed review and does not release a review gate. Manual
dispatch retains the helper's explicit draft/closed-PR denial. This workflow
change only affects trusted runs after it is merged and its exact source policy
is signed and installed; changing PR-head YAML cannot modify current base runs.

The 19November review of PR20 exhausted the DD flow's300-second launch budget
while successful model/tool calls were still occurring. Its separate proposed
600-second native deadline remains subject to complete configuration review and
matching signed installation gates. The hard whole-workload cutoff and terminal
cleanup remain required; a larger deadline is not proof a review will finish.

GitHub dispatch workflows must already be on the default branch. A repair of
the installed review gate does not authorise bypassing it: any exceptional
installation route needs its own exact signed scope, independent correctness
and security acceptance of the complete privileged source and installer, real
CI and matching signed runtime source bindings. A signature is not a review
verdict. Earlier exceptions do not apply to later PRs. Ordinary delivery still
requires the installed automated review and completed-finalizer merge gate;
source review or a desktop status cannot substitute for that live acceptance.

Canonical source review requires an up-to-date branch: target tip must equal
the merge base. If the target advances, update the branch and review the new
candidate. Binary diffs are explicitly refused because this text-only route
does not contain the binary patch bytes; an incomplete diff cannot pass.

Both signature loaders accept exactly one nonblank pinned public-key line and
require the key in the signed source manifest. Failure cleanup revalidates the
current revision, supersession and exact check ownership before any correction;
a stale or differently owned check receives no cleanup write. Failed or
unconfirmed cleanup remains visible and cannot replace the original failure.

## Offline regression tests

```sh
python3 -B -m unittest discover -s .github/preloop -p 'test_*.py' -v
```

These tests use synthetic local APIs and do not start Preloop, touch a device or
publish anything. They cover result bindings, full-diff/nonce checks, complete
findings and safe Markdown, HMAC tampering/staleness, trigger replay, execution
substitution, startup/revocation proof, write restrictions, publication readback
and authenticated recovery. They do not prove hosted execution, actual token
permissions, live dispatch delivery, independent review or merge acceptance.

Assisted-by: Briar.
