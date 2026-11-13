# Worked example: Nail Reveal

This example is derived from the public
[Nail Reveal skill](https://github.com/DynamicDevices/nail-reveal-ai-skill)
and its recorded tests. The study candidate is available at
[source revision 4830f785](https://github.com/DynamicDevices/nail-reveal-ai-skill/tree/4830f7855cfedd641d48efce600435fecaa5cdc2).
Keep game-specific reproduction data there; this package does not duplicate the
large recording collection or relicense game assets.

## What transfers

The tested environment was Nail Reveal 1.25, Android 15, a 1080×2400 phone and
Linux ADB. Experiments compared point holds and movement, then examined the
result rather than assuming what tool icons meant. A drill removed both applied
coats; a file/buffer did not erase the tested dots. The Cone Bit later worked
in a preparation stage, which did not establish polish-erasing behaviour.

These observations show why an app profile needs a stage as well as a tool:
“tidy the base” and “erase this painted mark” are different tests. The general
skill owns that distinction; the app-specific skill owns actual tool positions,
test timings and recreation recipes. None of those constants transfers blindly.

Continuous contact and a persistent input shell were useful optional speedups.
Focused image crops reduced the region needing attention, but original captures
and coordinate mappings remained necessary. Held contact was released before
inspection. Uncertain partial batches were inspected rather than replayed.

## What the failures teach

Masking with background colour could leave halos; a clean editing closeup did
not prove the design fit the actual Hand projection. Later work therefore
checked the real Hand before accepting silhouette extensions. Completion scores
and a ledger of changes were not substitutes for visual quality.

The study recorded twenty glazed single-nail outcomes and 100 accepted-change
entries, but outcomes were uneven and several starting motifs were unfinished.
Five complete-hand sets remained unstarted at an ad gate. No ad or purchase was
accepted. These are important limits, not results to hide in a generic success story.

## Example developer feedback — proposals, not player evidence

Observation: the tools' effects differed by stage, and progression changed the
available tools. Hypothesis: a new player may struggle to understand whether a
tool can remove colour or only prepare the nail. Possible comparison: show a
contextual preview/label versus the existing interface, then ask real players to
choose the right tool for an explicit task. Do not infer retention from an
agent choosing correctly after reading the skill.

A more imaginative alternative is an optional free-play tool-discovery challenge
with several valid artistic outcomes. It could improve expression or become an
unwanted interruption; start with a cheap prototype and player feedback. Neither
proposal has been tested or requested as an app code change.
