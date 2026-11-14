# Android setup — canonical instructions

The human must own the test phone or have permission to control it. ADB gives
powerful access: approve only a trusted computer and revoke temporary USB
debugging authorisation afterwards. The agent needs a shell/process tool and
image inspection. If either is absent, use human-operated instructions and mark
execution accurately; installing a skill does not supply missing tools.

## Install ADB

Use Google's [Android SDK Platform Tools](https://developer.android.com/tools/releases/platform-tools)
or a trusted distribution package, not an unknown ADB bundle.

On Linux, have the owner install the distribution's `adb` package or unpack
Google's Platform Tools. Use the extracted executable's actual path and check
`adb version`. Keep administrator passwords out of chat. For device permission
errors, use the distribution's Android/udev guidance; do not run ADB as root or
broadly relax USB permissions.

On Windows, extract Google's Windows ZIP. In PowerShell:

```powershell
$PlaytestAdb = 'C:\Tools\platform-tools\adb.exe'
& $PlaytestAdb version
& $PlaytestAdb devices -l
```

Replace the path with the actual extraction directory. Follow the device maker's
official USB-driver guidance where needed; do not disable driver signing or
security protections. Windows setup is documented, not live-validated here.

## Authorise the intended phone

Have the owner install/open the intended test app through an approved route.
On most Android devices, tapping Build number seven times enables Developer
options; exact locations vary. The owner enables USB debugging, connects an
unlocked phone with a data-capable cable, and approves only the expected trusted
host/fingerprint. Never bypass the prompt. Use File transfer mode if the device
requires it. Inspect `adb devices -l` and explicitly select the intended device.
Keep its serial private and pass it on every command. Never silently switch phones.

`unauthorized` needs owner approval; `offline` indicates a transport problem.
An empty list may mean cable, port, driver or permissions. Diagnose the observed
cause instead of blindly restarting. Wi-Fi pairing, root, data clearing or app
reinstallation is not a baseline requirement and needs its own authority.

```sh
adb -s SERIAL get-state
adb -s SERIAL shell getprop ro.product.model
adb -s SERIAL shell wm size
adb -s SERIAL shell pm path APP_PACKAGE
```

Substitute the private selected serial and actual package. In PowerShell use
`& $PlaytestAdb` instead of `adb`. Inspect a fresh full screenshot before input:
installation/transport success does not establish app state. Use
[execution and capture](android-execution.md) for binary-safe screenshots,
recording and fallbacks. Keep build-specific coordinates in the app profile.

Adapted from Dynamic Devices' MIT Nail Reveal setup. Assisted-by: Briar.
