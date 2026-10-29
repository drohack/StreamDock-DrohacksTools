# Vendor plugin patches

Local fixes to **third-party Mirabox StreamDock plugins** (not part of Drohack's
Tools). These are kept here so the patches aren't lost: the live copies are in
`%APPDATA%\HotSpot\StreamDock\plugins\`, and a plugin update from Mirabox will
silently overwrite them.

Each plugin folder mirrors the installed plugin's layout and holds every patched
file, its pristine original (`.orig`), and a unified diff (`.patch`).

## Re-applying after a Mirabox update reverts a patch

1. Check the installed files still match the `.orig` copies (`cmp`). If they
   do not, the update changed the code and the patch must be re-derived from the
   new original; save the new originals as `.orig` first.
2. Fully quit StreamDock (`Stream Controller.exe`, including the tray icon).
3. Copy the patched files over the installed ones, e.g.
   `com.mirabox.streamdock.weather.sdPlugin/plugin/index.js` ->
   `%APPDATA%\HotSpot\StreamDock\plugins\com.mirabox.streamdock.weather.sdPlugin\plugin\index.js`,
   or apply the diff from inside the installed plugin folder:
   `git apply <this repo>/vendor/com.mirabox.streamdock.weather.sdPlugin/weather.patch`
   (the weather patch uses paths relative to the plugin folder).
4. Start StreamDock.

The original files mix CRLF and LF line endings. Editors that normalize line
endings turn the diff into a whole-file rewrite; keep each untouched line's
original ending so the `.patch` shows only real changes. The repo's
`.gitattributes` marks the plugin folders here `-text` so git stores them
byte-exact instead of normalizing them to LF.

---

## com.mirabox.streamdock.weather.sdPlugin (version 2.0.261019)

Files: `plugin/index.js`, `propertyInspector/action1/index.html`,
`propertyInspector/action1/index.js`, and every language file (`*.json` except
`manifest.json`); diff in `weather.patch`.

This version fetches cities and weather from Mirabox's own gateway
(`weather.key123.vip`, falling back to `weather.miraboxeco.com`); it no longer
carries QWeather or WeatherAPI keys.

**Auto-refresh survives errors.** A `scheduleRetry()` helper is called on every
error path in `queryWeather` and `queryLocation`, retrying after 5 minutes. The
refresh timer is otherwise only re-armed on success, so a single failed fetch
(network blip, PC wake) left the key on "Timeout" until it was pressed. The
success-path refresh interval is 10 minutes instead of 2 hours.

**"None" display option.** The display options (city name / custom title) gain
a third choice, None (`radio` = `"2"`). It draws the weather name and the
temperature into the key image (`drawReading()`) with the temperature sized to
fill the space the city name line used, and sets an empty title. `setTitle`
cannot set a font size, which is why the text is drawn rather than titled. The
drawn text uses the key's title font family and color, and is always bold:
StreamDock draws key titles bold even when the reported style is Regular (checked
against StreamDock's own key preview). The custom-name input shows only for
Custom title.

The new option's label is the Chinese key `无`, with a `"无"` entry added to each
language file's `Localization`. The property inspector replaces every label with
its `Localization` entry and shows `undefined` when there is none
(`static/action.js`), so a label without entries in every language file breaks.

## com.mirabox.streamdock.time.sdPlugin (`index.html`)

**Feature added:** 12-hour clock option (the plugin was 24-hour only).

**Changes** (into the minified Vue bundle):
- The hour token now honors a per-button `hour12` setting ("12" default, "24"),
  computed as `getHours() % 12 || 12` for 12-hour.
- Added a **12H/24H** radio row to the World Time action's property inspector.
- The LED seven-segment theme renderer now centers the digits by measured width
  (a shorter 12-hour string like `2:24` was previously left-aligned).
