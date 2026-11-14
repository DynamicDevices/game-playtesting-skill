# Input, inspection and fallback adapters

The method is platform-neutral; the actual tool must exist in the agent's
environment. Confirm supported operations before use. Never install privileged
injectors, change security settings or attach an unrelated device as a workaround.

## Android with ADB

Use [Android setup](android-setup.md) and [execution/capture/recovery](android-execution.md).
Those are the canonical procedures for authorisation, explicit targeting, binary
capture, finite batches, contact release, recording and the fallback ladder.
App-specific skills link to them instead of keeping copies; calibrated app data
belongs in the app profile. No separate setup procedure is maintained here.

## Unity game in the editor

For a developer-authorised Unity project, a play-mode bot can play inside the
editor with no window or screen control. Use [the Unity in-editor adapter](unity-in-editor.md)
for run questions, checkpoints, stop conditions, stall diagnosis and session
records. It was used live on one game on macOS only.

## Browser, desktop and iOS

For a browser use the available authorised browser controller. Prefer roles,
labels and stable locators; record viewport and navigation state. Canvas input
still needs screenshot/landmark calibration. Browser DOM success is not proof
that a canvas animation or sound was correct.

For desktop apps use the environment's supported accessibility/input interface.
For iOS use a developer-provided, authorised simulator/test interface if available.
ADB is not an iOS adapter. If no suitable input or image tool exists, stop at
manual test instructions and mark execution not run. These adapters have not
been validated live by this project.

## Portable baseline

Use existing supported input calls, original full screenshots and explicit
expected/actual checks. When cropping, persistent connections, recording or
accessibility queries fail, preserve that failure and use the available baseline.
Manual assistance is an honest fallback; it is not autonomous execution.

Record the host OS and actual adapter. Linux, Windows and macOS require their
own validation; describing fallback logic does not establish compatibility.
Screen recording is optional evidence: confirm supported duration and successful
startup once, stop before its limit and disclose gaps. Avoid audio capture unless
needed and separately authorised. Keep raw captures private; inspect before sharing.
