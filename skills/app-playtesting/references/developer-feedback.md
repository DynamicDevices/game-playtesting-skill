# Feedback a developer can act on

Keep four categories distinct:

- **Bug:** expected behaviour is grounded in the brief, specification or a
  demonstrated invariant; actual behaviour differs. Include build, preconditions,
  reset, exact steps, evidence, impact and reproducibility.
- **Usability observation:** describe an observable obstacle, such as an
  unlabelled tool or absent confirmation. Separate it from a proposed explanation.
- **Disengagement hypothesis:** identify a moment that may lose a player's
  interest, and explain why. An agent's hesitation is not evidence that people
  quit, get bored or fail to understand the interface.
- **Creative proposal:** offer a new experience or feature. Explain the player
  benefit, fit with the game, a small prototype and possible downsides.

Do not inflate severity: show the effect and affected task rather than guessing
frequency. Distinguish crashes/data loss, blocked tasks, recoverable friction and
cosmetic issues. State unknown reach and reproduction rate. An intentional ad or
purchase gate can be a design concern without being a software defect.

## Find possible points of disengagement

Review the journey around first understanding, first successful interaction,
repetition, challenge, reward, waiting, failure and recovery. Ask:

- Does the player know what they can try and see a meaningful response?
- Is a repeated action an enjoyable mechanic, practice, or avoidable labour?
- Does failure teach something, and can the player recover without excessive replay?
- Is there room for choice, expression, surprise, mastery or discovery?
- Are interruptions or unclear progress likely to break the experience?

Record a timestamp/screen and the observed mechanics. Label interpretations as
hypotheses. Human observations and separately approved analytics may support or
contradict them; keep their source and sample limitations explicit. Do not invent
player quotes or treat the agent as a representative player population.

## Go beyond friction fixes

When creative feedback is requested, explore distinct directions: expressive
freedom, progression/mastery, playful surprises, optional challenges, accessibility
and different play styles. Preserve the intended audience and core fantasy.
Do not add social features, monetisation or complexity by default.

For a painting game, possible prototypes include a free-play canvas with no
client score, a themed challenge with several valid solutions, or a tool that
reveals a surprising interaction. These are proposals, not tested improvements.
Offer a cheap sketch/mock-up before a production feature and identify what would
disprove the idea. Keep at least one deliberately different alternative to avoid
reducing every improvement to button placement or a shorter tutorial.

Prioritise findings using evidence, player impact, uncertainty and effort—not
invented numerical precision. Separate “fix now”, “investigate” and “prototype”.
Use [experiment planning](experiments.md) and the [report template](../assets/developer-report.md).
