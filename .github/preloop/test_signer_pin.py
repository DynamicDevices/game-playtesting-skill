"""Pinned-key regressions; synthetic files and mocked verification only."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import trust


class SignerPinTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / '.github'
        self.folder.mkdir()
        self.key = self.folder / 'preloop-publication-key.pub'
        self.key.write_bytes(b'synthetic-key\n')
        workflow = self.folder / 'workflows/preloop-review-publish.yml'
        workflow.parent.mkdir()
        workflow.write_bytes(b'workflow')
        now = datetime.datetime.now(datetime.timezone.utc)
        files = {'.github/preloop-publication-key.pub': hashlib.sha256(self.key.read_bytes()).hexdigest(),
                 '.github/workflows/preloop-review-publish.yml': hashlib.sha256(b'workflow').hexdigest()}
        self.authority = dict(files=files, git_blobs={path: 'blob' for path in files},
            issued_at=(now - datetime.timedelta(hours=1)).isoformat(),
            expires_at=(now + datetime.timedelta(hours=1)).isoformat(),
            non_delegable=True, bindings=[{'repository': 'owner/repo'}])
        self.policy = self.folder / 'preloop-publication-authority.json'
        self.save()
        (self.folder / 'preloop-publication-authority.json.sig').write_bytes(b'signature')

    def save(self):
        self.policy.write_text(json.dumps({'publisher_authority': self.authority}))

    def verify(self):
        def fingerprint(argv, **kwargs):
            self.assertEqual(Path(argv[2]).read_bytes(), b'synthetic-key\n')
            return '256 ' + trust.KEY + ' fixture'

        def signature(argv, **kwargs):
            signers = Path(argv[argv.index('-f') + 1]).read_bytes()
            self.assertEqual(signers, b'ajlennon@dynamicdevices.co.uk synthetic-key\n')
            return subprocess.CompletedProcess(argv, 0)

        with patch.object(trust.subprocess, 'check_output', side_effect=fingerprint), \
             patch.object(trust.subprocess, 'run', side_effect=signature):
            return trust.load_authority(self.folder, 'owner/repo')

    def test_only_verified_line_is_used(self):
        self.assertEqual(self.verify()['repository'], 'owner/repo')

    def test_appended_signer_or_second_public_key_rejected(self):
        for appended in [b'ajlennon@dynamicdevices.co.uk attacker-key', b'attacker-key']:
            with self.subTest(appended=appended):
                self.key.write_bytes(b'synthetic-key\n' + appended + b'\n')
                with patch.object(trust.subprocess, 'check_output') as fingerprint:
                    with self.assertRaisesRegex(ValueError, 'exactly one public key'):
                        trust.load_authority(self.folder, 'owner/repo')
                    fingerprint.assert_not_called()

    def test_empty_key_rejected(self):
        self.key.write_bytes(b'\n \n')
        with self.assertRaisesRegex(ValueError, 'exactly one public key'):
            self.verify()

    def test_missing_key_manifest_rejected(self):
        self.authority['files'].pop('.github/preloop-publication-key.pub')
        self.save()
        with self.assertRaisesRegex(ValueError, 'public key missing'):
            self.verify()


if __name__ == '__main__':
    unittest.main()
