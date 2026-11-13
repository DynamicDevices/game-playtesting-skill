"""Native reviewer schema and projection; no network or service mutation.

Run this file to print the proposed result_schema for operator review. Nothing
is installed in Preloop. The server's completion marker is not a clean verdict.
Assisted-by: Briar.
"""
import json

from review_contract import FINDING_FIELDS, RESULT_FIELDS, SEVERITIES, require

JUDGEMENT_FIELDS = RESULT_FIELDS - {"diff_sha256", "challenge"}
_TEXT = {"type": "string", "pattern": r"\S"}
_SHA = {"type": "string", "pattern": "^[0-9a-f]{40}$"}
NATIVE_RESULT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": sorted(JUDGEMENT_FIELDS | {"status"}),
    "properties": {
        "status": {"type": "string", "enum": ["success"],
                   "description": "Review output completed; blocking findings may still be present."},
        "success": {"type": "boolean"},
        "verdict": {"type": "string", "enum": ["pass", "changes_requested", "error"]},
        "review": _TEXT,
        "head_sha": _SHA,
        "base_sha": _SHA,
        "findings": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": sorted(FINDING_FIELDS),
            "properties": {key: ({"type": "string", "enum": sorted(SEVERITIES)}
                                  if key == "severity" else _TEXT) for key in FINDING_FIELDS},
        }},
    },
}


def reviewer_projection(result):
    """Call only AFTER signed digest, completeness and service-schema checks.

    The provider documents container_termination as a controller-added object
    outside the reviewer schema. Preserve it without interpreting its internals;
    neither it nor the status marker can override execution or verdict checks.
    Do not remove any other unknown field or mutate the signed projection.
    """
    require(type(result) is dict, "Native result must be an object")
    metadata = {}
    if "container_termination" in result:
        require(type(result["container_termination"]) is dict,
                "Malformed controller container_termination object")
        metadata["container_termination"] = result["container_termination"]
    require(set(result) - set(metadata) == set(NATIVE_RESULT_SCHEMA["required"]),
            "Unexpected or missing native review result fields")
    require(type(result["status"]) is str and result["status"] == "success",
            "Missing native completion status marker")
    return {key: result[key] for key in JUDGEMENT_FIELDS}, metadata


if __name__ == '__main__':
    print(json.dumps(NATIVE_RESULT_SCHEMA, sort_keys=True, indent=2))
