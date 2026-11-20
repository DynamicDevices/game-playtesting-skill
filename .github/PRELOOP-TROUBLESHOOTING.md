# Reading Preloop delivery evidence

Use the PR's current commit and target branch when investigating a review.
A result for an older commit or target does not describe the current candidate.

## Find the failed phase

1. **Trigger:** Open the `Start Preloop review` Actions run. Its saved intent
   identifies the repository, PR and revisions requested. A failed preparation
   step is not a model-review failure; inspect that step's reported cause.
2. **Review:** Follow the execution link to the hosted Preloop result. Check
   whether execution completed and whether its complete findings were captured.
   A successful API request, running execution or placeholder is not a completed
   review. Keep any substantive findings even if delivery later fails.
3. **Publication:** Look for the actual bot review on the same PR revision and
   the `Preloop review` check. A callback receiving HTTP 204 only confirms that
   endpoint's response; it does not establish that GitHub received the review.
4. **Finalization:** Inspect the publication/finalizer workflows and the
   `Preloop merge gate` check. A completed model result can coexist with a failed
   publication or finalizer. Record which phase failed rather than describing
   every red check as a failed model review.
5. **Merge:** Check the PR's actual merged state. Passing contract or prompt
   tests establishes those tests' results, not hosted review or merge completion.

The workflow sources are [trigger](workflows/preloop-review-trigger.yml),
[publisher](workflows/preloop-review-publish.yml),
[finalizer](workflows/preloop-review-finalize.yml) and
[merge gate](workflows/preloop-review-merge.yml).

## Useful failure report

Include the PR URL, current head and target SHAs, execution URL when available,
Actions run URL, failed phase and a short sanitized error. State whether a
complete result and a matching bot post exist. Do not include credentials,
raw private logs or unrelated source. Preserve the original failed run so a
later correction can be compared against it.

This guide describes evidence, not an alternative approval or retry procedure.
The [contribution requirements](../CONTRIBUTING.md) and
[integration documentation](preloop/README.md) remain applicable.

Assisted-by: Briar.
