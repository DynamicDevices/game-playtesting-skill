# Android execution, capture and recovery — canonical instructions

Select/authorise the phone using [Android setup](android-setup.md), then establish
the app state using [the testing method](method.md). All coordinates/delays below
are placeholders to calibrate in the app profile, not inputs to replay blindly.

## Persistent control connection

Open one managed `adb -s SERIAL shell` process and retain its session handle.
Send finite known batches to the same stdin. Do not share stdin between workers
or submit the next batch before the previous completion marker. Never interpolate
untrusted app text into shell commands. A batch can use this structure after
replacing X/Y with an authorised, calibrated action:

```sh
(input tap X Y)
playtest_batch_rc=$?
printf '\nPLAYTEST_BATCH_001_DONE:%s\n' "$playtest_batch_rc"
```

Use a unique marker per batch, preserve stderr and read through the matching
marker rather than merely the prompt. Chain dependent commands with failure
checks; preserve app-specific settling delays. Missing output is an unknown
partial result, not proof that input did not happen. Android still launches each
`input` command: do not claim a matched latency improvement without measuring it.

## Binary-safe screenshots

Keep PNG bytes out of the control shell/PTY. Use a separate binary-safe capture
connection and a unique destination. On a POSIX shell, where supported:

```sh
adb -s SERIAL exec-out screencap -p > capture-001.png
```

Older PowerShell redirection can corrupt binary output. A device-file/pull route
avoids host binary redirection:

```sh
adb -s SERIAL shell screencap -p /sdcard/Download/playtest-capture-001.png
adb -s SERIAL pull /sdcard/Download/playtest-capture-001.png playtest-capture-001.png
```

Verify the original PNG and its physical dimensions. Any device-file writes
require the intended test device and a unique path; do not overwrite unrelated
files. Accessibility hierarchy dumps are optional and may fail idle detection
or leave stale XML in animated scenes. Use a fresh screenshot after such failure.

## Focused image inspection

Retain the full original but show the region relevant to the next decision:
the complete edited object/edges, all relevant palette choices, or the full dialog
text/options. Inspect the full frame initially, after resumption, on unfamiliar
transitions, unexpected outcomes or suspected overlays. A crop cannot prove
there is no off-crop modal. Expand it whenever missing context could affect input.

For crop `(x0,y0,w,h)` displayed at `(W,H)`, preview point `(u,v)` maps to physical
input `(x0+u*w/W, y0+v*h/H)`. Record the mapping with the capture; recalibrate after
layout/orientation/viewport changes. Prefer an available viewer crop or existing
image runtime; ImageMagick is an optional fallback, not a dependency. Inspect the
original when conversion fails or loses necessary detail. Do not install a daemon
merely to crop. Measure transport, command, conversion and inspection time
separately before diagnosing slow image analysis or claiming a speedup.

## Contact and recording

Baseline input uses `adb -s SERIAL shell input tap X Y` or
`adb -s SERIAL shell input swipe X1 Y1 X2 Y2 DURATION_MS`. Continuous
`input motionevent DOWN`, `MOVE`, `UP` is optional/device-dependent single-pointer
input, not multitouch. Test on a reversible interaction. Start on a verified
interactive region, not a toolbar/overlay. Finish and recover with explicit UP
where supported; if release is uncertain, get human assistance before continuing.
Never leave contact held while reasoning or launching unrelated actions.

Check the device's `screenrecord --help`. Use a supported finite limit and unique
output path; zero/unlimited is not portable. Start as a managed process, confirm
its PID/running state once before input, and stop painting before expiry. Stop
the identified recorder with its supported graceful mechanism (normally SIGINT),
pull the MP4 and verify it opens. Resume input only after the next segment starts.
Keep gaps explicit. Audio capture needs separate justification/permission.

## Fallback ladder

| Optional facility | Failure | Baseline |
| --- | --- | --- |
| Persistent shell | Lost session/marker | Inspect partial effects, then fresh explicit-serial ADB for unfinished actions |
| Batches | Unclear effect/modal/stage change | One verified action at a time, with inspection |
| Continuous contact | Unsupported/uncertain | Release, inspect, then calibrated held swipes |
| Crop/converter | Invalid/incomplete view | Original full PNG; no mandatory image dependency |
| Accessibility dump | Failed/stale | Fresh screenshot |
| Agent image access | Cannot inspect | Human inspection; stop unattended input |
| Unlimited recording | Rejected/stopped | Supported finite segments and disclosed gaps |

These fallbacks keep the same chosen device, authorisation, privacy and dialog
boundaries. If transport/state cannot be restored, stop; do not switch devices,
root, relax security or install privileged injectors. If required recording fails,
pause and ask before continuing without it.

## Recover without duplicate actions

Stop dependent input, save the error/last marker, release held contact through
the working route, and obtain a fresh screenshot. Re-establish actual screen,
tool, modal, content and recorder state. Resume only unfinished actions using
the supported baseline. Never repeat an uncertain purchase, completion, palette
toggle or whole partly executed sequence just because its marker was lost.
Inspect the recovered result and record the failed speedup/fallback. Do not retry
an unchanged failure or turn completion reads into an autonomous polling loop.

The baseline method has Android/Linux source evidence; injected disconnect,
recorder-limit recovery, Windows and other-device compatibility remain untested.
Keep app-specific observations in the originating profile, not in this generic
procedure. Adapted from the MIT-licensed `nail-reveal` skill by Dynamic Devices.
Assisted-by: Briar.
