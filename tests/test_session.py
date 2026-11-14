"""Offline synthetic fixtures only; these tests never interact with an app."""

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("session_validator", ROOT / "scripts/validate_session.py")
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.record = VALIDATOR.load_record(ROOT / "skills/app-playtesting/assets/session.json")

    def observed(self):
        record = copy.deepcopy(self.record)
        record.update(record_kind="synthetic", status="pass")
        record["limitations"] = ["Synthetic fixture: no app was exercised"]
        (self.root / "trace.txt").write_text("Synthetic expected/actual trace", encoding="utf-8")
        record["evidence"] = [{"id": "trace", "kind": "log", "path": "trace.txt"}]
        record["steps"][0].update(actual="Synthetic visible response", outcome="pass", evidence=["trace"])
        return record

    def test_template_is_explicitly_not_run(self):
        result = VALIDATOR.validate(self.record, self.root)
        self.assertEqual(result["session_status"], "not_run")

    def test_synthetic_success_is_not_observed(self):
        result = VALIDATOR.validate(self.observed(), self.root)
        self.assertEqual(result["record_kind"], "synthetic")

    def test_pass_cannot_hide_failed_or_unexecuted_step(self):
        for outcome in ["fail", "not_run"]:
            with self.subTest(outcome=outcome):
                record = self.observed()
                record["steps"].append({"action": "Second input", "expected": "Response",
                                        "actual": "" if outcome == "not_run" else "Failed",
                                        "outcome": outcome,
                                        "evidence": [] if outcome == "not_run" else ["trace"]})
                with self.assertRaises(VALIDATOR.InvalidSession):
                    VALIDATOR.validate(record, self.root)

    def test_executed_step_needs_actual_and_evidence(self):
        for field, value in [("actual", ""), ("evidence", [])]:
            record = self.observed()
            record["steps"][0][field] = value
            with self.assertRaises(VALIDATOR.InvalidSession):
                VALIDATOR.validate(record, self.root)

    def test_unknown_missing_or_duplicate_evidence(self):
        for problem in ["unknown", "missing", "duplicate"]:
            record = self.observed()
            if problem == "unknown":
                record["steps"][0]["evidence"] = ["absent"]
            elif problem == "missing":
                record["evidence"][0]["path"] = "absent.txt"
            else:
                record["evidence"].append(copy.deepcopy(record["evidence"][0]))
            with self.assertRaises(VALIDATOR.InvalidSession):
                VALIDATOR.validate(record, self.root)

    def test_path_escape_and_external_urls_are_rejected(self):
        for path in ["../escape.txt", "/tmp/private.txt", "https://example.com/evidence",
                     "C:\\private.txt", "file:private.txt"]:
            with self.subTest(path=path):
                record = self.observed()
                record["evidence"][0]["path"] = path
                with self.assertRaises(VALIDATOR.InvalidSession):
                    VALIDATOR.validate(record, self.root)

    def test_symlink_outside_evidence_root_is_rejected(self):
        record = self.observed()
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "private.txt"
            target.write_text("Synthetic", encoding="utf-8")
            try:
                (self.root / "escape.txt").symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("Host does not support unprivileged symlink creation")
            record["evidence"][0]["path"] = "escape.txt"
            with self.assertRaises(VALIDATOR.InvalidSession):
                VALIDATOR.validate(record, self.root)

    def test_template_cannot_claim_execution(self):
        record = self.observed()
        record["record_kind"] = "template"
        with self.assertRaises(VALIDATOR.InvalidSession):
            VALIDATOR.validate(record, self.root)

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaises(VALIDATOR.InvalidSession):
            json.loads('{"status":"pass","status":"fail"}', object_pairs_hook=VALIDATOR.unique_object)

    def test_unknown_schema_or_fields_are_rejected(self):
        for problem in ["schema", "field"]:
            record = copy.deepcopy(self.record)
            record["schema" if problem == "schema" else "unexpected"] = "unknown"
            with self.assertRaises(VALIDATOR.InvalidSession):
                VALIDATOR.validate(record, self.root)


if __name__ == "__main__":
    unittest.main()
