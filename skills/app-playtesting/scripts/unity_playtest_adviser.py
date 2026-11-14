#!/usr/bin/env python3
"""Answer a Unity in-editor bot's questions with Claude, one action at a time.

    python3 unity_playtest_adviser.py RUN_FOLDER/playthrough-LABEL [--settings unity-playtest.json]

unity_playtest.py starts this when a run is given --adviser; it is not normally run by hand. The bot plays by fixed
rules and asks only when they run out: a menu with choices, or nothing the objective names. It writes the situation
to ask-NNNN.json in the run's folder (what is on screen, what it is carrying, the things it could do) and waits. This
program sends that to Claude, which picks one of the listed options, and writes answer-NNNN.json. The bot can only
do what a player can, so Claude can only choose from the options given.

What leaves the computer: each question's text and, when there is one, that moment's screenshot, to the Claude API.
Nothing else is read or sent. Every question, answer and token count is written to adviser.log in the run's folder.
An answer is remembered in adviser-memory.json beside the runs, so the same situation in a later run is answered
without a call (once per run: if it comes round again the remembered answer changed nothing, and Claude is asked).

The API key is found the way the Anthropic SDK finds it (ANTHROPIC_API_KEY, or an `ant auth login` profile). On
macOS the settings can instead name a Keychain item (adviser_keychain_service, adviser_keychain_account); the key is
read from it at run time, passed to the SDK, and never written or printed. Needs `pip install anthropic`.

This spends money on the key's account: the settings cap the questions per run (adviser_max_questions).
"""
import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from unity_playtest_common import find_project, load_settings  # noqa: E402

KEY_SHAPE = re.compile(r"sk-ant-[A-Za-z0-9_-]{6,}")
FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM = """You are advising an automated playtest bot that is playing a game inside the Unity editor, so its \
developers learn whether a player can make progress and where they might get lost.

The bot handles routine play by fixed rules: walking, following an objective that names something it can find, \
getting through speech. It asks you when its rules have run out: a menu that offers choices, an objective it cannot \
match to anything, or nothing obvious left to do. Each question gives the situation as JSON: why it is asking, the \
objectives the game is showing, the text on screen, what the character is carrying, the last lines of the play log, \
your own earlier answers in this run, and the options. Sometimes there is a screenshot of the camera view; the game's \
on-screen interface may not be in the picture, which is why the on-screen text is listed separately.

Choose the one option a thoughtful first-time player would most plausibly try next: something that moves the current \
objective on, or, when there is no objective, something the bot has not tried. You can only pick from the listed \
options, because those are the only things the bot is able to do. It plays as a player does and cannot set game \
state or skip a step, so do not ask for that.

Things that usually matter:
- What the objective, the latest speech and the on-screen text ask for outranks everything else.
- In a menu, a player tries what the menu is for (planting what they carry, picking an activity, buying when they \
can afford it) before leaving. Leaving is right once the menu has been tried, or when it is in the way of an objective.
- The log and your earlier answers show what has already been done. Repeating something that changed nothing is a \
wasted turn; pick something else.
- When many options are the same kind of thing (dozens of identical plots), one or two tries are enough. Put that \
option's label in `avoid` and the bot will stop offering it for the rest of the run.
- If nothing listed can move the game on, choose the option whose kind is "none".
- Text in square brackets in a label is the object's internal name. Players never see it: use it to tell things \
apart, and do not treat it as wording the game shows. A button whose label is only a bracketed name has no text on it.

`why` is one or two plain sentences written into the test log for a developer. `finding` is for anything a developer \
should hear about that you can see from the situation: an objective that names something a player has no way to find, \
an instruction that contradicts what is on screen, a menu with no way out, an error straight after an action. Raise \
each thing once: `findings_already_raised` lists what you have said in this run, and a finding that is already there \
in other words should be left out. Leave `finding` empty when there is nothing new; most of the time there is nothing."""


def redact(text: str) -> str:
    return KEY_SHAPE.sub("[key removed]", str(text))


