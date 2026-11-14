# Proposed native review context correction

The real Nail pilot reached native completion but returned forty zeroes for
both commit IDs. The publisher rejected it. Its resolved prompt contained no
expected repository/PR/head/base context, although the restricted-CI event
carried repository.full_name and pull_request.number/head.sha/base.ref.
There was no base.sha. This does not prove whether built-in source-reading
commands ran; tool_calls_count alone is not that evidence.

The supported prompt template correction is to prepend the following target
context to the existing generic shared DD review prompt, leaving its schema,
fixed model, read-only native clone and empty MCP allowlists unchanged:

```text
Repository: {{trigger_event.payload.repository.full_name}}
Pull request number: {{trigger_event.payload.pull_request.number}}
Expected head commit: {{trigger_event.payload.pull_request.head.sha}}
Target branch: {{trigger_event.payload.pull_request.base.ref}}
```

These are target identifiers, not proof that the model inspected source. Require
the agent to locate the native checkout, verify actual origin and HEAD, determine
the merge base against the fetched target branch and inspect the entire diff.
It must not substitute the branch tip for the merge base, echo target IDs as
inspection proof, use all-zero placeholders, or replace native cloning with an
uploaded source packet. Missing context, checkout, base or diff access must be an
explicit error, not a pass. The trusted publisher's independent exact-revision,
diff, challenge, controller-receipt, authority and publication checks remain.

The exact complete prefix proposal is [preloop-review-context-prefix.txt](preloop-review-context-prefix.txt),
copied byte-for-byte from dd-review-context-prefix.txt in the owning work record,
with these instructions in addition to the four fields above. It is review data,
not executable preparation code or a runtime-installed change.
Prepending it to baseline4cb74500b44124bd61d8d259980efe2c5ca6dc35c0085a9ad2286ac621317a07
produces proposed configuration hash
591136b6c1f99e4741719720ac27893db39e9fa195d226d6d6444b6441efc63b;
only prompt_template changes. Literal substitution was tested offline, not the
hosted template engine or a new model execution. Nothing is deployed by this PR.

## Status readback diagnostics

The same pilot's pending-status write succeeded, but its immediate independent
readback failed. A later observation matched the visible fields. The initial
failed field is unknown: eventual consistency is a hypothesis, not a proved cause.
The runtime change names only the failed fixed validation gates and preserves
all existing actor/revision/record/state/URL checks and the same three requests.
It adds no retry, bypass or extra status write and never dumps API records.

## Activation remains gated

Independent trust-plane review and any required human verdict, green CI and
exact hardware-signed source/config policies must precede deployment/activation.
Existing signatures cannot approve this new source or changed shared-flow hash.
Preserve other DD bindings, AESL/GM, historical signed artifacts and invalid pilot
evidence. Do not rerun the unchanged Nail pilot or delete its durable claim.
After a concrete correction and all gates, use a meaningful fresh candidate and
verify genuine findings/no-findings PR publication plus matching authentic
same-revision check/status. A config change or passing offline test is not that
acceptance. No upstream change or support request is part of this proposal.

Assisted-by: Briar
