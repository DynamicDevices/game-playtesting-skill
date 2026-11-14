# Unity in-editor adapter

For a Unity game whose developer lets you open the project on a computer you
control. A play-mode test drives the game inside the editor with no window, so
no screen or input device is controlled and no screenshot of the desktop is
involved. It answers "can a player get from here to there by playing", cheaply
and repeatably. It does not replace screenshot-grounded checks of what a person
sees, hears and can reach. Read [adapters](adapters.md) for the other platforms.

Status: used live on one Unity 6 desktop game, on macOS, with one editor build,
over about twenty runs. Windows and Linux are described, not run. Nothing here
is evidence for another game until you have tried it. Game-specific controls,
quest routes and timings belong in that game's app profile or skill.

## Agree the boundaries first

Use a developer-authorised local project. Never point the bot at a production
build, a live account or a store purchase. Turn analytics and online services
off, or confirm they are off, and say how you know. Do not activate a user trial
or sign-in that sends data to a live environment. The bot never deletes saved
games, changes game code or checks anything in; those need separate approval.

## What the bot may do

The bot plays as a player does: it calls the game's own input layer, presses
buttons that are on screen, moves with the same stick or keys a player has, uses
what the game lets the player select, and picks conversation and menu answers.
It never sets a variable, gives an item, loads a scene or skips a step. If it
cannot get past something by playing, that is the result, and it is either a
finding about the game or a missing rule in the bot. Decide which before
reporting (see "Stalls" below). Answer yes/no questions with the safe option
unless the experiment is about the other one.

Test for "usable" the way the game does, not by one component. In the project
this was developed on, a thing could be usable with its interaction component
disabled. Active object, enabled collider and the layer the game raycasts
against were the checks that matched what a player could do.

Menus that take over the screen lock movement. A bot with no rule for a menu
sits in it forever and looks like a hang. Give it each menu's own exit, give
ratings and questions a policy, and stop the run with a named reason when a menu
holds it too long.

## Ask a question, stop when it is answered

A full play-through is the expensive way to test one step. Write the question and
the log line that would answer it before the run, then end the run when that line
appears:

1. The bot appends one line per event to a play log (state changes, menu opens,
   objectives, conversation lines, errors, an end-of-run summary).
2. A run takes `--until "<text>"` (repeatable). It stops shortly after every text
   has appeared, ignoring its own settings line so it cannot match itself.
3. The runner prints a report and exits non-zero if an expected line is missing,
   a new error appeared, a menu held the bot, or the run paused.

A play-mode test framework reports `Passed` whatever the bot found. The verdict
is the report and exit code, never the test result. A run with no question ends
by itself when nothing new has happened for several minutes.

## The scripts and what the bot must do

Three scripts in `scripts/` do the parts that are the same for every game. They
need Python 3.9+, and the Unity command line or the editor program.

- `unity_playtest.py LABEL [--until TEXT] [--fresh | --from-checkpoint NAME] [--save-checkpoint NAME]`
  runs the bot, keeps and restores checkpoints, tidies the workspace (Plastic
  SCM or git) and prints the report.
- `unity_playtest_report.py RUN [--expect TEXT]` turns a play log into the
  report, the exit code and a session record.
- `unity_playtest_coverage.py` adds runs up into what has and hasn't been tried.

The game's details go in one settings file, `unity-playtest.json`, in the
project folder (or `--settings`). Start from [the template](../assets/unity-playtest.json):
the game's name, Unity's Company and Product names (they locate the saved
games), the bot's test name, the scenes that come before the game proper, and
optional files of known errors and of every scripted sequence.

The bot is the game's own play-mode test; this skill does not supply one,
because how to press a button or walk is different in every game. It must:

- read `PLAYTEST_LABEL`, `PLAYTEST_RUN_FOLDER`, `PLAYTEST_MEMORY`, and when set
  `PLAYTEST_UNTIL` (texts joined with `||`), `PLAYTEST_MINUTES` and
  `PLAYTEST_IDLE_MINUTES`;
- write `playthrough-<label>/progress.txt` as it goes and `playthrough.txt` at
  the end, in the run folder, with any screenshots beside them;
- write one event per line as seconds, two spaces, a tag, then text:
  `  12.3  VAR    TutorialComplete = True`.

