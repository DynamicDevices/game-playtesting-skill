"""Synthetic contract composition, not live runner/publisher acceptance."""
import copy
import unittest

from bound_review import bind_completed_review
from completion_contract import canonical_digest
from review_contract import InvalidReview


class BoundReviewTests(unittest.TestCase):
    def setUp(self):
        self.intent = dict(flow_id="flow", project_id="project", repository_identifier="42",
                           pr_number=7, head_sha="a" * 40, base_sha="b" * 40,
                           diff_sha256="c" * 64, challenge="d" * 48)
        self.eid = "487d988a-53ad-4f5d-8b84-d77bb733676f"
        self.receipt = dict(self.intent, execution_id=self.eid)
        self.result = dict(status="success", success=True, verdict="pass", review="Complete review",
                           head_sha="a" * 40, base_sha="b" * 40, findings=[])
        self.execution = dict(self.intent, id=self.eid, status="SUCCEEDED", startup_receipt={
            "version": 1, "executor": "hosted", "checkout_verified": True,
            "setup_completed": True, "commit": "a" * 40,
            "agent_started_at": "2026-11-13T15:00:00Z"})
        self.completion = dict(self.intent, execution_id=self.eid, status="SUCCEEDED",
                               event_id="73db8ab4-33db-4359-a135-9f20edc61ff8",
                               result_ready=True, result_sha256=canonical_digest(self.result))
        self.artifact = dict(execution_id=self.eid, status="SUCCEEDED", result=self.result,
                             result_withheld_paths=[],
                             schema_validation=dict(valid=True, error_count=0, errors=[]))

    def check(self, diff=None):
        return bind_completed_review(self.completion, self.intent, self.receipt,
                                     self.execution, self.artifact, diff or "c" * 64)

    def test_current_native_schema_can_be_bound_outside_model(self):
        proof = self.check()
        self.assertEqual(proof["state"], "success")
        self.assertEqual(proof["result"]["challenge"], self.intent["challenge"])
        self.assertEqual(len(proof["claim_sha256"]), 64)
        self.assertNotIn("challenge", self.result)

    def test_model_cannot_supply_bookkeeping(self):
        self.result["challenge"] = "f" * 48
        self.completion["result_sha256"] = canonical_digest(self.result)
        with self.assertRaises(InvalidReview):
            self.check()

    def test_receipt_nonce_and_digest_must_match_durable_intent(self):
        for field in ("challenge", "diff_sha256"):
            saved = self.receipt[field]
            self.receipt[field] = "e" * len(saved)
            with self.assertRaises(InvalidReview):
                self.check()
            self.receipt[field] = saved

    def test_complete_diff_must_be_independently_recomputed(self):
        with self.assertRaises(InvalidReview):
            self.check(diff="e" * 64)

    def test_every_external_correlation_must_agree(self):
        for record in (self.receipt, self.execution, self.completion):
            for field in ("head_sha", "base_sha", "pr_number", "flow_id", "project_id",
                          "repository_identifier"):
                saved = record[field]
                record[field] = "wrong"
                with self.assertRaises(InvalidReview):
                    self.check()
                record[field] = saved

    def test_missing_controller_startup_never_passes(self):
        for startup in (None, {}, dict(self.execution["startup_receipt"], setup_completed=False)):
            self.execution["startup_receipt"] = startup
            with self.assertRaises(InvalidReview):
                self.check()

    def test_revoked_native_lease_never_passes(self):
        self.execution['startup_receipt']['lease_revoked'] = '2026-11-13T15:01:00Z'
        with self.assertRaises(InvalidReview):
            self.check()

    def test_failed_execution_preserves_blocking_findings_without_green(self):
        self.result.update(success=False, verdict="changes_requested", findings=[dict(
            severity="HIGH", location="file.py:1", problem="Problem", evidence="Evidence", fix="Fix")])
        self.completion.update(status="FAILED", result_sha256=canonical_digest(self.result))
        self.execution["status"] = self.artifact["status"] = "FAILED"
        proof = self.check()
        self.assertEqual(proof["state"], "error")
        self.assertEqual(len(proof["result"]["findings"]), 1)

    def test_execution_substitution_or_result_tampering_refused(self):
        self.receipt["execution_id"] = "other"
        with self.assertRaises(InvalidReview):
            self.check()
        self.receipt["execution_id"] = self.eid
        self.artifact["result"] = copy.deepcopy(self.result)
        self.artifact["result"]["review"] = "Changed"
        with self.assertRaises(InvalidReview):
            self.check()

    def test_documented_telemetry_is_preserved_without_mutating_signed_result(self):
        self.result['container_termination'] = {'reason': 'completed', 'exit_code': 0}
        self.completion['result_sha256'] = canonical_digest(self.result)
        original = copy.deepcopy(self.result)
        proof = self.check()
        self.assertEqual(proof['controller_metadata'],
                         {'container_termination': self.result['container_termination']})
        self.assertEqual(proof['native_completion_status'], 'success')
        self.assertNotIn('container_termination', proof['result'])
        self.assertNotIn('status', proof['result'])
        self.assertEqual(self.result, original)

    def test_native_marker_is_not_an_execution_success_override(self):
        self.execution['status'] = self.artifact['status'] = self.completion['status'] = 'FAILED'
        self.assertEqual(self.check()['state'], 'error')

    def test_unknown_native_fields_are_not_silently_dropped(self):
        self.result['controller_debug'] = {'safe': True}
        self.completion['result_sha256'] = canonical_digest(self.result)
        with self.assertRaises(InvalidReview):
            self.check()


if __name__ == "__main__":
    unittest.main()
