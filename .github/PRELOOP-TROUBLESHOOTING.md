# Reading native Preloop delivery evidence

Use the PR's current commit and target branch when investigating a review.
A result for an older commit or target does not describe the current candidate.

## Find the failed phase

1. **Trigger:** A ready, same-repository PR should start the existing shared DD
   flow through the Preloop GitHub App. Check the execution's tracker event,
   repository and exact head/base. There is no bespoke Actions review job to
   start manually. Drafts, forks and unrelated events must not become reviews.
2. **Review:** Follow the execution link from `preloop/review` to the hosted
   result. Check native authenticated clone/checkout, complete diff inspection,
   terminal execution, result validation and all findings. An API response,
   running execution, placeholder or model completion alone is not a passed
   review. Keep substantive findings even if publication later fails.
3. **Publication:** Confirm the actual Preloop App review on the same commit and
   the App-produced `preloop/review` status. Its target links to the execution.
   A passing verdict maps to success; changes requested, errors and incomplete
   reviews must not become green. Verify actual publication, not only the saved
   flow settings or execution state. The controller posts; the model remains
   read-only and must not receive publication credentials.
4. **CI and merge:** While the old `Preloop merge gate` remains required with
   its producer disabled, merges are intentionally frozen, even if native review
   passes. Do not bypass it. Only the separately accepted migration may replace
   it with the App-bound native status. `Preloop contracts` and `Native prompt regressions` remain
   required. Strict up-to-date branch protection and admin enforcement remain
   enabled. Verify the review still describes the current head and target before
   enabling native automatic squash merge under live authority. A changed target
   needs a current candidate and review, not a carried-forward approval. Finally
   verify the PR actually merged; green tests alone do not prove delivery.

The shared DD flow uses a 30-minute runner timeout. A timeout is not permission
to poll continuously or retry an unchanged failed review. Use one startup
validation and native completion/publication evidence. If posting failed after a
valid review, use the supported idempotent publication recovery with exact
preconditions under applicable authority; do not rerun inference just to post.

The old trigger, callback publisher, finalizer and merge workflows are disabled.
Their retained sources are historical, not a fallback. Do not create a separate
publisher, new flow, callback token or replacement green status. Diagnose a native
failure from its actual execution and use Preloop support when needed.

## Useful failure report

Include the PR URL, current head and target SHAs, Preloop execution/publication
URL when available, failed phase and a short sanitized error. Include an Actions
run URL only for a CI failure, not as evidence of a native review. State whether a
complete result and a matching bot post exist. Do not include credentials,
raw private logs or unrelated source. Preserve the original failed run so a
later correction can be compared against it.

This guide describes evidence, not an alternative approval or retry procedure.
The [contribution requirements](../CONTRIBUTING.md) remain applicable.
The [legacy integration reference](preloop/README.md) is historical only;
do not apply its setup or operation instructions.

Assisted-by: Briar.
