# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Windows-only StreamDock (Mirabox) plugin — "Drohack's Tools" — built on the official Python SDK example. It provides button/knob actions: system Volume, per-app Volume (pycaw), and a Gif player. There is no test suite.

## Commands

```powershell
# Setup (once)
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Build the plugin exe (output: dist/DrohackPlugin.exe)
pyinstaller main.spec
```

Deploy: copy `dist/DrohackPlugin.exe` into `com.drohack.streamdock.tools.sdPlugin/`, then copy that whole folder to `%APPDATA%\HotSpot\StreamDock\plugins\`, and restart StreamDock.

The plugin cannot be run standalone — StreamDock launches the exe with `-port -pluginUUID -registerEvent -info` args and the plugin connects back over WebSocket. Debug via the log file: `logs/plugin.log` (next to the repo root in dev, next to the exe when deployed).

## Architecture

Two halves that ship together in the `com.drohack.streamdock.tools.sdPlugin/` bundle:

1. **Python backend** (`main.py`, `src/`) — compiled to `DrohackPlugin.exe` with PyInstaller.
2. **Plugin bundle** (`com.drohack.streamdock.tools.sdPlugin/`) — `manifest.json` (declares actions/UUIDs), per-action HTML/JS property inspectors, and static assets. The JS runs inside StreamDock's webview, not in Python.

### Backend event flow

- `src/core/plugin.py` — `Plugin` owns the WebSocket to StreamDock. On `willAppear` it creates one `Action` instance per button context via `ActionFactory`; all later events (`keyUp`, `dialRotate`, `didReceiveSettings`, `sendToPlugin`, …) are dispatched to that instance by duck-typed handler names (`on_key_up`, `on_dial_rotate`, `on_send_to_plugin`, …) — handlers are optional, checked with `hasattr`.
- `src/core/action_factory.py` — at import time it scans `src/actions/*.py` and registers each `Action` subclass under its **module filename** (lowercased). The registry key is matched against the **last dot-segment of the action UUID** from the manifest, so `com.drohack.streamdock.tools.gif` → `src/actions/gif.py`. Filename and UUID suffix must match exactly.
- `src/core/action.py` — base class with the outbound API (`set_title`, `set_image` (base64 data URL), `set_state`, `set_settings`, `send_to_property_inspector`, …).
- `src/core/timer.py` — single shared background thread; `plugin.timer.set_interval(uuid, ms, callback)` / `clear_interval(uuid)`. Actions use per-context uuids (e.g. `f'app_volume_update_{context}'`) and must clear them in `on_will_disappear`.

### Property inspectors

`propertyInspector/<action>/index.html` + `index.js`, sharing `static/action.js` which provides the `$websocket` global (`saveData`, `sendToPlugin`, `setGlobalSettings`) and expects a `$propEvent` object of handlers (`didReceiveSettings`, `sendToPropertyInspector`, …). PI ↔ backend messaging: JS `sendToPlugin` → Python `on_send_to_plugin(payload)`; Python `send_to_property_inspector(payload)` → JS `$propEvent.sendToPropertyInspector(data)`.

### Adding a new action — full checklist

1. `src/actions/<name>.py` with an `Action` subclass (auto-registered by filename).
2. `manifest.json`: new entry in `Actions` with `UUID` ending `.<name>` and a `PropertyInspectorPath`.
3. `propertyInspector/<name>/index.html` + `index.js`.
4. New third-party imports → add to `requirements.txt` **and** to `hiddenimports` in `main.spec` — `action_factory` loads action modules via `importlib`, so PyInstaller's static analysis misses anything imported only from `src/actions/` and silently omits it from the exe.
5. Rebuild (`pyinstaller main.spec`) and redeploy.

### Frozen-vs-dev path handling

Code distinguishes environments with `getattr(sys, 'frozen', False)`. Bundled Python sources unpack to `sys._MEIPASS`; runtime assets that live in the plugin folder (e.g. gifs in `static/gifs/` for the Gif action) are resolved relative to `os.path.dirname(sys.executable)` — i.e. next to the exe inside the deployed `.sdPlugin` folder. Follow the same pattern for any new file access.

### Windows specifics

Audio actions use pycaw/comtypes (COM): call `CoInitialize()` in the action's `__init__` (see `app_volume.py`). App icons are extracted via raw ctypes `user32`/`gdi32` calls. Everything volume-related is Windows-only by design.

## Repo quirks

- `com.mirabox.streamdock.time.sdPlugin/` is the untracked upstream SDK example — ignore it.
- `com.drohack.streamdock.tools.sdPlugin/DrohackPlugin.exe` is a build artifact committed into the bundle; the source of truth is `dist/` after a rebuild.
- StreamDock SDK event reference: https://sdk.key123.vip/en/guide/events-received.html (see also `propertyInspector/readme.md` for sdpi HTML snippets).
