# Optional developer-owned debug-build interface

These are recommendations for Jon or another app developer, not hooks already
implemented in Nail Reveal. The skill works without them. Adding app code needs
its own requested development work and review.

Useful capabilities are: reset to a named checkpoint, set a deterministic seed,
read build/screen/state identifiers, inspect named interactive objects and capture
a bounded input/event trace. Expose only what is necessary to explain a test.
Keep personal data, credentials, production accounts and arbitrary code execution
out of the interface.

A proposed read-only state snapshot might be:

```json
{
  "schema": "playtest-debug-state/v1",
  "build": "developer-build-id",
  "screen": "colour-editor",
  "checkpoint": "clean-canvas",
  "seed": 42,
  "viewport": {"width": 1080, "height": 2400, "orientation": "portrait"},
  "objects": [
    {"id": "palette.open", "role": "button", "label": "Colours",
     "bounds": {"x": 180, "y": 2140, "width": 100, "height": 100}}
  ],
  "modal": null
}
```

Bounds use physical screenshot pixels in this example; implementations must
state their coordinate space and scaling. Object/state identifiers aid targeting
but do not prove the object is visible, reachable or understandable to a player.
Compare internal state with screenshots and actual input results.

Reset and seed changes are separate, explicitly mutating operations. Require a
developer-authorised local/simulator or test-device build, a test session and a
known checkpoint; return the resulting build/state and verify it visually. Refuse
production or unknown builds. Do not use a reset to bypass purchases, consent or
normal access restrictions, and do not erase a real user's progress.

Prefer the app framework's existing test interface. Keep transport local or
otherwise authenticated and explicitly authorised. Keep the interface absent or
disabled in release builds, with an automated release check. Redact logs and
bound their duration. A debug interface can itself introduce security risk: it
is not a reason to ship an unrestricted remote command console.