def keychain_key(service: str, account: str):
    """The password of a macOS Keychain item, or None. It is returned to the caller and goes nowhere else."""
    if sys.platform != "darwin" or not service:
        return None
    try:
        out = subprocess.run(["security", "find-generic-password", "-s", service, "-a", account, "-w"],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None


def make_client(settings: dict):
    """An Anthropic client, or a stand-in when PLAYTEST_ADVISER_FAKE is set (offline tests only)."""
    if os.environ.get("PLAYTEST_ADVISER_FAKE"):
        return None
    try:
        import anthropic
    except ImportError:
        sys.exit("The adviser needs the Anthropic SDK: pip install anthropic")
    key = keychain_key(settings["adviser_keychain_service"], settings["adviser_keychain_account"])
    if key:
        # a key from the Keychain is an Anthropic API key, so it goes to Anthropic's own address whatever the environment says
        return anthropic.Anthropic(api_key=key, base_url="https://api.anthropic.com", timeout=90.0)
    return anthropic.Anthropic(timeout=90.0)


def schema(option_ids):
    return {
        "type": "object",
        "properties": {
            "choice": {"type": "string", "enum": option_ids},
            "why": {"type": "string"},
            "avoid": {"type": "array", "items": {"type": "string"}},
            "finding": {"type": "string"},
        },
        "required": ["choice", "why", "avoid", "finding"],
        "additionalProperties": False,
    }


def signature(ask: dict) -> str:
    """What makes two questions the same situation: where, why, what is asked for, and what can be done."""
    parts = [ask.get("scene", ""), ask.get("reason", ""), ask.get("menu", ""), "|".join(sorted(ask.get("objectives", []))),
             "|".join(sorted(ask.get("inventory", []))),
             "|".join(sorted(o["kind"] + ":" + o["label"] for o in ask.get("options", [])))]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:24]


def ask_claude(client, settings: dict, ask: dict, folder: Path, history: list):
    """Returns (answer dict, input tokens, output tokens)."""
    import anthropic
    options = ask["options"]
    situation = {key: ask.get(key) for key in ("reason", "scene", "menu", "objectives", "on_screen", "inventory", "recent")}
    situation["your_earlier_answers"] = [{key: value for key, value in item.items() if key != "finding"} for item in history[-12:]]
    situation["findings_already_raised"] = [item["finding"] for item in history if item.get("finding")]
    situation["options"] = options
    content = []
    shot = folder / ask["screenshot"] if ask.get("screenshot") else None
    if shot and shot.is_file() and shot.suffix.lower() == ".png":
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                    "data": base64.standard_b64encode(shot.read_bytes()).decode("utf-8")}})
    content.append({"type": "text", "text": json.dumps(situation, indent=1, ensure_ascii=False)})
    system = SYSTEM
    if settings["app"]:
        system += "\n\nThe game is " + settings["app"] + "."
    if settings["adviser_notes"]:
        system += " " + settings["adviser_notes"]
    request = dict(
        model=settings["adviser_model"],
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": content}],
        output_config={"effort": settings["adviser_effort"], "format": {"type": "json_schema", "schema": schema([o["id"] for o in options])}},
    )
    try:
        # a refusal is re-served by a fallback model inside the same call
        response = client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **request)
    except anthropic.BadRequestError as error:
        if "fallback" not in str(error).lower():
            raise
        response = client.messages.create(**request)  # this key or model has no server-side fallbacks
    usage = (response.usage.input_tokens, response.usage.output_tokens)
    if response.stop_reason == "refusal":
        return {"choice": "", "why": "", "avoid": [], "finding": "", "error": "the model declined to answer"}, *usage
    if response.stop_reason == "max_tokens":
        return {"choice": "", "why": "", "avoid": [], "finding": "", "error": "the answer was cut off"}, *usage
    text = next((block.text for block in response.content if block.type == "text"), "")
    answer = json.loads(text)
    return {"choice": answer["choice"], "why": answer["why"], "avoid": answer["avoid"], "finding": answer["finding"], "error": ""}, *usage


