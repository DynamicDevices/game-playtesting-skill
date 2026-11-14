"""Offline checks of the Unity in-editor scripts against a stand-in editor and synthetic play logs.

These do not start Unity, a game or a device. They show the scripts' own handling of checkpoints, workspace
tidy-up, verdicts and session records; they are not evidence that any game or Unity version works.
"""

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/app-playtesting/scripts"
POSIX_WITH_GIT = os.name == "posix" and shutil.which("git") is not None


def python(*arguments, cwd=None, env=None):
    return subprocess.run([sys.executable, "-B", *map(str, arguments)], cwd=cwd, env=env, capture_output=True, text=True)


@unittest.skipUnless(POSIX_WITH_GIT, "needs a POSIX shell and git")
class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name).resolve()
        self.project, self.saves = base / "project", base / "saves"
        (self.project / "ProjectSettings").mkdir(parents=True)
        (self.project / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 6000.0.0f1\n", encoding="utf-8")
        (self.project / "Assets").mkdir()
        (self.project / "Assets" / "Thing.mat").write_text("as checked in\n", encoding="utf-8")
        (self.project / "Assets" / "Bot.cs").write_text("// as checked in\n", encoding="utf-8")
        (self.project / "known-issues.txt").write_text("# errors that don't fail a report\nold error\n", encoding="utf-8")
        (self.project / "unity-playtest.json").write_text(json.dumps({
            "app": "Synthetic Game", "save_folder": str(self.saves), "start_scenes": ["Loader"],
            "known_issues": "known-issues.txt", "max_minutes": 40,
            "session_validator": str(ROOT / "scripts" / "validate_session.py"), "adviser_remember": True}), encoding="utf-8")
        (self.project / ".gitignore").write_text("Logs/\n", encoding="utf-8")
        identity = ["-c", "user.name=Offline Test", "-c", "user.email=offline@example.invalid", "-c", "commit.gpgsign=false"]
        for command in (["init", "-q"], ["add", "-A"], [*identity, "commit", "-q", "-m", "synthetic project"]):
            subprocess.run(["git", *command], cwd=self.project, check=True, capture_output=True)
        self.editor = base / "editor"
        self.editor.write_text('#!/bin/sh\nexec "%s" -B "%s" "$@"\n' % (sys.executable, ROOT / "tests" / "fake_unity_editor.py"), encoding="utf-8")
        self.editor.chmod(self.editor.stat().st_mode | stat.S_IXUSR)

    def tearDown(self):
        self.temporary.cleanup()

    def run_bot(self, label, *options, mode="ok"):
        env = dict(os.environ, FAKE_EDITOR_MODE=mode, FAKE_EDITOR_SAVES=str(self.saves))
        env.pop("UNITY_PLAYTEST_SETTINGS", None)
        return python(SCRIPTS / "unity_playtest.py", label, "--editor-path", self.editor, *options, cwd=self.project, env=env)

    def run_folder(self, label):
        return self.project / "Logs" / "Playtest" / ("playthrough-" + label)

    def test_clean_run_is_tidied_recorded_and_kept(self):
        self.saves.mkdir()
        (self.saves / "slot.txt").write_text("the developer's own save\n", encoding="utf-8")
        done = self.run_bot("first", "--fresh", "--until", "TutorialComplete = True", "--save-checkpoint", "after-tutorial")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("Result: OK", done.stdout)
        self.assertIn("session record is valid", done.stdout)
        # the editor's rewrite is undone; a person's edit and the checked-in state are respected
        self.assertEqual((self.project / "Assets" / "Thing.mat").read_text(encoding="utf-8"), "as checked in\n")
        self.assertIn("edited by a person", (self.project / "Assets" / "Bot.cs").read_text(encoding="utf-8"))
        self.assertIn("left alone", done.stdout)
        self.assertFalse((self.project / "Assets" / "InitTestScene123.unity").exists())
        self.assertFalse((self.saves / "TestResults.xml").exists())
        # nothing was deleted: the save that was replaced is kept, and the new one is a named checkpoint
        checkpoints = Path(str(self.saves) + ".checkpoints")
        aside = [p for p in checkpoints.iterdir() if p.name.startswith("aside-")]
        self.assertEqual(len(aside), 1)
        self.assertEqual((aside[0] / "save" / "slot.txt").read_text(encoding="utf-8"), "the developer's own save\n")
        self.assertIn("TutorialComplete", (checkpoints / "after-tutorial" / "info.txt").read_text(encoding="utf-8"))
        self.assertTrue((checkpoints / "after-tutorial" / "bot-memory.txt").is_file())
        # the session record is one this repository's validator accepts
        record = self.run_folder("first") / "session.json"
        checked = python(ROOT / "scripts" / "validate_session.py", record)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(json.loads(checked.stdout)["session_status"], "pass")
        self.assertEqual(json.loads(record.read_text(encoding="utf-8"))["app"]["name"], "Synthetic Game")

    def test_starts_from_a_checkpoint(self):
        self.assertEqual(self.run_bot("first", "--fresh", "--save-checkpoint", "one").returncode, 0)
        self.assertEqual(self.run_bot("second").returncode, 0)
        done = self.run_bot("third", "--from-checkpoint", "one")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        log = (self.run_folder("third") / "playthrough.txt").read_text(encoding="utf-8")
        self.assertIn("StartedFrom = after first", log)

    def test_a_held_run_fails_and_keeps_no_checkpoint(self):
        done = self.run_bot("stuck", "--fresh", "--until", "TutorialComplete = True", "--save-checkpoint", "bad", mode="held")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("NEEDS ATTENTION", done.stdout)
        self.assertIn("held by the Shop menu", done.stdout)
        self.assertIn("expected but not found", done.stdout)
        self.assertFalse((Path(str(self.saves) + ".checkpoints") / "bad").exists())
        record = json.loads((self.run_folder("stuck") / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "fail")

    def test_the_settings_line_does_not_answer_the_question(self):
        done = self.run_bot("echo", "--fresh", "--until", "until:")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("expected but not found: until:", done.stdout)

    def test_refuses_bad_requests_before_touching_anything(self):
        for options in (["--fresh", "--from-checkpoint", "x"], ["--from-checkpoint", "missing"], ["--minutes", "41"],
                        ["--until", "a||b"]):
            done = self.run_bot("bad", *options)
            self.assertNotEqual(done.returncode, 0, options)
            self.assertFalse(self.saves.exists(), options)
        self.assertNotEqual(self.run_bot("no spaces allowed").returncode, 0)

    def test_the_bot_can_ask_an_adviser(self):
        # a stand-in answers (PLAYTEST_ADVISER_FAKE); no model is called and nothing leaves the computer
        os.environ["PLAYTEST_ADVISER_FAKE"] = "press:Plant"
        try:
            done = self.run_bot("asks", "--fresh", "--adviser")
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            folder = self.run_folder("asks")
            self.assertIn("TOLD   press:Plant", (folder / "playthrough.txt").read_text(encoding="utf-8"))
            self.assertIn("press Plant", (folder / "adviser.log").read_text(encoding="utf-8"))
            # the answer is remembered, and a later run in the same situation is answered from memory
            self.assertEqual(self.run_bot("again", "--adviser").returncode, 0)
            self.assertIn("[memory]", (self.run_folder("again") / "adviser.log").read_text(encoding="utf-8"))
        finally:
            del os.environ["PLAYTEST_ADVISER_FAKE"]
        # without --adviser the bot is not told to ask
        self.assertEqual(self.run_bot("quiet").returncode, 0)
        self.assertFalse((self.run_folder("quiet") / "ask-0001.json").exists())

    def test_coverage_adds_runs_up(self):
        self.assertEqual(self.run_bot("first", "--fresh").returncode, 0)
        (self.project / "sequences.txt").write_text("Village | Village | OpenDoor\nVillage | Village | CloseDoor\n", encoding="utf-8")
        settings = json.loads((self.project / "unity-playtest.json").read_text(encoding="utf-8"))
        settings["catalogue"] = "sequences.txt"
        (self.project / "unity-playtest.json").write_text(json.dumps(settings), encoding="utf-8")
        done = python(SCRIPTS / "unity_playtest_coverage.py", cwd=self.project)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("Scripted sequences started: 1 of 2", done.stdout)
        self.assertIn("1 used, 1 on but never used", done.stdout)
        self.assertIn("Read (Sign) at 9,9: no walkable route to it", done.stdout)


class AdviserTests(unittest.TestCase):
    def test_an_answer_is_always_written_and_no_key_is_logged(self):
        with tempfile.TemporaryDirectory() as base:
            folder = Path(base) / "playthrough-x"
            folder.mkdir()
            (folder / "ask-0001.json").write_text(json.dumps({"id": 1, "reason": "nothing to do", "options": []}), encoding="utf-8")
            (folder / "ask-0002.json").write_text(json.dumps({"id": 2, "reason": "sk-ant-abcdefghijklmnop", "scene": "S",
                                                              "options": [{"id": "use:1", "kind": "use", "label": "Door", "detail": ""}]}), encoding="utf-8")
            env = dict(os.environ, PLAYTEST_ADVISER_FAKE="1")
            done = python(SCRIPTS / "unity_playtest_adviser.py", folder, "--once", cwd=base, env=env)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("no options", json.loads((folder / "answer-0001.json").read_text(encoding="utf-8"))["error"])
            self.assertEqual(json.loads((folder / "answer-0002.json").read_text(encoding="utf-8"))["choice"], "use:1")
            written = (folder / "adviser.log").read_text(encoding="utf-8")
            self.assertNotIn("sk-ant-abcdefghijklmnop", written)
            self.assertIn("[key removed]", written)


    def test_ruled_out_options_never_reach_the_model_or_the_answer(self):
        with tempfile.TemporaryDirectory() as base:
            folder = Path(base) / "playthrough-x"
            folder.mkdir()
            settings = Path(base) / "unity-playtest.json"
            settings.write_text(json.dumps({"adviser_never_offer": ["buy .*\\d", "^accept all$"]}), encoding="utf-8")
            options = [{"id": "menu:buy", "kind": "menu", "label": "Buy 500 gems for 4.99", "detail": ""},
                       {"id": "menu:leave", "kind": "menu", "label": "Leave the shop", "detail": ""}]
            (folder / "ask-0001.json").write_text(json.dumps({"id": 1, "reason": "a menu", "options": options}), encoding="utf-8")
            (folder / "ask-0002.json").write_text(json.dumps({"id": 2, "reason": "a form", "options": [
                {"id": "menu:all", "kind": "menu", "label": "Accept all", "detail": ""}]}), encoding="utf-8")
            env = dict(os.environ, PLAYTEST_ADVISER_FAKE="menu:buy")
            done = python(SCRIPTS / "unity_playtest_adviser.py", folder, "--once", "--settings", settings, cwd=base, env=env)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(json.loads((folder / "answer-0001.json").read_text(encoding="utf-8"))["choice"], "menu:leave")
            self.assertIn("ruled out", json.loads((folder / "answer-0002.json").read_text(encoding="utf-8"))["error"])
            self.assertIn("1 option(s) held back", (folder / "adviser.log").read_text(encoding="utf-8"))


class SettingsTests(unittest.TestCase):
    def test_unknown_setting_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = Path(folder) / "unity-playtest.json"
            settings.write_text(json.dumps({"compnay": "typo"}), encoding="utf-8")
            (Path(folder) / "progress.txt").write_text("   1.0  SCENE  now Village\n", encoding="utf-8")
            done = python(SCRIPTS / "unity_playtest_report.py", folder, "--settings", settings)
            self.assertNotEqual(done.returncode, 0)
            self.assertIn("Unknown settings", done.stderr)

    def test_template_settings_are_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "progress.txt").write_text("   1.0  SCENE  now Village\n", encoding="utf-8")
            done = python(SCRIPTS / "unity_playtest_report.py", folder, "--settings",
                          ROOT / "skills/app-playtesting/assets/unity-playtest.json")
            self.assertEqual(done.returncode, 0, done.stderr)

    def test_scripts_explain_themselves(self):
        for script in sorted(SCRIPTS.glob("unity_playtest*.py")):
            if script.name != "unity_playtest_common.py":
                self.assertEqual(python(script, "--help").returncode, 0, script.name)


if __name__ == "__main__":
    unittest.main()
