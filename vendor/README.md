# Vendor plugin patches

Local fixes to **third-party Mirabox StreamDock plugins** (not part of Drohack's
Tools). These are kept here so the patches aren't lost — the live copies are in
`%APPDATA%\HotSpot\StreamDock\plugins\`, and a plugin update from Mirabox will
silently overwrite them.

Each plugin folder holds the patched file, the pristine original (`.orig`), and
a unified diff (`.patch`).

## Re-applying after a Mirabox update reverts a patch

1. Copy the patched file over the installed one, e.g.:
   `com.mirabox.streamdock.weather.sdPlugin/plugin/index.js` →
   `%APPDATA%\HotSpot\StreamDock\plugins\com.mirabox.streamdock.weather.sdPlugin\plugin\index.js`
   (or apply the `.patch` against a fresh install with `git apply`/`patch`).
2. Restart the StreamDock app (`Stream Controller.exe`).

Verify the file still matches before trusting a stored copy — a Mirabox update
may change surrounding code enough that the patch must be re-derived from the
new original.

---

## com.mirabox.streamdock.weather.sdPlugin — `plugin/index.js`

**Symptom fixed:** the weather key showed "Timeout" and stopped updating after
~3 days idle, needing a manual button press to recover.

**Changes:**
- Added a `scheduleRetry()` helper and call it on every error path in
  `queryWeather` and `queryLocation`. The refresh timer was previously only
  re-armed on success, so a single failed fetch (network blip, PC wake, slow
  API) permanently killed the auto-refresh loop.
- Success-path refresh interval changed from 1 hour to 10 minutes
  (`1000 * 60 * 60` → `1000 * 60 * 10`).

## com.mirabox.streamdock.time.sdPlugin — `index.html`

**Feature added:** 12-hour clock option (the plugin was 24-hour only).

**Changes** (into the minified Vue bundle):
- The hour token now honors a per-button `hour12` setting ("12" default, "24"),
  computed as `getHours() % 12 || 12` for 12-hour.
- Added a **12H/24H** radio row to the World Time action's property inspector.
- The LED seven-segment theme renderer now centers the digits by measured width
  (a shorter 12-hour string like `2:24` was previously left-aligned).
