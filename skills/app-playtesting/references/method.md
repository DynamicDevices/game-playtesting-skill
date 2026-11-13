# Controlled exploration and regression testing

## Learn the app, not a coordinate script

Start with a full-screen view and a bounded task: for example, find the first
playable level, understand one drawing tool, or save a draft. Record named states
and evidence for transitions. Do not assume a rotating hint describes the actual
stage. A loading screen, modal, success screen and editable canvas are different
states even if some controls share coordinates.

A useful action description is:

> Given the colour editor is visible and no modal is open, open the palette.
> Verify the swatches appeared. Select the labelled blue swatch, or the calibrated
> landmark if there are no accessible labels. Verify the selected colour changed.

An executable coordinate is adapter data, not a general instruction. Bind it to
the build, viewport, orientation and screenshot. Record crop offsets and scales
when translating inspection coordinates to physical input. Recalibrate after
resizing, rotation, scrolling or layout changes; proportional scaling alone is
not proof that the same control remains there.

## Characterise an unknown interaction

Write one question and a prediction. Establish a baseline and reset method,
then change one variable. For a brush, compare a short tap, a held point and
movement with similar duration. Examine whether it reacts on DOWN, continuously,
on movement or on UP. For a button, test ordinary activation before long press.
Use inputs appropriate to the app; do not poke unknown destructive controls.

Record requested duration separately from measured elapsed time. Frame rate,
input transport and animation can affect an apparent threshold. Repeat only
when variation affects the conclusion and the repetition is authorised; a single
observation is not a universal minimum or performance benchmark.

## Keep speed subordinate to evidence

Reuse one input connection for finite known batches when supported. Separate
binary screenshot capture from a text shell. Reuse a cropper/runtime if it is
already available, rather than starting a converter for every frame. No persistent
Node/Python daemon is required. If a speedup fails, release contact, inspect the
actual state and resume with a supported baseline. Never replay a whole batch
solely because its final marker was lost.

Inspect a small region for a known local effect; use the full view for state
discovery and surprises. Save the original, crop rectangle and display scale.
If the crop misses a dialog or quality defect, return to the original. A smaller
image can reduce inspection work; do not claim a timing saving without measurement.

## Acceptance and failures

Define acceptance before the change: correct saved content, a visible response,
a contained drawing edge, readable instructions or successful task completion.
Use multiple views when the game projects the same work onto another surface.
Scores, animations and counters cannot substitute for the relevant observation.

Keep a parent/baseline and record rejected variants with their reasons. Restore
the actual app state before testing another candidate; a reference image is not
a reset. Do not prescribe a fixed number of improvements or force weak changes
to count. A significant improvement needs a stated criterion and comparison.

For regressions, preserve build identity, fixture, seed/checkpoint where available,
input sequence, expected/actual outcome and evidence. Test changed behaviour and
nearby failure/recovery paths. Do not turn a content check or a simulated example
into a claim that the real app passed.
