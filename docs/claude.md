# Using the skill with Claude

This is a plain Agent Skills package, not a Claude-specific automation service.
Installation and device access are different tasks. This project has not yet
verified a live Claude session; use the acceptance exercise below to find gaps.

## Claude Code

In your own project, copy the complete `skills/app-playtesting` folder into
`.claude/skills/app-playtesting`. Its `SKILL.md`, `references/` and `assets/` must
remain together. Follow your installed Claude Code version's skill-loading
instructions and confirm the skill is available. Keep Nail Reveal's separate
skill alongside it only when testing that game. Do not copy this repository's
`.git` directory, private sessions or credentials.

The package does not depend on Codex, Briar's local skills, Node or an always-on
daemon. Claude Code still needs your permission and working tools to control the
chosen test environment and inspect images. Start with the standard tool route
you already trust; this package does not ask you to relax tool permissions.

## Claude Desktop or another Claude environment

If the product supports user-uploaded skills, follow its current import procedure
for this folder. Do not assume it exposes your local shell, ADB, USB or browser.
If it only supports file/image conversation, supply the skill and screenshots
and ask for a human-operated test plan. Mark input execution as manual/not run
as appropriate. Browser, remote and mobile capabilities vary by product/version.
No Claude account, paid API key or connector is created by these instructions.

## First-session acceptance exercise

Use an authorised debug build/test account and one reversible task. Ask:

> Use app-playtesting to investigate one unfamiliar control. First confirm your
> input and image capabilities, identify the current state and tell me the
> experiment. Test one variable, release input, inspect the result and record
> expected versus actual behaviour. Stop at ads, purchases or uncertain dialogs.
> Report observations separately from explanations. Suggest one friction fix
> and one genuinely different feature idea, labelled as untested proposals.

Observe whether Claude actually loaded the references, inspected a real image,
targeted the correct environment, respected the stopping boundaries and retained
reproduction evidence. Then test an unavailable optional speedup and verify it
returns to the supported baseline without replaying uncertain actions.

Record the Claude product/version, host OS, adapter, app/build and pass/fail/gaps.
Do not call the installation validated merely because Claude can quote the skill.
Use [the cross-app plan](validation.md) before claiming generalisation.
