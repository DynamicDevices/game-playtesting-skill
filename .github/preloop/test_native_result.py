"""The proposed native schema and exact normalization boundary."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from native_result import JUDGEMENT_FIELDS, NATIVE_RESULT_SCHEMA, reviewer_projection
from review_contract import FINDING_FIELDS, InvalidReview


class NativeResultTests(unittest.TestCase):
    def setUp(self):
        self.result = dict(status='success', success=True, verdict='pass',
                           review='Complete review', head_sha='a' * 40, base_sha='b' * 40, findings=[])

    def test_proposed_schema_requires_marker_and_only_native_judgement(self):
        self.assertEqual(set(NATIVE_RESULT_SCHEMA['required']), JUDGEMENT_FIELDS | {'status'})
        self.assertEqual(set(NATIVE_RESULT_SCHEMA['properties']), set(NATIVE_RESULT_SCHEMA['required']))
        self.assertEqual(NATIVE_RESULT_SCHEMA['properties']['status']['enum'], ['success'])
        self.assertIs(NATIVE_RESULT_SCHEMA['additionalProperties'], False)
        finding = NATIVE_RESULT_SCHEMA['properties']['findings']['items']
        self.assertEqual(set(finding['required']), FINDING_FIELDS)
        self.assertIs(finding['additionalProperties'], False)

    def test_missing_or_invalid_marker_never_projects(self):
        for status in (None, True, 'SUCCEEDED', 'failed', ''):
            result = dict(self.result, status=status)
            with self.subTest(status=status), self.assertRaises(InvalidReview):
                reviewer_projection(result)
        del self.result['status']
        with self.assertRaises(InvalidReview):
            reviewer_projection(self.result)

    def test_only_documented_object_telemetry_is_separated(self):
        for telemetry in (None, [], 'completed', True):
            with self.subTest(telemetry=telemetry), self.assertRaises(InvalidReview):
                reviewer_projection(dict(self.result, container_termination=telemetry))
        for extra in ('containerTermination', 'controller_metadata', 'error', 'challenge'):
            with self.subTest(extra=extra), self.assertRaises(InvalidReview):
                reviewer_projection(dict(self.result, **{extra: 'not allowed'}))

    def test_projection_does_not_mutate_or_truncate_findings(self):
        self.result['findings'] = [dict(severity='LOW', location='source.py:1',
                                        problem='Problem', evidence='Evidence', fix='Fix') for _ in range(50)]
        original = copy.deepcopy(self.result)
        projected, metadata = reviewer_projection(self.result)
        self.assertEqual(projected['findings'], original['findings'])
        self.assertEqual(len(projected['findings']), 50)
        self.assertEqual(metadata, {})
        self.assertEqual(self.result, original)

    def test_operator_schema_export_matches_the_validators_contract(self):
        raw = subprocess.check_output([sys.executable, '-B',
                                       str(Path(__file__).with_name('native_result.py'))])
        self.assertEqual(json.loads(raw), NATIVE_RESULT_SCHEMA)


if __name__ == '__main__':
    unittest.main()
