"""Shared by the Unity in-editor scripts: the per-game settings file and the play-log line format.

No input, network or app-control operations are performed here.
"""
import json
import os
import re
import sys
from pathlib import Path

# "  12.3  TAG    text": seconds since the run began, a tag, the rest
LINE = re.compile(r"^\s*(\d+\.\d)\s{2}(\S+)\s*(.*)$")

DEFAULTS = {
    "app": "",              # the game's name, for reports and session records
    "company": "",          # Unity's Company Name and Product Name: together they locate the saved games
    "product": "",
    "save_folder": "",      # or give the saved-game folder outright (absolute, or relative to the project)
    "run_folder": "Logs/Playtest",   # where runs are kept, relative to the project
    "test_filter": "PlaytestBot",    # the play-mode test class or name that is the bot
    "max_minutes": 0,       # the longest --minutes the bot's test allows; 0 for no limit
    "start_scenes": [],     # scenes that come before the game proper (a loader, a title screen)
    "milestone_text": "Complete",    # a VAR line containing this and ending "= True" counts as a milestone
    "hud_menus": [],        # menus that are part of the normal screen, not ones that take it over
    "known_issues": "",     # a text file of error texts that don't fail a report, relative to this settings file
    "catalogue": "",        # a text file listing every scripted sequence ("group | scene | name"), for coverage
    "leftovers": ["Assets/InitTestScene*"],  # files and folders a test run leaves in the project, removed if the run made them
    "session_validator": "",  # a copy of this repository's scripts/validate_session.py, relative to this settings file
    # the optional AI adviser (unity_playtest.py --adviser): it answers the bot's questions with Claude
    "adviser_model": "claude-opus-5-5",
    "adviser_effort": "low",          # low, medium, high: how hard the model thinks about each question
    "adviser_max_questions": 60,      # the most questions sent to the model in one run
    "adviser_keychain_service": "",   # macOS only: a Keychain item that holds the API key, instead of the environment
    "adviser_keychain_account": "",
    "adviser_notes": "",              # a few sentences about the game, added to what the model is told
}
SETTINGS_NAME = "unity-playtest.json"


def find_project(start: Path):
    for folder in [start, *start.parents]:
        if (folder / "ProjectSettings" / "ProjectVersion.txt").is_file():
            return folder
    return None


def load_settings(path, project):
    """Returns (settings, the file they came from or None). Unknown keys are refused so a typo isn't ignored."""
    chosen = Path(path) if path else None
    if chosen is None and os.environ.get("UNITY_PLAYTEST_SETTINGS"):
        chosen = Path(os.environ["UNITY_PLAYTEST_SETTINGS"])
    if chosen is None and project and (project / SETTINGS_NAME).is_file():
        chosen = project / SETTINGS_NAME
    settings = dict(DEFAULTS)
    if chosen is None:
        return settings, None
    if not chosen.is_file():
        sys.exit("No settings file at " + str(chosen))
    try:
        given = json.loads(chosen.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        sys.exit("The settings file " + str(chosen) + " is not valid JSON: " + str(error))
    if not isinstance(given, dict):
        sys.exit("The settings file must hold one JSON object")
    unknown = sorted(set(given) - set(DEFAULTS))
    if unknown:
        sys.exit("Unknown settings in " + str(chosen) + ": " + ", ".join(unknown))
    for key, value in given.items():
        if type(value) is not type(DEFAULTS[key]):
            sys.exit("The setting " + key + " should be " + type(DEFAULTS[key]).__name__)
        settings[key] = value
    return settings, chosen.resolve()


def beside(settings_file, name):
    """A path named in the settings file, taken relative to that file."""
    if not name:
        return None
    path = Path(name)
    if not path.is_absolute() and settings_file is not None:
        path = settings_file.parent / path
    return path


def play_log_in(path: Path) -> Path:
    """A run's folder holds playthrough.txt once the run has ended and progress.txt while it is going."""
    if path.is_dir():
        return path / "playthrough.txt" if (path / "playthrough.txt").is_file() else path / "progress.txt"
    return path
