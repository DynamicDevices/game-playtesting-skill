# Native review context regression

The original Nail pilot completed but returned all-zero head/base IDs. Its
publisher correctly rejected that result. The native event had repository/PR/
head/base-branch fields, but the resolved prompt did not include them.

The merged repair documents an exact prefix in
[preloop-review-context-prefix.txt](preloop-review-context-prefix.txt). These
offline tests keep its four supported inputs and fail-on-missing-context/source
requirements from disappearing. They check documentation, not the hosted template
engine, source access, model behaviour or publisher delivery.

Run `python3 -B tests/test_preloop_context_prompt.py`; the read-only, secret-free
workflow runs the same three tests on pushes and PRs. No repository code runs
with review/publication credentials. The signed24-file publisher source manifest
is unchanged by this test/workflow/documentation addition.

Actual acceptance still requires the supported DD prompt update under its exact
signed configuration binding, one meaningful fresh PR review, native checkout
and revision/diff proof, readable authorised PR publication and independent
same-revision status/check readback. An echo of supplied commit IDs is not proof
that source was read. Do not reuse the failed Nail result or consumed intent.

Assisted-by: Briar
