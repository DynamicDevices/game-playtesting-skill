# Automatic native Preloop review acceptance

This procedure checks the shared DD flow's native GitHub App route for this
repository. Configuration, an old recovered review or local tests do not prove
that a new PR completes it. See the [delivery guide](../.github/PRELOOP-TROUBLESHOOTING.md).

## Start with a real PR event

Use a ready, same-repository PR containing a useful, reviewable change. Under
live signed authority, record the PR number, exact head, target tip, merge base
and complete diff identity. Arm authenticated completion before the event.
The ordinary opened or updated PR event must start the existing native DD flow;
manual dispatch does not prove automatic triggering. Do not enable the retired
Actions trigger, publisher, finalizer or merger, or create another flow.

Keep the candidate frozen through completion. A changed head or target requires
fresh review of the current candidate, not acceptance of an earlier result.
Preserve the admitted provider, model, credentials and security checks.

## Check the workload and its result

Record the native execution URL and its repository, PR, flow revision and event
bindings. Perform one startup validation, then use authenticated completion
events. Require evidence of native clone, exact checkout and complete diff
inspection. A running agent, a model's assertion or a nonzero count of diff
commands alone does not prove those requirements. Missing evidence blocks
delivery acceptance; do not invent a receipt or substitute copied source.

Read the authoritative complete result and its schema validation. Match head and
merge base to the current PR and verify captured evidence/digests through the
supported native evidence interfaces. Archive availability marked `not_checked`
is not integrity verification: downloading verifies the archive digest.
Keep all findings, including LOW findings. A pass requires success=true and no
blocking findings. Changes requested or errors require success=false. Reject
placeholders, missing fields, contradictory passes and all-zero revision IDs.

## Check actual GitHub delivery

Preloop's controller, not the model or an Actions publisher, posts the review
and `preloop/review` commit status. Verify automatic tracker-event publication
and independently read back the authentic Preloop App review on the exact head,
its complete readable findings and matching status linking to the execution.
Pass maps to success; blocking findings map to failure; errors and incomplete
reviews must not become green. Pending publication is not delivered review.
Recover a valid result using supported idempotent native publication under exact
preconditions and applicable authority; do not rerun inference just to post it.
A manual recovery does not prove automatic publication.

## Check protection and merge

Both required CI checks, `Preloop contracts` and `Native prompt regressions`,
must pass on the current head. Preserve strict up-to-date protection, admin
enforcement and all other controls. During migration, retain the old required
`Preloop merge gate` until the specifically approved native transition has its
delivery evidence. Do not fabricate its success or bypass it to finish a test.
After the separately accepted gate replacement, require `preloop/review` bound
to the Preloop App alongside those two CI checks. Only then enable covered
native automatic squash merge and verify the actual protected merge.

## State the outcome accurately

Report automatic triggering, review completion, automatic publication, required
CI and actual merge separately. A delivered review with blocking findings proves
review delivery, not approval. Briar fixes findings, tests and pushes the
correction; the normal native updated event starts the corrected-head review.
Retain the first failed execution. Do not use empty commits, draft toggles,
unchanged paid retries, provider fallback or replacement green statuses.
Unsupported native behaviour goes to Preloop support. A verdict alone is not
merge authority; trust/security and production changes retain explicit approval.

Assisted-by: Briar.
