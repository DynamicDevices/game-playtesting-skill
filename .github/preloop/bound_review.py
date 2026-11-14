"""Join trusted trigger receipts, signed completion and native review results.

This is a pure validation contract, NOT a publisher. Its caller must verify
the exact signed service policy and trusted Actions source/OIDC provenance of
BOTH intent and receipt before calling; caller-supplied JSON is not proof.
Consume replay/supersession state before transmitting and read back all writes.

The nonce and complete-diff digest belong to trusted orchestration, not the
model. Preloop's signed completion digest binds the fetched result to the owned
execution; the execution ID joins that result to the original durable intent.
Assisted-by: Briar.
"""
import re

from completion_contract import canonical_digest, verify_result_projection
from native_result import reviewer_projection
from review_contract import publication_state, require

CORRELATION_FIELDS = (
    "flow_id", "project_id", "repository_identifier", "pr_number", "head_sha", "base_sha",
)


def bind_owned_execution(completion, intent, receipt, execution):
    """Join authenticated completion to durable intent, even when no result exists."""
    for field in CORRELATION_FIELDS:
        value = intent.get(field)
        require(value is not None and receipt.get(field) == value and
                completion.get(field) == value and execution.get(field) == value,
                "Owned review correlation mismatch: " + field)
    eid = receipt.get("execution_id")
    require(eid is not None and execution.get("id") == eid and
            completion.get("execution_id") == eid, "Execution receipt mismatch")
    require(execution.get("status") == completion.get("status"), "Terminal status mismatch")
    for field, length in (("challenge", 48), ("diff_sha256", 64)):
        value = intent.get(field)
        require(type(value) is str and re.fullmatch("[0-9a-f]{" + str(length) + "}", value),
                "Missing durable trigger " + field)
        require(receipt.get(field) == value, "Trigger receipt changed " + field)
    return eid


def bind_completed_review(completion, intent, receipt, execution, artifact, diff_sha256):
    """All arguments must come from independently verified trusted sources.

    diff_sha256 is recomputed over the full canonical merge-base-to-head diff
    with trusted bare Git, not read from the result or supplied by the PR.
    An incomplete/missing result refuses review publication; orchestration may
    post an authorised service-error status without manufacturing a review.
    """
    eid = bind_owned_execution(completion, intent, receipt, execution)
    require(diff_sha256 == intent["diff_sha256"], "Complete canonical diff changed")
    startup = execution.get("startup_receipt")
    require(type(startup) is dict and startup.get("version") == 1 and
            startup.get("executor") == "hosted" and
            startup.get("lease_revoked") is True and
            startup.get("checkout_verified") is True and
            startup.get("setup_completed") is True and
            startup.get("commit") == intent["head_sha"] and
            type(startup.get("agent_started_at")) is str and startup["agent_started_at"],
            "Missing controller-observed native checkout/startup")
    raw_result = verify_result_projection(completion, artifact)
    result, controller_metadata = reviewer_projection(raw_result)
    expected = {key: intent[key] for key in ("head_sha", "base_sha", "diff_sha256", "challenge")}
    # Add ONLY externally verified bookkeeping, never a model-provided value.
    bound = {**result, "diff_sha256": expected["diff_sha256"], "challenge": expected["challenge"]}
    state, validated = publication_state(execution["status"], bound, expected)
    claim = {**expected, "execution_id": eid, "event_id": completion["event_id"],
             "result_sha256": completion["result_sha256"]}
    return {"state": state, "result": validated, "claim_sha256": canonical_digest(claim),
            "execution_id": eid, "event_id": completion["event_id"],
            "native_completion_status": raw_result["status"],
            "controller_metadata": controller_metadata}
