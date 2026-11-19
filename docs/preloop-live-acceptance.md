# Automatic Preloop review acceptance

This procedure checks the normal PR-review route for this public repository.
A successful configuration check or an old recovered review does not establish
that a new PR can complete that route.

## Start with a real PR event

Use a documentation-only PR with a useful, reviewable change. Record the PR
number, exact head and base commits, and full diff digest before assessing the
result. The ordinary PR event must start the existing review workflow; a manual
flow dispatch does not prove automatic triggering. Keep that candidate frozen
through completion, and report a changed head or base rather than accepting a
review against an earlier revision.

Use the normal signed service policy. The consumed PR14 publication-recovery
exception is not a normal-operation policy and must not be reused for a new PR.
Do not change the provider, flow, credentials or security checks for this test.

## Check the workload and its result

Record the triggering Actions run and the corresponding Preloop execution.
Require native repository clone and exact-checkout evidence, the complete bound
diff, and matching head, base, challenge and result digest. Startup acceptance
alone is not proof of checkout or a completed review. If startup proof is pending,
publication must still require the completed proof.

Keep every finding, including LOW findings. Reject placeholders, incomplete
findings and contradictions between execution success, verdict and findings.
A terminal execution alone is not proof that GitHub received the result.

## Check actual GitHub delivery

After authenticated completion, verify the actual publisher and completion
finalizer runs, their required steps and durable evidence. Independently read
back the authorised bot review and the real check and commit status on the exact
PR revision. Their contents and verdict must agree with the validated result.
Duplicate or stale posts and a manually manufactured green status are failures.

Normal publication starts with unfinished-check semantics. Only the admitted
completion finalizer may release the final verdict after verifying the completed
producer and its evidence. The old retained-failure recovery is not applicable.

## State the outcome accurately

Report automatic triggering, review completion and GitHub delivery separately.
A correctly delivered review containing blocking findings proves delivery, not
approval of the change. Pending work, skipped checks or configuration-only
success must not be reported as a passed end-to-end test.

On failure, retain the first failed execution and identify its failed phase.
Do not repeat a paid review without a concrete correction and the required
authority. Use authenticated completion events rather than repeated status
polling. Leave merging to Alex; a review verdict is not merge authority.
