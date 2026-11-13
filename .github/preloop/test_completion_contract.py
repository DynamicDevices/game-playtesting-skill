"""Synthetic signed-event regression tests; no provider calls or secrets."""
import copy
import hashlib
import hmac
import json
import unittest

from completion_contract import canonical_digest, verify_dispatch, verify_result_projection
from review_contract import InvalidReview


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.secret = "whsec_synthetic_fixture_not_a_real_secret"
        self.now = 1900000000
        self.binding = dict(repository="example/repository", repository_id=42,
                            flow_id="flow", project_id="project", default_branch="main")
        self.result = {"review": "Complete", "findings": []}
        self.data = dict(execution_id="487d988a-53ad-4f5d-8b84-d77bb733676f",
                         flow_id="flow", project_id="project", repository_identifier="42",
                         repository_slug="example/repository", tracker_type="github",
                         pr_number=7, base_branch="main", head_sha="a" * 40,
                         base_sha="b" * 40, status="SUCCEEDED", result_ready=True,
                         result_sha256=canonical_digest(self.result))
        self.envelope = dict(id="73db8ab4-33db-4359-a135-9f20edc61ff8", version="1",
                             type="flow.execution.finished", data=self.data)

    def event(self, timestamp=None, raw=None):
        timestamp = self.now if timestamp is None else timestamp
        raw = json.dumps(self.envelope, ensure_ascii=False) if raw is None else raw
        signature = hmac.new(self.secret.encode(), str(timestamp).encode() + b"." + raw.encode(),
                             hashlib.sha256).hexdigest()
        return dict(action="preloop-review-completed",
                    repository={"id": 42, "full_name": "example/repository"},
                    client_payload=dict(event=raw, signature=f"t={timestamp},v1={signature}",
                                        event_id=self.envelope["id"], delivery_id="unsigned", attempt=1))

    def check(self, event=None):
        return verify_dispatch(event or self.event(), self.secret, self.binding, self.now, 300)

    def test_valid_wake_and_exact_projection(self):
        completion = self.check()
        artifact = dict(execution_id=self.data["execution_id"], status="SUCCEEDED", result=self.result)
        self.assertEqual(verify_result_projection(completion, artifact), self.result)

    def test_tampered_bytes_fail(self):
        event = self.event()
        event["client_payload"]["event"] += " "
        with self.assertRaises(InvalidReview):
            self.check(event)

    def test_timestamp_window_in_both_directions(self):
        for delta in (-301, 301):
            with self.assertRaises(InvalidReview):
                self.check(self.event(self.now + delta))

    def test_wrong_signed_bindings_fail(self):
        for field in ("flow_id", "project_id", "repository_identifier", "repository_slug",
                      "tracker_type", "base_branch", "head_sha", "base_sha", "execution_id"):
            with self.subTest(field=field):
                saved = self.data[field]
                self.data[field] = "wrong"
                with self.assertRaises(InvalidReview):
                    self.check()
                self.data[field] = saved

    def test_wrong_outer_repository_and_event_id_fail(self):
        event = self.event()
        event["repository"]["id"] = 99
        with self.assertRaises(InvalidReview):
            self.check(event)
        event = self.event()
        event["client_payload"]["event_id"] = "wrong"
        with self.assertRaises(InvalidReview):
            self.check(event)

    def test_wrong_version_event_and_truncation_fail(self):
        for field, value in (("version", 1), ("type", "webhook.test"),
                             ("data", {"truncated": True})):
            with self.subTest(field=field):
                saved = self.envelope[field]
                self.envelope[field] = value
                with self.assertRaises(InvalidReview):
                    self.check()
                self.envelope[field] = saved

    def test_duplicate_and_nonfinite_json_fail_even_with_valid_hmac(self):
        for raw in ('{"id":"first","id":"second"}', '{"number":NaN}'):
            with self.assertRaises(InvalidReview):
                self.check(self.event(raw=raw))

    def test_missing_result_cannot_be_accepted(self):
        self.data.update(result_ready=False, result_sha256=None)
        completion = self.check()
        with self.assertRaises(InvalidReview):
            verify_result_projection(completion, {})

    def test_failed_completion_with_result_is_preserved(self):
        self.data["status"] = "FAILED"
        completion = self.check()
        artifact = dict(execution_id=self.data["execution_id"], status="FAILED", result=self.result)
        self.assertEqual(verify_result_projection(completion, artifact), self.result)

    def test_changed_result_status_or_execution_rejected(self):
        completion = self.check()
        artifact = dict(execution_id=self.data["execution_id"], status="SUCCEEDED", result=self.result)
        for field, value in (("execution_id", "other"), ("status", "FAILED"), ("result", {})):
            bad = copy.deepcopy(artifact)
            bad[field] = value
            with self.assertRaises(InvalidReview):
                verify_result_projection(completion, bad)

    def test_transport_attempt_does_not_grant_identity(self):
        event = self.event()
        event["client_payload"].update(attempt=900, delivery_id="different")
        self.assertEqual(self.check(event)["execution_id"], self.data["execution_id"])


if __name__ == "__main__":
    unittest.main()
