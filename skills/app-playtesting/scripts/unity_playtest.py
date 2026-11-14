#!/usr/bin/env python3
"""Run a Unity play-mode bot inside the editor with no window, and tidy up after the editor.

    python3 unity_playtest.py LABEL [--until "TEXT"] [--minutes 10] [--fresh | --from-checkpoint NAME] [--save-checkpoint NAME]
    python3 unity_playtest.py --list-checkpoints

The game's details (its name, where it saves, which test is the bot) come from a settings file, unity-playtest.json,
in the project folder or named with --settings. See the Unity in-editor adapter page for the keys and for what the
bot has to do: it reads PLAYTEST_* environment variables and writes a play log.

What this does, in order:
  1. notes which workspace files are already changed, so it never touches the developer's own edits
  2. with --fresh or --from-checkpoint, moves the current saved game into the checkpoints folder, then starts from
     no save (a new game) or from a copy of the named checkpoint
  3. runs the test with the Unity CLI (`unity test`), or with the editor program if --editor-path is given
  4. prints the result, any compile errors, and where the logs are
  5. undoes the asset and settings files the editor rewrote during the run, and removes files the run left behind
  6. prints the report; each --until text is also checked, so the exit code is the verdict
  7. with --save-checkpoint, keeps the saved game under that name, but only if the report was clean

Nothing is deleted: a save that is replaced is kept as a checkpoint called "aside-<date>-<label>". This script
drives a local developer project only. It does not install anything, change security settings or contact a network.
Run live on macOS with Plastic SCM; the git path is covered by an offline test with a stand-in editor only.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unity_playtest_common import find_project, load_settings  # noqa: E402

NAME = r"[A-Za-z0-9_-]+"
HAND_WRITTEN = {".cs", ".asmdef", ".asmref", ".shader", ".hlsl", ".cginc", ".py", ".sh", ".md", ".txt", ".json", ".xml",
                ".yml", ".yaml", ".uxml", ".uss"}


def editor_version(project: Path) -> str:
    text = (project / "ProjectSettings" / "ProjectVersion.txt").read_text(encoding="utf-8")
    match = re.search(r"m_EditorVersion:\s*(\S+)", text)
    if not match:
        sys.exit("Could not read the editor version from ProjectVersion.txt")
    return match.group(1)


def save_folder(settings: dict, project: Path) -> Path:
    """Where the game keeps its saves: the folder given in the settings, or Unity's persistentDataPath."""
    if settings["save_folder"]:
        folder = Path(settings["save_folder"]).expanduser()
        return folder if folder.is_absolute() else project / folder
    if not settings["company"] or not settings["product"]:
        sys.exit("The settings need company and product (or save_folder) to find the game's saved games")
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform.startswith("win"):
        base = Path.home() / "AppData" / "LocalLow"
    else:
        base = Path.home() / ".config" / "unity3d"
    return base / settings["company"] / settings["product"]


def checkpoints_folder(saves: Path) -> Path:
    return saves.with_name(saves.name + ".checkpoints")


