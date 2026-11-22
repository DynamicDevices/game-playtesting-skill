# Historical one-shot Preloop reproduction — inactive

The procedure below belongs to the retired Actions integration. Its trigger
workflow is disabled, so this procedure is unavailable and is not an authorised
fallback. Do not dispatch or re-enable it. For native review failures use the
[current delivery guide](../.github/PRELOOP-TROUBLESHOOTING.md): retain the existing
execution and diagnose its failed phase. Recover valid results through supported
native publication, not a second inference run. An unchanged failed review does
not authorise a diagnostic retry; unsupported behaviour goes to Preloop support.

## Retained historical procedure

This manual diagnostic is not a successful PR review or a repair to Preloop.
It can reproduce an invalid result on an unchanged candidate without deleting
the original execution or its durable intent. Normal triggers still reject
duplicate head/base pairs.

The existing trigger workflow accepts an optional `diagnostic_execution_id`.
That input only selects an exact permit already present in the hardware-signed
service policy at `native_ci_contract.diagnostic_rerun`. Without that permit,
the input fails before a model call. Automatic events cannot select it.

The permit must contain exactly these fields:

- `source_execution_id`: the original terminal, repository-owned execution.
- `nonce`: a fresh 48-character lowercase hexadecimal one-shot identifier.
- `expires_at`: an unexpired timezone-aware ISO timestamp.
- `pr_number`, `head_sha`, `base_sha`, `diff_sha256`: the exact candidate.
- `model_id`, `flow_config_sha256`: the existing fixed review configuration.

Trusted code recomputes the complete diff and checks the current PR bindings.
The original must be the only execution of that exact head/base pair, and no
same-PR work may still be running. These checks run again immediately before
launch; the operator cannot use the input to override another field.

The workflow persists `preloop-diagnostic-<nonce>` before triggering. Any earlier
artifact with that name, even an expired one, blocks another attempt. The saved
controller receipt carries the diagnostic permit and a distinct execution ID.
Do not delete artifacts, create dummy commits, or rerun an ambiguous launch.

Diagnostic runs do not post pending statuses. Both the normal publisher and
its error-status fallback reject diagnostic receipts before making PR review,
check or status writes. Authenticated completion and native startup verification
remain required. Retain the result privately and compare it with the original;
even a genuine diagnostic verdict is not a published acceptance gate.

Deployment changes trusted workflow/helper source, so it needs independent
review, actual CI and a new exact-source hardware signature before activation.
It must not run PR-head orchestration. When reproducing an old PR comparison,
account for the fact that installing helpers on the default branch changes the
PR base tip. Any temporary pinned base branch/PR retarget and restoration need
their own explicit signed scope; do not silently test different revisions.

Offline checks:

```sh
python3 -B -m unittest discover -s .github/preloop -p 'test_*.py' -q
```

Assisted-by: Briar.
