#!/usr/bin/env python3
"""Add up a Unity in-editor bot's play logs into what it has and hasn't tried.

    python3 unity_playtest_coverage.py [RUNS_FOLDER | RUN ...] [--show 30] [--settings unity-playtest.json]

Give it the folder that holds the runs (default: run_folder in the settings), or the runs to count. Across those
runs it reports:
  - which scripted sequences have started, out of all those in the game if the settings name a catalogue of them
  - which interactive things have been used, which are on but were never used, and which the bot could not reach
  - which menus have been opened and which milestones were reached

"Started" and "used" mean it happened once; they do not mean the thing works. Use the lists to choose what to
test next, not as a score.
"""
import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unity_playtest_common import LINE, beside, find_project, load_settings, play_log_in  # noqa: E402


def catalogue(path) -> dict:
    """Every scripted sequence in the game, from a text file of "group | scene | name" lines (scene may be empty)."""
    lists = {}
    if path is None or not path.is_file():
        return lists
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = [part.strip() for part in raw.split("|")]
        if len(parts) == 3 and parts[2] and not raw.startswith("#"):
            lists[parts[1] + "/" + parts[2]] = (parts[0], parts[1], parts[2])
    return lists


def read_run(path: Path, settings: dict) -> dict:
    path = play_log_in(path)
    run = {"label": path.parent.name.replace("playthrough-", ""), "begun": set(), "scenes": set(), "menus": set(),
           "completed": set(), "used": Counter(), "hotspots": {}, "has_hotspots": False}
    if not path.is_file():
        return run
    hud, milestone, section = set(settings["hud_menus"]), settings["milestone_text"], "log"
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if raw.startswith("=== "):
            section = raw[4:].split(" ")[0].lower()
            run["has_hotspots"] = run["has_hotspots"] or section == "hotspots"
            continue
        if section in ("log", "playthrough"):
            match = LINE.match(raw)
            if not match:
                continue
            tag, text = match.group(2), match.group(3).strip()
            if tag == "BEGIN":
                run["begun"].add(re.sub(r" from \d+$", "", text))
            elif tag == "SCENE" and text.startswith("now "):
                run["scenes"].add(text[4:])
            elif tag == "MENU+" and text not in hud:
                run["menus"].add(text)
            elif tag == "VAR" and milestone and milestone in text and text.endswith("= True"):
                run["completed"].add(text.split(" = ")[0])
            elif tag == "USE":
                run["used"][text.replace("hotspot ", "", 1)] += 1
        elif section == "hotspots":
            parts = [part.strip() for part in raw.split(" | ")]
            if len(parts) >= 5:
                # used N or never | on or off | label | object name | x,z | why it couldn't be reached
                run["hotspots"]["%s (%s) at %s" % (parts[2], parts[3], parts[4])] = (parts[0], parts[1], parts[5] if len(parts) > 5 else "")
    return run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", type=Path, help="the folder of runs, or the runs to count")
    parser.add_argument("--show", type=int, default=30, help="how many names to print in each list (default 30)")
    parser.add_argument("--settings", type=Path, default=None, help="the game's settings file (default: unity-playtest.json in the project)")
    args = parser.parse_args()

    project = find_project(Path.cwd())
    settings, settings_file = load_settings(args.settings, project)
    paths = args.paths or ([project / settings["run_folder"]] if project else [])
    runs = []
    for path in paths:
        if path.is_dir() and not (path / "playthrough.txt").is_file() and not (path / "progress.txt").is_file():
            runs += [read_run(p, settings) for p in sorted(path.glob("playthrough-*"))]
        else:
            runs.append(read_run(path, settings))
    runs = [run for run in runs if run["begun"] or run["hotspots"] or run["used"]]
    if not runs:
        sys.exit("No play logs found; give the folder that holds playthrough-* folders")
    print("Coverage across %d runs: %s" % (len(runs), ", ".join(run["label"] for run in runs)))

    # scripted sequences: a log names a scene's sequence without its scene, so match it within the scenes a run visited
    lists = catalogue(beside(settings_file, settings["catalogue"]))
    begun = set().union(*(run["begun"] for run in runs))
    if lists:
        started = set()
        for run in runs:
            for key, (_, scene, name) in lists.items():
                if name in run["begun"] and (not scene or scene in run["scenes"]):
                    started.add(key)
        print("\nScripted sequences started: %d of %d" % (len(started), len(lists)))
        by_group = defaultdict(lambda: [0, 0])
        for key, (group, _, _) in lists.items():
            by_group[group][1] += 1
            by_group[group][0] += key in started
        for group, (done, total) in sorted(by_group.items(), key=lambda item: -item[1][1]):
            print("  %-22s %3d of %3d" % (group, done, total))
        unknown = sorted(begun - {name for _, _, name in lists.values()})
        if unknown:
            print("  started but not in the catalogue (made at run time, or renamed): " + ", ".join(unknown[:args.show]))
    else:
        print("\nScripted sequences started: %d (the settings name no catalogue, so there is no total)" % len(begun))

    # interactive things: the runs that list them say what exists; any run can have used one
    with_section = [run for run in runs if run["has_hotspots"]]
    if with_section:
        ever = {}
        for run in with_section:
            for name, (used, state, why) in run["hotspots"].items():
                before = ever.get(name, ("never", state, why))
                ever[name] = ("used" if used.startswith("used") or before[0] == "used" else "never", state, why or before[2])
        used = sorted(name for name, (u, _, _) in ever.items() if u == "used")
        blocked = sorted("%s: %s" % (name, why) for name, (u, state, why) in ever.items() if u == "never" and state == "on" and why)
        untried = sorted(name for name, (u, state, why) in ever.items() if u == "never" and state == "on" and not why)
        off = sorted(name for name, (u, state, _) in ever.items() if u == "never" and state == "off")
        print("\nInteractive things (from %d runs that list them): %d used, %d on but never used, %d switched off"
              % (len(with_section), len(used), len(blocked) + len(untried), len(off)))
        for title, names in (("On, never used, and the bot could not get there", blocked), ("On, never used, not yet tried", untried),
                             ("Switched off the whole time (something in the game probably turns them on)", off)):
            if names:
                print("  " + title + " (%d):" % len(names))
                for name in names[:args.show]:
                    print("    " + name)
                if len(names) > args.show:
                    print("    ... and %d more (use --show)" % (len(names) - args.show))
    else:
        used = Counter()
        for run in runs:
            used.update(run["used"])
        print("\nInteractive things used (no run lists all of them, so there is no total): %d" % len(used))

    menus = sorted(set().union(*(run["menus"] for run in runs)))
    print("\nMenus opened (%d): %s" % (len(menus), ", ".join(menus)))
    flags = sorted(set().union(*(run["completed"] for run in runs)))
    print("Milestones reached (%d): %s" % (len(flags), ", ".join(flags)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
