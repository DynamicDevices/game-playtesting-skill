"""Verify Preloop's signed repository_dispatch wake, not review acceptance.

No I/O or publication. A valid wake must still be matched to an owned trusted
trigger receipt, fetched authoritative result, current PR and signed policy.
Replay consumption belongs to the eventual durable publisher, not this module.
Assisted-by: Briar.
"""
import hashlib
import hmac
import json
import re
import uuid

from review_contract import InvalidReview, TERMINAL, require


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result

    def nonfinite(_value):
        raise InvalidReview("Non-finite JSON value")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
    except (ValueError, TypeError, RecursionError) as error:
        raise InvalidReview("Malformed completion JSON") from error


def canonical_digest(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError) as error:
        raise InvalidReview("Malformed result projection") from error
    return hashlib.sha256(raw).hexdigest()


def verify_dispatch(event, secret, binding, now, tolerance_seconds):
    """Use the service-recommended 300s tolerance, frozen by service policy.

    Exact signed event bytes are verified BEFORE parsing; never reserialize them.
    tolerance_seconds must come from trusted configuration, never event input.
    Delivery ID and attempt are unsigned transport metadata, not identity proof.
    """
    require(type(event) is dict and event.get("action") == "preloop-review-completed",
            "Wrong dispatch event")
    repo = event.get("repository", {})
    require(repo.get("id") == binding["repository_id"] and
            repo.get("full_name") == binding["repository"], "Wrong receiving repository")
    require(type(tolerance_seconds) is int and tolerance_seconds > 0,
            "Missing trusted signature tolerance")
    require(type(secret) is str and secret.startswith("whsec_"), "Missing signing secret")
    payload = event.get("client_payload")
    require(type(payload) is dict, "Missing dispatch payload")
    raw, header = payload.get("event"), payload.get("signature")
    require(type(raw) is str and type(header) is str, "Malformed signed payload")
    match = re.fullmatch(r"t=([0-9]+),v1=([0-9a-f]{64})", header)
    require(match is not None, "Malformed signature")
    timestamp = int(match[1])
    require(abs(now - timestamp) <= tolerance_seconds, "Expired or future signature")
    expected = hmac.new(secret.encode(), str(timestamp).encode() + b"." + raw.encode(),
                        hashlib.sha256).hexdigest()
    require(hmac.compare_digest(expected, match[2]), "Invalid signature")
    envelope = strict_json(raw)
    require(type(envelope) is dict and envelope.get("version") == "1" and
            envelope.get("type") == "flow.execution.finished", "Wrong signed event type")
    require(envelope.get("id") == payload.get("event_id"), "Event ID mismatch")
    data = envelope.get("data")
    require(type(data) is dict and data.get("truncated") is not True,
            "Missing complete event data")
    for key, value in (("flow_id", binding["flow_id"]),
                       ("project_id", binding["project_id"]),
                       ("repository_identifier", str(binding["repository_id"])),
                       ("repository_slug", binding["repository"]),
                       ("tracker_type", "github"),
                       ("base_branch", binding["default_branch"])):
        require(data.get(key) == value, "Completion binding mismatch: " + key)
    try:
        require(str(uuid.UUID(data["execution_id"])) == data["execution_id"],
                "Malformed execution ID")
        require(str(uuid.UUID(envelope["id"])) == envelope["id"], "Malformed event ID")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise InvalidReview("Malformed completion identity") from error
    require(type(data.get("pr_number")) is int and data["pr_number"] > 0,
            "Malformed PR number")
    for key in ("head_sha", "base_sha"):
        require(type(data.get(key)) is str and re.fullmatch("[0-9a-f]{40}", data[key]),
                "Missing bound revision")
    require(type(data.get("status")) is str and data["status"] in TERMINAL,
            "Completion is not terminal")
    require(type(data.get("result_ready")) is bool, "Missing result readiness")
    digest = data.get("result_sha256")
    require((data["result_ready"] and type(digest) is str and
             re.fullmatch("[0-9a-f]{64}", digest)) or
            (not data["result_ready"] and digest is None), "Invalid result digest")
    return {"event_id": envelope["id"], **data}


def verify_result_projection(completion, artifact):
    """Digest is of artifact.result, not the HTTP response wrapper or raw JSON."""
    require(type(artifact) is dict and completion["result_ready"] and
            artifact.get("execution_id") == completion["execution_id"] and
            artifact.get("status") == completion["status"], "Artifact identity mismatch")
    require("result" in artifact and
            canonical_digest(artifact["result"]) == completion["result_sha256"],
            "Artifact differs from signed completion")
    return artifact["result"]
