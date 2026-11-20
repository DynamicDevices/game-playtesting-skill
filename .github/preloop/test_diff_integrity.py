"""Offline regression tests for exact base identity and complete source diffs."""
import hashlib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import runtime
import trust
from review_contract import InvalidReview


class DiffIntegrityTests(unittest.TestCase):
    base = 'b' * 40
    head = 'a' * 40

    def canonical(self, merge_base=None, numstat=b'1\t1\tfile.txt\n'):
        merge_base = self.base if merge_base is None else merge_base
        payload = b'complete textual patch\n'
        commands = []
        def run(argv, **kwargs):
            commands.append(argv)
            output = b''
            if 'merge-base' in argv:
                output = (merge_base + '\n').encode()
            elif '--numstat' in argv:
                output = numstat
            elif all(arg in argv for arg in trust.DIFF_ARGS):
                kwargs['stdout'].write(payload)
            return SimpleNamespace(returncode=0, stdout=output)
        with patch.object(runtime.subprocess, 'run', side_effect=run):
            actual = runtime.full_diff_sha256('example/repository', self.base,
                                              self.head, 'synthetic-token')
        return actual, commands, payload

    def test_up_to_date_text_diff_is_hashed_completely(self):
        actual, commands, payload = self.canonical()
        self.assertEqual(actual, hashlib.sha256(payload).hexdigest())
        self.assertTrue(any(argv[-3:] == [self.base, self.head, '--'] and
                            all(arg in argv for arg in trust.DIFF_ARGS)
                            for argv in commands))

    def test_distinct_target_tip_and_merge_base_are_rejected(self):
        with self.assertRaisesRegex(InvalidReview, 'target tip differs from merge base'):
            self.canonical(merge_base='c' * 40)

    def test_binary_change_is_rejected(self):
        with self.assertRaisesRegex(InvalidReview, 'Binary changes are unsupported'):
            self.canonical(numstat=b'-\t-\tfirmware.bin\n')

    def test_mixed_text_and_binary_changes_are_rejected(self):
        with self.assertRaisesRegex(InvalidReview, 'Binary changes are unsupported'):
            self.canonical(numstat=b'2\t1\treadme.txt\n-\t-\tfirmware.bin\n')


if __name__ == '__main__':
    unittest.main()
