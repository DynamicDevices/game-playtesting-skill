"""A stand-in for the Unity editor, for offline tests of the Unity in-editor scripts. It is not Unity.

It takes the editor's batch-mode test arguments, reads the PLAYTEST_* environment variables a real bot would read,
and writes a small synthetic play log, a test result and a saved game. It also does what the real editor does to a
workspace: rewrites an asset, and leaves files behind. FAKE_EDITOR_MODE picks the story: "ok" or "held".
"""
import json
import os
import sys
import time
from pathlib import Path


def value(flag):
    return sys.argv[sys.argv.index(flag) + 1]


def main():
    project = Path(value("-projectPath"))
    label = os.environ["PLAYTEST_LABEL"]
    run = Path(os.environ["PLAYTEST_RUN_FOLDER"]) / ("playthrough-" + label)
    run.mkdir(parents=True, exist_ok=True)
    saves = Path(os.environ["FAKE_EDITOR_SAVES"])
    started_from = (saves / "slot.txt").read_text(encoding="utf-8").strip() if (saves / "slot.txt").is_file() else "nothing"
    held = os.environ.get("FAKE_EDITOR_MODE", "ok") == "held"

    lines = ["=== PLAYTHROUGH (" + label + ")",
             "   0.0  SETUP  until: " + os.environ.get("PLAYTEST_UNTIL", ""),
             "   1.0  SCENE  now Loader",
             "   2.0  SCENE  now Village",
             "   2.5  VAR    StartedFrom = " + started_from,
             "   3.0  ERROR  old error at start",
             "   4.0  BEGIN  OpenDoor",
             "   4.5  END    OpenDoor",
             "   6.0  USE    hotspot Door"]
    if os.environ.get("PLAYTEST_ADVISER") == "1":
        # what a real bot does when its rules run out: write the situation, wait for an answer, act on it
        ask = {"id": 1, "reason": "a menu with choices", "scene": "Village", "menu": "Garden", "objectives": ["Plant a seed 0/1"],
               "on_screen": ["Plant", "Done"], "inventory": ["Seed x1"], "recent": lines[-3:], "screenshot": "",
               "options": [{"id": "press:Done", "kind": "press", "label": "Done", "detail": ""},
                           {"id": "press:Plant", "kind": "press", "label": "Plant", "detail": ""}]}
        (run / "ask-0001.json").write_text(json.dumps(ask), encoding="utf-8")
        answer, waited = run / "answer-0001.json", 0.0
        while not answer.is_file() and waited < 20:
            time.sleep(0.2)
            waited += 0.2
        told = json.loads(answer.read_text(encoding="utf-8")) if answer.is_file() else {"choice": "", "error": "no answer in time"}
        lines += ["   6.5  ASK    a menu with choices: Garden",
                  "   6.9  TOLD   " + (told["choice"] or "nothing (" + told.get("error", "") + ")")]
    if held:
        lines += ["   7.0  MENU   Shop is open (Buy, Sell)",
                  " 127.0  DONE   held by the Shop menu: no rule for Buy, Sell"]
    else:
        lines += ["   7.0  VAR    TutorialComplete = True",
                  "  17.0  DONE   reached what the run was asked to reach"]
    lines += ["=== FINAL VARIABLES"] + ([] if held else ["1 TutorialComplete = True"])
    lines += ["=== HOTSPOTS (Village: 2)",
              "used 1 | on | Open | Door | 1,2 | ",
              "never | on | Read | Sign | 9,9 | no walkable route to it",
              "=== ERRORS", "1x old error at start"]
    (run / "playthrough.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (run / "0001.png").write_bytes(b"synthetic, not an image")

    Path(value("-testResults")).write_text('<test-run><test-case name="Bot" result="Passed"/></test-run>\n', encoding="utf-8")
    Path(value("-logFile")).write_text("stand-in editor log\n", encoding="utf-8")
    saves.mkdir(parents=True, exist_ok=True)
    (saves / "slot.txt").write_text("after " + label + "\n", encoding="utf-8")
    (saves / "TestResults.xml").write_text("<copy/>\n", encoding="utf-8")
    Path(os.environ["PLAYTEST_MEMORY"]).write_text("Village|Door|1,2\n", encoding="utf-8")

    (project / "Assets" / "Thing.mat").write_text("rewritten by the editor\n", encoding="utf-8")     # the editor's own rewrite
    (project / "Assets" / "Bot.cs").write_text("// edited by a person during the run\n", encoding="utf-8")  # not the editor's
    (project / "Assets" / "InitTestScene123.unity").write_text("left behind\n", encoding="utf-8")


if __name__ == "__main__":
    main()