def list_checkpoints(saves: Path) -> int:
    folder = checkpoints_folder(saves)
    names = sorted(p.name for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []
    print("checkpoints in " + str(folder) + ":" if names else "no checkpoints yet in " + str(folder))
    for name in names:
        info = folder / name / "info.txt"
        print("  %-28s %s" % (name, info.read_text(encoding="utf-8").strip().replace("\n", "; ") if info.is_file() else ""))
    return 0


def store_checkpoint(saves: Path, name: str, memory: Path, note: str) -> Path:
    """Copies the current saved game (and the bot's memory) into the checkpoints folder."""
    target = checkpoints_folder(saves) / name
    target.mkdir(parents=True)
    shutil.copytree(saves, target / "save")
    if memory.is_file():
        shutil.copy2(memory, target / "bot-memory.txt")
    (target / "info.txt").write_text(note + "\n", encoding="utf-8")
    return target


def milestones(play_log: Path, text: str) -> str:
    """The milestone flags that are true at the end of a run, for a checkpoint's description."""
    if not play_log.is_file() or not text:
        return ""
    whole = play_log.read_text(encoding="utf-8", errors="replace")
    final = whole.split("=== FINAL VARIABLES", 1)[1] if "=== FINAL VARIABLES" in whole else ""
    return ", ".join(re.findall(r"(?m)^\d+ (\w*" + re.escape(text) + r"\w*) = True$", final))


def editor_owned(project: Path, path: Path) -> bool:
    """True for a file the editor rewrites by itself when it opens a project: an asset or a setting, not code or text."""
    try:
        parts = path.resolve().relative_to(project).parts
    except ValueError:
        return False
    return bool(parts) and parts[0] in ("Assets", "ProjectSettings", "Packages") and path.suffix.lower() not in HAND_WRITTEN


class Workspace:
    """The project's version control: Plastic SCM or git. Used to see what a run changed, and to put it back."""

    def __init__(self, project: Path):
        self.project, self.kind, self.top = project, None, project
        for folder in [project, *project.parents]:
            if (folder / ".plastic").exists() and shutil.which("cm"):
                self.kind = "plastic"
                break
            if (folder / ".git").exists() and shutil.which("git"):
                self.kind, self.top = "git", folder
                break

    def run(self, *command, timeout=600):
        try:
            return subprocess.run(command, cwd=self.project, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            return None

    def changed(self):
        """Absolute paths of controlled files that differ from what is checked in. None if that can't be found out."""
        if self.kind == "plastic":
            out = self.run("cm", "status", "--machinereadable", "--fieldseparator=|")
            if out is None or out.returncode != 0:
                return None
            return {line.split("|")[1] for line in out.stdout.splitlines() if line.startswith("CH|")}
        if self.kind == "git":
            out = self.run("git", "status", "--porcelain", "-z", "--untracked-files=no")
            if out is None or out.returncode != 0:
                return None
            return {str(self.top / entry[3:]) for entry in out.stdout.split("\0") if len(entry) > 3}
        return None

    def undo(self, paths):
        for i in range(0, len(paths), 100):
            if self.kind == "plastic":
                self.run("cm", "undo", *paths[i:i + 100])
            elif self.kind == "git":
                self.run("git", "checkout", "--", *paths[i:i + 100])

    def build(self) -> str:
        """What the workspace is on, for the session record."""
        if self.kind == "plastic":
            out = self.run("cm", "status", "--header", timeout=60)
            found = re.search(r"cs:\d+", out.stdout) if out else None
            return found.group(0) if found else "not recorded"
        if self.kind == "git":
            out = self.run("git", "rev-parse", "--short", "HEAD", timeout=60)
            return "git " + out.stdout.strip() if out and out.returncode == 0 and out.stdout.strip() else "not recorded"
        return "not recorded"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("label", nargs="?", help="name for this run, e.g. shop-1 (letters, digits, - and _)")
    parser.add_argument("--settings", type=Path, default=None, help="the game's settings file (default: unity-playtest.json in the project)")
    parser.add_argument("--filter", default=None, help="test class or name to run (default: test_filter in the settings)")
    parser.add_argument("--minutes", type=float, default=None, help="how long the bot plays (default: the bot's own)")
    parser.add_argument("--until", action="append", default=[], metavar="TEXT",
                        help="end the run once a log line contains this text (repeatable)")
    parser.add_argument("--idle-minutes", type=float, default=None,
                        help="end the run when nothing new has happened for this long (default: the bot's own; 0 never)")
    parser.add_argument("--fresh", action="store_true", help="keep the saved game as a checkpoint and start a new game")
    parser.add_argument("--from-checkpoint", metavar="NAME", help="keep the saved game as a checkpoint and start from this one")
    parser.add_argument("--save-checkpoint", metavar="NAME", help="after a clean run, keep the saved game under this name")
    parser.add_argument("--list-checkpoints", action="store_true", help="list the checkpoints and stop")
    parser.add_argument("--no-report", action="store_true", help="don't print the report after the run")
    parser.add_argument("--project", type=Path, default=None, help="Unity project folder (default: found from the current folder)")
    parser.add_argument("--editor-path", default=None, help="run this Unity editor program instead of the Unity CLI")
    parser.add_argument("--timeout", type=int, default=3000, help="seconds before the run is abandoned (default 3000)")
    parser.add_argument("--keep-changes", action="store_true", help="don't undo the files the editor changed")
    args = parser.parse_args()

    project = args.project or find_project(Path.cwd())
    if project is None:
        sys.exit("No Unity project found above " + str(Path.cwd()) + "; pass --project")
    project = project.resolve()
    settings, settings_file = load_settings(args.settings, project)
    saves = save_folder(settings, project)
    if args.list_checkpoints:
        return list_checkpoints(saves)
    if not args.label or not re.fullmatch(NAME, args.label):
        sys.exit("Give the run a label; it may only contain letters, digits, - and _")
    for name in (args.from_checkpoint, args.save_checkpoint):
        if name and not re.fullmatch(NAME, name):
            sys.exit("A checkpoint name may only contain letters, digits, - and _")
    if args.fresh and args.from_checkpoint:
        sys.exit("Use --fresh or --from-checkpoint, not both")
    if args.from_checkpoint and not (checkpoints_folder(saves) / args.from_checkpoint / "save").is_dir():
        sys.exit("No checkpoint called " + args.from_checkpoint + "; see --list-checkpoints")
    if args.save_checkpoint and (checkpoints_folder(saves) / args.save_checkpoint).exists():
        sys.exit("There is already a checkpoint called " + args.save_checkpoint + "; pick another name")
    if any("||" in text for text in args.until):
        sys.exit("An --until text can't contain ||")
    if args.minutes is not None and args.minutes <= 0:
        sys.exit("--minutes must be more than 0")
    if args.minutes is not None and settings["max_minutes"] and args.minutes > settings["max_minutes"]:
        sys.exit("--minutes can be at most %s for this game's bot" % settings["max_minutes"])

    test_filter = args.filter or settings["test_filter"]
    version = editor_version(project)
    run_folder = project / settings["run_folder"]
    out_dir = run_folder / ("run-" + args.label)
    out_dir.mkdir(parents=True, exist_ok=True)
    results, editor_log = out_dir / "test-results.xml", out_dir / "editor.log"
    for old in (results, editor_log):
        if old.exists():
            old.unlink()

    workspace = Workspace(project)
    before = workspace.changed()
    if before is None:
        print("note: no usable version control (Plastic or git) was found, so files the editor changes won't be undone")
    leftovers_before = {path for pattern in settings["leftovers"] for path in project.glob(pattern)}
    dump = saves / "TestResults.xml"  # the test runner drops a copy of its results beside the saves
    had_dump = dump.exists()

    memory = run_folder / "bot-memory.txt"
    if args.fresh or args.from_checkpoint:
        if saves.exists():
            aside = store_checkpoint(saves, "aside-" + time.strftime("%Y%m%d-%H%M%S") + "-" + args.label, memory,
                                     "the saved game as it was before run " + args.label)
            shutil.rmtree(saves)
            print("the saved game was kept as checkpoint " + aside.name)
        if memory.is_file():
            memory.unlink()
        if args.from_checkpoint:
            source = checkpoints_folder(saves) / args.from_checkpoint
            shutil.copytree(source / "save", saves)
            if (source / "bot-memory.txt").is_file():
                shutil.copy2(source / "bot-memory.txt", memory)
            print("starting from checkpoint " + args.from_checkpoint)
        else:
            print("starting a new game")

    env = dict(os.environ, PLAYTEST_LABEL=args.label, PLAYTEST_RUN_FOLDER=str(run_folder), PLAYTEST_MEMORY=str(memory))
    if args.until:
        env["PLAYTEST_UNTIL"] = "||".join(args.until)
    if args.idle_minutes is not None:
        env["PLAYTEST_IDLE_MINUTES"] = str(args.idle_minutes)
    if args.minutes is not None:
        env["PLAYTEST_MINUTES"] = str(args.minutes)
    if args.editor_path:
        command = [args.editor_path, "-batchmode", "-projectPath", str(project), "-runTests", "-testPlatform", "PlayMode",
                   "-testFilter", test_filter, "-testResults", str(results), "-logFile", str(editor_log)]
    else:
        unity = shutil.which("unity")
        if not unity:
            sys.exit("The Unity CLI (`unity`) isn't on the PATH; install it or pass --editor-path")
        command = [unity, "test", str(project), "--mode", "PlayMode", "--editor-version", version, "--filter", test_filter,
                   "--output", str(results), "--timeout", str(args.timeout), "--no-banner", "--non-interactive",
                   "--", "-logFile", str(editor_log)]
    if sys.platform == "darwin" and shutil.which("caffeinate"):
        command = ["caffeinate", "-i", "-s", *command]  # a Mac that goes to sleep freezes the editor in the middle of a run

    print("running " + test_filter + " as " + args.label + " on Unity " + version + " (this takes a while)")
    started = time.time()
    try:
        with open(out_dir / "runner.out", "w", encoding="utf-8") as sink:
            code = subprocess.run(command, cwd=project, env=env, stdout=sink, stderr=subprocess.STDOUT,
                                  timeout=args.timeout + 300).returncode
    except subprocess.TimeoutExpired:
        code = -1
        print("the run did not finish within the timeout")
    print("finished in %d s, exit code %d" % (time.time() - started, code))

    if editor_log.exists():
        log_text = editor_log.read_text(encoding="utf-8", errors="replace")
        for line in sorted(set(re.findall(r"Assets[^\n]*error CS\d+[^\n]*", log_text)))[:10]:
            print("compile error: " + line)
    if results.exists():
        outcomes = re.findall(r'<test-case[^>]*\bresult="(\w+)"', results.read_text(encoding="utf-8", errors="replace"))
        print("tests: " + (", ".join("%d %s" % (outcomes.count(o), o) for o in sorted(set(outcomes))) or "none ran"))
    else:
        print("no test results were written; read " + str(editor_log))

    # tidy up: only the kinds of file the editor rewrites (assets and settings), and only ones that changed during
    # this run. Files that were already changed are left alone, and so is anything a person may be editing while
    # the run is going: code, scripts, documents.
    if not args.keep_changes and before is not None:
        changed = sorted((workspace.changed() or set()) - before)
        mine = [path for path in changed if editor_owned(project, Path(path))]
        workspace.undo(mine)
        print("undid %d files the editor changed during the run" % len(mine))
        for path in changed:
            if path not in mine:
                print("left alone (changed during the run, not by the editor): " + path)
    for pattern in settings["leftovers"]:
        for leftover in project.glob(pattern):
            if leftover not in leftovers_before and leftover.is_file():
                leftover.unlink()
    if dump.exists() and not had_dump:
        dump.unlink()

    play_log = run_folder / ("playthrough-" + args.label) / "playthrough.txt"
    if play_log.exists():
        print("play log: " + str(play_log))
    print("run files: " + str(out_dir))
    verdict = 0
    if play_log.exists() and not args.no_report:
        print()
        start = ("checkpoint " + args.from_checkpoint if args.from_checkpoint
                 else "a new game" if args.fresh else "the saved game the last run left")
        report = [sys.executable, "-B", str(Path(__file__).with_name("unity_playtest_report.py")), str(play_log),
                  "--session", "session.json", "--build", workspace.build(), "--start", start]
        if settings_file:
            report += ["--settings", str(settings_file)]
        for text in args.until:
            report += ["--expect", text]
        verdict = subprocess.run(report, cwd=project).returncode
    elif not play_log.exists() and test_filter == settings["test_filter"]:
        print("the bot wrote no play log, so there is nothing to report on")
        verdict = 1  # another test (--filter) has no play log and is judged by its own result
    if args.save_checkpoint:
        # only a run that did what was asked of it is worth starting later runs from
        if code == 0 and verdict == 0 and saves.is_dir():
            flags = milestones(play_log, settings["milestone_text"])
            kept = store_checkpoint(saves, args.save_checkpoint, memory, "after run " + args.label + " on "
                                    + time.strftime("%Y-%m-%d") + ("\ncompleted: " + flags if flags else ""))
            print("saved game kept as checkpoint " + kept.name)
        else:
            print("no checkpoint was kept: the run failed, the report needs attention, or there is no saved game")
    return 0 if code == 0 and verdict == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
