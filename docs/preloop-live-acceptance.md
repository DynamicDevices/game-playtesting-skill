# Preloop live acceptance procedure

This document is a controlled review fixture and an operator procedure, not a
claim that the hosted review has passed. The test PR stays unmerged until its
disposition is agreed. No runtime code or trusted workflow changes are required.

## Purpose

Verify the activated review route on a real, non-empty, same-repository PR:
trusted default-branch Actions trigger, hosted read-only native checkout,
substantive review, authenticated completion and exact-commit publication by
the existing trusted Actions publisher. Native platform posting stays off.

The earlier failed execution returned placeholder text and zero commit IDs.
Preloop reports deployed result-binding and repository-inspection checks;
those prevent false success but do not guarantee a complete review. The local
validator also rejects placeholder-only review text. Preserve that failed run.

## Acceptance evidence

- Record the PR, exact head/base, complete diff digest, fixed flow/model and
  actual Actions run identity before interpreting a result.
- Native source checkout must be controller-verified. A RUNNING container with
  a pending receipt is unverified startup, not a passed review. Completion
  requires the full recorded receipt and confirmed lease cleanup.
- The authoritative result must validate against the complete projection,
  signed completion digest and exact revision bindings. A SUCCEEDED execution
  or empty findings array alone is insufficient. Evidence of a repository tool
  call is only an inspection floor, not proof every changed line was reviewed.
- The review must discuss the actual change rather than return placeholder
  text. Preserve all findings, including LOW, and distinguish a valid review
  requesting changes from a failed review service.
- Independently read back the readable PR post, authentic publisher identity,
  reviewed commit and matching Actions-backed status/check. A pending status,
  manual green status or console-only result does not prove publication.

## Failure and cleanup

Keep errors and original results intact. Diagnose the failing phase before a
corrected attempt; recover valid stored results when only publication failed.
Do not retry unchanged failures, manufacture a pass, change providers, widen
credentials, weaken validation or patch Preloop. Use authenticated completion
rather than model polling. Do not merge, delete branches or close the test PR
automatically. Record actual limits and leave the result visible for inspection.

This documentation-only fixture can prove the review/publication route for its
own diff. It cannot establish the correctness of gameplay, device behaviour or
unreviewed code, and it is not a substitute for those separate tests.

Assisted-by: Briar
