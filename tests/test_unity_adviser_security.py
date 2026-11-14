"""Offline adviser file-boundary tests; no SDK, network or credential access."""
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1] / "skills/app-playtesting/scripts/unity_playtest_adviser.py"
SPEC = importlib.util.spec_from_file_location("unity_adviser_security", SOURCE)
ADVISER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADVISER)


class ScreenshotBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "run"
        self.run.mkdir()
        self.png = b"\x89PNG\r\n\x1a\nsynthetic fixture, not a decoded image"
        (self.run / "frame.png").write_bytes(self.png)
        (self.root / "private.png").write_bytes(self.png)

    def test_only_a_run_local_png_is_read(self):
        self.assertEqual(ADVISER.screenshot_bytes(self.run, "frame.png"), self.png)

    def test_absolute_parent_missing_and_wrong_type_paths_are_rejected(self):
        for name in [str(self.root / "private.png"), "../private.png", "missing.png",
                     "frame.txt", "", None, ["frame.png"]]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                ADVISER.screenshot_bytes(self.run, name)

    def test_escaping_symlink_is_rejected(self):
        try:
            (self.run / "escape.png").symlink_to(self.root / "private.png")
        except (OSError, NotImplementedError):
            self.skipTest("Host cannot create a test symlink")
        with self.assertRaises(ValueError):
            ADVISER.screenshot_bytes(self.run, "escape.png")

    def test_other_content_renamed_png_is_rejected(self):
        (self.run / "not-an-image.png").write_text("synthetic non-image", encoding="utf-8")
        with self.assertRaises(ValueError):
            ADVISER.screenshot_bytes(self.run, "not-an-image.png")


class CredentialSelectionTests(unittest.TestCase):
    def test_only_the_explicit_item_is_requested_without_a_shell(self):
        with mock.patch.object(ADVISER.sys, "platform", "darwin"), mock.patch.object(
                ADVISER.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="synthetic credential\n")) as run:
            self.assertEqual(ADVISER.keychain_key("test-service", "test-account"), "synthetic credential")
        self.assertEqual(run.call_args.args[0], ["security", "find-generic-password", "-s", "test-service",
                                                "-a", "test-account", "-w"])
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_explicit_item_cannot_be_redirected_by_the_environment(self):
        constructor = mock.Mock()
        with mock.patch.dict(ADVISER.os.environ, {"ANTHROPIC_BASE_URL": "https://invalid.example"}, clear=True), \
                mock.patch.dict(ADVISER.sys.modules, {"anthropic": SimpleNamespace(Anthropic=constructor)}), \
                mock.patch.object(ADVISER, "keychain_key", return_value="synthetic credential"):
            ADVISER.make_client({"adviser_keychain_service": "test-service", "adviser_keychain_account": "test-account"})
        constructor.assert_called_once_with(api_key="synthetic credential", base_url="https://api.anthropic.com", timeout=90.0)

    def test_missing_explicit_item_does_not_use_another_account(self):
        constructor = mock.Mock()
        with mock.patch.dict(ADVISER.os.environ, {}, clear=True), \
                mock.patch.dict(ADVISER.sys.modules, {"anthropic": SimpleNamespace(Anthropic=constructor)}), \
                mock.patch.object(ADVISER, "keychain_key", return_value=None):
            with self.assertRaisesRegex(ValueError, "no other credential"):
                ADVISER.make_client({"adviser_keychain_service": "missing", "adviser_keychain_account": "test-account"})
        constructor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
