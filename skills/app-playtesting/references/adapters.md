# Input, inspection and fallback adapters

The method is platform-neutral; the actual tool must exist in the agent's
environment. Confirm supported operations before use. Never install privileged
injectors, change security settings or attach an unrelated device as a workaround.

## Android with ADB

The owner enables debugging and authorises the selected phone. Privately identify
it with `adb devices -l`; pass its explicit serial on every command. Never publish
serials. Baseline operations include `adb -s SERIAL shell input tap X Y` and
`adb -s SERIAL shell input swipe X1 Y1 X2 Y2 MILLISECONDS`. These are examples,
not a queue to execute or proof that a long swipe simulates every contact gesture.

Capture original PNG bytes using `adb -s SERIAL exec-out screencap -p` through
a binary-safe process API or transport. Text pipelines can corrupt binary data,
particularly on some Windows shells. Verify the PNG and inspect it. If capture
fails, use an available supported screenshot route or ask for a manual screenshot.

A persistent control shell, finite batches and continuous contact are optional
optimisations. Test device support on a reversible interaction. Use a separate
capture connection; preserve command boundaries and completion markers. Release
contact explicitly on success and failure. After transport loss, inspect partial
effects before reverting to individual ADB calls. Do not launch competing input
streams or assume parallel swipes implement multitouch.

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
