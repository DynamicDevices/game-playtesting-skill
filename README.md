# Game and app playtesting skill

Help an agent learn an unfamiliar game, test it carefully and give a developer
useful feedback. Designed with Jon's 2D-game playtesting needs in mind, and
derived from Alex and Briar's [Nail Reveal experiments](https://github.com/DynamicDevices/nail-reveal-ai-skill).

The aim is a reusable way of investigating an app, not a script for one game.
The agent observes the current screen, tests one uncertainty, checks the outcome
and records enough evidence for someone else to reproduce it. It can also
suggest where players might disengage and propose imaginative new experiences.
Those suggestions are hypotheses, not evidence of real-player engagement.

## Start here

1. Read the [general skill](skills/app-playtesting/SKILL.md).
2. For Claude, use the [installation and first-session guide](docs/claude.md).
3. Make a small app profile using the [template](skills/app-playtesting/assets/app-profile.md).
4. Start with one reversible interaction. Record a test using the
   [session template](skills/app-playtesting/assets/session.json), then follow
   the [developer-report template](skills/app-playtesting/assets/developer-report.md).

No daemon, paid model service or agent vendor is required by this repository.
An agent still needs actual device/browser input and screenshot tools; a skill
does not give Claude Desktop, Claude Code or any other agent those capabilities.

## What is included

- [Controlled exploration and state-based testing](skills/app-playtesting/references/method.md).
- [Portable device/browser adapters and fallbacks](skills/app-playtesting/references/adapters.md).
- Canonical [Android setup](skills/app-playtesting/references/android-setup.md) and
  [execution/capture/recovery](skills/app-playtesting/references/android-execution.md)
  for companion skills to require rather than duplicate.
- [Unity in-editor adapter](skills/app-playtesting/references/unity-in-editor.md): scripts
  that run a game's own play-mode bot with no window, keep saved-game checkpoints
  and report with an exit code. The bot can optionally ask Claude what to try.
- [Bugs, usability, disengagement and creative suggestions](skills/app-playtesting/references/developer-feedback.md).
- [Experiment and A/B-test planning](skills/app-playtesting/references/experiments.md).
- [Optional developer debug-build interface](skills/app-playtesting/references/debug-builds.md).
- [Nail Reveal worked example and provenance](examples/nail-reveal.md).
- [Cross-app validation plan and honest limits](docs/validation.md).

## Check the working

Python 3.9+ is needed only for the optional offline checks, not to read the skill:

```sh
python3 -B -m unittest discover -s tests -v
python3 -B scripts/validate_session.py skills/app-playtesting/assets/session.json
```

The supplied JSON is a synthetic, unexecuted template. A validator pass checks
record structure and local evidence references, not app behaviour or test quality.
Copy it into your private session directory before filling it in. Screenshots,
logs, player data and recordings stay private unless separately approved for
sharing. This repo does not collect telemetry or run live user experiments.

## Optional: an API key for the Unity bot's adviser

Nothing in this repository needs a key unless you run the Unity scripts with
`--adviser`. That option lets the bot ask Claude what a player would try when
its rules run out. It sends each question's text and a screenshot to the Claude
API and is charged to the key's account, so use it only with the game
developer's agreement. Without `--adviser` nothing leaves the computer.

1. Install the SDK the adviser uses: `pip install anthropic`.
2. Create an API key in the [Claude Console](https://platform.claude.com/) under
   API keys. Usage is billed to that organisation.
3. Give the key to the adviser in one of these ways. Do not put it in
   `unity-playtest.json`, a script or anything that is committed.

   - **Environment variable (any system).** Set it in the shell that starts the
     run. The Anthropic SDK reads it; its other standard credential sources work
     too.

     ```sh
     export ANTHROPIC_API_KEY="paste-the-key-here"
     ```

   - **macOS Keychain.** Store the key once; the command asks for it, so it is
     not left in your shell history:

     ```sh
     security add-generic-password -U -s "Playtest adviser (Claude API key)" -a playtest -w
     ```

     Then name that item in the game's `unity-playtest.json`. Only the item's
     name is stored there, never the key:

     ```json
     "adviser_keychain_service": "Playtest adviser (Claude API key)",
     "adviser_keychain_account": "playtest"
     ```

     When a Keychain item is named and found, it is used in preference to the
     environment variable. macOS may ask once to let `security` read it.

4. Run with the adviser and check it worked:

   ```sh
   python3 skills/app-playtesting/scripts/unity_playtest.py try-1 --adviser --minutes 5
   ```

   The run's folder then has `adviser.log` with one line per question: what was
   chosen, why, and the tokens used. If a line there says `no API key was found`
   or `the API key was refused`, the key did not reach the adviser or is wrong;
   the bot carries on by its rules and stops asking after three failures.

The same settings file chooses the model (`adviser_model`), how hard it thinks
(`adviser_effort`) and the most questions per run (`adviser_max_questions`); see
the [Unity in-editor adapter](skills/app-playtesting/references/unity-in-editor.md).
The key is read when a run starts, passed to the SDK, and never written to a
log or a file. Remove a Keychain item with
`security delete-generic-password -s "Playtest adviser (Claude API key)" -a playtest`.

## Status and licence

Development candidate. The parent method was exercised on Nail Reveal 1.25 on
Android 15 from Linux. This general package has not yet been tested in Claude,
on a second game or on a conventional app. The Unity in-editor adapter is the
exception: it was run live on one Unity 6 desktop game on macOS. It is not a proven autonomous QA
system, engagement predictor or substitute for player research.

MIT, retaining Copyright (c) 2026 Dynamic Devices. Game assets and third-party
software remain their owners' property. See [provenance](docs/provenance.md).

Assisted-by: Briar
