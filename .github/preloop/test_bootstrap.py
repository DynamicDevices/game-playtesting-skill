"""Synthetic isolated-loader regressions; no credentials or hosted calls."""
import copy
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import bootstrap


class BootstrapTests(unittest.TestCase):
    def fixture(self, folder):
        root = Path(folder)
        source = root / '.github/preloop/bootstrap.py'
        source.parent.mkdir(parents=True)
        source.write_bytes(b'# verified fixture\n')
        raw = source.read_bytes()
        rel = '.github/preloop/bootstrap.py'
        authority = dict(non_delegable=True,
            issued_at=(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)).isoformat(),
            expires_at=(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat(),
            files={rel: hashlib.sha256(raw).hexdigest()},
            git_blobs={rel: hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()})
        (root / '.github/preloop-publication-authority.json').write_text(
            json.dumps({'publisher_authority': authority}))
        (root / '.github/preloop-publication-authority.json.sig').write_text('synthetic-signature')
        (root / '.github/preloop-publication-key.pub').write_text('synthetic-public-key')
        key = (root / '.github/preloop-publication-key.pub').read_bytes()
        authority['files']['.github/preloop-publication-key.pub'] = hashlib.sha256(key).hexdigest()
        authority['git_blobs']['.github/preloop-publication-key.pub'] = hashlib.sha1(
            b'blob ' + str(len(key)).encode() + b'\0' + key).hexdigest()
        (root / '.github/preloop-publication-authority.json').write_text(
            json.dumps({'publisher_authority': authority}))
        return root, authority

    def verified(self, root, signature=0):
        with patch.object(bootstrap.subprocess, 'check_output', return_value='256 ' + bootstrap.KEY + ' fixture'), \
             patch.object(bootstrap.subprocess, 'run', return_value=subprocess.CompletedProcess([], signature)):
            return bootstrap.verified_sources(root)

    def test_only_manifest_files_are_staged_not_checkout_shadow_modules(self):
        with tempfile.TemporaryDirectory() as folder:
            root, _ = self.fixture(folder)
            (root / '.github/preloop/json.py').write_text("raise RuntimeError('shadow')")
            (root / '.github/preloop/unsigned.pyc').write_bytes(b'not approved')
            files = self.verified(root)
            self.assertIn('.github/preloop/bootstrap.py', files)
            self.assertNotIn('.github/preloop/json.py', files)
            self.assertNotIn('.github/preloop/unsigned.pyc', files)

    def test_invalid_signature_or_changed_source_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root, _ = self.fixture(folder)
            with self.assertRaisesRegex(ValueError, 'signature'): self.verified(root, signature=1)
            (root / '.github/preloop/bootstrap.py').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'Unapproved source'): self.verified(root)

    def test_appended_key_rejected_before_signature_verification(self):
        with tempfile.TemporaryDirectory() as folder:
            root, _ = self.fixture(folder)
            (root / '.github/preloop-publication-key.pub').write_text(
                'synthetic-public-key\najlennon@dynamicdevices.co.uk attacker-key\n')
            with self.assertRaisesRegex(ValueError, 'exactly one public key'):
                self.verified(root)

    def test_public_key_must_be_in_signed_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root, authority = self.fixture(folder)
            for name in ['files', 'git_blobs']:
                authority[name].pop('.github/preloop-publication-key.pub')
            (root / '.github/preloop-publication-authority.json').write_text(
                json.dumps({'publisher_authority': authority}))
            with self.assertRaisesRegex(ValueError, 'Incomplete source manifest'):
                self.verified(root)

    def test_missing_manifest_paths_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root, _ = self.fixture(folder)
            source = root / '.github/preloop/bootstrap.py'
            source.unlink()
            with self.assertRaises(ValueError): self.verified(root)
            source.symlink_to(Path(__file__).resolve())
            with self.assertRaises(ValueError): self.verified(root)

    def test_incomplete_manifest_or_expired_policy_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root, authority = self.fixture(folder)
            for updates in ({'git_blobs': {}}, {'expires_at': '2000-01-01T00:00:00+00:00'},
                            {'files': {}, 'git_blobs': {}}):
                policy = copy.deepcopy(authority)
                policy.update(updates)
                (root / '.github/preloop-publication-authority.json').write_text(
                    json.dumps({'publisher_authority': policy}))
                with self.subTest(updates=updates), self.assertRaises(ValueError): self.verified(root)

    def test_isolated_python_cannot_import_unsigned_checkout_json(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            entry = root / 'bootstrap.py'
            entry.write_bytes(Path(bootstrap.__file__).read_bytes())
            (root / 'json.py').write_text("raise RuntimeError('UNSIGNED_SHADOW_EXECUTED')")
            result = subprocess.run([sys.executable, '-I', '-B', str(entry), 'publisher', 'publish'],
                                    cwd=root, capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)  # No policy exists.
            self.assertNotIn('UNSIGNED_SHADOW_EXECUTED', result.stderr)


if __name__ == '__main__':
    unittest.main()
