"""Offline regression tests. No API calls, credentials or device input."""
import copy
import unittest

from review_contract import InvalidReview, publication_state, review_body


class ReviewContractTests(unittest.TestCase):
    def setUp(self):
        self.expected = dict(head_sha="a" * 40, base_sha="b" * 40,
                             diff_sha256="c" * 64, challenge="d" * 48)
        self.result = dict(self.expected, success=True, verdict="pass",
                           review="Complete review.", findings=[])

    def check(self, status="SUCCEEDED", result=None, expected=None):
        return publication_state(status, result or self.result,
                                 expected or self.expected)

    def finding(self, severity):
        return dict(severity=severity, location="file.py:1", problem="Problem",
                    evidence="Observed evidence", fix="Suggested correction")

    def test_clean_pass(self):
        self.assertEqual(self.check()[0], "success")

    def test_all_blocking_severities_remain_visible(self):
        for severity in ("MEDIUM", "HIGH", "CRITICAL"):
            with self.subTest(severity=severity):
                result = dict(self.result, success=False,
                              verdict="changes_requested",
                              findings=[self.finding(severity)])
                state, validated = self.check(result=result)
                self.assertEqual(state, "failure")
                self.assertEqual(validated["findings"], result["findings"])

    def test_low_findings_pass_but_remain_visible(self):
        result = dict(self.result, findings=[self.finding("LOW")])
        self.assertEqual(self.check(result=result)[0], "success")
        self.assertIn("🟡 Low", review_body(result))

    def test_failed_execution_never_discards_findings_or_passes(self):
        for status in ("FAILED", "CANCELLED", "TIMED_OUT"):
            for verdict in ("pass", "changes_requested", "error"):
                with self.subTest(status=status, verdict=verdict):
                    result = dict(self.result, success=verdict == "pass",
                                  verdict=verdict,
                                  findings=[self.finding("LOW" if verdict == "pass"
                                                         else "HIGH")])
                    state, validated = self.check(status=status, result=result)
                    self.assertEqual(state, "error")
                    self.assertEqual(len(validated["findings"]), 1)

    def test_service_succeeded_but_review_error_cannot_pass(self):
        self.assertEqual(self.check(result=dict(self.result, success=False,
                                               verdict="error"))[0], "error")

    def test_reject_each_wrong_binding(self):
        for field in self.expected:
            with self.subTest(field=field):
                result = dict(self.result)
                result[field] = "e" * len(result[field])
                with self.assertRaises(InvalidReview):
                    self.check(result=result)

    def test_old_deployed_schema_refused(self):
        result = dict(self.result)
        del result["diff_sha256"]
        del result["challenge"]
        with self.assertRaises(InvalidReview):
            self.check(result=result)

    def test_nonterminal_refused(self):
        for status in ("RUNNING", "PENDING", "UNKNOWN"):
            with self.assertRaises(InvalidReview):
                self.check(status=status)

    def test_false_green_and_inconsistent_verdicts_refused(self):
        cases = [dict(self.result, findings=[self.finding("HIGH")]),
                 dict(self.result, success=False),
                 dict(self.result, success=False, verdict="changes_requested")]
        for result in cases:
            with self.assertRaises(InvalidReview):
                self.check(result=result)

    def test_malformed_results_refused(self):
        for key, value in (("success", 1), ("verdict", []), ("verdict", None),
                           ("findings", {}), ("review", ""),
                           ("head_sha", "not-a-sha"), ("unexpected", "field")):
            with self.subTest(key=key):
                with self.assertRaises(InvalidReview):
                    self.check(result=dict(self.result, **{key: value}))

    def test_malformed_findings_refused(self):
        for key, value in (("severity", "INFO"), ("problem", ""),
                           ("fix", None), ("extra", "field")):
            result = dict(self.result, findings=[dict(self.finding("LOW"),
                                                     **{key: value})])
            with self.assertRaises(InvalidReview):
                self.check(result=result)

    def test_all_findings_render_without_truncation_and_without_mutation(self):
        result = dict(self.result, findings=[self.finding("LOW") for _ in range(150)])
        before = copy.deepcopy(result)
        self.assertEqual(review_body(result).count("### 🟡 Low"), 150)
        self.assertEqual(result, before)

    def test_unsafe_text_and_mentions(self):
        result = dict(self.result, review='@alex <script> [click](https://bad) `code`')
        body = review_body(result)
        self.assertNotIn("@alex", body)
        self.assertNotIn("<script>", body)
        self.assertNotIn("[click](", body)
        self.assertIn("@\u200balex", body)
        self.assertIn("&lt;script&gt;", body)


if __name__ == "__main__":
    unittest.main()