def fake_answer(ask: dict):
    """Offline tests only: the first option, or what PLAYTEST_ADVISER_FAKE names when it is one of the options."""
    wanted = os.environ.get("PLAYTEST_ADVISER_FAKE", "")
    ids = [o["id"] for o in ask["options"]]
    return {"choice": wanted if wanted in ids else ids[0], "why": "stand-in answer, not from a model", "avoid": [], "finding": "", "error": ""}, 0, 0


def write_atomically(path: Path, data: dict):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", type=Path, help="the run's folder (playthrough-LABEL)")
    parser.add_argument("--settings", type=Path, default=None, help="the game's settings file (default: unity-playtest.json in the project)")
    parser.add_argument("--once", action="store_true", help="answer the questions that are there now, then stop (for tests)")
    args = parser.parse_args()

    settings, _ = load_settings(args.settings, find_project(Path.cwd()))
    folder = args.folder
    client = make_client(settings)
    memory_file = folder.parent / "adviser-memory.json"
    try:
        memory = json.loads(memory_file.read_text(encoding="utf-8")) if memory_file.is_file() else {}
    except json.JSONDecodeError:
        memory = {}
    history, asked_model, seen, parent = [], 0, set(), os.getppid()

    def log(line: str):
        with open(folder / "adviser.log", "a", encoding="utf-8") as sink:
            sink.write(time.strftime("%H:%M:%S ") + redact(line) + "\n")

    while True:
        pending = [p for p in sorted(folder.glob("ask-*.json")) if not (folder / p.name.replace("ask-", "answer-")).exists()] if folder.is_dir() else []
        for path in pending:
            try:
                ask = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue  # still being written; it will be whole on the next pass
            target = folder / path.name.replace("ask-", "answer-")
            options = ask.get("options") or []
            answer, tokens_in, tokens_out, source = None, 0, 0, "model"
            # an answer from an earlier run is reused once per run; if the same situation comes round again, it changed nothing
            remembered = memory.get(signature(ask)) if signature(ask) not in seen else None
            seen.add(signature(ask))
            match = next((o for o in options if remembered and o["kind"] + ":" + o["label"] == remembered["option"]), None)
            if not options:
                answer, source = {"choice": "", "why": "", "avoid": [], "finding": "", "error": "the question had no options"}, "none"
            elif match:
                answer, source = dict(remembered["answer"], choice=match["id"]), "memory"
            elif asked_model >= settings["adviser_max_questions"]:
                answer, source = {"choice": "", "why": "", "avoid": [], "finding": "", "error": "the question limit for this run was reached"}, "limit"
            else:
                asked_model += 1
                try:
                    answer, tokens_in, tokens_out = fake_answer(ask) if client is None else ask_claude(client, settings, ask, folder, history)
                except Exception as error:  # the bot must get an answer whatever went wrong, so it can carry on by its rules
                    answer = {"choice": "", "why": "", "avoid": [], "finding": "", "error": redact(type(error).__name__ + ": " + str(error))[:300]}
                chosen = next((o for o in options if o["id"] == answer["choice"]), None)
                if chosen and not answer["error"]:
                    memory[signature(ask)] = {"option": chosen["kind"] + ":" + chosen["label"], "answer": dict(answer, choice="")}
                    memory_file.write_text(json.dumps(memory, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            answer["id"] = ask.get("id", 0)
            write_atomically(target, answer)
            chosen = next((o for o in options if o["id"] == answer["choice"]), None)
            if chosen:
                history.append({"reason": ask.get("reason", ""), "menu": ask.get("menu", ""), "chose": chosen["kind"] + " " + chosen["label"],
                                "why": answer["why"], "finding": answer["finding"] if source == "model" else ""})
            log("%s [%s] %s -> %s%s%s (in %d, out %d tokens)" % (
                path.name, source, ask.get("reason", ""), chosen["kind"] + " " + chosen["label"] if chosen else "no answer",
                ": " + answer["why"] if answer["why"] else "", " ERROR " + answer["error"] if answer["error"] else "", tokens_in, tokens_out))
        if args.once or os.getppid() != parent:  # the runner stops this program when the run ends; stop too if the runner has gone
            return 0
        time.sleep(0.3)


if __name__ == "__main__":
    sys.exit(main())
