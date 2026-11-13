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

## Status and licence

Development candidate. The parent method was exercised on Nail Reveal 1.25 on
Android 15 from Linux. This general package has not yet been tested in Claude,
on a second game or on a conventional app. It is not a proven autonomous QA
system, engagement predictor or substitute for player research.

MIT, retaining Copyright (c) 2026 Dynamic Devices. Game assets and third-party
software remain their owners' property. See [provenance](docs/provenance.md).

Assisted-by: Briar