Tags the report understands, all optional: `SETUP` (the bot's settings),
`SCENE now <name>`, `VAR`, `OBJ`, `USE`, `SAY`, `PICK`, `CHOOSE`, `RATE`,
`INV+`/`INV-`, `BEGIN`/`END` (a scripted sequence), `MENU <name> is open`,
`MENU+`, `MENU-`, `LEAVE <name>`, `GOAL nothing usable matches`, `STUCK short of <name> by <n>m`,
`STALL?`, `PAUSE`, `ERROR` and `DONE <why the run ended>`. Sections after the
events start with `=== `: `FINAL VARIABLES`, `HOTSPOTS` (one line per
interactive thing: `used N` or `never`, `on` or `off`, label, object name,
place, and why it could not be reached, separated by ` | `) and `ERRORS`
(`3x <text>`).

The scripts were run live as part of one game's own skill before being made
general. In this general form they have been run only against a stand-in editor
and synthetic logs in this repository's offline tests.

## Checkpoints

Keep saved games as named checkpoints so a later step starts in minutes, not
after replaying everything before it. A checkpoint is the game's own save folder
plus any memory the bot keeps, copied to a folder outside the project.

- Restoring a checkpoint or starting a new game moves the live save aside as a
  new checkpoint. Nothing is deleted. Ask the owner first on a machine where the
  game is also played for real.
- Save a checkpoint only after a run whose report is clean and whose expected
  lines appeared. A checkpoint from a false start misleads every later run.
- Label each with what it contains (quest flags set) so you can choose one.

Let the bot remember places it has used in earlier runs of the same save and
prefer new ones, otherwise it keeps going back to the nearest thing.

## Keep the machine and workspace steady

A computer that sleeps freezes the editor and the run looks like a game hang.
Keep it awake for the run (`caffeinate` on macOS) and log a `PAUSE` line if the
test loop ever stops for longer than a normal long step; distrust such a run.

Opening a project can rewrite many asset files (materials, render pipeline
settings). Undo only the kinds of file the editor rewrites, and report anything
else the runner left alone, so you never revert the developer's own edits. Do
not check the rewrites in. Changing the bot's source during a run has no effect
on that run; the editor compiled it at the start. Close the project in the
editor first, or use a second copy.

## Reading results

Read the report first, then the play log, then screenshots only where the report
points. Screenshots from a headless run are camera renders without the interface
layer. Log the on-screen text with each one so you can compare it with the
game's own text rather than with the bot's internal strings.

Useful sections at the end of a log: final variables and inventory; every
interactive thing with how often it was used and why it was or was not reachable;
the scripted sequences that started; and every error with its time. A coverage
script that adds runs up shows what has never been tried, which is a better
guide to the next test than the last run.

Record known errors in a list the report treats as `[known]` so they neither
fail every run nor hide new ones. Remove a line when its cause is fixed.

## Stalls

Ask whether a player could get past it with what is on screen.

| The log shows | Likely | Do |
| --- | --- | --- |
| Held by a menu, with its button names | The bot has no rule for it | Add the rule |
| The objective names something switched off | The game has not enabled it | A finding, unless an earlier step was skipped |
| The objective names nothing that exists | The text is in other words or another scene | Read the speech before it; often a finding about the text |
| No walkable route, or the route stops short | Blocked on purpose, or a gap in navigation | Find which |
| Nothing new for several minutes | The bot is circling | Give it a reason to go elsewhere, or accept the run is finished |
| An error straight after the bot used something | The bot may have used it in a way a player cannot | Check before reporting |

Teach the bot in small steps: start from the checkpoint just before the problem,
change one rule, run until the line that proves it, then rerun a short
regression (a new game through the early tutorial steps) in case the rule broke
an earlier one.

## Session records

Write a run in the [session record](../assets/session.json) format with
`record_kind: observed`. One step for the health of the run (no new errors, no
pause, no menu left open) and one per expected line, each with the play log and
the last screenshot as evidence. A step is `pass` only if its line appeared and
the report was clean. The validator checks structure, not truth.

## Fallbacks

Use the best available rung and say which one you used: the Unity command line,
the editor program with its batch flags, the editor open on a human's machine
with a human watching a run, a human playing a step that needs real input or
sound. If you cannot run a shell or read screenshots, say so and give the human
the commands.

## Not covered

Sound, frame rate and stutter, the look and legibility of the interface, real
keyboard, mouse, gamepad or touch input, device-specific behaviour, built
players, other operating systems, and anything a person would feel. A bot that
reaches the end of a quest says the quest can be completed, not that it is
understandable or enjoyable. Report possible disengagement as hypotheses with a
way to check them, not as findings.

Assisted-by: Claude (Anthropic)
