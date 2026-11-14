"""Validate a local playtest record, not the truth or quality of its findings.

No input, network, telemetry or app-control operations are performed.
Evidence paths must stay inside the supplied private evidence directory.
"""

import argparse
import json
from pathlib import Path, PurePosixPath


class InvalidSession(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InvalidSession(message)


def fields(value, names, context):
    require(isinstance(value, dict), context + " must be an object")
    require(set(value) == set(names), context + " has missing or unexpected fields")


def text(value, context):
    require(isinstance(value, str) and bool(value.strip()), context + " must be nonempty text")


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "Duplicate JSON field: " + key)
        value[key] = item
    return value


def evidence_file(root, value):
    text(value, "evidence path")
    relative = PurePosixPath(value)
    require(not relative.is_absolute() and ".." not in relative.parts
            and ":" not in value and "\\" not in value,
            "Evidence must use local relative paths without traversal")
    target = (root / value).resolve()
    require(target.is_relative_to(root) and target.is_file(),
            "Evidence is missing or escapes its private root")


def validate(record, evidence_root):
    fields(record, ["schema", "record_kind", "app", "question", "starting_state",
                    "reset_method", "status", "steps", "evidence", "limitations"], "session")
    require(record["schema"] == "app-playtest-session/v1", "Unsupported schema")
    require(record["record_kind"] in ["template", "synthetic", "observed"], "Invalid record kind")
    fields(record["app"], ["name", "build", "platform"], "app")
    for key, value in record["app"].items():
        text(value, "app." + key)
    for key in ["question", "starting_state", "reset_method"]:
        text(record[key], key)
    outcomes = ["pass", "fail", "inconclusive", "not_run"]
    require(record["status"] in outcomes, "Invalid status")
    require(isinstance(record["limitations"], list), "limitations must be a list")
    for item in record["limitations"]:
        text(item, "limitation")
    if record["record_kind"] == "template":
        require(record["status"] == "not_run", "Templates cannot claim execution")
    if record["record_kind"] != "observed":
        require(bool(record["limitations"]), "Templates/synthetic records must disclose their limits")
    require(isinstance(record["evidence"], list), "evidence must be a list")
    root = Path(evidence_root).resolve()
    ids = set()
    for item in record["evidence"]:
        fields(item, ["id", "kind", "path"], "evidence")
        text(item["id"], "evidence id")
        require(item["id"] not in ids, "Duplicate evidence id")
        require(item["kind"] in ["screenshot", "video", "log"], "Invalid evidence kind")
        evidence_file(root, item["path"])
        ids.add(item["id"])
    require(isinstance(record["steps"], list) and bool(record["steps"]), "steps must be a nonempty list")
    results = []
    for step in record["steps"]:
        fields(step, ["action", "expected", "actual", "outcome", "evidence"], "step")
        text(step["action"], "step action")
        text(step["expected"], "step expected")
        require(step["outcome"] in outcomes, "Invalid step outcome")
        require(isinstance(step["evidence"], list)
                and all(isinstance(i, str) and i in ids for i in step["evidence"]),
                "Step references unknown evidence")
        if step["outcome"] == "not_run":
            require(step["actual"] == "" and not step["evidence"],
                    "Unexecuted steps cannot claim an actual result or evidence")
        else:
            text(step["actual"], "step actual")
            require(bool(step["evidence"]), "Executed steps need evidence")
        results.append(step["outcome"])
    expected = ("fail" if "fail" in results else
                "not_run" if all(r == "not_run" for r in results) else
                "pass" if all(r == "pass" for r in results) else "inconclusive")
    require(record["status"] == expected, "Session status contradicts step outcomes")
    return {"result": "PASS", "record_kind": record["record_kind"],
            "session_status": record["status"], "steps": len(results),
            "limitation": "Structure and local references only; not execution, correctness or quality proof"}


def load_record(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream, object_pairs_hook=unique_object)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("--evidence-root", type=Path,
                        help="Private evidence directory; defaults to the session's parent")
    args = parser.parse_args()
    try:
        result = validate(load_record(args.session), args.evidence_root or args.session.parent)
    except (InvalidSession, OSError, json.JSONDecodeError) as error:
        parser.exit(1, "Invalid session: " + str(error) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
