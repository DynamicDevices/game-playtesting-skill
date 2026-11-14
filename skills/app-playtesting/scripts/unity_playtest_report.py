#!/usr/bin/env python3
"""Turn a Unity in-editor bot's play log into a short report with an exit code.

    python3 unity_playtest_report.py RUN_FOLDER_OR_LOG [--expect "TEXT"] [--compare OTHER_RUN]
        [--session session.json --build BUILD --start "STARTING STATE"] [--settings unity-playtest.json]

Give it a run's folder or its playthrough.txt. While a run is still going (or if it was cut short) the folder only
has progress.txt, and the report reads that instead; it has the same lines but no final list of errors.

The report lists what the bot got done (milestones, items, objectives), what held it up, and every error. It exits
with 1 if anything needs attention: an error that isn't in the known-issues file, a stall, a pause, a menu the bot
never got out of, a run that never reached the game, or an --expect text that isn't in the log. Otherwise 0.

It reads a log and writes text. It checks what the bot logged, not whether the game is good to play.
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unity_playtest_common import LINE, beside, find_project, load_settings, play_log_in  # noqa: E402


def read(path: Path):
    """Returns (label, events, errors). events are (seconds, tag, text); errors are (count, text)."""
    path = play_log_in(path)
    if not path.is_file():
        sys.exit("No play log at " + str(path))
    label, events, errors, section = path.parent.name.replace("playthrough-", ""), [], [], "log"
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if raw.startswith("=== "):
            section = raw[4:].split(" ")[0].lower()
            if section == "playthrough":
                label = raw[raw.find("(") + 1:raw.rfind(")")]
                section = "log"
            continue
        if section == "log":
            match = LINE.match(raw)
            if match:
                events.append((float(match.group(1)), match.group(2), match.group(3).strip()))
        elif section == "errors":
            match = re.match(r"^(\d+)x\s+(.*)$", raw)
            if match:
                errors.append((int(match.group(1)), match.group(2)))
    if not errors:  # progress.txt has no summary of errors; count the ERROR lines (each distinct error is logged once)
        errors = [(1, text) for _, tag, text in events if tag == "ERROR"]
    return path, label, events, errors


def known_issues(path) -> list:
    if path is None or not path.is_file():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]


def summarise(path: Path, settings: dict, known: list):
    path, label, events, errors = read(path)
    before_game = set(settings["start_scenes"])
    game_start = next((t for t, tag, text in events if tag == "SCENE" and text.startswith("now ") and text[4:] not in before_game), None)
    milestone = settings["milestone_text"]
    # "short of Well by 17.2m" or "short of Miner by 32.1m; the walkable route stops 31m short of it"
    stuck = [m for m in (re.match(r"short of (.*) by [\d.]+m(?:; (.*))?$", text) for _, tag, text in events if tag == "STUCK") if m]
    facts = {
        "label": label,
        "path": path,
        "length": events[-1][0] if events else 0.0,
        "scenes": [text[4:] for _, tag, text in events if tag == "SCENE" and text.startswith("now ")],
        "completed": [(t, text) for t, tag, text in events if tag == "VAR" and milestone and milestone in text and text.endswith("= True")],
        "items": [(t, tag + " " + text) for t, tag, text in events if tag in ("INV+", "INV-")],
        "objectives": [(t, text) for t, tag, text in events if tag == "OBJ"],
        "menus_left": [(t, text) for t, tag, text in events if tag == "LEAVE"],
        "ratings": [(t, text) for t, tag, text in events if tag == "RATE"],
        "used": [text for _, tag, text in events if tag == "USE"],
        "speech": sum(1 for _, tag, _ in events if tag == "SAY"),
        "picks": [text for _, tag, text in events if tag == "PICK"],
        "pauses": [(t, text) for t, tag, text in events if tag == "PAUSE"],
        "stalls": [(t, text) for t, tag, text in events if tag == "STALL?"],
        "stuck": Counter(m.group(1) for m in stuck if not m.group(2)),
        "no_route": Counter(m.group(1) + " (" + m.group(2) + ")" for m in stuck if m.group(2)),
        "chosen": [(t, text) for t, tag, text in events if tag == "CHOOSE"],
        "setup": next((text for _, tag, text in events if tag == "SETUP"), ""),
        "goal_notes": [text for _, tag, text in events if tag == "GOAL" and text.startswith("nothing usable")],
        "done": next((text for _, tag, text in events if tag == "DONE"), ""),
        "game_start": game_start,
        "errors": errors,
        "new_errors": [(n, e) for n, e in errors if not any(k in e for k in known)],
        "lines": [tag + " " + text for _, tag, text in events],
    }
    running = Counter()
    for _, tag, text in events:
        name = re.sub(r" from \d+$", "", text)
        if tag == "BEGIN":
            running[name] += 1
        elif tag == "END" and running[name] > 0:
            running[name] -= 1
    facts["still_running"] = sorted(name for name, n in running.items() if n > 0)
    # a menu that took over the screen and was still up at the end: the bot found no way out of it
    held = {}
    for t, tag, text in events:
        if tag == "MENU" and " is open" in text:
            held[text.split(" is open")[0]] = t
        elif tag in ("LEAVE", "MENU-"):
            held.pop(text.split(" ")[0], None)
    facts["menus_held"] = sorted((t, name) for name, t in held.items())
    return facts


def write_session(args, settings, f, faults, expected):
    """Writes what this run checked as one record in this skill's session format (app-playtest-session/v1).

    The record goes in the run's folder, because the evidence it names (the log, a screenshot) is given relative to it.
    """
    folder = f["path"].parent
    evidence = [{"id": "log", "kind": "log", "path": f["path"].name}]
    shots = sorted(p.name for p in folder.glob("*.png"))
    if shots:
        evidence.append({"id": "last-screen", "kind": "screenshot", "path": shots[-1]})
    steps = [{
        "action": "The bot plays from the starting state for %.0f s (ended: %s)" % (f["length"], f["done"] or "time ran out"),
        "expected": "No error outside the known-issues file, no stall or pause, and no menu left up at the end",
        "actual": "; ".join(faults) if faults else "None of those happened. %d errors were logged, all listed as known" % len(f["errors"]),
        "outcome": "fail" if faults else "pass",
        "evidence": [item["id"] for item in evidence],
    }]
    for text, found in expected:
        steps.append({
            "action": "Look in the play log for: " + text,
            "expected": "A log line containing that text",
            "actual": found if found else "No log line contains it",
            "outcome": "pass" if found else "fail",
            "evidence": ["log"],
        })
    record = {
        "schema": "app-playtest-session/v1",
        "record_kind": "observed",
        "app": {"name": settings["app"] or "not recorded", "build": args.build,
                "platform": "Unity editor play mode with no window; play-mode test " + settings["test_filter"]},
        "question": ("Does the game reach " + ", ".join(text for text, _ in expected) + " with no fault logged?") if expected
                    else "Does the bot play on from this state with no fault logged?",
        "starting_state": args.start,
        "reset_method": "unity_playtest.py --from-checkpoint NAME restores a kept saved game and --fresh starts a new one; both keep the current save",
        "status": "fail" if any(step["outcome"] == "fail" for step in steps) else "pass",
        "steps": steps,
        "evidence": evidence,
        "limitations": [
            "The bot plays inside the editor with no window: sound, frame rate, the look of the interface and real input devices are not checked",
            "A pass means the expected log lines appeared and no fault was logged; it does not say the game is good to play",
            "Screenshots are the camera view and may not show the on-screen interface; the on-screen text is in the log",
        ],
    }
    target = folder / Path(args.session).name
    target.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("session record: " + str(target))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("log", type=Path)
    parser.add_argument("--expect", action="append", default=[], help="text that must appear in a log line (repeatable)")
    parser.add_argument("--compare", type=Path, default=None, help="another run to compare with")
    parser.add_argument("--settings", type=Path, default=None, help="the game's settings file (default: unity-playtest.json in the project)")
    parser.add_argument("--known-issues", type=Path, default=None, help="a file of error texts that don't fail the report (default: from the settings)")
    parser.add_argument("--session", default=None, metavar="NAME",
                        help="also write the checks as a session record (app-playtest-session/v1) in the run's folder, e.g. session.json")
    parser.add_argument("--build", default="not recorded", help="the build or changeset that was run, for the session record")
    parser.add_argument("--start", default="not recorded", help="the starting state (a checkpoint name, or 'a new game'), for the session record")
    args = parser.parse_args()

    settings, settings_file = load_settings(args.settings, find_project(Path.cwd()))
    known = known_issues(args.known_issues or beside(settings_file, settings["known_issues"]))
    f = summarise(args.log, settings, known)
    attention = []
    if f["game_start"] is None:
        attention.append("the run never reached the game" + (" (it stayed in: " + ", ".join(f["scenes"]) + ")" if f["scenes"] else ""))
    for t, text in f["pauses"]:
        attention.append("at %.0f s %s (is the computer going to sleep? the rest of the run can't be trusted)" % (t, text))
    for t, text in f["stalls"]:
        attention.append("stalled at %.0f s: %s" % (t, text))
    for t, name in f["menus_held"]:
        attention.append("the %s menu opened at %.0f s and was still up at the end" % (name, t))
    for n, e in f["new_errors"]:
        attention.append("error (%dx): %s" % (n, e))
    if f["done"].startswith("held by"):
        attention.append("the run ended early: " + f["done"])
    faults = list(attention)  # everything above is a fault in the run; below, what the run was expected to reach
    expected = []
    for text in args.expect:
        squeezed = " ".join(text.split())
        # the bot logs its own settings, including these texts, on a SETUP line: that line must not count
        found = next((line for line in f["lines"] if squeezed in " ".join(line.split()) and not line.startswith("SETUP")), None)
        expected.append((text, found))
        if found is None:
            attention.append("expected but not found: " + text)

    print("Play-through %s: %.0f s, scenes: %s" % (f["label"], f["length"], " > ".join(f["scenes"]) or "none"))
    print("Result: " + ("NEEDS ATTENTION" if attention else "OK"))
    for item in attention:
        print("  ! " + item)

    def block(title, rows):
        if rows:
            print("\n" + title)
            for row in rows:
                print("  " + row)

    def when(t):
        return "from the saved game" if f["game_start"] is not None and t < f["game_start"] else "%.0f s" % t

    block("Completed", ["%s (%s)" % (text, when(t)) for t, text in f["completed"]])
    block("Items", ["%s (%.0f s)" % (text, t) for t, text in f["items"]])
    block("Objectives shown", ["%.0f s  %s" % (t, text) for t, text in f["objectives"]])
    block("Menus the bot left", ["%.0f s  %s" % (t, text) for t, text in f["menus_left"]])
    block("Ratings given", ["%.0f s  %s" % (t, text) for t, text in f["ratings"]])
    block("Objectives nothing matched", f["goal_notes"])
    block("Used (%d)" % len(f["used"]), ["%dx %s" % (n, name) for name, n in Counter(f["used"]).most_common(15)])
    block("Answers chosen", ["%.0f s  %s" % (t, text) for t, text in f["chosen"]])
    block("No walkable route to (%d tries)" % sum(f["no_route"].values()), ["%dx %s" % (n, name) for name, n in f["no_route"].most_common(10)])
    block("Stopped moving on the way to (%d tries)" % sum(f["stuck"].values()), ["%dx %s" % (n, name) for name, n in f["stuck"].most_common(10)])
    block("Sequences still running at the end", f["still_running"])
    block("All errors", ["%dx %s%s" % (n, e, "" if (n, e) in f["new_errors"] else "  [known]") for n, e in f["errors"]])
    print("\nSpeech lines: %d. Conversation choices: %d. Ended: %s" % (f["speech"], len(f["picks"]), f["done"] or "time ran out"))
    if f["setup"]:
        print("Run settings: " + f["setup"])
    if args.session:
        write_session(args, settings, f, faults, expected)

    if args.compare:
        g = summarise(args.compare, settings, known)
        print("\nCompared with %s:" % g["label"])
        for key in ("completed", "items"):
            mine, theirs = {text for _, text in f[key]}, {text for _, text in g[key]}
            for text in sorted(mine - theirs):
                print("  only in %s: %s" % (f["label"], text))
            for text in sorted(theirs - mine):
                print("  only in %s: %s" % (g["label"], text))
        mine, theirs = {e for _, e in f["errors"]}, {e for _, e in g["errors"]}
        for e in sorted(mine - theirs):
            print("  new error: " + e)
        for e in sorted(theirs - mine):
            print("  error gone: " + e)
    return 1 if attention else 0


if __name__ == "__main__":
    sys.exit(main())
