# Automatic Preloop review acceptance test

This documentation-only PR tests the DD automatic review route. Leave it open
and unmerged while collecting the evidence.

1. Record this PR's immutable head, target base and complete diff.
2. Confirm its opened event starts the existing Start Preloop review workflow,
   not a manual workflow dispatch.
3. Confirm the hosted DD reviewer checks out the exact revision and reviews the
   complete diff. A placeholder or failed execution is not a review.
4. Read the full findings posted on this PR and the matching commit status.
5. After the publisher Actions run finishes, run the local acceptance command
   against the recorded trigger, execution and publisher identities. A green
   custom check while the workflow is running is not sufficient.

A delivered review requesting changes proves delivery, not approval to merge.
Keep failures and findings visible; this test does not authorise another review.

Assisted-by: Briar
