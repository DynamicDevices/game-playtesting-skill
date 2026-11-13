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

The current code checks signature, expiry and source bytes before each write.
It does not yet provide an independently live service-revocation check for each
GitHub write. Desktop `allowed_signers` is not automatically propagated to
Actions. Freeze and independently review the exact revocation mechanism before
signing or activating the policy; do not mistake local tests for that proof.

Bootstrap also needs resolution: GitHub dispatch workflows must already be on
the default branch, but independent Preloop review is required before installation.
The current grant permits reviewed bootstrap installation, not installing this
unreviewed publisher to review itself. An already authorised authenticated
completion route, or an exact signed amendment for a minimal inert receiver,
is needed before launching that review. No synthetic trigger commit, extra flow,
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
