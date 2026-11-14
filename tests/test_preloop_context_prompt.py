"""Offline regression for documented native target inputs, not a live flow test.

This catches the missing-target prompt that let the failed pilot report zero
commit IDs. Native source inspection and authentic publication need a real run.
Assisted-by: Briar.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREFIX = ROOT / 'docs/preloop-review-context-prefix.txt'
EXPECTED = {
    'trigger_event.payload.repository.full_name',
    'trigger_event.payload.pull_request.number',
    'trigger_event.payload.pull_request.head.sha',
    'trigger_event.payload.pull_request.base.ref',
}


class NativeTargetPromptTests(unittest.TestCase):
    def test_supported_target_fields_are_complete_and_not_base_sha(self):
        fields = re.findall(r'\{\{\s*([^{}]+?)\s*\}\}', PREFIX.read_text())
        self.assertEqual(set(fields), EXPECTED)
        self.assertEqual(len(fields), 4)

    def test_target_values_are_not_claimed_as_source_inspection(self):
        text = PREFIX.read_text()
        for boundary in ['not evidence that source was', 'verify its actual origin',
                         'HEAD against that target', 'complete merge-base-to-head diff',
                         'not from the target branch tip', 'never placeholder or all-zero IDs',
                         'native checkout and its controller receipts remain mandatory']:
            with self.subTest(boundary=boundary):
                self.assertIn(boundary, text)

    def test_missing_context_and_source_access_must_not_be_a_pass(self):
        text = PREFIX.read_text()
        for boundary in ['missing or unresolved', 'native checkout is inaccessible',
                         'actual HEAD differs', 'full diff cannot',
                         'success false and verdict error', 'do not invent source observations']:
            with self.subTest(boundary=boundary):
                self.assertIn(boundary, text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
