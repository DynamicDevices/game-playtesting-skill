# Contributing

Use a development branch and explain the playtesting problem, proposed change,
evidence, checks and untested boundaries. Keep skill instructions short; put
details/examples in linked references bundled inside the installable skill.
Keep game-specific constants in app profiles or dedicated skills.

Run `python3 -B -m unittest discover -s tests -v` and validate a synthetic/template
session with `python3 -B scripts/validate_session.py skills/app-playtesting/assets/session.json`.
Do not add device-driving tests to offline discovery. Do not submit credentials,
personal data, private recordings or other people's game assets. Clearly label
synthetic examples, hypotheses and proposed interfaces. Material skill changes
also need a static skill scan and the repository's applicable review gates.

Sign commits using your approved signing setup. Disclose agent assistance using
an `Assisted-by:` trailer and visible PR disclosure, not an AI co-author identity.
Alex retains manual merges. Missing review integration is a reported gap, never
a reason to create a green status, bypass review or invent another review flow.
