# What is proved and what needs trying

The source method was exercised on Nail Reveal 1.25 / Android 15 / Linux ADB.
The adapted generic package has not been exercised live on any app or in Claude.
Offline tests validate content and record handling, not end-to-end interaction,
player engagement, the quality of suggestions or cross-platform compatibility.

## Proposed validation, not completed work

1. Run the [Claude first-session exercise](claude.md) on Nail Reveal. Check real
   screenshots/input, a controlled tool experiment, unexpected-dialog stopping,
   reset/restoration and honest reporting. Do not buy or accept an ad to pass.
2. Try a second developer-authorised 2D game with a different mechanic. Begin
   without a bespoke coordinate script. Record discoveries and needed app-profile
   additions. Check that Nail Reveal assumptions do not leak into the test.
3. Try a conventional app on a test account: create/edit/save a disposable draft
   or another authorised reversible task. Check state transitions, saved results,
   keyboard/input behaviour and failure recovery.
4. Repeat the relevant capability and fallback checks for each claimed OS/adapter.
   Simulated missing features can test decisions; they do not prove the real
   platform works. Keep manual intervention and recording gaps explicit.
5. Ask the developer whether the bug report was reproducible and the proposals
   were useful. Separately approved real-player work is needed for engagement
   conclusions. Preserve failed or inconclusive trials and revise the method.

For each run retain the skill revision, app/build, agent/product, platform,
starting state, criterion, actual result, evidence and limitations. A record of
three runs is not enough by itself: assess the relevant criteria and explain gaps.
Do not run this plan on real devices/users without their required authorisation.
