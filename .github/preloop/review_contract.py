"""Pure validation only: not a publisher or an authority verifier.

Inputs must be fetched by trusted orchestration, never supplied by the PR.
Authority, callback authentication, ownership, current-PR checks, full streamed
diff hashing and replay consumption remain separate mandatory publication gates.
Assisted-by: Briar.
"""
import html
import re


class InvalidReview(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InvalidReview(message)


RESULT_FIELDS = {
    "success", "verdict", "review", "head_sha", "base_sha", "diff_sha256",
    "challenge", "findings",
}
FINDING_FIELDS = {"severity", "location", "problem", "evidence", "fix"}
SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"}


def validate_result(result, expected):
    """Validate the proposed DD schema against a trusted trigger receipt.

    A model's success flag never overrides blocking findings or service errors.
    expected contains independently established head/base/diff/challenge values.
    Trusted orchestration adds these bindings only after checking the native
    result's digest, complete projection, schema and completion marker.
    """
    require(type(result) is dict and set(result) == RESULT_FIELDS,
            "Unexpected or missing review fields")
    require(type(result["success"]) is bool, "Invalid success flag")
    require(type(result["verdict"]) is str and
            result["verdict"] in {"pass", "changes_requested", "error"},
            "Invalid verdict")
    require(type(result["review"]) is str and result["review"].strip(),
            "Missing readable review")
    for field, length in (("head_sha", 40), ("base_sha", 40),
                          ("diff_sha256", 64), ("challenge", 48)):
        value = result[field]
        require(type(value) is str and
                re.fullmatch("[0-9a-f]{" + str(length) + "}", value),
                "Malformed " + field)
        require(value == expected.get(field), "Mismatched " + field)
    findings = result["findings"]
    require(type(findings) is list, "Findings must be a list")
    for finding in findings:
        require(type(finding) is dict and set(finding) == FINDING_FIELDS,
                "Unexpected or missing finding fields")
        require(type(finding["severity"]) is str and
                finding["severity"] in SEVERITIES, "Invalid severity")
        for field in FINDING_FIELDS - {"severity"}:
            require(type(finding[field]) is str and finding[field].strip(),
                    "Missing finding " + field)
    blocking = any(f["severity"] != "LOW" for f in findings)
    verdict = result["verdict"]
    require(result["success"] == (verdict == "pass"),
            "Verdict and success disagree")
    require(verdict != "pass" or not blocking,
            "Passing verdict contains blocking findings")
    require(verdict != "changes_requested" or blocking,
            "Blocking verdict has no blocking findings")
    return result


def publication_state(execution_status, result, expected):
    """Return status plus ALL valid findings, including failed executions.

    Missing/invalid results are refused. Orchestration may publish an error
    status after its identity/authority gates; it must not fabricate a review.
    """
    require(type(execution_status) is str and execution_status in TERMINAL,
            "Execution is not terminal")
    validated = validate_result(result, expected)
    if execution_status != "SUCCEEDED" or validated["verdict"] == "error":
        state = "error"
    elif validated["verdict"] == "changes_requested":
        state = "failure"
    else:
        state = "success"
    return state, validated


def safe_text(value):
    # Render as text, never model-authored Markdown/HTML. Suppress mentions too.
    escaped = html.escape(value, quote=True).replace("@", "@\u200b")
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~:-])", r"\\\1", escaped)


def review_body(result):
    """Render only a result already checked by validate_result; no truncation."""
    labels = {"CRITICAL": "🔴 Critical", "HIGH": "🔴 High",
              "MEDIUM": "🟠 Medium", "LOW": "🟡 Low"}
    lines = ["## Preloop review", "", "Reviewed commit: `" +
             result["head_sha"] + "`", "", safe_text(result["review"])]
    for finding in result["findings"]:
        lines += ["", "### " + labels[finding["severity"]]]
        for field in ("location", "problem", "evidence", "fix"):
            lines += ["", field.title() + ": " + safe_text(finding[field])]
    if not result["findings"]:
        lines += ["", "No actionable findings reported."]
    return "\n".join(lines) + "\n"
