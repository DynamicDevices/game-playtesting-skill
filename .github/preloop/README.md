# Shared Preloop review publication — integration candidate

This implementation has not been accepted or activated. It needs independent
exact-candidate review, signed service authority and a live PR pilot before use.
It uses the existing shared organisation flow, not a new flow per repository.

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
projection, including any `container_termination` object. It requires empty
`result_withheld_paths` and explicit successful `schema_validation` with no errors.
Only then does it separate the documented controller object and completion marker
from the strict reviewer judgement. Unknown fields, malformed telemetry, missing
schema proof and error responses fail closed. Telemetry and the original digest
are preserved in the publication receipt, not posted as review findings.

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
Queued/failed executions do not count as running. No sleep loop, polling or
automatic re-trigger compensates for startup timing. A live queued observation
remains a failed startup gate requiring phase diagnosis, not successful delivery.

Bootstrap also needs resolution: GitHub dispatch workflows must already be on
the default branch, but independent Preloop review is required before installation.
The selected project grant permits bootstrap installation only after Alex's
actual exact-candidate correctness review plus independent security review by
the identified existing DD Sandchest service. Sandchest excludes correctness;
neither volunteering to review nor signing a grant is a review verdict.
Both reviews, required CI, accepted revocation and final signed publisher policies
must precede installation. No unreviewed self-installation, synthetic trigger commit, extra flow,
manual green status or review waiver is an acceptable workaround.

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
